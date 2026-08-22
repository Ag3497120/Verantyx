//! CSS Box Model — Complete implementation of the CSS box model
//!
//! Implements: content box, padding box, border box, margin box,
//! box-sizing, writing modes, logical properties

use std::fmt;

use serde::{Serialize, Deserialize};

/// A rectangle with f32 coordinates
#[derive(Debug, Clone, Copy, PartialEq, Default, Serialize, Deserialize)]
pub struct BoxRect {
    pub x: f32,
    pub y: f32,
    pub width: f32,
    pub height: f32,
}

impl BoxRect {
    pub fn new(x: f32, y: f32, width: f32, height: f32) -> Self {
        Self { x, y, width, height }
    }

    pub fn zero() -> Self { Self::default() }

    pub fn right(&self) -> f32 { self.x + self.width }
    pub fn bottom(&self) -> f32 { self.y + self.height }

    pub fn contains(&self, px: f32, py: f32) -> bool {
        px >= self.x && px <= self.right() && py >= self.y && py <= self.bottom()
    }

    pub fn intersects(&self, other: &Self) -> bool {
        self.x < other.right() && self.right() > other.x &&
        self.y < other.bottom() && self.bottom() > other.y
    }

    pub fn union(&self, other: &Self) -> Self {
        let x = self.x.min(other.x);
        let y = self.y.min(other.y);
        let right = self.right().max(other.right());
        let bottom = self.bottom().max(other.bottom());
        Self::new(x, y, right - x, bottom - y)
    }

    pub fn intersection(&self, other: &Self) -> Option<Self> {
        let x = self.x.max(other.x);
        let y = self.y.max(other.y);
        let right = self.right().min(other.right());
        let bottom = self.bottom().min(other.bottom());
        if right > x && bottom > y {
            Some(Self::new(x, y, right - x, bottom - y))
        } else {
            None
        }
    }

    pub fn translate(&self, dx: f32, dy: f32) -> Self {
        Self::new(self.x + dx, self.y + dy, self.width, self.height)
    }

    pub fn scale(&self, sx: f32, sy: f32) -> Self {
        Self::new(self.x * sx, self.y * sy, self.width * sx, self.height * sy)
    }

    pub fn expand(&self, amount: f32) -> Self {
        Self::new(self.x - amount, self.y - amount, self.width + 2.0 * amount, self.height + 2.0 * amount)
    }

    pub fn shrink(&self, amount: f32) -> Self {
        self.expand(-amount)
    }

    pub fn center_x(&self) -> f32 { self.x + self.width / 2.0 }
    pub fn center_y(&self) -> f32 { self.y + self.height / 2.0 }
    pub fn area(&self) -> f32 { self.width * self.height }
    pub fn is_empty(&self) -> bool { self.width <= 0.0 || self.height <= 0.0 }
    pub fn aspect_ratio(&self) -> f32 { if self.height > 0.0 { self.width / self.height } else { 0.0 } }
}

impl fmt::Display for BoxRect {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "({:.1}, {:.1}, {:.1}×{:.1})", self.x, self.y, self.width, self.height)
    }
}

/// Four-sided edge values (margin, padding, border)
#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct BoxEdges {
    pub top: f32,
    pub right: f32,
    pub bottom: f32,
    pub left: f32,
}

impl BoxEdges {
    pub fn new(top: f32, right: f32, bottom: f32, left: f32) -> Self {
        Self { top, right, bottom, left }
    }

    pub fn all(value: f32) -> Self {
        Self { top: value, right: value, bottom: value, left: value }
    }

    pub fn zero() -> Self { Self::default() }

    pub fn horizontal(&self) -> f32 { self.left + self.right }
    pub fn vertical(&self) -> f32 { self.top + self.bottom }

    pub fn is_zero(&self) -> bool {
        self.top == 0.0 && self.right == 0.0 && self.bottom == 0.0 && self.left == 0.0
    }

    /// Logical start (inline-start = left in LTR)
    pub fn inline_start(&self, rtl: bool) -> f32 {
        if rtl { self.right } else { self.left }
    }

    /// Logical end (inline-end = right in LTR)
    pub fn inline_end(&self, rtl: bool) -> f32 {
        if rtl { self.left } else { self.right }
    }

    pub fn block_start(&self) -> f32 { self.top }
    pub fn block_end(&self) -> f32 { self.bottom }
}

/// Corner radii
#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct BorderRadii {
    pub top_left: (f32, f32),     // (x, y) radii
    pub top_right: (f32, f32),
    pub bottom_right: (f32, f32),
    pub bottom_left: (f32, f32),
}

impl BorderRadii {
    pub fn uniform(r: f32) -> Self {
        Self {
            top_left: (r, r),
            top_right: (r, r),
            bottom_right: (r, r),
            bottom_left: (r, r),
        }
    }

    pub fn is_zero(&self) -> bool {
        self.top_left == (0.0, 0.0) && self.top_right == (0.0, 0.0) &&
        self.bottom_right == (0.0, 0.0) && self.bottom_left == (0.0, 0.0)
    }

    /// Inflate radii to fit within a box (CSS spec constraint)
    pub fn constrain(&self, width: f32, height: f32) -> Self {
        let scale = {
            let s1 = width / (self.top_left.0 + self.top_right.0);
            let s2 = width / (self.bottom_left.0 + self.bottom_right.0);
            let s3 = height / (self.top_left.1 + self.bottom_left.1);
            let s4 = height / (self.top_right.1 + self.bottom_right.1);
            let min = s1.min(s2).min(s3).min(s4);
            if min < 1.0 { min } else { 1.0 }
        };
        Self {
            top_left: (self.top_left.0 * scale, self.top_left.1 * scale),
            top_right: (self.top_right.0 * scale, self.top_right.1 * scale),
            bottom_right: (self.bottom_right.0 * scale, self.bottom_right.1 * scale),
            bottom_left: (self.bottom_left.0 * scale, self.bottom_left.1 * scale),
        }
    }
}

/// The box model for a single element
#[derive(Debug, Clone, Default)]
pub struct BoxModel {
    /// Content box position/size
    pub content: BoxRect,
    /// Padding edges
    pub padding: BoxEdges,
    /// Border edges
    pub border: BoxEdges,
    /// Margin edges
    pub margin: BoxEdges,
    /// Border radii
    pub border_radii: BorderRadii,
}

impl BoxModel {
    pub fn new() -> Self { Self::default() }

    /// The padding box (content + padding)
    pub fn padding_box(&self) -> BoxRect {
        BoxRect::new(
            self.content.x - self.padding.left,
            self.content.y - self.padding.top,
            self.content.width + self.padding.horizontal(),
            self.content.height + self.padding.vertical(),
        )
    }

    /// The border box (padding box + border)
    pub fn border_box(&self) -> BoxRect {
        let pb = self.padding_box();
        BoxRect::new(
            pb.x - self.border.left,
            pb.y - self.border.top,
            pb.width + self.border.horizontal(),
            pb.height + self.border.vertical(),
        )
    }

    /// The margin box (border box + margin)
    pub fn margin_box(&self) -> BoxRect {
        let bb = self.border_box();
        BoxRect::new(
            bb.x - self.margin.left,
            bb.y - self.margin.top,
            bb.width + self.margin.horizontal(),
            bb.height + self.margin.vertical(),
        )
    }

    /// Total width including all edges
    pub fn total_width(&self) -> f32 {
        self.content.width + self.padding.horizontal() + self.border.horizontal() + self.margin.horizontal()
    }

    /// Total height including all edges
    pub fn total_height(&self) -> f32 {
        self.content.height + self.padding.vertical() + self.border.vertical() + self.margin.vertical()
    }

    /// Check if a point is inside the border box (hit test)
    pub fn hit_test(&self, x: f32, y: f32) -> HitResult {
        let bb = self.border_box();
        let pb = self.padding_box();
        let cb = self.content;

        if !bb.contains(x, y) {
            return HitResult::Miss;
        }
        if !pb.contains(x, y) {
            return HitResult::Border;
        }
        if !cb.contains(x, y) {
            return HitResult::Padding;
        }
        HitResult::Content
    }
}

/// Result of a point-in-box hit test
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum HitResult {
    Miss,
    Border,
    Padding,
    Content,
}

/// A fully computed box (with position in the page)
#[derive(Debug, Clone, Default)]
pub struct ComputedBox {
    pub model: BoxModel,
    /// Position in the page coordinate system (after layout)
    pub screen_x: f32,
    pub screen_y: f32,
    pub paint_order: u32,
    pub stacking_level: i32,
    pub visible: bool,
    pub overflow_visible: bool,
}

impl ComputedBox {
    pub fn new(model: BoxModel) -> Self {
        Self { model, screen_x: 0.0, screen_y: 0.0, paint_order: 0, stacking_level: 0, visible: true, overflow_visible: true }
    }

    pub fn absolute_border_box(&self) -> BoxRect {
        let bb = self.model.border_box();
        BoxRect::new(bb.x + self.screen_x, bb.y + self.screen_y, bb.width, bb.height)
    }

    pub fn absolute_content_box(&self) -> BoxRect {
        let cb = self.model.content;
        BoxRect::new(cb.x + self.screen_x, cb.y + self.screen_y, cb.width, cb.height)
    }
}

/// CSS box-sizing modes
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum BoxSizingMode {
    ContentBox,
    BorderBox,
}

/// Apply box-sizing to resolve content width
pub fn resolve_content_width(
    specified_width: Option<f32>,
    padding: &BoxEdges,
    border: &BoxEdges,
    mode: BoxSizingMode,
) -> Option<f32> {
    match (specified_width, mode) {
        (None, _) => None,
        (Some(w), BoxSizingMode::ContentBox) => Some(w.max(0.0)),
        (Some(w), BoxSizingMode::BorderBox) => {
            let deductions = padding.horizontal() + border.horizontal();
            Some((w - deductions).max(0.0))
        }
    }
}

/// Apply box-sizing to resolve content height
pub fn resolve_content_height(
    specified_height: Option<f32>,
    padding: &BoxEdges,
    border: &BoxEdges,
    mode: BoxSizingMode,
) -> Option<f32> {
    match (specified_height, mode) {
        (None, _) => None,
        (Some(h), BoxSizingMode::ContentBox) => Some(h.max(0.0)),
        (Some(h), BoxSizingMode::BorderBox) => {
            let deductions = padding.vertical() + border.vertical();
            Some((h - deductions).max(0.0))
        }
    }
}

/// Margin collapsing
///
/// CSS margin collapsing rules (positive/negative margin combination)
pub fn collapse_margins(margins: &[f32]) -> f32 {
    let max_positive = margins.iter().cloned().filter(|&m| m >= 0.0).fold(0.0f32, f32::max);
    let min_negative = margins.iter().cloned().filter(|&m| m < 0.0).fold(0.0f32, f32::min);

    if max_positive > 0.0 && min_negative < 0.0 {
        max_positive + min_negative // CSS spec: sum of max positive and min negative
    } else if max_positive > 0.0 {
        max_positive
    } else {
        min_negative
    }
}

/// Auto margin resolution (centering)
pub fn resolve_auto_margins(
    available_width: f32,
    content_width: f32,
    padding: &BoxEdges,
    border: &BoxEdges,
    auto_left: bool,
    auto_right: bool,
) -> (f32, f32) {
    let used_width = content_width + padding.horizontal() + border.horizontal();
    let remainder = available_width - used_width;

    if remainder <= 0.0 {
        return (0.0, 0.0);
    }

    match (auto_left, auto_right) {
        (true, true) => (remainder / 2.0, remainder / 2.0),
        (true, false) => (remainder, 0.0),
        (false, true) => (0.0, remainder),
        (false, false) => (0.0, 0.0),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_box_rect() {
        let r = BoxRect::new(10.0, 20.0, 100.0, 50.0);
        assert_eq!(r.right(), 110.0);
        assert_eq!(r.bottom(), 70.0);
        assert!(r.contains(50.0, 40.0));
        assert!(!r.contains(5.0, 40.0));
    }

    #[test]
    fn test_box_edges() {
        let e = BoxEdges::new(10.0, 20.0, 30.0, 40.0);
        assert_eq!(e.horizontal(), 60.0);
        assert_eq!(e.vertical(), 40.0);
    }

    #[test]
    fn test_box_model_padding_box() {
        let mut model = BoxModel::new();
        model.content = BoxRect::new(10.0, 10.0, 80.0, 60.0);
        model.padding = BoxEdges::all(5.0);
        let pb = model.padding_box();
        assert_eq!(pb.x, 5.0);
        assert_eq!(pb.y, 5.0);
        assert_eq!(pb.width, 90.0);
        assert_eq!(pb.height, 70.0);
    }

    #[test]
    fn test_box_model_border_box() {
        let mut model = BoxModel::new();
        model.content = BoxRect::new(13.0, 13.0, 74.0, 54.0);
        model.padding = BoxEdges::all(5.0);
        model.border = BoxEdges::all(3.0);
        let bb = model.border_box();
        // 74 + 10 + 6 = 90
        // 54 + 10 + 6 = 70
        assert_eq!(bb.width, 90.0);
        assert_eq!(bb.height, 70.0);
    }

    #[test]
    fn test_margin_collapsing() {
        // Positive + positive = max
        assert_eq!(collapse_margins(&[10.0, 20.0, 15.0]), 20.0);
        // Negative + negative = min (most negative)
        assert_eq!(collapse_margins(&[-5.0, -15.0, -10.0]), -15.0);
        // Mixed
        assert_eq!(collapse_margins(&[20.0, -5.0]), 15.0);
    }

    #[test]
    fn test_content_width_content_box() {
        let padding = BoxEdges::all(10.0);
        let border = BoxEdges::all(2.0);
        let result = resolve_content_width(Some(100.0), &padding, &border, BoxSizingMode::ContentBox);
        assert_eq!(result, Some(100.0));
    }

    #[test]
    fn test_content_width_border_box() {
        let padding = BoxEdges::all(10.0);
        let border = BoxEdges::all(2.0);
        let result = resolve_content_width(Some(100.0), &padding, &border, BoxSizingMode::BorderBox);
        // 100 - (10+10) - (2+2) = 78
        assert_eq!(result, Some(76.0));
    }

    #[test]
    fn test_auto_margin_centering() {
        let padding = BoxEdges::all(0.0);
        let border = BoxEdges::all(0.0);
        let (left, right) = resolve_auto_margins(300.0, 100.0, &padding, &border, true, true);
        assert_eq!(left, 100.0);
        assert_eq!(right, 100.0);
    }

    #[test]
    fn test_border_radii_constrain() {
        let radii = BorderRadii {
            top_left: (100.0, 100.0),
            top_right: (100.0, 100.0),
            bottom_right: (100.0, 100.0),
            bottom_left: (100.0, 100.0),
        };
        // Box is 100x100, radii should be scaled to fit
        let constrained = radii.constrain(100.0, 100.0);
        assert!(constrained.top_left.0 <= 50.0);
    }

    #[test]
    fn test_rect_intersection() {
        let a = BoxRect::new(0.0, 0.0, 100.0, 100.0);
        let b = BoxRect::new(50.0, 50.0, 100.0, 100.0);
        let intersection = a.intersection(&b).unwrap();
        assert_eq!(intersection.x, 50.0);
        assert_eq!(intersection.y, 50.0);
        assert_eq!(intersection.width, 50.0);
        assert_eq!(intersection.height, 50.0);
    }
}
