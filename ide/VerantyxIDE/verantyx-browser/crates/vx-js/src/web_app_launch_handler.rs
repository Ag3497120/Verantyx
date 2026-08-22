//! Web App Launch Handler API — WICG Launch Handler
//!
//! Implements logical geometric windowing topologies for PWA OS execution limits:
//!   - `launch_handler: { client_mode: "navigate-existing" }` (§ 2): Re-using active window bounds
//!   - `client_mode: "focus-existing"`: Activating OS window focus without re-navigation
//!   - `window.launchQueue`: Polling OS start-args in a background logical state
//!   - AI-facing: PWA Application Launch/Focus Vectors

use std::collections::HashMap;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LaunchClientMode {
    Auto,              // OS Default behavior (Usually new-client)
    NavigateNew,       // Spawns a completely new Window bound
    NavigateExisting,  // Recycles the most recently focused window, forcing a re-navigation
    FocusExisting      // Just brings the existing window to the front without navigation
}

#[derive(Debug, Clone)]
pub struct AppLaunchParams {
    pub target_url: String,
    pub launch_mode: LaunchClientMode,
}

/// The global Constraint Resolver governing OS PWA Invocation limits
pub struct WebAppLaunchHandlerEngine {
    // App ID -> Launch queue waiting for JS to consume
    pub pending_launch_queues: HashMap<String, Vec<AppLaunchParams>>,
    pub total_existing_sessions_recycled: u64,
}

impl WebAppLaunchHandlerEngine {
    pub fn new() -> Self {
        Self {
            pending_launch_queues: HashMap::new(),
            total_existing_sessions_recycled: 0,
        }
    }

    /// Executed when the User double-clicks a PWA icon in Windows/macOS.
    /// Determines whether to tell `vx-js` to create a new Document or recycle an existing one.
    pub fn handle_os_invocation(&mut self, app_id: &str, target_url: &str, configured_mode: LaunchClientMode, has_active_window: bool) -> LaunchClientMode {
        let actual_mode = match configured_mode {
            LaunchClientMode::NavigateExisting | LaunchClientMode::FocusExisting if has_active_window => {
                self.total_existing_sessions_recycled += 1;
                configured_mode
            },
            _ => LaunchClientMode::NavigateNew
        };

        // If FocusExisting, enqueue the new target URL into `window.launchQueue`
        if actual_mode == LaunchClientMode::FocusExisting {
            let queue = self.pending_launch_queues.entry(app_id.to_string()).or_default();
            queue.push(AppLaunchParams {
                target_url: target_url.to_string(),
                launch_mode: actual_mode,
            });
        }
        
        actual_mode
    }

    /// JS execution: `window.launchQueue.setConsumer(params => { ... })`
    pub fn poll_js_launch_queue(&mut self, app_id: &str) -> Vec<AppLaunchParams> {
        self.pending_launch_queues.remove(app_id).unwrap_or_default()
    }

    /// AI-facing PWA Invocation Vectors
    pub fn ai_launch_handler_summary(&self, app_id: &str) -> String {
        let queued = self.pending_launch_queues.get(app_id).map(|q| q.len()).unwrap_or(0);
        format!("🪟 App Launch Handler (App: {}): Queued OS Invocations: {} | Global Windows Recycled: {}", 
            app_id, queued, self.total_existing_sessions_recycled)
    }
}
