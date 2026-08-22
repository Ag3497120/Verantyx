//! Idle Detection API — W3C Idle Detection
//!
//! Implements hardware presence mapping for user away mechanics:
//!   - `IdleDetector` (§ 9): Polling the OS for keyboard/mouse logic timeouts
//!   - UserState (`active`, `idle`) and ScreenState (`locked`, `unlocked`)
//!   - Permissions mediated execution (`navigator.permissions.query({name: 'idle-detection'})`)
//!   - AI-facing: User somatic presence tracker

use std::collections::HashMap;

/// Denotes the interaction state of the human using the input hardware (§ 4)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum UserState { Active, Idle }

/// Denotes the OS-level screen protection state (§ 4)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ScreenState { Unlocked, Locked }

/// A recorded state of OS idleness
#[derive(Debug, Clone)]
pub struct IdleStateRecord {
    pub user: UserState,
    pub screen: ScreenState,
    pub last_active_epoch_ms: u64,
}

/// A specific bound JS observer threshold configuration
#[derive(Debug, Clone)]
pub struct IdleObserver {
    pub threshold_ms: u64, // The amount of time until the JS considers the user 'idle'
    pub current_emitted_state: Option<UserState>,
}

/// The global Idle Engine bridging OS screen savers to web apps
pub struct IdleDetectionEngine {
    // Current Global Hardware State
    pub global_state: IdleStateRecord,

    // Document ID -> (Observer ID -> Observer constraints)
    pub observers: HashMap<u64, HashMap<u64, IdleObserver>>,
    pub total_state_changes_emitted: u64,
}

impl IdleDetectionEngine {
    pub fn new() -> Self {
        Self {
            global_state: IdleStateRecord {
                user: UserState::Active,
                screen: ScreenState::Unlocked,
                last_active_epoch_ms: 0,
            },
            observers: HashMap::new(),
            total_state_changes_emitted: 0,
        }
    }

    /// JS execution: `await detector.start({ threshold: 60000 })` (§ 9.2)
    pub fn bind_observer(&mut self, document_id: u64, observer_id: u64, threshold_ms: u64) {
        let obs = self.observers.entry(document_id).or_default();
        obs.insert(observer_id, IdleObserver {
            threshold_ms,
            current_emitted_state: None,
        });
    }

    /// Executed continuously by an OS polling thread (evaluating native mouse movements)
    pub fn poll_hardware_state(&mut self, current_epoch_ms: u64, os_locked: bool, native_user_active: bool) {
        self.global_state.screen = if os_locked { ScreenState::Locked } else { ScreenState::Unlocked };
        
        if native_user_active {
            self.global_state.user = UserState::Active;
            self.global_state.last_active_epoch_ms = current_epoch_ms;
        }

        let time_since_active = current_epoch_ms.saturating_sub(self.global_state.last_active_epoch_ms);

        // Notify active observers
        for doc_obs in self.observers.values_mut() {
            for obs in doc_obs.values_mut() {
                let computed_state = if time_since_active >= obs.threshold_ms || os_locked {
                    UserState::Idle
                } else {
                    UserState::Active
                };

                if obs.current_emitted_state != Some(computed_state) {
                    obs.current_emitted_state = Some(computed_state);
                    self.total_state_changes_emitted += 1;
                    // In a real engine, this queues a DOM Event on the IdleDetector instance
                }
            }
        }
    }

    /// AI-facing Hardware Presence topologicial mapper
    pub fn ai_idle_detection_summary(&self, document_id: u64) -> String {
        let count = self.observers.get(&document_id).map_or(0, |o| o.len());
        format!("😴 Idle Detection API (Doc #{}): {} Tracking Observers | Global Hardware State: {:?} / {:?} | Events Emitted: {}", 
            document_id, count, self.global_state.user, self.global_state.screen, self.total_state_changes_emitted)
    }
}
