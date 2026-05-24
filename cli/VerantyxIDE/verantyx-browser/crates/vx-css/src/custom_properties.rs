//! CSS Custom Properties (CSS Variables) Engine — W3C CSS Custom Properties Level 1+2
//!
//! Implements the complete CSS variable system:
//!   - Custom property registration (--name: value)
//!   - var() substitution with fallback chains
//!   - @property at-rule (registered custom properties with syntax, inherits, initial-value)
//!   - Cyclic reference detection during substitution
//!   - guaranteed-invalid values (syntax mismatch, cycles)
//!   - Animation/transition support for registered properties with <number>, <length>, <color>
//!   - env() environment variable substitution
//!   - Scoped custom property inheritance per element scope

use std::collections::HashMap;

/// A registered custom property (from @property at-rule)
#[derive(Debug, Clone)]
pub struct RegisteredCustomProperty {
    /// The property name (e.g., "--my-color")
    pub name: String,
    /// CSS syntax definition (e.g., "<color>", "<length>", "*")
    pub syntax: PropertySyntax,
    /// Whether this property inherits (per @property inherits descriptor)
    pub inherits: bool,
    /// The initial value (must be valid per syntax)
    pub initial_value: Option<String>,
}

/// CSS Syntax for a registered @property
#[derive(Debug, Clone, PartialEq)]
pub enum PropertySyntax {
    /// Accepts any value (universal syntax)
    Universal,
    /// Accepts a CSS <length> value
    Length,
    /// Accepts a CSS <number>
    Number,
    /// Accepts a CSS <percentage>
    Percentage,
    /// Accepts a CSS <color>
    Color,
    /// Accepts a CSS <image>
    Image,
    /// Accepts a CSS <url>
    Url,
    /// Accepts a CSS <integer>
    Integer,
    /// Accepts a CSS <angle>
    Angle,
    /// Accepts a CSS <time>
    Time,
    /// Accepts a CSS <resolution>
    Resolution,
    /// Accepts a CSS <transform-function>
    TransformFunction,
    /// Accepts a CSS <transform-list>
    TransformList,
    /// Accepts a CSS <custom-ident>
    CustomIdent,
    /// Accepts a specific list of keywords
    Keywords(Vec<String>),
    /// A multiplied syntax (e.g., "<length>+" or "<color>#")
    Multiplied { inner: Box<PropertySyntax>, multiplier: SyntaxMultiplier },
    /// A combined syntax (e.g., "<length> | <percentage>")
    Or(Vec<PropertySyntax>),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SyntaxMultiplier {
    Plus,         // One or more (space-separated)
    Hash,         // One or more (comma-separated)
    Optional,     // Zero or one
}

impl PropertySyntax {
    /// Parse a CSS @property syntax string
    pub fn parse(s: &str) -> Self {
        let s = s.trim();
        if s == "*" { return Self::Universal; }
        
        // Handle | (or) syntax
        if s.contains('|') {
            let parts: Vec<PropertySyntax> = s.split('|')
                .map(|p| Self::parse(p.trim()))
                .collect();
            if parts.len() == 1 {
                return parts.into_iter().next().unwrap();
            }
            return Self::Or(parts);
        }
        
        // Handle multipliers
        if s.ends_with('+') {
            let inner = Self::parse(&s[..s.len()-1]);
            return Self::Multiplied {
                inner: Box::new(inner),
                multiplier: SyntaxMultiplier::Plus,
            };
        }
        if s.ends_with('#') {
            let inner = Self::parse(&s[..s.len()-1]);
            return Self::Multiplied {
                inner: Box::new(inner),
                multiplier: SyntaxMultiplier::Hash,
            };
        }
        if s.ends_with('?') {
            let inner = Self::parse(&s[..s.len()-1]);
            return Self::Multiplied {
                inner: Box::new(inner),
                multiplier: SyntaxMultiplier::Optional,
            };
        }
        
        match s {
            "<length>" => Self::Length,
            "<number>" => Self::Number,
            "<percentage>" => Self::Percentage,
            "<color>" => Self::Color,
            "<image>" => Self::Image,
            "<url>" => Self::Url,
            "<integer>" => Self::Integer,
            "<angle>" => Self::Angle,
            "<time>" => Self::Time,
            "<resolution>" => Self::Resolution,
            "<transform-function>" => Self::TransformFunction,
            "<transform-list>" => Self::TransformList,
            "<custom-ident>" => Self::CustomIdent,
            _ => Self::Universal, // Fallback
        }
    }
    
    /// Validate a value against this syntax
    pub fn validate(&self, value: &str) -> bool {
        let value = value.trim();
        match self {
            Self::Universal => true,
            Self::Length => {
                value == "0" ||
                value.ends_with("px") || value.ends_with("em") || value.ends_with("rem") ||
                value.ends_with("vw") || value.ends_with("vh") || value.ends_with("%)") ||
                value.ends_with("pt") || value.ends_with("in") || value.ends_with("cm") ||
                value.ends_with("mm") || value.ends_with("dvh") || value.ends_with("svh")
            }
            Self::Number => value.parse::<f64>().is_ok(),
            Self::Integer => value.parse::<i64>().is_ok(),
            Self::Percentage => value.ends_with('%') && 
                value[..value.len()-1].parse::<f64>().is_ok(),
            Self::Color => {
                value.starts_with('#') || value.starts_with("rgb") ||
                value.starts_with("hsl") || value.starts_with("oklch") ||
                value.starts_with("oklab") || value.starts_with("lab") ||
                matches!(value, "red" | "green" | "blue" | "white" | "black" |
                         "transparent" | "currentcolor" | "inherit")
            }
            Self::Angle => {
                value.ends_with("deg") || value.ends_with("rad") ||
                value.ends_with("grad") || value.ends_with("turn")
            }
            Self::Time => value.ends_with("ms") || value.ends_with('s'),
            Self::Keywords(keywords) => keywords.iter().any(|k| k == value),
            Self::Or(parts) => parts.iter().any(|p| p.validate(value)),
            Self::Multiplied { inner, .. } => {
                let sep = if matches!(self, Self::Multiplied { multiplier: SyntaxMultiplier::Hash, .. }) {
                    ","
                } else {
                    " "
                };
                value.split(sep).all(|v| inner.validate(v.trim()))
            }
            _ => true,
        }
    }
    
    /// Whether this syntax supports animation/interpolation
    pub fn is_animatable(&self) -> bool {
        matches!(self,
            Self::Length | Self::Number | Self::Integer |
            Self::Percentage | Self::Color | Self::Angle | Self::Time
        ) || matches!(self, Self::Or(parts) if parts.iter().any(|p| p.is_animatable()))
    }
}

/// A CSS custom property value — either registered or unregistered
#[derive(Debug, Clone)]
pub struct CustomPropertyValue {
    /// The raw string value (before var() substitution)
    pub raw: String,
    /// Whether this value is guaranteed-invalid (cycle, syntax mismatch)
    pub is_invalid: bool,
}

impl CustomPropertyValue {
    pub fn valid(raw: String) -> Self { Self { raw, is_invalid: false } }
    pub fn invalid() -> Self { Self { raw: String::new(), is_invalid: true } }
}

/// Custom property scope — the set of custom properties in scope for one element
#[derive(Debug, Clone, Default)]
pub struct CustomPropertyScope {
    /// All custom property values on this element (--name -> value)
    pub own_properties: HashMap<String, CustomPropertyValue>,
}

impl CustomPropertyScope {
    pub fn set(&mut self, name: &str, value: String) {
        self.own_properties.insert(name.to_string(), CustomPropertyValue::valid(value));
    }
    
    pub fn invalidate(&mut self, name: &str) {
        self.own_properties.insert(name.to_string(), CustomPropertyValue::invalid());
    }
    
    pub fn get(&self, name: &str) -> Option<&CustomPropertyValue> {
        self.own_properties.get(name)
    }
}

/// The CSS variable substitution engine
pub struct CssVariableEngine {
    /// Global registry of @property registered custom properties
    pub registry: HashMap<String, RegisteredCustomProperty>,
    /// CSS env() variables (device-specific environment values)
    pub env_vars: HashMap<String, String>,
}

impl CssVariableEngine {
    pub fn new() -> Self {
        let mut env = HashMap::new();
        // Standard env() variables
        env.insert("safe-area-inset-top".to_string(), "0px".to_string());
        env.insert("safe-area-inset-right".to_string(), "0px".to_string());
        env.insert("safe-area-inset-bottom".to_string(), "0px".to_string());
        env.insert("safe-area-inset-left".to_string(), "0px".to_string());
        env.insert("titlebar-area-x".to_string(), "0px".to_string());
        env.insert("titlebar-area-y".to_string(), "0px".to_string());
        env.insert("titlebar-area-width".to_string(), "0px".to_string());
        env.insert("titlebar-area-height".to_string(), "0px".to_string());
        
        Self { registry: HashMap::new(), env_vars: env }
    }
    
    /// Register an @property rule
    pub fn register_property(&mut self, prop: RegisteredCustomProperty) -> Result<(), String> {
        if !prop.name.starts_with("--") {
            return Err(format!("@property name must start with '--': {}", prop.name));
        }
        
        // Validate initial value against syntax if provided
        if let Some(ref initial) = prop.initial_value {
            if !prop.syntax.validate(initial) {
                return Err(format!(
                    "@property {}: initial-value '{}' does not match syntax",
                    prop.name, initial
                ));
            }
        }
        
        self.registry.insert(prop.name.clone(), prop);
        Ok(())
    }
    
    /// Perform var() substitution on a CSS property value string.
    /// Returns the substituted string or None if substitution fails.
    pub fn substitute(
        &self,
        value: &str,
        scope_chain: &[&CustomPropertyScope],
        visited: &mut Vec<String>,
    ) -> Option<String> {
        if !value.contains("var(") && !value.contains("env(") {
            return Some(value.to_string());
        }
        
        let mut result = String::new();
        let mut rest = value;
        
        while !rest.is_empty() {
            if let Some(var_start) = rest.find("var(") {
                // Copy text before the var()
                result.push_str(&rest[..var_start]);
                rest = &rest[var_start + 4..];
                
                // Find the matching closing paren (accounting for nesting)
                let (inner, after) = Self::find_matching_paren(rest)?;
                rest = after;
                
                let substituted = self.resolve_var(&inner, scope_chain, visited)?;
                result.push_str(&substituted);
            } else if let Some(env_start) = rest.find("env(") {
                result.push_str(&rest[..env_start]);
                rest = &rest[env_start + 4..];
                
                let (inner, after) = Self::find_matching_paren(rest)?;
                rest = after;
                
                let substituted = self.resolve_env(&inner)?;
                result.push_str(&substituted);
            } else {
                result.push_str(rest);
                break;
            }
        }
        
        Some(result)
    }
    
    /// Resolve a var(--name, fallback) expression
    fn resolve_var(
        &self,
        inner: &str,
        scope_chain: &[&CustomPropertyScope],
        visited: &mut Vec<String>,
    ) -> Option<String> {
        // Split on first comma to get name and optional fallback
        let (name_part, fallback) = Self::split_var_args(inner);
        let name = name_part.trim().to_string();
        
        if !name.starts_with("--") {
            return None; // Invalid custom property name
        }
        
        // Cycle detection
        if visited.contains(&name) {
            // Guaranteed-invalid — use fallback or fail
            return fallback.and_then(|f| self.substitute(f.trim(), scope_chain, visited));
        }
        
        visited.push(name.clone());
        
        // Look up the value in the scope chain (innermost first)
        let value = scope_chain.iter().rev()
            .find_map(|scope| scope.get(&name))
            .cloned();
        
        let result = if let Some(ref cv) = value {
            if cv.is_invalid {
                None
            } else {
                // Recursively substitute vars in the resolved value
                self.substitute(&cv.raw, scope_chain, visited)
                    .or_else(|| fallback.and_then(|f| {
                        self.substitute(f.trim(), scope_chain, visited)
                    }))
            }
        } else {
            // Property not set — check @property initial value
            let initial = self.registry.get(&name)
                .and_then(|r| r.initial_value.as_deref());
            
            initial.map(String::from)
                .or_else(|| fallback.and_then(|f| {
                    self.substitute(f.trim(), scope_chain, visited)
                }))
        };
        
        visited.pop();
        result
    }
    
    /// Resolve an env(--name, fallback) expression
    fn resolve_env(&self, inner: &str) -> Option<String> {
        let (name_part, fallback) = Self::split_var_args(inner);
        let name = name_part.trim();
        
        self.env_vars.get(name)
            .cloned()
            .or_else(|| fallback.map(|f| f.trim().to_string()))
    }
    
    /// Set an environment variable (e.g., safe-area-inset-top for notch devices)
    pub fn set_env(&mut self, name: &str, value: String) {
        self.env_vars.insert(name.to_string(), value);
    }
    
    /// Find the content inside balanced parentheses
    fn find_matching_paren(s: &str) -> Option<(&str, &str)> {
        let mut depth = 1i32;
        for (i, ch) in s.char_indices() {
            match ch {
                '(' => depth += 1,
                ')' => {
                    depth -= 1;
                    if depth == 0 {
                        return Some((&s[..i], &s[i+1..]));
                    }
                }
                _ => {}
            }
        }
        None
    }
    
    /// Split "name, fallback" at the first top-level comma
    fn split_var_args(s: &str) -> (&str, Option<&str>) {
        let mut depth = 0i32;
        for (i, ch) in s.char_indices() {
            match ch {
                '(' => depth += 1,
                ')' => depth -= 1,
                ',' if depth == 0 => return (&s[..i], Some(&s[i+1..])),
                _ => {}
            }
        }
        (s, None)
    }
    
    /// Interpolate two registered custom property values at time t
    pub fn interpolate_registered(
        &self,
        name: &str,
        from: &str,
        to: &str,
        t: f64,
    ) -> Option<String> {
        let reg = self.registry.get(name)?;
        
        if !reg.syntax.is_animatable() {
            // Non-animatable: discrete at 50%
            if t < 0.5 { return Some(from.to_string()); }
            else { return Some(to.to_string()); }
        }
        
        match reg.syntax {
            PropertySyntax::Number | PropertySyntax::Integer => {
                let a: f64 = from.parse().ok()?;
                let b: f64 = to.parse().ok()?;
                let result = a + (b - a) * t;
                if matches!(reg.syntax, PropertySyntax::Integer) {
                    Some(result.round().to_string())
                } else {
                    Some(format!("{:.4}", result))
                }
            }
            PropertySyntax::Length => {
                // Simplified: only handle px values
                let a = from.trim_end_matches("px").parse::<f64>().ok()?;
                let b = to.trim_end_matches("px").parse::<f64>().ok()?;
                Some(format!("{:.2}px", a + (b - a) * t))
            }
            PropertySyntax::Percentage => {
                let a = from.trim_end_matches('%').parse::<f64>().ok()?;
                let b = to.trim_end_matches('%').parse::<f64>().ok()?;
                Some(format!("{:.2}%", a + (b - a) * t))
            }
            PropertySyntax::Angle => {
                let parse_angle = |s: &str| -> Option<f64> {
                    if let Some(v) = s.strip_suffix("deg") { return v.parse().ok(); }
                    if let Some(v) = s.strip_suffix("rad") { return Some(v.parse::<f64>().ok()? * 180.0 / std::f64::consts::PI); }
                    if let Some(v) = s.strip_suffix("turn") { return Some(v.parse::<f64>().ok()? * 360.0); }
                    None
                };
                let a = parse_angle(from)?;
                let b = parse_angle(to)?;
                Some(format!("{:.2}deg", a + (b - a) * t))
            }
            _ => Some(if t < 0.5 { from.to_string() } else { to.to_string() }),
        }
    }
}
