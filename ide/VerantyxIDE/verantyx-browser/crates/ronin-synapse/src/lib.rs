//! # ronin-synapse
//!
//! Ronin's unified multi-channel neural interface.
//! Normalizes messages from Discord, Slack, and local terminal into a
//! single SynapseMessage stream dispatched to the agent inference core.
//! Outgoing responses are routed back to the originating channel automatically.

pub mod event;
pub mod router;
pub mod channels;
