//! CSS Pseudo-Elements Module Level 4 — W3C CSS Pseudo 4
//!
//! Implements advanced typographical and grammatical pseudo-element targeting:
//!   - `::target-text` (§ 3): Styling text highlighted by a scroll-to-text fragment URL
//!   - `::spelling-error` (§ 4.1): Native OS spellcheck squiggly line styling overrides
//!   - `::grammar-error` (§ 4.2): Native OS grammar check overrides
//!   - Highlight Pseudo-element cascade inheritance rules (unlike normal elements)
//!   - Text decoration integration (replaces default native underlines)
//!   - AI-facing: Text fragment and proofing visualizer mapping

use std::collections::HashMap;

/// Types of Text Proofing / Selection highlights supported (§ 3, 4)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HighlightPseudoType { TargetText, SpellingError, GrammarError, Selection }

/// State mapping indicating active text segments caught by a Highlight Pseudo-element
#[derive(Debug, Clone)]
pub struct ActiveTextHighlight {
    pub pseudo_type: HighlightPseudoType,
    pub start_offset: usize,
    pub end_offset: usize,
    pub applied_color: Option<String>,
    pub applied_text_decoration: Option<String>,
}

/// The global CSS Pseudo Elements Level 4 Engine
pub struct CssPseudo4Engine {
    // node_id -> active highlight segments
    pub active_highlights: HashMap<u64, Vec<ActiveTextHighlight>>,
}

impl CssPseudo4Engine {
    pub fn new() -> Self {
        Self { active_highlights: HashMap::new() }
    }

    /// Registers a text fragment triggered by the URL e.g. `#:~:text=foo` (§ 3)
    pub fn trigger_target_text(&mut self, node_id: u64, start: usize, end: usize, style_color: Option<&str>) {
        let entry = self.active_highlights.entry(node_id).or_insert(Vec::new());
        entry.push(ActiveTextHighlight {
            pseudo_type: HighlightPseudoType::TargetText,
            start_offset: start,
            end_offset: end,
            applied_color: style_color.map(|s| s.to_string()),
            applied_text_decoration: Some("solid".to_string()), // Default browser style
        });
    }

    /// Invoked by native OS spellchecker integration bridging back into CSS (§ 4)
    pub fn trigger_proofing_error(&mut self, node_id: u64, is_grammar: bool, start: usize, end: usize, css_override: Option<&str>) {
        let entry = self.active_highlights.entry(node_id).or_insert(Vec::new());
        entry.push(ActiveTextHighlight {
            pseudo_type: if is_grammar { HighlightPseudoType::GrammarError } else { HighlightPseudoType::SpellingError },
            start_offset: start,
            end_offset: end,
            applied_color: None, // Proofing pseudo normally defaults to decoration color
            applied_text_decoration: css_override.map(|s| s.to_string()).or(Some("wavy red".into())), 
        });
    }

    /// AI-facing Highlight Pseudo topological mapping
    pub fn ai_pseudo4_summary(&self, node_id: u64) -> String {
        if let Some(highlights) = self.active_highlights.get(&node_id) {
            let mut summary = format!("🖍️ CSS Pseudo Level 4 (Node #{}): {} Active Highlight Segments", node_id, highlights.len());
            for h in highlights {
                let color_str = h.applied_color.as_deref().unwrap_or("auto");
                let doc_str = h.applied_text_decoration.as_deref().unwrap_or("none");
                summary.push_str(&format!("\n  - [{:?}] Chars {} to {} | Color: {}, Decor: {}", 
                    h.pseudo_type, h.start_offset, h.end_offset, color_str, doc_str));
            }
            summary
        } else {
            format!("Node #{} has no active text fragment or proofing highlights", node_id)
        }
    }
}
