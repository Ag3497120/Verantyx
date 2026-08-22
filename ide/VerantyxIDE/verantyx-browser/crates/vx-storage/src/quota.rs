//! Sovereign Quota Management — Storage Limits per Origin
//!
//! Tracks and enforces storage limits across LocalStorage, IndexedDB, and Cache.

use std::collections::HashMap;
use std::sync::{Arc, RwLock};
use anyhow::{Result, bail};

#[derive(Debug, Clone, Default)]
pub struct QuotaState {
    pub used_bytes: u64,
    pub limit_bytes: u64,
}

pub struct QuotaManager {
    quotas: Arc<RwLock<HashMap<String, QuotaState>>>,
    default_limit: u64,
}

impl QuotaManager {
    pub fn new(default_limit: u64) -> Self {
        Self {
            quotas: Arc::new(RwLock::new(HashMap::new())),
            default_limit,
        }
    }

    /// Request a storage allocation for an origin
    pub fn request_quota(&self, origin: &str, requested_bytes: u64) -> Result<()> {
        let mut quotas = self.quotas.write().unwrap();
        let state = quotas.entry(origin.to_string()).or_insert(QuotaState {
            used_bytes: 0,
            limit_bytes: self.default_limit,
        });

        if state.used_bytes + requested_bytes > state.limit_bytes {
            bail!("QuotaExceededError: Storage limit for {} is exceeded", origin);
        }

        state.used_bytes += requested_bytes;
        Ok(())
    }

    /// Release a storage allocation for an origin
    pub fn release_quota(&self, origin: &str, released_bytes: u64) {
        let mut quotas = self.quotas.write().unwrap();
        if let Some(state) = quotas.get_mut(origin) {
            state.used_bytes = state.used_bytes.saturating_sub(released_bytes);
        }
    }

    pub fn get_usage(&self, origin: &str) -> QuotaState {
        let quotas = self.quotas.read().unwrap();
        quotas.get(origin).cloned().unwrap_or(QuotaState {
            used_bytes: 0,
            limit_bytes: self.default_limit,
        })
    }
}

pub const DEFAULT_STORAGE_LIMIT: u64 = 50 * 1024 * 1024; // 50MB
