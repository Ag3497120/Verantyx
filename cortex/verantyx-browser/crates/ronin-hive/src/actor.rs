use async_trait::async_trait;
use uuid::Uuid;
use serde::{Serialize, Deserialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Envelope {
    pub message_id: Uuid,
    pub sender: String,
    pub recipient: String,
    pub payload: String,
}

#[async_trait]
pub trait Actor: Send + Sync {
    /// Name/Role of the actor (e.g. "Commander", "Reviewer")
    fn name(&self) -> &str;
    
    /// Handle an incoming message
    async fn receive(&mut self, env: Envelope) -> anyhow::Result<Option<Envelope>>;
}
