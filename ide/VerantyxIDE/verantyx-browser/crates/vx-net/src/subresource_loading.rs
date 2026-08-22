//! Subresource Loading — W3C Preload / Prefetch API
//!
//! Implements HTML5 resource fetching prioritization and asynchronous load management:
//!   - `link rel=preload` (§ 4): Fetching critical assets ahead of DOM parsing
//!   - `link rel=prefetch` (§ 5): Fetching assets for future navigations in idle time
//!   - Preload scanner heuristics (finding `<script async>` before building the DOM)
//!   - Network cache topology isolation boundaries
//!   - AI-facing: Resource preemption mapping topologies

use std::collections::HashMap;

/// Denotes the intended execution priority of a scanned asset
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ScannerPriority { Critical, High, Medium, Low, Idle }

/// Defines the type of asset intended to be loaded (determining correct HTTP Accept headers)
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ResourceAsType { Script, Style, Image, Font, Fetch, Video, Audio }

/// An internal task tracking a subresource network dispatch
#[derive(Debug, Clone)]
pub struct SubresourceLoadTask {
    pub url: String,
    pub priority: ScannerPriority,
    pub as_type: ResourceAsType,
    pub is_crossorigin: bool,
    pub is_fulfilled: bool,
}

/// The global Preload/Prefetch Engine executing alongside the HTML Tokenizer
pub struct SubresourceLoadingEngine {
    // Top-level document -> Dispatched Tasks
    pub document_queues: HashMap<u64, Vec<SubresourceLoadTask>>,
    pub is_network_idle: bool,
    pub total_critical_preloads_started: u64,
}

impl SubresourceLoadingEngine {
    pub fn new() -> Self {
        Self {
            document_queues: HashMap::new(),
            is_network_idle: false,
            total_critical_preloads_started: 0,
        }
    }

    /// Executed by the Preload Scanner before the main DOM parser even reaches the specific tag
    pub fn trigger_speculative_preload(&mut self, document_id: u64, url: &str, as_type: ResourceAsType, priority: ScannerPriority) {
        let queue = self.document_queues.entry(document_id).or_default();
        
        // Deduplication
        if queue.iter().any(|q| q.url == url) {
            return;
        }

        queue.push(SubresourceLoadTask {
            url: url.to_string(),
            priority,
            as_type: as_type.clone(),
            is_crossorigin: false, // Simplified
            is_fulfilled: false,
        });

        if priority == ScannerPriority::Critical || priority == ScannerPriority::High {
            self.total_critical_preloads_started += 1;
            // Initiate immediately to network daemon
        } else if self.is_network_idle {
            // Initiate immediately if network allows
        } else {
            // Queue for `requestIdleCallback` timing equivalent
        }
    }

    /// Evaluated by the OS process tracking data flow rates
    pub fn set_network_idle_state(&mut self, is_idle: bool) {
        self.is_network_idle = is_idle;
        if is_idle {
            // Dispatch all queued Low/Idle priority prefetches
            for queue in self.document_queues.values_mut() {
                for task in queue.iter_mut() {
                    if !task.is_fulfilled && (task.priority == ScannerPriority::Low || task.priority == ScannerPriority::Idle) {
                        task.is_fulfilled = true; // Simulating dispatch
                    }
                }
            }
        }
    }

    /// Used by the primary DOM Parser to claim a resource that was already fetched
    pub fn claim_resource(&mut self, document_id: u64, url: &str) -> bool {
        if let Some(queue) = self.document_queues.get_mut(&document_id) {
            for task in queue.iter_mut() {
                if task.url == url && !task.is_fulfilled {
                    task.is_fulfilled = true;
                    return true;
                }
            }
        }
        false
    }

    /// AI-facing Resource Scanner topography
    pub fn ai_subresource_summary(&self, document_id: u64) -> String {
        let total = self.document_queues.get(&document_id).map_or(0, |q| q.len());
        format!("🔍 Subresource Loading (Doc #{}): Total Preloads Tracked: {} | Global Critical Preemptions: {} | Idle Phase: {}", 
            document_id, total, self.total_critical_preloads_started, self.is_network_idle)
    }
}
