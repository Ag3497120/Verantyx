//! Core message and event type definitions for the Synapse channel router.
//!
//! All incoming messages from Discord, Slack, or the local terminal are
//! normalized into this unified `SynapseMessage` type before being dispatched
//! to the Ronin agent core for inference.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::fmt;

// ─────────────────────────────────────────────────────────────────────────────
// Channel Source
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum ChannelSource {
    Discord { guild_id: String, channel_id: String },
    Slack { workspace_id: String, channel_id: String },
    Terminal { session_id: String },
}

impl fmt::Display for ChannelSource {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ChannelSource::Discord { channel_id, .. } => write!(f, "discord:{}", channel_id),
            ChannelSource::Slack { channel_id, .. }   => write!(f, "slack:{}", channel_id),
            ChannelSource::Terminal { session_id }     => write!(f, "terminal:{}", session_id),
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Unified Message
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SynapseMessage {
    pub id: String,
    pub source: ChannelSource,
    pub author_id: String,
    pub author_name: String,
    pub content: String,
    pub is_command: bool,
    pub timestamp: DateTime<Utc>,
    pub reply_to: Option<String>,
    pub attachments: Vec<SynapseAttachment>,
}

impl SynapseMessage {
    pub fn new_terminal(session_id: &str, content: &str) -> Self {
        Self {
            id: uuid::Uuid::new_v4().to_string(),
            source: ChannelSource::Terminal { session_id: session_id.to_string() },
            author_id: "local_user".to_string(),
            author_name: "Local".to_string(),
            content: content.to_string(),
            is_command: content.starts_with('/'),
            timestamp: Utc::now(),
            reply_to: None,
            attachments: vec![],
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SynapseAttachment {
    pub filename: String,
    pub content_type: String,
    pub url: Option<String>,
    pub data: Option<Vec<u8>>,
}

// ─────────────────────────────────────────────────────────────────────────────
// Outgoing Response
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SynapseResponse {
    pub destination: ChannelSource,
    pub content: String,
    pub reply_to_message_id: Option<String>,
    pub is_ephemeral: bool,
}

impl SynapseResponse {
    pub fn reply(msg: &SynapseMessage, content: &str) -> Self {
        Self {
            destination: msg.source.clone(),
            content: content.to_string(),
            reply_to_message_id: Some(msg.id.clone()),
            is_ephemeral: false,
        }
    }

    pub fn ephemeral(destination: ChannelSource, content: &str) -> Self {
        Self { destination, content: content.to_string(), reply_to_message_id: None, is_ephemeral: true }
    }
}
