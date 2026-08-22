//! WebTransport API Streams — WebTransport
//!
//! Implements low-latency, multiplexed bidirectional streaming bounds bridging to QUIC:
//!   - `WebTransportBidirectionalStream` (§ 4): Concurrent multiplexing abstractions
//!   - `WebTransportDatagramDuplexStream` (§ 5): Unordered, unreliable packet injection limits
//!   - Head-of-line blocking elimination vectors
//!   - AI-facing: QUIC Multiplexed Stream Extraction topologies

use std::collections::HashMap;

/// Identifies the inherent reliability and ordering constraints of a WebTransport Stream
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TransportStreamType {
    UnidirectionalReceive,
    UnidirectionalSend,
    Bidirectional,
    Datagram // Unreliable, Unordered
}

/// A specific multiplexed logical stream abstraction mapped onto a physical QUIC connection
#[derive(Debug, Clone)]
pub struct WebTransportStreamDescriptor {
    pub stream_id: u32,
    pub stream_type: TransportStreamType,
    pub bytes_transmitted: u64,
    pub bytes_received: u64,
    pub is_closed: bool,
}

/// The global Constraint Resolver bridging JavaScript Streams to physical QUIC datagrams
pub struct WebTransportStreamsEngine {
    // Session ID -> Stream ID -> Stream
    pub active_multiplexed_sessions: HashMap<u64, HashMap<u32, WebTransportStreamDescriptor>>,
    pub total_datagrams_transmitted: u64,
    pub total_streams_opened: u64,
}

impl WebTransportStreamsEngine {
    pub fn new() -> Self {
        Self {
            active_multiplexed_sessions: HashMap::new(),
            total_datagrams_transmitted: 0,
            total_streams_opened: 0,
        }
    }

    /// JS execution: `let stream = await transport.createBidirectionalStream()`
    pub fn allocate_logical_stream(&mut self, session_id: u64, s_type: TransportStreamType) -> u32 {
        let streams = self.active_multiplexed_sessions.entry(session_id).or_default();
        
        // Simulates QUIC stream ID generation (Client-initiated bidirectional = even numbers etc)
        let new_id = (streams.len() as u32 * 4) + match s_type {
            TransportStreamType::Bidirectional => 0,
            TransportStreamType::UnidirectionalSend => 2,
            _ => 1,
        };

        streams.insert(new_id, WebTransportStreamDescriptor {
            stream_id: new_id,
            stream_type: s_type,
            bytes_transmitted: 0,
            bytes_received: 0,
            is_closed: false,
        });

        self.total_streams_opened += 1;
        new_id
    }

    /// JS execution: `let writer = stream.writable.getWriter(); await writer.write(data);`
    pub fn transmit_payload(&mut self, session_id: u64, stream_id: u32, payload_bytes: usize) -> Result<(), String> {
        let streams = self.active_multiplexed_sessions.get_mut(&session_id)
            .ok_or("Session Expired")?;
            
        let stream = streams.get_mut(&stream_id).ok_or("Stream NotFound")?;
        
        if stream.is_closed { return Err("InvalidStateError: Stream closed".into()); }
        
        if stream.stream_type == TransportStreamType::UnidirectionalReceive {
            return Err("TypeError: Cannot write to Receive stream".into());
        }

        stream.bytes_transmitted += payload_bytes as u64;

        if stream.stream_type == TransportStreamType::Datagram {
            // Unreliable push immediately to UDP layer bound skipping flow control windows
            self.total_datagrams_transmitted += 1;
        } else {
            // Relies on QUIC MAX_STREAM_DATA flow control frames
        }

        Ok(())
    }

    /// AI-facing QUIC Multiplex Topologies
    pub fn ai_webtransport_summary(&self, session_id: u64) -> String {
        if let Some(streams) = self.active_multiplexed_sessions.get(&session_id) {
            let active = streams.values().filter(|s| !s.is_closed).count();
            format!("🚀 WebTransport API (Session #{}): Active Streams: {} | Global STREAMS Opened: {} | Datagrams Sent: {}", 
                session_id, active, self.total_streams_opened, self.total_datagrams_transmitted)
        } else {
            format!("Session #{} possesses no underlying physical WebTransport QUIC topologies", session_id)
        }
    }
}
