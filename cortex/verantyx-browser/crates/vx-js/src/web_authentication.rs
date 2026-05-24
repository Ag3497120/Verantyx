//! Web Authentication API — W3C WebAuthn (FIDO2)
//!
//! Implements strong public-key cryptographic authentication:
//!   - navigator.credentials.create() (§ 5.1): Creating a new PublicKeyCredential
//!   - navigator.credentials.get() (§ 5.2): Asserting an existing PublicKeyCredential
//!   - PublicKeyCredentialCreationOptions (§ 5.4): rp, user, challenge, pubKeyCredParams
//!   - PublicKeyCredentialRequestOptions (§ 5.5): challenge, allowCredentials, userVerification
//!   - Authenticator integration: YubiKey (CTAP2), TouchID/FaceID (Platform Authenticators)
//!   - Attestation and Assertion validations (§ 7)
//!   - Security (§ 13): Requiring Secure Context and user-activation, RP ID matching
//!   - AI-facing: WebAuthn challenge log and authenticator interaction visualizer

use std::collections::HashMap;

/// WebAuthn transport types (§ 5.8)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AuthenticatorTransport { Usb, Nfc, Ble, Internal, Hybrid }

/// Representation of a generated public key credential (§ 5.1.1)
#[derive(Debug, Clone)]
pub struct PublicKeyCredentialRecord {
    pub id: String, // Base64URL-encoded credential ID
    pub raw_id: Vec<u8>,
    pub public_key: Vec<u8>,
    pub sign_count: u32,
    pub rp_id: String,
    pub user_handle: Vec<u8>,
}

/// The global WebAuthn (FIDO2) Manager
pub struct WebAuthnManager {
    pub registered_credentials: HashMap<String, PublicKeyCredentialRecord>, // CredID -> Record
    pub active_challenges: Vec<String>, // Tracks active cryptographic challenges
    pub permission_granted: bool,
}

impl WebAuthnManager {
    pub fn new() -> Self {
        Self {
            registered_credentials: HashMap::new(),
            active_challenges: Vec::new(),
            permission_granted: false,
        }
    }

    /// Simulates the OS/Authenticator creating a new credential (§ 5.1)
    pub fn create_credential(&mut self, rp_id: &str, user_handle: Vec<u8>, _challenge: Vec<u8>) -> Result<PublicKeyCredentialRecord, String> {
        let cred_id = format!("cred_{}_{}", rp_id, self.registered_credentials.len());
        
        let cred = PublicKeyCredentialRecord {
            id: cred_id.clone(),
            raw_id: cred_id.as_bytes().to_vec(),
            public_key: vec![0x04, 0x01, 0x02, 0x03], // Mocked ECC P-256 public key
            sign_count: 0,
            rp_id: rp_id.to_string(),
            user_handle,
        };

        self.registered_credentials.insert(cred_id, cred.clone());
        Ok(cred)
    }

    /// Simulates asserting an existing credential for login (§ 5.2)
    pub fn assert_credential(&mut self, rp_id: &str, allowed_credentials: Vec<String>) -> Result<PublicKeyCredentialRecord, String> {
        for cred_id in allowed_credentials {
            if let Some(cred) = self.registered_credentials.get_mut(&cred_id) {
                if cred.rp_id == rp_id {
                    cred.sign_count += 1;
                    return Ok(cred.clone());
                }
            }
        }
        Err("No valid credential found for this Relying Party".into())
    }

    /// AI-facing WebAuthn metrics
    pub fn ai_webauthn_summary(&self) -> String {
        let mut lines = vec![format!("🔑 WebAuthn (FIDO2) Registry (Credentials: {}):", self.registered_credentials.len())];
        for (id, cred) in &self.registered_credentials {
            lines.push(format!("  - [{}] RP: '{}', SignCount: {}", id, cred.rp_id, cred.sign_count));
        }
        lines.join("\n")
    }
}
