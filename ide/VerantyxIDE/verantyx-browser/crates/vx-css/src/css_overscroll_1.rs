//! CSS Overscroll Behavior Module Level 1 — W3C CSS Overscroll
//!
//! Implements bounds limits for momentum scrolling preventing pull-to-refresh:
//!   - `overscroll-behavior` (§ 3): `auto`, `contain`, `none` constraints
//!   - Overriding OS default rubber-banding animations
//!   - Scroll chaining physics preventing event bubbling up spatial trees
//!   - AI-facing: Typographical bound elastic scrolling limits tracker

use std::collections::HashMap;

/// Defines behavior when a scroll container hits the boundary edge (§ 3)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OverscrollBehavior { Auto, Contain, None }

/// Maps behavior across X and Y physical axes
#[derive(Debug, Clone, Copy)]
pub struct OverscrollConfiguration {
    pub behavior_x: OverscrollBehavior,
    pub behavior_y: OverscrollBehavior,
}

impl Default for OverscrollConfiguration {
    fn default() -> Self {
        Self {
            behavior_x: OverscrollBehavior::Auto,
            behavior_y: OverscrollBehavior::Auto,
        }
    }
}

/// Global Engine evaluating spatial scroll boundaries during touch events
pub struct CssOverscrollEngine {
    pub rules: HashMap<u64, OverscrollConfiguration>,
    pub total_chained_scrolls_prevented: u64,
}

impl CssOverscrollEngine {
    pub fn new() -> Self {
        Self {
            rules: HashMap::new(),
            total_chained_scrolls_prevented: 0,
        }
    }

    pub fn set_overscroll_config(&mut self, node_id: u64, config: OverscrollConfiguration) {
        self.rules.insert(node_id, config);
    }

    /// Deep compositor evaluation logic: Executes continuously during trackpad / touch scroll loops
    /// Returns `true` if the scroll should bubble up to the parent container.
    pub fn evaluate_scroll_chaining(&mut self, node_id: u64, axis_is_x: bool) -> bool {
        if let Some(config) = self.rules.get(&node_id) {
            let active_behavior = if axis_is_x { config.behavior_x } else { config.behavior_y };

            match active_behavior {
                OverscrollBehavior::Auto => {
                    // Standard W3C behavior: Scroll bubbles to parent when boundary limits are hit
                    return true; 
                }
                OverscrollBehavior::Contain | OverscrollBehavior::None => {
                    // Prevent bubbling! 
                    // Difference: `None` also prevents the local OS rubber-band "glow" effect entirely
                    // while `Contain` still shows the glow locally but refuses to chain up.
                    self.total_chained_scrolls_prevented += 1;
                    return false;
                }
            }
        }
        true // Defaults to chaining
    }

    /// Evaluator for whether the underlying Native windowing system should execute "Pull to refresh" or "Swipe back" navigation
    pub fn evaluate_root_navigation_trigger(&self, root_node_id: u64, is_pull_down: bool) -> bool {
        if let Some(config) = self.rules.get(&root_node_id) {
            let active_behavior = if is_pull_down { config.behavior_y } else { config.behavior_x };
            // Typical heuristic: overscroll-behavior-y: none on the `body` disables Chrome's Pull to Refresh
            if active_behavior == OverscrollBehavior::None || active_behavior == OverscrollBehavior::Contain {
                return false;
            }
        }
        true
    }

    /// AI-facing Kinetic scrolling topological boundaries tracker
    pub fn ai_overscroll_summary(&self, node_id: u64) -> String {
        if let Some(config) = self.rules.get(&node_id) {
            format!("🛑 CSS Overscroll (Node #{}): X: {:?} | Y: {:?} | Global Chain Prevented: {}", 
                node_id, config.behavior_x, config.behavior_y, self.total_chained_scrolls_prevented)
        } else {
            format!("Node #{} employs standard chain-bubbling scroll physics", node_id)
        }
    }
}
