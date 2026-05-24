//! CSS Table layout
use crate::box_model::BoxRect;
#[derive(Debug, Clone, Default)]
pub struct TableLayout {
    pub columns: Vec<f32>,
    pub rows: Vec<f32>,
    pub cells: Vec<TableCell>,
}
#[derive(Debug, Clone)]
pub struct TableCell { pub row: usize, pub col: usize, pub row_span: usize, pub col_span: usize, pub rect: BoxRect }
impl TableLayout {
    pub fn new() -> Self { Self::default() }
    pub fn add_cell(&mut self, cell: TableCell) { self.cells.push(cell); }
}
