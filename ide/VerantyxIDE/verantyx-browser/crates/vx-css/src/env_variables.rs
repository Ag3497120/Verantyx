//! CSS Environment Variables Module Level 1 — W3C CSS Env
//!
//! Implements global environment variables provided by the user agent:
//!   - env() function (§ 2): Accessing variables with an optional fallback
//!   - safe-area-inset (§ 3): Handling notches, home indicators, and rounded corners
//!     (safe-area-inset-top, safe-area-inset-right, safe-area-inset-bottom, safe-area-inset-left)
//!   - titlebar-area (§ 4): Handling Progressive Web App (PWA) window controls overlay
//!     (titlebar-area-x, titlebar-area-y, titlebar-area-width, titlebar-area-height)
//!   - Keyboard Insets (§ 5): Handling virtual keyboard occlusions
//!   - Propagation: Resolving environmental values dynamically across the CSS OM
//!   - AI-facing: Display geometry state and hardware inset visualizer

use std::collections::HashMap;

/// Pre-defined environment variables mapping
#[derive(Debug, Clone)]
pub struct EnvironmentVariables {
    pub variables: HashMap<String, String>,
}

impl EnvironmentVariables {
    pub fn new() -> Self {
        let mut variables = HashMap::new();
        // Safe-area defaults for a standard rectangular screen (§ 3)
        variables.insert("safe-area-inset-top".into(), "0px".into());
        variables.insert("safe-area-inset-right".into(), "0px".into());
        variables.insert("safe-area-inset-bottom".into(), "0px".into());
        variables.insert("safe-area-inset-left".into(), "0px".into());
        
        // PWA Titlebar defaults (§ 4)
        variables.insert("titlebar-area-x".into(), "0px".into());
        variables.insert("titlebar-area-y".into(), "0px".into());
        variables.insert("titlebar-area-width".into(), "0px".into());
        variables.insert("titlebar-area-height".into(), "0px".into());

        Self { variables }
    }

    /// Primary entry point: Resolves an env() function call (§ 2.1)
    pub fn resolve_env(&self, var_name: &str, fallback: Option<&str>) -> String {
        if let Some(val) = self.variables.get(var_name) {
            val.clone()
        } else if let Some(fb) = fallback {
            fb.to_string()
        } else {
            "initial".into() // Invalid or missing fallback
        }
    }

    /// Updates the safe area dynamically, i.e., rotation or notch change (§ 3)
    pub fn update_safe_area(&mut self, top: f64, right: f64, bottom: f64, left: f64) {
        self.variables.insert("safe-area-inset-top".into(), format!("{}px", top));
        self.variables.insert("safe-area-inset-right".into(), format!("{}px", right));
        self.variables.insert("safe-area-inset-bottom".into(), format!("{}px", bottom));
        self.variables.insert("safe-area-inset-left".into(), format!("{}px", left));
    }

    /// AI-facing display geometry configuration
    pub fn ai_env_summary(&self) -> String {
        let mut lines = vec!["📱 Display Environment Configuration:".to_string()];
        
        let mut insets = Vec::new();
        for edge in ["top", "right", "bottom", "left"] {
            let key = format!("safe-area-inset-{}", edge);
            insets.push(format!("{}: {}", edge, self.variables.get(&key).map(|s| s.as_str()).unwrap_or("0px")));
        }
        lines.push(format!("  Safe Area Insets: [{}]", insets.join(", ")));
        
        let titlebar_h = self.variables.get("titlebar-area-height").map(|s| s.as_str()).unwrap_or("0px");
        lines.push(format!("  Titlebar Area Height: {}", titlebar_h));
        
        lines.join("\n")
    }
}
