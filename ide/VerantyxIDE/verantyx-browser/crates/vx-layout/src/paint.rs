//! Paint order and background rendering
use crate::box_model::BoxRect;
#[derive(Debug, Clone)]
pub enum PaintPhase { Background, Border, Content, Outline }
#[derive(Debug, Clone)]
pub struct PaintCommand { pub rect: BoxRect, pub phase: PaintPhase, pub order: u32 }
#[derive(Debug, Clone, Default)]
pub struct DisplayList { pub commands: Vec<PaintCommand> }
impl DisplayList {
    pub fn new() -> Self { Self::default() }
    pub fn push(&mut self, cmd: PaintCommand) { self.commands.push(cmd); }
    pub fn sort(&mut self) { self.commands.sort_by_key(|c| c.order); }
}
