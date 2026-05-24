use serde::{Deserialize, Serialize};
use crate::models::tier_calibration::TierProfile;
use tracing::info;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum TaskDomain {
    Coding,
    Reasoning,
    WebScraping,
    Planning,
    Trivial,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskContext {
    pub domain: TaskDomain,
    pub payload: String,
    pub required_tier_numeric: u8,
}

impl TaskContext {
    /// In a real system, you would parse the prompt locally to guess requirements.
    /// Here we use a heuristic constructor for the prototype.
    pub fn interpret(objective: &str) -> Self {
        let text = objective.to_lowercase();
        
        let mut domain = TaskDomain::Trivial;
        let mut req_tier = 1;

        if objective.starts_with("[STEALTH_FORCE]") {
            return Self {
                domain: TaskDomain::Reasoning,
                payload: objective.strip_prefix("[STEALTH_FORCE] ").unwrap_or(objective).to_string(),
                required_tier_numeric: 3,
            };
        }

        // English Heuristics
        if text.contains("research") || text.contains("analyze") || text.contains("scrape") {
            domain = TaskDomain::WebScraping;
            req_tier = 2; // Usually needs middle capability to sift through DOM
        } else if text.contains("refactor") || text.contains("rewrite") || text.contains("code") {
            domain = TaskDomain::Coding;
            req_tier = 3; // Coding heavy tasks require high tier
        } else if text.contains("plan") || text.contains("design") || text.contains("architect") {
            domain = TaskDomain::Planning;
            req_tier = 3; // High reasoning required
        }
        
        // Japanese Heuristics
        if text.contains("調査") || text.contains("検索") || text.contains("スクレイピング") || text.contains("分析") {
            domain = TaskDomain::WebScraping;
            req_tier = 2;
        } else if text.contains("設計") || text.contains("アーキテクチャ") || text.contains("構成") || text.contains("複雑") || text.contains("リファクタリング") {
            domain = TaskDomain::Planning;
            req_tier = 3; 
        }

        Self {
            domain,
            payload: objective.to_string(),
            required_tier_numeric: req_tier,
        }
    }
}

pub enum ExecutionMode {
    /// Proceed using only the local SLM. Needs 0 external instances constraint.
    Autonomous,
    /// Send off complex tasks to external Gemini workers, waiting for results to collapse back.
    Hybrid,
}

pub fn evaluate_task_capability(task: &TaskContext, profile: &TierProfile) -> ExecutionMode {
    // Note: To match strict numbering since TierProfile doesn't store the bare `InferenceTier` enum directly currently,
    // we derive its tier number from context limits or simple assumptions (In a fully refined schema, `TierProfile` would carry `base_tier: InferenceTier`).
    
    // Simplification for current TierProfile prototype:
    let local_tier_numeric = if profile.max_web_subagents >= 15 {
        3 // Heavyweight (Tier 3)
    } else if profile.max_web_subagents >= 5 {
        2 // Midweight (Tier 2)
    } else {
        1 // Lightweight (Tier 1)
    };

    info!(
        "[Bayesian-Eval] Task required tier: {} vs Local SLM capability tier: {}",
        task.required_tier_numeric, local_tier_numeric
    );

    if local_tier_numeric < task.required_tier_numeric {
        info!("[Bayesian-Eval] SLM prior_tier insufficient. Switching to Hybrid Execution Mode.");
        ExecutionMode::Hybrid
    } else {
        info!("[Bayesian-Eval] SLM prior_tier acceptable. Firing Autonomous Execution Mode.");
        ExecutionMode::Autonomous
    }
}
