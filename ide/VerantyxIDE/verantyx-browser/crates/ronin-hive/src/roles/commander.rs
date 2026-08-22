use crate::actor::{Actor, Envelope};
use crate::messages::HiveMessage;
use async_trait::async_trait;
use tracing::{info, warn};
use uuid::Uuid;

use ronin_core::models::task_evaluator::{TaskContext, ExecutionMode, evaluate_task_capability};
use ronin_core::models::tier_calibration::TierProfile;

pub struct CommanderActor;
#[async_trait]
impl Actor for CommanderActor {
    fn name(&self) -> &str { "Commander" }
    
    async fn receive(&mut self, env: Envelope) -> anyhow::Result<Option<Envelope>> {
        let msg: HiveMessage = match serde_json::from_str(&env.payload) {
            Ok(m) => m,
            Err(e) => {
                warn!("[Commander] Failed to parse payload: {}", e);
                return Ok(None);
            }
        };

        match msg {
            HiveMessage::Objective(task) => {
                info!("[Commander] Received Objective: {}", task);
                
                // 1. Convert the objective strings to a concrete TaskContext requirement
                let ctx = TaskContext::interpret(&task);
                info!("[Commander] Computed Task Context: Domain={:?}, ReqTier={}", ctx.domain, ctx.required_tier_numeric);

                // 2. Evaluate local model capability (using default Llama-8B emulation profile Tier 1)
                let local_profile = TierProfile::extrapolate_from_model("gemma-2-9b"); 
                
                // 3. Apply Bayesian/Hybrid decision tree
                match evaluate_task_capability(&ctx, &local_profile) {
                    ExecutionMode::Hybrid => {
                        info!("[Commander] -> ExecutionMode::Hybrid assigned.");
                        info!("[Commander] Deploying Ephemeral Web Gemini Sub-Agent to offload task...");
                        
                        let worker_id = Uuid::new_v4();
                        let spawn_req = HiveMessage::SpawnSubAgent {
                            id: worker_id,
                            objective: task,
                        };
                        
                        Ok(Some(Envelope {
                            message_id: Uuid::new_v4(),
                            sender: self.name().to_string(),
                            recipient: "StealthGeminiWorker".to_string(),
                            payload: serde_json::to_string(&spawn_req)?,
                        }))
                    },
                    ExecutionMode::Autonomous => {
                        info!("[Commander] -> ExecutionMode::Autonomous assigned.");
                        info!("[Commander] Delegating decomposition to Planner...");
                        
                        // Reply with a directive to the Planner
                        let plan_req = HiveMessage::Objective(format!("DECOMPOSE: {}", task));
                        
                        Ok(Some(Envelope {
                            message_id: Uuid::new_v4(),
                            sender: self.name().to_string(),
                            recipient: "Planner".to_string(),
                            payload: serde_json::to_string(&plan_req)?,
                        }))
                    }
                }
            },
            HiveMessage::SubAgentResult { id, output } => {
                info!("[Commander] Received output from Stealth Web Worker [{}]: {}", id, output);
                // SubAgent did the research, now pass to Planner
                let plan_req = HiveMessage::Objective(format!("DECOMPOSE: Build plan using context: {}", output));
                Ok(Some(Envelope {
                    message_id: Uuid::new_v4(),
                    sender: self.name().to_string(),
                    recipient: "Planner".to_string(),
                    payload: serde_json::to_string(&plan_req)?,
                }))
            },
            HiveMessage::Observation { success, notes } => {
                info!("[Commander] Received final Observation. Success: {}, Notes: {}", success, notes);
                // Cycle complete
                Ok(None)
            },
            _ => {
                warn!("[Commander] Ignored unsupported message from {}", env.sender);
                Ok(None)
            }
        }
    }
}
