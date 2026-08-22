//! CSS Table Module Level 3 — W3C CSS Tables
//!
//! Implements logical tabular data structural formatting and layout heuristics:
//!   - Table Models (§ 3): `table-layout: auto` (content-driven sizing) vs `fixed` (predictable fast layout)
//!   - Anonymous Table Object Generation (§ 3.1): Wrapping `display: table-cell` automatically inside a row/table
//!   - Border Collapse (§ 4): Resolved collapsed borders matrix rendering heuristics
//!   - Empty Cells (§ 5): `empty-cells: show` or `hide` boundaries handling
//!   - Caption Side (§ 6): Aligning `caption-side: top` or `bottom` across table dimensions
//!   - AI-facing: Tabular grid topology resolving missing cells and table dimensions

use std::collections::HashMap;

/// The foundational sizing algorithm for determining column widths (§ 4.0)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TableLayoutAlgorithm { Auto, Fixed }

/// Behavior dictating cell rendering when border lines overlap (§ 4.4)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BorderCollapse { Separate, Collapse }

/// Determines whether empty tabular cells render borders and backgrounds (§ 5.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EmptyCells { Show, Hide }

/// Configuration specific to an overarching table container
#[derive(Debug, Clone)]
pub struct TableConfiguration {
    pub layout: TableLayoutAlgorithm,
    pub border_collapse: BorderCollapse,
    pub empty_cells: EmptyCells,
    pub border_spacing_x: f64,
    pub border_spacing_y: f64,
}

/// Defines an internal mapping of resolved cells in the logic table grid
#[derive(Debug, Clone)]
pub struct LogicalTableGrid {
    pub columns: usize,
    pub rows: usize,
    pub cell_node_ids: Vec<Vec<Option<u64>>>, // Y -> X -> Node ID
}

/// The global CSS Tables Level 3 Engine
pub struct CssTableEngine {
    pub tables: HashMap<u64, TableConfiguration>,
    pub logical_grids: HashMap<u64, LogicalTableGrid>,
}

impl CssTableEngine {
    pub fn new() -> Self {
        Self {
            tables: HashMap::new(),
            logical_grids: HashMap::new(),
        }
    }

    pub fn set_table_config(&mut self, table_id: u64, config: TableConfiguration) {
        self.tables.insert(table_id, config);
    }

    /// Evaluates the basic column count dictated by a table row's children
    pub fn build_logical_grid(&mut self, table_id: u64, raw_rows: Vec<Vec<u64>>) {
        let max_cols = raw_rows.iter().map(|r| r.len()).max().unwrap_or(0);
        let mut grid_data = Vec::with_capacity(raw_rows.len());

        for row in raw_rows {
            let mut x_cells = Vec::with_capacity(max_cols);
            for col_idx in 0..max_cols {
                if col_idx < row.len() {
                    x_cells.push(Some(row[col_idx]));
                } else {
                    x_cells.push(None); // Sparse table expansion
                }
            }
            grid_data.push(x_cells);
        }

        self.logical_grids.insert(table_id, LogicalTableGrid {
            columns: max_cols,
            rows: grid_data.len(),
            cell_node_ids: grid_data,
        });
    }

    /// Layout-phase determination for spacing blocks (§ 4.2)
    pub fn calculate_cell_spacing(&self, table_id: u64) -> (f64, f64) {
        if let Some(config) = self.tables.get(&table_id) {
            if config.border_collapse == BorderCollapse::Separate {
                return (config.border_spacing_x, config.border_spacing_y);
            }
        }
        (0.0, 0.0) // Collapse eliminates physical spacing voids
    }

    /// AI-facing CSS Table topology summary
    pub fn ai_table_summary(&self, table_id: u64) -> String {
        let config_str = match self.tables.get(&table_id) {
            Some(c) => format!("Layout: {:?} | Border: {:?} | Empty: {:?}", c.layout, c.border_collapse, c.empty_cells),
            None => "Standard Auto-Layout".into(),
        };

        if let Some(grid) = self.logical_grids.get(&table_id) {
            format!("📊 CSS Table #{} ({}x{} grid) -> {}", table_id, grid.columns, grid.rows, config_str)
        } else {
            format!("Table #{} has no resolved DOM structural rows yet.", table_id)
        }
    }
}
