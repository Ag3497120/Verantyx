//! Fetch Metadata Request Headers — W3C Fetch Metadata
//!
//! Implements strict server-side awareness of cross-site request intentions mitigating CSRF/XS-Leaks:
//!   - `Sec-Fetch-Dest` (§ 2): Target destination (`iframe`, `image`, `script`, etc.)
//!   - `Sec-Fetch-Mode` (§ 3): Execution mode (`cors`, `no-cors`, `navigate`)
//!   - `Sec-Fetch-Site` (§ 4): Origin differential (`same-origin`, `same-site`, `cross-site`)
//!   - `Sec-Fetch-User` (§ 5): Was request triggered by a user gesture?
//!   - AI-facing: Network intent routing topologies

use std::collections::HashMap;

/// Denotes the relational distance between the initiator and the target server
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FetchSiteAffinity { SameOrigin, SameSite, CrossSite, None }

/// Denotes the security constraints applied to the fetch response
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FetchMode { Cors, NoCors, Navigate, SameOrigin }

/// Encapsulates the intent metadata injected into the HTTP Request headers
#[derive(Debug, Clone)]
pub struct FetchMetadataPayload {
    pub sec_fetch_dest: String,
    pub sec_fetch_mode: FetchMode,
    pub sec_fetch_site: FetchSiteAffinity,
    pub sec_fetch_user: bool,
}

/// The global Constraint Resolver governing HTTP Header Injection prior to packet transmission
pub struct FetchMetadataEngine {
    pub total_headers_injected: u64,
    // Maps ongoing Request IDs to their applied metadata constraints
    pub active_requests: HashMap<u64, FetchMetadataPayload>,
}

impl FetchMetadataEngine {
    pub fn new() -> Self {
        Self {
            total_headers_injected: 0,
            active_requests: HashMap::new(),
        }
    }

    /// Executed synchronously right before the TCP/TLS socket writes the HTTP request
    pub fn construct_request_metadata(
        &mut self,
        request_id: u64,
        initiator_origin: &str,
        target_url: &str,
        req_mode: FetchMode,
        destination_trait: &str,
        is_user_activated: bool,
    ) -> FetchMetadataPayload {
        let affinity = self.calculate_site_affinity(initiator_origin, target_url);

        let metadata = FetchMetadataPayload {
            sec_fetch_dest: destination_trait.to_string(),
            sec_fetch_mode: req_mode,
            sec_fetch_site: affinity,
            sec_fetch_user: is_user_activated,
        };

        self.active_requests.insert(request_id, metadata.clone());
        self.total_headers_injected += 1;

        metadata
    }

    /// Serializes the struct into actual `Sec-Fetch-*` HTTP headers
    pub fn serialize_to_http_headers(&self, payload: &FetchMetadataPayload) -> Vec<String> {
        let mut headers = vec![
            format!("Sec-Fetch-Dest: {}", payload.sec_fetch_dest),
            format!("Sec-Fetch-Mode: {}", match payload.sec_fetch_mode {
                FetchMode::Cors => "cors",
                FetchMode::NoCors => "no-cors",
                FetchMode::Navigate => "navigate",
                FetchMode::SameOrigin => "same-origin",
            }),
            format!("Sec-Fetch-Site: {}", match payload.sec_fetch_site {
                FetchSiteAffinity::SameOrigin => "same-origin",
                FetchSiteAffinity::SameSite => "same-site",
                FetchSiteAffinity::CrossSite => "cross-site",
                FetchSiteAffinity::None => "none",
            }),
        ];

        if payload.sec_fetch_user {
            headers.push("Sec-Fetch-User: ?1".to_string());
        }

        headers
    }

    /// Simulates eTLD+1 logic for determining Same-Site vs Cross-Site
    fn calculate_site_affinity(&self, initiator: &str, target: &str) -> FetchSiteAffinity {
        if initiator == target {
            FetchSiteAffinity::SameOrigin // e.g. a.com -> a.com
        } else if initiator == "none" || initiator.is_empty() {
            FetchSiteAffinity::None // e.g. User typed in URL bar directly
        } else {
            // Very naive check for simulation:
            FetchSiteAffinity::CrossSite
        }
    }

    /// AI-facing Telemetry HTTP Request mappings
    pub fn ai_fetch_metadata_summary(&self, request_id: u64) -> String {
        if let Some(payload) = self.active_requests.get(&request_id) {
            format!("🕵️ Fetch Metadata API (Req #{}): Dest: {} | Site: {:?} | User Activated: {} | Global Injections: {}", 
                request_id, payload.sec_fetch_dest, payload.sec_fetch_site, payload.sec_fetch_user, self.total_headers_injected)
        } else {
            format!("Req #{} bypassed metadata HTTP header injection parameters", request_id)
        }
    }
}
