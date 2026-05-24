//! CSS Sizing Module Level 4 — W3C CSS Sizing 4
//!
//! Implements complex dimension bounding logic augmenting intrinsic flow algorithms:
//!   - `aspect-ratio` (§ 3): Creating geometric ratios bounding width/height evaluations
//!   - `contain-intrinsic-size` (§ 4): Bounding limits when elements are skipped by `content-visibility`
//!   - `max-content` / `min-content` mappings interacting with fixed aspect constraints
//!   - AI-facing: CSS Layout Extrinsic constraint modifications

use std::collections::HashMap;

/// Defines the declared aspect ratio geometric projection (§ 3)
#[derive(Debug, Clone, Copy)]
pub struct AspectRatioGeometry {
    pub ratio_width: f64,
    pub ratio_height: f64,
}

/// The overarching Configuration extracted by vx-css and handed to vx-layout
#[derive(Debug, Clone)]
pub struct CssSizing4Configuration {
    pub aspect_ratio: Option<AspectRatioGeometry>,
    pub contain_intrinsic_width: Option<f64>,
    pub contain_intrinsic_height: Option<f64>,
}

impl Default for CssSizing4Configuration {
    fn default() -> Self {
        Self {
            aspect_ratio: None,
            contain_intrinsic_width: None,
            contain_intrinsic_height: None,
        }
    }
}

/// The global Constraint Resolver governing physical layout edge-cases
pub struct CssSizing4Engine {
    pub active_sizing_rules: HashMap<u64, CssSizing4Configuration>,
    pub total_aspect_ratios_enforced: u64,
}

impl CssSizing4Engine {
    pub fn new() -> Self {
        Self {
            active_sizing_rules: HashMap::new(),
            total_aspect_ratios_enforced: 0,
        }
    }

    pub fn set_sizing_config(&mut self, node_id: u64, config: CssSizing4Configuration) {
        self.active_sizing_rules.insert(node_id, config);
    }

    /// Primary execution hook used by the layout engine while parsing constraints.
    /// If an element has an explicit width but `height: auto`, this evaluates the `aspect-ratio`.
    pub fn resolve_aspect_ratio_height(&mut self, node_id: u64, physical_width: f64) -> Option<f64> {
        if let Some(config) = self.active_sizing_rules.get(&node_id) {
            if let Some(ratio) = config.aspect_ratio {
                self.total_aspect_ratios_enforced += 1;
                // Ratio calculation: W / H = ratio_width / ratio_height
                // Therefore: H = (W * ratio_height) / ratio_width
                if ratio.ratio_width > 0.0 {
                    return Some((physical_width * ratio.ratio_height) / ratio.ratio_width);
                }
            }
        }
        None
    }

    /// Executed by the intersection observer logic when `content-visibility: auto` skips painting
    pub fn fetch_container_intrinsic_fallback(&self, node_id: u64) -> (f64, f64) {
        if let Some(config) = self.active_sizing_rules.get(&node_id) {
            let w = config.contain_intrinsic_width.unwrap_or(0.0);
            let h = config.contain_intrinsic_height.unwrap_or(0.0);
            return (w, h);
        }
        (0.0, 0.0) // Element collapses to 0 when skipped
    }

    /// AI-facing CSS Extrinsic Spatial Constraints
    pub fn ai_sizing_summary(&self, node_id: u64) -> String {
        if let Some(config) = self.active_sizing_rules.get(&node_id) {
            let r_str = match config.aspect_ratio {
                Some(r) => format!("{}:{}", r.ratio_width, r.ratio_height),
                None => "Auto".into(),
            };
            format!("📐 CSS Sizing 4 (Node #{}): Aspect Ratio: {} | Contain Fallbacks: Evi | Global Ratios Mapped: {}", 
                node_id, r_str, self.total_aspect_ratios_enforced)
        } else {
            format!("Node #{} executes entirely based on internal DOM constraints", node_id)
        }
    }
}
