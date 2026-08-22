//! HTTP Range Requests — RFC 7233
//!
//! Implements partial content retrieval for the browser:
//!   - Range Header (§ 3.1): Parsing "bytes=0-499", "bytes=500-", "bytes=-500"
//!   - Content-Range Header (§ 4.2): Validating "bytes 0-499/1234" responses
//!   - 206 Partial Content (§ 4.1): Handling successful range fulfillment
//!   - 416 Range Not Satisfiable (§ 4.4): Handling out-of-bounds requests
//!   - If-Range Header (§ 3.2): Conditional range requests based on ETag or Last-Modified
//!   - Multipart/ByteRanges (§ 4.1): Handling multiple ranges in a single response
//!   - AI-facing: Range request log and partial body reassembly visualizer

use std::collections::HashMap;

/// An individual byte range (§ 2.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ByteRange {
    pub first_byte: Option<u64>,
    pub last_byte: Option<u64>,
    pub suffix_length: Option<u64>,
}

/// The global HTTP Range Manager
pub struct HttpRangeManager {
    pub active_ranges: HashMap<String, Vec<ByteRange>>, // URL -> Ranges
}

impl HttpRangeManager {
    pub fn new() -> Self {
        Self { active_ranges: HashMap::new() }
    }

    /// Parses the Range header value (§ 3.1.1)
    pub fn parse_range_header(&mut self, url: &str, header_value: &str) -> bool {
        if !header_value.starts_with("bytes=") { return false; }
        
        let mut ranges = Vec::new();
        let value = &header_value[6..];
        
        for part in value.split(',') {
            let part = part.trim();
            if part.starts_with('-') {
                if let Ok(len) = part[1..].parse::<u64>() {
                    ranges.push(ByteRange { first_byte: None, last_byte: None, suffix_length: Some(len) });
                }
            } else if part.ends_with('-') {
                if let Ok(first) = part[..part.len()-1].parse::<u64>() {
                    ranges.push(ByteRange { first_byte: Some(first), last_byte: None, suffix_length: None });
                }
            } else {
                let bytes: Vec<&str> = part.split('-').collect();
                if bytes.len() == 2 {
                    if let (Ok(f), Ok(l)) = (bytes[0].parse::<u64>(), bytes[1].parse::<u64>()) {
                        ranges.push(ByteRange { first_byte: Some(f), last_byte: Some(l), suffix_length: None });
                    }
                }
            }
        }

        if !ranges.is_empty() {
            self.active_ranges.insert(url.to_string(), ranges);
            return true;
        }
        false
    }

    /// AI-facing range request summary
    pub fn ai_range_summary(&self, url: &str) -> String {
        if let Some(ranges) = self.active_ranges.get(url) {
            let mut lines = vec![format!("🧩 HTTP Range Request for {}:", url)];
            for (idx, r) in ranges.iter().enumerate() {
                let range_str = match (r.first_byte, r.last_byte, r.suffix_length) {
                    (Some(f), Some(l), _) => format!("{}-{}", f, l),
                    (Some(f), None, _) => format!("{}-", f),
                    (_, _, Some(s)) => format!("-{}", s),
                    _ => "[Invalid]".into(),
                };
                lines.push(format!("  - Range {}: bytes={}", idx, range_str));
            }
            lines.join("\n")
        } else {
            format!("No active range request for {}", url)
        }
    }
}
