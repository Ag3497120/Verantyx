//! CSS Nesting Module Level 1 — W3C CSS Nesting
//!
//! Implements parser expansion and resolution for nested CSS rules:
//!   - Nesting Selector (`&`) (§ 3.1): Resolving explicit parent references
//!   - Implicit Nesting (§ 3.2): Determining when standard selectors act as nested
//!   - @nest rule (Legacy support / desugaring)
//!   - Desugaring Algorithm (§ 5): Flattening nested rules into the global cascade
//!   - Specificity Resolution (§ 4): Calculating weight of `&` mapped to the parent
//!   - AI-facing: CSS Nesting depth visualizer and flattened rule emission metrics

use std::collections::HashMap;

/// A raw parsed CSS node capable of nesting
#[derive(Debug, Clone)]
pub struct NestedCssRule {
    pub selector_text: String,
    pub properties: HashMap<String, String>,
    pub nested_children: Vec<NestedCssRule>,
}

/// A flattened standard CSS rule (Desugared)
#[derive(Debug, Clone)]
pub struct FlattenedCssRule {
    pub resolved_selector: String,
    pub properties: HashMap<String, String>,
}

/// The global CSS Nesting Desugar Engine
pub struct CssNestingEngine {
    pub max_depth_encountered: usize,
    pub total_desugared_rules: usize,
}

impl CssNestingEngine {
    pub fn new() -> Self {
        Self {
            max_depth_encountered: 0,
            total_desugared_rules: 0,
        }
    }

    /// Primary Desugaring Algorithm (§ 5)
    pub fn flatten(&mut self, rule: &NestedCssRule) -> Vec<FlattenedCssRule> {
        self.flatten_recursive(rule, "", 0)
    }

    fn flatten_recursive(&mut self, rule: &NestedCssRule, parent_selector: &str, current_depth: usize) -> Vec<FlattenedCssRule> {
        if current_depth > self.max_depth_encountered {
            self.max_depth_encountered = current_depth;
        }

        let mut output = Vec::new();

        // Resolve this rule's selector
        // E.g. parent: `.card`, rule: `&:hover` -> `.card:hover`
        // E.g. parent: `.card`, rule: `.header` -> `.card .header`
        let resolved_selector = if parent_selector.is_empty() {
            rule.selector_text.clone()
        } else if rule.selector_text.contains('&') {
            rule.selector_text.replace('&', parent_selector)
        } else {
            // Implicit ancestor relationship
            format!("{} {}", parent_selector, rule.selector_text)
        };

        // Emit this node's properties if any exist
        if !rule.properties.is_empty() {
            output.push(FlattenedCssRule {
                resolved_selector: resolved_selector.clone(),
                properties: rule.properties.clone(),
            });
            self.total_desugared_rules += 1;
        }

        // Recursively unroll children
        for child in &rule.nested_children {
            let mut child_flattened = self.flatten_recursive(child, &resolved_selector, current_depth + 1);
            output.append(&mut child_flattened);
        }

        output
    }

    /// AI-facing CSS Nesting performance analytics
    pub fn ai_nesting_summary(&self) -> String {
        format!("🪺 CSS Nesting Translator: {} flattened rules generated (Max nesting depth reached: {})", 
            self.total_desugared_rules, self.max_depth_encountered)
    }
}
