use tracing::{info, debug};

pub struct DocumentChunker {
    max_chunk_size: usize,
    overlap: usize,
}

impl DocumentChunker {
    pub const fn new(max_chunk_size: usize, overlap: usize) -> Self {
        Self { max_chunk_size, overlap }
    }

    /// Splits a large string (representing a file) into overlapping subsets
    /// to preserve semantic context across chunk boundaries.
    pub fn chunk(&self, payload: &str) -> Vec<String> {
        let mut chunks = Vec::new();
        let chars: Vec<char> = payload.chars().collect();
        let len = chars.len();
        
        if len == 0 {
            return chunks;
        }
        
        let mut i = 0;
        while i < len {
            let end_idx = std::cmp::min(i + self.max_chunk_size, len);
            let chunk_str: String = chars[i..end_idx].iter().collect();
            chunks.push(chunk_str);
            
            if end_idx == len {
                break;
            }
            // Step forward but retreat by `overlap`
            i = end_idx - self.overlap;
        }

        debug!("[RAG Chunker] Split document into {} chunks (size: {}, overlap: {})", chunks.len(), self.max_chunk_size, self.overlap);
        chunks
    }
}
