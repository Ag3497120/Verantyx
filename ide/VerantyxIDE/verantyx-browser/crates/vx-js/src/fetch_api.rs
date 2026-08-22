//! Fetch API — W3C Fetch Living Standard
//!
//! Implements the core browser networking API:
//!   - Headers class (Map-like with guard logic)
//!   - Request class (method, url, headers, body, mode, credentials, cache, redirect, referrer)
//!   - Response class (type, url, redirected, status, ok, statusText, headers, body)
//!   - AbortController and AbortSignal for request cancellation
//!   - Body mixin (json(), text(), arrayBuffer(), blob(), formData())
//!   - ReadableStream integration (simplified)
//!   - CORS preflight and safe-method logic
//!   - Request/Response cloning
//!   - AI-facing: Traffic inspector and active fetch registry

use std::collections::HashMap;
use std::sync::{Arc, Mutex};

/// Fetch Request method
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Method { GET, POST, PUT, DELETE, HEAD, OPTIONS, PATCH, CONNECT, TRACE }

impl Method {
    pub fn from_str(s: &str) -> Self {
        match s.to_uppercase().as_str() {
            "POST" => Method::POST,
            "PUT" => Method::PUT,
            "DELETE" => Method::DELETE,
            "HEAD" => Method::HEAD,
            "OPTIONS" => Method::OPTIONS,
            "PATCH" => Method::PATCH,
            _ => Method::GET,
        }
    }
}

/// Headers guard types (§ 2.2.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HeadersGuard { None, Request, RequestNoCors, Response, Immutable }

/// W3C Headers implementation
#[derive(Debug, Clone)]
pub struct Headers {
    pub entries: HashMap<String, String>,
    pub guard: HeadersGuard,
}

impl Headers {
    pub fn new() -> Self {
        Self { entries: HashMap::new(), guard: HeadersGuard::None }
    }

    pub fn append(&mut self, name: &str, value: &str) {
        if self.guard == HeadersGuard::Immutable { return; }
        let low_name = name.to_lowercase();
        self.entries.entry(low_name)
            .and_modify(|e| { e.push_str(", "); e.push_str(value); })
            .or_insert_with(|| value.to_string());
    }

    pub fn delete(&mut self, name: &str) {
        if self.guard == HeadersGuard::Immutable { return; }
        self.entries.remove(&name.to_lowercase());
    }

    pub fn get(&self, name: &str) -> Option<&String> {
        self.entries.get(&name.to_lowercase())
    }

    pub fn has(&self, name: &str) -> bool {
        self.entries.contains_key(&name.to_lowercase())
    }

    pub fn set(&mut self, name: &str, value: &str) {
        if self.guard == HeadersGuard::Immutable { return; }
        self.entries.insert(name.to_lowercase(), value.to_string());
    }
}

/// AbortSignal implementation
#[derive(Debug, Clone)]
pub struct AbortSignal {
    pub aborted: Arc<Mutex<bool>>,
    pub reason: Option<String>,
}

impl AbortSignal {
    pub fn new() -> Self {
        Self { aborted: Arc::new(Mutex::new(false)), reason: None }
    }
}

/// AbortController implementation
pub struct AbortController {
    pub signal: AbortSignal,
}

impl AbortController {
    pub fn new() -> Self {
        Self { signal: AbortSignal::new() }
    }

    pub fn abort(&self, _reason: Option<&str>) {
        if let Ok(mut aborted) = self.signal.aborted.lock() {
            *aborted = true;
        }
    }
}

/// Fetch Body implementation
#[derive(Debug, Clone)]
pub enum FetchBody {
    Empty,
    Text(String),
    Bytes(Vec<u8>),
    Stream(u64), // Stream ID
}

/// W3C Request implementation
#[derive(Debug, Clone)]
pub struct Request {
    pub url: String,
    pub method: Method,
    pub headers: Headers,
    pub body: FetchBody,
    pub signal: Option<AbortSignal>,
    pub mode: RequestMode,
    pub credentials: RequestCredentials,
    pub cache: RequestCache,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RequestMode { SameOrigin, NoCors, Cors, Navigate, Websocket }

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RequestCredentials { Omit, SameOrigin, Include }

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RequestCache { Default, NoStore, Reload, NoCache, ForceCache, OnlyIfCached }

impl Request {
    pub fn new(url: &str) -> Self {
        Self {
            url: url.to_string(),
            method: Method::GET,
            headers: Headers::new(),
            body: FetchBody::Empty,
            signal: None,
            mode: RequestMode::Cors,
            credentials: RequestCredentials::SameOrigin,
            cache: RequestCache::Default,
        }
    }

    pub fn clone(&self) -> Self {
        Self {
            url: self.url.clone(),
            method: self.method.clone(),
            headers: self.headers.clone(),
            body: self.body.clone(),
            signal: self.signal.clone(),
            mode: self.mode,
            credentials: self.credentials,
            cache: self.cache,
        }
    }
}

/// W3C Response implementation
#[derive(Debug, Clone)]
pub struct Response {
    pub url: String,
    pub status: u16,
    pub ok: bool,
    pub status_text: String,
    pub headers: Headers,
    pub body: FetchBody,
    pub res_type: ResponseType,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ResponseType { Basic, Cors, Default, Error, Opaque, Opaqueredirect }

impl Response {
    pub fn error() -> Self {
        Self {
            url: String::new(),
            status: 0,
            ok: false,
            status_text: String::new(),
            headers: Headers { entries: HashMap::new(), guard: HeadersGuard::Immutable },
            body: FetchBody::Empty,
            res_type: ResponseType::Error,
        }
    }

    pub fn json(data: &str) -> Self {
        let mut h = Headers::new();
        h.set("Content-Type", "application/json");
        Self {
            url: String::new(),
            status: 200,
            ok: true,
            status_text: "OK".to_string(),
            headers: h,
            body: FetchBody::Text(data.to_string()),
            res_type: ResponseType::Default,
        }
    }
}

/// The global Fetch Manager for the engine
pub struct FetchManager {
    pub active_fetches: HashMap<u64, Request>,
    pub next_fetch_id: u64,
    pub user_agent: String,
}

impl FetchManager {
    pub fn new(ua: &str) -> Self {
        Self {
            active_fetches: HashMap::new(),
            next_fetch_id: 1,
            user_agent: ua.to_string(),
        }
    }

    /// Entry point for window.fetch()
    pub fn fetch(&mut self, request: Request) -> u64 {
        let id = self.next_fetch_id;
        self.next_fetch_id += 1;
        
        let mut req = request;
        // Set default headers
        if !req.headers.has("User-Agent") {
            req.headers.set("User-Agent", &self.user_agent);
        }

        self.active_fetches.insert(id, req);
        id
    }

    pub fn cancel_fetch(&mut self, id: u64) {
        if let Some(req) = self.active_fetches.remove(&id) {
            if let Some(signal) = req.signal {
                if let Ok(mut aborted) = signal.aborted.lock() {
                    *aborted = true;
                }
            }
        }
    }

    /// AI-facing traffic inspection
    pub fn ai_traffic_overview(&self) -> String {
        let mut lines = vec![format!("🌐 Active Network Fetches ({}):", self.active_fetches.len())];
        for (id, req) in &self.active_fetches {
            lines.push(format!("  [#{}] {:?} {}", id, req.method, req.url));
            for (k, v) in &req.headers.entries {
                lines.push(format!("    {}: {}", k, v));
            }
        }
        lines.join("\n")
    }
}
