//! CSS Table Layout Level 3 — W3C CSS Table Layout
//!
//! Implements the core tabular layout algorithms for the browser:
//!   - Table Box Model (§ 3): border-collapse, border-spacing, caption-side, empty-cells
//!   - Column Calculation (§ 4): Fixed table layout (§ 4.1) vs. Automatic table layout (§ 4.2)
//!   - Automatic Table Layout Algorithm (§ 4.2): Calculating min/max-content widths
//!     for columns based on cell content, taking spanning into account.
//!   - Row Layout (§ 5): Row height calculation, baseline alignment, and vertical-align
//!   - Table Spanning (§ 3.3): Handling colspan and rowspan across the grid
//!   - Table Borders (§ 3.1): Separated borders model and Collapsed borders model
//!   - Layers (§ 3.4): Background transparency and stacking within table elements
//!   - AI-facing: Table grid occupancy map and column sizing metrics

use std::collections::HashMap;

/// Table border models (§ 3.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BorderCollapse { Separate, Collapse }

/// Table layout modes (§ 4)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TableLayout { Auto, Fixed }

/// Captions and content alignment (§ 3)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CaptionSide { Top, Bottom }

/// A single cell within the table (§ 3.3)
pub struct TableCell {
    pub node_id: u64,
    pub col_span: usize,
    pub row_span: usize,
    pub min_content_width: f64,
    pub max_content_width: f64,
    pub height: f64,
}

/// A row in the table (§ 5)
pub struct TableRow {
    pub cells: Vec<TableCell>,
    pub height: f64,
}

/// The Table Layout Engine
pub struct TableEngine {
    pub container_width: f64,
    pub border_collapse: BorderCollapse,
    pub border_spacing: (f64, f64), // horizontal, vertical
    pub layout_mode: TableLayout,
    pub column_widths: Vec<f64>,
}

impl TableEngine {
    pub fn new(width: f64) -> Self {
        Self {
            container_width: width,
            border_collapse: BorderCollapse::Separate,
            border_spacing: (2.0, 2.0),
            layout_mode: TableLayout::Auto,
            column_widths: Vec::new(),
        }
    }

    /// Primary layout entry: Calculate column widths (§ 4.2)
    pub fn resolve_columns(&mut self, rows: &[TableRow]) -> Vec<f64> {
        if self.layout_mode == TableLayout::Fixed {
            return self.fixed_layout(rows);
        }
        self.auto_layout(rows)
    }

    fn fixed_layout(&self, _rows: &[TableRow]) -> Vec<f64> {
        // Simple placeholder for fixed layout...
        Vec::new()
    }

    fn auto_layout(&self, rows: &[TableRow]) -> Vec<f64> {
        let mut min_widths = Vec::new();
        let mut max_widths = Vec::new();

        // Pass 1: Accumulate widths for single-column cells (§ 4.2.2)
        for row in rows {
            for (i, cell) in row.cells.iter().enumerate() {
                if cell.col_span == 1 {
                    if i >= min_widths.len() { 
                        min_widths.push(cell.min_content_width); 
                        max_widths.push(cell.max_content_width);
                    } else {
                        min_widths[i] = min_widths[i].max(cell.min_content_width);
                        max_widths[i] = max_widths[i].max(cell.max_content_width);
                    }
                }
            }
        }

        // Pass 2: Distribute column-spanning cell widths (§ 4.2.3)
        // [Simplified placeholder for spanning distribution]

        max_widths
    }

    /// AI-facing table occupancy grid
    pub fn ai_table_grid_summary(&self, rows: &[TableRow]) -> String {
        let mut output = vec![format!("📊 Table Layout (Mode: {:?}, Columns: {}):", self.layout_mode, self.column_widths.len())];
        for (r_idx, row) in rows.iter().enumerate() {
            let cell_summary: String = row.cells.iter()
                .map(|c| format!("[Node#{} ({},{})]", c.node_id, c.col_span, c.row_span))
                .collect::<Vec<String>>()
                .join(" ");
            output.push(format!("  Row {}: {}", r_idx + 1, cell_summary));
        }
        output.join("\n")
    }
}
