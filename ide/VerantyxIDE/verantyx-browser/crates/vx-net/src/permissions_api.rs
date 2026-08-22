//! Permissions API — W3C Permissions
//!
//! Implements a unified interface for checking, requesting, and revoking web platform permissions:
//!   - `navigator.permissions.query()` (§ 5): Querying the status of a specific API permission
//!   - Permission Names (§ 6): 'geolocation', 'notifications', 'push', 'midi', 'camera', 'microphone'
//!   - PermissionStatus (§ 7): 'granted', 'denied', 'prompt' states
//!   - Reacting to permission changes over time via the 'change' event
//!   - AI-facing: Permission state matrix reporting mapping capabilities

use std::collections::HashMap;

/// Standard W3C recognizable features that require permission mediation (§ 6)
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum PermissionName {
    Geolocation,
    Notifications,
    Push,
    Midi,
    Camera,
    Microphone,
    BackgroundSync,
    AmbientLightSensor,
    Accelerometer,
    Gyroscope,
    Magnetometer,
    ScreenWakeLock,
    Nfc,
    // Verantyx Appended AI Privileges
    AiSemanticMemory,
}

/// The resolution state of a permission granting flow (§ 7)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PermissionState { Granted, Denied, Prompt }

/// Central tracker for application privileges mapped by origin
pub struct PermissionsEngine {
    // Top-Level Origin -> (PermissionName -> State)
    pub origin_permissions: HashMap<String, HashMap<PermissionName, PermissionState>>,
    pub total_prompts_triggered: u64,
}

impl PermissionsEngine {
    pub fn new() -> Self {
        Self {
            origin_permissions: HashMap::new(),
            total_prompts_triggered: 0,
        }
    }

    /// JS execution: `navigator.permissions.query({ name: 'geolocation' })` (§ 5)
    pub fn query_permission(&self, origin: &str, permission: PermissionName) -> PermissionState {
        if let Some(perms) = self.origin_permissions.get(origin) {
            if let Some(state) = perms.get(&permission) {
                return *state;
            }
        }
        PermissionState::Prompt // Default W3C behavior for un-queried secure contexts
    }

    /// Executed whenever a site attempts an operation directly (e.g., `navigator.geolocation.getCurrentPosition()`)
    pub fn request_permission(&mut self, origin: &str, permission: PermissionName) -> PermissionState {
        let current_state = self.query_permission(origin, permission.clone());

        if current_state == PermissionState::Prompt {
            // Emulate OS-level or browser-level prompting logic
            self.total_prompts_triggered += 1;
            
            // For headless/AI mode, we reject high-privacy APIs by default unless explicitly whitelisted
            let new_state = match permission {
                PermissionName::BackgroundSync | PermissionName::ScreenWakeLock => PermissionState::Granted, // Harmless
                _ => PermissionState::Denied, // High-sec APIs fail silently
            };

            let perms = self.origin_permissions.entry(origin.to_string()).or_default();
            perms.insert(permission, new_state);
            return new_state;
        }

        current_state
    }

    /// AI-facing Permissions matrix configuration
    pub fn ai_permissions_summary(&self, origin: &str) -> String {
        if let Some(perms) = self.origin_permissions.get(origin) {
            let mut report = format!("🔐 Permissions API (Origin: {}) [Prompts Triggered: {}]:\n", origin, self.total_prompts_triggered);
            for (name, state) in perms {
                report.push_str(&format!("  - {:?}: {:?}\n", name, state));
            }
            report
        } else {
            format!("Origin {} has requested zero permissions. All default to Prompt.", origin)
        }
    }
}
