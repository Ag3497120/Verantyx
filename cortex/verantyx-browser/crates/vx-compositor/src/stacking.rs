//! Stacking Context & Paint Order Engine
//!
//! Implements the full CSS 2.1 / CSS Transforms / CSS z-index paint order
//! specification as defined in the W3C "Elaborate description of Stacking Contexts"
//!
//! The algorithm determines the correct painting order for all boxes,
//! essential for the AI to correctly identify which elements are visible
//! and which are occluded by elements painted above them.
//!
//! Paint order phases (in-order):
//!   1. Background/borders of the element creating the context
//!   2. Child stacking contexts with negative z-indexes
//!   3. Block-level descendants (ifc, bfc, in-flow blocks)
//!   4. Floating descendants
//!   5. Inline descendants, including inline tables and inline blocks
//!   6. Child stacking contexts with z-index == 0 or auto
//!   7. Child stacking contexts with positive z-indexes


/// 2D point (re-defined locally to avoid cross-crate dependency)
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct Point { pub x: f64, pub y: f64 }
impl Point { pub fn new(x: f64, y: f64) -> Self { Self { x, y } } }

/// Rectangle (re-defined locally to avoid cross-crate dependency)
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct Rect { pub x: f64, pub y: f64, pub width: f64, pub height: f64 }
impl Rect {
    pub fn new(x: f64, y: f64, width: f64, height: f64) -> Self { Self { x, y, width, height } }
    pub fn max_x(&self) -> f64 { self.x + self.width }
    pub fn max_y(&self) -> f64 { self.y + self.height }
    pub fn contains_point(&self, p: Point) -> bool {
        p.x >= self.x && p.x <= self.max_x() && p.y >= self.y && p.y <= self.max_y()
    }
    pub fn intersects(&self, other: &Rect) -> bool {
        self.x < other.max_x() && self.max_x() > other.x
        && self.y < other.max_y() && self.max_y() > other.y
    }
}

/// A stacking context node in the stacking tree
#[derive(Debug, Clone)]
pub struct StackingContext {
    /// Node identifier (ties back to the DOM)
    pub node_id: u64,
    
    /// Z-index used for ordering within the parent context
    pub z_index: ZIndex,
    
    /// Bounding rect of this context
    pub bounds: Rect,
    
    /// Opacity (0.0 to 1.0)
    pub opacity: f64,
    
    /// Whether this context is the root stacking context
    pub is_root: bool,
    
    /// CSS transform matrix (simplified as a bool indicating presence of transform)
    pub has_transform: bool,
    
    /// Whether position is non-static
    pub is_positioned: bool,
    
    /// Mix-blend-mode
    pub blend_mode: BlendMode,
    
    /// Children sorted by paint order
    pub paint_layers: Vec<PaintLayer>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum ZIndex {
    Auto,
    Integer(i32),
}

impl ZIndex {
    pub fn from_str(s: &str) -> Self {
        match s.trim() {
            "auto" => Self::Auto,
            n => n.parse().map(Self::Integer).unwrap_or(Self::Auto),
        }
    }
    
    pub fn as_i32(&self) -> i32 {
        match self {
            Self::Auto => 0,
            Self::Integer(n) => *n,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BlendMode {
    Normal,
    Multiply,
    Screen,
    Overlay,
    Darken,
    Lighten,
    ColorDodge,
    ColorBurn,
    HardLight,
    SoftLight,
    Difference,
    Exclusion,
    Hue,
    Saturation,
    Color,
    Luminosity,
}

impl BlendMode {
    pub fn from_str(s: &str) -> Self {
        match s {
            "multiply" => Self::Multiply,
            "screen" => Self::Screen,
            "overlay" => Self::Overlay,
            "darken" => Self::Darken,
            "lighten" => Self::Lighten,
            "color-dodge" => Self::ColorDodge,
            "color-burn" => Self::ColorBurn,
            "hard-light" => Self::HardLight,
            "soft-light" => Self::SoftLight,
            "difference" => Self::Difference,
            "exclusion" => Self::Exclusion,
            "hue" => Self::Hue,
            "saturation" => Self::Saturation,
            "color" => Self::Color,
            "luminosity" => Self::Luminosity,
            _ => Self::Normal,
        }
    }
}

/// A single layer in the paint order
#[derive(Debug, Clone)]
pub struct PaintLayer {
    pub node_id: u64,
    pub bounds: Rect,
    pub opacity: f64,
    pub z_index: i32,
    pub phase: PaintPhase,
    pub overflow_hidden: bool,
    pub clip_rect: Option<Rect>,
    pub blend_mode: BlendMode,
}

/// The 7 phases of CSS paint order
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum PaintPhase {
    Background = 0,
    NegativeZIndex = 1,
    BlockLevelBoxes = 2,
    FloatingBoxes = 3,
    InlineElements = 4,
    ZeroZIndex = 5,
    PositiveZIndex = 6,
}

/// The stacking context builder and paint-order solver
pub struct StackingContextBuilder;

impl StackingContextBuilder {
    /// Build the stacking tree from a flat list of layout boxes
    pub fn build(root_bounds: Rect) -> StackingContext {
        StackingContext {
            node_id: 0,
            z_index: ZIndex::Integer(0),
            bounds: root_bounds,
            opacity: 1.0,
            is_root: true,
            has_transform: false,
            is_positioned: false,
            blend_mode: BlendMode::Normal,
            paint_layers: Vec::new(),
        }
    }
    
    /// Determines if an element establishes a new stacking context
    pub fn creates_stacking_context(
        position: &str,
        z_index_str: &str,
        opacity: f64,
        has_transform: bool,
        has_filter: bool,
        has_clip_path: bool,
        isolation: &str,
        mix_blend_mode: &str,
        will_change: &str,
    ) -> bool {
        // Root element always creates one
        // Non-static position with z-index other than auto
        let is_positioned = matches!(position, "relative" | "absolute" | "fixed" | "sticky");
        let has_z_index = z_index_str != "auto";
        
        if is_positioned && has_z_index { return true; }
        
        // opacity < 1
        if opacity < 1.0 { return true; }
        
        // transform/filter/clip-path
        if has_transform || has_filter || has_clip_path { return true; }
        
        // isolation: isolate
        if isolation == "isolate" { return true; }
        
        // mix-blend-mode other than normal
        if mix_blend_mode != "normal" { return true; }
        
        // will-change: opacity, transform, etc.
        if will_change.contains("opacity") || will_change.contains("transform")
        || will_change.contains("filter") { return true; }
        
        // sticky position always creates stacking context
        if position == "sticky" { return true; }
        
        // fixed position always creates stacking context
        if position == "fixed" { return true; }
        
        false
    }
}

/// Point-in-stacking-context hit test — finds the topmost element at a point
pub struct HitTester {
    /// All paint layers sorted by effective paint order (index = paint order)
    ordered_layers: Vec<PaintLayer>,
}

impl HitTester {
    pub fn new(mut layers: Vec<PaintLayer>) -> Self {
        // Sort: higher phase and higher z-index = painted later = on top
        layers.sort_by(|a, b| {
            a.phase.cmp(&b.phase)
                .then_with(|| a.z_index.cmp(&b.z_index))
                .then_with(|| (a.node_id).cmp(&b.node_id))
        });
        Self { ordered_layers: layers }
    }
    
    /// Returns the topmost visible element at the given viewport point
    pub fn hit_test(&self, point: Point) -> Option<u64> {
        // Iterate in reverse (last painted = topmost visually)
        for layer in self.ordered_layers.iter().rev() {
            if layer.opacity <= 0.0 { continue; }
            
            // Check clip rect if applicable
            if let Some(clip) = layer.clip_rect {
                if !clip.contains_point(point) { continue; }
            }
            
            if layer.bounds.contains_point(point) {
                return Some(layer.node_id);
            }
        }
        None
    }
    
    /// Returns all elements at the given point, sorted topmost first
    pub fn all_at_point(&self, point: Point) -> Vec<u64> {
        self.ordered_layers.iter().rev()
            .filter(|layer| {
                layer.opacity > 0.0
                && layer.bounds.contains_point(point)
                && layer.clip_rect.map_or(true, |clip| clip.contains_point(point))
            })
            .map(|layer| layer.node_id)
            .collect()
    }
    
    /// Returns elements occluding a given element (painted above it)
    pub fn occluding_elements(&self, target_node_id: u64, target_bounds: Rect) -> Vec<u64> {
        // Find the target's position in the paint order
        let target_pos = self.ordered_layers.iter()
            .position(|l| l.node_id == target_node_id);
        
        let target_pos = match target_pos {
            Some(p) => p,
            None => return Vec::new(),
        };
        
        // Elements painted AFTER (higher index) that overlap the target bounds
        self.ordered_layers[target_pos+1..].iter()
            .filter(|layer| {
                layer.opacity > 0.0
                && layer.bounds.intersects(&target_bounds)
                && layer.clip_rect.map_or(true, |clip| clip.intersects(&target_bounds))
            })
            .map(|layer| layer.node_id)
            .collect()
    }
}

/// RGBA color representation
#[derive(Debug, Clone, Copy, Default)]
pub struct Color {
    pub r: u8,
    pub g: u8,
    pub b: u8,
    pub a: f64, // 0.0 to 1.0
}

impl Color {
    pub const TRANSPARENT: Color = Color { r: 0, g: 0, b: 0, a: 0.0 };
    pub const BLACK: Color = Color { r: 0, g: 0, b: 0, a: 1.0 };
    pub const WHITE: Color = Color { r: 255, g: 255, b: 255, a: 1.0 };
    
    pub fn rgba(r: u8, g: u8, b: u8, a: f64) -> Self { Self { r, g, b, a } }
    pub fn rgb(r: u8, g: u8, b: u8) -> Self { Self { r, g, b, a: 1.0 } }
    
    pub fn is_transparent(&self) -> bool { self.a == 0.0 }
    pub fn is_opaque(&self) -> bool { self.a == 1.0 }
    
    /// Composite this color over another using the Porter-Duff "over" operator
    pub fn composite_over(&self, background: Color) -> Color {
        if self.a == 1.0 { return *self; }
        if self.a == 0.0 { return background; }
        
        let out_a = self.a + background.a * (1.0 - self.a);
        if out_a == 0.0 { return Color::TRANSPARENT; }
        
        Color {
            r: ((self.r as f64 * self.a + background.r as f64 * background.a * (1.0 - self.a)) / out_a) as u8,
            g: ((self.g as f64 * self.a + background.g as f64 * background.a * (1.0 - self.a)) / out_a) as u8,
            b: ((self.b as f64 * self.a + background.b as f64 * background.a * (1.0 - self.a)) / out_a) as u8,
            a: out_a,
        }
    }
    
    /// Compute luminance (W3C relative luminance for contrast ratio)
    pub fn relative_luminance(&self) -> f64 {
        fn linearize(c: u8) -> f64 {
            let v = c as f64 / 255.0;
            if v <= 0.04045 { v / 12.92 } else { ((v + 0.055) / 1.055).powf(2.4) }
        }
        0.2126 * linearize(self.r) + 0.7152 * linearize(self.g) + 0.0722 * linearize(self.b)
    }
    
    /// Compute WCAG 2.1 contrast ratio against another color
    pub fn contrast_ratio(&self, other: &Color) -> f64 {
        let l1 = self.relative_luminance();
        let l2 = other.relative_luminance();
        let (lighter, darker) = if l1 > l2 { (l1, l2) } else { (l2, l1) };
        (lighter + 0.05) / (darker + 0.05)
    }
    
    /// Check if text with this color on a given background passes WCAG AA
    pub fn passes_wcag_aa(&self, background: &Color, large_text: bool) -> bool {
        let ratio = self.contrast_ratio(background);
        if large_text { ratio >= 3.0 } else { ratio >= 4.5 }
    }
    
    /// Check WCAG AAA
    pub fn passes_wcag_aaa(&self, background: &Color, large_text: bool) -> bool {
        let ratio = self.contrast_ratio(background);
        if large_text { ratio >= 4.5 } else { ratio >= 7.0 }
    }
}
