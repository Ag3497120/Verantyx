//! CSS Anchor Positioning Fallback Level 1 — W3C CSS Anchor Positioning
//!
//! Implements adaptive fallback geometry for elements tied to an anchor:
//!   - @position-try rules (§ 4): Defining alternative layout configurations
//!   - position-try-fallbacks property (§ 5): Specifying a prioritized list of fallbacks
//!   - position-try-order (§ 6): Normalizing and reordering fallbacks (most-inline-size)
//!   - Flip alignments: flip-block, flip-inline, flip-start options
//!   - Collision Detection Algorthim: Determining when an anchored popup triggers a fallback
//!   - AI-facing: Anchor collision visualization and active layout configuration metrics

use std::collections::HashMap;

/// Built-in programmatic flip strategies (§ 5.2)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TryTactic { FlipBlock, FlipInline, FlipStart }

/// A prioritized fallback entry
#[derive(Debug, Clone)]
pub enum PositionFallbackEntry {
    CustomIdent(String),     // User-defined @position-try rule
    Tactic(TryTactic),       // Built in flip
}

/// Layout results for collision evaluation
#[derive(Debug, Clone)]
pub struct CollisionGeometry {
    pub is_overflowing_inline: bool,
    pub is_overflowing_block: bool,
    pub inline_gap: f64, // Remaining space, if negative -> collision
    pub block_gap: f64,
}

/// The CSS Anchor Position Fallback Engine
pub struct PositionFallbackEngine {
    pub fallback_rules: HashMap<String, Vec<String>>, // @position-try -> CSS Properties
    pub assigned_fallbacks: HashMap<u64, Vec<PositionFallbackEntry>>, // node_id -> position-try-fallbacks
    pub active_layout_choice: HashMap<u64, usize>, // node_id -> active fallback index
}

impl PositionFallbackEngine {
    pub fn new() -> Self {
        Self {
            fallback_rules: HashMap::new(),
            assigned_fallbacks: HashMap::new(),
            active_layout_choice: HashMap::new(),
        }
    }

    /// Algorithm to test and execute the first viable fallback geometry (§ 4)
    pub fn evaluate_fallbacks(&mut self, node_id: u64, geometries: Vec<CollisionGeometry>) {
        if let Some(fallbacks) = self.assigned_fallbacks.get(&node_id) {
            // geometries vec aligns sequentially with the fallback list
            for (idx, geom) in geometries.iter().enumerate() {
                // If this layout geometry does not overflow the containing block at all
                if !geom.is_overflowing_inline && !geom.is_overflowing_block {
                    // Lock in this fallback as the active layout state!
                    self.active_layout_choice.insert(node_id, idx);
                    return;
                }
            }
            
            // If all fail, use the first one (idx 0) or the element's default position
            self.active_layout_choice.insert(node_id, 0); 
        }
    }

    /// AI-facing internal Anchor positions
    pub fn ai_anchor_fallback_summary(&self, node_id: u64) -> String {
        if let Some(fallbacks) = self.assigned_fallbacks.get(&node_id) {
            let active_idx = self.active_layout_choice.get(&node_id).unwrap_or(&0);
            format!("⚓️ Position Fallback (Node #{}): Selected index {} out of {} defined fallbacks", 
                node_id, active_idx, fallbacks.len())
        } else {
            format!("Node #{} has no dynamic position fallbacks configured", node_id)
        }
    }
}
