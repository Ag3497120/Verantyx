//! CSS Float layout
use crate::box_model::BoxRect;
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum FloatSide { Left, Right }
#[derive(Debug, Clone)]
pub struct FloatBox { pub rect: BoxRect, pub side: FloatSide, pub clear: ClearMode }
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum ClearMode { None, Left, Right, Both, InlineStart, InlineEnd }
#[derive(Debug, Clone, Default)]
pub struct FloatContext { pub floats: Vec<FloatBox> }
impl FloatContext {
    pub fn new() -> Self { Self::default() }
    pub fn add(&mut self, float: FloatBox) { self.floats.push(float); }
    pub fn top_of_clear(&self, side: ClearMode, y: f32) -> f32 {
        self.floats.iter().filter(|f| match side {
            ClearMode::Left => f.side == FloatSide::Left,
            ClearMode::Right => f.side == FloatSide::Right,
            ClearMode::Both => true,
            _ => false,
        }).map(|f| f.rect.bottom()).fold(y, f32::max)
    }
}
