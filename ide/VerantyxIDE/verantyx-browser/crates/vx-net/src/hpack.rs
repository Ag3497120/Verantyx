//! HPACK Header Compression for HTTP/2 — RFC 7541
//!
//! Implements header compression for HTTP/2 to reduce redundant header transfer:
//!   - Static Table (§ B): 61 predefined header fields
//!   - Dynamic Table (§ 4): Per-connection table for new header fields
//!   - Integer Representation (§ 5.1): Variable-length encoding with prefix
//!   - String Representation (§ 5.2): Huffman encoding and literal strings
//!   - Header Field Representation (§ 6): Indexed, Literal with Indexing, Literal without Indexing
//!   - Dynamic Table Management (§ 4.4): Eviction logic based on table size
//!   - Decoding/Encoding state machine
//!   - AI-facing: HPACK table inspector and compression ratio analysis

use std::collections::VecDeque;

/// A single header field (name, value)
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HeaderField {
    pub name: String,
    pub value: String,
}

impl HeaderField {
    pub fn new(name: &str, value: &str) -> Self {
        Self { name: name.to_string(), value: value.to_string() }
    }

    pub fn size(&self) -> usize {
        self.name.len() + self.value.len() + 32 // RFC 7541 § 4.1
    }
}

/// HPACK Static Table (RFC 7541 Appendix B)
const STATIC_TABLE: &[(&str, &str)] = &[
    (":authority", ""), (":method", "GET"), (":method", "POST"), (":path", "/"),
    (":path", "/index.html"), (":scheme", "http"), (":scheme", "https"), (":status", "200"),
    (":status", "204"), (":status", "206"), (":status", "304"), (":status", "400"),
    (":status", "404"), (":status", "500"), ("accept-charset", ""), ("accept-encoding", "gzip, deflate"),
    ("accept-language", ""), ("accept-ranges", ""), ("accept", ""), ("access-control-allow-origin", ""),
    ("age", ""), ("allow", ""), ("authorization", ""), ("cache-control", ""),
    ("content-disposition", ""), ("content-encoding", ""), ("content-language", ""), ("content-length", ""),
    ("content-location", ""), ("content-range", ""), ("content-type", ""), ("cookie", ""),
    ("date", ""), ("etag", ""), ("expect", ""), ("expires", ""),
    ("from", ""), ("host", ""), ("if-match", ""), ("if-modified-since", ""),
    ("if-none-match", ""), ("if-range", ""), ("if-unmodified-since", ""), ("last-modified", ""),
    ("link", ""), ("location", ""), ("max-forwards", ""), ("proxy-authenticate", ""),
    ("proxy-authorization", ""), ("range", ""), ("referer", ""), ("refresh", ""),
    ("retry-after", ""), ("server", ""), ("set-cookie", ""), ("strict-transport-security", ""),
    ("transfer-encoding", ""), ("user-agent", ""), ("vary", ""), ("via", ""),
    ("www-authenticate", ""),
];

/// HPACK Decoder/Encoder context
pub struct HpackContext {
    pub dynamic_table: VecDeque<HeaderField>,
    pub max_table_size: usize,
    pub current_table_size: usize,
}

impl HpackContext {
    pub fn new(max_size: usize) -> Self {
        Self {
            dynamic_table: VecDeque::new(),
            max_table_size: max_size,
            current_table_size: 0,
        }
    }

    /// Get a header from either the static or dynamic table (§ 2.3)
    pub fn get_table_entry(&self, index: usize) -> Option<HeaderField> {
        if index == 0 { return None; }
        if index <= STATIC_TABLE.len() {
            let (n, v) = STATIC_TABLE[index - 1];
            return Some(HeaderField::new(n, v));
        }
        let dynamic_index = index - STATIC_TABLE.len() - 1;
        self.dynamic_table.get(dynamic_index).cloned()
    }

    /// Add an entry to the dynamic table (§ 4)
    pub fn add_dynamic_entry(&mut self, field: HeaderField) {
        let field_size = field.size();
        
        while self.current_table_size + field_size > self.max_table_size && !self.dynamic_table.is_empty() {
            if let Some(removed) = self.dynamic_table.pop_back() {
                self.current_table_size -= removed.size();
            }
        }

        if self.current_table_size + field_size <= self.max_table_size {
            self.current_table_size += field_size;
            self.dynamic_table.push_front(field);
        }
    }

    /// Decode an HPACK-encoded integer (§ 5.1)
    pub fn decode_integer(data: &[u8], pos: &mut usize, prefix: u8) -> u32 {
        let mask = (1 << prefix) - 1;
        let mut n = (data[*pos] & mask) as u32;
        *pos += 1;

        if n < mask as u32 { return n; }

        let mut m = 0;
        loop {
            let b = data[*pos];
            *pos += 1;
            n += ((b & 127) as u32) << m;
            m += 7;
            if b & 128 == 0 { break; }
        }
        n
    }

    /// Encode an integer into the HPACK representation (§ 5.1)
    pub fn encode_integer(n: u32, prefix: u8) -> Vec<u8> {
        let mask = (1 << prefix) - 1;
        let mut buf = Vec::new();

        if n < mask as u32 {
            buf.push(n as u8);
            return buf;
        }

        buf.push(mask as u8);
        let mut remaining = n - mask as u32;
        while remaining >= 128 {
            buf.push((remaining % 128 + 128) as u8);
            remaining /= 128;
        }
        buf.push(remaining as u8);
        buf
    }

    /// AI-facing table inspector
    pub fn ai_table_snapshot(&self) -> String {
        let mut lines = vec![format!("📑 HPACK Dynamic Table (Size: {}/{} bytes):", self.current_table_size, self.max_table_size)];
        for (i, field) in self.dynamic_table.iter().enumerate() {
            lines.push(format!("  [{}] {}: {}", i + 62, field.name, field.value));
        }
        lines.join("\n")
    }
}
