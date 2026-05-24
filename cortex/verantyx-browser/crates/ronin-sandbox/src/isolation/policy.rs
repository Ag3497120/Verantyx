//! Execution policy and isolation ruleset.
//!
//! Defines the allowlist/denylist rules applied to every command before
//! it is dispatched to the shell. Implements multi-layer filtering:
//! 1. Hardcoded dangerous command blacklist (rm -rf /, dd, mkfs, etc.)
//! 2. Configurable path escape detection
//! 3. Network operation controls (curl/wget/nc gating)
//! 4. Resource limit enforcement (file size caps, time limits)

use serde::{Deserialize, Serialize};
use std::collections::HashSet;

// ─────────────────────────────────────────────────────────────────────────────
// Policy Decision
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PolicyDecision {
    Allow,
    Deny(String),
    Warn(String),
}

// ─────────────────────────────────────────────────────────────────────────────
// Sandbox Policy
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SandboxPolicy {
    /// Commands that are always blocked regardless of other settings.
    pub denylist: Vec<String>,
    /// If true, allow network access tools (curl, wget, nc, nmap…).
    pub allow_network_tools: bool,
    /// If true, allow commands that modify /etc, /usr, /bin in-place.
    pub allow_system_writes: bool,
    /// If true, allow sudo execution.
    pub allow_sudo: bool,
    /// Maximum bytes any single command's output may produce.
    pub max_output_bytes: usize,
    /// Maximum time allowed for a single command in seconds.
    pub max_execution_secs: u64,
}

impl Default for SandboxPolicy {
    fn default() -> Self {
        Self {
            denylist: vec![
                // Catastrophic destructors
                "rm -rf /".to_string(),
                "rm -rf /*".to_string(),
                "rm -rf ~".to_string(),
                ":(){:|:&};:".to_string(), // Fork bomb
                "mkfs".to_string(),
                "dd if=/dev/".to_string(),
                "shred".to_string(),
                // Privilege escalation
                "chmod 777 /".to_string(),
                "chown root".to_string(),
            ],
            allow_network_tools: false,
            allow_system_writes: false,
            allow_sudo: false,
            max_output_bytes: 10 * 1024 * 1024, // 10 MB
            max_execution_secs: 60,
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Policy Engine
// ─────────────────────────────────────────────────────────────────────────────

pub struct PolicyEngine {
    policy: SandboxPolicy,
    network_tools: HashSet<&'static str>,
    system_paths: HashSet<&'static str>,
}

impl PolicyEngine {
    pub fn new(policy: SandboxPolicy) -> Self {
        let network_tools = HashSet::from([
            "curl", "wget", "nc", "nmap", "ssh", "ftp", "sftp",
            "telnet", "ping", "dig", "nslookup", "tcpdump",
        ]);
        let system_paths = HashSet::from([
            "/etc", "/usr/bin", "/usr/sbin", "/bin", "/sbin", "/boot",
        ]);
        Self { policy, network_tools, system_paths }
    }

    /// Evaluates a command string against the active policy.
    pub fn evaluate(&self, command: &str) -> PolicyDecision {
        let cmd_lower = command.to_lowercase();
        let first_token = command.split_whitespace().next().unwrap_or("").to_string();
        let first_token = first_token.split('/').last().unwrap_or("");

        // 1. Hardcoded denylist check
        for denied in &self.policy.denylist {
            if cmd_lower.contains(&denied.to_lowercase()) {
                return PolicyDecision::Deny(format!(
                    "Command matches denylist pattern: '{}'", denied
                ));
            }
        }

        // 2. sudo check
        if !self.policy.allow_sudo && cmd_lower.starts_with("sudo") {
            return PolicyDecision::Deny(
                "sudo is disabled in the current sandbox policy".to_string()
            );
        }

        // 3. Network tool check
        if !self.policy.allow_network_tools
            && self.network_tools.contains(first_token)
        {
            return PolicyDecision::Deny(format!(
                "Network tool '{}' is blocked by sandbox policy (allow_network_tools=false)",
                first_token
            ));
        }

        // 4. System path write check
        if !self.policy.allow_system_writes {
            for sys_path in &self.system_paths {
                if command.contains(sys_path) && (command.contains('>') || first_token == "cp") {
                    return PolicyDecision::Warn(format!(
                        "Command targets system path '{}' — review recommended before applying",
                        sys_path
                    ));
                }
            }
        }

        // 5. Directory traversal check
        if command.contains("../../") || command.contains("/../") {
            return PolicyDecision::Warn(
                "Command contains path traversal pattern ('../../')".to_string()
            );
        }

        PolicyDecision::Allow
    }

    pub fn policy(&self) -> &SandboxPolicy {
        &self.policy
    }
}
