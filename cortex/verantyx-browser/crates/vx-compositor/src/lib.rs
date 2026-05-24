//! vx-compositor — AI Headless Cognitive Compositor
//!
//! Replaces traditional pixel rendering with semantic layer stacking, enabling
//! perfect hit-testing (z-index, occlusion algorithms) for self-driving AI agents.

pub mod layer;
pub mod paint;
pub mod occlusion;
pub mod stacking;

pub use layer::{LayerTree, CompositingLayer, LayerBounds};
pub use paint::PaintEngine;
pub use occlusion::OcclusionEngine;
