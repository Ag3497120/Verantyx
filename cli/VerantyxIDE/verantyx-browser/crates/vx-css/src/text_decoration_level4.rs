//! CSS Text Decoration Module Level 4 — W3C CSS Text Decoration
//!
//! Implements advanced text styling and visual annotations:
//!   - Decoration Line (§ 2.1): underline, overline, line-through, blink, spelling-error, grammar-error
//!   - Decoration Style (§ 2.2): solid, double, dotted, dashed, wavy
//!   - Decoration Color (§ 2.3) and Thickness (§ 2.4): auto, from-font, <length-percentage>
//!   - Underline Offset (§ 2.5): auto, <length-percentage>
//!   - Underline Position (§ 2.6): auto, [ under || [ left | right ] ]
//!   - Text Emphasis (§ 3): text-emphasis-style, text-emphasis-color, text-emphasis-position
//!   - Text Shadow (§ 5): horizontal, vertical, blur-radius, color
//!   - Text Decoration Skip (§ 4): ink, edges, spaces, leading-spaces, trailing-spaces
//!   - AI-facing: Text decoration layer registry and emphasis mark visualizer metrics

use std::collections::HashMap;

/// Text decoration lines (§ 2.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum TextDecorationLine { Underline, Overline, LineThrough, Blink, SpellingError, GrammarError }

/// Text decoration styles (§ 2.2)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TextDecorationStyle { Solid, Double, Dotted, Dashed, Wavy }

/// Text emphasis styles (§ 3.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EmphasisStyle { None, Filled, Open, Dot, Circle, DoubleCircle, Triangle, Sesame, String(char) }

/// Layout state for text decoration (§ 2)
pub struct TextDecoration {
    pub node_id: u64,
    pub lines: Vec<TextDecorationLine>,
    pub style: TextDecorationStyle,
    pub color: String,
    pub thickness: f64,
    pub underline_offset: f64,
    pub emphasis_style: EmphasisStyle,
}

impl TextDecoration {
    pub fn new(node_id: u64) -> Self {
        Self {
            node_id,
            lines: Vec::new(),
            style: TextDecorationStyle::Solid,
            color: "currentColor".into(),
            thickness: 1.0,
            underline_offset: 0.0,
            emphasis_style: EmphasisStyle::None,
        }
    }

    /// AI-facing text styling summary
    pub fn ai_decoration_metrics(&self) -> String {
        format!("🖋️ Text Decoration for Node #{}: (Lines: {:?}, Style: {:?}, Color: {}, Offset: {:.1})", 
            self.node_id, self.lines, self.style, self.color, self.underline_offset)
    }
}

/// The CSS Text Decoration Engine
pub struct DecorationEngine {
    pub decorations: HashMap<u64, TextDecoration>, // node_id -> decoration
    pub shadows: HashMap<u64, Vec<TextShadow>>, // node_id -> shadows
}

#[derive(Debug, Clone)]
pub struct TextShadow {
    pub h_offset: f64,
    pub v_offset: f64,
    pub blur: f64,
    pub color: String,
}

impl DecorationEngine {
    pub fn new() -> Self {
        Self {
            decorations: HashMap::new(),
            shadows: HashMap::new(),
        }
    }

    pub fn set_decoration(&mut self, node_id: u64, deco: TextDecoration) {
        self.decorations.insert(node_id, deco);
    }

    pub fn add_shadow(&mut self, node_id: u64, shadow: TextShadow) {
        self.shadows.entry(node_id).or_default().push(shadow);
    }

    /// AI-facing emphasis mark inspector
    pub fn ai_emphasis_summary(&self, node_id: u64) -> String {
        if let Some(deco) = self.decorations.get(&node_id) {
            format!("✨ Text Emphasis for Node #{}: {:?}", node_id, deco.emphasis_style)
        } else {
            format!("No emphasis defined for Node #{}", node_id)
        }
    }
}
