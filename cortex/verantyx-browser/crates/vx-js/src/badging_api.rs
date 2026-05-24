//! Badging API — W3C Badging API
//!
//! Implements operating system agnostic notification counters usually shown on taskbars:
//!   - `navigator.setAppBadge(content)` (§ 3): Updating the application icon's numeric indicator
//!   - `navigator.clearAppBadge()` (§ 4): Clearing the indicator
//!   - Number constraints (`0` acts as clear, `> 0` displays counter)
//!   - Unspecified badge value (`setAppBadge()`) representing an indeterminate notification marker (e.g. a red dot)
//!   - Cross-domain isolation boundaries
//!   - AI-facing: Interaction badge state matrices tracking user attention requirements

use std::collections::HashMap;

/// The internal representation of an application badge state (§ 3.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AppBadgeState {
    None,            // No badge
    Flag,            // Indeterminate badge (e.g. simple red dot on iOS/Android)
    Number(u64),     // Explicit numeric counter
}

/// Details about a PWA's physical OS-dock status
#[derive(Debug, Clone)]
pub struct PwaBadgeRegistration {
    pub origin_scope: String,
    pub current_badge: AppBadgeState,
    pub install_status: bool, // Simulating if the app is actually installed to the OS
}

/// The global Engine communicating with mac/win/linux dock management APIs
pub struct BadgingEngine {
    pub active_badges: HashMap<String, PwaBadgeRegistration>,
    pub total_badge_updates: u64,
}

impl BadgingEngine {
    pub fn new() -> Self {
        Self {
            active_badges: HashMap::new(),
            total_badge_updates: 0,
        }
    }

    /// Internal installation tracking
    pub fn mark_pwa_installed(&mut self, origin: &str) {
        let registry = self.active_badges.entry(origin.to_string()).or_insert_with(|| PwaBadgeRegistration {
            origin_scope: origin.to_string(),
            current_badge: AppBadgeState::None,
            install_status: true,
        });
        registry.install_status = true;
    }

    /// JS execution: `navigator.setAppBadge(count?)` (§ 3)
    pub fn set_app_badge(&mut self, origin: &str, count: Option<u64>) -> Result<(), String> {
        let registry = self.active_badges.entry(origin.to_string()).or_insert_with(|| PwaBadgeRegistration {
            origin_scope: origin.to_string(),
            current_badge: AppBadgeState::None,
            install_status: false, // E.g., just running in a tab
        });

        self.total_badge_updates += 1;

        if let Some(n) = count {
            if n == 0 {
                // "If contents is 0, clear the badge" (§ 3.3)
                registry.current_badge = AppBadgeState::None;
            } else {
                registry.current_badge = AppBadgeState::Number(n);
            }
        } else {
            // "If contents is omitted, set the badge to an indeterminate value"
            registry.current_badge = AppBadgeState::Flag;
        }

        // Technically, if not installed, the OS ignores it, but the spec allows tracking it virtually
        Ok(())
    }

    /// JS execution: `navigator.clearAppBadge()` (§ 4)
    pub fn clear_app_badge(&mut self, origin: &str) {
        if let Some(registry) = self.active_badges.get_mut(origin) {
            self.total_badge_updates += 1;
            registry.current_badge = AppBadgeState::None;
        }
    }

    /// AI-facing Unread attention tracking metrics
    pub fn ai_badging_summary(&self, origin: &str) -> String {
        if let Some(registry) = self.active_badges.get(origin) {
            let state_str = match registry.current_badge {
                AppBadgeState::None => "No Badge",
                AppBadgeState::Flag => "Indicator Dot (Unread)",
                AppBadgeState::Number(n) => return format!("Count: {}", n),
            };
            format!("🔴 Badging API (Origin: {} [Installed: {}]): State: {} | Total global updates: {}", 
                origin, registry.install_status, state_str, self.total_badge_updates)
        } else {
            format!("Origin {} has no active notification badge tracking", origin)
        }
    }
}
