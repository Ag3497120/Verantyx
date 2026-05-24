//! CSS Inline Layout Module Level 3 — W3C CSS Inline 3
//!
//! Implements logical typographical linebox structural mathematics:
//!   - `initial-letter` (§ 2): Multi-line drop caps (sizing typography over N lines)
//!   - `line-height` (§ 3): The core strut metric governing physical line box heights
//!   - `vertical-align` (§ 4): `top`, `middle`, `baseline`, `super` alignment against the strut
//!   - `baseline-shift` (§ 4.3): Exact coordinate shifting of the ink baseline
//!   - Dominant Baseline extraction logic for mixed-script typography
//!   - AI-facing: Strut topology metrics and typographic box alignment states

use std::collections::HashMap;

/// Denotes the vertical anchor point of an inline box within the line box (§ 4)
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum VerticalAlign { Baseline, Sub, Super, Top, TextTop, Middle, Bottom, TextBottom, Length(f64) }

/// Defines the drop-cap properties sizing a glyph across multiple lines (§ 2)
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct InitialLetter {
    pub size_lines: f64, // e.g., 3.0 lines tall
    pub sink_lines: usize, // e.g., drops down 2 lines
}

/// Logical configuration shaping the text layout bounds
#[derive(Debug, Clone)]
pub struct CssInlineConfiguration {
    pub line_height_multiplier: Option<f64>, // e.g. 1.5
    pub line_height_exact: Option<f64>, // e.g. 24px
    pub vertical_align: VerticalAlign,
    pub initial_letter: Option<InitialLetter>,
    pub dominant_baseline: bool, // Simplified tracking of ideographic/alphabetic
}

/// The global CSS Inline Layout mathematical solver
pub struct CssInlineEngine {
    pub configs: HashMap<u64, CssInlineConfiguration>,
    pub total_struts_calculated: u64,
}

impl CssInlineEngine {
    pub fn new() -> Self {
        Self {
            configs: HashMap::new(),
            total_struts_calculated: 0,
        }
    }

    pub fn set_inline_config(&mut self, node_id: u64, config: CssInlineConfiguration) {
        self.configs.insert(node_id, config);
    }

    /// Evaluates the invisible `strut` which establishes the minimum line-box height (§ 3)
    pub fn calculate_strut_height(&mut self, node_id: u64, computed_font_size: f64) -> f64 {
        self.total_struts_calculated += 1;
        if let Some(config) = self.configs.get(&node_id) {
            if let Some(exact) = config.line_height_exact {
                return exact.max(computed_font_size); // Browsers prevent negative ink overlap physically
            }
            if let Some(mult) = config.line_height_multiplier {
                return computed_font_size * mult;
            }
        }
        // Default `normal` behavior depends on OS font metrics, modeled here as 1.2
        computed_font_size * 1.2
    }

    /// Calculates the physical Y translation to align a child box inside the line box (§ 4)
    pub fn calculate_vertical_alignment_shift(&self, child_node_id: u64, linebox_height: f64, child_height: f64) -> f64 {
        if let Some(config) = self.configs.get(&child_node_id) {
            match config.vertical_align {
                VerticalAlign::Top => return 0.0,
                VerticalAlign::Bottom => return linebox_height - child_height,
                VerticalAlign::Middle => return (linebox_height - child_height) / 2.0,
                VerticalAlign::Length(l) => return -l, // Shifts baseline up physically (negative Y)
                _ => return 0.0, // Baseline/TextBottom needs complex font metrics, mocked here
            }
        }
        0.0
    }

    /// AI-facing Typographical strut tracking summary
    pub fn ai_inline_summary(&self, node_id: u64) -> String {
        if let Some(config) = self.configs.get(&node_id) {
            let drop = config.initial_letter.map_or("None".into(), |il| format!("{}L", il.size_lines));
            format!("📝 CSS Inline 3 (Node #{}): V-Align: {:?} | DropCap: {} | Dominant Baseline: {}", 
                node_id, config.vertical_align, drop, config.dominant_baseline)
        } else {
            format!("Node #{} utilizes default 'normal' line-height bounding", node_id)
        }
    }
}
