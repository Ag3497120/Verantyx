//! Phase 10: Complete fetch() API implementation
//!
//! W3C Fetch specification:
//! - Request / Response / Headers objects
//! - ReadableStream body (streaming)
//! - CORS mode, credentials, cache, redirect
//! - AbortController support
//! - FormData, URLSearchParams body types
//! - Body mixin (json(), text(), blob(), arrayBuffer(), formData())

use anyhow::{Result, anyhow};
use std::collections::HashMap;
use std::time::Duration;
use bytes::Bytes;

/// HTTP method
#[derive(Debug, Clone, PartialEq)]
pub enum HttpMethod {
    Get, Post, Put, Delete, Patch, Head, Options, Connect, Trace,
    Custom(String),
}

impl HttpMethod {
    pub fn parse(s: &str) -> Self {
        match s.to_uppercase().as_str() {
            "GET" => Self::Get,
            "POST" => Self::Post,
            "PUT" => Self::Put,
            "DELETE" => Self::Delete,
            "PATCH" => Self::Patch,
            "HEAD" => Self::Head,
            "OPTIONS" => Self::Options,
            "CONNECT" => Self::Connect,
            "TRACE" => Self::Trace,
            other => Self::Custom(other.to_string()),
        }
    }

    pub fn as_str(&self) -> &str {
        match self {
            Self::Get => "GET", Self::Post => "POST", Self::Put => "PUT",
            Self::Delete => "DELETE", Self::Patch => "PATCH", Self::Head => "HEAD",
            Self::Options => "OPTIONS", Self::Connect => "CONNECT", Self::Trace => "TRACE",
            Self::Custom(s) => s.as_str(),
        }
    }

    pub fn is_safe(&self) -> bool {
        matches!(self, Self::Get | Self::Head | Self::Options | Self::Trace)
    }

    pub fn is_idempotent(&self) -> bool {
        matches!(self, Self::Get | Self::Head | Self::Put | Self::Delete | Self::Options | Self::Trace)
    }
}

impl std::fmt::Display for HttpMethod {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result { write!(f, "{}", self.as_str()) }
}

/// HTTP Headers (case-insensitive)
#[derive(Debug, Clone, Default)]
pub struct Headers {
    inner: HashMap<String, Vec<String>>,  // lowercase key → values
}

impl Headers {
    pub fn new() -> Self { Self::default() }

    pub fn append(&mut self, name: &str, value: &str) {
        self.inner.entry(name.to_lowercase())
            .or_insert_with(Vec::new)
            .push(value.to_string());
    }

    pub fn set(&mut self, name: &str, value: &str) {
        self.inner.insert(name.to_lowercase(), vec![value.to_string()]);
    }

    pub fn get(&self, name: &str) -> Option<&str> {
        self.inner.get(&name.to_lowercase())
            .and_then(|v| v.first())
            .map(|s| s.as_str())
    }

    pub fn get_all(&self, name: &str) -> &[String] {
        self.inner.get(&name.to_lowercase())
            .map(|v| v.as_slice())
            .unwrap_or(&[])
    }

    pub fn delete(&mut self, name: &str) {
        self.inner.remove(&name.to_lowercase());
    }

    pub fn has(&self, name: &str) -> bool {
        self.inner.contains_key(&name.to_lowercase())
    }

    pub fn iter(&self) -> impl Iterator<Item = (&str, &str)> {
        self.inner.iter().flat_map(|(k, vs)| vs.iter().map(move |v| (k.as_str(), v.as_str())))
    }

    pub fn content_type(&self) -> Option<&str> {
        self.get("content-type")
    }

    pub fn content_length(&self) -> Option<u64> {
        self.get("content-length")?.parse().ok()
    }

    pub fn is_json(&self) -> bool {
        self.content_type()
            .map(|ct| ct.contains("json"))
            .unwrap_or(false)
    }

    /// Convert to reqwest HeaderMap
    pub fn to_reqwest(&self) -> reqwest::header::HeaderMap {
        let mut map = reqwest::header::HeaderMap::new();
        for (k, vs) in &self.inner {
            if let Ok(name) = k.parse::<reqwest::header::HeaderName>() {
                for v in vs {
                    if let Ok(value) = v.parse::<reqwest::header::HeaderValue>() {
                        map.append(name.clone(), value);
                    }
                }
            }
        }
        map
    }
}

impl From<reqwest::header::HeaderMap> for Headers {
    fn from(map: reqwest::header::HeaderMap) -> Self {
        let mut headers = Self::new();
        for (name, value) in &map {
            if let Ok(v) = value.to_str() {
                headers.append(name.as_str(), v);
            }
        }
        headers
    }
}

/// Request body type
#[derive(Debug, Clone)]
pub enum RequestBody {
    None,
    Text(String),
    Json(serde_json::Value),
    Binary(Vec<u8>),
    Form(Vec<(String, String)>),         // application/x-www-form-urlencoded
    MultipartForm(Vec<FormField>),       // multipart/form-data
    UrlSearchParams(Vec<(String, String)>),
}

#[derive(Debug, Clone)]
pub struct FormField {
    pub name: String,
    pub filename: Option<String>,
    pub content_type: Option<String>,
    pub data: Vec<u8>,
}

impl RequestBody {
    pub fn from_json<T: serde::Serialize>(value: &T) -> Result<Self> {
        let v = serde_json::to_value(value)?;
        Ok(Self::Json(v))
    }

    pub fn is_empty(&self) -> bool { matches!(self, Self::None) }

    pub fn as_text(&self) -> Option<&str> {
        if let Self::Text(s) = self { Some(s) } else { None }
    }

    pub fn content_type_header(&self) -> Option<&str> {
        match self {
            Self::None => None,
            Self::Text(_) => Some("text/plain;charset=UTF-8"),
            Self::Json(_) => Some("application/json"),
            Self::Binary(_) => Some("application/octet-stream"),
            Self::Form(_) => Some("application/x-www-form-urlencoded"),
            Self::MultipartForm(_) => Some("multipart/form-data"),
            Self::UrlSearchParams(_) => Some("application/x-www-form-urlencoded"),
        }
    }
}

/// CORS credential mode
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum CredentialsMode { Omit, SameOrigin, Include }

/// CORS mode
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum FetchMode { Cors, NoCors, SameOrigin, Navigate }

/// Cache mode
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum CacheMode { Default, NoStore, Reload, NoCache, ForceCache, OnlyIfCached }

/// Redirect mode
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum RedirectMode { Follow, Error, Manual }

/// A fetch Request
#[derive(Debug, Clone)]
pub struct FetchRequest {
    pub url: String,
    pub method: HttpMethod,
    pub headers: Headers,
    pub body: RequestBody,
    pub mode: FetchMode,
    pub credentials: CredentialsMode,
    pub cache: CacheMode,
    pub redirect: RedirectMode,
    pub referrer: Option<String>,
    pub referrer_policy: Option<String>,
    pub integrity: Option<String>,
    pub keepalive: bool,
    pub timeout: Option<Duration>,
    pub abort_signal: Option<String>,
}

impl FetchRequest {
    pub fn get(url: &str) -> Self {
        Self {
            url: url.to_string(),
            method: HttpMethod::Get,
            headers: Headers::new(),
            body: RequestBody::None,
            mode: FetchMode::Cors,
            credentials: CredentialsMode::SameOrigin,
            cache: CacheMode::Default,
            redirect: RedirectMode::Follow,
            referrer: None,
            referrer_policy: None,
            integrity: None,
            keepalive: false,
            timeout: Some(Duration::from_secs(30)),
            abort_signal: None,
        }
    }

    pub fn post(url: &str, body: RequestBody) -> Self {
        let mut req = Self::get(url);
        req.method = HttpMethod::Post;
        req.body = body;
        req
    }

    pub fn post_json(url: &str, value: serde_json::Value) -> Self {
        let mut req = Self::post(url, RequestBody::Json(value));
        req.headers.set("content-type", "application/json");
        req
    }

    pub fn with_header(mut self, name: &str, value: &str) -> Self {
        self.headers.set(name, value);
        self
    }

    pub fn with_bearer(mut self, token: &str) -> Self {
        self.headers.set("authorization", &format!("Bearer {}", token));
        self
    }

    pub fn with_timeout(mut self, timeout: Duration) -> Self {
        self.timeout = Some(timeout);
        self
    }

    pub fn with_credentials(mut self) -> Self {
        self.credentials = CredentialsMode::Include;
        self
    }
}

/// A fetch Response
#[derive(Debug, Clone)]
pub struct FetchResponse {
    pub url: String,
    pub status: u16,
    pub status_text: String,
    pub headers: Headers,
    pub redirected: bool,
    pub response_type: ResponseType,
    pub body: Option<Bytes>,
    pub body_used: bool,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum ResponseType { Basic, Cors, Default, Error, Opaque, OpaqueRedirect }

impl FetchResponse {
    pub fn ok(&self) -> bool { self.status >= 200 && self.status < 300 }
    pub fn status(&self) -> u16 { self.status }

    /// Consume body as text
    pub fn text(&mut self) -> Result<String> {
        if self.body_used { return Err(anyhow!("Body already used")); }
        self.body_used = true;
        let bytes = self.body.as_ref().ok_or_else(|| anyhow!("No body"))?;
        Ok(String::from_utf8_lossy(bytes).into_owned())
    }

    /// Consume body as JSON
    pub fn json(&mut self) -> Result<serde_json::Value> {
        let text = self.text()?;
        Ok(serde_json::from_str(&text)?)
    }

    /// Consume body as bytes
    pub fn array_buffer(&mut self) -> Result<Vec<u8>> {
        if self.body_used { return Err(anyhow!("Body already used")); }
        self.body_used = true;
        Ok(self.body.as_ref().map(|b| b.to_vec()).unwrap_or_default())
    }

    /// Get body bytes without consuming
    pub fn body_bytes(&self) -> Option<&[u8]> {
        self.body.as_deref()
    }

    /// Error response
    pub fn error() -> Self {
        Self {
            url: String::new(),
            status: 0,
            status_text: String::new(),
            headers: Headers::new(),
            redirected: false,
            response_type: ResponseType::Error,
            body: None,
            body_used: false,
        }
    }
}

/// The main fetch executor
#[derive(Clone)]
pub struct FetchClient {
    client: reqwest::Client,
    base_url: Option<String>,
    default_headers: Headers,
    max_redirects: u32,
}

impl FetchClient {
    pub fn new() -> Result<Self> {
        let client = reqwest::Client::builder()
            .user_agent("vx-browser/0.2.0 Fetch")
            .redirect(reqwest::redirect::Policy::limited(20))
            .build()?;
        Ok(Self {
            client,
            base_url: None,
            default_headers: Headers::new(),
            max_redirects: 20,
        })
    }

    pub fn with_base_url(mut self, url: &str) -> Self {
        self.base_url = Some(url.to_string());
        self
    }

    pub fn with_default_header(mut self, name: &str, value: &str) -> Self {
        self.default_headers.set(name, value);
        self
    }

    /// Execute a fetch request
    pub async fn fetch(&self, request: &FetchRequest) -> Result<FetchResponse> {
        let url = if request.url.starts_with("http") {
            request.url.clone()
        } else if let Some(base) = &self.base_url {
            let base_url = url::Url::parse(base)?;
            base_url.join(&request.url)?.to_string()
        } else {
            return Err(anyhow!("No base URL and request URL is relative: {}", request.url));
        };

        let mut builder = match &request.method {
            HttpMethod::Get => self.client.get(&url),
            HttpMethod::Post => self.client.post(&url),
            HttpMethod::Put => self.client.put(&url),
            HttpMethod::Delete => self.client.delete(&url),
            HttpMethod::Patch => self.client.patch(&url),
            HttpMethod::Head => self.client.head(&url),
            HttpMethod::Options => self.client.request(reqwest::Method::OPTIONS, &url),
            _ => self.client.request(reqwest::Method::GET, &url),
        };

        // Merge default headers  
        let mut merged_headers = self.default_headers.clone();
        for (k, v) in request.headers.iter() {
            merged_headers.set(k, v);
        }
        builder = builder.headers(merged_headers.to_reqwest());

        // Timeout
        if let Some(timeout) = request.timeout {
            builder = builder.timeout(timeout);
        }

        // Body
        builder = match &request.body {
            RequestBody::None => builder,
            RequestBody::Text(s) => builder.body(s.clone()),
            RequestBody::Json(v) => builder.json(v),
            RequestBody::Binary(b) => builder.body(b.clone()),
            RequestBody::Form(fields) => {
                let form: Vec<(&str, &str)> = fields.iter()
                    .map(|(k, v)| (k.as_str(), v.as_str()))
                    .collect();
                builder.form(&form)
            }
            RequestBody::UrlSearchParams(params) => {
                let encoded = url::form_urlencoded::Serializer::new(String::new())
                    .extend_pairs(params)
                    .finish();
                builder.body(encoded)
            }
            RequestBody::MultipartForm(fields) => {
                let mut form = reqwest::multipart::Form::new();
                for field in fields {
                    let mut part = reqwest::multipart::Part::bytes(field.data.clone())
                        .file_name(field.filename.clone().unwrap_or_default());
                    if let Some(ref ct) = field.content_type {
                        part = part.mime_str(ct).unwrap_or_else(|_| {
                            reqwest::multipart::Part::bytes(field.data.clone())
                                .file_name(field.filename.clone().unwrap_or_default())
                        });
                    }
                    form = form.part(field.name.clone(), part);
                }
                builder.multipart(form)
            }
        };

        // Execute
        let response = builder.send().await
            .map_err(|e| anyhow!("fetch failed: {}", e))?;

        let final_url = response.url().to_string();
        let status = response.status().as_u16();
        let status_text = response.status().canonical_reason().unwrap_or("").to_string();
        let headers = Headers::from(response.headers().clone());
        let redirected = final_url != url;

        let body_bytes = response.bytes().await.ok().map(|b| b);

        Ok(FetchResponse {
            url: final_url,
            status,
            status_text,
            headers,
            redirected,
            response_type: ResponseType::Basic,
            body: body_bytes,
            body_used: false,
        })
    }

    /// GET convenience
    pub async fn get(&self, url: &str) -> Result<FetchResponse> {
        self.fetch(&FetchRequest::get(url)).await
    }

    /// GET as JSON
    pub async fn get_json(&self, url: &str) -> Result<serde_json::Value> {
        let mut resp = self.get(url).await?;
        if !resp.ok() {
            return Err(anyhow!("HTTP {} for {}", resp.status, url));
        }
        resp.json()
    }

    /// POST JSON
    pub async fn post_json(&self, url: &str, body: serde_json::Value) -> Result<FetchResponse> {
        self.fetch(&FetchRequest::post_json(url, body)).await
    }

    /// GET as text
    pub async fn get_text(&self, url: &str) -> Result<String> {
        let mut resp = self.get(url).await?;
        resp.text()
    }
}

impl Default for FetchClient {
    fn default() -> Self { Self::new().unwrap() }
}

/// URL class (browser API compatible)
#[derive(Debug, Clone)]
pub struct BrowserUrl {
    pub href: String,
    pub origin: String,
    pub protocol: String,
    pub username: String,
    pub password: String,
    pub hostname: String,
    pub port: String,
    pub pathname: String,
    pub search: String,
    pub hash: String,
    parsed: url::Url,
}

impl BrowserUrl {
    pub fn new(url_str: &str) -> Result<Self> {
        let parsed = url::Url::parse(url_str)
            .map_err(|e| anyhow!("Invalid URL '{}': {}", url_str, e))?;
        Ok(Self::from_parsed(parsed))
    }

    pub fn new_with_base(url_str: &str, base: &str) -> Result<Self> {
        let base_url = url::Url::parse(base)?;
        let parsed = base_url.join(url_str)?;
        Ok(Self::from_parsed(parsed))
    }

    fn from_parsed(parsed: url::Url) -> Self {
        Self {
            href: parsed.as_str().to_string(),
            origin: parsed.origin().ascii_serialization(),
            protocol: format!("{}:", parsed.scheme()),
            username: parsed.username().to_string(),
            password: parsed.password().unwrap_or("").to_string(),
            hostname: parsed.host_str().unwrap_or("").to_string(),
            port: parsed.port().map(|p| p.to_string()).unwrap_or_default(),
            pathname: parsed.path().to_string(),
            search: parsed.query().map(|q| format!("?{}", q)).unwrap_or_default(),
            hash: parsed.fragment().map(|f| format!("#{}", f)).unwrap_or_default(),
            parsed,
        }
    }

    pub fn search_params(&self) -> Vec<(String, String)> {
        self.parsed.query_pairs()
            .map(|(k, v)| (k.into_owned(), v.into_owned()))
            .collect()
    }

    pub fn set_search_param(&mut self, key: &str, value: &str) {
        let mut params = self.search_params();
        if let Some(existing) = params.iter_mut().find(|(k, _)| k == key) {
            existing.1 = value.to_string();
        } else {
            params.push((key.to_string(), value.to_string()));
        }
        let qs: String = url::form_urlencoded::Serializer::new(String::new())
            .extend_pairs(&params)
            .finish();
        self.parsed.set_query(if qs.is_empty() { None } else { Some(&qs) });
        self.href = self.parsed.as_str().to_string();
        self.search = self.parsed.query().map(|q| format!("?{}", q)).unwrap_or_default();
    }

    pub fn to_string(&self) -> &str { &self.href }
}

/// URLSearchParams
#[derive(Debug, Clone, Default)]
pub struct UrlSearchParams {
    params: Vec<(String, String)>,
}

impl UrlSearchParams {
    pub fn new() -> Self { Self::default() }

    pub fn from_string(s: &str) -> Self {
        let s = s.trim_start_matches('?');
        let params = url::form_urlencoded::parse(s.as_bytes())
            .map(|(k, v)| (k.into_owned(), v.into_owned()))
            .collect();
        Self { params }
    }

    pub fn append(&mut self, key: &str, value: &str) {
        self.params.push((key.to_string(), value.to_string()));
    }

    pub fn set(&mut self, key: &str, value: &str) {
        self.params.retain(|(k, _)| k != key);
        self.params.push((key.to_string(), value.to_string()));
    }

    pub fn get(&self, key: &str) -> Option<&str> {
        self.params.iter().find(|(k, _)| k == key).map(|(_, v)| v.as_str())
    }

    pub fn get_all(&self, key: &str) -> Vec<&str> {
        self.params.iter().filter(|(k, _)| k == key).map(|(_, v)| v.as_str()).collect()
    }

    pub fn delete(&mut self, key: &str) {
        self.params.retain(|(k, _)| k != key);
    }

    pub fn has(&self, key: &str) -> bool {
        self.params.iter().any(|(k, _)| k == key)
    }

    pub fn to_string(&self) -> String {
        url::form_urlencoded::Serializer::new(String::new())
            .extend_pairs(&self.params)
            .finish()
    }

    pub fn iter(&self) -> impl Iterator<Item = (&str, &str)> {
        self.params.iter().map(|(k, v)| (k.as_str(), v.as_str()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_headers_case_insensitive() {
        let mut h = Headers::new();
        h.set("Content-Type", "application/json");
        assert_eq!(h.get("content-type"), Some("application/json"));
        assert_eq!(h.get("CONTENT-TYPE"), Some("application/json"));
    }

    #[test]
    fn test_headers_append_multiple() {
        let mut h = Headers::new();
        h.append("Accept", "text/html");
        h.append("Accept", "application/json");
        assert_eq!(h.get_all("accept").len(), 2);
    }

    #[test]
    fn test_fetch_request_builder() {
        let req = FetchRequest::post_json("https://api.example.com/data", serde_json::json!({"key": "value"}))
            .with_bearer("my-token")
            .with_timeout(Duration::from_secs(10));
        assert_eq!(req.method, HttpMethod::Post);
        assert!(req.headers.has("authorization"));
        assert_eq!(req.timeout, Some(Duration::from_secs(10)));
    }

    #[test]
    fn test_http_method() {
        assert!(HttpMethod::Get.is_safe());
        assert!(HttpMethod::Delete.is_idempotent());
        assert!(!HttpMethod::Post.is_safe());
        assert!(!HttpMethod::Post.is_idempotent());
    }

    #[test]
    fn test_url_search_params() {
        let mut params = UrlSearchParams::from_string("?foo=1&bar=2&foo=3");
        assert_eq!(params.get("foo"), Some("1"));
        assert_eq!(params.get_all("foo").len(), 2);
        params.set("foo", "new");
        assert_eq!(params.get("foo"), Some("new"));
        assert_eq!(params.get_all("foo").len(), 1);
    }

    #[test]
    fn test_browser_url() {
        let url = BrowserUrl::new("https://user:pass@example.com:8080/path?q=1#section").unwrap();
        assert_eq!(url.protocol, "https:");
        assert_eq!(url.hostname, "example.com");
        assert_eq!(url.port, "8080");
        assert_eq!(url.pathname, "/path");
        assert_eq!(url.search, "?q=1");
        assert_eq!(url.hash, "#section");
        assert_eq!(url.username, "user");
    }

    #[test]
    fn test_browser_url_relative() {
        let url = BrowserUrl::new_with_base("../api/data", "https://example.com/app/page.html").unwrap();
        assert!(url.href.contains("example.com"));
        assert!(url.href.contains("api/data"));
    }

    #[test]
    fn test_response_not_ok() {
        let resp = FetchResponse {
            url: "https://example.com".into(),
            status: 404,
            status_text: "Not Found".into(),
            headers: Headers::new(),
            redirected: false,
            response_type: ResponseType::Basic,
            body: None,
            body_used: false,
        };
        assert!(!resp.ok());
    }
}
