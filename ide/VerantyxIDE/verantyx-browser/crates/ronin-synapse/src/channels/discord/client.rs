//! Discord channel adapter for the Ronin Synapse system.
//!
//! Connects to the Discord REST/WebSocket API, listens for messages,
//! normalizes them to SynapseMessage, and sends outgoing Ronin responses
//! back to the correct channel. All logic is async and non-blocking.

use crate::event::message::{ChannelSource, SynapseMessage, SynapseResponse};
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::time::Duration;
use tokio::sync::mpsc;
use tracing::{debug, info, warn};

const DISCORD_API_BASE: &str = "https://discord.com/api/v10";

// ─────────────────────────────────────────────────────────────────────────────
// Discord API Types
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Deserialize)]
pub struct DiscordGatewayMessage {
    pub op: u8,
    #[serde(rename = "d")]
    pub data: Option<serde_json::Value>,
    #[serde(rename = "t")]
    pub event_type: Option<String>,
    #[serde(rename = "s")]
    pub sequence: Option<u64>,
}

#[derive(Debug, Serialize)]
struct SendMessagePayload {
    content: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    message_reference: Option<MessageReference>,
}

#[derive(Debug, Serialize)]
struct MessageReference {
    message_id: String,
}

// ─────────────────────────────────────────────────────────────────────────────
// Discord Client
// ─────────────────────────────────────────────────────────────────────────────

pub struct DiscordClient {
    http: Client,
    bot_token: String,
    allowed_channel_ids: Vec<String>,
    ingress_tx: mpsc::Sender<SynapseMessage>,
}

impl DiscordClient {
    pub fn new(
        bot_token: &str,
        allowed_channel_ids: Vec<String>,
        ingress_tx: mpsc::Sender<SynapseMessage>,
    ) -> Self {
        let http = Client::builder()
            .timeout(Duration::from_secs(30))
            .build()
            .expect("Failed to build Discord HTTP client");

        Self {
            http,
            bot_token: bot_token.to_string(),
            allowed_channel_ids,
            ingress_tx,
        }
    }

    fn auth_header(&self) -> String {
        format!("Bot {}", self.bot_token)
    }

    /// Sends a text message to a Discord channel.
    pub async fn send_message(
        &self,
        channel_id: &str,
        content: &str,
        reply_to: Option<&str>,
    ) -> anyhow::Result<()> {
        let payload = SendMessagePayload {
            content: content.to_string(),
            message_reference: reply_to.map(|id| MessageReference { message_id: id.to_string() }),
        };

        let resp = self
            .http
            .post(format!("{}/channels/{}/messages", DISCORD_API_BASE, channel_id))
            .header("Authorization", self.auth_header())
            .json(&payload)
            .send()
            .await?;

        if resp.status().is_success() {
            debug!("[Discord] Sent message to channel {}", channel_id);
        } else {
            warn!("[Discord] Failed to send message: HTTP {}", resp.status());
        }

        Ok(())
    }

    /// Handles an inbound Discord MESSAGE_CREATE event and normalizes it.
    pub async fn handle_message_create(&self, data: &serde_json::Value) {
        let channel_id = match data.get("channel_id").and_then(|v| v.as_str()) {
            Some(id) => id.to_string(),
            None => return,
        };

        // Filter to allowed channels
        if !self.allowed_channel_ids.is_empty() && !self.allowed_channel_ids.contains(&channel_id) {
            return;
        }

        let content = data["content"].as_str().unwrap_or("").to_string();
        if content.is_empty() { return; }

        // Skip bot messages
        let is_bot = data["author"]["bot"].as_bool().unwrap_or(false);
        if is_bot { return; }

        let author_id = data["author"]["id"].as_str().unwrap_or("unknown").to_string();
        let author_name = data["author"]["username"].as_str().unwrap_or("unknown").to_string();
        let message_id = data["id"].as_str().unwrap_or("0").to_string();
        let guild_id = data["guild_id"].as_str().unwrap_or("dm").to_string();

        let msg = SynapseMessage {
            id: message_id,
            source: ChannelSource::Discord { guild_id, channel_id },
            author_id,
            author_name,
            content,
            is_command: data["content"].as_str().map(|c| c.starts_with('!')).unwrap_or(false),
            timestamp: chrono::Utc::now(),
            reply_to: None,
            attachments: vec![],
        };

        info!("[Discord] Routing message from: {}", msg.author_name);
        let _ = self.ingress_tx.send(msg).await;
    }

    /// Dispatches an outgoing SynapseResponse back to Discord.
    pub async fn dispatch_response(&self, response: SynapseResponse) {
        if let ChannelSource::Discord { channel_id, .. } = &response.destination {
            let _ = self
                .send_message(
                    channel_id,
                    &response.content,
                    response.reply_to_message_id.as_deref(),
                )
                .await;
        }
    }
}
