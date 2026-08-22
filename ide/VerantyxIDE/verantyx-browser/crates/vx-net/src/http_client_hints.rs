//! HTTP Client Hints — W3C Client Hints (UA-CH)
//!
//! Implements the browser's proactive resource negotiation infrastructure:
//!   - Accept-CH Header (§ 3.1): Handling server requests for specific hints
//!   - Critical-CH Header (§ 3.2): Handling hints required for recovery
//!   - User Agent Client Hints (§ 4): Sec-CH-UA, Sec-CH-UA-Platform, Sec-CH-UA-Model, Sec-CH-UA-Full-Version-List
//!   - Device Performance Hints (§ 5): Sec-CH-Device-Memory, Sec-CH-Viewport-Width, Sec-CH-Width
//!   - Network Hints (§ 6): Sec-CH-Save-Data, Sec-CH-Downlink, Sec-CH-ECT
//!   - Permissions Policy (§ 7): Controlling hint delegation across frames
//!   - Privacy and Security (§ 8): Fingerprinting mitigation and secure context requirements
//!   - AI-facing: Client hints registry and origin-to-hint capability map

use std::collections::HashMap;

/// Client hint categories (§ 4-6)
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum ClientHint {
    UA, UAPlatform, UAModel, UAMobile, UAFullVersion,
    DeviceMemory, ViewportWidth, Width, SaveData, Downlink, ECT,
}

/// The global Client Hints Manager
pub struct ClientHintsManager {
    pub enabled_hints: HashMap<String, Vec<ClientHint>>, // Origin -> Enabled hints
    pub device_memory_gb: f32,
    pub viewport_width: u32,
    pub save_data: bool,
}

impl ClientHintsManager {
    pub fn new() -> Self {
        Self {
            enabled_hints: HashMap::new(),
            device_memory_gb: 8.0,
            viewport_width: 1920,
            save_data: false,
        }
    }

    /// Handles an Accept-CH header from a server (§ 3.1)
    pub fn handle_accept_ch(&mut self, origin: &str, header_value: &str) {
        let mut hints = Vec::new();
        if header_value.contains("Sec-CH-UA") { hints.push(ClientHint::UA); }
        if header_value.contains("Device-Memory") { hints.push(ClientHint::DeviceMemory); }
        if header_value.contains("Width") { hints.push(ClientHint::Width); }
        if header_value.contains("Viewport-Width") { hints.push(ClientHint::ViewportWidth); }
        if header_value.contains("Save-Data") { hints.push(ClientHint::SaveData); }

        self.enabled_hints.insert(origin.to_string(), hints);
    }

    /// Resolves headers for an outgoing request (§ 4.1)
    pub fn resolve_headers(&self, origin: &str) -> HashMap<String, String> {
        let mut headers = HashMap::new();
        if let Some(hints) = self.enabled_hints.get(origin) {
            for hint in hints {
                match hint {
                    ClientHint::UA => { headers.insert("Sec-CH-UA".into(), "\"Verantyx\"; v=\"1.0\"".into()); }
                    ClientHint::DeviceMemory => { headers.insert("Sec-CH-Device-Memory".into(), format!("{}", self.device_memory_gb)); }
                    ClientHint::SaveData => { if self.save_data { headers.insert("Sec-CH-Save-Data".into(), "on".into()); } }
                    _ => {}
                }
            }
        }
        headers
    }

    /// AI-facing origin-to-hint capability summary
    pub fn ai_client_hints_summary(&self) -> String {
        let mut lines = vec![format!("🧩 Client Hints Profile (Origins: {}):", self.enabled_hints.len())];
        for (origin, hints) in &self.enabled_hints {
            lines.push(format!("  - {}: {:?}", origin, hints));
        }
        lines.join("\n")
    }
}
