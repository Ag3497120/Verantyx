//! vx-net — HTTP Client
//!
//! Provides a high-level API for network requests, wrapping the core FetchClient.

use crate::fetch::{FetchClient, FetchResponse, FetchRequest};
use anyhow::Result;

#[derive(Clone)]
pub struct HttpClient {
    inner: FetchClient,
}

impl HttpClient {
    pub fn new() -> Self {
        Self {
            // FetchClient::new() returns Result<Self>, unwrap for high-level API
            inner: FetchClient::new().expect("Failed to initialize FetchClient"),
        }
    }

    /// Asynchronous GET request (Phase 7/11)
    pub async fn get(&self, url: &str) -> Result<FetchResponse> {
        let req = FetchRequest::get(url);
        self.inner.fetch(&req).await
    }
}
