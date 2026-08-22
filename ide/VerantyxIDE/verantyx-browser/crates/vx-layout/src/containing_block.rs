//! Containing block and formatting context
use crate::box_model::BoxRect;
#[derive(Debug, Clone, PartialEq)]
pub enum FormattingContext { Block, Inline, Flex, Grid, Table, Flow }
#[derive(Debug, Clone)]
pub struct ContainingBlock { pub rect: BoxRect, pub context: FormattingContext, pub rtl: bool }
impl ContainingBlock {
    pub fn viewport(width: f32, height: f32) -> Self { Self { rect: BoxRect::new(0.0, 0.0, width, height), context: FormattingContext::Block, rtl: false } }
    pub fn width(&self) -> f32 { self.rect.width }
    pub fn height(&self) -> f32 { self.rect.height }
}
