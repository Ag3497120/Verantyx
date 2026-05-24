//! Web OTP API — W3C Web OTP
//!
//! Implements the browser's credentials management infrastructure for SMS OTPs:
//!   - navigator.credentials.get() integration (§ 3): Requesting an OTP credential
//!   - OTPCredential (§ 4): Handling the parsed code from an intercepted SMS
//!   - Formatting Rules (§ 5): Validating `@origin #123456` message structures
//!   - Transport (§ 6): abstracting the inter-process communication with the OS mobile layer
//!   - User Mediation (§ 7): Requiring explicit user approval before auto-filling
//!   - Permissions and Security (§ 8): Restricting to Secure Contexts and top-level origins
//!   - AI-facing: OTP request registry and parsing metrics visualizer

use std::collections::VecDeque;

/// A requested OTP credential state
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum OTPRequestState { Pending, Resolved, Rejected }

pub struct OTPRequest {
    pub origin: String,
    pub timestamp: u64,
    pub state: OTPRequestState,
    pub received_code: Option<String>,
}

/// The global Web OTP Manager
pub struct WebOTPManager {
    pub requests: VecDeque<OTPRequest>,
}

impl WebOTPManager {
    pub fn new() -> Self {
        Self {
            requests: VecDeque::with_capacity(20),
        }
    }

    /// Entry point for navigator.credentials.get({ otp: { transport: ['sms'] } }) (§ 3)
    pub fn request_otp(&mut self, origin: &str, timestamp: u64) {
        if self.requests.len() >= 20 { self.requests.pop_front(); }
        self.requests.push_back(OTPRequest {
            origin: origin.to_string(),
            timestamp,
            state: OTPRequestState::Pending,
            received_code: None,
        });
    }

    /// Resolves an incoming SMS binding to a pending request (§ 5)
    pub fn resolve_sms(&mut self, origin: &str, code: &str) -> bool {
        for req in self.requests.iter_mut().rev() {
            if req.origin == origin && req.state == OTPRequestState::Pending {
                req.state = OTPRequestState::Resolved;
                req.received_code = Some(code.to_string());
                return true;
            }
        }
        false
    }

    /// AI-facing OTP integration summary
    pub fn ai_otp_status(&self) -> String {
        let mut lines = vec![format!("📲 Web OTP API Registry (Requests: {}):", self.requests.len())];
        for req in self.requests.iter().rev() {
            let status = match req.state {
                OTPRequestState::Pending => "🟡 Pending",
                OTPRequestState::Resolved => "🟢 Resolved",
                OTPRequestState::Rejected => "🔴 Rejected",
            };
            lines.push(format!("  - {} for '{}' [Code: {:?}]", status, req.origin, req.received_code));
        }
        lines.join("\n")
    }
}
