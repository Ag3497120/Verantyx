//! vx-media-pipeline — Advanced Audio/Video Routing Engine
//!
//! Enables Verantyx to natively decode HTML5 media and WebRTC components directly
//! into byte matrices consumable by generic AI models (Vision, Speech-to-Text).

pub mod stream;

pub use stream::{MediaStream, VideoFrame, AudioChunk};
