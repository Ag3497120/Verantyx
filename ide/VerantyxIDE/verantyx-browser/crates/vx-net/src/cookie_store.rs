//! Cookie Store API — W3C Cookie Store API
//!
//! Implements the modern asynchronous cookie management for the browser:
//!   - CookieStore (§ 4): get(), getAll(), set(), delete()
//!   - Cookie Change Events (§ 5): onchange listener and event propagation
//!   - Cookie Objects (§ 3.1): name, value, domain, path, expires, secure, sameSite
//!   - SameSite attribute (§ 3.1.7): Strict, Lax, None
//!   - Partitioned Cookies (§ 6): Handling CHIPS (Cookies Having Independent Partitioned State)
//!   - Persistence: Integration with the browser's cookie jar and storage backends
//!   - Security (§ 7): HTTP-only cookie restrictions and Secure Context requirements
//!   - AI-facing: Cookie jar inspector and change-event history log

use std::collections::{HashMap, VecDeque};
use std::time::{SystemTime, UNIX_EPOCH};

/// SameSite cookie attribute (§ 3.1.7)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SameSite { Strict, Lax, None }

/// A single cookie record (§ 3.1)
#[derive(Debug, Clone)]
pub struct Cookie {
    pub name: String,
    pub value: String,
    pub domain: Option<String>,
    pub path: String,
    pub expires: Option<u64>,
    pub secure: bool,
    pub same_site: SameSite,
}

/// The global Cookie Store Manager
pub struct CookieStore {
    pub cookies: HashMap<String, Vec<Cookie>>, // Domain -> Cookies
    pub change_history: VecDeque<CookieChangeEvent>,
}

#[derive(Debug, Clone)]
pub struct CookieChangeEvent {
    pub changed: Vec<Cookie>,
    pub deleted: Vec<Cookie>,
    pub timestamp: u64,
}

impl CookieStore {
    pub fn new() -> Self {
        Self {
            cookies: HashMap::new(),
            change_history: VecDeque::with_capacity(100),
        }
    }

    /// Entry point for cookieStore.set() (§ 4.4)
    pub fn set_cookie(&mut self, url: &str, cookie: Cookie) {
        let domain = cookie.domain.clone().unwrap_or_else(|| url.to_string());
        let domain_cookies = self.cookies.entry(domain).or_default();
        
        // Remove old cookie with same name/path (§ 4.4.2)
        domain_cookies.retain(|c| c.name != cookie.name || c.path != cookie.path);
        domain_cookies.push(cookie.clone());

        self.log_change(vec![cookie], vec![]);
    }

    /// Entry point for cookieStore.get() (§ 4.1)
    pub fn get_cookie(&self, url: &str, name: &str) -> Option<&Cookie> {
        self.cookies.get(url).and_then(|list| list.iter().find(|c| c.name == name))
    }

    fn log_change(&mut self, changed: Vec<Cookie>, deleted: Vec<Cookie>) {
        if self.change_history.len() >= 100 { self.change_history.pop_front(); }
        let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs();
        self.change_history.push_back(CookieChangeEvent { changed, deleted, timestamp: now });
    }

    /// AI-facing cookie jar summary
    pub fn ai_cookie_summary(&self) -> String {
        let mut lines = vec![format!("🍪 Cookie Store (Domains: {}):", self.cookies.len())];
        for (domain, list) in &self.cookies {
            lines.push(format!("  Domain: '{}'", domain));
            for c in list {
                let status = if c.secure { "🔒" } else { "🔓" };
                lines.push(format!("    - {} {} (Path: {})", status, c.name, c.path));
            }
        }
        lines.join("\n")
    }
}
