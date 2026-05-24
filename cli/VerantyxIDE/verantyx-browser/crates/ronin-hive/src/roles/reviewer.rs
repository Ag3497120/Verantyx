use crate::actor::{Actor, Envelope};
use crate::messages::HiveMessage;
use async_trait::async_trait;
use tracing::{info, warn};
use uuid::Uuid;
use std::path::PathBuf;
use ronin_sandbox::process::session::SandboxSession;
use ronin_sandbox::isolation::policy::SandboxPolicy;

pub struct ReviewerActor {
    work_dir: PathBuf,
}

impl ReviewerActor {
    pub fn new(work_dir: impl Into<PathBuf>) -> Self {
        Self {
            work_dir: work_dir.into(),
        }
    }
}

#[async_trait]
impl Actor for ReviewerActor {
    fn name(&self) -> &str { "Reviewer" }
    
    async fn receive(&mut self, env: Envelope) -> anyhow::Result<Option<Envelope>> {
        let msg: HiveMessage = match serde_json::from_str(&env.payload) {
            Ok(m) => m,
            Err(_) => return Ok(None),
        };

        match msg {
            HiveMessage::ReviewRequest { diff } => {
                info!("[Reviewer] Received review request: evaluating diff state.");
                info!("[Reviewer] Analyzing diff constraints: \n{}", diff);
                
                // Set up sandbox session for automated review (e.g. `cargo check`)
                let policy = SandboxPolicy::default(); // 30 sec timeout, normal usage
                let mut session = SandboxSession::new(self.work_dir.clone(), "Reviewer", policy);
                
                // Assuming Rust project for this agent context, we run `cargo check`
                info!("[Reviewer] Running automated compilation validation inside Sandbox...");
                let exec_result = session.exec("cargo check --color=never").await;
                
                if exec_result.is_success() {
                    info!("[Reviewer] Validation PASS. No errors found.");
                    
                    let ob = HiveMessage::Observation {
                        success: true,
                        notes: "Compilation successful, all tests pass.".to_string(),
                    };
                    
                    Ok(Some(Envelope {
                        message_id: Uuid::new_v4(),
                        sender: self.name().to_string(),
                        recipient: env.sender, // Sending back to whoever requested it (Coder)
                        payload: serde_json::to_string(&ob)?,
                    }))
                } else {
                    warn!("[Reviewer] Validation FAIL. Intercepting stderr.");
                    
                    // Parse out exactly the errors for the Coder to learn from
                    let error_snippet = exec_result.to_observation();
                    
                    let ob = HiveMessage::Observation {
                        success: false,
                        notes: format!("Compilation failed! Fix these errors:\n{}", error_snippet),
                    };
                    
                    Ok(Some(Envelope {
                        message_id: Uuid::new_v4(),
                        sender: self.name().to_string(),
                        recipient: env.sender,
                        payload: serde_json::to_string(&ob)?,
                    }))
                }
            },
            _ => {
                warn!("[Reviewer] Ignored unknown message");
                Ok(None)
            }
        }
    }
}
