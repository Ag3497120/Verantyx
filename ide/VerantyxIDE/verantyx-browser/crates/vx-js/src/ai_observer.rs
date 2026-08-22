//! JavaScript Bytecode Analysis & AI Hook System
//!
//! Intercepts JavaScript execution to provide the AI agent with:
//! - Real-time DOM mutation notifications
//! - Fetch/XHR interception for AI-aware network monitoring
//! - Console log capture for debugging insight
//! - Promise resolution tracking
//! - Custom event routing to the AI command bus

use std::collections::HashMap;
use tokio::sync::mpsc;
use serde::{Serialize, Deserialize};

/// Events emitted from the JavaScript runtime to the AI Observer
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum JsAiEvent {
    /// DOM was mutated (new elements added/removed)
    DomMutation {
        mutation_type: DomMutationType,
        target_node_id: String,
        added_nodes: Vec<String>,
        removed_nodes: Vec<String>,
        attribute_name: Option<String>,
        old_value: Option<String>,
    },
    
    /// A fetch/XHR request was initiated
    NetworkRequest {
        id: u64,
        url: String,
        method: String,
        headers: HashMap<String, String>,
        body_size: Option<u64>,
        initiator: RequestInitiator,
    },
    
    /// A fetch/XHR response was received
    NetworkResponse {
        request_id: u64,
        url: String,
        status: u16,
        headers: HashMap<String, String>,
        body_preview: Option<String>, // First 1KB of body for AI inspection
    },
    
    /// console.log/warn/error was called
    ConsoleOutput {
        level: ConsoleLevel,
        message: String,
        stack_trace: Option<String>,
    },
    
    /// A JavaScript error occurred
    JsError {
        message: String,
        filename: Option<String>,
        line: Option<u32>,
        column: Option<u32>,
        stack: Option<String>,
    },
    
    /// A custom event was dispatched on the document
    CustomEvent {
        event_type: String,
        detail: Option<String>,
        target: String,
    },
    
    /// A form was submitted
    FormSubmit {
        action: String,
        method: String,
        data: HashMap<String, String>,
    },
    
    /// Navigation was triggered by JavaScript
    NavigationTriggered {
        url: String,
        push_state: bool,
    },
    
    /// A dialog was opened (alert/confirm/prompt)
    DialogOpened {
        dialog_type: DialogType,
        message: String,
    },
    
    /// Worker thread spawned
    WorkerSpawned {
        url: String,
        worker_type: WorkerType,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum DomMutationType {
    ChildList,
    Attributes,
    CharacterData,
    Subtree,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum RequestInitiator {
    Script,
    Parser,
    Preflight,
    Other,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum ConsoleLevel {
    Log,
    Info,
    Warn,
    Error,
    Debug,
    Table,
    Dir,
    Group,
    GroupEnd,
    Assert,
    Clear,
    Count,
    Time,
    TimeEnd,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum DialogType {
    Alert,
    Confirm,
    Prompt,
    BeforeUnload,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum WorkerType {
    DedicatedWorker,
    SharedWorker,
    ServiceWorker,
}

/// The JavaScript Runtime Observer — hooks into the V8/Deno runtime
pub struct JsRuntimeObserver {
    /// Channel to send events to the AI Brain
    event_tx: mpsc::UnboundedSender<JsAiEvent>,
    
    /// Monotonically increasing request ID counter
    request_counter: u64,
    
    /// Active network requests being tracked
    pending_requests: HashMap<u64, String>,
}

impl JsRuntimeObserver {
    pub fn new(event_tx: mpsc::UnboundedSender<JsAiEvent>) -> Self {
        Self {
            event_tx,
            request_counter: 1,
            pending_requests: HashMap::new(),
        }
    }
    
    /// Called by the runtime when fetch() is invoked  
    pub fn on_fetch_start(&mut self, url: &str, method: &str, headers: HashMap<String, String>) -> u64 {
        let id = self.request_counter;
        self.request_counter += 1;
        
        self.pending_requests.insert(id, url.to_string());
        
        let _ = self.event_tx.send(JsAiEvent::NetworkRequest {
            id,
            url: url.to_string(),
            method: method.to_string(),
            headers,
            body_size: None,
            initiator: RequestInitiator::Script,
        });
        
        id
    }
    
    /// Called by the runtime when a fetch() response is received
    pub fn on_fetch_response(
        &mut self,
        request_id: u64,
        status: u16,
        headers: HashMap<String, String>,
        body_preview: Option<String>
    ) {
        let url = self.pending_requests.remove(&request_id)
            .unwrap_or_default();
        
        let _ = self.event_tx.send(JsAiEvent::NetworkResponse {
            request_id,
            url,
            status,
            headers,
            body_preview,
        });
    }
    
    /// Called when a MutationObserver fires
    pub fn on_dom_mutation(
        &self,
        mutation_type: DomMutationType,
        target_node_id: &str,
        added_nodes: Vec<String>,
        removed_nodes: Vec<String>,
        attribute_name: Option<String>,
        old_value: Option<String>,
    ) {
        let _ = self.event_tx.send(JsAiEvent::DomMutation {
            mutation_type,
            target_node_id: target_node_id.to_string(),
            added_nodes,
            removed_nodes,
            attribute_name,
            old_value,
        });
    }
    
    /// Called when console.log/warn/error is used
    pub fn on_console(&self, level: ConsoleLevel, message: String) {
        let _ = self.event_tx.send(JsAiEvent::ConsoleOutput {
            level,
            message,
            stack_trace: None,
        });
    }
    
    /// Called when an uncaught JavaScript error occurs
    pub fn on_error(&self, message: String, filename: Option<String>, line: Option<u32>, col: Option<u32>, stack: Option<String>) {
        let _ = self.event_tx.send(JsAiEvent::JsError {
            message,
            filename,
            line,
            column: col,
            stack,
        });
    }
    
    /// Called when history.pushState or history.replaceState is called
    pub fn on_navigation(&self, url: &str, push_state: bool) {
        let _ = self.event_tx.send(JsAiEvent::NavigationTriggered {
            url: url.to_string(),
            push_state,
        });
    }
    
    /// Called when a form is submitted
    pub fn on_form_submit(&self, action: &str, method: &str, data: HashMap<String, String>) {
        let _ = self.event_tx.send(JsAiEvent::FormSubmit {
            action: action.to_string(),
            method: method.to_string(),
            data,
        });
    }
    
    /// Called when alert/confirm/prompt is called
    pub fn on_dialog(&self, dialog_type: DialogType, message: String) {
        let _ = self.event_tx.send(JsAiEvent::DialogOpened { dialog_type, message });
    }
}

/// AI-facing JavaScript injection API
/// Allows the AI to inject scripts, intercept handlers, etc.
pub struct JsAiInjector {
    /// Scripts queued to run at next tick
    pending_scripts: Vec<PendingScript>,
}

#[derive(Debug, Clone)]
pub struct PendingScript {
    pub code: String,
    pub execution_context: ExecutionContext,
    pub timeout_ms: Option<u64>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExecutionContext {
    MainFrame,
    IsolatedWorld,
    UserGesture,
}

impl JsAiInjector {
    pub fn new() -> Self {
        Self { pending_scripts: Vec::new() }
    }
    
    /// Inject a script to be run in the page context
    pub fn inject(&mut self, code: String, context: ExecutionContext) {
        self.pending_scripts.push(PendingScript {
            code,
            execution_context: context,
            timeout_ms: None,
        });
    }
    
    /// Inject a script with a timeout (prevents runaway AI-generated scripts)
    pub fn inject_with_timeout(&mut self, code: String, timeout_ms: u64) {
        self.pending_scripts.push(PendingScript {
            code,
            execution_context: ExecutionContext::IsolatedWorld,
            timeout_ms: Some(timeout_ms),
        });
    }
    
    /// Generate the scroll-to-element injection script
    pub fn scroll_to_element_script(selector: &str) -> String {
        format!(
            r#"
            (function() {{
                const el = document.querySelector('{}');
                if (el) {{
                    el.scrollIntoView({{behavior: 'smooth', block: 'center'}});
                    return {{success: true, found: true}};
                }}
                return {{success: false, found: false}};
            }})();
            "#,
            selector.replace('\'', "\\'")
        )
    }
    
    /// Generate the fill form injection script
    pub fn fill_form_script(selector: &str, value: &str) -> String {
        format!(
            r#"
            (function() {{
                const el = document.querySelector('{}');
                if (el) {{
                    el.focus();
                    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value'
                    )?.set;
                    if (nativeInputValueSetter) {{
                        nativeInputValueSetter.call(el, '{}');
                    }} else {{
                        el.value = '{}';
                    }}
                    el.dispatchEvent(new Event('input', {{bubbles: true}}));
                    el.dispatchEvent(new Event('change', {{bubbles: true}}));
                    return {{success: true}};
                }}
                return {{success: false}};
            }})();
            "#,
            selector.replace('\'', "\\'"),
            value.replace('\'', "\\'"),
            value.replace('\'', "\\'"),
        )
    }
    
    /// Extract structured data from the page using the AI-formatted schema
    pub fn extract_page_data_script() -> String {
        r#"
        (function() {
            function getInteractiveElements() {
                const interactiveSelectors = 'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"]), [role="button"], [role="link"], [role="menuitem"]';
                return Array.from(document.querySelectorAll(interactiveSelectors)).map((el, idx) => {
                    const rect = el.getBoundingClientRect();
                    return {
                        ai_id: idx + 1,
                        tag: el.tagName.toLowerCase(),
                        type: el.type || null,
                        text: (el.textContent || el.value || el.placeholder || el.alt || '').trim().slice(0, 200),
                        href: el.href || null,
                        placeholder: el.placeholder || null,
                        value: el.value || null,
                        name: el.name || null,
                        role: el.getAttribute('role') || null,
                        aria_label: el.getAttribute('aria-label') || null,
                        disabled: el.disabled || false,
                        visible: rect.width > 0 && rect.height > 0,
                        bounds: [rect.x, rect.y, rect.width, rect.height],
                    };
                });
            }
            
            return {
                url: window.location.href,
                title: document.title,
                interactive: getInteractiveElements(),
                meta: {
                    description: document.querySelector('meta[name="description"]')?.content,
                    canonical: document.querySelector('link[rel="canonical"]')?.href,
                    og_title: document.querySelector('meta[property="og:title"]')?.content,
                },
            };
        })();
        "#.to_string()
    }
}
