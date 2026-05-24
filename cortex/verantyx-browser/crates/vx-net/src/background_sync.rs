//! Web Background Synchronization API — W3C Background Sync
//!
//! Implements offline-capable deferred task execution mapping:
//!   - `SyncManager.register(tag)` (§ 3): Requesting a background sync event when online
//!   - `sync` event inside Service Worker (§ 4): The system waking the worker to execute limits
//!   - Periodic Background Sync (§ 5): Recurring low-frequency wake-ups `periodicSync.register()`
//!   - OS Power heuristics constraint limits
//!   - AI-facing: Asynchronous deferred network execution topology

use std::collections::HashMap;

/// An individual deferred task registered by a web application
#[derive(Debug, Clone)]
pub struct SyncRegistration {
    pub tag: String,
    pub is_periodic: bool,
    pub min_interval_ms: u64,
    pub last_fired_epoch_ms: u64,
}

/// A background sync processor attached to a specific Service Worker
#[derive(Debug, Clone)]
pub struct BackgroundSyncManager {
    pub service_worker_scope: String,
    pub pending_one_off_syncs: HashMap<String, SyncRegistration>,
    pub registered_periodic_syncs: HashMap<String, SyncRegistration>,
}

/// The global Background Sync Engine mapped to the network daemon
pub struct BackgroundSyncEngine {
    pub worker_managers: HashMap<String, BackgroundSyncManager>,
    pub is_network_online: bool, // Simulated OS network state
    pub total_sync_events_dispatched: u64,
}

impl BackgroundSyncEngine {
    pub fn new() -> Self {
        Self {
            worker_managers: HashMap::new(),
            is_network_online: true,
            total_sync_events_dispatched: 0,
        }
    }

    /// JS execution: `registration.sync.register('send-messages')` (§ 3)
    pub fn register_sync(&mut self, sw_scope: &str, tag: &str) {
        let manager = self.worker_managers.entry(sw_scope.to_string()).or_insert(BackgroundSyncManager {
            service_worker_scope: sw_scope.to_string(),
            pending_one_off_syncs: HashMap::new(),
            registered_periodic_syncs: HashMap::new(),
        });

        manager.pending_one_off_syncs.insert(tag.to_string(), SyncRegistration {
            tag: tag.to_string(),
            is_periodic: false,
            min_interval_ms: 0,
            last_fired_epoch_ms: 0, // Pending immediately
        });

        // Trigger immediately if already online
        if self.is_network_online {
            self.execute_pending_one_off_syncs(sw_scope);
        }
    }

    /// JS execution: `registration.periodicSync.register('fetch-news', { minInterval: 24 * 60 * 60 * 1000 })` (§ 5)
    pub fn register_periodic_sync(&mut self, sw_scope: &str, tag: &str, min_interval_ms: u64) {
        let manager = self.worker_managers.entry(sw_scope.to_string()).or_insert(BackgroundSyncManager {
            service_worker_scope: sw_scope.to_string(),
            pending_one_off_syncs: HashMap::new(),
            registered_periodic_syncs: HashMap::new(),
        });

        manager.registered_periodic_syncs.insert(tag.to_string(), SyncRegistration {
            tag: tag.to_string(),
            is_periodic: true,
            min_interval_ms,
            last_fired_epoch_ms: 0, // Never fired yet
        });
    }

    /// Executed by the OS when the network reconnects via Wi-Fi or Cellular
    pub fn trigger_network_reconnection(&mut self) -> usize {
        self.is_network_online = true;
        let mut executed = 0;
        
        let scopes: Vec<String> = self.worker_managers.keys().cloned().collect();
        for scope in scopes {
            executed += self.execute_pending_one_off_syncs(&scope);
        }
        executed
    }

    /// Fires logic simulating waking up a Service Worker to emit a 'sync' event
    fn execute_pending_one_off_syncs(&mut self, sw_scope: &str) -> usize {
        if let Some(manager) = self.worker_managers.get_mut(sw_scope) {
            let drained_tasks = manager.pending_one_off_syncs.drain().count();
            self.total_sync_events_dispatched += drained_tasks as u64;
            return drained_tasks;
        }
        0
    }

    /// AI-facing Background Sync topological matrix
    pub fn ai_background_sync_summary(&self) -> String {
        let mut total_one_off = 0;
        let mut total_periodic = 0;
        
        for m in self.worker_managers.values() {
            total_one_off += m.pending_one_off_syncs.len();
            total_periodic += m.registered_periodic_syncs.len();
        }

        format!("🔄 Background Sync API: Network Online: {} | Pending 1-Off: {} | Periodic Subscriptions: {} | Dispatched Tasks: {}", 
            self.is_network_online, total_one_off, total_periodic, self.total_sync_events_dispatched)
    }
}
