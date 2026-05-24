//! Dimension/sizing constraints for layout
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum AvailableSpace { Definite(f32), Indefinite, MinContent, MaxContent }
impl AvailableSpace {
    pub fn to_f32(self) -> Option<f32> { match self { Self::Definite(v) => Some(v), _ => None } }
    pub fn is_definite(self) -> bool { matches!(self, Self::Definite(_)) }
}
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct SizingConstraint { pub min: f32, pub max: f32, pub preferred: Option<f32> }
impl SizingConstraint {
    pub fn unconstrained() -> Self { Self { min: 0.0, max: f32::INFINITY, preferred: None } }
    pub fn fixed(size: f32) -> Self { Self { min: size, max: size, preferred: Some(size) } }
    pub fn clamp(&self, v: f32) -> f32 { v.max(self.min).min(self.max) }
}
