//! Capture Handle API — W3C Capture Handle
//!
//! Implements secure geometric bounds for Screen Sharing telemetry:
//!   - `navigator.mediaDevices.setCaptureHandleConfig()` (§ 3): Exposing internal origin identity
//!   - Identifying when a tab is actively being broadcast over WebRTC
//!   - AI-facing: Cross-tab Broadcaster and Receiver Isolation boundaries

use std::collections::HashMap;

/// A payload containing strict string bounds proving ownership of the currently captured Tab
#[derive(Debug, Clone)]
pub struct CaptureHandlePayload {
    pub handle: String, // Up to 1024 characters
    pub permitted_origins: Vec<String>, // Contains CORS boundaries e.g. ["https://zoom.us"]
    pub expose_origin: bool,
}

/// The global Constraint Resolver governing OS Screen Capture privacy leak boundaries
pub struct CaptureHandleEngine {
    // Broadcasting Document ID -> Declared Info
    pub active_broadcasters: HashMap<u64, CaptureHandlePayload>,
    pub total_handle_exposures: u64,
}

impl CaptureHandleEngine {
    pub fn new() -> Self {
        Self {
            active_broadcasters: HashMap::new(),
            total_handle_exposures: 0,
        }
    }

    /// JS execution: `navigator.mediaDevices.setCaptureHandleConfig({ handle: "doc-123", permittedOrigins: ["*"] });`
    pub fn set_capture_config(&mut self, document_id: u64, payload: Option<CaptureHandlePayload>) -> Result<(), String> {
        if let Some(config) = payload {
            if config.handle.len() > 1024 {
                return Err("TypeError: Handle string exceeds 1024 character buffer".into());
            }
            self.active_broadcasters.insert(document_id, config);
        } else {
            self.active_broadcasters.remove(&document_id);
        }
        Ok(())
    }

    /// Executed by `getDisplayMedia()` capturing a specific Tab.
    /// Checks if the captured Tab allows the Capturing Tab to see its internal identity.
    pub fn evaluate_handle_exposure(&mut self, captured_doc_id: u64, receiver_origin: &str) -> Option<CaptureHandlePayload> {
        if let Some(payload) = self.active_broadcasters.get(&captured_doc_id).cloned() {
            
            // Check cross-origin boundaries
            if payload.permitted_origins.contains(&"*".to_string()) || payload.permitted_origins.contains(&receiver_origin.to_string()) {
                self.total_handle_exposures += 1;
                return Some(payload);
            }
        }
        None
    }

    /// AI-facing Screen Sharer Identity extraction
    pub fn ai_capture_handle_summary(&self, document_id: u64) -> String {
        if let Some(payload) = self.active_broadcasters.get(&document_id) {
            format!("🎥 Capture Handle API (Doc #{}): Exposing ID: '{}' | Allowed Origins: {} | Global Handle Reconciliations: {}", 
                document_id, payload.handle, payload.permitted_origins.len(), self.total_handle_exposures)
        } else {
            format!("Doc #{} maintains strict opaque origin privacy during OS-level tab screen capturing", document_id)
        }
    }
}
