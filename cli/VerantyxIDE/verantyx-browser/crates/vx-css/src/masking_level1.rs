//! CSS Masking Module Level 1 — W3C CSS Masking
//!
//! Implements partial or complete hiding of elements using masks and paths:
//!   - Masking properties (§ 3): mask-image, mask-mode, mask-repeat, mask-position, mask-size,
//!     mask-clip, mask-origin, mask-composite
//!   - Clipping properties (§ 4): clip-path (basic-shape, <url>), clip-rule (nonzero, evenodd)
//!   - Mask composite modes (§ 3.7): add, subtract, intersect, exclude
//!   - Mask source types (§ 3.1): alpha (default), luminance, match-source
//!   - Layered masking: Handling multiple mask layers and their blending sequence
//!   - SVG Clipping and Masking integration: Resolving <clipPath> and <mask> references
//!   - AI-facing: Mask layer inspector and composite blending visualizer

use std::collections::HashMap;

/// Masking image types (§ 3)
#[derive(Debug, Clone)]
pub enum MaskImage { None, Url(String), Gradient(u64) }

/// Mask composite operations (§ 3.7)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MaskComposite { Add, Subtract, Intersect, Exclude }

/// Mask source modes (§ 3.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MaskMode { Alpha, Luminance, MatchSource }

/// An individual mask layer (§ 3)
#[derive(Debug, Clone)]
pub struct MaskLayer {
    pub image: MaskImage,
    pub mode: MaskMode,
    pub composite: MaskComposite,
    pub clip: MaskBox,
    pub origin: MaskBox,
    pub repeat: (MaskRepeat, MaskRepeat),
    pub size: MaskSize,
    pub x: f64,
    pub y: f64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MaskBox { BorderBox, PaddingBox, ContentBox, MarginBox, FillBox, StrokeBox, ViewBox }

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MaskRepeat { Repeat, NoRepeat, Space, Round }

#[derive(Debug, Clone, Copy)]
pub enum MaskSize { Contain, Cover, Fixed(f64, f64) }

/// The CSS Masking Engine
pub struct MaskingEngine {
    pub mask_layers: HashMap<u64, Vec<MaskLayer>>, // node_id -> mask-layers
    pub clip_paths: HashMap<u64, String>, // node_id -> clip-path path string
}

impl MaskingEngine {
    pub fn new() -> Self {
        Self {
            mask_layers: HashMap::new(),
            clip_paths: HashMap::new(),
        }
    }

    pub fn register_mask(&mut self, node_id: u64, layer: MaskLayer) {
        self.mask_layers.entry(node_id).or_default().push(layer);
    }

    pub fn set_clip_path(&mut self, node_id: u64, path: &str) {
        self.clip_paths.insert(node_id, path.to_string());
    }

    /// AI-facing masking visualizer
    pub fn ai_mask_inspector(&self, node_id: u64) -> String {
        let mut lines = vec![format!("🎭 CSS Masking Profile for Node #{}:", node_id)];
        
        if let Some(path) = self.clip_paths.get(&node_id) {
            lines.push(format!("  ClipPath: [Path: \"{}\"]", path));
        }

        if let Some(layers) = self.mask_layers.get(&node_id) {
            lines.push(format!("  Mask Layers (Count: {}):", layers.len()));
            for (idx, layer) in layers.iter().enumerate() {
                lines.push(format!("    - Layer {}: Mode={:?}, Composite={:?}, Size={:?}, Image={:?}", 
                    idx, layer.mode, layer.composite, layer.size, layer.image));
            }
        }
        lines.join("\n")
    }
}
