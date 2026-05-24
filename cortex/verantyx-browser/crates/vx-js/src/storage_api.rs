//! Web Storage API — W3C Web Storage Living Standard
//!
//! Implements the complete browser storage system:
//!   - localStorage (persistent across sessions, same-origin isolated)
//!   - sessionStorage (per-tab, clears on session end)
//!   - Storage interface: getItem, setItem, removeItem, clear, key(n), length
//!   - StorageEvent dispatch on cross-tab mutations (via shared storage)
//!   - Origin isolation (scheme + host + port)
//!   - Quota enforcement (per-origin limit, default 5MB like Chrome)
//!   - Storage event key, oldValue, newValue, url, storageArea fields
//!   - AI-facing: structured storage dump per origin

use std::collections::{HashMap, BTreeMap, VecDeque};

/// The maximum storage size per origin (5 MB in bytes, matching Chrome default)
pub const DEFAULT_QUOTA_BYTES: usize = 5 * 1024 * 1024;

/// A Storage event (dispatched to other documents sharing the same storage)
#[derive(Debug, Clone)]
pub struct StorageEvent {
    pub key: Option<String>,       // None = clear()
    pub old_value: Option<String>,
    pub new_value: Option<String>,
    pub url: String,               // URL of the document that made the change
    pub storage_type: StorageType,
    pub origin: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StorageType { Local, Session }

/// Possible errors returned by Storage operations
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum StorageError {
    /// DOM Exception: QuotaExceededError
    QuotaExceeded { used: usize, quota: usize, key: String },
    /// Key not found (getItem returns null, not an error per spec, but useful internally)
    NotFound,
    /// Invalid origin
    InvalidOrigin,
}

impl std::fmt::Display for StorageError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::QuotaExceeded { used, quota, key } =>
                write!(f, "QuotaExceededError: quota {}B exceeded (used {}B) while setting '{}'", quota, used, key),
            Self::NotFound => write!(f, "Key not found"),
            Self::InvalidOrigin => write!(f, "Invalid origin"),
        }
    }
}

/// The core in-memory storage area for one origin
#[derive(Debug, Clone, Default)]
pub struct StorageArea {
    /// Ordered by insertion time (BTreeMap for stable key() ordering)
    items: BTreeMap<String, String>,
    /// Tracks insertion order for key(n) semantics
    key_order: Vec<String>,
    /// Per-origin quota in bytes
    pub quota: usize,
}

impl StorageArea {
    pub fn new(quota: usize) -> Self {
        Self { items: BTreeMap::new(), key_order: Vec::new(), quota }
    }

    /// Storage.length — number of key/value pairs
    pub fn length(&self) -> usize { self.items.len() }

    /// Storage.key(n) — returns the n-th key in insertion order
    pub fn key(&self, n: usize) -> Option<&str> {
        self.key_order.get(n).and_then(|k| {
            if self.items.contains_key(k.as_str()) { Some(k.as_str()) } else { None }
        })
    }

    /// Storage.getItem(key) — returns None if not present
    pub fn get_item(&self, key: &str) -> Option<&str> {
        self.items.get(key).map(|v| v.as_str())
    }

    /// Storage.setItem(key, value) — may return QuotaExceeded
    pub fn set_item(&mut self, key: &str, value: &str) -> Result<Option<String>, StorageError> {
        let old_value = self.items.get(key).cloned();

        // Compute new total bytes if we add/overwrite this entry
        let current_usage = self.byte_usage();
        let old_entry_size = old_value.as_ref().map(|v| key.len() + v.len()).unwrap_or(0);
        let new_entry_size = key.len() + value.len();
        let projected = current_usage - old_entry_size + new_entry_size;

        if projected > self.quota {
            return Err(StorageError::QuotaExceeded {
                used: projected,
                quota: self.quota,
                key: key.to_string(),
            });
        }

        // Update insertion order tracking
        if !self.items.contains_key(key) {
            self.key_order.push(key.to_string());
        }

        self.items.insert(key.to_string(), value.to_string());
        Ok(old_value)
    }

    /// Storage.removeItem(key)
    pub fn remove_item(&mut self, key: &str) -> Option<String> {
        let old = self.items.remove(key);
        if old.is_some() {
            self.key_order.retain(|k| k != key);
        }
        old
    }

    /// Storage.clear()
    pub fn clear(&mut self) {
        self.items.clear();
        self.key_order.clear();
    }

    /// Total byte usage (sum of key.len + value.len for all entries)
    pub fn byte_usage(&self) -> usize {
        self.items.iter().map(|(k, v)| k.len() + v.len()).sum()
    }

    /// Remaining quota in bytes
    pub fn remaining_quota(&self) -> usize {
        self.quota.saturating_sub(self.byte_usage())
    }

    /// Iterate all key-value pairs
    pub fn iter(&self) -> impl Iterator<Item = (&str, &str)> {
        self.items.iter().map(|(k, v)| (k.as_str(), v.as_str()))
    }

    /// AI-facing dump
    pub fn ai_dump(&self, label: &str, origin: &str) -> String {
        let mut lines = vec![format!(
            "💾 {} [{}] — {}/{} bytes ({} items)",
            label, origin, self.byte_usage(), self.quota, self.length()
        )];
        for (k, v) in &self.items {
            let truncated_v = if v.len() > 80 { format!("{}…", &v[..80]) } else { v.clone() };
            lines.push(format!("  {:30} = {}", k, truncated_v));
        }
        lines.join("\n")
    }
}

/// A per-origin, per-tab session storage area
#[derive(Debug, Clone, Default)]
pub struct SessionStorageArea {
    pub inner: StorageArea,
    pub tab_id: u64,
    pub origin: String,
}

impl SessionStorageArea {
    pub fn new(tab_id: u64, origin: &str, quota: usize) -> Self {
        Self { inner: StorageArea::new(quota), tab_id, origin: origin.to_string() }
    }
}

/// The global Web Storage manager
pub struct WebStorageManager {
    /// localStorage: origin -> Storage area (shared across tabs)
    local_storage: HashMap<String, StorageArea>,
    /// sessionStorage: (origin, tab_id) -> Storage area (tab-scoped)
    session_storage: HashMap<(String, u64), StorageArea>,
    /// StorageEvent queue for delivery to other same-origin frames
    pending_events: VecDeque<StorageEvent>,
    /// Per-origin quota override
    quota_overrides: HashMap<String, usize>,
    pub default_quota: usize,
}

impl WebStorageManager {
    pub fn new() -> Self {
        Self {
            local_storage: HashMap::new(),
            session_storage: HashMap::new(),
            pending_events: VecDeque::new(),
            quota_overrides: HashMap::new(),
            default_quota: DEFAULT_QUOTA_BYTES,
        }
    }

    fn quota_for(&self, origin: &str) -> usize {
        self.quota_overrides.get(origin).copied().unwrap_or(self.default_quota)
    }

    // ──────────────────────────────────────────
    //  localStorage Operations
    // ──────────────────────────────────────────

    pub fn local_get_item(&self, origin: &str, key: &str) -> Option<&str> {
        self.local_storage.get(origin)?.get_item(key)
    }

    pub fn local_set_item(
        &mut self,
        origin: &str,
        key: &str,
        value: &str,
        document_url: &str,
    ) -> Result<(), StorageError> {
        let quota = self.quota_for(origin);
        let area = self.local_storage
            .entry(origin.to_string())
            .or_insert_with(|| StorageArea::new(quota));

        let old_value = area.set_item(key, value)?;

        // Queue StorageEvent for other same-origin tabs
        self.pending_events.push_back(StorageEvent {
            key: Some(key.to_string()),
            old_value,
            new_value: Some(value.to_string()),
            url: document_url.to_string(),
            storage_type: StorageType::Local,
            origin: origin.to_string(),
        });

        Ok(())
    }

    pub fn local_remove_item(&mut self, origin: &str, key: &str, document_url: &str) -> Option<String> {
        let area = self.local_storage.get_mut(origin)?;
        let old = area.remove_item(key)?;

        self.pending_events.push_back(StorageEvent {
            key: Some(key.to_string()),
            old_value: Some(old.clone()),
            new_value: None,
            url: document_url.to_string(),
            storage_type: StorageType::Local,
            origin: origin.to_string(),
        });

        Some(old)
    }

    pub fn local_clear(&mut self, origin: &str, document_url: &str) {
        if let Some(area) = self.local_storage.get_mut(origin) {
            area.clear();
            self.pending_events.push_back(StorageEvent {
                key: None,
                old_value: None,
                new_value: None,
                url: document_url.to_string(),
                storage_type: StorageType::Local,
                origin: origin.to_string(),
            });
        }
    }

    pub fn local_length(&self, origin: &str) -> usize {
        self.local_storage.get(origin).map(|a| a.length()).unwrap_or(0)
    }

    pub fn local_key(&self, origin: &str, n: usize) -> Option<&str> {
        self.local_storage.get(origin)?.key(n)
    }

    // ──────────────────────────────────────────
    //  sessionStorage Operations
    // ──────────────────────────────────────────

    pub fn session_get_item(&self, origin: &str, tab_id: u64, key: &str) -> Option<&str> {
        self.session_storage.get(&(origin.to_string(), tab_id))?.get_item(key)
    }

    pub fn session_set_item(
        &mut self,
        origin: &str,
        tab_id: u64,
        key: &str,
        value: &str,
        document_url: &str,
    ) -> Result<(), StorageError> {
        let quota = self.quota_for(origin);
        let area = self.session_storage
            .entry((origin.to_string(), tab_id))
            .or_insert_with(|| StorageArea::new(quota));

        let old_value = area.set_item(key, value)?;

        self.pending_events.push_back(StorageEvent {
            key: Some(key.to_string()),
            old_value,
            new_value: Some(value.to_string()),
            url: document_url.to_string(),
            storage_type: StorageType::Session,
            origin: origin.to_string(),
        });

        Ok(())
    }

    pub fn session_remove_item(&mut self, origin: &str, tab_id: u64, key: &str, document_url: &str) -> Option<String> {
        let area = self.session_storage.get_mut(&(origin.to_string(), tab_id))?;
        let old = area.remove_item(key)?;
        self.pending_events.push_back(StorageEvent {
            key: Some(key.to_string()),
            old_value: Some(old.clone()),
            new_value: None,
            url: document_url.to_string(),
            storage_type: StorageType::Session,
            origin: origin.to_string(),
        });
        Some(old)
    }

    pub fn session_clear(&mut self, origin: &str, tab_id: u64, document_url: &str) {
        if let Some(area) = self.session_storage.get_mut(&(origin.to_string(), tab_id)) {
            area.clear();
            self.pending_events.push_back(StorageEvent {
                key: None, old_value: None, new_value: None,
                url: document_url.to_string(),
                storage_type: StorageType::Session,
                origin: origin.to_string(),
            });
        }
    }

    /// Remove all sessionStorage areas for a closed tab
    pub fn close_tab(&mut self, tab_id: u64) {
        self.session_storage.retain(|(_, tid), _| *tid != tab_id);
    }

    // ──────────────────────────────────────────
    //  Event Dispatch
    // ──────────────────────────────────────────

    pub fn take_events(&mut self) -> Vec<StorageEvent> {
        self.pending_events.drain(..).collect()
    }

    pub fn take_events_for_origin(&mut self, origin: &str) -> Vec<StorageEvent> {
        let mut out = Vec::new();
        let mut remaining = VecDeque::new();
        while let Some(ev) = self.pending_events.pop_front() {
            if ev.origin == origin { out.push(ev); }
            else { remaining.push_back(ev); }
        }
        self.pending_events = remaining;
        out
    }

    // ──────────────────────────────────────────
    //  Quota Management
    // ──────────────────────────────────────────

    pub fn local_usage(&self, origin: &str) -> usize {
        self.local_storage.get(origin).map(|a| a.byte_usage()).unwrap_or(0)
    }

    pub fn set_quota_override(&mut self, origin: &str, quota: usize) {
        self.quota_overrides.insert(origin.to_string(), quota);
    }

    // ──────────────────────────────────────────
    //  AI-facing
    // ──────────────────────────────────────────

    pub fn ai_storage_snapshot(&self, origin: &str) -> String {
        let mut lines = Vec::new();

        if let Some(area) = self.local_storage.get(origin) {
            lines.push(area.ai_dump("localStorage", origin));
        } else {
            lines.push(format!("💾 localStorage [{}] — empty", origin));
        }

        let session_areas: Vec<_> = self.session_storage.iter()
            .filter(|((o, _), _)| o == origin)
            .collect();

        for ((_, tab_id), area) in &session_areas {
            lines.push(area.ai_dump(&format!("sessionStorage[tab#{}]", tab_id), origin));
        }

        lines.join("\n\n")
    }

    pub fn ai_quota_summary(&self) -> String {
        let mut lines = vec!["📊 Storage Quota Summary:".to_string()];
        for (origin, area) in &self.local_storage {
            let pct = (area.byte_usage() as f64 / area.quota as f64 * 100.0) as u32;
            lines.push(format!("  {} — {}/{} bytes ({}%)", origin, area.byte_usage(), area.quota, pct));
        }
        lines.join("\n")
    }
}

/// Parse an origin string from a URL (scheme + host + port)
pub fn parse_origin(url: &str) -> String {
    let scheme_end = url.find("://").unwrap_or(0);
    let after_scheme = &url[scheme_end + 3..];
    let host_end = after_scheme.find('/').unwrap_or(after_scheme.len());
    let host_part = &after_scheme[..host_end];

    // Remove path
    let scheme = &url[..scheme_end];
    format!("{}://{}", scheme, host_part)
}
