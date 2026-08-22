//! # ronin-core
//!
//! The Rust heart of the Ronin autonomous hacker agent framework.
//! Provides the full agent ReAct loop, LLM provider abstraction,
//! JCross spatial memory bridge, and tool execution layer.

pub mod domain;
pub mod engine;
pub mod memory_bridge;
pub mod models;
pub mod tools;
