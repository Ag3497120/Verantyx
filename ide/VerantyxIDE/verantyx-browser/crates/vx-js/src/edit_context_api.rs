//! EditContext API — W3C EditContext
//!
//! Implements strict OS-level Input Method Editor (IME) decoupled geometries:
//!   - `EditContext` class (§ 2): Constructing non-DOM text abstraction targets
//!   - `updateControlBounds()` / `updateSelectionBounds()` (§ 4): IME floating window positioning physics
//!   - `textupdate` events: Raw OS character injection streams bridging the composition loop
//!   - AI-facing: Virtual Keyboard and IME Spatial Abstraction extractors

use std::collections::HashMap;

#[derive(Debug, Clone)]
pub struct ImeGeometricBounds {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}

/// Abstract representation of the decoupled text buffer managed by JS natively
#[derive(Debug, Clone)]
pub struct EditContextBuffer {
    pub text: String,
    pub selection_start: u32,
    pub selection_end: u32,
    pub control_bounds: Option<ImeGeometricBounds>,
    pub selection_bounds: Option<ImeGeometricBounds>,
}

/// The global Constraint Resolver governing decoupled OS-to-Canvas text input bridges
pub struct EditContextEngine {
    // Document ID -> Edit Context ID -> Buffer State
    pub active_contexts: HashMap<u64, HashMap<u64, EditContextBuffer>>,
    pub total_ime_compositions_yielded: u64,
}

impl EditContextEngine {
    pub fn new() -> Self {
        Self {
            active_contexts: HashMap::new(),
            total_ime_compositions_yielded: 0,
        }
    }

    /// JS execution: `const ctx = new EditContext({ text: 'initial' });`
    pub fn allocate_edit_context(&mut self, document_id: u64, initial_text: &str) -> u64 {
        let contexts = self.active_contexts.entry(document_id).or_default();
        let new_id = contexts.len() as u64 + 1;
        
        contexts.insert(new_id, EditContextBuffer {
            text: initial_text.to_string(),
            selection_start: 0,
            selection_end: 0,
            control_bounds: None,
            selection_bounds: None,
        });
        
        new_id
    }

    /// JS execution: `ctx.updateControlBounds(new DOMRect(x,y,w,h));`
    /// Crucial for moving the native OS Chinese/Japanese IME suggestion window over a `<canvas>` element.
    pub fn sync_os_ime_position(&mut self, document_id: u64, ctx_id: u64, bounds: ImeGeometricBounds) -> Result<(), String> {
        let contexts = self.active_contexts.get_mut(&document_id)
            .ok_or("Invalid Context")?;
            
        let ctx = contexts.get_mut(&ctx_id)
            .ok_or("EditContext Not Found")?;
            
        ctx.control_bounds = Some(bounds);
        Ok(())
    }

    /// Incoming OS Event: The user types a character into the native IME buffer
    pub fn inject_os_text_mutation(&mut self, document_id: u64, ctx_id: u64, new_text: &str) -> Result<(), String> {
        if let Some(contexts) = self.active_contexts.get_mut(&document_id) {
            if let Some(ctx) = contexts.get_mut(&ctx_id) {
                // Simulates dispatching the `textupdate` Event
                ctx.text = new_text.to_string(); // Simplified replacement
                self.total_ime_compositions_yielded += 1;
                return Ok(());
            }
        }
        Err("Context Lost".into())
    }

    /// AI-facing Decoupled Text Vectors
    /// Allows the AI to understand that an HTML Canvas is actually operating as a text editor via EditContext.
    pub fn ai_edit_context_summary(&self, document_id: u64) -> String {
        if let Some(contexts) = self.active_contexts.get(&document_id) {
            format!("⌨️ EditContext API (Doc #{}): Active Spatial Buffers: {} | Global IME Composition Yields: {}", 
                document_id, contexts.len(), self.total_ime_compositions_yielded)
        } else {
            format!("Doc #{} utilizes standard DOM node contenteditable/input elements for composition buffers", document_id)
        }
    }
}
