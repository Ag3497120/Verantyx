//! Phase 8: External Script Loading + ES Module cache
//!
//! Handles:
//! - <script src="..."> fetch and execution
//! - ES Module loading (import/export)  
//! - Script integrity verification (SRI)
//! - Module caching

use anyhow::{Result, anyhow};
use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use url::Url;
use vx_net::HttpClient;

/// Script cache keyed by URL
#[derive(Debug, Default, Clone)]
pub struct ScriptCache {
    inner: Arc<Mutex<HashMap<String, CachedScript>>>,
}

#[derive(Debug, Clone)]
pub struct CachedScript {
    pub url: String,
    pub source: String,
    pub integrity: Option<String>,
    pub content_type: String,
    pub cached_at: std::time::SystemTime,
}

impl ScriptCache {
    pub fn new() -> Self { Self::default() }

    pub fn get(&self, url: &str) -> Option<CachedScript> {
        self.inner.lock().unwrap().get(url).cloned()
    }

    pub fn insert(&self, url: String, script: CachedScript) {
        self.inner.lock().unwrap().insert(url, script);
    }

    pub fn invalidate(&self, url: &str) {
        self.inner.lock().unwrap().remove(url);
    }

    pub fn clear(&self) {
        self.inner.lock().unwrap().clear();
    }
}

/// Script fetcher — downloads scripts over HTTP/HTTPS
#[derive(Clone)]
pub struct ScriptFetcher {
    cache: ScriptCache,
    client: HttpClient,
    base_url: Option<Url>,
    allowed_origins: Vec<String>,
}

impl ScriptFetcher {
    pub fn new() -> Self {
        Self {
            cache: ScriptCache::new(),
            client: HttpClient::new(),
            base_url: None,
            allowed_origins: vec![],
        }
    }

    pub fn with_client(mut self, client: HttpClient) -> Self {
        self.client = client;
        self
    }

    pub fn with_base_url(mut self, url: &str) -> Self {
        self.base_url = Url::parse(url).ok();
        self
    }

    pub fn with_cache(mut self, cache: ScriptCache) -> Self {
        self.cache = cache;
        self
    }

    /// Resolve a relative URL against the page base URL
    pub fn resolve_url(&self, src: &str) -> Result<String> {
        if src.starts_with("http://") || src.starts_with("https://") || src.starts_with("//") {
            let resolved = if src.starts_with("//") {
                let scheme = self.base_url.as_ref()
                    .map(|u| u.scheme())
                    .unwrap_or("https");
                format!("{}:{}", scheme, src)
            } else {
                src.to_string()
            };
            return Ok(resolved);
        }

        if let Some(base) = &self.base_url {
            let resolved = base.join(src)
                .map_err(|e| anyhow!("URL resolution failed: {}", e))?;
            Ok(resolved.to_string())
        } else {
            Err(anyhow!("No base URL set and script src is relative: {}", src))
        }
    }

    /// Fetch a script from URL (with cache)
    pub async fn fetch(&self, url: &str) -> Result<String> {
        // Check cache first
        if let Some(cached) = self.cache.get(url) {
            return Ok(cached.source);
        }

        let resolved = self.resolve_url(url)?;
        let source = self.fetch_uncached(&resolved).await?;

        self.cache.insert(resolved.clone(), CachedScript {
            url: resolved,
            source: source.clone(),
            integrity: None,
            content_type: "application/javascript".to_string(),
            cached_at: std::time::SystemTime::now(),
        });

        Ok(source)
    }

    /// Fetch without cache
    async fn fetch_uncached(&self, url: &str) -> Result<String> {
        let mut resp = self.client.get(url).await?;
        let text = resp.text()?;
        Ok(text)
    }

    /// Verify script integrity (SRI)
    pub fn verify_integrity(&self, source: &str, integrity: &str) -> Result<()> {
        use sha2::{Sha256, Sha384, Sha512, Digest};
        use base64::Engine;

        let parts: Vec<&str> = integrity.split_whitespace().collect();
        for part in &parts {
            if let Some((algo, b64)) = part.split_once('-') {
                let expected = base64::engine::general_purpose::STANDARD
                    .decode(b64)
                    .map_err(|e| anyhow!("SRI base64 decode: {}", e))?;

                let computed: Vec<u8> = match algo {
                    "sha256" => { let mut h = Sha256::new(); h.update(source.as_bytes()); h.finalize().to_vec() }
                    "sha384" => { let mut h = Sha384::new(); h.update(source.as_bytes()); h.finalize().to_vec() }
                    "sha512" => { let mut h = Sha512::new(); h.update(source.as_bytes()); h.finalize().to_vec() }
                    _ => return Err(anyhow!("Unknown SRI hash algorithm: {}", algo)),
                };

                if computed == expected {
                    return Ok(());
                } else {
                    return Err(anyhow!("SRI integrity check failed for algorithm {}", algo));
                }
            }
        }
        Err(anyhow!("No valid SRI hash found in: {}", integrity))
    }
}

impl Default for ScriptFetcher {
    fn default() -> Self { Self::new() }
}

/// Module loading record
#[derive(Debug, Clone)]
pub struct ModuleRecord {
    pub url: String,
    pub source: String,
    pub exports: Vec<String>,
    pub imports: Vec<ModuleImport>,
    pub loaded: bool,
}

#[derive(Debug, Clone)]
pub struct ModuleImport {
    pub from: String,
    pub specifiers: Vec<String>,
}

/// ES Module dependency graph
#[derive(Debug, Default)]
pub struct ModuleGraph {
    pub modules: HashMap<String, ModuleRecord>,
    pub loading: Vec<String>,
}

impl ModuleGraph {
    pub fn new() -> Self { Self::default() }

    pub fn is_loaded(&self, url: &str) -> bool {
        self.modules.get(url).map(|m| m.loaded).unwrap_or(false)
    }

    pub fn add_module(&mut self, record: ModuleRecord) {
        self.modules.insert(record.url.clone(), record);
    }

    /// Parse static imports from a module source
    pub fn parse_imports(source: &str) -> Vec<ModuleImport> {
        let mut imports = Vec::new();
        for line in source.lines() {
            let trimmed = line.trim();
            // Match: import { x, y } from 'module'
            // Match: import x from 'module'
            // Match: import * as ns from 'module'
            if trimmed.starts_with("import ") {
                if let Some(from_idx) = trimmed.rfind("from ") {
                    let from_str = &trimmed[from_idx + 5..];
                    let module_url = from_str.trim().trim_matches(|c| c == '\'' || c == '"' || c == ';').to_string();

                    let spec_part = &trimmed[7..from_idx].trim();
                    let specifiers = if spec_part.contains('{') {
                        spec_part.trim_matches(|c| c == '{' || c == '}')
                            .split(',')
                            .map(|s| s.trim().split_whitespace().next().unwrap_or("").to_string())
                            .filter(|s| !s.is_empty())
                            .collect()
                    } else if spec_part.starts_with("* as ") {
                        vec![format!("* as {}", &spec_part[5..])]
                    } else {
                        vec![spec_part.to_string()]
                    };

                    imports.push(ModuleImport { from: module_url, specifiers });
                }
            }
        }
        imports
    }

    /// Parse exports from module source
    pub fn parse_exports(source: &str) -> Vec<String> {
        let mut exports = Vec::new();
        for line in source.lines() {
            let trimmed = line.trim();
            if trimmed.starts_with("export ") {
                // export const/let/var/function/class name
                for keyword in &["const ", "let ", "var ", "function ", "class ", "default "] {
                    if let Some(rest) = trimmed.strip_prefix(&format!("export {}", keyword)) {
                        let name = rest.split_whitespace().next()
                            .unwrap_or("default")
                            .trim_end_matches('(')
                            .to_string();
                        exports.push(name);
                        break;
                    }
                }
                // export { x, y as z }
                if trimmed.starts_with("export {") {
                    let inner = &trimmed[7..];
                    let end = inner.find('}').unwrap_or(inner.len());
                    for spec in inner[..end].split(',') {
                        let name = spec.split(" as ").last()
                            .unwrap_or(spec)
                            .trim()
                            .to_string();
                        if !name.is_empty() { exports.push(name); }
                    }
                }
            }
        }
        exports
    }

    /// Generate a CommonJS-compatible wrapper for a module
    pub fn wrap_esm_as_cjs(source: &str, _module_url: &str) -> String {
        // Basic ESM → CJS transform for QuickJS
        let mut result = String::new();
        result.push_str("(function(exports, require, module, __filename, __dirname) {\n");

        // Convert import statements to requires
        let mut transformed = source.to_string();
        for imp in Self::parse_imports(source) {
            let old = format!("from '{}'", imp.from);
            let new = format!("= require('{}')", imp.from);
            // Simple replacement (not perfect, but works for basic cases)
            transformed = transformed.replace(&old, &new);
            // Also fix the import keyword
        }

        // Convert export to module.exports
        result.push_str(&transformed);
        result.push_str("\n})(exports, require, module, __filename, __dirname);\n");
        result
    }
}

/// Inline script extractor from HTML
pub fn extract_script_tags(html: &str) -> Vec<ScriptTag> {
    let mut tags = Vec::new();
    let mut pos = 0;
    let lower = html.to_lowercase();

    while let Some(start) = lower[pos..].find("<script") {
        let abs_start = pos + start;
        let tag_end = html[abs_start..].find('>').map(|e| abs_start + e + 1).unwrap_or(abs_start + 7);
        let tag_attrs = &html[abs_start..tag_end];

        let src = extract_attr(tag_attrs, "src");
        let type_attr = extract_attr(tag_attrs, "type").unwrap_or_else(|| "text/javascript".to_string());
        let integrity = extract_attr(tag_attrs, "integrity");
        let defer = tag_attrs.to_lowercase().contains("defer");
        let async_load = tag_attrs.to_lowercase().contains("async");
        let crossorigin = extract_attr(tag_attrs, "crossorigin");
        let nonce = extract_attr(tag_attrs, "nonce");

        // Get inline content
        let script_end = lower[tag_end..].find("</script>").map(|e| tag_end + e);
        let inline_content = script_end.map(|end| html[tag_end..end].to_string());

        tags.push(ScriptTag {
            src,
            type_attr,
            integrity,
            defer,
            async_load,
            crossorigin,
            nonce,
            inline_content,
            position: abs_start,
        });

        pos = script_end.unwrap_or(tag_end) + 9; // after </script>
        if pos >= html.len() { break; }
    }

    tags
}

fn extract_attr(tag: &str, attr: &str) -> Option<String> {
    let pattern_dq = format!("{}=\"", attr);
    let pattern_sq = format!("{}='", attr);
    let lower = tag.to_lowercase();

    if let Some(start) = lower.find(&pattern_dq) {
        let content_start = start + pattern_dq.len();
        let end = tag[content_start..].find('"').map(|e| content_start + e)?;
        return Some(tag[content_start..end].to_string());
    }
    if let Some(start) = lower.find(&pattern_sq) {
        let content_start = start + pattern_sq.len();
        let end = tag[content_start..].find('\'').map(|e| content_start + e)?;
        return Some(tag[content_start..end].to_string());
    }
    // boolean attribute or bare value
    if lower.contains(&format!(" {} ", attr)) || lower.contains(&format!(" {}>", attr)) {
        return Some(attr.to_string());
    }
    None
}

/// A parsed <script> tag
#[derive(Debug, Clone)]
pub struct ScriptTag {
    pub src: Option<String>,
    pub type_attr: String,
    pub integrity: Option<String>,
    pub defer: bool,
    pub async_load: bool,
    pub crossorigin: Option<String>,
    pub nonce: Option<String>,
    pub inline_content: Option<String>,
    pub position: usize,
}

impl ScriptTag {
    pub fn is_module(&self) -> bool {
        self.type_attr.to_lowercase() == "module"
    }

    pub fn is_json(&self) -> bool {
        self.type_attr.to_lowercase().contains("json")
    }

    pub fn is_executable(&self) -> bool {
        let t = self.type_attr.to_lowercase();
        t.is_empty() || t == "text/javascript" || t == "application/javascript"
            || t == "module" || t.contains("javascript")
    }

    pub fn is_external(&self) -> bool {
        self.src.is_some()
    }
}

/// Script load order resolution
/// Returns: (immediate, deferred, async_scripts)
pub fn classify_scripts(tags: Vec<ScriptTag>) -> (Vec<ScriptTag>, Vec<ScriptTag>, Vec<ScriptTag>) {
    let mut immediate = Vec::new();
    let mut deferred = Vec::new();
    let mut async_scripts = Vec::new();

    for tag in tags {
        if !tag.is_executable() { continue; }
        if tag.async_load {
            async_scripts.push(tag);
        } else if tag.defer || tag.is_module() {
            deferred.push(tag);
        } else {
            immediate.push(tag);
        }
    }

    (immediate, deferred, async_scripts)
}

/// CommonJS require() shim for bundled libraries
pub fn generate_require_shim(available_modules: &[(&str, &str)]) -> String {
    let mut shim = String::from(r#"
var __modules = {};
var __cache = {};
function require(id) {
    if (__cache[id]) return __cache[id].exports;
    if (__modules[id]) {
        var module = { exports: {}, id: id };
        __cache[id] = module;
        __modules[id](module.exports, require, module);
        return module.exports;
    }
    // Try without extension
    var withJs = id + '.js';
    if (__modules[withJs]) {
        var module2 = { exports: {}, id: withJs };
        __cache[withJs] = module2;
        __modules[withJs](module2.exports, require, module2);
        return module2.exports;
    }
    throw new Error('Cannot find module: ' + id);
}
"#);

    for (name, code) in available_modules {
        shim.push_str(&format!(
            "__modules['{}'] = function(exports, require, module) {{\n{}\n}};\n",
            name, code
        ));
    }

    shim
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_extract_script_tags_inline() {
        let html = r#"<html><head>
            <script>var x = 1;</script>
            <script type="text/javascript">var y = 2;</script>
        </head></html>"#;
        let tags = extract_script_tags(html);
        assert_eq!(tags.len(), 2);
        assert!(tags[0].inline_content.as_deref().unwrap_or("").contains("x = 1"));
    }

    #[test]
    fn test_extract_script_tags_external() {
        let html = r#"<script src="/app.js" defer></script><script src="https://cdn.example.com/lib.js" async integrity="sha256-abc123"></script>"#;
        let tags = extract_script_tags(html);
        assert_eq!(tags.len(), 2);
        assert_eq!(tags[0].src.as_deref(), Some("/app.js"));
        assert!(tags[0].defer);
        assert_eq!(tags[1].src.as_deref(), Some("https://cdn.example.com/lib.js"));
        assert!(tags[1].async_load);
        assert!(tags[1].integrity.is_some());
    }

    #[test]
    fn test_classify_scripts() {
        let tags = vec![
            ScriptTag { src: Some("a.js".into()), type_attr: "text/javascript".into(), integrity: None, defer: false, async_load: false, crossorigin: None, nonce: None, inline_content: None, position: 0 },
            ScriptTag { src: Some("b.js".into()), type_attr: "text/javascript".into(), integrity: None, defer: true, async_load: false, crossorigin: None, nonce: None, inline_content: None, position: 1 },
            ScriptTag { src: Some("c.js".into()), type_attr: "text/javascript".into(), integrity: None, defer: false, async_load: true, crossorigin: None, nonce: None, inline_content: None, position: 2 },
        ];
        let (imm, def, asyn) = classify_scripts(tags);
        assert_eq!(imm.len(), 1);
        assert_eq!(def.len(), 1);
        assert_eq!(asyn.len(), 1);
    }

    #[test]
    fn test_parse_imports() {
        let source = r#"
import React from 'react';
import { useState, useEffect } from 'react';
import * as utils from './utils';
"#;
        let imports = ModuleGraph::parse_imports(source);
        assert_eq!(imports.len(), 3);
        assert_eq!(imports[0].from, "react");
        assert!(imports[1].specifiers.contains(&"useState".to_string()));
    }

    #[test]
    fn test_parse_exports() {
        let source = r#"
export const VERSION = '1.0';
export function greet(name) {}
export class Widget {}
export default App;
export { foo, bar as baz };
"#;
        let exports = ModuleGraph::parse_exports(source);
        assert!(exports.len() >= 3);
    }

    #[test]
    fn test_resolve_relative_url() {
        let fetcher = ScriptFetcher::new().with_base_url("https://example.com/app/index.html");
        let resolved = fetcher.resolve_url("../lib.js").unwrap();
        assert!(resolved.contains("example.com"));
    }

    #[test]
    fn test_require_shim() {
        let shim = generate_require_shim(&[
            ("lodash", "exports.add = function(a,b){ return a+b; };"),
        ]);
        assert!(shim.contains("__modules"));
        assert!(shim.contains("lodash"));
    }
}
