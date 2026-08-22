//! Slack channel adapter for the Ronin Synapse system.
//!
//! Connects to the Slack Events API and Socket Mode, normalizes
//! events into SynapseMessages, and sends Ronin responses back
//! via the Slack Web API (chat.postMessage).

use crate::event::message::{ChannelSource, SynapseMessage, SynapseResponse};
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::time::Duration;
use tokio::sync::mpsc;
use tracing::{debug, info, warn};

const SLACK_API_BASE: &str = "https://slack.com/api";

// ─────────────────────────────────────────────────────────────────────────────
// Slack API Types
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Serialize)]
struct PostMessagePayload {
    channel: String,
    text: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    thread_ts: Option<String>,
}

#[derive(Debug, Deserialize)]
struct SlackApiResponse {
    ok: bool,
    error: Option<String>,
}

// ─────────────────────────────────────────────────────────────────────────────
// Slack Client
// ─────────────────────────────────────────────────────────────────────────────

pub struct SlackClient {
    http: Client,
    bot_token: String,
    workspace_id: String,
    ingress_tx: mpsc::Sender<SynapseMessage>,
}

impl SlackClient {
    pub fn new(
        bot_token: &str,
        workspace_id: &str,
        ingress_tx: mpsc::Sender<SynapseMessage>,
    ) -> Self {
        let http = Client::builder()
            .timeout(Duration::from_secs(30))
            .build()
            .expect("Failed to build Slack HTTP client");

        Self {
            http,
            bot_token: bot_token.to_string(),
            workspace_id: workspace_id.to_string(),
            ingress_tx,
        }
    }

    /// Sends a message to a Slack channel via chat.postMessage.
    pub async fn post_message(
        &self,
        channel_id: &str,
        text: &str,
        thread_ts: Option<&str>,
    ) -> anyhow::Result<()> {
        let payload = PostMessagePayload {
            channel: channel_id.to_string(),
            text: text.to_string(),
            thread_ts: thread_ts.map(|s| s.to_string()),
        };

        let resp: SlackApiResponse = self
            .http
            .post(format!("{}/chat.postMessage", SLACK_API_BASE))
            .bearer_auth(&self.bot_token)
            .json(&payload)
            .send()
            .await?
            .json()
            .await?;

        if resp.ok {
            debug!("[Slack] Message sent to {}", channel_id);
        } else {
            warn!("[Slack] API error: {:?}", resp.error);
        }

        Ok(())
    }

    /// Handles a Slack `message` event payload and normalizes it.
    pub async fn handle_message_event(&self, payload: &serde_json::Value) {
        let event = match payload.get("event") {
            Some(e) => e,
            None => return,
        };

        // Ignore bot messages
        if event.get("bot_id").is_some() { return; }

        let content = event["text"].as_str().unwrap_or("").to_string();
        if content.is_empty() { return; }

        let channel_id = event["channel"].as_str().unwrap_or("unknown").to_string();
        let user_id = event["user"].as_str().unwrap_or("unknown").to_string();
        let ts = event["ts"].as_str().unwrap_or("0").to_string();

        let msg = SynapseMessage {
            id: ts.replace('.', ""),
            source: ChannelSource::Slack {
                workspace_id: self.workspace_id.clone(),
                channel_id: channel_id.clone(),
            },
            author_id: user_id.clone(),
            author_name: user_id,
            content,
            is_command: event["text"].as_str().map(|t| t.starts_with('!')).unwrap_or(false),
            timestamp: chrono::Utc::now(),
            reply_to: None,
            attachments: vec![],
        };

        info!("[Slack] Routing message from: {}", msg.author_id);
        let _ = self.ingress_tx.send(msg).await;
    }

    /// Dispatches an outgoing SynapseResponse back to Slack.
    pub async fn dispatch_response(&self, response: SynapseResponse) {
        if let ChannelSource::Slack { channel_id, .. } = &response.destination {
            let _ = self
                .post_message(channel_id, &response.content, None)
                .await;
        }
    }
}
