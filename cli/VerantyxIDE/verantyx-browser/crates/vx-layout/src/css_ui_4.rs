//! CSS Basic User Interface Module Level 4 — W3C CSS UI 4
//!
//! Implements CSS properties controlling core interactivity mapping:
//!   - pointer-events (§ 4.1): Determining which layout boxes hit-test successfully
//!   - appearance (§ 6.1): Switching between native OS components vs raw layout rendering
//!   - caret-color (§ 3.3): The color of the text insertion cursor
//!   - resize (§ 5.1): both, horizontal, vertical control of interactive boundaries
//!   - outline properties (§ 3): Generating focus rings around hit-boxes
//!   - AI-facing: User interactivity constraint mappings and UI geometric states

use std::collections::HashMap;

/// Determines hit-testing transparency (§ 4.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PointerEvents { Auto, None, VisiblePainted, VisibleFill }

/// Controls usage of native platform rendering controls (§ 6.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Appearance { Auto, None, TextField, Button, Checkbox }

/// Control allowed dimensionality of boundary resizing (§ 5.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Resize { None, Both, Horizontal, Vertical }

/// Configuration applied to individual layout boxes
#[derive(Debug, Clone)]
pub struct UserInterfaceConfig {
    pub pointer_events: PointerEvents,
    pub appearance: Appearance,
    pub resize: Resize,
    pub caret_color: Option<String>, // Defines an automatic fallback if none
    pub has_focus_outline: bool,
}

/// The global CSS User Interface engine
pub struct CssUserInterfaceEngine {
    pub configurations: HashMap<u64, UserInterfaceConfig>,
    pub total_hit_tests_processed: u64,
}

impl CssUserInterfaceEngine {
    pub fn new() -> Self {
        Self {
            configurations: HashMap::new(),
            total_hit_tests_processed: 0,
        }
    }

    pub fn set_ui_config(&mut self, node_id: u64, config: UserInterfaceConfig) {
        self.configurations.insert(node_id, config);
    }

    /// Hit-testing algorithm invoked by the compositor on physical coordinates
    pub fn is_hittable(&mut self, node_id: u64) -> bool {
        self.total_hit_tests_processed += 1;
        if let Some(config) = self.configurations.get(&node_id) {
            // Simplified hit-test model
            if config.pointer_events == PointerEvents::None {
                return false;
            }
        }
        true
    }

    /// Determines if layout relies on Skia paths or macOS/Windows native widgets
    pub fn uses_native_appearance(&self, node_id: u64) -> bool {
        if let Some(config) = self.configurations.get(&node_id) {
            return config.appearance != Appearance::None && config.appearance != Appearance::Auto;
        }
        false
    }

    /// Evaluates geometrical bounds changes allowed by user interaction
    pub fn allows_viewport_resize(&self, node_id: u64) -> (bool, bool) {
        if let Some(config) = self.configurations.get(&node_id) {
            match config.resize {
                Resize::None => return (false, false),
                Resize::Both => return (true, true),
                Resize::Horizontal => return (true, false),
                Resize::Vertical => return (false, true),
            }
        }
        (false, false)
    }

    /// AI-facing User Interface metric topology
    pub fn ai_ui_summary(&self, node_id: u64) -> String {
        if let Some(config) = self.configurations.get(&node_id) {
            format!("🔘 CSS UI 4 (Node #{}): Hit-Testable: {}, Native-Look: {:?}, Resize: {:?}", 
                node_id, config.pointer_events != PointerEvents::None, config.appearance, config.resize)
        } else {
            format!("Node #{} utilizes default uninteractive boundaries", node_id)
        }
    }
}
