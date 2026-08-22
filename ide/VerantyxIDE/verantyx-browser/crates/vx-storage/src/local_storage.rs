//! Sovereign LocalStorage — Persistent, Origin-Isolated Key-Value Memory
//!
//! Implementation of the W3C Storage spec using 'sled' as the persistent backend.

use std::collections::HashMap;
use std::sync::{Arc, RwLock};
use anyhow::Result;
use serde::{Serialize, Deserialize};

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct StorageData {
    pub map: HashMap<String, String>,
}

pub struct LocalStorage {
    origin: String,
    data: Arc<RwLock<StorageData>>,
    db: sled::Db,
}

impl LocalStorage {
    pub fn new(origin: &str, db_path: &std::path::Path) -> Result<Self> {
        let db = sled::open(db_path)?;
        let origin_key = format!("ls_{}", origin);
        
        let initial_data = if let Some(bytes) = db.get(&origin_key)? {
            serde_json::from_slice(&bytes).unwrap_or_default()
        } else {
            StorageData::default()
        };

        Ok(Self {
            origin: origin.to_string(),
            data: Arc::new(RwLock::new(initial_data)),
            db,
        })
    }

    pub fn set_item(&self, key: &str, value: &str) -> Result<()> {
        {
            let mut data = self.data.write().unwrap();
            data.map.insert(key.to_string(), value.to_string());
        }
        self.persist()
    }

    pub fn get_item(&self, key: &str) -> Option<String> {
        let data = self.data.read().unwrap();
        data.map.get(key).cloned()
    }

    pub fn remove_item(&self, key: &str) -> Result<()> {
        {
            let mut data = self.data.write().unwrap();
            data.map.remove(key);
        }
        self.persist()
    }

    pub fn clear(&self) -> Result<()> {
        {
            let mut data = self.data.write().unwrap();
            data.map.clear();
        }
        self.persist()
    }

    pub fn length(&self) -> usize {
        let data = self.data.read().unwrap();
        data.map.len()
    }

    fn persist(&self) -> Result<()> {
        let data = self.data.read().unwrap();
        let bytes = serde_json::to_vec(&*data)?;
        let origin_key = format!("ls_{}", self.origin);
        self.db.insert(origin_key, bytes)?;
        self.db.flush()?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn test_local_storage_persistence() -> Result<()> {
        let dir = tempdir()?;
        let db_path = dir.path().join("test_db");
        
        {
            let ls = LocalStorage::new("example.com", &db_path)?;
            ls.set_item("key1", "value1")?;
            assert_eq!(ls.get_item("key1"), Some("value1".to_string()));
        }

        // Re-open and verify persistence
        {
            let ls = LocalStorage::new("example.com", &db_path)?;
            assert_eq!(ls.get_item("key1"), Some("value1".to_string()));
            ls.remove_item("key1")?;
            assert_eq!(ls.get_item("key1"), None);
        }

        Ok(())
    }
}
