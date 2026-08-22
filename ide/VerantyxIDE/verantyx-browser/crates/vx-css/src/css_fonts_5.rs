//! CSS Fonts Module Level 5 — W3C CSS Fonts 5
//!
//! Implements advanced font palette control and metric adjustments:
//!   - font-size-adjust (§ 2): Standardizing dimensions between fallback fonts (`ex`, `cap`, `ch`, `ic`)
//!   - font-palette (§ 3): Selecting color palettes built into CPAL/COLR/SVG OpenType tables
//!   - @font-palette-values (§ 3.1): Declaring custom palettes that mix colors
//!   - Multi-Color Typeography: Overriding specific indices in an emoji/variable font palette
//!   - AI-facing: Font geometric fallback metrics and color-font palette visualizer

use std::collections::HashMap;

/// CSS `font-size-adjust` metric to normalize (§ 2.2)
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum FontSizeAdjustMetric { ExHeight, CapHeight, ChWidth, IcWidth }

#[derive(Debug, Clone, PartialEq)]
pub struct FontSizeAdjust {
    pub metric: FontSizeAdjustMetric,
    pub aspect_value: Option<f64>, // e.g. 0.5. None means `from-font`.
}

/// User overriden palette defined via `@font-palette-values` (§ 3.1)
#[derive(Debug, Clone)]
pub struct CustomFontPalette {
    pub base_palette: Option<usize>, // light, dark, or generic numerical index
    pub overridden_colors: HashMap<usize, String>, // Color Index -> CSS Color
}

/// The global CSS Fonts Level 5 Engine
pub struct CSSFonts5Engine {
    pub custom_palettes: HashMap<String, CustomFontPalette>, // @font-palette-values name -> config
    pub node_adjustments: HashMap<u64, FontSizeAdjust>,
    pub node_palettes: HashMap<u64, String>, // node_id -> applied palette name
}

impl CSSFonts5Engine {
    pub fn new() -> Self {
        Self {
            custom_palettes: HashMap::new(),
            node_adjustments: HashMap::new(),
            node_palettes: HashMap::new(),
        }
    }

    /// Registers a `@font-palette-values` descriptor from a stylesheet
    pub fn define_custom_palette(&mut self, name: &str, palette: CustomFontPalette) {
        self.custom_palettes.insert(name.to_string(), palette);
    }

    /// Calculates a normalized font size to match typographical consistency (§ 2.3)
    pub fn compute_adjusted_font_size(&self, node_id: u64, base_font_size: f64, actual_font_aspect: f64) -> f64 {
        if let Some(adjust) = self.node_adjustments.get(&node_id) {
            // E.g., font-size = base_font_size * (desired_ex / actual_ex)
            if let Some(desired_aspect) = adjust.aspect_value {
                return base_font_size * (desired_aspect / actual_font_aspect);
            }
        }
        base_font_size
    }

    /// Resolves the specific color layers for a COLR/CPAL font rendering pass (§ 3)
    pub fn resolve_font_colors(&self, node_id: u64) -> Option<&CustomFontPalette> {
        if let Some(palette_name) = self.node_palettes.get(&node_id) {
            return self.custom_palettes.get(palette_name);
        }
        None
    }

    /// AI-facing CSS Fonts Level 5 topology
    pub fn ai_fonts5_summary(&self, node_id: u64) -> String {
        let adjust_info = match self.node_adjustments.get(&node_id) {
            Some(a) => format!("{:?} -> {:?}", a.metric, a.aspect_value),
            None => "none".into(),
        };
        let palette_info = self.node_palettes.get(&node_id).map_or("normal", |s| s.as_str());

        format!("🎨 CSS Fonts Level 5 (Node #{}): [Size-Adjust: {}] [Palette: {}]", 
            node_id, adjust_info, palette_info)
    }
}
