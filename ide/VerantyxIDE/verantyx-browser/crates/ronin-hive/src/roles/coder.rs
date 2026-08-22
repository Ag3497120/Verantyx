use crate::actor::{Actor, Envelope};
use crate::messages::HiveMessage;
use async_trait::async_trait;
use tracing::{info, warn, error};
use uuid::Uuid;
use ronin_coder::editor::FileEditor;

pub struct CoderActor {
    editor: FileEditor,
}

impl CoderActor {
    pub fn new(project_root: &std::path::Path) -> Self {
        Self {
            editor: FileEditor::new(project_root),
        }
    }
}

#[async_trait]
impl Actor for CoderActor {
    fn name(&self) -> &str { "Coder" }
    
    async fn receive(&mut self, env: Envelope) -> anyhow::Result<Option<Envelope>> {
        let msg: HiveMessage = match serde_json::from_str(&env.payload) {
            Ok(m) => m,
            Err(_) => return Ok(None),
        };

        match msg {
            HiveMessage::CodePatch { req } => {
                info!("[Coder] Applying SEARCH/REPLACE patch to {}", req.path);
                
                // 1. Physically apply patch
                let edit_result = self.editor.apply(&req);
                
                if edit_result.success {
                    info!("[Coder] Patch successful. Dispatching to Reviewer...");
                    // 2. Dispatch ReviewRequest
                    let review_req = HiveMessage::ReviewRequest {
                        // In real architecture, maybe we extract the unified diff.
                        // Here we just notify Reviewer to check the current CWD.
                        diff: format!("Patch applied to {}", edit_result.path),
                    };
                    
                    Ok(Some(Envelope {
                        message_id: Uuid::new_v4(),
                        sender: self.name().to_string(),
                        recipient: "Reviewer".to_string(),
                        payload: serde_json::to_string(&review_req)?,
                    }))
                } else {
                    error!("[Coder] Patch failed: {}", edit_result.feedback);
                    // Bouncing the error back to Planner or Commander
                    let err_obs = HiveMessage::Observation {
                        success: false,
                        notes: format!("Coder failed to patch {}: {}", req.path, edit_result.feedback),
                    };
                    
                    Ok(Some(Envelope {
                        message_id: Uuid::new_v4(),
                        sender: self.name().to_string(),
                        recipient: env.sender,
                        payload: serde_json::to_string(&err_obs)?,
                    }))
                }
            },
            HiveMessage::Observation { success, notes } => {
                if !success {
                    warn!("[Coder] Received rejected observation: {}. Must retry.", notes);
                    // In a live system, this buffers the errors and triggers LLM generation again
                }
                Ok(None)
            },
            _ => {
                warn!("[Coder] Ignored message");
                Ok(None)
            }
        }
    }
}
