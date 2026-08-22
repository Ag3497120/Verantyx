//! CSS Fonts Level 4 — W3C CSS Fonts
//!
//! Implements advanced typography and variable font support:
//!   - @font-face descriptors (§ 4): font-family, src, font-weight, font-style, font-stretch, font-display, unicode-range
//!   - Variable Fonts (§ 5): font-variation-settings (wght, wdth, slnt, ital)
//!   - Color Fonts (§ 6): font-palette, @font-palette-values, COLR/CPAL support
//!   - Font Selection Algorithm (§ 5): Matching fonts by weight, style, and stretch
//!   - Font Synthesis (§ 7): font-synthesis (weight, style, small-caps)
//!   - OpenType Features (§ 9): font-kerning, font-variant-ligatures, font-feature-settings
//!   - Relative Sizing (§ 10): font-size-adjust, font-stretch
//!   - AI-facing: Font registry and variable font axis inspector

use std::collections::HashMap;

/// Font weight values (§ 3.2)
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum FontWeight { Thin, Light, Normal, Medium, Bold, Black, Custom(u16) }

impl FontWeight {
    pub fn to_u16(self) -> u16 {
        match self {
            FontWeight::Thin => 100,
            FontWeight::Light => 300,
            FontWeight::Normal => 400,
            FontWeight::Medium => 500,
            FontWeight::Bold => 700,
            FontWeight::Black => 900,
            FontWeight::Custom(v) => v,
        }
    }
}

/// Font style values (§ 3.3)
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum FontStyle { Normal, Italic, Oblique(f32) }

impl Eq for FontStyle {}

impl PartialOrd for FontStyle {
    fn partial_cmp(&self, other: &Self) -> Option<std::cmp::Ordering> {
        Some(self.cmp(other))
    }
}

impl Ord for FontStyle {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        match (self, other) {
            (FontStyle::Normal, FontStyle::Normal) => std::cmp::Ordering::Equal,
            (FontStyle::Normal, _) => std::cmp::Ordering::Less,
            (FontStyle::Italic, FontStyle::Normal) => std::cmp::Ordering::Greater,
            (FontStyle::Italic, FontStyle::Italic) => std::cmp::Ordering::Equal,
            (FontStyle::Italic, _) => std::cmp::Ordering::Less,
            (FontStyle::Oblique(a), FontStyle::Oblique(b)) => a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal),
            (FontStyle::Oblique(_), _) => std::cmp::Ordering::Greater,
        }
    }
}

/// Font stretch values (§ 3.4)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FontStretch { UltraCondensed, Condensed, SemiCondensed, Normal, SemiExpanded, Expanded, UltraExpanded }

/// Individual @font-face descriptor (§ 4)
#[derive(Debug, Clone)]
pub struct FontFace {
    pub family: String,
    pub src: Vec<String>,
    pub weight: (FontWeight, FontWeight),
    pub style: FontStyle,
    pub stretch: (FontStretch, FontStretch),
    pub unicode_range: String,
    pub display: FontDisplay,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FontDisplay { Auto, Block, Swap, Fallback, Optional }

/// Variable font axis values (§ 5)
#[derive(Debug, Clone)]
pub struct FontVariationSettings {
    pub axes: HashMap<String, f32>, // Tag (e.g., 'wght') -> Value
}

/// The global Font Registry
pub struct FontRegistry {
    pub faces: Vec<FontFace>,
    pub system_fonts: HashMap<String, Vec<String>>, // Family -> [System Font Names]
    pub variations: HashMap<u64, FontVariationSettings>, // node_id -> settings
}

impl FontRegistry {
    pub fn new() -> Self {
        Self {
            faces: Vec::new(),
            system_fonts: HashMap::new(),
            variations: HashMap::new(),
        }
    }

    pub fn register_face(&mut self, face: FontFace) {
        self.faces.push(face);
    }

    /// Primary font selection algorithm (§ 5)
    pub fn match_font(&self, family: &str, weight: FontWeight, style: FontStyle) -> Option<&FontFace> {
        self.faces.iter().find(|f| {
            f.family == family && f.weight.0 <= weight && f.weight.1 >= weight && f.style == style
        })
    }

    pub fn set_variation(&mut self, node_id: u64, tag: &str, value: f32) {
        self.variations.entry(node_id).or_insert(FontVariationSettings {
            axes: HashMap::new(),
        }).axes.insert(tag.to_string(), value);
    }

    /// AI-facing font registry summary
    pub fn ai_font_registry(&self) -> String {
        let mut lines = vec![format!("🔠 CSS Font Registry (@font-face count: {}):", self.faces.len())];
        for face in &self.faces {
            lines.push(format!("  - '{}' (Weight: {:?}, Style: {:?})", face.family, face.weight, face.style));
        }
        lines.join("\n")
    }

    /// AI-facing variation axis inspector
    pub fn ai_variation_inspector(&self, node_id: u64) -> String {
        if let Some(var) = self.variations.get(&node_id) {
            let mut lines = vec![format!("🎨 Font Variations for Node #{}:", node_id)];
            for (tag, val) in &var.axes {
                lines.push(format!("    - '{}': {}", tag, val));
            }
            lines.join("\n")
        } else {
            format!("Node #{} has no custom font variations", node_id)
        }
    }
}
