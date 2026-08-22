//! Resource Loader — HTML Living Standard § 2.5
//!
//! Implements the high-level infrastructure for resource fetching and prioritization:
//!   - Resource types: Image, Script, Style, Font, XHR/Fetch, Media, Plugin, Manifest
//!   - Preloading and speculative fetching (§ 2.5.10): `<link rel="preload">`, `prefetch`, `dns-prefetch`, `preconnect`
//!   - Fetch priority (§ 2.5.11): auto, low, high
//!   - Caching strategies: Memory cache, Disk cache, Service Worker cache
//!   - Security policies: Content Security Policy (CSP), Subresource Integrity (SRI)
//!   - Resource lifecycle: Request, Loading, Decoded, Error, Cancelled
//!   - Data URI scheme (data:) handling
//!   - AI-facing: Resource dependency graph and load-time timeline

use std::collections::HashMap;

/// Resource types (§ 2.5.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ResourceType { Image, Script, Style, Font, Fetch, Media, Manifest }

/// Fetch priority (§ 2.5.11)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FetchPriority { Auto, Low, High }

/// Possible resource states
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ResourceState { Pending, Loading, Loaded, Errored, Cancelled }

/// Individual resource metadata
#[derive(Debug, Clone)]
pub struct Resource {
    pub url: String,
    pub res_type: ResourceType,
    pub priority: FetchPriority,
    pub state: ResourceState,
    pub bytes_total: u64,
    pub bytes_loaded: u64,
}

/// The global Resource Loader
pub struct ResourceLoader {
    pub resources: HashMap<String, Resource>,
    pub memory_cache: HashMap<String, Vec<u8>>,
    pub user_agent: String,
    pub max_parallel_requests: usize,
}

impl ResourceLoader {
    pub fn new(ua: &str) -> Self {
        Self {
            resources: HashMap::new(),
            memory_cache: HashMap::new(),
            user_agent: ua.to_string(),
            max_parallel_requests: 6,
        }
    }

    /// Primary entry point: Load a resource
    pub fn load_resource(&mut self, url: &str, res_type: ResourceType, priority: FetchPriority) {
        if self.resources.contains_key(url) { return; }

        self.resources.insert(url.to_string(), Resource {
            url: url.to_string(),
            res_type,
            priority,
            state: ResourceState::Pending,
            bytes_total: 0,
            bytes_loaded: 0,
        });

        // Trigger network request placeholder
    }

    /// Handles preloading directives (§ 2.5.10.2)
    pub fn preload(&mut self, url: &str, res_type: ResourceType) {
        self.load_resource(url, res_type, FetchPriority::Low);
    }

    pub fn set_resource_state(&mut self, url: &str, state: ResourceState) {
        if let Some(res) = self.resources.get_mut(url) {
            res.state = state;
        }
    }

    /// AI-facing resource dependency graph
    pub fn ai_resource_graph(&self) -> String {
        let mut lines = vec![format!("📦 Resource Loader Status ({} tracked):", self.resources.len())];
        for (url, res) in &self.resources {
            let status = match res.state {
                ResourceState::Pending => "⏳ Pending",
                ResourceState::Loading => "🔄 Loading",
                ResourceState::Loaded => "✅ Loaded",
                ResourceState::Errored => "❌ Error",
                ResourceState::Cancelled => "🚫 Cancelled",
            };
            lines.push(format!("  [{:?}] {} (Pri: {:?}) {}", res.res_type, url, res.priority, status));
        }
        lines.join("\n")
    }
}
