//! Core domain types shared across all Ronin subsystems.
//! These are the fundamental building blocks of the agent identity model.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use uuid::Uuid;

// ─────────────────────────────────────────────────────────────────────────────
// Agent Identity
// ─────────────────────────────────────────────────────────────────────────────

/// The hierarchical role this agent instance occupies in the Ronin swarm.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum AgentRole {
    /// The top-level decision maker. Holds full context, delegates execution.
    Commander,
    /// A specialized execution unit. Receives bounded tasks from the Commander.
    Worker,
    /// A read-only observer that gathers signals from the environment.
    Scout,
}

impl std::fmt::Display for AgentRole {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            AgentRole::Commander => write!(f, "Commander"),
            AgentRole::Worker    => write!(f, "Worker"),
            AgentRole::Scout     => write!(f, "Scout"),
        }
    }
}

/// Unique session scope for a single connected agent pair.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentSession {
    pub id: Uuid,
    pub role: AgentRole,
    pub model_id: String,
    pub started_at: DateTime<Utc>,
    pub turn_count: u32,
    pub metadata: HashMap<String, String>,
}

impl AgentSession {
    pub fn new(role: AgentRole, model_id: &str) -> Self {
        Self {
            id: Uuid::new_v4(),
            role,
            model_id: model_id.to_string(),
            started_at: Utc::now(),
            turn_count: 0,
            metadata: HashMap::new(),
        }
    }

    pub fn increment_turn(&mut self) {
        self.turn_count += 1;
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Message Parts (Multi-Modal)
// ─────────────────────────────────────────────────────────────────────────────

/// A single content block within a message. Supports multi-modal payload types.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", content = "data")]
pub enum MessagePart {
    /// Plain text
    Text(String),
    /// Raw code block with optional language tag
    Code { language: Option<String>, body: String },
    /// An embedded base64 image payload
    Image { mime: String, base64: String },
    /// A reference to a virtual file in the Gatekeeper VFS
    FileRef { vfs_id: Uuid, label: String },
    /// A captured shell observation (stdout + stderr + exit code)
    ShellObservation {
        command: String,
        stdout: String,
        stderr: String,
        exit_code: i32,
    },
    /// A JCross memory node reference
    MemoryRef { zone: MemoryZone, key: String },
}

/// The spatial memory zone classification in the JCross topology.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum MemoryZone {
    /// Hot context — injected into every prompt automatically.
    Front,
    /// Recent context — checked when task domain matches.
    Near,
    /// Historical context — surfaced only on explicit retrieval.
    Mid,
    /// Long-term archive — indexed, rarely loaded into context.
    Deep,
}

/// A single message in the conversation history.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConversationMessage {
    pub id: Uuid,
    pub role: MessageRole,
    pub parts: Vec<MessagePart>,
    pub timestamp: DateTime<Utc>,
    pub token_count: Option<usize>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum MessageRole {
    System,
    User,
    Assistant,
}

impl ConversationMessage {
    pub fn user(text: &str) -> Self {
        Self {
            id: Uuid::new_v4(),
            role: MessageRole::User,
            parts: vec![MessagePart::Text(text.to_string())],
            timestamp: Utc::now(),
            token_count: None,
        }
    }

    pub fn assistant(text: &str) -> Self {
        Self {
            id: Uuid::new_v4(),
            role: MessageRole::Assistant,
            parts: vec![MessagePart::Text(text.to_string())],
            timestamp: Utc::now(),
            token_count: None,
        }
    }

    pub fn system(text: &str) -> Self {
        Self {
            id: Uuid::new_v4(),
            role: MessageRole::System,
            parts: vec![MessagePart::Text(text.to_string())],
            timestamp: Utc::now(),
            token_count: None,
        }
    }

    /// Extracts a flat text representation of all text parts.
    pub fn to_flat_text(&self) -> String {
        self.parts.iter().filter_map(|p| {
            if let MessagePart::Text(t) = p { Some(t.as_str()) } else { None }
        }).collect::<Vec<_>>().join("\n")
    }
}
