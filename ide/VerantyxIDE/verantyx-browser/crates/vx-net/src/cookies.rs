//! Cookie Manager — Persistent cookie storage with domain isolation
//!
//! Features:
//! - Cookies stored per-domain
//! - HttpOnly, Secure, SameSite support
//! - Expiry tracking
//! - Private mode (ephemeral cookies)
//! - File-based persistence (~/.verantyx/cookies.json)

use std::collections::HashMap;
use std::time::{SystemTime, UNIX_EPOCH};
use serde::{Deserialize, Serialize};

/// A single HTTP cookie
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Cookie {
    pub name: String,
    pub value: String,
    pub domain: String,
    pub path: String,
    pub expires: Option<u64>,   // Unix timestamp
    pub http_only: bool,
    pub secure: bool,
    pub same_site: SameSite,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum SameSite {
    Strict,
    Lax,
    None,
}

impl Default for SameSite {
    fn default() -> Self {
        SameSite::Lax
    }
}

impl Cookie {
    /// Check if cookie is expired
    pub fn is_expired(&self) -> bool {
        if let Some(expires) = self.expires {
            let now = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_secs();
            expires < now
        } else {
            false // Session cookie — never expires (until browser close)
        }
    }

    /// Check if cookie matches a URL
    pub fn matches_url(&self, url_domain: &str, url_path: &str, is_secure: bool) -> bool {
        // Domain match
        if !url_domain.ends_with(&self.domain) && url_domain != self.domain.trim_start_matches('.') {
            return false;
        }
        // Path match
        if !url_path.starts_with(&self.path) {
            return false;
        }
        // Secure check
        if self.secure && !is_secure {
            return false;
        }
        // Not expired
        !self.is_expired()
    }

    /// Format as Cookie header value
    pub fn to_header_value(&self) -> String {
        format!("{}={}", self.name, self.value)
    }

    /// Format as Set-Cookie header
    pub fn to_set_cookie_header(&self) -> String {
        let mut parts = vec![format!("{}={}", self.name, self.value)];
        if !self.domain.is_empty() {
            parts.push(format!("Domain={}", self.domain));
        }
        if self.path != "/" {
            parts.push(format!("Path={}", self.path));
        }
        if self.http_only {
            parts.push("HttpOnly".to_string());
        }
        if self.secure {
            parts.push("Secure".to_string());
        }
        match self.same_site {
            SameSite::Strict => parts.push("SameSite=Strict".to_string()),
            SameSite::None => parts.push("SameSite=None".to_string()),
            SameSite::Lax => {} // default, don't need to specify
        }
        if let Some(exp) = self.expires {
            parts.push(format!("Max-Age={}", exp.saturating_sub(
                SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs()
            )));
        }
        parts.join("; ")
    }
}

/// Parse a Set-Cookie header into a Cookie
pub fn parse_set_cookie(header: &str, request_domain: &str) -> Option<Cookie> {
    let parts: Vec<&str> = header.split(';').collect();
    if parts.is_empty() { return None; }

    // First part is name=value
    let name_value: Vec<&str> = parts[0].splitn(2, '=').collect();
    if name_value.len() != 2 { return None; }

    let mut cookie = Cookie {
        name: name_value[0].trim().to_string(),
        value: name_value[1].trim().to_string(),
        domain: request_domain.to_string(),
        path: "/".to_string(),
        expires: None,
        http_only: false,
        secure: false,
        same_site: SameSite::Lax,
    };

    // Parse attributes
    for part in &parts[1..] {
        let part = part.trim();
        let lower = part.to_lowercase();

        if lower == "httponly" {
            cookie.http_only = true;
        } else if lower == "secure" {
            cookie.secure = true;
        } else if lower.starts_with("domain=") {
            cookie.domain = lower[7..].to_string();
        } else if lower.starts_with("path=") {
            cookie.path = part[5..].to_string();
        } else if lower.starts_with("max-age=") {
            if let Ok(max_age) = lower[8..].parse::<u64>() {
                let now = SystemTime::now()
                    .duration_since(UNIX_EPOCH)
                    .unwrap_or_default()
                    .as_secs();
                cookie.expires = Some(now + max_age);
            }
        } else if lower.starts_with("samesite=") {
            cookie.same_site = match &lower[9..] {
                "strict" => SameSite::Strict,
                "none" => SameSite::None,
                _ => SameSite::Lax,
            };
        }
    }

    Some(cookie)
}

/// Cookie jar — stores cookies per domain
#[derive(Debug, Default, Serialize, Deserialize)]
pub struct CookieJar {
    cookies: HashMap<String, Vec<Cookie>>,  // domain → cookies
}

impl CookieJar {
    pub fn new() -> Self {
        Self::default()
    }

    /// Add or update a cookie
    pub fn set(&mut self, cookie: Cookie) {
        let domain = cookie.domain.clone();
        let entry = self.cookies.entry(domain).or_default();

        // Remove existing cookie with same name + path
        entry.retain(|c| !(c.name == cookie.name && c.path == cookie.path));
        entry.push(cookie);
    }

    /// Get all cookies that match a URL
    pub fn get_for_url(&self, domain: &str, path: &str, is_secure: bool) -> Vec<&Cookie> {
        let mut result = Vec::new();

        for (cookie_domain, cookies) in &self.cookies {
            for cookie in cookies {
                if cookie.matches_url(domain, path, is_secure) {
                    result.push(cookie);
                }
            }
        }

        result
    }

    /// Format cookies as a Cookie header value
    pub fn cookie_header(&self, domain: &str, path: &str, is_secure: bool) -> Option<String> {
        let cookies = self.get_for_url(domain, path, is_secure);
        if cookies.is_empty() { return None; }

        Some(cookies.iter()
            .map(|c| c.to_header_value())
            .collect::<Vec<_>>()
            .join("; "))
    }

    /// Process Set-Cookie headers from a response
    pub fn process_response_headers(&mut self, headers: &[(String, String)], request_domain: &str) {
        for (name, value) in headers {
            if name.to_lowercase() == "set-cookie" {
                if let Some(cookie) = parse_set_cookie(value, request_domain) {
                    self.set(cookie);
                }
            }
        }
    }

    /// Remove expired cookies
    pub fn clean_expired(&mut self) {
        for cookies in self.cookies.values_mut() {
            cookies.retain(|c| !c.is_expired());
        }
        self.cookies.retain(|_, v| !v.is_empty());
    }

    /// Remove all cookies for a domain
    pub fn clear_domain(&mut self, domain: &str) {
        self.cookies.remove(domain);
    }

    /// Remove all cookies
    pub fn clear_all(&mut self) {
        self.cookies.clear();
    }

    /// Get total cookie count
    pub fn len(&self) -> usize {
        self.cookies.values().map(|v| v.len()).sum()
    }

    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    /// Save cookies to file
    pub fn save_to_file(&self, path: &str) -> std::io::Result<()> {
        let json = serde_json::to_string_pretty(self)
            .map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e))?;
        std::fs::write(path, json)
    }

    /// Load cookies from file
    pub fn load_from_file(path: &str) -> std::io::Result<Self> {
        let data = std::fs::read_to_string(path)?;
        serde_json::from_str(&data)
            .map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e))
    }
}

/// CORS (Cross-Origin Resource Sharing) checker
pub struct CorsChecker;

impl CorsChecker {
    /// Check if a request from `origin` to `target_url` is same-origin
    pub fn is_same_origin(origin: &str, target_url: &str) -> bool {
        let origin_parsed = url::Url::parse(origin);
        let target_parsed = url::Url::parse(target_url);

        match (origin_parsed, target_parsed) {
            (Ok(o), Ok(t)) => {
                o.scheme() == t.scheme() &&
                o.host_str() == t.host_str() &&
                o.port() == t.port()
            }
            _ => false,
        }
    }

    /// Check CORS response headers
    pub fn check_cors_headers(
        origin: &str,
        response_headers: &HashMap<String, String>,
    ) -> CorsResult {
        let allowed_origin = response_headers.get("access-control-allow-origin");

        match allowed_origin {
            Some(ao) if ao == "*" => CorsResult::Allowed,
            Some(ao) if ao == origin => CorsResult::Allowed,
            Some(_) => CorsResult::Denied("Origin not in Access-Control-Allow-Origin".into()),
            None => CorsResult::Denied("No Access-Control-Allow-Origin header".into()),
        }
    }
}

#[derive(Debug, PartialEq)]
pub enum CorsResult {
    Allowed,
    Denied(String),
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cookie_creation() {
        let cookie = Cookie {
            name: "session".into(),
            value: "abc123".into(),
            domain: ".example.com".into(),
            path: "/".into(),
            expires: None,
            http_only: true,
            secure: true,
            same_site: SameSite::Strict,
        };
        assert!(!cookie.is_expired());
        assert_eq!(cookie.to_header_value(), "session=abc123");
    }

    #[test]
    fn test_cookie_matching() {
        let cookie = Cookie {
            name: "test".into(),
            value: "val".into(),
            domain: ".example.com".into(),
            path: "/".into(),
            expires: None,
            http_only: false,
            secure: false,
            same_site: SameSite::Lax,
        };

        assert!(cookie.matches_url("www.example.com", "/page", false));
        assert!(cookie.matches_url("example.com", "/", false));
        assert!(!cookie.matches_url("other.com", "/", false));
    }

    #[test]
    fn test_parse_set_cookie() {
        let header = "session=abc123; Domain=.example.com; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=3600";
        let cookie = parse_set_cookie(header, "example.com").unwrap();
        assert_eq!(cookie.name, "session");
        assert_eq!(cookie.value, "abc123");
        assert!(cookie.http_only);
        assert!(cookie.secure);
        assert_eq!(cookie.same_site, SameSite::Strict);
        assert!(cookie.expires.is_some());
    }

    #[test]
    fn test_cookie_jar() {
        let mut jar = CookieJar::new();

        let c1 = Cookie {
            name: "a".into(), value: "1".into(),
            domain: ".example.com".into(), path: "/".into(),
            expires: None, http_only: false, secure: false, same_site: SameSite::Lax,
        };
        jar.set(c1);

        let c2 = Cookie {
            name: "b".into(), value: "2".into(),
            domain: ".other.com".into(), path: "/".into(),
            expires: None, http_only: false, secure: false, same_site: SameSite::Lax,
        };
        jar.set(c2);

        assert_eq!(jar.len(), 2);

        let cookies = jar.get_for_url("www.example.com", "/page", false);
        assert_eq!(cookies.len(), 1);
        assert_eq!(cookies[0].name, "a");

        let header = jar.cookie_header("www.example.com", "/", false);
        assert_eq!(header, Some("a=1".to_string()));
    }

    #[test]
    fn test_cookie_update() {
        let mut jar = CookieJar::new();

        let c1 = Cookie {
            name: "token".into(), value: "old".into(),
            domain: "example.com".into(), path: "/".into(),
            expires: None, http_only: false, secure: false, same_site: SameSite::Lax,
        };
        jar.set(c1);

        let c2 = Cookie {
            name: "token".into(), value: "new".into(),
            domain: "example.com".into(), path: "/".into(),
            expires: None, http_only: false, secure: false, same_site: SameSite::Lax,
        };
        jar.set(c2);

        assert_eq!(jar.len(), 1);
        let cookies = jar.get_for_url("example.com", "/", false);
        assert_eq!(cookies[0].value, "new");
    }

    #[test]
    fn test_cors_same_origin() {
        assert!(CorsChecker::is_same_origin("https://example.com", "https://example.com/api"));
        assert!(!CorsChecker::is_same_origin("https://example.com", "https://other.com/api"));
        assert!(!CorsChecker::is_same_origin("http://example.com", "https://example.com"));
    }

    #[test]
    fn test_cors_headers() {
        let mut headers = HashMap::new();
        headers.insert("access-control-allow-origin".into(), "*".into());
        assert_eq!(CorsChecker::check_cors_headers("https://example.com", &headers), CorsResult::Allowed);

        let mut headers2 = HashMap::new();
        headers2.insert("access-control-allow-origin".into(), "https://other.com".into());
        assert_eq!(
            CorsChecker::check_cors_headers("https://example.com", &headers2),
            CorsResult::Denied("Origin not in Access-Control-Allow-Origin".into())
        );
    }
}
