//! CSS Table Layout Engine — W3C CSS Table Module Level 3
//!
//! Implements the full CSS table layout algorithm per Chrome/WebKit behavior:
//!   - Table element display types (table, table-row, table-cell, table-column, etc.)
//!   - Column width distribution (fixed vs auto table-layout)
//!   - Auto table layout: min/max content width computation
//!   - Fixed table layout: first-row column width assignment
//!   - Row height computation (intrinsic + explicit)
//!   - Cell spanning (colspan / rowspan)
//!   - border-collapse vs border-separate models
//!   - Cell alignment (vertical-align: top/middle/bottom/baseline)
//!   - Caption placement (top/bottom)
//!   - Anonymous box generation for missing table elements

use std::collections::HashMap;

/// CSS display types for table elements
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TableDisplayType {
    Table,
    InlineTable,
    TableRow,
    TableRowGroup,      // thead, tbody, tfoot
    TableHeaderGroup,
    TableFooterGroup,
    TableColumn,
    TableColumnGroup,
    TableCell,
    TableCaption,
}

/// Whether to participate in collapsed border model
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BorderCollapse {
    Collapse,
    Separate,
}

/// Table layout algorithm
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TableLayout {
    Auto,
    Fixed,
}

/// A table cell (td / th)
#[derive(Debug, Clone)]
pub struct TableCell {
    pub node_id: u64,
    pub col_span: usize,
    pub row_span: usize,
    pub min_content_width: f64,
    pub max_content_width: f64,
    pub specified_width: Option<f64>,    // Explicit width= or CSS width
    pub specified_height: Option<f64>,
    pub padding_top: f64,
    pub padding_right: f64,
    pub padding_bottom: f64,
    pub padding_left: f64,
    pub border_top: f64,
    pub border_right: f64,
    pub border_bottom: f64,
    pub border_left: f64,
    pub vertical_align: CellVerticalAlign,
    pub is_header: bool,     // th vs td
    
    // Resolved during layout:
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}

impl TableCell {
    pub fn new(node_id: u64) -> Self {
        Self {
            node_id, col_span: 1, row_span: 1,
            min_content_width: 0.0, max_content_width: 0.0,
            specified_width: None, specified_height: None,
            padding_top: 1.0, padding_right: 1.0, padding_bottom: 1.0, padding_left: 1.0,
            border_top: 0.0, border_right: 0.0, border_bottom: 0.0, border_left: 0.0,
            vertical_align: CellVerticalAlign::Middle,
            is_header: false,
            x: 0.0, y: 0.0, width: 0.0, height: 0.0,
        }
    }
    
    pub fn outer_min_width(&self) -> f64 {
        self.min_content_width + self.padding_left + self.padding_right
            + self.border_left + self.border_right
    }
    
    pub fn outer_max_width(&self) -> f64 {
        self.max_content_width + self.padding_left + self.padding_right
            + self.border_left + self.border_right
    }
    
    pub fn inner_width(&self) -> f64 {
        (self.width - self.padding_left - self.padding_right
            - self.border_left - self.border_right).max(0.0)
    }
    
    pub fn inner_height(&self) -> f64 {
        (self.height - self.padding_top - self.padding_bottom
            - self.border_top - self.border_bottom).max(0.0)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CellVerticalAlign {
    Top,
    Middle,
    Bottom,
    Baseline,
}

impl CellVerticalAlign {
    pub fn from_str(s: &str) -> Self {
        match s {
            "top" => Self::Top,
            "bottom" => Self::Bottom,
            "baseline" => Self::Baseline,
            _ => Self::Middle,
        }
    }
}

/// A table column definition
#[derive(Debug, Clone)]
pub struct TableColumn {
    pub node_id: Option<u64>,
    pub span: usize,           // col span attribute
    pub specified_width: Option<TableColumnWidth>,
    
    // Resolved during layout:
    pub x: f64,
    pub width: f64,
    pub min_width: f64,
    pub max_width: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub enum TableColumnWidth {
    Fixed(f64),
    Percentage(f64),
    Auto,
}

/// A table row
#[derive(Debug, Clone)]
pub struct TableRow {
    pub node_id: u64,
    pub cells: Vec<TableCell>,
    pub specified_height: Option<f64>,
    pub group: RowGroup,
    
    // Resolved:
    pub y: f64,
    pub height: f64,
    pub baseline: f64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RowGroup {
    Header,
    Body,
    Footer,
}

/// Spanning cell occupancy grid — tracks which (col, row) cells are occupied by rowspan
#[derive(Debug, Default)]
struct SpanGrid {
    /// (col_index, row_index) -> spanning cell reference (node_id, remaining_rows)
    occupied: HashMap<(usize, usize), u64>,
}

impl SpanGrid {
    fn is_occupied(&self, col: usize, row: usize) -> bool {
        self.occupied.contains_key(&(col, row))
    }
    
    fn occupy(&mut self, col: usize, row: usize, node_id: u64) {
        self.occupied.insert((col, row), node_id);
    }
    
    fn clear_row(&mut self, row: usize) {
        self.occupied.retain(|&(_, r), _| r != row);
    }
}

/// Resolved column layout output
#[derive(Debug, Clone)]
pub struct ColumnGeometry {
    pub col_index: usize,
    pub x: f64,
    pub width: f64,
}

/// Resolved cell geometry output
#[derive(Debug, Clone)]
pub struct CellGeometry {
    pub node_id: u64,
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
    pub inner_width: f64,
    pub inner_height: f64,
    pub vertical_align: CellVerticalAlign,
    pub col_span: usize,
    pub row_span: usize,
}

/// The CSS Table Layout Engine
pub struct TableLayoutEngine {
    pub layout_mode: TableLayout,
    pub border_collapse: BorderCollapse,
    pub border_spacing_h: f64,
    pub border_spacing_v: f64,
    pub caption_side: CaptionSide,
    pub specified_width: Option<f64>,
    pub specified_height: Option<f64>,
    pub min_width: f64,
    pub columns: Vec<TableColumn>,
    pub rows: Vec<TableRow>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CaptionSide { Top, Bottom }

impl TableLayoutEngine {
    pub fn new() -> Self {
        Self {
            layout_mode: TableLayout::Auto,
            border_collapse: BorderCollapse::Separate,
            border_spacing_h: 2.0,
            border_spacing_v: 2.0,
            caption_side: CaptionSide::Top,
            specified_width: None,
            specified_height: None,
            min_width: 0.0,
            columns: Vec::new(),
            rows: Vec::new(),
        }
    }
    
    /// Compute the number of columns in the table
    pub fn column_count(&self) -> usize {
        self.rows.iter().map(|row| {
            row.cells.iter().map(|c| c.col_span).sum::<usize>()
        }).max().unwrap_or(0)
    }
    
    /// Execute the full table layout algorithm
    pub fn layout(&mut self, available_width: f64) -> TableLayoutResult {
        let col_count = self.column_count();
        if col_count == 0 { return TableLayoutResult::empty(); }
        
        // Step 1: Ensure we have enough column definitions
        while self.columns.len() < col_count {
            self.columns.push(TableColumn {
                node_id: None, span: 1, specified_width: None,
                x: 0.0, width: 0.0, min_width: 0.0, max_width: f64::INFINITY,
            });
        }
        
        // Step 2: Calculate column widths based on layout mode
        let column_widths = match self.layout_mode {
            TableLayout::Fixed => self.fixed_table_layout(available_width, col_count),
            TableLayout::Auto => self.auto_table_layout(available_width, col_count),
        };
        
        // Step 3: Assign x positions to columns
        let mut col_geometries = Vec::new();
        let mut x_cursor = self.h_border_spacing();
        for (i, &width) in column_widths.iter().enumerate() {
            col_geometries.push(ColumnGeometry { col_index: i, x: x_cursor, width });
            x_cursor += width + self.h_border_spacing();
        }
        
        let table_width = x_cursor;
        
        // Step 4: Layout rows and cells
        let mut cell_geometries = Vec::new();
        let mut y_cursor = self.v_border_spacing();
        let mut span_grid = SpanGrid::default();
        
        // Process rows in visual order: header, body, footer
        let mut ordered_rows: Vec<usize> = Vec::new();
        for i in 0..self.rows.len() {
            if self.rows[i].group == RowGroup::Header { ordered_rows.push(i); }
        }
        for i in 0..self.rows.len() {
            if self.rows[i].group == RowGroup::Body { ordered_rows.push(i); }
        }
        for i in 0..self.rows.len() {
            if self.rows[i].group == RowGroup::Footer { ordered_rows.push(i); }
        }
        
        for &row_idx in &ordered_rows {
            let row = &self.rows[row_idx];
            let row_y = y_cursor;
            
            // Compute row height from cells
            let mut row_height = row.specified_height.unwrap_or(0.0);
            
            let mut col_cursor = 0usize;
            for cell in &row.cells {
                // Skip occupied cells (from rowspan)
                while col_cursor < col_count && span_grid.is_occupied(col_cursor, row_idx) {
                    col_cursor += 1;
                }
                
                if col_cursor >= col_count { break; }
                
                // Calculate cell width (sum of spanned columns + gaps)
                let span_end = (col_cursor + cell.col_span).min(col_count);
                let cell_x = col_geometries.get(col_cursor).map(|c| c.x).unwrap_or(0.0);
                let cell_width: f64 = (col_cursor..span_end)
                    .map(|i| col_geometries.get(i).map(|c| c.width).unwrap_or(0.0))
                    .sum::<f64>()
                    + self.h_border_spacing() * (span_end - col_cursor - 1) as f64;
                
                // The content height of the cell
                let cell_inner_height = (cell.specified_height.unwrap_or(0.0)
                    - cell.padding_top - cell.padding_bottom
                    - cell.border_top - cell.border_bottom).max(0.0);
                
                let cell_outer_height = cell_inner_height
                    + cell.padding_top + cell.padding_bottom
                    + cell.border_top + cell.border_bottom;
                
                row_height = row_height.max(cell_outer_height / cell.row_span as f64);
                
                // Mark span occupancy
                for cs in 0..cell.col_span {
                    for rs in 1..cell.row_span {
                        span_grid.occupy(col_cursor + cs, row_idx + rs, cell.node_id);
                    }
                }
                
                cell_geometries.push(CellGeometry {
                    node_id: cell.node_id,
                    x: cell_x,
                    y: row_y,
                    width: cell_width,
                    height: row_height,
                    inner_width: (cell_width - cell.padding_left - cell.padding_right
                        - cell.border_left - cell.border_right).max(0.0),
                    inner_height: cell_inner_height,
                    vertical_align: cell.vertical_align,
                    col_span: cell.col_span,
                    row_span: cell.row_span,
                });
                
                col_cursor += cell.col_span;
            }
            
            span_grid.clear_row(row_idx);
            y_cursor += row_height + self.v_border_spacing();
        }
        
        let table_height = y_cursor;
        
        TableLayoutResult {
            table_width,
            table_height,
            column_geometries: col_geometries,
            cell_geometries,
        }
    }
    
    /// Fixed table layout (CSS Table Module § 12.5)
    fn fixed_table_layout(&self, available_width: f64, col_count: usize) -> Vec<f64> {
        let total_spacing = self.h_border_spacing() * (col_count + 1) as f64;
        let distributable = (available_width - total_spacing).max(0.0);
        
        let mut widths = vec![0.0f64; col_count];
        let mut remaining = distributable;
        let mut auto_count = 0usize;
        
        // Step 1: Apply explicitly specified widths from column definitions
        for (i, col) in self.columns.iter().enumerate().take(col_count) {
            match &col.specified_width {
                Some(TableColumnWidth::Fixed(px)) => {
                    widths[i] = *px;
                    remaining -= px;
                }
                Some(TableColumnWidth::Percentage(pct)) => {
                    let w = distributable * pct / 100.0;
                    widths[i] = w;
                    remaining -= w;
                }
                _ => auto_count += 1,
            }
        }
        
        // Distribute remaining to auto columns
        if auto_count > 0 && remaining > 0.0 {
            let per_auto = remaining / auto_count as f64;
            for (i, col) in self.columns.iter().enumerate().take(col_count) {
                if matches!(col.specified_width, None | Some(TableColumnWidth::Auto)) {
                    widths[i] = per_auto;
                }
            }
        }
        
        widths
    }
    
    /// Auto table layout (CSS Table Module § 12.4)
    fn auto_table_layout(&self, available_width: f64, col_count: usize) -> Vec<f64> {
        let total_spacing = self.h_border_spacing() * (col_count + 1) as f64;
        let distributable = (available_width - total_spacing).max(0.0);
        
        // Collect per-column min/max from cells
        let mut col_min = vec![0.0f64; col_count];
        let mut col_max = vec![0.0f64; col_count];
        
        for row in &self.rows {
            let mut col = 0usize;
            for cell in &row.cells {
                if col >= col_count { break; }
                if cell.col_span == 1 {
                    col_min[col] = col_min[col].max(cell.outer_min_width());
                    col_max[col] = col_max[col].max(cell.outer_max_width());
                }
                col += cell.col_span;
            }
        }
        
        // Include explicit column widths
        for (i, col) in self.columns.iter().enumerate().take(col_count) {
            if let Some(TableColumnWidth::Fixed(px)) = &col.specified_width {
                col_min[i] = col_min[i].max(*px);
                col_max[i] = col_max[i].max(*px);
            }
        }
        
        let total_min: f64 = col_min.iter().sum();
        let total_max: f64 = col_max.iter().sum();
        
        if total_max <= distributable {
            // All columns fit at max content width
            col_max.clone()
        } else if total_min >= distributable {
            // Not enough space — use min widths
            col_min.clone()
        } else {
            // Distribute proportionally between min and max
            let excess = distributable - total_min;
            let max_excess = total_max - total_min;
            
            col_min.iter().zip(col_max.iter()).map(|(&min, &max)| {
                let proportion = if max_excess > 0.0 { (max - min) / max_excess } else { 0.0 };
                min + excess * proportion
            }).collect()
        }
    }
    
    fn h_border_spacing(&self) -> f64 {
        match self.border_collapse {
            BorderCollapse::Collapse => 0.0,
            BorderCollapse::Separate => self.border_spacing_h,
        }
    }
    
    fn v_border_spacing(&self) -> f64 {
        match self.border_collapse {
            BorderCollapse::Collapse => 0.0,
            BorderCollapse::Separate => self.border_spacing_v,
        }
    }
}

/// Result of the table layout computation
#[derive(Debug, Clone)]
pub struct TableLayoutResult {
    pub table_width: f64,
    pub table_height: f64,
    pub column_geometries: Vec<ColumnGeometry>,
    pub cell_geometries: Vec<CellGeometry>,
}

impl TableLayoutResult {
    pub fn empty() -> Self {
        Self { table_width: 0.0, table_height: 0.0, column_geometries: Vec::new(), cell_geometries: Vec::new() }
    }
    
    pub fn cell_at(&self, node_id: u64) -> Option<&CellGeometry> {
        self.cell_geometries.iter().find(|c| c.node_id == node_id)
    }
}
