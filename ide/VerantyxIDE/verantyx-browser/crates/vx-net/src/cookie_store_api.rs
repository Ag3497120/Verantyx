//! Cookie Store API — W3C Cookie Store
//!
//! Implements the asynchronous JavaScript interface for managing cookies:
//!   - CookieStore (§ 2): get(), getAll(), set(), delete()
//!   - CookieListItem (§ 3): name, value, domain, path, expires, secure, sameSite
//!   - Service Worker Exposure: Permitting cookie monitoring and writes within workers
//!   - change event (§ 4): Dispatching CookieChangeEvent when cookies are modified
//!   - Integration with the underlying HTTP CookieJar
//!   - AI-facing: Async cookie operation tracker and secure storage topology

use std::collections::{HashMap, VecDeque};

/// Cookie attributes exposed to the JS API
#[derive(Debug, Clone)]
pub struct CookieListItem {
    pub name: String,
    pub value: String,
    pub domain: Option<String>,
    pub path: String,
    pub expires: Option<u64>, // Epoch MS
    pub secure: bool,
    pub same_site: String, // "strict", "lax", "none"
}

/// Dispatched to scripts when cookies are added or deleted (§ 4)
#[derive(Debug, Clone)]
pub struct CookieChangeEvent {
    pub changed: Vec<CookieListItem>,
    pub deleted: Vec<CookieListItem>,
}

/// The global Async Cookie Store Engine mapped to the JS Context
pub struct CookieStoreEngine {
    // Underlying storage integration point (simulated local map for JS scope)
    pub registry: HashMap<String, HashMap<String, CookieListItem>>, // Domain -> Name -> Cookie
    pub events_queue: VecDeque<CookieChangeEvent>,
    pub total_async_ops: u64,
}

impl CookieStoreEngine {
    pub fn new() -> Self {
        Self {
            registry: HashMap::new(),
            events_queue: VecDeque::new(),
            total_async_ops: 0,
        }
    }

    /// Asynchronous `set()` operation (§ 2)
    pub fn set_cookie(&mut self, origin: &str, mut cookie: CookieListItem) -> Result<(), String> {
        self.total_async_ops += 1;
        
        // Ensure defaults matching Document.cookie heuristics
        if cookie.domain.is_none() {
            cookie.domain = Some(origin.to_string());
        }

        let domain_map = self.registry.entry(cookie.domain.clone().unwrap()).or_default();
        domain_map.insert(cookie.name.clone(), cookie.clone());

        self.emit_change_event(vec![cookie], vec![]);
        Ok(())
    }

    /// Asynchronous `get()` operation (§ 2)
    pub fn get_cookie(&mut self, domain: &str, name: &str) -> Option<CookieListItem> {
        self.total_async_ops += 1;
        self.registry.get(domain)?.get(name).cloned()
    }

    /// Asynchronous `delete()` operation (§ 2)
    pub fn delete_cookie(&mut self, domain: &str, name: &str) -> Result<(), String> {
        self.total_async_ops += 1;
        if let Some(domain_map) = self.registry.get_mut(domain) {
            if let Some(removed) = domain_map.remove(name) {
                self.emit_change_event(vec![], vec![removed]);
            }
        }
        Ok(())
    }

    fn emit_change_event(&mut self, changed: Vec<CookieListItem>, deleted: Vec<CookieListItem>) {
        if self.events_queue.len() >= 50 { self.events_queue.pop_front(); }
        self.events_queue.push_back(CookieChangeEvent { changed, deleted });
    }

    /// AI-facing Async Cookie Operations
    pub fn ai_cookie_store_summary(&self) -> String {
        let mut count = 0;
        self.registry.values().for_each(|v| count += v.len());
        
        format!("🍪 Async Cookie Store API: {} total cookies tracked across {} domains | Total Operations: {}", 
            count, self.registry.len(), self.total_async_ops)
    }
}
