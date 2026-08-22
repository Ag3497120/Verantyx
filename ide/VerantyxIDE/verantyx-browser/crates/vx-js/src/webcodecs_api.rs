//! WebCodecs API — W3C WebCodecs
//!
//! Implements low-level access to video and audio compression/decompression algorithms:
//!   - `VideoEncoder` / `VideoDecoder` (§ 3): Direct hardware accelerated bitstream manipulation
//!   - `VideoFrame` (§ 4): Raw pixel buffer abstractions moving across WebGL/Canvas boundaries
//!   - `EncodedVideoChunk` (§ 5): Compressed keyframes/deltaframes (H.264, VP9, AV1)
//!   - Frame queueing semantics preventing main thread starvation
//!   - AI-facing: Computer Vision pipeline ingestion capability mapper

use std::collections::HashMap;

/// Denotes the type of video frame chunk mapped to the bitstream (§ 5)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EncodedChunkType { Key, Delta }

/// Simulates a raw uncompressed planar pixel buffer representation
#[derive(Debug, Clone)]
pub struct VideoFrame {
    pub coded_width: u32,
    pub coded_height: u32,
    pub timestamp_microseconds: u64,
    pub duration_microseconds: Option<u64>,
}

/// Simulates an Annex B or ISOBMFF bitstream compressed payload
#[derive(Debug, Clone)]
pub struct EncodedVideoChunk {
    pub chunk_type: EncodedChunkType,
    pub timestamp_microseconds: u64,
    pub byte_length: usize,
}

/// A simulated hardware encoder context
#[derive(Debug, Clone)]
pub struct HardwareEncoder {
    pub codec_string: String, // e.g., "av01.0.04M.08"
    pub is_configured: bool,
    pub active_queue_size: usize,
    pub frames_encoded: u64,
}

/// The global WebCodecs Engine mediating GPU hardware acceleration routes
pub struct WebCodecsEngine {
    pub encoders: HashMap<u64, HardwareEncoder>,
    pub next_encoder_id: u64,
    pub total_video_frames_processed: u64,
}

impl WebCodecsEngine {
    pub fn new() -> Self {
        Self {
            encoders: HashMap::new(),
            next_encoder_id: 1,
            total_video_frames_processed: 0,
        }
    }

    /// JS execution: `new VideoEncoder({ output: cb, error: cb })`
    pub fn create_encoder(&mut self) -> u64 {
        let id = self.next_encoder_id;
        self.next_encoder_id += 1;

        self.encoders.insert(id, HardwareEncoder {
            codec_string: String::new(),
            is_configured: false,
            active_queue_size: 0,
            frames_encoded: 0,
        });

        id
    }

    /// JS execution: `encoder.configure({ codec: 'vp09.00.10.08', width: 1920, height: 1080 })`
    pub fn configure_encoder(&mut self, encoder_id: u64, codec: &str) -> Result<(), String> {
        if let Some(enc) = self.encoders.get_mut(&encoder_id) {
            enc.codec_string = codec.to_string();
            enc.is_configured = true;
            return Ok(());
        }
        Err("InvalidStateError: Encoder discarded".into())
    }

    /// JS execution: `encoder.encode(frame, { keyFrame: false })`
    pub fn encode_video_frame(&mut self, encoder_id: u64, frame: &VideoFrame, force_keyframe: bool) -> Result<EncodedVideoChunk, String> {
        if let Some(enc) = self.encoders.get_mut(&encoder_id) {
            if !enc.is_configured {
                return Err("InvalidStateError: Encoder not configured".into());
            }

            self.total_video_frames_processed += 1;
            enc.frames_encoded += 1;
            enc.active_queue_size += 1; // Pushed onto hardware queue

            // Simulate immediate pop (ideally async callback)
            enc.active_queue_size -= 1;

            let byte_size = if force_keyframe { 150_000 } else { 15_000 }; // Mock compression sizes

            Ok(EncodedVideoChunk {
                chunk_type: if force_keyframe { EncodedChunkType::Key } else { EncodedChunkType::Delta },
                timestamp_microseconds: frame.timestamp_microseconds,
                byte_length: byte_size,
            })
        } else {
            Err("InvalidStateError: Encoder discarded".into())
        }
    }

    /// AI-facing High Performance computer vision streaming capabilities
    pub fn ai_webcodecs_summary(&self, encoder_id: u64) -> String {
        if let Some(enc) = self.encoders.get(&encoder_id) {
            format!("🎬 WebCodecs API (Encoder #{}): Codec: {} | Frames Encoded: {} | Hardware Queue: {}", 
                encoder_id, enc.codec_string, enc.frames_encoded, enc.active_queue_size)
        } else {
            format!("Encoder #{} not found", encoder_id)
        }
    }
}
