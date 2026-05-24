//! CSS Properties and Values API Level 1 — W3C CSS Properties
//!
//! Implements strict parsing bounds for Custom Properties (Houdini):
//!   - `@property` rule (§ 2): Registering strictly typed variables
//!   - Syntax parsing: `<color>`, `<length>`, `<angle>`, etc.
//!   - `initial-value` constraint fallback matrices
//!   - AI-facing: Houdini Type-Safe Variable geometric limits

use std::collections::HashMap;

/// Strict topological definitions of allowed CSS types bounding interpolation engines
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CssSyntaxDefinition {
    Universal, // "*"
    Length,    // "<length>"
    Color,     // "<color>"
    Angle,     // "<angle>"
    Time,      // "<time>"
    Percentage,// "<percentage>"
    CustomIdent(String),
}

/// Logical bounds capturing the registration limits of a `@property`
#[derive(Debug, Clone)]
pub struct CustomPropertyRegistration {
    pub name: String,
    pub syntax: Vec<CssSyntaxDefinition>,
    pub inherits: bool,
    pub initial_value: Option<String>,
}

/// The global Constraint Resolver bridging Custom CSS Variables into natively typed Animation / Transition targets
pub struct CssPropertiesValues1Engine {
    // Variable Name -> Strict Registration Bounds
    pub registered_properties: HashMap<String, CustomPropertyRegistration>,
    pub total_strict_type_enforcements: u64,
}

impl CssPropertiesValues1Engine {
    pub fn new() -> Self {
        Self {
            registered_properties: HashMap::new(),
            total_strict_type_enforcements: 0,
        }
    }

    /// Executed by CSS Parser upon encountering `@property --foo { syntax: '<color>'; }`
    /// Or JS executing `CSS.registerProperty({ name: '--foo', syntax: '<color>' })`
    pub fn register_strict_custom_property(&mut self, name: &str, syntax: Vec<CssSyntaxDefinition>, inherits: bool, initial: Option<&str>) {
        self.registered_properties.insert(name.to_string(), CustomPropertyRegistration {
            name: name.to_string(),
            syntax,
            inherits,
            initial_value: initial.map(|s| s.to_string()),
        });
    }

    /// Evaluator executed by the Compute phase when assigning a variable.
    /// If `--foo` is registered as `<color>`, assigning `10px` immediately aborts yielding the initial-value fallback.
    pub fn validate_and_compute_variable(&mut self, name: &str, declared_value: &str) -> Result<String, String> {
        if let Some(reg) = self.registered_properties.get(name) {
            self.total_strict_type_enforcements += 1;
            
            // Simulating Strict Syntax Parsing
            return if reg.syntax.contains(&CssSyntaxDefinition::Universal) {
                Ok(declared_value.to_string())
            } else if reg.syntax.contains(&CssSyntaxDefinition::Length) && (declared_value.ends_with("px") || declared_value.ends_with("rem")) {
                Ok(declared_value.to_string())
            } else if reg.syntax.contains(&CssSyntaxDefinition::Color) && (declared_value.starts_with('#') || declared_value.starts_with("rgb")) {
                Ok(declared_value.to_string())
            } else {
                // Reject invalid value, utilize strict Houdini fallback limits
                reg.initial_value.clone().ok_or("TypeError: Fallback empty".into())
            };
        }
        
        // Native CSS variables (unregistered) act purely as token-streams
        Ok(declared_value.to_string())
    }

    /// AI-facing Houdini Variable Typings
    pub fn ai_properties_summary(&self) -> String {
        format!("🎨 CSS Properties & Values 1: Registered Custom Bounds: {} | Global Type Enforcements: {}", 
            self.registered_properties.len(), self.total_strict_type_enforcements)
    }
}
