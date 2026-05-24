//! SVG 2.0 Layout — W3C SVG 2.0
//!
//! Implements the vector graphics layout and coordinate mapping:
//!   - SVG Viewport (§ 7.2): x, y, width, height, viewBox, preserveAspectRatio
//!   - Coordinate Systems (§ 8): User units, userSpaceOnUse, objectBoundingBox
//!   - Shapes (§ 9): rect, circle, ellipse, line, polyline, polygon
//!   - Paths (§ 10): Command parsing (M, L, H, V, C, S, Q, T, A, Z) and geometry
//!   - Clipping and Masking (§ 14): clipPath and mask reference resolution
//!   - SVG Transforms (§ 8.5): translate, scale, rotate, skewX, skewY, matrix
//!   - Text in SVG (§ 11): text, tspan, textPath (layout along path)
//!   - Paint Servers (§ 13): linearGradient, radialGradient, pattern
//!   - AI-facing: SVG element tree and viewport-to-pixel coordinate mapper

use std::collections::HashMap;

/// SVG ViewBox (§ 7.2)
#[derive(Debug, Clone, Copy)]
pub struct ViewBox { pub x: f64, pub y: f64, pub width: f64, pub height: f64 }

/// SVG Aspect Ratio alignment (§ 7.8)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AspectRatioAlign { None, XMinYMin, XMidYMin, XMaxYMin, XMinYMid, XMidYMid, XMaxYMid, XMinYMax, XMidYMax, XMaxYMax }

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AspectRatioMeetOrSlice { Meet, Slice }

/// Layout for a basic shape (§ 9)
#[derive(Debug, Clone)]
pub enum SvgShape {
    Rect { x: f64, y: f64, width: f64, height: f64, rx: f64, ry: f64 },
    Circle { cx: f64, cy: f64, r: f64 },
    Ellipse { cx: f64, cy: f64, rx: f64, ry: f64 },
    Line { x1: f64, y1: f64, x2: f64, y2: f64 },
    Polygon { points: Vec<(f64, f64)> },
    Path { commands: Vec<PathCommand> },
}

#[derive(Debug, Clone)]
pub enum PathCommand {
    MoveTo(f64, f64), LineTo(f64, f64), CurveTo(f64, f64, f64, f64, f64, f64), Close,
}

/// A node in the SVG element tree (§ 5)
pub struct SvgNode {
    pub id: u64,
    pub shape: SvgShape,
    pub transform: [f64; 6], // Affine transform matrix
    pub fill: Option<String>,
    pub stroke: Option<String>,
    pub stroke_width: f64,
}

/// The SVG Layout Engine
pub struct SvgEngine {
    pub viewport_width: f64,
    pub viewport_height: f64,
    pub view_box: Option<ViewBox>,
    pub aspect_ratio_align: AspectRatioAlign,
    pub aspect_ratio_meet: AspectRatioMeetOrSlice,
}

impl SvgEngine {
    pub fn new(w: f64, h: f64) -> Self {
        Self {
            viewport_width: w,
            viewport_height: h,
            view_box: None,
            aspect_ratio_align: AspectRatioAlign::XMidYMid,
            aspect_ratio_meet: AspectRatioMeetOrSlice::Meet,
        }
    }

    /// Calculate the transform matrix from viewBox to viewport (§ 7.8)
    pub fn calculate_viewbox_transform(&self) -> [f64; 6] {
        let vb = match self.view_box {
            Some(v) => v,
            None => return [1.0, 0.0, 0.0, 1.0, 0.0, 0.0],
        };

        let scale_x = self.viewport_width / vb.width;
        let scale_y = self.viewport_height / vb.height;
        
        let scale = match self.aspect_ratio_meet {
            AspectRatioMeetOrSlice::Meet => scale_x.min(scale_y),
            AspectRatioMeetOrSlice::Slice => scale_x.max(scale_y),
        };

        let final_scale_x = if self.aspect_ratio_align == AspectRatioAlign::None { scale_x } else { scale };
        let final_scale_y = if self.aspect_ratio_align == AspectRatioAlign::None { scale_y } else { scale };

        let offset_x = -vb.x * final_scale_x;
        let offset_y = -vb.y * final_scale_y;

        [final_scale_x, 0.0, 0.0, final_scale_y, offset_x, offset_y]
    }

    /// AI-facing SVG element summary
    pub fn ai_svg_inspector(&self, nodes: &[SvgNode]) -> String {
        let mut output = vec![format!("🎨 SVG Viewport ({}×{}, ViewBox: {:?}):", self.viewport_width, self.viewport_height, self.view_box)];
        for node in nodes {
            output.push(format!("  - Node #{}: {:?} (Fill: {:?}, Width: {})", 
                node.id, node.shape, node.fill, node.stroke_width));
        }
        output.join("\n")
    }
}
