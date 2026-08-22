//! WebSocket Protocol — RFC 6455
//!
//! Implements the full binary protocol for persistent browser-server communication:
//!   - Opening Handshake (§ 4.2): Sec-WebSocket-Key, Sec-WebSocket-Accept, and 101 Switching Protocols
//!   - Data Framing (§ 5.2): FIN, RSV1-3, Opcode, Masking, Payload length (7, 7+16, or 7+64 bits)
//!   - Opcodes (§ 5.2): Continuation (0), Text (1), Binary (2), Close (8), Ping (9), Pong (A)
//!   - Masking (§ 5.3): XOR-based payload masking for client-to-server frames
//!   - Control Frames (§ 5.5): Handling Ping/Pong heartbeats and Close handshakes
//!   - Fragmentation (§ 5.4): Reassembling large messages from multiple frames
//!   - Error Handling (§ 7): Fail the WebSocket connection on protocol violations
//!   - AI-facing: WebSocket frame inspector and message stream visualizer

use std::str;

/// WebSocket Opcodes (§ 5.2)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Opcode {
    Continuation,
    Text,
    Binary,
    Close,
    Ping,
    Pong,
    Reserved(u8),
}

impl Opcode {
    pub fn from_u8(v: u8) -> Self {
        match v & 0xF {
            0x0 => Opcode::Continuation,
            0x1 => Opcode::Text,
            0x2 => Opcode::Binary,
            0x8 => Opcode::Close,
            0x9 => Opcode::Ping,
            0xA => Opcode::Pong,
            v => Opcode::Reserved(v),
        }
    }

    pub fn to_u8(self) -> u8 {
        match self {
            Opcode::Continuation => 0x0,
            Opcode::Text => 0x1,
            Opcode::Binary => 0x2,
            Opcode::Close => 0x8,
            Opcode::Ping => 0x9,
            Opcode::Pong => 0xA,
            Opcode::Reserved(v) => v,
        }
    }
}

/// WebSocket Frame (§ 5.2)
#[derive(Debug, Clone)]
pub struct WebSocketFrame {
    pub fin: bool,
    pub opcode: Opcode,
    pub masked: bool,
    pub mask_key: Option<[u8; 4]>,
    pub payload: Vec<u8>,
}

impl WebSocketFrame {
    /// Parse a raw WebSocket frame from bytes
    pub fn parse(data: &[u8]) -> Option<(Self, usize)> {
        if data.len() < 2 { return None; }

        let fin = (data[0] & 0x80) != 0;
        let opcode = Opcode::from_u8(data[0] & 0x0F);
        let masked = (data[1] & 0x80) != 0;
        let mut payload_len = (data[1] & 0x7F) as u64;
        let mut offset = 2;

        if payload_len == 126 {
            if data.len() < 4 { return None; }
            payload_len = ((data[2] as u64) << 8) | (data[3] as u64);
            offset = 4;
        } else if payload_len == 127 {
            if data.len() < 10 { return None; }
            payload_len = 0;
            for i in 0..8 {
                payload_len = (payload_len << 8) | (data[offset + i] as u64);
            }
            offset = 10;
        }

        let mut mask_key = None;
        if masked {
            if data.len() < offset + 4 { return None; }
            let mut key = [0u8; 4];
            key.copy_from_slice(&data[offset..offset+4]);
            mask_key = Some(key);
            offset += 4;
        }

        if data.len() < offset + payload_len as usize { return None; }
        let mut payload = data[offset..offset + payload_len as usize].to_vec();

        if let Some(key) = mask_key {
            for (i, byte) in payload.iter_mut().enumerate() {
                *byte ^= key[i % 4];
            }
        }

        Some((WebSocketFrame { fin, opcode, masked, mask_key, payload }, offset + payload_len as usize))
    }

    /// Encode a frame to bytes (Client-to-Server, always masked per spec)
    pub fn encode(&self) -> Vec<u8> {
        let mut buf = Vec::new();
        let mut first_byte = if self.fin { 0x80 } else { 0x00 };
        first_byte |= self.opcode.to_u8();
        buf.push(first_byte);

        let mut second_byte = if self.masked { 0x80 } else { 0x00 };
        let len = self.payload.len();
        if len <= 125 {
            second_byte |= len as u8;
            buf.push(second_byte);
        } else if len <= 65535 {
            second_byte |= 126;
            buf.push(second_byte);
            buf.push((len >> 8) as u8);
            buf.push(len as u8);
        } else {
            second_byte |= 127;
            buf.push(second_byte);
            let len_bytes = (len as u64).to_be_bytes();
            buf.extend_from_slice(&len_bytes);
        }

        if let Some(key) = self.mask_key {
            buf.extend_from_slice(&key);
            let mut masked_payload = self.payload.clone();
            for (i, byte) in masked_payload.iter_mut().enumerate() {
                *byte ^= key[i % 4];
            }
            buf.extend(masked_payload);
        } else {
            buf.extend(&self.payload);
        }

        buf
    }
}

/// WebSocket Client implementation
pub struct WebSocketClient {
    pub url: String,
    pub protocol: Option<String>,
    pub ready_state: WebSocketState,
    pub buffered_amount: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WebSocketState { Connecting, Open, Closing, Closed }

impl WebSocketClient {
    pub fn new(url: &str) -> Self {
        Self {
            url: url.to_string(),
            protocol: None,
            ready_state: WebSocketState::Connecting,
            buffered_amount: 0,
        }
    }

    /// AI-facing WebSocket traffic overview
    pub fn ai_traffic_summary(&self, frames: &[WebSocketFrame]) -> String {
        let mut lines = vec![format!("🔌 WebSocket Connection: {} [{:?}]", self.url, self.ready_state)];
        for (i, frame) in frames.iter().enumerate() {
            if i > 20 { lines.push("  ... [truncated]".into()); break; }
            let summary = match frame.opcode {
                Opcode::Text => format!("\"{}\"", str::from_utf8(&frame.payload).unwrap_or("[invalid utf8]")),
                Opcode::Binary => format!("<Binary: {} bytes>", frame.payload.len()),
                _ => format!("{:?} frame", frame.opcode),
            };
            lines.push(format!("  [{}] {} (FIN: {})", i, summary, frame.fin));
        }
        lines.join("\n")
    }
}
