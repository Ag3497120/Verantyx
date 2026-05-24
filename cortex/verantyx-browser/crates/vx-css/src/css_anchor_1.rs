//! CSS Anchor Positioning Level 1 — W3C CSS Anchor Positioning
//!
//! Implements absolute box placement dynamically bound to target scrollable boxes:
//!   - `anchor()` (§ 5): Binding `top`, `left`, etc. to the boundaries of another element
//!   - `anchor-name` (§ 3): Exposing the target node reference globally
//!   - `position-try` / `@position-try` (§ 6): Collision detection flip matrices
//!   - AI-facing: Geometrical relative constraint topographies

use std::collections::HashMap;

/// Denotes which edge of the anchor is being referenced
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AnchorEdge { Top, Left, Bottom, Right, Center, Start, End }

/// Defines an explicit constraint bound to a specific exposed anchor name
#[derive(Debug, Clone)]
pub struct AnchorConstraint {
    pub target_anchor_name: String,
    pub referenced_edge: AnchorEdge,
    pub fallback_length: f64, // Used if anchor doesn't exist
}

/// The layout engine passes physical rects for the named anchors into CSS OM
#[derive(Debug, Clone, Copy)]
pub struct PhysicalAnchorRect {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}

/// Global Engine evaluating complex geometrical mapping vectors prior to layout
pub struct CssAnchorPositioningEngine {
    // Registry of active named anchors attached to specific nodes (`anchor-name: --foo`)
    pub named_anchors: HashMap<String, PhysicalAnchorRect>,
    
    // Node -> Declared Constraint mappings (e.g., Node 5 has `top: anchor(--foo bottom)`)
    pub declared_constraints: HashMap<u64, Vec<AnchorConstraint>>,

    pub total_anchors_evaluated: u64,
}

impl CssAnchorPositioningEngine {
    pub fn new() -> Self {
        Self {
            named_anchors: HashMap::new(),
            declared_constraints: HashMap::new(),
            total_anchors_evaluated: 0,
        }
    }

    /// Evaluated dynamically as elements are added to DOM or mutate `anchor-name` attributes
    pub fn register_anchor(&mut self, name: &str, rect: PhysicalAnchorRect) {
        self.named_anchors.insert(name.to_string(), rect);
    }

    pub fn attach_constraint(&mut self, node_id: u64, constraint: AnchorConstraint) {
        let constraints = self.declared_constraints.entry(node_id).or_default();
        constraints.push(constraint);
    }

    /// Used by `vx-layout` exactly when computing the absolute bounds of the positioned element
    pub fn resolve_anchor_function(&mut self, constraint: &AnchorConstraint) -> f64 {
        self.total_anchors_evaluated += 1;

        if let Some(target) = self.named_anchors.get(&constraint.target_anchor_name) {
            match constraint.referenced_edge {
                AnchorEdge::Top => target.y,
                AnchorEdge::Bottom => target.y + target.height,
                AnchorEdge::Left => target.x,
                AnchorEdge::Right => target.x + target.width,
                AnchorEdge::Center => {
                    // Requires context if asking X or Y, assuming vertical for abstract example
                    target.y + (target.height / 2.0)
                }
                _ => constraint.fallback_length,
            }
        } else {
            // Anchor missing from DOM or hidden
            constraint.fallback_length
        }
    }

    /// Handles `position-try` (fallback alignments if popover collides with viewport bounds)
    pub fn evaluate_collision_flip(&self, requested_y: f64, element_height: f64, viewport_height: f64) -> bool {
        // If element draws offscreen downwards...
        requested_y + element_height > viewport_height
    }

    /// AI-facing Relativity constraints topologies
    pub fn ai_anchor_summary(&self, node_id: u64) -> String {
        let count = self.declared_constraints.get(&node_id).map_or(0, |c| c.len());
        format!("⚓ CSS Anchor Pos (Node #{}): Relational Constraints Built: {} | Total Evals: {} | Active Global Anchors: {}", 
            node_id, count, self.total_anchors_evaluated, self.named_anchors.len())
    }
}
