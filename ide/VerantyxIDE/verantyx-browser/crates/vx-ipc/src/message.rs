//! Mojo-Style IPC Messaging Pipeline
//!
//! Provides the core serialization boundary and message envelopes for multi-process
//! AI browser communication separating the AI Orchestrator from the Renderer limits.

use serde::{Serialize, Deserialize};
use std::fmt::Debug;

/// Globally unique route identifier for cross-process communication targets
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct RouteId(pub u64);

/// Message Types defining the action spectrum across process boundaries
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum IpcMessageCode {
    // Renderer -> Browser
    RendererReady,
    NetworkRequest { url: String, method: String },
    DomMutation { node_id: u32, html: String },
    SemanticA11yUpdate { tree_tensor: Vec<u8> },

    // Browser -> Renderer
    Navigate { url: String },
    ExecuteScript { script: String },
    ResizeViewport { width: u32, height: u32 },
    PaintRequest,
    
    // Compositor Sync
    SyncLayerTree { compressed_layers: Vec<u8> },

    // Fallback/Custom
    Custom(String, Vec<u8>),
}

/// The IPC Envelope wrapping payloads for cross-boundary transport
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IpcEnvelope {
    pub message_id: u64,
    pub route_id: RouteId,
    pub code: IpcMessageCode,
    pub payload_size: u64,
}

impl IpcEnvelope {
    pub fn new(message_id: u64, route_id: RouteId, code: IpcMessageCode) -> Self {
        Self {
            message_id,
            route_id,
            code,
            payload_size: 0, // Computed during serialization
        }
    }

    /// Serialize via Bincode for zero-copy memory transport boundaries
    pub fn serialize(&self) -> anyhow::Result<Vec<u8>> {
        let bytes = bincode::serialize(self)?;
        // In a real Chromium clone, this sets payload headers
        Ok(bytes)
    }

    pub fn deserialize(bytes: &[u8]) -> anyhow::Result<Self> {
        let envelope = bincode::deserialize(bytes)?;
        Ok(envelope)
    }
}
