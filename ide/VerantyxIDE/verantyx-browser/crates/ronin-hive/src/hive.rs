use std::collections::HashMap;
use tokio::sync::mpsc;
use tracing::{info, debug};
use crate::actor::{Actor, Envelope};

pub struct HiveMind {
    actors: HashMap<String, Box<dyn Actor>>,
    inbox_tx: mpsc::Sender<Envelope>,
    inbox_rx: mpsc::Receiver<Envelope>,
}

impl HiveMind {
    pub fn new() -> Self {
        let (tx, rx) = mpsc::channel(100);
        Self {
            actors: HashMap::new(),
            inbox_tx: tx,
            inbox_rx: rx,
        }
    }

    pub fn hire_agent(&mut self, agent: Box<dyn Actor>) {
        info!("[HiveMind] Hired agent role: {}", agent.name());
        self.actors.insert(agent.name().to_string(), agent);
    }

    pub fn get_channel(&self) -> mpsc::Sender<Envelope> {
        self.inbox_tx.clone()
    }

    pub async fn run_swarm(&mut self) -> anyhow::Result<()> {
        info!("[HiveMind] Swarm runtime initiated.");
        
        while let Some(msg) = self.inbox_rx.recv().await {
            debug!("[HiveMind] Routing message from {} to {}", msg.sender, msg.recipient);
            
            // Check if it's a broadcast or point-to-point
            if let Some(actor) = self.actors.get_mut(&msg.recipient) {
                if let Ok(Some(reply)) = actor.receive(msg).await {
                    let _ = self.inbox_tx.send(reply).await;
                }
            } else if msg.recipient == "BROADCAST" {
                // Future: route to all actors
            } else if msg.recipient == "SYSTEM" && msg.payload == "SHUTDOWN" {
                info!("[HiveMind] Received shutdown signal.");
                break;
            } else {
                debug!("[HiveMind] Unreachable recipient: {}", msg.recipient);
            }
        }
        Ok(())
    }
}
