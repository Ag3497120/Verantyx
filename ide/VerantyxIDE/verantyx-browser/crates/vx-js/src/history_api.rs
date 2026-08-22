//! History API — W3C HTML Living Standard § 7.7
//!
//! Implements the complete browser navigation history:
//!   - history.pushState(state, title, url)
//!   - history.replaceState(state, title, url)
//!   - history.go(delta) / history.back() / history.forward()
//!   - history.length / history.scrollRestoration
//!   - popstate event dispatch on navigation
//!   - hashchange event on fragment navigation
//!   - URL parsing and relative URL resolution
//!   - Session history entries with scroll position restoration
//!   - AI-facing: navigation audit trail + page state diff

use std::collections::VecDeque;

/// A state object stored in a history entry
#[derive(Debug, Clone, PartialEq)]
pub enum HistoryState {
    Null,
    String(String),
    Number(f64),
    Boolean(bool),
    Object(Vec<(String, HistoryState)>),
    Array(Vec<HistoryState>),
}

impl HistoryState {
    pub fn as_json(&self) -> String {
        match self {
            Self::Null => "null".to_string(),
            Self::String(s) => format!("\"{}\"", s.replace('"', "\\\"")),
            Self::Number(n) => n.to_string(),
            Self::Boolean(b) => b.to_string(),
            Self::Object(fields) => {
                let inner: Vec<String> = fields.iter()
                    .map(|(k, v)| format!("\"{}\":{}", k, v.as_json()))
                    .collect();
                format!("{{{}}}", inner.join(","))
            }
            Self::Array(items) => {
                let inner: Vec<String> = items.iter().map(|v| v.as_json()).collect();
                format!("[{}]", inner.join(","))
            }
        }
    }
}

/// Scroll restoration policy per History API
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ScrollRestoration {
    Auto,
    Manual,
}

/// A single session history entry
#[derive(Debug, Clone)]
pub struct HistoryEntry {
    /// The serialized URL for this entry
    pub url: String,
    /// The title string (deprecated but still part of the API)
    pub title: String,
    /// The state object passed to pushState/replaceState
    pub state: HistoryState,
    /// Saved scroll position (for scroll restoration)
    pub scroll_x: f64,
    pub scroll_y: f64,
    /// Timestamp when this entry was created
    pub timestamp: u64,
    /// Navigation type (pushState, replaceState, standard navigation)
    pub nav_type: NavigationType,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum NavigationType {
    Navigate,
    PushState,
    ReplaceState,
    HashChange,
    Reload,
    Traverse,
}

/// Events dispatched during history navigation
#[derive(Debug, Clone)]
pub enum HistoryEvent {
    PopState {
        state: HistoryState,
        url: String,
    },
    HashChange {
        old_url: String,
        new_url: String,
    },
    NavigateAwayBlocked,
    NavigationCommit {
        url: String,
        nav_type: NavigationType,
    },
}

/// The browser session history manager
pub struct HistoryManager {
    /// All session history entries
    entries: Vec<HistoryEntry>,
    /// Current index into entries
    current_index: usize,
    /// Scroll restoration policy
    pub scroll_restoration: ScrollRestoration,
    /// Base URL for relative URL resolution
    pub base_url: String,
    /// Events queued for dispatch
    pending_events: VecDeque<HistoryEvent>,
    /// Maximum entries (browsers typically cap at 50+)
    max_entries: usize,
}

impl HistoryManager {
    pub fn new(initial_url: &str) -> Self {
        let initial_entry = HistoryEntry {
            url: initial_url.to_string(),
            title: String::new(),
            state: HistoryState::Null,
            scroll_x: 0.0,
            scroll_y: 0.0,
            timestamp: Self::now_ms(),
            nav_type: NavigationType::Navigate,
        };
        
        Self {
            entries: vec![initial_entry],
            current_index: 0,
            scroll_restoration: ScrollRestoration::Auto,
            base_url: initial_url.to_string(),
            pending_events: VecDeque::new(),
            max_entries: 100,
        }
    }
    
    // ──────────────────────────────
    // Core History API
    // ──────────────────────────────
    
    /// history.pushState(state, title, url)
    pub fn push_state(&mut self, state: HistoryState, title: &str, url: &str) {
        let resolved_url = self.resolve_url(url);
        
        // Truncate forward entries (any entries after current_index)
        self.entries.truncate(self.current_index + 1);
        
        // Enforce max entries
        if self.entries.len() >= self.max_entries {
            self.entries.remove(0);
            if self.current_index > 0 { self.current_index -= 1; }
        }
        
        self.entries.push(HistoryEntry {
            url: resolved_url.clone(),
            title: title.to_string(),
            state,
            scroll_x: 0.0,
            scroll_y: 0.0,
            timestamp: Self::now_ms(),
            nav_type: NavigationType::PushState,
        });
        
        self.current_index = self.entries.len() - 1;
        
        self.pending_events.push_back(HistoryEvent::NavigationCommit {
            url: resolved_url,
            nav_type: NavigationType::PushState,
        });
    }
    
    /// history.replaceState(state, title, url)
    pub fn replace_state(&mut self, state: HistoryState, title: &str, url: &str) {
        let resolved_url = self.resolve_url(url);
        
        if let Some(entry) = self.entries.get_mut(self.current_index) {
            entry.state = state;
            entry.title = title.to_string();
            entry.url = resolved_url.clone();
            entry.nav_type = NavigationType::ReplaceState;
            entry.timestamp = Self::now_ms();
        }
        
        self.pending_events.push_back(HistoryEvent::NavigationCommit {
            url: resolved_url,
            nav_type: NavigationType::ReplaceState,
        });
    }
    
    /// history.go(delta) — returns the URL we navigated to, or None if out of range
    pub fn go(&mut self, delta: i32) -> Option<String> {
        let new_index = self.current_index as i64 + delta as i64;
        
        if new_index < 0 || new_index >= self.entries.len() as i64 {
            return None; // Out of range — no-op
        }
        
        let old_url = self.current_url().to_string();
        self.current_index = new_index as usize;
        let new_url = self.current_url().to_string();
        let new_state = self.current_state().clone();
        
        // Check if it's a hash change within the same page
        if Self::same_document_but_different_hash(&old_url, &new_url) {
            self.pending_events.push_back(HistoryEvent::HashChange {
                old_url: old_url.clone(),
                new_url: new_url.clone(),
            });
        }
        
        self.pending_events.push_back(HistoryEvent::PopState {
            state: new_state,
            url: new_url.clone(),
        });
        
        Some(new_url)
    }
    
    pub fn back(&mut self) -> Option<String> { self.go(-1) }
    pub fn forward(&mut self) -> Option<String> { self.go(1) }
    
    // ──────────────────────────────
    // Accessors
    // ──────────────────────────────
    
    pub fn length(&self) -> usize { self.entries.len() }
    
    pub fn current_url(&self) -> &str {
        self.entries.get(self.current_index)
            .map(|e| e.url.as_str())
            .unwrap_or("")
    }
    
    pub fn current_state(&self) -> &HistoryState {
        self.entries.get(self.current_index)
            .map(|e| &e.state)
            .unwrap_or(&HistoryState::Null)
    }
    
    pub fn current_entry(&self) -> Option<&HistoryEntry> {
        self.entries.get(self.current_index)
    }
    
    pub fn can_go_back(&self) -> bool { self.current_index > 0 }
    pub fn can_go_forward(&self) -> bool { self.current_index + 1 < self.entries.len() }
    
    // ──────────────────────────────
    // Scroll position management
    // ──────────────────────────────
    
    /// Save current scroll position before navigating away
    pub fn save_scroll(&mut self, scroll_x: f64, scroll_y: f64) {
        if let Some(entry) = self.entries.get_mut(self.current_index) {
            entry.scroll_x = scroll_x;
            entry.scroll_y = scroll_y;
        }
    }
    
    /// Get the scroll position to restore for the current entry
    pub fn restore_scroll(&self) -> (f64, f64) {
        match self.scroll_restoration {
            ScrollRestoration::Manual => (0.0, 0.0),
            ScrollRestoration::Auto => {
                self.entries.get(self.current_index)
                    .map(|e| (e.scroll_x, e.scroll_y))
                    .unwrap_or((0.0, 0.0))
            }
        }
    }
    
    // ──────────────────────────────
    // Internal navigation
    // ──────────────────────────────
    
    /// Navigate to a new page (full navigation, not pushState)
    pub fn navigate(&mut self, url: &str) {
        let resolved = self.resolve_url(url);
        let old_url = self.current_url().to_string();
        
        // Hash change detection
        if Self::same_document_but_different_hash(&old_url, &resolved) {
            self.push_state(HistoryState::Null, "", url);
            self.pending_events.push_back(HistoryEvent::HashChange {
                old_url, new_url: resolved,
            });
            return;
        }
        
        // Full navigation
        self.entries.truncate(self.current_index + 1);
        self.entries.push(HistoryEntry {
            url: resolved.clone(),
            title: String::new(),
            state: HistoryState::Null,
            scroll_x: 0.0, scroll_y: 0.0,
            timestamp: Self::now_ms(),
            nav_type: NavigationType::Navigate,
        });
        self.current_index = self.entries.len() - 1;
        self.base_url = resolved.clone();
        
        self.pending_events.push_back(HistoryEvent::NavigationCommit {
            url: resolved,
            nav_type: NavigationType::Navigate,
        });
    }
    
    /// Reload the current page
    pub fn reload(&mut self) {
        let url = self.current_url().to_string();
        self.pending_events.push_back(HistoryEvent::NavigationCommit {
            url,
            nav_type: NavigationType::Reload,
        });
    }
    
    // ──────────────────────────────
    // Event dispatch
    // ──────────────────────────────
    
    pub fn take_events(&mut self) -> Vec<HistoryEvent> {
        self.pending_events.drain(..).collect()
    }
    
    pub fn has_pending_events(&self) -> bool { !self.pending_events.is_empty() }
    
    // ──────────────────────────────
    // URL utilities
    // ──────────────────────────────
    
    /// Resolve a potentially relative URL against the base URL
    pub fn resolve_url(&self, url: &str) -> String {
        if url.starts_with("http://") || url.starts_with("https://") {
            return url.to_string();
        }
        
        if url.starts_with('/') {
            // Absolute path — prepend origin
            if let Some(origin) = Self::extract_origin(&self.base_url) {
                return format!("{}{}", origin, url);
            }
            return url.to_string();
        }
        
        if url.starts_with('#') {
            // Fragment only — append to current URL without fragment
            let base_without_fragment = self.base_url.split('#').next().unwrap_or(&self.base_url);
            return format!("{}{}", base_without_fragment, url);
        }
        
        // Relative path
        let base_dir = self.base_url.rsplit('/').skip(1)
            .collect::<Vec<_>>().iter().rev()
            .cloned().collect::<Vec<_>>().join("/");
        
        if base_dir.is_empty() {
            url.to_string()
        } else {
            format!("{}/{}", base_dir, url)
        }
    }
    
    fn extract_origin(url: &str) -> Option<&str> {
        let scheme_end = url.find("://")?;
        let after_scheme = &url[scheme_end + 3..];
        let path_start = after_scheme.find('/').unwrap_or(after_scheme.len());
        Some(&url[..scheme_end + 3 + path_start])
    }
    
    fn same_document_but_different_hash(old: &str, new: &str) -> bool {
        let old_base = old.split('#').next().unwrap_or(old);
        let new_base = new.split('#').next().unwrap_or(new);
        old_base == new_base && old != new
    }
    
    fn now_ms() -> u64 {
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_millis() as u64)
            .unwrap_or(0)
    }
    
    // ──────────────────────────────
    // AI-facing
    // ──────────────────────────────
    
    /// Generate an AI-readable navigation audit trail
    pub fn ai_navigation_trail(&self) -> String {
        let mut lines = vec![
            format!("🗂️ Navigation History ({} entries, current: #{})",
                self.entries.len(), self.current_index)
        ];
        
        for (i, entry) in self.entries.iter().enumerate() {
            let marker = if i == self.current_index { "→ " } else { "  " };
            let nav_type = match entry.nav_type {
                NavigationType::PushState => "push",
                NavigationType::ReplaceState => "replace",
                NavigationType::HashChange => "hash",
                NavigationType::Navigate => "nav",
                NavigationType::Reload => "reload",
                NavigationType::Traverse => "traverse",
            };
            lines.push(format!("{}[{}] {} ({})", marker, i, entry.url, nav_type));
        }
        
        lines.join("\n")
    }
}
