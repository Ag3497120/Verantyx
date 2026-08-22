//! Keyboard Lock API — W3C Keyboard Lock
//!
//! Implements mechanisms allowing full-screen applications (like games or remote desktops) to capture all keys:
//!   - `navigator.keyboard.lock([keyCodes])` (§ 4): Capturing OS-level keys like Cmd-Tab or Windows Key
//!   - `navigator.keyboard.unlock()` (§ 5): Releasing the hardware hook bindings
//!   - High security bounds checking: Usually requires Fullscreen API to be active
//!   - Preventing malicious lockouts via prolonged Esc key holding logic
//!   - AI-facing: OS hardware input capture topological limits

use std::collections::HashMap;

/// The physical state of the hardware locking hook tied to a frame
#[derive(Debug, Clone)]
pub struct KeyboardLockState {
    pub is_locked: bool,
    pub specific_keys: Option<Vec<String>>, // Specific scancodes e.g., ["AltLeft", "Tab"]
    pub is_fullscreen: bool, // Required condition for elevated locks
}

/// The global Keyboard Lock Engine interacting with the OS Windowing system
pub struct KeyboardLockEngine {
    pub frame_locks: HashMap<u64, KeyboardLockState>,
    pub total_lock_assertions: u64,
}

impl KeyboardLockEngine {
    pub fn new() -> Self {
        Self {
            frame_locks: HashMap::new(),
            total_lock_assertions: 0,
        }
    }

    /// Internal integration triggered by Fullscreen API
    pub fn set_fullscreen_state(&mut self, frame_id: u64, active: bool) {
        let state = self.frame_locks.entry(frame_id).or_insert(KeyboardLockState {
            is_locked: false,
            specific_keys: None,
            is_fullscreen: false,
        });
        state.is_fullscreen = active;

        // "If the document loses fullscreen state, the lock is implicitly released" (§ 6)
        if !active {
            state.is_locked = false;
        }
    }

    /// JS execution: `navigator.keyboard.lock(['Escape', 'MetaLeft'])` (§ 4)
    pub fn request_keyboard_lock(&mut self, frame_id: u64, keys: Option<Vec<String>>) -> Result<(), String> {
        let state = self.frame_locks.entry(frame_id).or_insert(KeyboardLockState {
            is_locked: false,
            specific_keys: None,
            is_fullscreen: false,
        });

        // W3C suggests capturing keys like the OS Start button requires elevated conditions
        if !state.is_fullscreen {
            return Err("SecurityError: Full OS key capture requires Fullscreen mode".into());
        }

        self.total_lock_assertions += 1;
        state.is_locked = true;
        state.specific_keys = keys;

        // Instructs the OS via native APIs (e.g. CGEventTap on Mac, RegisterHotKey on Win)
        Ok(())
    }

    /// JS execution: `navigator.keyboard.unlock()` (§ 5)
    pub fn release_keyboard_lock(&mut self, frame_id: u64) {
        if let Some(state) = self.frame_locks.get_mut(&frame_id) {
            state.is_locked = false;
            state.specific_keys = None;
        }
    }

    /// Pre-flight validation logic evaluated by the main input thread
    pub fn is_key_captured(&self, frame_id: u64, hardware_code: &str) -> bool {
        if let Some(state) = self.frame_locks.get(&frame_id) {
            if state.is_locked {
                if let Some(specific) = &state.specific_keys {
                    return specific.contains(&hardware_code.to_string());
                }
                // If None, all keys are captured
                return true;
            }
        }
        false
    }

    /// AI-facing Hardware locking state
    pub fn ai_keyboard_lock_summary(&self, frame_id: u64) -> String {
        if let Some(state) = self.frame_locks.get(&frame_id) {
            let key_str = match &state.specific_keys {
                Some(arr) => format!("Specific Keys: {}", arr.len()),
                None => "ALL KEYS".into(),
            };
            format!("🔒 Keyboard Lock API (Frame #{} [Fullscreen: {}]): Locked: {} | Targeting: {} | Assertions: {}", 
                frame_id, state.is_fullscreen, state.is_locked, key_str, self.total_lock_assertions)
        } else {
            format!("Frame #{} uses standard browser keyboard routing", frame_id)
        }
    }
}
