//! Fetch API — V8 (deno_core) Ops for non-blocking network requests
//!
//! Provides the bridge between JS fetch() calls and the vx-net HTTP client.
//! Implements: Request initiation, Response header resolution, and Body streaming.

use anyhow::Result;
use deno_core::{op2, OpState};
use vx_net::fetch::{FetchClient, FetchRequest, HttpMethod, RequestBody};
use serde::{Serialize, Deserialize};
use std::rc::Rc;
use std::cell::RefCell;

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct FetchArgs {
    pub url: String,
    pub method: String,
    pub headers: Option<Vec<(String, String)>>,
    pub body: Option<String>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct FetchResponseSync {
    pub status: u16,
    pub status_text: String,
    pub headers: Vec<(String, String)>,
    pub url: String,
}

/// Start a fetch request and return the result asynchronously
#[op2(async)]
#[serde]
pub async fn op_fetch(
    state: Rc<RefCell<OpState>>,
    #[serde] args: FetchArgs,
) -> Result<FetchResponseSync> {
    let client = {
        let state = state.borrow();
        state.borrow::<FetchClient>().clone()
    };

    let mut request = FetchRequest::get(&args.url);
    request.method = HttpMethod::parse(&args.method);
    
    if let Some(headers) = args.headers {
        for (k, v) in headers {
            request.headers.set(&k, &v);
        }
    }

    if let Some(body_text) = args.body {
        request.body = RequestBody::Text(body_text);
    }

    let response = client.fetch(&request).await?;
    
    let mut headers_vec = Vec::new();
    for (k, v) in response.headers.iter() {
        headers_vec.push((k.to_string(), v.to_string()));
    }

    Ok(FetchResponseSync {
        status: response.status,
        status_text: response.status_text,
        headers: headers_vec,
        url: response.url,
    })
}

/// Helper op to read the body of a completed fetch (buffered for now)
#[op2(async)]
#[string]
pub async fn op_fetch_read_text(
    state: Rc<RefCell<OpState>>,
    #[string] url: String,
) -> Result<String> {
    let client = {
        let state = state.borrow();
        state.borrow::<FetchClient>().clone()
    };

    let mut resp = client.get(&url).await?;
    resp.text()
}

deno_core::extension!(
    vx_fetch,
    ops = [op_fetch, op_fetch_read_text],
);
