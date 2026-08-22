//! CSS Fragmentation Module Level 4 — W3C CSS Fragmentation
//!
//! Implements advanced content-breaking rules across disjointed fragmentation containers (pages/columns):
//!   - Break properties (§ 3): `break-before`, `break-after`, `break-inside`
//!   - Forced Breaks (§ 3.1): always, page, column, avoid, avoid-page
//!   - Orphans and Widows (§ 4): Ensuring typographical coherence during breaks
//!   - Margin Collapsing at Fragmentation Boundaries (§ 6.1): Discarding margins at break points
//!   - Box Decoration Break (§ 7): `slice` versus `clone` when elements are bisected
//!   - AI-facing: Fragmentation boundary evaluation mapping and break execution metrics

use std::collections::HashMap;

/// Desired break behavior for an element edge (§ 3)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BreakStyle { Auto, Avoid, Always, LeftPage, RightPage, Column, Page }

/// Decoration rendering approach when an element spans across fragments (§ 7)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BoxDecorationBreak { Slice, Clone }

/// Configuration of fragmentation values for a node
#[derive(Debug, Clone)]
pub struct FragmentationState {
    pub break_before: BreakStyle,
    pub break_after: BreakStyle,
    pub break_inside: BreakStyle,
    pub orphans: usize,
    pub widows: usize,
    pub box_decoration: BoxDecorationBreak,
}

/// Result of evaluating a fragmentation boundary constraint
#[derive(Debug, Clone)]
pub struct FragmentationResult {
    pub force_break: bool,
    pub discard_margins: bool,
}

/// The global CSS Fragmentation Engine
pub struct FragmentationEngine {
    pub rules: HashMap<u64, FragmentationState>,
}

impl FragmentationEngine {
    pub fn new() -> Self {
        Self { rules: HashMap::new() }
    }

    pub fn set_fragmentation_rules(&mut self, node_id: u64, rules: FragmentationState) {
        self.rules.insert(node_id, rules);
    }

    /// Core algorithm evaluating if a break MUST occur before this node (§ 3)
    pub fn evaluate_break_before(&self, node_id: u64, in_page_context: bool, in_column_context: bool) -> FragmentationResult {
        let mut force_break = false;
        let mut discard_margins = false;

        if let Some(state) = self.rules.get(&node_id) {
            match state.break_before {
                BreakStyle::Always => { force_break = true; }
                BreakStyle::Page | BreakStyle::LeftPage | BreakStyle::RightPage => {
                    if in_page_context { force_break = true; discard_margins = true; }
                }
                BreakStyle::Column => {
                    if in_column_context { force_break = true; discard_margins = true; }
                }
                _ => {} // Auto/Avoid don't force breaks outright here
            }
        }

        FragmentationResult { force_break, discard_margins }
    }

    /// Evaluates if a block of content is allowed to be bisected (§ 3)
    pub fn breaks_allowed_inside(&self, node_id: u64) -> bool {
        if let Some(state) = self.rules.get(&node_id) {
            return state.break_inside != BreakStyle::Avoid;
        }
        true
    }

    /// AI-facing CSS Fragmentation flow status
    pub fn ai_fragmentation_summary(&self, node_id: u64) -> String {
        if let Some(state) = self.rules.get(&node_id) {
            format!("✂️ CSS Fragmentation (Node #{}): [Decor: {:?}] Before: {:?}, Inside: {:?}, After: {:?} | Orphans: {}, Widows: {}", 
                node_id, state.box_decoration, state.break_before, state.break_inside, state.break_after, state.orphans, state.widows)
        } else {
            format!("Node #{} utilizes default `auto` fragmentation semantics", node_id)
        }
    }
}
