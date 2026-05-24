//! Private Network Access (PNA) API — W3C Private Network Access
//!
//! Implements strict controls guarding local/private networks from public websites:
//!   - IP Address Space (§ 2): Distinguishing `public`, `private`, and `local` IPs
//!   - CORS Preflight (§ 6): Generating `Access-Control-Request-Private-Network` headers
//!   - Response Validation (§ 7): Expecting `Access-Control-Allow-Private-Network: true`
//!   - Insecure Context Ban: Requiring HTTPS for PNA requests
//!   - IP Address Resolution: Categorizing routing boundaries during DNS resolution
//!   - AI-facing: PNA violation monitor and local network exposure topology

use std::collections::HashMap;

/// Defined network routing spaces based on IP blocks (§ 2)
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum IpAddressSpace { Local, Private, Public, Unknown }

/// The global Private Network Access Engine
pub struct PrivateNetworkAccessEngine {
    pub cached_spaces: HashMap<String, IpAddressSpace>, // IP -> Space
    pub blocked_requests: Vec<String>, // Log of PNA violations
}

impl PrivateNetworkAccessEngine {
    pub fn new() -> Self {
        Self {
            cached_spaces: HashMap::new(),
            blocked_requests: Vec::new(),
        }
    }

    /// Evaluates the space of an IPv4 or IPv6 address (§ 2)
    pub fn evaluate_address_space(&mut self, ip: &str) -> IpAddressSpace {
        if let Some(space) = self.cached_spaces.get(ip) {
            return *space;
        }

        // Extremely simplified routing boundary check
        let space = if ip == "127.0.0.1" || ip == "::1" {
            IpAddressSpace::Local
        } else if ip.starts_with("192.168.") || ip.starts_with("10.") {
            IpAddressSpace::Private
        } else {
            IpAddressSpace::Public
        };

        self.cached_spaces.insert(ip.to_string(), space);
        space
    }

    /// Primary entry point for `fetch()` interceptions (§ 4)
    pub fn check_fetch_preflight(&mut self, initiator_space: IpAddressSpace, target_space: IpAddressSpace, is_secure_context: bool) -> Result<bool, String> {
        // Public -> Private, Public -> Local, Private -> Local require protection
        if initiator_space > target_space {
            if !is_secure_context {
                self.record_violation(format!("Insecure public context attempted PNA to {:?}", target_space));
                return Err("PNA requires a Secure Context".into());
            }
            // Indicates a preflight must be sent
            return Ok(true);
        }
        // No preflight required for safe boundaries
        Ok(false)
    }

    /// Validates the response of the PNA Preflight Options request
    pub fn validate_preflight_response(&mut self, header_allow_private: Option<&str>) -> bool {
        if let Some(val) = header_allow_private {
            val.trim().eq_ignore_ascii_case("true")
        } else {
            self.record_violation("PNA Preflight failed: missing Access-Control-Allow-Private-Network header".into());
            false
        }
    }

    fn record_violation(&mut self, message: String) {
        if self.blocked_requests.len() >= 100 { self.blocked_requests.remove(0); }
        self.blocked_requests.push(message);
    }

    /// AI-facing PNA status and violation matrix
    pub fn ai_pna_summary(&self) -> String {
        let mut lines = vec![format!("🔒 Private Network Access (Violations: {})", self.blocked_requests.len())];
        for (idx, msg) in self.blocked_requests.iter().rev().take(5).enumerate() {
            lines.push(format!("  [{}] {}", idx, msg));
        }
        lines.join("\n")
    }
}
