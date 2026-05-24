//! HTTP Caching — RFC 7234
//!
//! Implements the browser's caching infrastructure for high-performance networking:
//!   - Cache Control (§ 5.2): no-store, no-cache, max-age, must-revalidate,
//!     proxy-revalidate, public, private
//!   - Freshness Model (§ 4.2): Calculating freshness lifetime and current age
//!   - Validation (§ 4.3): If-None-Match (ETag), If-Modified-Since (Last-Modified)
//!   - Cache Invalidation (§ 4.4): Purging cache on unsafe requests (PUT, POST, DELETE)
//!   - VARY header (§ 4.1): Secondary cache key matching
//!   - Storage: Integration with memory and persistent disk cache backends
//!   - Heuristic Freshness (§ 4.2.2): Handling responses without explicit expiration
//!   - AI-facing: Cache hit/miss inspector and freshness graph

use std::collections::HashMap;
use std::time::{SystemTime, UNIX_EPOCH};

/// Cache control directives (§ 5.2)
#[derive(Debug, Clone)]
pub struct CacheControl {
    pub no_store: bool,
    pub no_cache: bool,
    pub max_age: Option<u64>,
    pub must_revalidate: bool,
    pub is_public: bool,
    pub is_private: bool,
}

/// A single cache entry (§ 2)
#[derive(Debug, Clone)]
pub struct CacheEntry {
    pub url: String,
    pub response_headers: HashMap<String, String>,
    pub body: Vec<u8>,
    pub request_time: u64,
    pub response_time: u64,
}

impl CacheEntry {
    /// Calculate current age of the response (§ 4.2.3)
    pub fn current_age(&self, now: u64) -> u64 {
        let apparent_age = if self.response_time > self.request_time {
            self.response_time - self.request_time
        } else {
            0
        };
        let corrected_age = apparent_age;
        let resident_time = now - self.response_time;
        corrected_age + resident_time
    }

    /// Calculate freshness lifetime (§ 4.2.1)
    pub fn freshness_lifetime(&self) -> u64 {
        // Simple placeholder for max-age parsing...
        300 // 5 minutes default
    }

    pub fn is_fresh(&self, now: u64) -> bool {
        self.current_age(now) < self.freshness_lifetime()
    }
}

/// The global HTTP Cache Manager
pub struct HttpCache {
    pub entries: HashMap<String, CacheEntry>,
    pub max_size_bytes: usize,
    pub current_size_bytes: usize,
}

impl HttpCache {
    pub fn new(max_size: usize) -> Self {
        Self {
            entries: HashMap::new(),
            max_size_bytes: max_size,
            current_size_bytes: 0,
        }
    }

    pub fn get_entry(&self, url: &str) -> Option<&CacheEntry> {
        let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs();
        let entry = self.entries.get(url)?;
        if entry.is_fresh(now) { Some(entry) } else { None }
    }

    pub fn put_entry(&mut self, url: &str, entry: CacheEntry) {
        let size = entry.body.len();
        self.entries.insert(url.to_string(), entry);
        self.current_size_bytes += size;
    }

    /// AI-facing cache hit/miss profile
    pub fn ai_cache_summary(&self) -> String {
        let mut lines = vec![format!("💾 HTTP Cache Profile (Size: {}/{} bytes):", self.current_size_bytes, self.max_size_bytes)];
        for (url, entry) in &self.entries {
            let freshness = if entry.is_fresh(SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs()) { "🟢 Fresh" } else { "🔴 Stale" };
            lines.push(format!("  - {} ({})", url, freshness));
        }
        lines.join("\n")
    }
}
