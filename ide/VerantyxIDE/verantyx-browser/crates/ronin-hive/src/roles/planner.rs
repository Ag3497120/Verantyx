use crate::actor::{Actor, Envelope};
use crate::messages::HiveMessage;
use async_trait::async_trait;
use tracing::{info, warn};
use uuid::Uuid;
use ronin_rag::memory::VectorStore;

pub struct PlannerActor {
    vector_store: VectorStore,
}

impl PlannerActor {
    pub fn new(vector_store_path: &std::path::Path) -> Self {
        Self {
            vector_store: VectorStore::new(vector_store_path),
        }
    }
}

#[async_trait]
impl Actor for PlannerActor {
    fn name(&self) -> &str { "Planner" }
    
    async fn receive(&mut self, env: Envelope) -> anyhow::Result<Option<Envelope>> {
        let msg: HiveMessage = match serde_json::from_str(&env.payload) {
            Ok(m) => m,
            Err(_) => return Ok(None),
        };

        match msg {
            HiveMessage::Objective(task) => {
                info!("[Planner] Received directive: {}", task);
                info!("[Planner] Querying MemoryBridge (RAG) to fetch codebase 70k context shards...");
                
                // 1. Fetch semantic codebase context directly from RAG
                let context_shards = self.vector_store.search(&task, 5).await?;
                info!("[Planner] Retrieved {} context shards from VectorStore.", context_shards.len());
                
                // Print top shard for debugging flow
                if let Some(top) = context_shards.first() {
                    info!("[Planner] Top RAG Insight: {}", top);
                }
                
                // 2. Break down the task into concrete files using context
                info!("[Planner] Synthesizing Implementation Plan using Vector RAG boundaries.");
                
                let plan = HiveMessage::ImplementationPlan {
                    // LLM would normally generate these dynamically
                    steps: vec!["Refactor logic".to_string(), "Add rigorous tests".to_string()],
                    target_files: vec!["src/main.rs".to_string()],
                };
                
                Ok(Some(Envelope {
                    message_id: Uuid::new_v4(),
                    sender: self.name().to_string(),
                    recipient: "Coder".to_string(),
                    payload: serde_json::to_string(&plan)?,
                }))
            },
            _ => {
                warn!("[Planner] Ignored unsupported message");
                Ok(None)
            }
        }
    }
}
