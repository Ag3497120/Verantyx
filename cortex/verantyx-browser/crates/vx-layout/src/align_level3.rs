//! CSS Box Alignment Module Level 3 — W3C CSS Box Alignment
//!
//! Implements universal alignment architecture for Block, Flex, and Grid layouts:
//!   - Content Distribution (§ 4): justify-content, align-content (flex-start, space-between, etc.)
//!   - Self Alignment (§ 5): justify-self, align-self (start, end, center, stretch)
//!   - Default Alignment (§ 6): justify-items, align-items (setting defaults for children)
//!   - Baseline Alignment (§ 7): first baseline, last baseline alignment within groups
//!   - Overflow Alignment (§ 8): safe, unsafe (preventing data loss on overflow)
//!   - Gap Spacing (§ 9): row-gap, column-gap (consistent gutter rendering)
//!   - AI-facing: Box alignment offset recalculation visualizer and safe-boundary metrics

use std::collections::HashMap;

/// Distribution alignment values (§ 4)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ContentDistribution { Start, End, Center, SpaceBetween, SpaceAround, SpaceEvenly, Stretch }

/// Self/Item alignment values (§ 5)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SelfAlignment { Auto, Start, End, Center, Stretch, Baseline, LastBaseline }

/// Safe/unsafe overflow modes (§ 8)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OverflowAlignment { Default, Safe, Unsafe }

/// Configuration for a specific alignment axis
#[derive(Debug, Clone)]
pub struct AlignmentAxis {
    pub content: ContentDistribution,
    pub items: SelfAlignment, // Default for children
    pub overflow: OverflowAlignment,
    pub gap: f64,
}

/// The global Box Alignment Engine
pub struct BoxAlignmentEngine {
    pub container_axes: HashMap<u64, (AlignmentAxis, AlignmentAxis)>, // node_id -> (Justify/Inline, Align/Block)
    pub item_overrides: HashMap<u64, (SelfAlignment, SelfAlignment)>, // node_id -> (JustifySelf, AlignSelf)
}

impl BoxAlignmentEngine {
    pub fn new() -> Self {
        Self {
            container_axes: HashMap::new(),
            item_overrides: HashMap::new(),
        }
    }

    /// Analyzes the free space and calculates the offset for a self-aligned item (§ 5)
    pub fn resolve_self_alignment(&self, alignment: SelfAlignment, overflow: OverflowAlignment, free_space: f64) -> f64 {
        let align_value = if free_space < 0.0 && overflow == OverflowAlignment::Safe {
            SelfAlignment::Start // Prevent data loss off-screen (§ 8)
        } else {
            alignment
        };

        match align_value {
            SelfAlignment::Start | SelfAlignment::Stretch => 0.0,
            SelfAlignment::Center => free_space / 2.0,
            SelfAlignment::End => free_space,
            _ => 0.0, // Baselines handled elsewhere
        }
    }

    /// Distributes free space according to justify-content or align-content (§ 4)
    pub fn distribute_content(&self, distribution: ContentDistribution, free_space: f64, item_count: usize) -> (f64, f64) {
        if item_count == 0 { return (0.0, 0.0); }
        let n = item_count as f64;

        match distribution {
            ContentDistribution::Start => (0.0, 0.0),
            ContentDistribution::Center => (free_space / 2.0, 0.0),
            ContentDistribution::End => (free_space, 0.0),
            ContentDistribution::SpaceBetween => (0.0, if n > 1.0 { free_space / (n - 1.0) } else { 0.0 }),
            ContentDistribution::SpaceAround => (free_space / (n * 2.0), free_space / n),
            ContentDistribution::SpaceEvenly => (free_space / (n + 1.0), free_space / (n + 1.0)),
            ContentDistribution::Stretch => (0.0, 0.0), // Item sizes modified via stretch rule
        }
    }

    /// AI-facing box alignment configuration
    pub fn ai_alignment_summary(&self, node_id: u64) -> String {
        if let Some((just, align)) = self.container_axes.get(&node_id) {
            format!("📐 Box Alignment (Node #{}): Justify[{:?} (Gap:{:.1})], Align[{:?} (Gap:{:.1})]", 
                node_id, just.content, just.gap, align.content, align.gap)
        } else {
            format!("Node #{} uses Flow layout standard block alignment", node_id)
        }
    }
}
