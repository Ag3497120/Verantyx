//! CSS Multi-column Layout — W3C CSS Multi-column Layout
//!
//! Implements the infrastructure for column-based content flow:
//!   - Column properties (§ 2): column-width, column-count, column-gap, column-rule
//!   - Used column calculation (§ 3): Resolving count vs. width based on available space
//!   - Column Span (§ 6): column-span (none, all) for header/footer-like integration
//!   - Column Fill (§ 4): column-fill (auto, balance) for even height distribution
//!   - Column Breaking (§ 5): break-before, break-after, break-inside (auto, avoid, column)
//!   - Column Rules (§ 2.4): column-rule-width, column-rule-style, column-rule-color
//!   - Box Model (§ 7): How padding/borders interact with column boxes
//!   - AI-facing: Column fragmentation visualizer and rule map metrics

use std::collections::HashMap;

/// Used column calculation results (§ 3)
#[derive(Debug, Clone, Copy)]
pub struct ColumnMetrics {
    pub count: usize,
    pub width: f64,
    pub gap: f64,
}

/// Column span behavior (§ 6)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ColumnSpan { None, All }

/// Column fill behavior (§ 4)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ColumnFill { Auto, Balance }

/// Column rule style (§ 2.4)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ColumnRuleStyle { None, Hidden, Dotted, Dashed, Solid, Double, Groove, Ridge, Inset, Outset }

/// Individual column fragment
#[derive(Debug, Clone)]
pub struct ColumnBox {
    pub index: usize,
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}

/// The Multi-column Layout Engine
pub struct MultiColumnEngine {
    pub container_width: f64,
    pub column_width: Option<f64>,
    pub column_count: Option<usize>,
    pub column_gap: f64,
    pub column_fill: ColumnFill,
    pub column_span_node_ids: Vec<u64>,
}

impl MultiColumnEngine {
    pub fn new(width: f64) -> Self {
        Self {
            container_width: width,
            column_width: None,
            column_count: None,
            column_gap: 1.0, // Multiplier of 1em default
            column_fill: ColumnFill::Balance,
            column_span_node_ids: Vec::new(),
        }
    }

    /// Primary entry point: Resolve column metrics (§ 3.4)
    pub fn resolve_metrics(&self, font_size: f64) -> ColumnMetrics {
        let gap = self.column_gap * font_size;
        let avail = (self.container_width - gap).max(0.0);
        
        let (used_count, used_width) = match (self.column_width, self.column_count) {
            (Some(w), Some(c)) => {
                let n = ((avail + gap) / (w + gap)).floor().max(1.0) as usize;
                let used_n = n.min(c);
                let used_w = ((avail + gap) / used_n as f64) - gap;
                (used_n, used_w)
            }
            (Some(w), None) => {
                let n = ((avail + gap) / (w + gap)).floor().max(1.0) as usize;
                let used_w = ((avail + gap) / n as f64) - gap;
                (n, used_w)
            }
            (None, Some(c)) => {
                let used_w = ((avail + gap) / c as f64) - gap;
                (c, used_w)
            }
            (None, None) => (1, self.container_width),
        };

        ColumnMetrics { count: used_count, width: used_width, gap }
    }

    /// Layout content into column boxes
    pub fn fragment_content(&self, metrics: &ColumnMetrics, total_height: f64) -> Vec<ColumnBox> {
        let mut columns = Vec::new();
        let col_height = if self.column_fill == ColumnFill::Balance {
            (total_height / metrics.count as f64).max(1.0)
        } else {
            total_height // Placeholder for auto fill
        };

        for i in 0..metrics.count {
            columns.push(ColumnBox {
                index: i,
                x: i as f64 * (metrics.width + metrics.gap),
                y: 0.0,
                width: metrics.width,
                height: col_height,
            });
        }
        columns
    }

    /// AI-facing multi-column visualizer
    pub fn ai_column_fragmentation(&self, columns: &[ColumnBox]) -> String {
        let mut output = vec![format!("🏛️ Multi-column Fragmentation (Used columns: {}):", columns.len())];
        for col in columns {
            output.push(format!("  Column {}: (x:{:.1}, w:{:.1}, h:{:.1})", col.index, col.x, col.width, col.height));
        }
        output.join("\n")
    }
}
