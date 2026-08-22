//! Storage Manager — Central Registry for Origin-Isolated Memory
//!
//! Handles lifecycle of LocalStorage and IndexedDB instances per origin.

use std::collections::HashMap;
use std::sync::{Arc, RwLock};
use std::path::PathBuf;
use anyhow::Result;
use crate::local_storage::LocalStorage;
use crate::indexed_db::IndexedDbManager;

pub struct StorageManager {
    base_path: PathBuf,
    local_storages: Arc<RwLock<HashMap<String, Arc<LocalStorage>>>>,
    indexed_dbs: Arc<RwLock<HashMap<String, Arc<IndexedDbManager>>>>,
}

impl StorageManager {
    pub fn new(base_path: PathBuf) -> Self {
        Self {
            base_path,
            local_storages: Arc::new(RwLock::new(HashMap::new())),
            indexed_dbs: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    pub fn get_local_storage(&self, origin: &str) -> Result<Arc<LocalStorage>> {
        let mut storages = self.local_storages.write().unwrap();
        if let Some(storage) = storages.get(origin) {
            return Ok(storage.clone());
        }

        let db_path = self.base_path.join("local_storage.sled");
        let storage = Arc::new(LocalStorage::new(origin, &db_path)?);
        storages.insert(origin.to_string(), storage.clone());
        Ok(storage)
    }

    pub fn get_indexed_db(&self, origin: &str) -> Result<Arc<IndexedDbManager>> {
        let mut dbs = self.indexed_dbs.write().unwrap();
        if let Some(db) = dbs.get(origin) {
            return Ok(db.clone());
        }

        let db_path = self.base_path.join("indexed_db.sled");
        let db = Arc::new(IndexedDbManager::new(origin, &db_path)?);
        dbs.insert(origin.to_string(), db.clone());
        Ok(db)
    }

    pub fn clear_origin(&self, origin: &str) -> Result<()> {
        let ls = self.get_local_storage(origin)?;
        ls.clear()?;
        // IndexedDB clear logic would go here
        Ok(())
    }
}
