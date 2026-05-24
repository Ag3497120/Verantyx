//! Media Stream Pipeline
//!
//! Exposes WebRTC and standard <video>/<audio> streams to the AI agent natively.
//! Allows the AI to "view" and "hear" canvas payloads without expensive OS rendering.

use bytes::Bytes;
use tokio::sync::broadcast;

#[derive(Debug, Clone)]
pub struct VideoFrame {
    pub width: u32,
    pub height: u32,
    // RGBA payload stream representing an extracted I-frame
    pub payload: Bytes,
}

#[derive(Debug, Clone)]
pub struct AudioChunk {
    pub sample_rate: u32,
    pub channels: u16,
    // Pulse-code modulation payload
    pub payload: Bytes,
}

pub struct MediaStream {
    pub id: String,
    video_tx: broadcast::Sender<VideoFrame>,
    audio_tx: broadcast::Sender<AudioChunk>,
}

impl MediaStream {
    pub fn new(id: &str) -> Self {
        let (video_tx, _) = broadcast::channel(32);
        let (audio_tx, _) = broadcast::channel(128);

        Self {
            id: id.to_string(),
            video_tx,
            audio_tx,
        }
    }

    /// Subscribes the AI Vision Model directly to the decoded video pipeline
    pub fn subscribe_vision(&self) -> broadcast::Receiver<VideoFrame> {
        self.video_tx.subscribe()
    }

    /// Subscribes the AI Speech-to-Text Model directly to the audio pipeline
    pub fn subscribe_audio(&self) -> broadcast::Receiver<AudioChunk> {
        self.audio_tx.subscribe()
    }

    // Mock dispatch routines for internal browser decoding loops
    pub fn dispatch_frame(&self, frame: VideoFrame) {
        let _ = self.video_tx.send(frame);
    }
}
