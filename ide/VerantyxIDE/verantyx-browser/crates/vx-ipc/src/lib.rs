//! vx-ipc — Verantyx Inter-Process Communication Engine
//!
//! A Chromium-style multiprocess engine abstracting Mojo communication. 
//! Separates the AI Orchestrator Main Process from Sandboxed Worker Renderers.

pub mod message;
pub mod channel;
pub mod router;

pub use message::{IpcMessageCode, IpcEnvelope, RouteId};
pub use channel::IpcChannel;
pub use router::{IpcRouter, RoutedConnection};
