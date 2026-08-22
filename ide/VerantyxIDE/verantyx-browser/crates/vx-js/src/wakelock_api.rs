//! Screen Wake Lock API — W3C Screen Wake Lock
//!
//! Implements mechanisms allowing web applications to prevent the screen from turning off:
//!   - `navigator.wakeLock.request('screen')` (§ 4): Acquiring a lock to keep the device active
//!   - WakeLockSentinel: Returned object used to release the lock (`release()`)
//!   - Document Visibility tracking: Locks are automatically evicted if the page is hidden (§ 5)
//!   - Battery heuristics integration preventing wake locks on low power
//!   - AI-facing: System resource retention topological mapping

use std::collections::HashMap;

/// The scope of the requested keep-awake lock (§ 3)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WakeLockType { Screen }

/// The representation of an active lock granted to a document (§ 4)
#[derive(Debug, Clone)]
pub struct WakeLockSentinel {
    pub lock_id: u64,
    pub lock_type: WakeLockType,
    pub is_released: bool,
}

/// The global Screen Wake Lock Engine interacting with the OS Display Daemon
pub struct WakeLockEngine {
    // Mapping document context to all active lock identifiers
    pub active_locks: HashMap<u64, Vec<WakeLockSentinel>>,
    pub next_lock_id: u64,
    pub is_battery_low_mode: bool, // Simulates OS low power state
}

impl WakeLockEngine {
    pub fn new() -> Self {
        Self {
            active_locks: HashMap::new(),
            next_lock_id: 1,
            is_battery_low_mode: false, // Default normal power
        }
    }

    /// JS execution: `navigator.wakeLock.request('screen')`
    pub fn request_wake_lock(&mut self, document_id: u64, lock_type: WakeLockType) -> Result<WakeLockSentinel, String> {
        // Battery saving mode enforces implicit rejection (§ 6)
        if self.is_battery_low_mode {
            return Err("NotAllowedError: Wake Lock is disabled during low battery mode".into());
        }

        let lock_id = self.next_lock_id;
        self.next_lock_id += 1;

        let sentinel = WakeLockSentinel {
            lock_id,
            lock_type,
            is_released: false,
        };

        let document_locks = self.active_locks.entry(document_id).or_default();
        document_locks.push(sentinel.clone());

        // Under the hood, this signals the platform compositor to discard idle-screen timers
        Ok(sentinel)
    }

    /// JS execution: `sentinel.release()`
    pub fn release_wake_lock(&mut self, document_id: u64, lock_id: u64) {
        if let Some(locks) = self.active_locks.get_mut(&document_id) {
            for lock in locks.iter_mut() {
                if lock.lock_id == lock_id {
                    lock.is_released = true;
                }
            }
            locks.retain(|l| !l.is_released);
        }
        // If system active_locks is entirely empty now, OS idle-timers resume
    }

    /// Page Lifecycle event execution (§ 5)
    pub fn page_visibility_changed(&mut self, document_id: u64, is_visible: bool) {
        if !is_visible {
            // "When the visibility state of the Document changes to 'hidden', release all wake locks"
            if let Some(locks) = self.active_locks.get_mut(&document_id) {
                for lock in locks.iter_mut() {
                    lock.is_released = true;
                }
                locks.clear();
            }
        }
    }

    /// AI-facing Screen Wake Lock orchestration summary
    pub fn ai_wake_lock_summary(&self, document_id: u64) -> String {
        let count = match self.active_locks.get(&document_id) {
            Some(locks) => locks.len(),
            None => 0,
        };
        format!("🔋 Screen Wake Lock API (Doc #{}): {} Active Locks | OS Powersave Constraint: {}", 
            document_id, count, self.is_battery_low_mode)
    }
}
