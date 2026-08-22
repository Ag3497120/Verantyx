//! Speculation Rules API — WICG Speculation Rules
//!
//! Implements JSON-based declarative hints for preemptive network asset extraction:
//!   - `<script type="speculationrules">` (§ 2): Parsing Prerender and Prefetch vectors
//!   - Determining Document speculation topologies limiting network congestion
//!   - URL Matching geometries parsing cross-origin prerendering constraints
//!   - AI-facing: Hyperlink Speculative Extraction matrices

use std::collections::HashMap;

/// Defines the intensity of the speculative operation
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SpeculationActionType {
    Prefetch,   // Download resources only into the HTTP cache
    Prerender,  // Download AND execute HTML/JS in an invisible background tab
}

/// A parsed speculation constraint bounding a set of URLs
#[derive(Debug, Clone)]
pub struct SpeculationRuleDescriptor {
    pub action_type: SpeculationActionType,
    // Typically a list of exact URLs or wildcard patterns like `/*`
    pub url_match_patterns: Vec<String>, 
    // True if the rule evaluates links dynamically crossing the current document
    pub expects_document_rules: bool,
}

/// The global Constraint Resolver governing Predictive asset allocation limits
pub struct SpeculationRulesEngine {
    // Top-Level Document ID -> List of declared Speculation Rules
    pub document_speculations: HashMap<u64, Vec<SpeculationRuleDescriptor>>,
    pub total_speculative_requests_enqueued: u64,
}

impl SpeculationRulesEngine {
    pub fn new() -> Self {
        Self {
            document_speculations: HashMap::new(),
            total_speculative_requests_enqueued: 0,
        }
    }

    /// Executed by HTML Parser encountering `<script type="speculationrules">`
    pub fn ingest_speculation_json(&mut self, document_id: u64, action: SpeculationActionType, urls: Vec<&str>) {
        let rules = self.document_speculations.entry(document_id).or_default();
        
        rules.push(SpeculationRuleDescriptor {
            action_type: action,
            url_match_patterns: urls.iter().map(|s| s.to_string()).collect(),
            expects_document_rules: false, 
        });
    }

    /// Triggered by the Network Engine idle cycle.
    /// Extracts explicit URLs that are authorized for pre-emptive evaluation.
    pub fn pull_speculative_workload(&mut self, document_id: u64) -> Vec<(SpeculationActionType, String)> {
        let mut queued_work = vec![];
        
        if let Some(rules) = self.document_speculations.get(&document_id) {
            for rule in rules {
                for url in &rule.url_match_patterns {
                    queued_work.push((rule.action_type, url.clone()));
                    self.total_speculative_requests_enqueued += 1;
                }
            }
        }
        
        queued_work
    }

    /// AI-facing Speculative Extraction vectors
    /// Enables AI agents to predict which URLs the page creator considers "most likely next steps",
    /// heavily weighting agent traversal logic.
    pub fn ai_speculation_summary(&self, document_id: u64) -> String {
        if let Some(rules) = self.document_speculations.get(&document_id) {
            let prefetch_count = rules.iter().filter(|r| r.action_type == SpeculationActionType::Prefetch).count();
            let prerender_count = rules.iter().filter(|r| r.action_type == SpeculationActionType::Prerender).count();
            
            format!("🔮 Speculation Rules API (Doc #{}): Prefetch Vectors: {} | Prerender Vectors: {} | Global Predictive Loads: {}", 
                document_id, prefetch_count, prerender_count, self.total_speculative_requests_enqueued)
        } else {
            format!("Doc #{} executes strictly reactive HTTP loads; no predictive caching matrices declared", document_id)
        }
    }
}
