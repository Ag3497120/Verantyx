//! CSS Box Alignment Module Level 3 — W3C CSS Box Align
//!
//! Implements universal layout alignment shared across Grid, Flexbox, and Block contexts:
//!   - `justify-content` / `align-content` (§ 5): Distributing free space between alignment subjects
//!   - `justify-items` / `align-items` (§ 6): Aligning items within their grid/flex areas
//!   - `justify-self` / `align-self` (§ 6.1): Individual override alignment
//!   - `gap` / `row-gap` / `column-gap` (§ 8): Defining spacing between structural rows/columns
//!   - Safe / Unsafe alignment limits (preventing off-screen data loss)
//!   - AI-facing: Universal box distribution visualizer and bounding limits

use std::collections::HashMap;

/// Core distribution strategies for leftover layout space (§ 5)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ContentDistribution { Normal, Start, End, Center, SpaceBetween, SpaceAround, SpaceEvenly, Stretch }

/// Core alignment strategies within assigned layout boxes (§ 6)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ItemAlignment { Auto, Normal, Start, End, Center, Stretch, Baseline, FirstBaseline, LastBaseline }

/// Overflow safety mechanism (prevents centering off the top-left leading to data loss) (§ 4.4)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AlignmentSafety { Safe, Unsafe, Default }

/// Unified sizing gaps between content elements (§ 8)
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct LayoutGaps {
    pub column_gap: f64,
    pub row_gap: f64,
}

#[derive(Debug, Clone)]
pub struct BoxAlignmentConfig {
    pub justify_content: ContentDistribution,
    pub align_content: ContentDistribution,
    pub justify_items: ItemAlignment,
    pub align_items: ItemAlignment,
    pub justify_self: ItemAlignment, // Usually on children
    pub align_self: ItemAlignment,   // Usually on children
    pub safety: AlignmentSafety,
    pub gaps: LayoutGaps,
}

impl Default for BoxAlignmentConfig {
    fn default() -> Self {
        Self {
            justify_content: ContentDistribution::Normal,
            align_content: ContentDistribution::Normal,
            justify_items: ItemAlignment::Normal,
            align_items: ItemAlignment::Normal,
            justify_self: ItemAlignment::Auto,
            align_self: ItemAlignment::Auto,
            safety: AlignmentSafety::Default,
            gaps: LayoutGaps { column_gap: 0.0, row_gap: 0.0 },
        }
    }
}

/// Engine managing the unified mathematics of alignment
pub struct CssBoxAlignmentEngine {
    pub alignments: HashMap<u64, BoxAlignmentConfig>,
}

impl CssBoxAlignmentEngine {
    pub fn new() -> Self {
        Self { alignments: HashMap::new() }
    }

    pub fn set_alignment(&mut self, node_id: u64, config: BoxAlignmentConfig) {
        self.alignments.insert(node_id, config);
    }

    /// Evaluates exact translation offsets when free space is distributed (§ 5)
    pub fn calculate_distribution_offset(&self, strategy: ContentDistribution, free_space: f64, num_items: usize, item_index: usize) -> f64 {
        if free_space <= 0.0 || num_items <= 1 {
            return 0.0;
        }

        match strategy {
            ContentDistribution::Start | ContentDistribution::Normal => 0.0,
            ContentDistribution::End => if item_index == 0 { free_space } else { 0.0 },
            // Simplified interpolation algorithms
            ContentDistribution::Center => if item_index == 0 { free_space / 2.0 } else { 0.0 },
            ContentDistribution::SpaceBetween => {
                let step = free_space / (num_items - 1) as f64;
                if item_index > 0 { step } else { 0.0 }
            },
            ContentDistribution::SpaceAround => {
                let step = free_space / num_items as f64;
                if item_index == 0 { step / 2.0 } else { step }
            },
            ContentDistribution::SpaceEvenly => {
                let step = free_space / (num_items + 1) as f64;
                step // Applies before every item
            },
            ContentDistribution::Stretch => 0.0, // Stretch affects size, not offset directly here
        }
    }

    /// Resolves alignment with `Safe` data-loss mitigation applied (§ 4.4)
    pub fn resolve_safe_alignment(&self, alignment: ItemAlignment, safety: AlignmentSafety, overflows: bool) -> ItemAlignment {
        if safety == AlignmentSafety::Safe && overflows {
            return ItemAlignment::Start;
        }
        alignment
    }

    /// AI-facing CSS Box Alignment geometries
    pub fn ai_box_align_summary(&self, node_id: u64) -> String {
        if let Some(cfg) = self.alignments.get(&node_id) {
            format!("📦 CSS Box Align 3 (Node #{}): Content: {:?}/{:?} | Items: {:?}/{:?} | Gaps: {}x{}", 
                node_id, cfg.justify_content, cfg.align_content, cfg.justify_items, cfg.align_items, cfg.gaps.column_gap, cfg.gaps.row_gap)
        } else {
            format!("Node #{} uses default Box Alignment defaults", node_id)
        }
    }
}
