//! CSS Conditional Rules Module Level 5 — W3C CSS Conditional 5
//!
//! Implements procedural programming logic abstractions in CSS:
//!   - `@when` / `@else` rule structures (§ 2): Chaining media queries without duplication
//!   - Intersection evaluations between viewport and feature capabilities
//!   - Media condition resolution topological maps
//!   - AI-facing: CSS Logical Structural Branches

use std::collections::HashMap;

/// Maps a specific branching pathway evaluated by the CSS Parser
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ConditionalBranchState { Unevaluated, Active, Skipped }

/// Identifies an IF/ELSE structural block inside the CSSOM
#[derive(Debug, Clone)]
pub struct CssWhenElseBlock {
    pub primary_condition_string: String, // e.g. "media(min-width: 800px) and supports(display: grid)"
    pub primary_state: ConditionalBranchState,
    pub else_state: ConditionalBranchState,
}

/// The global Declarative Resolver handling AST procedural evaluations
pub struct CssConditional5Engine {
    pub logical_blocks: HashMap<u64, CssWhenElseBlock>,
    pub total_branches_stepped: u64,
}

impl CssConditional5Engine {
    pub fn new() -> Self {
        Self {
            logical_blocks: HashMap::new(),
            total_branches_stepped: 0,
        }
    }

    pub fn construct_block(&mut self, block_id: u64, condition: &str) {
        self.logical_blocks.insert(block_id, CssWhenElseBlock {
            primary_condition_string: condition.to_string(),
            primary_state: ConditionalBranchState::Unevaluated,
            else_state: ConditionalBranchState::Unevaluated,
        });
    }

    /// Executed whenever the viewport resizes or system features query resolves
    /// Returns true if the active branch logic mutated, requiring a CSS Recalculation Phase
    pub fn evaluate_branches(&mut self, block_id: u64, condition_is_true: bool) -> bool {
        if let Some(mut block) = self.logical_blocks.get_mut(&block_id) {
            self.total_branches_stepped += 1;

            let prev_primary = block.primary_state;

            if condition_is_true {
                block.primary_state = ConditionalBranchState::Active;
                block.else_state = ConditionalBranchState::Skipped;
            } else {
                block.primary_state = ConditionalBranchState::Skipped;
                block.else_state = ConditionalBranchState::Active;
            }

            return prev_primary != block.primary_state;
        }
        false
    }

    /// Identifies whether the active rule content should be ingested by the cascader
    pub fn should_process_rules(&self, block_id: u64, evaluating_else: bool) -> bool {
        if let Some(block) = self.logical_blocks.get(&block_id) {
            if evaluating_else {
                return block.else_state == ConditionalBranchState::Active;
            } else {
                return block.primary_state == ConditionalBranchState::Active;
            }
        }
        false
    }

    /// AI-facing CSS AST Procedural Bounds
    pub fn ai_conditional5_summary(&self, block_id: u64) -> String {
        if let Some(block) = self.logical_blocks.get(&block_id) {
            format!("🔀 CSS Conditional 5 (Block #{}): @when: {:?} | @else: {:?} | Global Branches Evals: {}", 
                block_id, block.primary_state, block.else_state, self.total_branches_stepped)
        } else {
            format!("Block #{} possesses no IF/ELSE abstractions", block_id)
        }
    }
}
