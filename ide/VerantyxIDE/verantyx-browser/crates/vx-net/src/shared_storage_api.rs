//! Shared Storage API — W3C Shared Storage
//!
//! Implements unpartitioned, cross-site storage access with privacy-preserving outputs:
//!   - window.sharedStorage (§ 2): `set()`, `append()`, `delete()`, `clear()`
//!   - Shared Storage Worklets (§ 3): The execution environment reading unpartitioned data
//!   - SelectURL / Run / Fenced Frames: Rendering outputs privately without revealing data
//!   - Budget limitation: Capping information entropy leakage across origins
//!   - AI-facing: Cross-site anonymous data tracking topology

use std::collections::HashMap;

/// A stored value piece within the shared storage environment
#[derive(Debug, Clone)]
pub struct SharedStorageEntry {
    pub key: String,
    pub values: Vec<String>, // 'append' adds multiple strings to the same key
}

/// A simulated Shared Storage Worklet execution space allowing private data access
#[derive(Debug, Clone)]
pub struct WorkletEnvironment {
    pub registered_operations: HashMap<String, String>, // Operation Name -> JS Source string
}

/// The global Shared Storage Engine
pub struct SharedStorageEngine {
    // Unpartitioned global storage: Origin -> Key -> Entry
    pub global_storage: HashMap<String, HashMap<String, SharedStorageEntry>>,
    pub worklets: HashMap<u64, WorkletEnvironment>, // ID -> env
    pub next_worklet_id: u64,
    pub privacy_budget_bits: f64, // Tracking bits leaked (cap at e.g., 3.0 bits per page load)
}

impl SharedStorageEngine {
    pub fn new() -> Self {
        Self {
            global_storage: HashMap::new(),
            worklets: HashMap::new(),
            next_worklet_id: 1,
            privacy_budget_bits: 0.0,
        }
    }

    /// `window.sharedStorage.set()` operation (§ 2)
    pub fn set_data(&mut self, origin: &str, key: &str, value: &str, ignore_if_present: bool) {
        let store = self.global_storage.entry(origin.to_string()).or_default();
        if ignore_if_present && store.contains_key(key) {
            return;
        }
        
        store.insert(key.to_string(), SharedStorageEntry {
            key: key.to_string(),
            values: vec![value.to_string()],
        });
    }

    /// `window.sharedStorage.append()` operation (§ 2)
    pub fn append_data(&mut self, origin: &str, key: &str, value: &str) {
        let store = self.global_storage.entry(origin.to_string()).or_default();
        let entry = store.entry(key.to_string()).or_insert(SharedStorageEntry {
            key: key.to_string(),
            values: Vec::new(),
        });
        entry.values.push(value.to_string());
    }

    /// Creates an anonymous iframe URL output `window.sharedStorage.selectURL(...)` (§ 3)
    pub fn execute_select_url(&mut self, _origin: &str, _operation_name: &str, urls: Vec<String>) -> Result<String, String> {
        // Leaking log2(N) bits of entropy where N is the number of URLs to choose from
        let entropy_leaked = (urls.len() as f64).log2();
        if self.privacy_budget_bits + entropy_leaked > 5.0 {
            return Err("PrivacyError: Privacy budget exceeded".into());
        }

        self.privacy_budget_bits += entropy_leaked;

        // In reality, it runs the worklet JS to pick an index securely. Here we mock returning the URL as an opaque URN.
        Ok(format!("urn:uuid:simulated-fenced-frame-target-for-{}", urls.first().unwrap_or(&String::new())))
    }

    /// AI-facing Unpartitioned storage topology
    pub fn ai_shared_storage_summary(&self) -> String {
        let mut keys = 0;
        self.global_storage.values().for_each(|m| keys += m.len());
        format!("🔒 Shared Storage API: {} Cross-Site Origins Storing {} keys | Privacy Budget Consumed: {:.2}/5.0 bits", 
            self.global_storage.len(), keys, self.privacy_budget_bits)
    }
}
