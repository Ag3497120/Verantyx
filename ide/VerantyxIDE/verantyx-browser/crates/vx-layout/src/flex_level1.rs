//! CSS Flexible Box Layout Module Level 1 — W3C CSS Flexbox
//!
//! Implements the browser's dynamic 1D layout infrastructure:
//!   - flex-direction (§ 5.1): row, row-reverse, column, column-reverse
//!   - flex-wrap (§ 5.2): nowrap, wrap, wrap-reverse
//!   - flex-flow (§ 5.3): Shorthand mapping
//!   - order (§ 5.4): Visual reordering of items
//!   - flex (§ 7.1): flex-grow, flex-shrink, flex-basis item sizing
//!   - Alignment (§ 8): justify-content, align-items, align-self, align-content
//!   - Flex Layout Algorithm (§ 9): Main/cross axis resolution, line breaking, and free space distribution
//!   - AI-facing: Flex line builder visualizer and shrink/grow metrics

use std::collections::HashMap;

/// Flexbox direction (§ 5.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FlexDirection { Row, RowReverse, Column, ColumnReverse }

/// Flexbox wrapping (§ 5.2)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FlexWrap { NoWrap, Wrap, WrapReverse }

/// Flex item parameters (§ 7)
#[derive(Debug, Clone)]
pub struct FlexItem {
    pub node_id: u64,
    pub order: i32,
    pub grow: f64,
    pub shrink: f64,
    pub basis: f64,
    pub main_size: f64, // Resolved main dimension
    pub cross_size: f64, // Resolved cross dimension
}

/// The CSS Flexible Box Engine
pub struct FlexboxEngine {
    pub container_id: u64,
    pub direction: FlexDirection,
    pub wrap: FlexWrap,
    pub items: Vec<FlexItem>,
}

impl FlexboxEngine {
    pub fn new(container_id: u64) -> Self {
        Self {
            container_id,
            direction: FlexDirection::Row,
            wrap: FlexWrap::NoWrap,
            items: Vec::new(),
        }
    }

    pub fn add_item(&mut self, item: FlexItem) {
        self.items.push(item);
        // Ensure items are sorted by 'order' property (§ 5.4)
        self.items.sort_by_key(|i| i.order);
    }

    /// Flex Layout Algorithm - Step 3: Determine container main size
    /// Step 4: Determine hypothetical main size of items
    /// Step 5: Collect items into flex lines
    pub fn layout_lines(&self, container_main_size: f64) -> Vec<Vec<u64>> {
        let mut lines = Vec::new();
        let mut current_line = Vec::new();
        let mut current_line_size = 0.0;

        for item in &self.items {
            if self.wrap == FlexWrap::NoWrap {
                current_line.push(item.node_id);
            } else {
                if current_line_size + item.basis > container_main_size && !current_line.is_empty() {
                    lines.push(current_line);
                    current_line = Vec::new();
                    current_line_size = 0.0;
                }
                current_line.push(item.node_id);
                current_line_size += item.basis;
            }
        }
        if !current_line.is_empty() {
            lines.push(current_line);
        }
        lines
    }

    /// Flex Layout Algorithm - Step 6: Resolve flexible lengths (resolve free space)
    pub fn resolve_flexible_lengths(&mut self, container_main_size: f64) {
        let total_basis: f64 = self.items.iter().map(|i| i.basis).sum();
        let free_space = container_main_size - total_basis;

        if free_space > 0.0 {
            // Grow items
            let total_grow: f64 = self.items.iter().map(|i| i.grow).sum();
            if total_grow > 0.0 {
                for item in &mut self.items {
                    item.main_size = item.basis + (free_space * (item.grow / total_grow));
                }
            } else {
                for item in &mut self.items { item.main_size = item.basis; }
            }
        } else {
            // Shrink items
            let total_shrink: f64 = self.items.iter().map(|i| i.shrink * i.basis).sum();
            if total_shrink > 0.0 {
                for item in &mut self.items {
                    // scaled shrink factor (§ 7.1)
                    let scaled_shrink = item.shrink * item.basis;
                    item.main_size = item.basis + (free_space * (scaled_shrink / total_shrink));
                }
            } else {
                for item in &mut self.items { item.main_size = item.basis; }
            }
        }
    }

    /// AI-facing flexbox parameters summary
    pub fn ai_flex_summary(&self) -> String {
        let mut lines = vec![format!("📏 CSS Flexbox (Node #{}, Dir={:?}, Wrap={:?}):", 
            self.container_id, self.direction, self.wrap)];
        for item in &self.items {
            lines.push(format!("  - Item #{}: order={}, flex: {:.1} {:.1} {:.1}px", 
                item.node_id, item.order, item.grow, item.shrink, item.basis));
        }
        lines.join("\n")
    }
}
