//! CSS Custom Properties (Variables) — CSS Custom Properties for Cascading Variables Level 1

use std::collections::HashMap;

/// A map of CSS custom properties (--varname: value)
#[derive(Debug, Clone, Default)]
pub struct CssVariableMap {
    vars: HashMap<String, VarEntry>,
    // Inheritance chain (parent vars merged first)
    inherited: Option<Box<CssVariableMap>>,
}

#[derive(Debug, Clone)]
struct VarEntry {
    value: String,
    is_animation_tainted: bool,
    is_transition_tainted: bool,
}

impl CssVariableMap {
    pub fn new() -> Self { Self::default() }

    pub fn with_inherited(parent: CssVariableMap) -> Self {
        Self {
            vars: HashMap::new(),
            inherited: Some(Box::new(parent)),
        }
    }

    /// Set a custom property
    pub fn set(&mut self, name: &str, value: &str) {
        let name = normalize_var_name(name);
        self.vars.insert(name, VarEntry {
            value: value.to_string(),
            is_animation_tainted: false,
            is_transition_tainted: false,
        });
    }

    /// Get a custom property value, checking ancestors
    pub fn get(&self, name: &str) -> Option<&str> {
        let name = normalize_var_name(name);
        if let Some(entry) = self.vars.get(&name) {
            return Some(&entry.value);
        }
        if let Some(parent) = &self.inherited {
            return parent.get(&name);
        }
        None
    }

    /// Check if a var exists
    pub fn contains(&self, name: &str) -> bool {
        self.get(name).is_some()
    }

    /// Resolve a var() reference with optional fallback
    pub fn resolve(&self, name: &str, fallback: Option<&str>) -> Option<String> {
        match self.get(name) {
            Some(v) => Some(v.to_string()),
            None => fallback.map(|f| f.to_string()),
        }
    }

    /// Substitute all var() references in a CSS value string
    pub fn substitute(&self, value: &str) -> Result<String, VarError> {
        self.substitute_with_stack(value, &mut Vec::new())
    }

    fn substitute_with_stack<'a>(
        &'a self,
        value: &str,
        stack: &mut Vec<String>,
    ) -> Result<String, VarError> {
        if !value.contains("var(") {
            return Ok(value.to_string());
        }

        let mut result = String::with_capacity(value.len());
        let mut pos = 0;
        let bytes = value.as_bytes();

        while pos < bytes.len() {
            if value[pos..].starts_with("var(") {
                let start = pos + 4;
                let (args, end) = extract_balanced(&value[start..])
                    .ok_or_else(|| VarError::MalformedVar(value.to_string()))?;
                pos = start + end;

                // Split on first comma (not inside parentheses)
                let (var_name, fallback) = split_var_args(&args);
                let var_name = normalize_var_name(var_name.trim());

                // Circular reference check
                if stack.contains(&var_name) {
                    return Err(VarError::CircularReference(var_name));
                }

                match self.get(&var_name) {
                    Some(resolved) => {
                        stack.push(var_name);
                        let substituted = self.substitute_with_stack(resolved, stack)?;
                        stack.pop();
                        result.push_str(&substituted);
                    }
                    None => {
                        match fallback {
                            Some(fb) => {
                                stack.push(var_name);
                                let substituted = self.substitute_with_stack(fb.trim(), stack)?;
                                stack.pop();
                                result.push_str(&substituted);
                            }
                            None => {
                                // Invalid — var is unset
                                return Err(VarError::Unresolved(var_name));
                            }
                        }
                    }
                }
            } else {
                result.push(bytes[pos] as char);
                pos += 1;
            }
        }

        Ok(result)
    }

    /// Merge another map into this one (this takes precedence)
    pub fn merge(&mut self, other: &CssVariableMap) {
        for (k, v) in &other.vars {
            self.vars.entry(k.clone()).or_insert_with(|| v.clone());
        }
    }

    /// Get all variable names in this map (not inherited)
    pub fn keys(&self) -> impl Iterator<Item = &str> {
        self.vars.keys().map(|s| s.as_str())
    }

    /// Collect all vars including inherited
    pub fn all_vars(&self) -> HashMap<String, String> {
        let mut result = HashMap::new();
        if let Some(parent) = &self.inherited {
            result.extend(parent.all_vars());
        }
        for (k, v) in &self.vars {
            result.insert(k.clone(), v.value.clone());
        }
        result
    }
}

/// A helper type alias
pub type CustomProperties = CssVariableMap;

fn normalize_var_name(name: &str) -> String {
    let name = name.trim();
    if name.starts_with("--") {
        name.to_string()
    } else {
        format!("--{}", name)
    }
}

fn extract_balanced(s: &str) -> Option<(String, usize)> {
    let mut depth = 1;
    let mut result = String::new();
    for (i, ch) in s.char_indices() {
        match ch {
            '(' => { depth += 1; result.push(ch); }
            ')' => {
                depth -= 1;
                if depth == 0 {
                    return Some((result, i + 1));
                }
                result.push(ch);
            }
            _ => result.push(ch),
        }
    }
    None
}

fn split_var_args(s: &str) -> (&str, Option<&str>) {
    let mut depth = 0;
    for (i, ch) in s.char_indices() {
        match ch {
            '(' => depth += 1,
            ')' => depth -= 1,
            ',' if depth == 0 => {
                return (&s[..i], Some(&s[i+1..]));
            }
            _ => {}
        }
    }
    (s, None)
}

/// Error type for variable resolution
#[derive(Debug, Clone, thiserror::Error)]
pub enum VarError {
    #[error("Circular var() reference: {0}")]
    CircularReference(String),
    #[error("Unresolved var(): {0}")]
    Unresolved(String),
    #[error("Malformed var(): {0}")]
    MalformedVar(String),
}

/// Environment variables (env())
pub struct EnvVariables {
    vars: HashMap<String, String>,
}

impl EnvVariables {
    pub fn default_browser() -> Self {
        let mut vars = HashMap::new();
        // Safe area insets (for iOS/notch support)
        vars.insert("safe-area-inset-top".to_string(), "0px".to_string());
        vars.insert("safe-area-inset-right".to_string(), "0px".to_string());
        vars.insert("safe-area-inset-bottom".to_string(), "0px".to_string());
        vars.insert("safe-area-inset-left".to_string(), "0px".to_string());
        // Titlebar area
        vars.insert("titlebar-area-x".to_string(), "0px".to_string());
        vars.insert("titlebar-area-y".to_string(), "0px".to_string());
        vars.insert("titlebar-area-width".to_string(), "100%".to_string());
        vars.insert("titlebar-area-height".to_string(), "0px".to_string());
        // Keyboard inset
        vars.insert("keyboard-inset-top".to_string(), "0px".to_string());
        vars.insert("keyboard-inset-right".to_string(), "0px".to_string());
        vars.insert("keyboard-inset-bottom".to_string(), "0px".to_string());
        vars.insert("keyboard-inset-left".to_string(), "0px".to_string());
        vars.insert("keyboard-inset-width".to_string(), "0px".to_string());
        vars.insert("keyboard-inset-height".to_string(), "0px".to_string());
        Self { vars }
    }

    pub fn get(&self, name: &str) -> Option<&str> {
        self.vars.get(name).map(|s| s.as_str())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_set_and_get() {
        let mut map = CssVariableMap::new();
        map.set("--color", "red");
        assert_eq!(map.get("--color"), Some("red"));
    }

    #[test]
    fn test_substitute_simple() {
        let mut map = CssVariableMap::new();
        map.set("--primary", "#ff0000");
        let result = map.substitute("color: var(--primary)").unwrap();
        assert_eq!(result, "color: #ff0000");
    }

    #[test]
    fn test_substitute_with_fallback() {
        let map = CssVariableMap::new();
        let result = map.substitute("color: var(--missing, blue)").unwrap();
        assert_eq!(result, "color: blue");
    }

    #[test]
    fn test_circular_reference() {
        let mut map = CssVariableMap::new();
        map.set("--a", "var(--b)");
        map.set("--b", "var(--a)");
        let result = map.substitute("var(--a)");
        assert!(result.is_err());
    }

    #[test]
    fn test_inheritance() {
        let mut parent = CssVariableMap::new();
        parent.set("--brand", "blue");
        let child = CssVariableMap::with_inherited(parent);
        assert_eq!(child.get("--brand"), Some("blue"));
    }

    #[test]
    fn test_normalize_var_name() {
        assert_eq!(normalize_var_name("--foo"), "--foo");
        assert_eq!(normalize_var_name("foo"), "--foo");
    }
}
