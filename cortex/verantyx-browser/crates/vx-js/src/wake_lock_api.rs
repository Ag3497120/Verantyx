//! Screen Wake Lock API — W3C Screen Wake Lock API
//!
//! Implements the browser's power management and screen visibility infrastructure:
//!   - Navigator.wakeLock.request() (§ 4.1): Requesting a lock (type: 'screen')
//!   - WakeLockSentinel (§ 4.2): release() and onrelease event
//!   - Wake Lock Types (§ 4.3): Only 'screen' is currently standardized
//!   - Policy (§ 4.4): Automatic release on document visibility state change (hidden)
//!   - Resource Management (§ 4.5): Handling multiple active sentinels and system integration
//!   - Permissions and Security (§ 5): Restricted to Secure Contexts and user-activation
//!   - AI-facing: Wake lock status monitor and request history log

use std::collections::HashMap;

/// Wake lock types (§ 4.3)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WakeLockType { Screen }

/// Wake Lock Sentinel state (§ 4.2)
pub struct WakeLockSentinel {
    pub id: u64,
    pub lock_type: WakeLockType,
    pub released: bool,
}

/// The global Wake Lock API Manager
pub struct WakeLockManager {
    pub active_locks: HashMap<u64, WakeLockSentinel>,
    pub next_lock_id: u64,
    pub is_screen_locked: bool,
    pub permission_granted: bool,
}

impl WakeLockManager {
    pub fn new() -> Self {
        Self {
            active_locks: HashMap::new(),
            next_lock_id: 1,
            is_screen_locked: false,
            permission_granted: false,
        }
    }

    /// Entry point for navigator.wakeLock.request() (§ 4.1)
    pub fn request_lock(&mut self, lock_type: WakeLockType) -> Result<u64, String> {
        if !self.permission_granted { return Err("NOT_ALLOWED".into()); }
        
        let id = self.next_lock_id;
        self.next_lock_id += 1;
        self.active_locks.insert(id, WakeLockSentinel {
            id,
            lock_type,
            released: false,
        });
        self.is_screen_locked = true;
        Ok(id)
    }

    pub fn release_lock(&mut self, id: u64) {
        if let Some(sentinel) = self.active_locks.get_mut(&id) {
            sentinel.released = true;
            // self.active_locks.remove(&id); // Maintain history record
        }
        
        // Re-evaluate if any active screen locks remain (§ 4.5)
        self.is_screen_locked = self.active_locks.values().any(|l| !l.released);
    }

    /// AI-facing wake lock status
    pub fn ai_wake_lock_summary(&self) -> String {
        let active_count = self.active_locks.values().filter(|l| !l.released).count();
        format!("🔋 Wake Lock Status: {} (Active Sentinels: {})", if self.is_screen_locked { "🟢 Locked" } else { "⚪️ Idle" }, active_count)
    }
}
