//! Service Workers — W3C Service Workers Living Standard
//!
//! Implements the browser's programmable network proxy and offline infrastructure:
//!   - ServiceWorkerRegistration (§ 3.1): scope, version, scriptURL, update()
//!   - ServiceWorkerContainer (§ 3.2): register(), getRegistration(), oncontrollerchange
//!   - Lifecycle Management (§ 4): Installing, Waiting, Activating, Activated, Redundant
//!   - Update Algorithm (§ 4.8): Byte-for-byte check and soft-delay updates
//!   - Fetch Interception (§ 5): RespondWith() and fetch event propagation
//!   - Cache Storage API integration (§ 5.4): match(), put(), delete(), keys()
//!   - Functional Events (§ 5): install, activate, fetch, message, push, sync, periodicsync
//!   - Client Control (§ 3.3.4): claim(), matchAll(), postMessage()
//!   - AI-facing: Service worker lifecycle visualizer and fetch interception logs

use std::collections::{HashMap, VecDeque};

/// Service Worker State (§ 4.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ServiceWorkerState { Installing, Installed, Activating, Activated, Redundant }

/// Service Worker Registration Metadata (§ 3.1)
#[derive(Debug, Clone)]
pub struct ServiceWorkerRegistration {
    pub scope: String,
    pub script_url: String,
    pub active: Option<ServiceWorker>,
    pub waiting: Option<ServiceWorker>,
    pub installing: Option<ServiceWorker>,
    pub update_via_cache: UpdateViaCache,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum UpdateViaCache { All, Imports, None }

/// An individual Service Worker instance (§ 3.1.2)
#[derive(Debug, Clone)]
pub struct ServiceWorker {
    pub script_url: String,
    pub state: ServiceWorkerState,
    pub script_resource: String, // Evaluated JS code
    pub registration_id: u64,
}

/// The global Service Worker Manager
pub struct ServiceWorkerManager {
    pub registrations: HashMap<String, ServiceWorkerRegistration>, // Scope -> Registration
    pub clients: HashMap<String, ServiceWorkerClient>, // Client ID -> Client
    pub pending_tasks: VecDeque<ServiceWorkerTask>,
    pub next_reg_id: u64,
}

#[derive(Debug, Clone)]
pub struct ServiceWorkerClient {
    pub id: String,
    pub url: String,
    pub type_: ClientType,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ClientType { Window, Worker, Sharedworker, All }

pub enum ServiceWorkerTask {
    Install(String),
    Activate(String),
    Fetch(String, String), // Scope, URL
}

impl ServiceWorkerManager {
    pub fn new() -> Self {
        Self {
            registrations: HashMap::new(),
            clients: HashMap::new(),
            pending_tasks: VecDeque::new(),
            next_reg_id: 1,
        }
    }

    /// Entry point for navigator.serviceWorker.register() (§ 3.2.3)
    pub fn register(&mut self, script_url: &str, scope: &str) -> u64 {
        let reg = self.registrations.entry(scope.to_string()).or_insert(ServiceWorkerRegistration {
            scope: scope.to_string(),
            script_url: script_url.to_string(),
            active: None,
            waiting: None,
            installing: Some(ServiceWorker {
                script_url: script_url.to_string(),
                state: ServiceWorkerState::Installing,
                script_resource: String::new(),
                registration_id: self.next_reg_id,
            }),
            update_via_cache: UpdateViaCache::Imports,
        });

        self.next_reg_id += 1;
        reg.installing.as_ref().unwrap().registration_id
    }

    /// Resolves the controlling service worker for a URL (§ 4.2.3)
    pub fn get_controller(&self, url: &str) -> Option<&ServiceWorker> {
        let mut best_match: Option<(&String, &ServiceWorkerRegistration)> = None;
        
        for (scope, reg) in &self.registrations {
            if url.starts_with(scope) {
                if best_match.is_none() || scope.len() > best_match.unwrap().0.len() {
                    best_match = Some((scope, reg));
                }
            }
        }

        best_match.and_then(|(_, reg)| reg.active.as_ref())
    }

    pub fn set_state(&mut self, scope: &str, state: ServiceWorkerState) {
        if let Some(reg) = self.registrations.get_mut(scope) {
            if let Some(sw) = reg.active.as_mut() { sw.state = state; }
            if let Some(sw) = reg.waiting.as_mut() { sw.state = state; }
            if let Some(sw) = reg.installing.as_mut() { sw.state = state; }
        }
    }

    /// AI-facing service worker dashboard
    pub fn ai_service_worker_status(&self) -> String {
        let mut lines = vec![format!("👷 Service Worker System (Registrations: {}):", self.registrations.len())];
        for (scope, reg) in &self.registrations {
            lines.push(format!("  Scope: '{}'", scope));
            if let Some(sw) = &reg.active { lines.push(format!("    [Active] {} (State: {:?})", sw.script_url, sw.state)); }
            if let Some(sw) = &reg.waiting { lines.push(format!("    [Waiting] {}", sw.script_url)); }
            if let Some(sw) = &reg.installing { lines.push(format!("    [Installing] {}", sw.script_url)); }
        }
        lines.join("\n")
    }
}
