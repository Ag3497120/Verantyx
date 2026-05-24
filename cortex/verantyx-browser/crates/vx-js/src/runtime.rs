//! JavaScript Runtime — V8 (deno_core) wrapper
//!
//! Manages the JS execution context and provides:
//! - Script evaluation via V8
//! - DOM API injection
//! - Console output capture

use anyhow::Result;
use deno_core::{op2, extension, RuntimeOptions, OpState};
use std::sync::{Arc, Mutex};

/// Captured console output
#[derive(Debug, Clone)]
pub struct ConsoleMessage {
    pub level: ConsoleLevel,
    pub message: String,
}

#[derive(Debug, Clone, PartialEq)]
pub enum ConsoleLevel {
    Log, Warn, Error, Info, Debug,
}

#[op2(fast)]
pub fn op_console_log(state: &mut OpState, #[string] msg: String, #[string] level: String) {
    let console_output = state.borrow::<Arc<Mutex<Vec<ConsoleMessage>>>>().clone();
    let lvl = match level.as_str() {
        "warn" => ConsoleLevel::Warn,
        "error" => ConsoleLevel::Error,
        _ => ConsoleLevel::Log,
    };
    console_output.lock().unwrap().push(ConsoleMessage {
        level: lvl,
        message: msg,
    });
}

extension!(
    vx_browser,
    ops = [op_console_log],
);

/// JavaScript runtime powered by V8
pub struct VxRuntime {
    inner: deno_core::JsRuntime,
    console_output: Arc<Mutex<Vec<ConsoleMessage>>>,
}

impl VxRuntime {
    /// Create a new JS runtime with V8
    pub fn new() -> Result<Self> {
        let console_output = Arc::new(Mutex::new(Vec::new()));
        let console_output_copy = console_output.clone();

        let handle_cache = Arc::new(Mutex::new(crate::dom_api::HandleCache::new()));
        let handle_cache_copy = handle_cache.clone();
        
        let mut inner = deno_core::JsRuntime::new(RuntimeOptions {
            extensions: vec![
                vx_browser::init_ops(),
                crate::dom_api::init_dom_ops(),
                crate::fetch::vx_fetch::init_ops(),
            ],
            ..Default::default()
        });

        // Inject shared state
        inner.op_state().borrow_mut().put(console_output_copy);
        inner.op_state().borrow_mut().put(handle_cache_copy);
        inner.op_state().borrow_mut().put(vx_net::fetch::FetchClient::new().unwrap());

        // Bootstrap core APIs
        inner.execute_script("<bootstrap>", r#"
            globalThis.console = {
                log: (...args) => Deno.core.ops.op_console_log(args.join(" "), "log"),
                warn: (...args) => Deno.core.ops.op_console_log(args.join(" "), "warn"),
                error: (...args) => Deno.core.ops.op_console_log(args.join(" "), "error"),
            };
            globalThis.window = globalThis;
        "#.to_string())?;

        // Inject DOM API bootstrap
        inner.execute_script("<dom_bootstrap>", crate::dom_api::DOM_BOOTSTRAP.to_string())?;

        Ok(Self { inner, console_output })
    }

    /// Execute JavaScript code
    pub fn eval(&mut self, code: &str) -> Result<String> {
        let val = self.inner.execute_script("<eval>", code.to_string())?;
        // Simple conversion for now
        Ok(format!("{:?}", val))
    }

    /// Execute pending microtasks
    pub async fn run_event_loop(&mut self) -> Result<()> {
        self.inner.run_event_loop(Default::default()).await?;
        Ok(())
    }

    pub fn get_console_output(&self) -> Vec<ConsoleMessage> {
        self.console_output.lock().unwrap().clone()
    }

    pub fn clear_console(&self) {
        self.console_output.lock().unwrap().clear();
    }

    pub fn set_location(&mut self, url: &str) -> Result<()> {
        let code = format!("globalThis.location.href = '{}';", url);
        let _ = self.inner.execute_script("<set_location>", code)?;
        Ok(())
    }

    /// Load and execute scripts from HTML (Phase 8 Integration)
    pub async fn load_scripts_from_html(&mut self, html: &str, base_url: &str) -> Result<()> {
        use crate::module_loader::{extract_script_tags, classify_scripts, ScriptFetcher};
        
        let tags = extract_script_tags(html);
        let (immediate, deferred, _async_scripts) = classify_scripts(tags);
        let fetcher = ScriptFetcher::new().with_base_url(base_url);

        // 1. Execute immediate scripts
        for tag in immediate {
            if let Some(src) = &tag.src {
                if let Ok(code) = fetcher.fetch(src).await {
                    let _ = self.inner.execute_script(src.clone().leak(), code);
                }
            } else if let Some(code) = &tag.inline_content {
                let _ = self.inner.execute_script("<inline>", code.clone());
            }
        }

        // 2. Execute deferred scripts
        for tag in deferred {
            if let Some(src) = &tag.src {
                if let Ok(code) = fetcher.fetch(src).await {
                    let _ = self.inner.execute_script(src.clone().leak(), code);
                }
            } else if let Some(code) = &tag.inline_content {
                let _ = self.inner.execute_script("<inline_deferred>", code.clone());
            }
        }

        // Process any microtasks
        self.run_event_loop().await?;

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_basic_v8_eval() {
        let mut rt = VxRuntime::new().unwrap();
        let result = rt.eval("1 + 2").unwrap();
        assert!(result.contains("3"));
    }

    #[tokio::test]
    async fn test_v8_console_log() {
        let mut rt = VxRuntime::new().unwrap();
        rt.eval("console.log('test V8')").unwrap();
        rt.run_event_loop().await.unwrap();
        let output = rt.get_console_output();
        assert_eq!(output.len(), 1);
        assert_eq!(output[0].message, "test V8");
    }
}
