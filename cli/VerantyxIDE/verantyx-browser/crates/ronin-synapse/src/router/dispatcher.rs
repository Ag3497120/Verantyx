//! Synapse message router and dispatcher.
//!
//! The router receives all incoming SynapseMessages from every registered channel,
//! applies command parsing and access control, then dispatches to the registered
//! handler (the Ronin agent inference pipeline). Outgoing responses are routed
//! back to the originating channel automatically.

use crate::event::message::{SynapseMessage, SynapseResponse};
use async_trait::async_trait;
use std::sync::Arc;
use tokio::sync::{broadcast, mpsc, Mutex};
use tracing::{debug, info, warn};

// ─────────────────────────────────────────────────────────────────────────────
// Routing Handler Trait
// ─────────────────────────────────────────────────────────────────────────────

#[async_trait]
pub trait MessageHandler: Send + Sync {
    /// Called for every message received by the router. Returns an optional response.
    async fn handle(&self, message: SynapseMessage) -> Option<SynapseResponse>;

    /// Human-readable name of this handler (for logging).
    fn name(&self) -> &str;
}

// ─────────────────────────────────────────────────────────────────────────────
// Router Configuration
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone)]
pub struct RouterConfig {
    /// Command prefix (e.g. "!" or "/")
    pub command_prefix: String,
    /// Allowed Discord/Slack user IDs. Empty = allow all.
    pub allowed_user_ids: Vec<String>,
    /// Max concurrent routing tasks
    pub concurrency_limit: usize,
}

impl Default for RouterConfig {
    fn default() -> Self {
        Self {
            command_prefix: "!".to_string(),
            allowed_user_ids: vec![],
            concurrency_limit: 8,
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Central Synapse Router
// ─────────────────────────────────────────────────────────────────────────────

pub struct SynapseRouter {
    config: RouterConfig,
    handler: Arc<Box<dyn MessageHandler>>,
    incoming_tx: mpsc::Sender<SynapseMessage>,
    incoming_rx: Arc<Mutex<mpsc::Receiver<SynapseMessage>>>,
    outgoing_tx: broadcast::Sender<SynapseResponse>,
}

impl SynapseRouter {
    pub fn new(config: RouterConfig, handler: Box<dyn MessageHandler>) -> Self {
        let (incoming_tx, incoming_rx) = mpsc::channel(512);
        let (outgoing_tx, _) = broadcast::channel(512);
        Self {
            config,
            handler: Arc::new(handler),
            incoming_tx,
            incoming_rx: Arc::new(Mutex::new(incoming_rx)),
            outgoing_tx,
        }
    }

    /// Returns an ingress sender for channel adapters to push messages into.
    pub fn ingress_sender(&self) -> mpsc::Sender<SynapseMessage> {
        self.incoming_tx.clone()
    }

    /// Returns a broadcast receiver for channel adapters to pull outbound responses from.
    pub fn egress_receiver(&self) -> broadcast::Receiver<SynapseResponse> {
        self.outgoing_tx.subscribe()
    }

    /// Starts the router event loop. Runs indefinitely.  
    pub async fn run(&self) {
        info!("[SynapseRouter] Starting message dispatch loop");

        loop {
            let msg = {
                let mut rx = self.incoming_rx.lock().await;
                rx.recv().await
            };

            match msg {
                Some(message) => {
                    if !self.is_authorized(&message) {
                        warn!(
                            "[SynapseRouter] Unauthorized message from {} on {}",
                            message.author_id, message.source
                        );
                        continue;
                    }

                    debug!(
                        "[SynapseRouter] Routing message from {} on {}",
                        message.author_name, message.source
                    );

                    let handler = self.handler.clone();
                    let outgoing_tx = self.outgoing_tx.clone();

                    tokio::spawn(async move {
                        if let Some(response) = handler.handle(message).await {
                            let _ = outgoing_tx.send(response);
                        }
                    });
                }
                None => {
                    warn!("[SynapseRouter] Incoming channel closed, shutting down");
                    break;
                }
            }
        }
    }

    fn is_authorized(&self, msg: &SynapseMessage) -> bool {
        if self.config.allowed_user_ids.is_empty() {
            return true; // Open access
        }
        self.config.allowed_user_ids.contains(&msg.author_id)
    }
}
