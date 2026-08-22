//! vx-storage — Sovereign Persistent Memory for Verantyx Browser
//!
//! Provides origin-isolated LocalStorage, SessionStorage, and IndexedDB with sled persistence.

pub mod local_storage;
pub mod indexed_db;
pub mod storage_manager;
pub mod quota;
pub mod session_storage;
pub mod cache;

pub use storage_manager::StorageManager;
pub use local_storage::LocalStorage;
pub use indexed_db::IndexedDbManager;
pub use quota::QuotaManager;
pub mod indexed_db_v2;
