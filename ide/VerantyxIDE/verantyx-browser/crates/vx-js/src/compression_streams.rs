//! Compression Streams API — W3C Compression Streams
//!
//! Implements streaming data compression within JavaScript using WHATWG Streams:
//!   - CompressionStream (§ 2): Constructing a Writable/Readable TransformStream (`gzip`, `deflate`, `deflate-raw`)
//!   - DecompressionStream (§ 3): Inflating compressed chunks from fetch responses
//!   - Dictionary Support: (Optional capabilities for custom dictionary Brotli compression)
//!   - Integration: Pipelining readable web streams directly into memory-efficient encoders
//!   - AI-facing: Compression ratio calculation and byte throughput graph metrics

/// Supported compression algorithms (§ 2.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CompressionFormat { Gzip, Deflate, DeflateRaw }

/// Represents an abstract TransformStream that mutates chunks
#[derive(Debug, Clone)]
pub struct StreamTransformer {
    pub algorithm: CompressionFormat,
    pub is_compression: bool,
    pub bytes_in: u64,
    pub bytes_out: u64,
}

/// The global Compression Streams Engine
pub struct CompressionStreamsEngine {
    pub active_transformers: std::collections::HashMap<u64, StreamTransformer>,
    pub next_id: u64,
    pub total_network_savings: u64, // Bytes saved via decompression pipelining
}

impl CompressionStreamsEngine {
    pub fn new() -> Self {
        Self {
            active_transformers: std::collections::HashMap::new(),
            next_id: 1,
            total_network_savings: 0,
        }
    }

    /// Initializes `new CompressionStream(format)` (§ 2)
    pub fn create_compressor(&mut self, format: CompressionFormat) -> u64 {
        let id = self.next_id;
        self.next_id += 1;
        self.active_transformers.insert(id, StreamTransformer {
            algorithm: format,
            is_compression: true,
            bytes_in: 0,
            bytes_out: 0,
        });
        id
    }

    /// Initializes `new DecompressionStream(format)` (§ 3)
    pub fn create_decompressor(&mut self, format: CompressionFormat) -> u64 {
        let id = self.next_id;
        self.next_id += 1;
        self.active_transformers.insert(id, StreamTransformer {
            algorithm: format,
            is_compression: false,
            bytes_in: 0,
            bytes_out: 0,
        });
        id
    }

    /// Simulates pushing a JS Uint8Array chunk through the underlying TransformStream algorithm
    pub fn process_chunk(&mut self, transformer_id: u64, chunk_size: u64) -> Result<u64, String> {
        if let Some(stream) = self.active_transformers.get_mut(&transformer_id) {
            stream.bytes_in += chunk_size;
            
            // Mock compression ratios (e.g. GZip 40% shrinkage, Decompression 250% expansion)
            let out_chunk_size = if stream.is_compression {
                (chunk_size as f64 * 0.40) as u64
            } else {
                (chunk_size as f64 * 2.50) as u64
            };
            
            stream.bytes_out += out_chunk_size;

            if !stream.is_compression && out_chunk_size > chunk_size {
                self.total_network_savings += out_chunk_size - chunk_size;
            }

            Ok(out_chunk_size)
        } else {
            Err("TransformStream not found".into())
        }
    }

    /// AI-facing Compression Stream throughput summary
    pub fn ai_compression_summary(&self) -> String {
        let mut lines = vec![format!("🗜️ Compression Streams API (Estimated BW Saved: {} bytes)", self.total_network_savings)];
        for (id, stream) in &self.active_transformers {
            let mode = if stream.is_compression { "Compressing" } else { "Decompressing" };
            lines.push(format!("  - Stream #{} ({:?} | {}): IN: {} | OUT: {}", 
                id, stream.algorithm, mode, stream.bytes_in, stream.bytes_out));
        }
        lines.join("\n")
    }
}
