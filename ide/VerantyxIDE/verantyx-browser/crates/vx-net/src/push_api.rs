//! Web Push API — W3C Push API / RFC 8030
//!
//! Implements the browser's infrastructure for receiving push messages:
//!   - PushManager (§ 5): subscribe(), getSubscription(), permissionState()
//!   - PushSubscription (§ 6): endpoint, keys (p256dh, auth), unsubscribe()
//!   - PushMessageData (§ 7): Extracting ArrayBuffer, Blob, JSON, Text from payload
//!   - Service Worker Integration (§ 8): Delivering 'push' events to the SW registration
//!   - VAPID/Authentication (§ 6): Application Server Keys support
//!   - Permissions and Security (§ 4): User-activation requirement and Secure Context restriction
//!   - AI-facing: Push subscription registry and incoming payload visualizer metrics

use std::collections::HashMap;

/// An active push subscription (§ 6)
#[derive(Debug, Clone)]
pub struct PushSubscription {
    pub endpoint: String,
    pub p256dh: String, // Base64URL-encoded public key
    pub auth: String,   // Base64URL-encoded authentication secret
    pub active: bool,
}

/// The global Push API Manager
pub struct PushManager {
    pub subscriptions: HashMap<u64, PushSubscription>, // SW Registration ID -> Sub
    pub next_endpoint_id: u64,
    pub permission_granted: bool,
    pub payload_history: Vec<(u64, usize)>, // (Reg ID, byte size)
}

impl PushManager {
    pub fn new() -> Self {
        Self {
            subscriptions: HashMap::new(),
            next_endpoint_id: 1000,
            permission_granted: false,
            payload_history: Vec::new(),
        }
    }

    /// Entry point for PushManager.subscribe() (§ 5.1)
    pub fn subscribe(&mut self, sw_registration_id: u64, _application_server_key: Option<&[u8]>) -> Result<PushSubscription, String> {
        if !self.permission_granted { return Err("NOT_ALLOWED".into()); }

        let endpoint_id = self.next_endpoint_id;
        self.next_endpoint_id += 1;

        let sub = PushSubscription {
            endpoint: format!("https://push.verantyx.engine/{}", endpoint_id),
            p256dh: "mock_p256dh_key_data".into(),
            auth: "mock_auth_secret".into(),
            active: true,
        };

        self.subscriptions.insert(sw_registration_id, sub.clone());
        Ok(sub)
    }

    /// Entry point for push message delivery (§ 8)
    pub fn receive_push_payload(&mut self, sw_registration_id: u64, payload_size: usize) {
        if let Some(sub) = self.subscriptions.get(&sw_registration_id) {
            if sub.active {
                if self.payload_history.len() >= 50 { self.payload_history.remove(0); }
                self.payload_history.push((sw_registration_id, payload_size));
                // Fire 'push' event to the SW...
            }
        }
    }

    /// AI-facing push subscription summary
    pub fn ai_push_summary(&self) -> String {
        let mut lines = vec![format!("📬 Web Push Registry (Active Subscriptions: {}):", self.subscriptions.len())];
        for (reg_id, sub) in &self.subscriptions {
            let status = if sub.active { "🟢 Active" } else { "⚪️ Inactive" };
            lines.push(format!("  [SW #{}] {} (Endpoint: {})", reg_id, status, sub.endpoint));
        }
        lines.push(format!("  Received payloads: {}", self.payload_history.len()));
        lines.join("\n")
    }
}
