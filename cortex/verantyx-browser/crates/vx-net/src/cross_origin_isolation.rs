//! Cross-Origin Isolation API — W3C COOP/COEP
//!
//! Implements strict memory sandboxing required for high-resolution timers and SharedArrayBuffers:
//!   - `Cross-Origin-Opener-Policy` (COOP) parsing (§ 3)
//!   - `Cross-Origin-Embedder-Policy` (COEP) parsing (§ 4)
//!   - `Cross-Origin-Resource-Policy` (CORP) parsing (§ 5)
//!   - `window.crossOriginIsolated` state deduction
//!   - AI-facing: Memory isolation execution threat bounds

use std::collections::HashMap;

/// Determines if the document isolates itself from popups/tabs opened via `window.open`
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CoopState { UnsafeNone, SameOriginAllowPopups, SameOrigin }

/// Determines if the document requires all subresources to explicitly opt-in to being loaded
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CoepState { UnsafeNone, RequireCorp, Credentialless }

/// The policy attached to an individual frame/document context
#[derive(Debug, Clone)]
pub struct IsolationPolicyState {
    pub coop: CoopState,
    pub coep: CoepState,
    pub is_secure_context: bool, // Must be HTTPS
}

/// A global Engine tracking hardware memory boundary logic across the JS execution phase
pub struct CrossOriginIsolationEngine {
    pub active_policies: HashMap<u64, IsolationPolicyState>,
    pub total_memory_locks_enforced: u64,
}

impl CrossOriginIsolationEngine {
    pub fn new() -> Self {
        Self {
            active_policies: HashMap::new(),
            total_memory_locks_enforced: 0,
        }
    }

    /// Evaluated during the primary HTTP response parsing phase
    pub fn ingest_headers(&mut self, document_id: u64, is_https: bool, coop_header: Option<&str>, coep_header: Option<&str>) {
        let mut coop = CoopState::UnsafeNone;
        if let Some(h) = coop_header {
            match h {
                "same-origin-allow-popups" => coop = CoopState::SameOriginAllowPopups,
                "same-origin" => coop = CoopState::SameOrigin,
                _ => {}
            }
        }

        let mut coep = CoepState::UnsafeNone;
        if let Some(h) = coep_header {
            match h {
                "require-corp" => coep = CoepState::RequireCorp,
                "credentialless" => coep = CoepState::Credentialless,
                _ => {}
            }
        }

        self.active_policies.insert(document_id, IsolationPolicyState {
            coop,
            coep,
            is_secure_context: is_https,
        });

        if self.is_cross_origin_isolated(document_id) {
            self.total_memory_locks_enforced += 1;
        }
    }

    /// JS execution: Returns `window.crossOriginIsolated`
    /// If true, the JS engine enables `SharedArrayBuffer` and `performance.now()` microsecond resolution.
    pub fn is_cross_origin_isolated(&self, document_id: u64) -> bool {
        if let Some(policy) = self.active_policies.get(&document_id) {
            return policy.is_secure_context && 
                   policy.coop == CoopState::SameOrigin && 
                   (policy.coep == CoepState::RequireCorp || policy.coep == CoepState::Credentialless);
        }
        false
    }

    /// Evaluated during subresource fetches (img, script, iframe).
    /// If COEP is active, the requested resource must reply with CORP: `cross-origin` or `same-site` to load.
    pub fn evaluate_corp_block(&self, document_id: u64, is_same_origin: bool, corp_header: Option<&str>) -> bool {
        if let Some(policy) = self.active_policies.get(&document_id) {
            if policy.coep == CoepState::RequireCorp {
                if is_same_origin {
                    return true; 
                }
                if let Some(corp) = corp_header {
                    return corp == "cross-origin";
                } else {
                    return false; // Blocked! Missing CORP header on a cross origin resource while COEP is active
                }
            } else if policy.coep == CoepState::Credentialless {
                // Skips CORP checks for cross-origin resources, but strips all cookies/auth on the fetch
                return true; 
            }
        }
        true // Allow
    }

    /// AI-facing Execution Boundary topography
    pub fn ai_coi_summary(&self, document_id: u64) -> String {
        if let Some(policy) = self.active_policies.get(&document_id) {
            let env = if self.is_cross_origin_isolated(document_id) { "Hardware SAB Locked" } else { "Unsafe Memory" };
            format!("⛓️ Cross-Origin Isolation (Doc #{}): COOP: {:?} | COEP: {:?} | Environment: {} | Total Locks: {}", 
                document_id, policy.coop, policy.coep, env, self.total_memory_locks_enforced)
        } else {
            format!("Doc #{} operates within standard memory profiles", document_id)
        }
    }
}
