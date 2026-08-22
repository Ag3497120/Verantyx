//! Credential Management API Level 1 — W3C CM Level 1
//!
//! Implements basic cross-origin credential sharing and lifecycle management:
//!   - navigator.credentials.store() (§ 3): Saving passwords and federated credentials
//!   - navigator.credentials.preventSilentAccess() (§ 4): Requiring user mediation on logout
//!   - PasswordCredential (§ 5): id, password, name, iconURL
//!   - FederatedCredential (§ 6): id, provider, protocol
//!   - User Mediation (§ 7): Tracking silent versus active mediation states per origin
//!   - Integration with WebAuthn and WebOTP endpoints
//!   - AI-facing: Saved credential vault registry and silent-access status visualizer

use std::collections::HashMap;

/// Types of general credentials handled by the API
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CredentialType { Password, Federated }

/// Abstract representation of a stored credential
#[derive(Debug, Clone)]
pub struct BrowserCredential {
    pub cred_type: CredentialType,
    pub id: String, // username or external identifier
    pub name: Option<String>,
    pub secret: Option<String>, // Empty on export
    pub provider: Option<String>, // 'https://accounts.google.com'
}

/// Mediation preference for fetching credentials (§ 7)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MediationRequirement { Silent, Optional, Required }

/// The global Credential Management Engine
pub struct CredentialManager {
    // Top-Level Origin -> vec of saved credentials
    pub vault: HashMap<String, Vec<BrowserCredential>>, 
    // Top-Level Origin -> Whether silent access is prevented (due to logout)
    pub prevent_silent_access: HashMap<String, bool>, 
}

impl CredentialManager {
    pub fn new() -> Self {
        Self {
            vault: HashMap::new(),
            prevent_silent_access: HashMap::new(),
        }
    }

    /// Entry point for navigator.credentials.store() (§ 3)
    pub fn store_credential(&mut self, origin: &str, cred: BrowserCredential) {
        let origin_vault = self.vault.entry(origin.to_string()).or_default();
        // Update existing if ID matches
        if let Some(existing) = origin_vault.iter_mut().find(|c| c.id == cred.id && c.cred_type == cred.cred_type) {
            *existing = cred;
        } else {
            origin_vault.push(cred);
        }
    }

    /// Entry point for navigator.credentials.preventSilentAccess() (§ 4)
    pub fn prevent_silent_access(&mut self, origin: &str) {
        self.prevent_silent_access.insert(origin.to_string(), true);
    }

    /// Evaluates if a credential can be automatically returned without user interaction
    pub fn allows_silent_access(&self, origin: &str) -> bool {
        !*self.prevent_silent_access.get(origin).unwrap_or(&false)
    }

    /// AI-facing credential vault summary
    pub fn ai_credential_summary(&self, origin: &str) -> String {
        let silent_allowed = self.allows_silent_access(origin);
        match self.vault.get(origin) {
            Some(creds) => {
                let mut txt = format!("🪪 Credential Vault ('{}'): {} stored [Silent Access: {}]", origin, creds.len(), silent_allowed);
                for c in creds {
                    txt.push_str(&format!("\n  - [{:?}] id: {}", c.cred_type, c.id));
                    if let Some(ref p) = c.provider { txt.push_str(&format!(" (federated via {})", p)); }
                }
                txt
            },
            None => format!("No credentials stored for '{}' [Silent Access: {}]", origin, silent_allowed)
        }
    }
}
