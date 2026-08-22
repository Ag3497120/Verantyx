//! Storage Access API — W3C Storage Access
//!
//! Implements cross-site third-party cookie/storage access mediation:
//!   - document.hasStorageAccess() (§ 3): Checking if an iframe has unpartitioned access
//!   - document.requestStorageAccess() (§ 4): Prompting the user to allow tracking
//!   - Partitioned vs Unpartitioned States: Distinguishing first-party sets from third-party
//!   - Interaction with Permissions Policy and embedded iframes
//!   - Top-level domain relationship evaluation (e.g. tracking protection strictness)
//!   - AI-facing: Storage isolation and third-party tracking topology visualizer

use std::collections::HashMap;

/// State of storage access for an embedded document
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StorageAccessState { Partitioned, Unpartitioned }

/// An evaluation context indicating relationships between origins
#[derive(Debug, Clone)]
pub struct StorageMediationContext {
    pub top_level_origin: String,
    pub embedded_origin: String,
    pub has_user_interaction: bool, // Required to request access
}

/// The global Storage Access Engine
pub struct StorageAccessEngine {
    // Top-Level Document Origin -> (Embedded Iframe Origin -> Access State)
    pub access_grants: HashMap<String, HashMap<String, StorageAccessState>>,
    pub total_prompts_shown: usize,
}

impl StorageAccessEngine {
    pub fn new() -> Self {
        Self {
            access_grants: HashMap::new(),
            total_prompts_shown: 0,
        }
    }

    /// Entry point for document.hasStorageAccess() (§ 3)
    pub fn has_storage_access(&self, top_origin: &str, embedded_origin: &str) -> bool {
        if top_origin == embedded_origin {
            return true; // First-party context is naturally unpartitioned
        }

        if let Some(embedded_states) = self.access_grants.get(top_origin) {
            if let Some(state) = embedded_states.get(embedded_origin) {
                return *state == StorageAccessState::Unpartitioned;
            }
        }
        false // Default for third-party embeds is heavily partitioned
    }

    /// Entry point for document.requestStorageAccess() (§ 4)
    pub fn request_storage_access(&mut self, context: StorageMediationContext) -> Result<(), String> {
        if context.top_level_origin == context.embedded_origin {
            return Ok(()); // Already granted
        }

        if !context.has_user_interaction {
            // Browsers universally reject prompts if the user hasn't clicked/tapped inside the iframe
            return Err("NotAllowedError: User interaction is required".into());
        }

        // Simulating the browser's native heuristic or user prompt dialog
        self.total_prompts_shown += 1;
        
        let embedded_states = self.access_grants.entry(context.top_level_origin).or_default();
        embedded_states.insert(context.embedded_origin, StorageAccessState::Unpartitioned);

        Ok(()) // Resolves JS Promise
    }

    /// Revokes an existing storage access grant (used by tracker blocking daemons)
    pub fn revoke_access(&mut self, top_origin: &str, embedded_origin: &str) {
        if let Some(embedded_states) = self.access_grants.get_mut(top_origin) {
            embedded_states.remove(embedded_origin);
        }
    }

    /// AI-facing Storage Access topology mapping
    pub fn ai_storage_access_summary(&self) -> String {
        let mut lines = vec![format!("🍪 Storage Access API (Prompts Generated: {}):", self.total_prompts_shown)];
        for (top, embeds) in &self.access_grants {
            lines.push(format!("  - Top-Level Orig: '{}'", top));
            for (embed, state) in embeds {
                lines.push(format!("    ↪ Embedded: '{}' [State: {:?}]", embed, state));
            }
        }
        lines.join("\n")
    }
}
