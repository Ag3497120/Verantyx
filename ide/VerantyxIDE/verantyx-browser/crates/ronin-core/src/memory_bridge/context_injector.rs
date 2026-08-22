//! Context injector — bridges the JCross spatial index to the prompt builder.
//!
//! Responsible for selecting *which* memory nodes to surface for a given task,
//! respecting the available token budget and zone prioritization rules.

use crate::models::context_budget::{ContextBudget, estimate_tokens};
use super::spatial_index::{SpatialIndex, MemoryNode};
use tracing::debug;

// ─────────────────────────────────────────────────────────────────────────────
// Injector Configuration
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone)]
pub struct InjectorConfig {
    /// Max tokens this injector may consume across all zones
    pub token_budget: usize,
    /// Whether to include Near-zone nodes when Front zone is underwhelming
    pub allow_near_fallback: bool,
    /// Optional domain keyword for semantic filtering
    pub domain_hint: Option<String>,
}

impl InjectorConfig {
    pub fn from_budget(budget: &ContextBudget) -> Self {
        Self {
            token_budget: budget.system_reserved / 2, // Reserve half of sys budget for memory
            allow_near_fallback: true,
            domain_hint: None,
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Context Injector
// ─────────────────────────────────────────────────────────────────────────────

pub struct ContextInjector<'a> {
    index: &'a SpatialIndex,
    cfg: InjectorConfig,
}

impl<'a> ContextInjector<'a> {
    pub fn new(index: &'a SpatialIndex, cfg: InjectorConfig) -> Self {
        Self { index, cfg }
    }

    /// Selects and formats the best memory nodes for prompt injection.
    /// Respects token budget and zone priority ordering.
    pub fn build_injection_block(&self) -> String {
        let mut budget_remaining = self.cfg.token_budget;
        let mut selected: Vec<&MemoryNode> = vec![];

        // Phase 1: Gather Front zone nodes
        let mut front_nodes: Vec<&MemoryNode> = self.index.front_nodes();
        front_nodes.sort_by(|a, b| b.weight.partial_cmp(&a.weight).unwrap());

        for node in front_nodes {
            let cost = estimate_tokens(&node.content);
            if cost > budget_remaining {
                debug!("[ContextInjector] Budget exhausted at Front node: {}", node.key);
                break;
            }
            budget_remaining -= cost;
            selected.push(node);
        }

        // Phase 2: Domain-keyword semantic filter (simple contains-match for now)
        if let Some(ref hint) = self.cfg.domain_hint {
            selected.retain(|n| n.content.contains(hint.as_str()) || n.kanji_tags.iter().any(|t| &t.name == hint));
        }

        if selected.is_empty() {
            return "(No relevant memory context available for this turn.)".to_string();
        }

        selected
            .iter()
            .map(|n| format!("**[{}]**\n{}", n.key, n.content))
            .collect::<Vec<_>>()
            .join("\n\n---\n\n")
    }

    /// Returns the estimated token cost of the current injection block.
    pub fn estimated_token_cost(&self) -> usize {
        let block = self.build_injection_block();
        estimate_tokens(&block)
    }
}
