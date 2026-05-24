use serde::{Serialize, Deserialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum HiveMessage {
    /// High-level objective sent from the User to the Commander
    Objective(String),
    
    /// Granular plan sent from Commander to Planner, or Planner to Coder
    ImplementationPlan {
        steps: Vec<String>,
        target_files: Vec<String>,
    },
    
    /// Review request from Coder to Reviewer
    ReviewRequest {
        diff: String,
    },
    
    /// Coder execution command specifying physical REPLACE blocks
    CodePatch {
        req: ronin_coder::protocol::ReplaceRequest,
    },
    
    /// Observation/Feedback from Reviewer back to Coder or Commander
    Observation {
        success: bool,
        notes: String,
    },
    
    /// Summon a completely free, stealth-mode Gemini browser proxy worker
    SpawnSubAgent {
        id: uuid::Uuid,
        objective: String,
    },
    
    /// Return output from the stealth worker back to the hive
    SubAgentResult {
        id: uuid::Uuid,
        output: String,
    },
    
    /// Global system control
    Shutdown,
}
