//! Keyboard Map API — W3C Keyboard Map
//!
//! Implements hardware keyboard mapping resolution for web applications:
//!   - `navigator.keyboard.getLayoutMap()` (§ 2): Emitting OS physical key configurations
//!   - KeyboardLayoutMap Map-like interface mapping physical hardware scancodes to standard strings
//!   - Layout variants tracking (e.g. QWERTY vs AZERTY vs Dvorak logic)
//!   - High-entropy privacy mitigation (User interaction / Secure Context limits)
//!   - AI-facing: OS mapping hardware topology metrics

use std::collections::HashMap;

/// The structure representing a hardware character emitted by a scancode based on OS locale
#[derive(Debug, Clone)]
pub struct KeyMapping {
    pub hardware_code: String, // e.g. "KeyQ"
    pub local_char: String,    // e.g. "q" (QWERTY) or "a" (AZERTY)
}

/// The global Keyboard Map Engine bridging OS HID logic to browser JS
pub struct KeyboardMapEngine {
    // Current OS-level layout mapping matrix
    pub layout_mapping: HashMap<String, String>, // HardwareCode -> Char (e.g., "KeyQ" -> "q")
    pub is_secure_context: bool,
    pub has_user_activation: bool,
    pub privacy_protection_active: bool,
}

impl KeyboardMapEngine {
    pub fn new() -> Self {
        let mut default_qwerty = HashMap::new();
        default_qwerty.insert("KeyQ".to_string(), "q".to_string());
        default_qwerty.insert("KeyW".to_string(), "w".to_string());
        default_qwerty.insert("KeyA".to_string(), "a".to_string());
        default_qwerty.insert("KeyZ".to_string(), "z".to_string());
        // Default physical mapping configuration

        Self {
            layout_mapping: default_qwerty,
            is_secure_context: true,
            has_user_activation: false,
            privacy_protection_active: true, // W3C recommends protecting hardware entropy
        }
    }

    /// Triggers OS hardware context updates to emulate physical language switching
    pub fn mock_switch_to_azerty(&mut self) {
        let mut azerty = HashMap::new();
        azerty.insert("KeyQ".to_string(), "a".to_string());
        azerty.insert("KeyW".to_string(), "z".to_string());
        azerty.insert("KeyA".to_string(), "q".to_string());
        azerty.insert("KeyZ".to_string(), "w".to_string());
        self.layout_mapping = azerty;
    }

    /// JS execution: `navigator.keyboard.getLayoutMap()` (§ 2)
    pub fn get_layout_map(&self) -> Result<HashMap<String, String>, String> {
        if !self.is_secure_context {
            return Err("SecurityError: Keyboard Map requires a secure context (HTTPS)".into());
        }

        // Privacy Sandbox limits full keyboard layout access without transient activation
        if self.privacy_protection_active && !self.has_user_activation {
            return Err("SecurityError: Cannot access keyboard layout without user transient activation".into());
        }

        Ok(self.layout_mapping.clone())
    }

    /// Resolves `KeyboardEvent.code` to what the printed character `KeyboardEvent.key` should be based on OS map
    pub fn resolve_event_key(&self, event_code: &str) -> String {
        self.layout_mapping.get(event_code).cloned().unwrap_or_else(|| event_code.to_string())
    }

    /// AI-facing Keyboard Hardware geometric topology
    pub fn ai_keyboard_map_summary(&self) -> String {
        format!("⌨️ Keyboard Map API: Hardware-Locale configuration holds {} mapped codes (Secure: {}, User Act: {})", 
            self.layout_mapping.len(), self.is_secure_context, self.has_user_activation)
    }
}
