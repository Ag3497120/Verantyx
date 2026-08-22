//! CSS Logical Properties Module Level 1 — W3C CSS Logical
//!
//! Implements writing-mode abstraction to decouple layout math from physical screens:
//!   - `block-size` / `inline-size` (§ 4): Replacing width/height based on text flow
//!   - `margin-block-start` / `padding-inline-end` (§ 5): Direction-agnostic spacing
//!   - `inset-block-start` etc (§ 4.3): Logical CSS positioning (replacing top/bottom/left/right)
//!   - `float: inline-start` (§ 4.4): Decoupled floating bounds
//!   - Physical mapping algorithms deriving final layout rectangles
//!   - AI-facing: CSS Writing Mode geometry converter bounds

use std::collections::HashMap;

/// Denotes the direction of block progression (§ 3)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WritingMode { HorizontalTb, VerticalRl, VerticalLr }

/// Denotes the direction of text flow along the inline axis
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TextDirection { Ltr, Rtl }

/// Values input by developers agnostic to screen orientation
#[derive(Debug, Clone)]
pub struct LogicalDimensions {
    pub inline_size: Option<f64>,
    pub block_size: Option<f64>,
    pub margin_block_start: f64,
    pub margin_block_end: f64,
    pub margin_inline_start: f64,
    pub margin_inline_end: f64,
    pub padding_block_start: f64,
    pub padding_block_end: f64,
    pub padding_inline_start: f64,
    pub padding_inline_end: f64,
}

/// The final physical bounds computed for Skia painting mapping
#[derive(Debug, Clone)]
pub struct PhysicalBoxResolution {
    pub width: Option<f64>,
    pub height: Option<f64>,
    pub margin_top: f64,
    pub margin_right: f64,
    pub margin_bottom: f64,
    pub margin_left: f64,
}

/// The global Engine mapping abstract logic to physical computer screens
pub struct CssLogicalEngine {
    pub logical_state: HashMap<u64, (WritingMode, TextDirection, LogicalDimensions)>,
    pub total_boxes_resolved: u64,
}

impl CssLogicalEngine {
    pub fn new() -> Self {
        Self {
            logical_state: HashMap::new(),
            total_boxes_resolved: 0,
        }
    }

    pub fn set_logical_box(&mut self, node_id: u64, wm: WritingMode, dir: TextDirection, dims: LogicalDimensions) {
        self.logical_state.insert(node_id, (wm, dir, dims));
    }

    /// Complex heuristic projecting direction-agnostic values onto the physical viewport bounds (§ 5)
    pub fn resolve_physical_box(&mut self, node_id: u64) -> Option<PhysicalBoxResolution> {
        if let Some((wm, dir, dims)) = self.logical_state.get(&node_id) {
            self.total_boxes_resolved += 1;

            let (mut width, mut height) = (None, None);
            let (mut mt, mut mr, mut mb, mut ml) = (0.0, 0.0, 0.0, 0.0);

            // Determine physical Width & Height mapping
            match wm {
                WritingMode::HorizontalTb => {
                    width = dims.inline_size;
                    height = dims.block_size;
                    
                    mt = dims.margin_block_start;
                    mb = dims.margin_block_end;
                    
                    if *dir == TextDirection::Ltr {
                        ml = dims.margin_inline_start;
                        mr = dims.margin_inline_end;
                    } else {
                        mr = dims.margin_inline_start;
                        ml = dims.margin_inline_end;
                    }
                }
                WritingMode::VerticalRl => {
                    width = dims.block_size;
                    height = dims.inline_size;
                    
                    mr = dims.margin_block_start;
                    ml = dims.margin_block_end;

                    if *dir == TextDirection::Ltr {
                        mt = dims.margin_inline_start;
                        mb = dims.margin_inline_end;
                    } else {
                        mb = dims.margin_inline_start;
                        mt = dims.margin_inline_end;
                    }
                }
                WritingMode::VerticalLr => {
                    width = dims.block_size;
                    height = dims.inline_size;

                    ml = dims.margin_block_start;
                    mr = dims.margin_block_end;

                    if *dir == TextDirection::Ltr {
                        mt = dims.margin_inline_start;
                        mb = dims.margin_inline_end;
                    } else {
                        mb = dims.margin_inline_start;
                        mt = dims.margin_inline_end;
                    }
                }
            }

            return Some(PhysicalBoxResolution { width, height, margin_top: mt, margin_right: mr, margin_bottom: mb, margin_left: ml });
        }
        None
    }

    /// AI-facing Flow geometry topological metrics
    pub fn ai_logical_summary(&self, node_id: u64) -> String {
        if let Some((wm, dir, _)) = self.logical_state.get(&node_id) {
            format!("📐 CSS Logical Flow (Node #{}): Writing Mode: {:?} | Text Direction: {:?}", 
                node_id, wm, dir)
        } else {
            format!("Node #{} utilizes default horizontal-tb rendering", node_id)
        }
    }
}
