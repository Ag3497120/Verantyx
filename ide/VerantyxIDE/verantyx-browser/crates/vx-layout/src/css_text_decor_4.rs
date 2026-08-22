//! CSS Text Decoration Module Level 4 — W3C CSS Text Decor 4
//!
//! Implements advanced underline and visual stroking typography rules:
//!   - text-decoration-skip-ink (§ 2): Skipping layout underlines where ascender/descender glyphs cross
//!   - text-decoration-thickness (§ 3): Dynamic or fixed stroke thickness (auto, from-font, length)
//!   - text-underline-offset (§ 4): Controlling the gap between the baseline and the stroke
//!   - text-decoration-line / color / style integration
//!   - Font-metric driven sizing (`from-font` accessing OpenType underline metrics)
//!   - AI-facing: Text decoration geometric mapping and ink-skip simulation metrics

use std::collections::HashMap;

/// Configuration defining how underlines intersect with descending letters (g, j, p, q, y) (§ 2)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SkipInk { Auto, None, All } // `All` is future-oriented / Chinese typography

/// The stroke thickness of the decoration geometry (§ 3)
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum DecorationThickness { Auto, FromFont, Length(f64) }

/// Computed typographical decoration rules for layout rasterization
#[derive(Debug, Clone)]
pub struct TextDecorationConfig {
    pub skip_ink: SkipInk,
    pub thickness: DecorationThickness,
    pub underline_offset_auto: bool,
    pub underline_offset_fixed: f64,
}

/// The global CSS Text Decoration engine handling metrics before Skia rasterization
pub struct CssTextDecorEngine {
    pub node_decorations: HashMap<u64, TextDecorationConfig>,
    pub total_ink_skips_calculated: u64, // Tracking geometrical intersections
}

impl CssTextDecorEngine {
    pub fn new() -> Self {
        Self {
            node_decorations: HashMap::new(),
            total_ink_skips_calculated: 0,
        }
    }

    pub fn set_decoration_config(&mut self, node_id: u64, config: TextDecorationConfig) {
        self.node_decorations.insert(node_id, config);
    }

    /// layout passes font metric geometry to determine final pixel thickness (§ 3)
    pub fn resolve_thickness(&self, node_id: u64, font_recommended_thickness: f64) -> f64 {
        if let Some(config) = self.node_decorations.get(&node_id) {
            match config.thickness {
                DecorationThickness::Length(v) => return v,
                DecorationThickness::FromFont => return font_recommended_thickness,
                DecorationThickness::Auto => {
                    // Typical browser behavior: ~8% of the font size or font_recommended
                    return font_recommended_thickness;
                }
            }
        }
        // Native fallback fallback
        1.0 
    }

    /// Evaluates if geometry calculations are needed to carve rectangles out of the underline (§ 2)
    pub fn evaluate_skip_ink(&mut self, node_id: u64, contains_descenders: bool) -> bool {
        if let Some(config) = self.node_decorations.get(&node_id) {
            if config.skip_ink == SkipInk::Auto && contains_descenders {
                self.total_ink_skips_calculated += 1;
                return true; // Skia will need to clip the stroke Path around the glyphs
            }
        }
        false
    }

    /// AI-facing Text Decoration geometrical constraint summary
    pub fn ai_text_decor_summary(&self, node_id: u64) -> String {
        if let Some(config) = self.node_decorations.get(&node_id) {
            let offset_str = if config.underline_offset_auto { "auto".into() } else { format!("{:.1}px", config.underline_offset_fixed) };
            format!("〰️ CSS Text Decor 4 (Node #{}): Skip-Ink: {:?} | Thickness: {:?} | Offset: {}", 
                node_id, config.skip_ink, config.thickness, offset_str)
        } else {
            format!("Node #{} uses default baseline decoration rendering", node_id)
        }
    }
}
