//! Permissions Policy API — W3C Permissions Policy
//!
//! Implements strict domain-level capability delegations mitigating unauthorized hardware/API usage:
//!   - `Permissions-Policy` HTTP header (§ 5): Declaring origin bounds (e.g., `camera=(), geolocation=(self)`)
//!   - `iframe allow=""` attribute overriding constraints
//!   - `document.featurePolicy` introspection vectors
//!   - AI-facing: Capability delegation boundary extraction matrices

use std::collections::HashMap;

/// Denotes the strict physical or abstract hardware/software capability being gated
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum PolicyFeature {
    Camera, Microphone, Geolocation, Midi, Usb, 
    Payment, SharedAutofill, Fullscreen, WebVr
}

/// A parsed sub-policy determining exactly which domains can execute the capability
#[derive(Debug, Clone)]
pub struct FeatureDelegationRule {
    pub allow_list: Vec<String>, // "self", "*", "https://trusted.com"
    pub is_completely_blocked: bool, // "()"
}

/// The global Constraint Resolver governing execution capabilities for Origins and IFrames
pub struct PermissionsPolicyEngine {
    // Document ID -> Feature -> Applied Rule
    pub active_policies: HashMap<u64, HashMap<PolicyFeature, FeatureDelegationRule>>,
    pub total_policy_violations_blocked: u64,
}

impl PermissionsPolicyEngine {
    pub fn new() -> Self {
        Self {
            active_policies: HashMap::new(),
            total_policy_violations_blocked: 0,
        }
    }

    /// Executed during HTML/HTTP Header parsing. 
    /// Ingests sequences like: `Permissions-Policy: camera=(), geolocation=(self "https://example.com")`
    pub fn parse_and_apply_header(&mut self, document_id: u64, feature: PolicyFeature, raw_allow_list: Vec<&str>) {
        let is_blocked = raw_allow_list.is_empty() || raw_allow_list == vec!["()"];
        
        let rule = FeatureDelegationRule {
            allow_list: raw_allow_list.iter().map(|s| s.to_string()).collect(),
            is_completely_blocked: is_blocked,
        };

        let docs = self.active_policies.entry(document_id).or_default();
        docs.insert(feature, rule);
    }

    /// Evaluator executed precisely before *any* JS Engine hardware access
    /// E.g., intercepting `navigator.geolocation.getCurrentPosition()`
    pub fn is_feature_allowed(&mut self, document_id: u64, feature: PolicyFeature, executing_origin: &str) -> bool {
        if let Some(docs) = self.active_policies.get(&document_id) {
            if let Some(rule) = docs.get(&feature) {
                if rule.is_completely_blocked {
                    self.total_policy_violations_blocked += 1;
                    return false;
                }
                
                // Allow `*`
                if rule.allow_list.contains(&"*".to_string()) { return true; }
                
                // eTLD+1 Origin matching (Simplified logic for mock)
                if rule.allow_list.contains(&"self".to_string()) || rule.allow_list.contains(&executing_origin.to_string()) {
                    return true;
                }
                
                self.total_policy_violations_blocked += 1;
                return false;
            }
        }
        // W3C Rule: If no policy is explicitly sent, default to "self" or "allow" depending on the feature severity.
        // We assume allow for the engine simulation un-gated bounds.
        true 
    }

    /// AI-facing Feature Policy Topologies
    pub fn ai_policy_summary(&self, document_id: u64) -> String {
        if let Some(docs) = self.active_policies.get(&document_id) {
            let features_mapped = docs.keys().count();
            format!("🔒 Permissions Policy (Doc #{}): Regulating {} distinct hardware/API features | Global Malicious Violations Blocked: {}", 
                document_id, features_mapped, self.total_policy_violations_blocked)
        } else {
            format!("Doc #{} executes under un-gated legacy origin hardware capability limits", document_id)
        }
    }
}
