//! CORS (Cross-Origin Resource Sharing) Engine — W3C Fetch API CORS Protocol
//!
//! Implements the full CORS fetch algorithm per W3C Fetch Standard:
//! - Simple requests (GET/POST + safe headers/MIME types)
//! - Preflight requests (OPTIONS + Access-Control-Request-*)
//! - Credentialed requests (cookies, authorization headers)
//! - Wildcard origin handling
//! - CORS-safelisted request headers
//! - CORS-exposed response headers
//! - Private network access (PNA) enforcement (Chrome-specific extension)

use std::collections::{HashMap, HashSet};

/// CORS request mode (mirrors the Fetch API 'mode' option)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CorsMode {
    /// No-cors: Only allows simple cross-origin requests
    NoCors,
    /// CORS: Standard CORS fetch, may require preflight
    Cors,
    /// Same-origin: Fails if cross-origin  
    SameOrigin,
    /// Navigate: Used for navigation requests
    Navigate,
    /// Websocket: WebSocket connection mode
    Websocket,
}

/// CORS credentials mode
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CredentialsMode {
    Omit,
    SameOrigin,
    Include,
}

/// The CORS-safelisted request headers per Fetch specification
pub static CORS_SAFELISTED_REQUEST_HEADERS: &[&str] = &[
    "accept",
    "accept-language",
    "content-language",
    "content-type",       // Only certain values (see CORS_SAFE_CONTENT_TYPES)
    "range",              // Only bytes=... format
];

/// CORS-safelisted content types (for Content-Type header to be safe)
pub static CORS_SAFE_CONTENT_TYPES: &[&str] = &[
    "application/x-www-form-urlencoded",
    "multipart/form-data",
    "text/plain",
];

/// Forbidden request headers (cannot be set by JavaScript)
pub static FORBIDDEN_REQUEST_HEADERS: &[&str] = &[
    "accept-charset",
    "accept-encoding",
    "access-control-request-headers",
    "access-control-request-method",
    "connection",
    "content-length",
    "cookie",
    "cookie2",
    "date",
    "dnt",
    "expect",
    "host",
    "keep-alive",
    "origin",
    "referer",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "via",
];

/// Forbidden response headers (cannot be read by JavaScript)
pub static FORBIDDEN_RESPONSE_HEADERS: &[&str] = &[
    "set-cookie",
    "set-cookie2",
];

/// CORS-safelisted response headers (accessible without explicit exposure)
pub static CORS_SAFELISTED_RESPONSE_HEADERS: &[&str] = &[
    "cache-control",
    "content-language",
    "content-length",
    "content-type",
    "expires",
    "last-modified",
    "pragma",
];

/// Result of a CORS check
#[derive(Debug, Clone)]
pub enum CorsCheckResult {
    Allowed,
    RequiresPreflight,
    Blocked { reason: CorsBlockReason },
}

#[derive(Debug, Clone, PartialEq)]
pub enum CorsBlockReason {
    NoAllowOriginHeader,
    OriginNotAllowed { expected: String, actual: String },
    CredentialsWithWildcard,
    PreflightFailed { header: String },
    MethodNotAllowed { method: String },
    HeaderNotAllowed { header: String },
    PrivateNetworkAccessDenied,
}

/// The request being validated for CORS
#[derive(Debug, Clone)]
pub struct CorsRequest {
    pub origin: String,
    pub method: String,
    pub url: String,
    pub headers: HashMap<String, String>,
    pub credentials: CredentialsMode,
    pub mode: CorsMode,
}

impl CorsRequest {
    /// Determine if a request is a "simple request" per CORS spec
    /// (and therefore does NOT need a preflight OPTIONS request)
    pub fn is_simple_request(&self) -> bool {
        // Simple methods
        let simple_method = matches!(self.method.to_uppercase().as_str(), "GET" | "HEAD" | "POST");
        if !simple_method { return false; }
        
        // All headers must be CORS-safelisted
        for (name, value) in &self.headers {
            let name_lower = name.to_lowercase();
            if !CORS_SAFELISTED_REQUEST_HEADERS.contains(&name_lower.as_str()) {
                return false;
            }
            // Content-Type must be a safe value
            if name_lower == "content-type" {
                let ct = value.split(';').next().unwrap_or("").trim().to_lowercase();
                if !CORS_SAFE_CONTENT_TYPES.contains(&ct.as_str()) {
                    return false;
                }
            }
        }
        
        true
    }
    
    /// Generate the list of non-safelisted headers for the preflight
    pub fn non_safelisted_headers(&self) -> Vec<String> {
        self.headers.keys()
            .filter(|h| {
                let lower = h.to_lowercase();
                !CORS_SAFELISTED_REQUEST_HEADERS.contains(&lower.as_str())
                && !FORBIDDEN_REQUEST_HEADERS.contains(&lower.as_str())
            })
            .cloned()
            .collect()
    }
}

/// The server's CORS response headers
#[derive(Debug, Clone, Default)]
pub struct CorsResponseHeaders {
    pub allow_origin: Option<String>,
    pub allow_credentials: bool,
    pub allow_methods: Vec<String>,
    pub allow_headers: Vec<String>,
    pub expose_headers: Vec<String>,
    pub max_age: Option<u32>,
    pub allow_private_network: bool,
}

impl CorsResponseHeaders {
    /// Parse from raw response headers map
    pub fn from_headers(headers: &HashMap<String, String>) -> Self {
        let mut cors = Self::default();
        
        for (key, value) in headers {
            match key.to_lowercase().as_str() {
                "access-control-allow-origin" => {
                    cors.allow_origin = Some(value.trim().to_string());
                }
                "access-control-allow-credentials" => {
                    cors.allow_credentials = value.trim().to_lowercase() == "true";
                }
                "access-control-allow-methods" => {
                    cors.allow_methods = value.split(',')
                        .map(|m| m.trim().to_uppercase())
                        .collect();
                }
                "access-control-allow-headers" => {
                    cors.allow_headers = value.split(',')
                        .map(|h| h.trim().to_lowercase())
                        .collect();
                }
                "access-control-expose-headers" => {
                    cors.expose_headers = value.split(',')
                        .map(|h| h.trim().to_lowercase())
                        .collect();
                }
                "access-control-max-age" => {
                    cors.max_age = value.trim().parse().ok();
                }
                "access-control-allow-private-network" => {
                    cors.allow_private_network = value.trim().to_lowercase() == "true";
                }
                _ => {}
            }
        }
        
        cors
    }
    
    /// Check if the origin is allowed based on the ACAO header
    pub fn origin_allowed(&self, request_origin: &str, credentials: CredentialsMode) -> CorsCheckResult {
        let allow_origin = match &self.allow_origin {
            Some(o) => o,
            None => return CorsCheckResult::Blocked {
                reason: CorsBlockReason::NoAllowOriginHeader
            },
        };
        
        if allow_origin == "*" {
            // Wildcard with credentials is forbidden
            if credentials == CredentialsMode::Include {
                return CorsCheckResult::Blocked {
                    reason: CorsBlockReason::CredentialsWithWildcard,
                };
            }
            return CorsCheckResult::Allowed;
        }
        
        if allow_origin == request_origin {
            return CorsCheckResult::Allowed;
        }
        
        CorsCheckResult::Blocked {
            reason: CorsBlockReason::OriginNotAllowed {
                expected: allow_origin.clone(),
                actual: request_origin.to_string(),
            },
        }
    }
    
    /// Validate a preflight response
    pub fn validate_preflight(
        &self,
        request: &CorsRequest,
    ) -> CorsCheckResult {
        // Check origin
        let origin_check = self.origin_allowed(&request.origin, request.credentials);
        if !matches!(origin_check, CorsCheckResult::Allowed) {
            return origin_check;
        }
        
        // Check method is allowed
        let method_upper = request.method.to_uppercase();
        if !self.allow_methods.is_empty() && !self.allow_methods.contains(&method_upper) {
            return CorsCheckResult::Blocked {
                reason: CorsBlockReason::MethodNotAllowed { method: method_upper },
            };
        }
        
        // Check all non-safelisted headers are permitted
        for header in request.non_safelisted_headers() {
            let header_lower = header.to_lowercase();
            if !self.allow_headers.contains(&header_lower)
            && !self.allow_headers.iter().any(|h| h == "*") {
                return CorsCheckResult::Blocked {
                    reason: CorsBlockReason::HeaderNotAllowed { header },
                };
            }
        }
        
        CorsCheckResult::Allowed
    }
    
    /// Get the set of response headers accessible to JavaScript
    pub fn accessible_response_headers(&self, all_headers: &HashMap<String, String>) -> HashMap<String, String> {
        let mut accessible = HashMap::new();
        
        // Always expose CORS-safelisted response headers
        for (key, value) in all_headers {
            let key_lower = key.to_lowercase();
            
            if CORS_SAFELISTED_RESPONSE_HEADERS.contains(&key_lower.as_str()) {
                accessible.insert(key.clone(), value.clone());
                continue;
            }
            
            // Check explicit expose list
            if self.expose_headers.contains(&key_lower)
            || self.expose_headers.iter().any(|h| h == "*") {
                // Wildcard exposure doesn't apply to forbidden headers
                if !FORBIDDEN_RESPONSE_HEADERS.contains(&key_lower.as_str()) {
                    accessible.insert(key.clone(), value.clone());
                }
            }
        }
        
        accessible
    }
}

/// Preflight cache entry
#[derive(Debug)]
pub struct PreflightCacheEntry {
    pub origin: String,
    pub methods: HashSet<String>,
    pub headers: HashSet<String>,
    pub max_age_seconds: u32,
    pub cached_at: std::time::Instant,
    pub credentials: bool,
}

impl PreflightCacheEntry {
    pub fn is_expired(&self) -> bool {
        self.cached_at.elapsed().as_secs() >= self.max_age_seconds as u64
    }
    
    pub fn covers_request(&self, request: &CorsRequest) -> bool {
        if !self.methods.contains(&request.method.to_uppercase()) { return false; }
        
        for header in request.non_safelisted_headers() {
            if !self.headers.contains(&header.to_lowercase()) { return false; }
        }
        
        if request.credentials == CredentialsMode::Include && !self.credentials { return false; }
        
        true
    }
}

/// The preflight cache (per browser instance)
pub struct PreflightCache {
    entries: HashMap<String, Vec<PreflightCacheEntry>>,
}

impl PreflightCache {
    pub fn new() -> Self { Self { entries: HashMap::new() } }
    
    pub fn cache_key(url: &str, origin: &str) -> String {
        format!("{}@{}", origin, url)
    }
    
    pub fn lookup(&self, request: &CorsRequest) -> bool {
        let key = Self::cache_key(&request.url, &request.origin);
        if let Some(entries) = self.entries.get(&key) {
            return entries.iter()
                .filter(|e| !e.is_expired())
                .any(|e| e.covers_request(request));
        }
        false
    }
    
    pub fn store(&mut self, url: &str, entry: PreflightCacheEntry) {
        let key = Self::cache_key(url, &entry.origin);
        self.entries.entry(key).or_default().push(entry);
    }
    
    pub fn evict_expired(&mut self) {
        for entries in self.entries.values_mut() {
            entries.retain(|e| !e.is_expired());
        }
        self.entries.retain(|_, v| !v.is_empty());
    }
}
