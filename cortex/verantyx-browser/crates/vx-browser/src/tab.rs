//! Tab Manager — Multiple concurrent pages with isolation
//!
//! Features:
//! - Multiple tabs with independent navigation history
//! - Private tabs with isolated cookies (no cross-tab leakage)
//! - Tab switching by ID
//! - Auto-cleanup of closed tabs

use anyhow::Result;
use vx_dom::Document;
use vx_net::HttpClient;
use vx_render::ai_renderer::{AiRenderer, AiRenderedPage};
use vx_input::FormState;
use std::collections::HashMap;

/// A single browser tab
pub struct Tab {
    pub id: usize,
    pub url: String,
    pub title: String,
    pub page: Option<AiRenderedPage>,
    pub form_state: FormState,
    pub history: Vec<String>,
    pub is_private: bool,
    client: HttpClient,
    raw_html: String,
}

impl Tab {
    /// Create a normal tab (shares default cookie jar)
    pub fn new(id: usize, client: HttpClient) -> Self {
        Self {
            id,
            url: String::new(),
            title: String::new(),
            page: None,
            form_state: FormState::new(),
            history: Vec::new(),
            is_private: false,
            client,
            raw_html: String::new(),
        }
    }

    /// Create a private tab (isolated cookie jar)
    pub fn new_private(id: usize) -> Result<Self> {
        let client = HttpClient::new()?;
        Ok(Self {
            id,
            url: String::new(),
            title: String::new(),
            page: None,
            form_state: FormState::new(),
            history: Vec::new(),
            is_private: true,
            client,
            raw_html: String::new(),
        })
    }

    /// Navigate to URL
    pub async fn navigate(&mut self, url: &str) -> Result<&AiRenderedPage> {
        let resp = self.client.get(url).await?;
        self.url = resp.url.to_string();
        self.history.push(self.url.clone());
        self.form_state.clear();
        self.raw_html = resp.body.clone();

        let doc = Document::parse(&resp.body);
        self.title = doc.title.clone();

        // Execute inline scripts
        if let Ok(js_rt) = vx_js::JsRuntime::new() {
            js_rt.set_location(&self.url).ok();
            let scripts = extract_inline_scripts(&resp.body);
            for script in &scripts {
                js_rt.exec(script).ok();
            }
            js_rt.execute_pending().ok();
        }

        let mut ai = AiRenderer::new();
        let page = ai.render(&doc.body, &doc.title, &self.url);
        self.page = Some(page);

        Ok(self.page.as_ref().unwrap())
    }

    /// Go back in history
    pub async fn back(&mut self) -> Result<bool> {
        if self.history.len() < 2 {
            return Ok(false);
        }
        self.history.pop(); // Remove current
        if let Some(prev_url) = self.history.last().cloned() {
            self.navigate(&prev_url).await?;
            Ok(true)
        } else {
            Ok(false)
        }
    }

    /// Reload current page
    pub async fn reload(&mut self) -> Result<()> {
        let url = self.url.clone();
        if !url.is_empty() {
            self.navigate(&url).await?;
        }
        Ok(())
    }

    /// Get current page summary for tab bar display
    pub fn summary(&self) -> String {
        let private_mark = if self.is_private { "🔒" } else { "" };
        let title = if self.title.len() > 20 {
            format!("{}...", &self.title[..17])
        } else if self.title.is_empty() {
            "(empty)".to_string()
        } else {
            self.title.clone()
        };
        format!("[{}]{} {}", self.id, private_mark, title)
    }
}

/// Tab Manager — manages multiple tabs
pub struct TabManager {
    tabs: HashMap<usize, Tab>,
    active_tab: usize,
    next_id: usize,
    shared_client: HttpClient,
}

impl TabManager {
    pub fn new() -> Result<Self> {
        let client = HttpClient::new()?;
        let mut manager = Self {
            tabs: HashMap::new(),
            active_tab: 1,
            next_id: 1,
            shared_client: client,
        };

        // Create initial tab
        manager.new_tab()?;
        Ok(manager)
    }

    /// Create a new normal tab
    pub fn new_tab(&mut self) -> Result<usize> {
        let id = self.next_id;
        self.next_id += 1;
        let client = HttpClient::new()?;
        let tab = Tab::new(id, client);
        self.tabs.insert(id, tab);
        self.active_tab = id;
        Ok(id)
    }

    /// Create a new private tab (isolated cookies)
    pub fn new_private_tab(&mut self) -> Result<usize> {
        let id = self.next_id;
        self.next_id += 1;
        let tab = Tab::new_private(id)?;
        self.tabs.insert(id, tab);
        self.active_tab = id;
        Ok(id)
    }

    /// Switch to a tab by ID
    pub fn switch_to(&mut self, id: usize) -> bool {
        if self.tabs.contains_key(&id) {
            self.active_tab = id;
            true
        } else {
            false
        }
    }

    /// Close a tab by ID
    pub fn close_tab(&mut self, id: usize) -> bool {
        if self.tabs.len() <= 1 {
            return false; // Can't close last tab
        }
        if self.tabs.remove(&id).is_some() {
            if self.active_tab == id {
                // Switch to first available tab
                self.active_tab = *self.tabs.keys().next().unwrap();
            }
            true
        } else {
            false
        }
    }

    /// Get the active tab
    pub fn active(&self) -> Option<&Tab> {
        self.tabs.get(&self.active_tab)
    }

    /// Get the active tab mutably
    pub fn active_mut(&mut self) -> Option<&mut Tab> {
        self.tabs.get_mut(&self.active_tab)
    }

    /// Get a specific tab
    pub fn get(&self, id: usize) -> Option<&Tab> {
        self.tabs.get(&id)
    }

    /// Get a specific tab mutably
    pub fn get_mut(&mut self, id: usize) -> Option<&mut Tab> {
        self.tabs.get_mut(&id)
    }

    /// Get active tab ID
    pub fn active_id(&self) -> usize {
        self.active_tab
    }

    /// List all tabs
    pub fn list(&self) -> Vec<(usize, String, bool)> {
        let mut tabs: Vec<_> = self.tabs.iter()
            .map(|(id, tab)| (*id, tab.summary(), *id == self.active_tab))
            .collect();
        tabs.sort_by_key(|(id, _, _)| *id);
        tabs
    }

    /// Get tab count
    pub fn count(&self) -> usize {
        self.tabs.len()
    }
}

/// Extract inline scripts (reused from main.rs logic)
fn extract_inline_scripts(html: &str) -> Vec<String> {
    let mut scripts = Vec::new();
    let mut pos = 0;

    while let Some(start) = html[pos..].find("<script") {
        let abs_start = pos + start;
        let tag_end = html[abs_start..].find('>').map(|i| abs_start + i);
        if let Some(te) = tag_end {
            let tag = &html[abs_start..te + 1];
            if tag.contains("src=") || (tag.contains("type=") && !tag.contains("text/javascript") && !tag.contains("module")) {
                if let Some(end) = html[te..].find("</script>") {
                    pos = te + end + 9;
                    continue;
                }
            }
            let content_start = te + 1;
            if let Some(end) = html[content_start..].find("</script>") {
                let script = html[content_start..content_start + end].trim().to_string();
                if !script.is_empty() {
                    scripts.push(script);
                }
                pos = content_start + end + 9;
            } else { break; }
        } else { break; }
    }
    scripts
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_tab_summary() {
        let client = HttpClient::new().unwrap();
        let mut tab = Tab::new(1, client);
        tab.title = "Example Domain".to_string();
        assert_eq!(tab.summary(), "[1] Example Domain");
    }

    #[test]
    fn test_private_tab_summary() {
        let mut tab = Tab::new_private(2).unwrap();
        tab.title = "Private Page".to_string();
        assert_eq!(tab.summary(), "[2]🔒 Private Page");
    }

    #[test]
    fn test_tab_manager_create_close() {
        let mut mgr = TabManager::new().unwrap();
        assert_eq!(mgr.count(), 1);

        let id2 = mgr.new_tab().unwrap();
        assert_eq!(mgr.count(), 2);
        assert_eq!(mgr.active_id(), id2);

        mgr.switch_to(1);
        assert_eq!(mgr.active_id(), 1);

        mgr.close_tab(id2);
        assert_eq!(mgr.count(), 1);
    }

    #[test]
    fn test_cannot_close_last_tab() {
        let mut mgr = TabManager::new().unwrap();
        assert!(!mgr.close_tab(1)); // Can't close the only tab
    }

    #[test]
    fn test_private_tab_creation() {
        let mut mgr = TabManager::new().unwrap();
        let private_id = mgr.new_private_tab().unwrap();
        assert!(mgr.get(private_id).unwrap().is_private);
    }
}
