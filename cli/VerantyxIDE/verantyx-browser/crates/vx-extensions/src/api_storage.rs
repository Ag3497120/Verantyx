//! Chrome Storage API Implementation
//!
//! Replicates `chrome.storage.local` and `chrome.storage.sync` allowing
//! extensions natively installed into Verantyx to persist their states safely.

use std::collections::HashMap;
use std::sync::{Arc, RwLock};

pub struct ChromeStorageArea {
    // Basic in-memory mock for state isolation; integrates to vx-storage
    data: Arc<RwLock<HashMap<String, serde_json::Value>>>,
}

impl ChromeStorageArea {
    pub fn new() -> Self {
        Self {
            data: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    pub fn get(&self, keys: Option<Vec<String>>) -> HashMap<String, serde_json::Value> {
        let store = self.data.read().unwrap();
        if let Some(keys) = keys {
            let mut result = HashMap::new();
            for k in keys {
                if let Some(v) = store.get(&k) {
                    result.insert(k.clone(), v.clone());
                }
            }
            result
        } else {
            store.clone()
        }
    }

    pub fn set(&self, items: HashMap<String, serde_json::Value>) {
        let mut store = self.data.write().unwrap();
        for (k, v) in items {
            store.insert(k, v);
        }
    }

    pub fn remove(&self, keys: Vec<String>) {
        let mut store = self.data.write().unwrap();
        for k in keys {
            store.remove(&k);
        }
    }

    pub fn clear(&self) {
        let mut store = self.data.write().unwrap();
        store.clear();
    }
}

pub struct ChromeStorageApi {
    pub local: ChromeStorageArea,
    pub sync: ChromeStorageArea,
    pub session: ChromeStorageArea,
}

impl Default for ChromeStorageApi {
    fn default() -> Self {
        Self {
            local: ChromeStorageArea::new(),
            sync: ChromeStorageArea::new(),
            session: ChromeStorageArea::new(),
        }
    }
}
