//! CSS Fill and Stroke Module Level 3 — W3C CSS Fill and Stroke
//!
//! Implements SVG-compatible painting properties for HTML elements:
//!   - fill (§ 2): <paint> (none, currentColor, <color>, <url>)
//!   - fill-rule (§ 2.1): nonzero, evenodd
//!   - fill-opacity (§ 2.2): [0.0, 1.0] alpha multiplier
//!   - stroke (§ 3): <paint> for the element outline
//!   - stroke-width (§ 3.1) and stroke-opacity (§ 3.2)
//!   - stroke-linecap (§ 3.4): butt, round, square
//!   - stroke-linejoin (§ 3.5): miter, round, bevel
//!   - stroke-dasharray (§ 4.1) and stroke-dashoffset (§ 4.2): Creating dashed patterns
//!   - AI-facing: Painting layer properties visualizer and vector geometry metrics

use std::collections::HashMap;

/// Fill rules (§ 2.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FillRule { NonZero, EvenOdd }

/// Line caps (§ 3.4)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LineCap { Butt, Round, Square }

/// Line joins (§ 3.5)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LineJoin { Miter, Round, Bevel }

/// Painting parameters for a node
#[derive(Debug, Clone)]
pub struct PaintProps {
    pub fill: String,
    pub fill_rule: FillRule,
    pub fill_opacity: f32,
    pub stroke: String,
    pub stroke_width: f64,
    pub stroke_opacity: f32,
    pub stroke_linecap: LineCap,
    pub stroke_linejoin: LineJoin,
    pub stroke_dasharray: Vec<f64>,
}

impl PaintProps {
    pub fn new() -> Self {
        Self {
            fill: "currentColor".into(),
            fill_rule: FillRule::NonZero,
            fill_opacity: 1.0,
            stroke: "none".into(),
            stroke_width: 1.0,
            stroke_opacity: 1.0,
            stroke_linecap: LineCap::Butt,
            stroke_linejoin: LineJoin::Miter,
            stroke_dasharray: Vec::new(),
        }
    }
}

/// The CSS Fill and Stroke Engine
pub struct FillStrokeEngine {
    pub nodes: HashMap<u64, PaintProps>, // node_id -> properties
}

impl FillStrokeEngine {
    pub fn new() -> Self {
        Self { nodes: HashMap::new() }
    }

    pub fn set_paint_props(&mut self, node_id: u64, props: PaintProps) {
        self.nodes.insert(node_id, props);
    }

    /// AI-facing fill/stroke summary
    pub fn ai_paint_summary(&self, node_id: u64) -> String {
        if let Some(props) = self.nodes.get(&node_id) {
            format!("🖌️ Paint Props (Node #{}): Fill: {} (Op:{:.1}), Stroke: {} (W:{:.1}, Op:{:.1})", 
                node_id, props.fill, props.fill_opacity, props.stroke, props.stroke_width, props.stroke_opacity)
        } else {
            format!("Node #{} uses default paint", node_id)
        }
    }
}
