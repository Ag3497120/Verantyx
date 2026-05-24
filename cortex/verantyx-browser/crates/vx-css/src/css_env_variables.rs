//! CSS Environment Variables Module Level 1 — W3C CSS Env Variables
//!
//! Implements strict OS Hardware boundaries into CSS parsing metrics:
//!   - `env(safe-area-inset-top)` (§ 2): Hardware Notch / Rounded Corner collision geometries
//!   - Support for custom fallback parsing arguments `env(custom-agent, 10px)`
//!   - AI-facing: OS Physical Screen Topology constraints

use std::collections::HashMap;

/// Maps a specific OS capability or screen geometry token
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum OsEnvironmentToken {
    SafeAreaInsetTop,
    SafeAreaInsetRight,
    SafeAreaInsetBottom,
    SafeAreaInsetLeft,
    KeyboardInsetTop,
    KeyboardInsetHeight,
    TitlebarAreaX,
    TitlebarAreaY,
    TitlebarAreaWidth,
    TitlebarAreaHeight,
}

/// The global Constraint Resolver governing physical device geometries fed directly into CSS calculations
pub struct CssEnvironmentVariablesEngine {
    // Current Physical Frame constraints (Mock values fed by Host OS)
    pub current_os_boundaries: HashMap<OsEnvironmentToken, f64>,
    pub total_env_resolutions: u64,
}

impl CssEnvironmentVariablesEngine {
    pub fn new() -> Self {
        let mut bounds = HashMap::new();
        // Assume default iPhone X style physical notch bounds 
        bounds.insert(OsEnvironmentToken::SafeAreaInsetTop, 44.0);
        bounds.insert(OsEnvironmentToken::SafeAreaInsetBottom, 34.0);
        bounds.insert(OsEnvironmentToken::SafeAreaInsetLeft, 0.0);
        bounds.insert(OsEnvironmentToken::SafeAreaInsetRight, 0.0);

        Self {
            current_os_boundaries: bounds,
            total_env_resolutions: 0,
        }
    }

    /// Evaluator executed when parsing `padding: env(safe-area-inset-top, 20px);`
    pub fn resolve_environment_variable(&mut self, var_name: &str, fallback_px: Option<f64>) -> f64 {
        self.total_env_resolutions += 1;
        
        let token = match var_name {
            "safe-area-inset-top" => Some(OsEnvironmentToken::SafeAreaInsetTop),
            "safe-area-inset-right" => Some(OsEnvironmentToken::SafeAreaInsetRight),
            "safe-area-inset-bottom" => Some(OsEnvironmentToken::SafeAreaInsetBottom),
            "safe-area-inset-left" => Some(OsEnvironmentToken::SafeAreaInsetLeft),
            "keyboard-inset-height" => Some(OsEnvironmentToken::KeyboardInsetHeight),
            _ => None,
        };

        if let Some(t) = token {
            if let Some(val) = self.current_os_boundaries.get(&t) {
                return *val;
            }
        }

        // Standard W3C Fallback
        fallback_px.unwrap_or(0.0)
    }
    
    /// Called by the host application (e.g. Android Activity resizing keyboard bounds)
    pub fn mutate_hardware_boundary(&mut self, token: OsEnvironmentToken, pixel_measure: f64) {
        self.current_os_boundaries.insert(token, pixel_measure);
    }

    /// AI-facing OS Physical Topologies
    pub fn ai_env_summary(&self) -> String {
        let top = self.current_os_boundaries.get(&OsEnvironmentToken::SafeAreaInsetTop).unwrap_or(&0.0);
        let bottom = self.current_os_boundaries.get(&OsEnvironmentToken::SafeAreaInsetBottom).unwrap_or(&0.0);
        
        format!("📱 CSS Environment Limits: Hardware Top Notch Margin: {}px | Hardware Bottom Swipe Area: {}px | Global ENV Injections: {}", 
            top, bottom, self.total_env_resolutions)
    }
}
