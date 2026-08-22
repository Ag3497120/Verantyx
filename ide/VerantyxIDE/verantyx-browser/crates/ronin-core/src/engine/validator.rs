use std::collections::VecDeque;

/// Monitors the local LLM's execution trajectory inside the sandbox.
/// Determines when the LLM is stuck in a loop of execution failures 
/// and signals when a Gemini verification/hint is required.
pub struct SandboxValidator {
    pub max_consecutive_failures: usize,
    failure_history: VecDeque<String>,
}

pub enum ValidationDecision {
    /// The agent can continue trying to self-correct.
    ContinueSelfCorrection,
    /// The agent is stuck. Provide these errors to a higher-tier validator (Gemini).
    RequireHigherTierAudit(Vec<String>),
}

impl Default for SandboxValidator {
    fn default() -> Self {
        Self::new(3)
    }
}

impl SandboxValidator {
    pub fn new(max_consecutive_failures: usize) -> Self {
        Self {
            max_consecutive_failures,
            failure_history: VecDeque::new(),
        }
    }

    /// Record a successful sandbox execution (e.g. tests passed).
    /// Clears the failure history.
    pub fn record_success(&mut self) {
        self.failure_history.clear();
    }

    /// Record a failed sandbox execution (e.g. compiler error).
    /// Returns a decision on whether to let the agent keep trying,
    /// or explicitly intervene via Gemini fallback.
    pub fn record_failure(&mut self, stderr: &str) -> ValidationDecision {
        // Keep only top 200 chars to avoid memory bloat
        let snippet = if stderr.len() > 200 {
            format!("{}...", &stderr[..200])
        } else {
            stderr.to_string()
        };

        self.failure_history.push_back(snippet);

        if self.failure_history.len() >= self.max_consecutive_failures {
            let errors = self.failure_history.iter().cloned().collect();
            // Clear history so we don't immediately trigger again in the next cycle unless it builds up
            self.failure_history.clear(); 
            ValidationDecision::RequireHigherTierAudit(errors)
        } else {
            ValidationDecision::ContinueSelfCorrection
        }
    }
}
