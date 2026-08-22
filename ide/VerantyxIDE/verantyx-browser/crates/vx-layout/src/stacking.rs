//! Stacking context and paint layers
use crate::box_model::BoxRect;
#[derive(Debug, Clone)]
pub struct PaintLayer { pub rect: BoxRect, pub z_index: i32, pub opacity: f32 }
#[derive(Debug, Clone, Default)]
pub struct StackingContext { pub layers: Vec<PaintLayer>, pub z_index: i32 }
impl StackingContext {
    pub fn new() -> Self { Self::default() }
    pub fn push(&mut self, layer: PaintLayer) { self.layers.push(layer); }
    pub fn sort(&mut self) { self.layers.sort_by_key(|l| l.z_index); }
}
