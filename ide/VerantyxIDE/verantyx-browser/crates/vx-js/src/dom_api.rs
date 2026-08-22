//! DOM API — V8 (deno_core) bindings for vx-browser
//!
//! Provides document.querySelector, getElementById, createElement, etc.
//! These operate on the Rust NodeArena via Deno ops.

use deno_core::{extension, op2, OpState};
use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use vx_dom::{NodeArena, NodeId};

/// Maps numeric JS handles to internal Rust NodeIds
pub struct HandleCache {
    next_handle: u32,
    nodes: HashMap<u32, NodeId>,
}

impl HandleCache {
    pub fn new() -> Self {
        Self {
            next_handle: 1,
            nodes: HashMap::new(),
        }
    }

    pub fn insert(&mut self, node_id: NodeId) -> u32 {
        let handle = self.next_handle;
        self.nodes.insert(handle, node_id);
        self.next_handle += 1;
        handle
    }

    pub fn get(&self, handle: u32) -> Option<NodeId> {
        self.nodes.get(&handle).copied()
    }
}

#[op2]
#[string]
pub fn op_document_get_title(_state: &mut OpState) -> String {
    "Verantyx Page".to_string()
}

#[op2(fast)]
pub fn op_document_query_selector(state: &mut OpState, #[string] _selector: String) -> u32 {
    let cache_rc = state.borrow::<Arc<Mutex<HandleCache>>>().clone();
    let mut cache = cache_rc.lock().unwrap();
    cache.insert(NodeId(1))
}

#[op2]
#[string]
pub fn op_node_get_text(state: &mut OpState, handle: u32) -> String {
    let cache_rc = state.borrow::<Arc<Mutex<HandleCache>>>().clone();
    let cache = cache_rc.lock().unwrap();
    if let Some(_id) = cache.get(handle) {
        "Sample Text".to_string()
    } else {
        String::new()
    }
}

#[op2]
pub fn op_node_add_listener(state: &mut OpState, #[serde] node_id: NodeId, #[string] type_: String, handler_id: u32, capture: bool) {
    let arena = state.borrow_mut::<Arc<Mutex<NodeArena>>>();
    let mut arena = arena.lock().unwrap();
    if let Some(node) = arena.get_mut(node_id) {
        node.event_target.registry.add(&type_, handler_id, capture);
    }
}

#[op2]
pub fn op_node_remove_listener(state: &mut OpState, #[serde] node_id: NodeId, #[string] type_: String, handler_id: u32, capture: bool) {
    let arena = state.borrow_mut::<Arc<Mutex<NodeArena>>>();
    let mut arena = arena.lock().unwrap();
    if let Some(node) = arena.get_mut(node_id) {
        node.event_target.registry.remove(&type_, handler_id, capture);
    }
}

#[op2]
#[serde]
pub fn op_node_dispatch_event(
    state: &mut OpState, 
    #[serde] node_id: NodeId, 
    #[string] type_: String, 
    bubbles: bool, 
    cancelable: bool
) -> vx_dom::events::EventDispatchResult {
    let arena_arc = state.borrow_mut::<Arc<Mutex<NodeArena>>>().clone();
    let mut arena = arena_arc.lock().unwrap();
    let event = vx_dom::events::Event::new(&type_, bubbles, cancelable);
    vx_dom::events::EventDispatcher::dispatch(&mut arena, node_id, event)
}

extension!(
    vx_dom_api,
    ops = [
        op_document_get_title,
        op_document_query_selector,
        op_node_get_text,
        op_node_add_listener,
        op_node_remove_listener,
        op_node_dispatch_event,
    ],
);

pub fn init_dom_ops() -> deno_core::Extension {
    vx_dom_api::init_ops()
}

// The bootstrap code will be injected in JsRuntime
pub const DOM_BOOTSTRAP: &str = r#"
    const _handlers = new Map();
    let _nextHandlerId = 1;

    class Headers {
        constructor(init) {
            this._map = new Map();
            if (init) {
                for (const [k, v] of Object.entries(init)) {
                    this.append(k, v);
                }
            }
        }
        append(k, v) { this._map.set(k.toLowerCase(), v); }
        get(k) { return this._map.get(k.toLowerCase()); }
        entries() { return this._map.entries(); }
    }

    class Response {
        constructor(body, init = {}) {
            this._bodyText = body;
            this.status = init.status || 200;
            this.statusText = init.statusText || 'OK';
            this.headers = new Headers(init.headers);
            this.url = init.url || '';
        }
        async text() { return this._bodyText; }
        async json() { return JSON.parse(this._bodyText); }
        get ok() { return this.status >= 200 && this.status < 300; }
    }

    globalThis.Headers = Headers;
    globalThis.Response = Response;

    globalThis.fetch = async (url, options = {}) => {
        const method = options.method || 'GET';
        const headers = options.headers ? Object.entries(options.headers) : [];
        const body = options.body || null;

        const resp = await Deno.core.ops.op_fetch({ url, method, headers, body });
        const bodyText = await Deno.core.ops.op_fetch_read_text(resp.url);
        
        return new Response(bodyText, {
            status: resp.status,
            statusText: resp.statusText,
            headers: Object.fromEntries(resp.headers),
            url: resp.url
        });
    };

    class EventTarget {
        addEventListener(type, listener, options = {}) {
            const capture = typeof options === 'boolean' ? options : !!options.capture;
            const handlerId = _nextHandlerId++;
            _handlers.set(handlerId, listener);
            Deno.core.ops.op_node_add_listener(this.handle || 0, type, handlerId, capture);
        }

        removeEventListener(type, listener, options = {}) {
            const capture = typeof options === 'boolean' ? options : !!options.capture;
            Deno.core.ops.op_node_remove_listener(this.handle || 0, type, 0, capture);
        }

        dispatchEvent(event) {
            return Deno.core.ops.op_node_dispatch_event(this.handle || 0, event.type, event.bubbles, event.cancelable);
        }
    }

    class Node extends EventTarget {
        constructor(handle) { 
            super();
            this.handle = handle; 
        }
        get textContent() { return Deno.core.ops.op_node_get_text(this.handle); }
    }

    globalThis.Event = class Event {
        constructor(type, options = {}) {
            this.type = type;
            this.bubbles = !!options.bubbles;
            this.cancelable = !!options.cancelable;
        }
    };

    globalThis.Node = Node;
    globalThis.EventTarget = EventTarget;

    globalThis.location = {
        href: 'about:blank',
        protocol: 'about:',
        host: '',
        hostname: '',
        port: '',
        pathname: 'blank',
        search: '',
        hash: '',
        assign: (url) => { globalThis.location.href = url; },
        replace: (url) => { globalThis.location.href = url; },
        reload: () => {}
    };

    globalThis.navigator = {
        userAgent: 'Verantyx/1.0 (AI Sovereign)',
        language: 'en-US',
        onLine: true,
        cookieEnabled: true
    };

    globalThis.document = Object.assign(new EventTarget(), {
        get title() { return Deno.core.ops.op_document_get_title(); },
        querySelector: (s) => {
            const h = Deno.core.ops.op_document_query_selector(s);
            return h ? new Node(h) : null;
        },
        body: new Node(1),
        readyState: "complete",
        location: globalThis.location
    });

    globalThis.window = globalThis;
    globalThis.self = globalThis;
"#;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_handle_cache() {
        let mut cache = HandleCache::new();
        let h = cache.insert(NodeId(10));
        assert_eq!(cache.get(h), Some(NodeId(10)));
    }
}
