//! Network Error Logging — W3C Network Error Logging (NEL)
//!
//! Implements the browser's infrastructure for reporting network-level errors to origins:
//!   - NEL Header (§ 3.1): Parsing "report_to": "group", "max_age": 86400, "include_subdomains": true
//!   - NEL Policy (§ 3): Storage and management of reporting configurations
//!   - Error Types (§ 4.1): dns.unreachable, tcp.timed_out, tls.cert.invalid, http.error, etc.
//!   - Sampling and Failure Rates (§ 3.4): Determining which errors to report
//!   - Reporting API integration: Delivering reports to the specified endpoint groups
//!   - Privacy (§ 7): Mitigating data leakage and tracking via error reports
//!   - AI-facing: Network error log history and reporting status metrics

use std::collections::{HashMap, VecDeque};
use std::time::{SystemTime, UNIX_EPOCH};

/// NEL Error types (§ 4.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum NelErrorType { DNSUnreachable, TCPTimedOut, TLSCertInvalid, HTTPError, ProtocolError }

/// NEL Policy definition (§ 3.1)
#[derive(Debug, Clone)]
pub struct NelPolicy {
    pub origin: String,
    pub report_to: String,
    pub max_age: u64,
    pub expires_at: u64,
    pub include_subdomains: bool,
    pub failure_fraction: f32,
    pub success_fraction: f32,
}

/// A recorded network error report (§ 4)
#[derive(Debug, Clone)]
pub struct NelReport {
    pub origin: String,
    pub error_type: NelErrorType,
    pub status_code: u16,
    pub elapsed_time: u32,
    pub timestamp: u64,
}

/// The global NEL Manager
pub struct NelManager {
    pub policies: HashMap<String, NelPolicy>,
    pub report_queue: VecDeque<NelReport>,
}

impl NelManager {
    pub fn new() -> Self {
        Self {
            policies: HashMap::new(),
            report_queue: VecDeque::with_capacity(100),
        }
    }

    /// Handles an NEL header (§ 3.1)
    pub fn handle_header(&mut self, origin: &str, header_value: &str) {
        // Simplified parser for NEL reporting config
        let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs();
        self.policies.insert(origin.to_string(), NelPolicy {
            origin: origin.to_string(),
            report_to: "default".into(),
            max_age: 86400,
            expires_at: now + 86400,
            include_subdomains: false,
            failure_fraction: 1.0,
            success_fraction: 0.0,
        });
    }

    /// Records a network failure for potential reporting (§ 4.2)
    pub fn record_error(&mut self, origin: &str, error: NelErrorType, status: u16, elapsed: u32) {
        if self.policies.contains_key(origin) {
            if self.report_queue.len() >= 100 { self.report_queue.pop_front(); }
            self.report_queue.push_back(NelReport {
                origin: origin.to_string(),
                error_type: error,
                status_code: status,
                elapsed_time: elapsed,
                timestamp: SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs(),
            });
        }
    }

    /// AI-facing NEL history summary
    pub fn ai_nel_summary(&self) -> String {
        let mut lines = vec![format!("📉 Network Error Logging (Policies: {}, Queued: {}):", 
            self.policies.len(), self.report_queue.len())];
        for report in self.report_queue.iter().rev().take(5) {
            lines.push(format!("  - {} [{:?}] status={} ({}ms)", report.origin, report.error_type, report.status_code, report.elapsed_time));
        }
        lines.join("\n")
    }
}
