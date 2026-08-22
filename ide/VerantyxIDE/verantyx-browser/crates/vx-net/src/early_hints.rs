//! HTTP/2 Early Hints — RFC 8297
//!
//! Implements speculative resource fetching driven by HTTP 103 Responses:
//!   - Intercepting `103 Early Hints` status codes prior to `200 OK` (§ 2)
//!   - Parsing `Link: <...>; rel=preload` headers asynchronously
//!   - Pre-warming TCP/TLS connections (`rel=preconnect`)
//!   - Preventing duplicate fetches when the final 200 OK arrives
//!   - AI-facing: Network speculation topological limits

use std::collections::HashMap;

/// Denotes the intended action for an Early Hint Link header
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HintAction { Preload, Preconnect, Prefetch, DnsPrefetch }

/// A single pre-loaded candidate parsed from a 103 response
#[derive(Debug, Clone)]
pub struct EarlyHintCandidate {
    pub url: String,
    pub action: HintAction,
    pub as_type: Option<String>, // e.g. "style", "script"
    pub is_fulfilled: bool,
}

/// The global Engine mapping ahead-of-time HTTP responses
pub struct EarlyHintsEngine {
    // Top-Level Document ID -> Early Hints Queue
    pub speculative_queues: HashMap<u64, Vec<EarlyHintCandidate>>,
    pub total_links_preloaded: u64,
}

impl EarlyHintsEngine {
    pub fn new() -> Self {
        Self {
            speculative_queues: HashMap::new(),
            total_links_preloaded: 0,
        }
    }

    /// Executed by the HTTP framing layer upon receiving a `103` response before headers complete
    pub fn process_103_response(&mut self, document_id: u64, link_headers: Vec<&str>) {
        let mut new_candidates = Vec::new();
        
        let queue = self.speculative_queues.entry(document_id).or_default();
        for link_str in link_headers {
            if let Some(candidate) = Self::parse_link_header(link_str) {
                queue.push(candidate.clone());
                new_candidates.push(candidate);
            }
        }

        for candidate in new_candidates {
            self.trigger_speculative_fetch(&candidate);
        }
    }

    /// Parses the raw HTTP Link header value
    fn parse_link_header(header: &str) -> Option<EarlyHintCandidate> {
        // e.g., <https://example.com/style.css>; rel=preload; as=style
        let parts: Vec<&str> = header.split(';').collect();
        if parts.is_empty() { return None; }

        let url = parts[0].trim().trim_start_matches('<').trim_end_matches('>').to_string();
        
        let mut action = HintAction::Preload;
        let mut as_type = None;

        for part in parts.iter().skip(1) {
            let p = part.trim();
            if p.starts_with("rel=preload") { action = HintAction::Preload; }
            if p.starts_with("rel=preconnect") { action = HintAction::Preconnect; }
            if p.starts_with("as=") { as_type = Some(p.replace("as=", "")); }
        }

        Some(EarlyHintCandidate { url, action, as_type, is_fulfilled: false })
    }

    /// Internally kicks off the speculative connection to the network daemon
    fn trigger_speculative_fetch(&mut self, candidate: &EarlyHintCandidate) {
        // Here we would communicate with `vx-net` FetchClient
        // For simulation, we just track the metric
        self.total_links_preloaded += 1;
    }

    /// Checked when the actual DOM parser tries to fetch a script or stylesheet
    pub fn claim_preloaded_resource(&mut self, document_id: u64, url: &str) -> bool {
        if let Some(queue) = self.speculative_queues.get_mut(&document_id) {
            for hint in queue.iter_mut() {
                if hint.url == url && !hint.is_fulfilled {
                    hint.is_fulfilled = true;
                    return true; // We successfully prevented a duplicate fetch!
                }
            }
        }
        false
    }

    /// AI-facing Network Speculation topology
    pub fn ai_early_hints_summary(&self, document_id: u64) -> String {
        if let Some(queue) = self.speculative_queues.get(&document_id) {
            let fulfilled = queue.iter().filter(|q| q.is_fulfilled).count();
            format!("🚀 HTTP 103 Early Hints (Doc #{}): Queued: {} | Utilized: {} | Global Specs: {}", 
                document_id, queue.len(), fulfilled, self.total_links_preloaded)
        } else {
            format!("Node #{} did not receive any HTTP 103 speculative hints", document_id)
        }
    }
}
