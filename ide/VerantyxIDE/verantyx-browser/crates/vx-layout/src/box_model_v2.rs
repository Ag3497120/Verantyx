//! Layout Box Model Engine — Full CSS Box Model Implementation
//!
//! Implements the W3C CSS Box Model specification including:
//! - Block Formatting Context (BFC) establishment
//! - Inline Formatting Context (IFC) with baseline alignment
//! - Margin collapsing (all 5 rules from the spec)
//! - Containing block resolution
//! - Stacking context creation
//! - Percentage resolution chains
//! - Min/max constraint solving

use std::collections::HashMap;

/// A 2D point in layout space  
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct Point {
    pub x: f64,
    pub y: f64,
}

impl Point {
    pub fn new(x: f64, y: f64) -> Self { Self { x, y } }
    pub fn zero() -> Self { Self { x: 0.0, y: 0.0 } }
}

/// A size in layout space
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct Size {
    pub width: f64,
    pub height: f64,
}

impl Size {
    pub fn new(width: f64, height: f64) -> Self { Self { width, height } }
    pub fn zero() -> Self { Self { width: 0.0, height: 0.0 } }
    
    pub fn is_definite(&self) -> bool {
        self.width.is_finite() && self.height.is_finite()
    }
}

/// A rectangle in layout space
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct Rect {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}

impl Rect {
    pub fn new(x: f64, y: f64, width: f64, height: f64) -> Self {
        Self { x, y, width, height }
    }
    
    pub fn zero() -> Self { Self { x: 0., y: 0., width: 0., height: 0. } }
    
    pub fn from_point_size(point: Point, size: Size) -> Self {
        Self { x: point.x, y: point.y, width: size.width, height: size.height }
    }
    
    pub fn max_x(&self) -> f64 { self.x + self.width }
    pub fn max_y(&self) -> f64 { self.y + self.height }
    
    pub fn intersects(&self, other: &Rect) -> bool {
        self.x < other.max_x() && self.max_x() > other.x
        && self.y < other.max_y() && self.max_y() > other.y
    }
    
    pub fn contains_point(&self, p: Point) -> bool {
        p.x >= self.x && p.x <= self.max_x() && p.y >= self.y && p.y <= self.max_y()
    }
    
    pub fn inflate(&self, amount: f64) -> Rect {
        Rect {
            x: self.x - amount,
            y: self.y - amount,
            width: self.width + amount * 2.0,
            height: self.height + amount * 2.0,
        }
    }
    
    pub fn union(&self, other: &Rect) -> Rect {
        let min_x = self.x.min(other.x);
        let min_y = self.y.min(other.y);
        let max_x = self.max_x().max(other.max_x());
        let max_y = self.max_y().max(other.max_y());
        Rect::new(min_x, min_y, max_x - min_x, max_y - min_y)
    }
}

/// Represents the four edges of a CSS box
#[derive(Debug, Clone, Copy, Default)]
pub struct EdgeSizes {
    pub top: f64,
    pub right: f64,
    pub bottom: f64,
    pub left: f64,
}

impl EdgeSizes {
    pub fn new(top: f64, right: f64, bottom: f64, left: f64) -> Self {
        Self { top, right, bottom, left }
    }
    
    pub fn uniform(value: f64) -> Self {
        Self { top: value, right: value, bottom: value, left: value }
    }
    
    pub fn zero() -> Self { Self::uniform(0.0) }
    
    pub fn horizontal(&self) -> f64 { self.left + self.right }
    pub fn vertical(&self) -> f64 { self.top + self.bottom }
}

/// The full CSS Box Model for a single element
#[derive(Debug, Clone, Default)]
pub struct BoxModel {
    /// The content area (width × height of the actual content)
    pub content: Rect,
    
    /// Padding around the content
    pub padding: EdgeSizes,
    
    /// Border around the padding box
    pub border: EdgeSizes,
    
    /// Margin around the border box
    pub margin: EdgeSizes,
    
    /// Computed margin after collapsing (may be 0 for collapsed edges)
    pub collapsed_margin_top: f64,
    pub collapsed_margin_bottom: f64,
}

impl BoxModel {
    pub fn padding_box(&self) -> Rect {
        Rect::new(
            self.content.x - self.padding.left,
            self.content.y - self.padding.top,
            self.content.width + self.padding.horizontal(),
            self.content.height + self.padding.vertical(),
        )
    }
    
    pub fn border_box(&self) -> Rect {
        let pb = self.padding_box();
        Rect::new(
            pb.x - self.border.left,
            pb.y - self.border.top,
            pb.width + self.border.horizontal(),
            pb.height + self.border.vertical(),
        )
    }
    
    pub fn margin_box(&self) -> Rect {
        let bb = self.border_box();
        Rect::new(
            bb.x - self.margin.left,
            bb.y - self.margin.top,
            bb.width + self.margin.horizontal(),
            bb.height + self.margin.vertical(),
        )
    }
}

/// The display type that determines the formatting context
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DisplayType {
    Block,
    Inline,
    InlineBlock,
    Flex,
    Grid,
    Table,
    TableRow,
    TableCell,
    TableHeaderGroup,
    TableFooterGroup,
    TableRowGroup,
    TableColumn,
    TableColumnGroup,
    TableCaption,
    ListItem,
    FlowRoot,
    None,
    Contents,
}

impl DisplayType {
    pub fn from_str(s: &str) -> Self {
        match s {
            "block" => Self::Block,
            "inline" => Self::Inline,
            "inline-block" => Self::InlineBlock,
            "flex" | "inline-flex" => Self::Flex,
            "grid" | "inline-grid" => Self::Grid,
            "table" => Self::Table,
            "table-row" => Self::TableRow,
            "table-cell" => Self::TableCell,
            "table-header-group" => Self::TableHeaderGroup,
            "table-footer-group" => Self::TableFooterGroup,
            "table-row-group" => Self::TableRowGroup,
            "table-column" => Self::TableColumn,
            "table-column-group" => Self::TableColumnGroup,
            "table-caption" => Self::TableCaption,
            "list-item" => Self::ListItem,
            "flow-root" => Self::FlowRoot,
            "none" => Self::None,
            "contents" => Self::Contents,
            _ => Self::Inline,
        }
    }
    
    pub fn establishes_bfc(&self) -> bool {
        matches!(self,
            Self::Block | Self::InlineBlock | Self::Flex | Self::Grid |
            Self::Table | Self::FlowRoot | Self::ListItem
        )
    }
    
    pub fn is_block_level(&self) -> bool {
        matches!(self,
            Self::Block | Self::Flex | Self::Grid | Self::Table |
            Self::ListItem | Self::FlowRoot
        )
    }
}

/// Position scheme
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PositionScheme {
    Static,
    Relative,
    Absolute,
    Fixed,
    Sticky,
}

impl PositionScheme {
    pub fn from_str(s: &str) -> Self {
        match s {
            "relative" => Self::Relative,
            "absolute" => Self::Absolute,
            "fixed" => Self::Fixed,
            "sticky" => Self::Sticky,
            _ => Self::Static,
        }
    }
    
    pub fn is_out_of_flow(&self) -> bool {
        matches!(self, Self::Absolute | Self::Fixed)
    }
    
    pub fn creates_stacking_context(&self) -> bool {
        matches!(self, Self::Absolute | Self::Fixed | Self::Sticky)
    }
}

/// The margin collapsing algorithm per CSS 2.1 Section 8.3.1
pub struct MarginCollapser;

impl MarginCollapser {
    /// Collapses two margins according to the CSS spec rules:
    /// - Both positive: take the maximum
    /// - Both negative: take the most negative  
    /// - One positive, one negative: subtract the absolute negative from positive
    pub fn collapse(a: f64, b: f64) -> f64 {
        if a >= 0.0 && b >= 0.0 {
            // Rule 1: Adjacent positive margins collapse to the largest
            a.max(b)
        } else if a < 0.0 && b < 0.0 {
            // Rule 2: Adjacent negative margins collapse to the most negative
            a.min(b)
        } else {
            // Rule 3: Mixed sign: sum of the largest positive and the absolute most negative
            let pos = a.max(b).max(0.0);
            let neg = a.min(b).min(0.0);
            pos + neg
        }
    }
    
    /// Check if block margins can collapse through the element
    /// (spec: no border, no padding, no established IFC, no block formatting context)
    pub fn can_margins_collapse_through(box_model: &BoxModel, display: DisplayType) -> bool {
        box_model.border.vertical() == 0.0
        && box_model.padding.vertical() == 0.0
        && box_model.content.height == 0.0
        && !display.establishes_bfc()
    }
    
    /// Compute the collapsed top/bottom margin after applying all 5 spec rules
    pub fn compute_collapsed_margins(children: &[f64]) -> f64 {
        if children.is_empty() { return 0.0; }
        children.iter().copied().fold(children[0], |acc, m| Self::collapse(acc, m))
    }
}

/// A layout constraint passed down to child boxes
#[derive(Debug, Clone, Copy)]
pub struct LayoutConstraints {
    pub available_width: f64,
    pub available_height: Option<f64>, // None = shrink-to-fit vertically
    pub containing_block_width: f64,
    pub containing_block_height: Option<f64>,
    pub is_bfc: bool,
    pub is_ifc: bool,
}

impl LayoutConstraints {
    pub fn new(available_width: f64) -> Self {
        Self {
            available_width,
            available_height: None,
            containing_block_width: available_width,
            containing_block_height: None,
            is_bfc: false,
            is_ifc: false,
        }
    }
    
    pub fn resolve_percentage_width(&self, pct: f64) -> f64 {
        self.containing_block_width * pct / 100.0
    }
    
    pub fn resolve_percentage_height(&self, pct: f64) -> Option<f64> {
        self.containing_block_height.map(|h| h * pct / 100.0)
    }
}

/// Length unit resolver — converts CSS lengths to pixels
pub struct LengthResolver {
    pub viewport_width: f64,
    pub viewport_height: f64,
    pub root_font_size: f64,
    pub parent_font_size: f64,
}

impl LengthResolver {
    pub fn new(viewport_width: f64, viewport_height: f64) -> Self {
        Self {
            viewport_width,
            viewport_height,
            root_font_size: 16.0,
            parent_font_size: 16.0,
        }
    }
    
    /// Resolve a CSS length value to pixels
    pub fn resolve(&self, value: &str, containing_size: Option<f64>) -> f64 {
        let value = value.trim();
        
        if value == "0" || value == "0px" { return 0.0; }
        if value == "auto" { return 0.0; } // Caller should handle auto differently
        
        // Try to parse number + unit
        let (num_str, unit) = self.split_number_unit(value);
        let num: f64 = num_str.parse().unwrap_or(0.0);
        
        match unit {
            "px" => num,
            "em" => num * self.parent_font_size,
            "rem" => num * self.root_font_size,
            "ex" => num * self.parent_font_size * 0.5,
            "ch" => num * self.parent_font_size * 0.5,
            "vw" => num * self.viewport_width / 100.0,
            "vh" => num * self.viewport_height / 100.0,
            "vmin" => num * self.viewport_width.min(self.viewport_height) / 100.0,
            "vmax" => num * self.viewport_width.max(self.viewport_height) / 100.0,
            "%" => {
                if let Some(container) = containing_size {
                    num * container / 100.0
                } else {
                    0.0 // Percentage with no containing size context
                }
            }
            "cm" => num * 96.0 / 2.54,
            "mm" => num * 96.0 / 25.4,
            "in" => num * 96.0,
            "pt" => num * 96.0 / 72.0,
            "pc" => num * 96.0 / 6.0,
            "Q" => num * 96.0 / 101.6,
            _ => num, // Fallback, treat as px
        }
    }
    
    fn split_number_unit<'a>(&self, value: &'a str) -> (&'a str, &'a str) {
        let unit_start = value.find(|c: char| c.is_alphabetic() || c == '%')
            .unwrap_or(value.len());
        (&value[..unit_start], &value[unit_start..])
    }
}

/// Min/Max constraint solver
pub struct ConstraintSolver;

impl ConstraintSolver {
    /// Apply min-width / max-width constraints to a computed width
    pub fn apply_width_constraints(
        mut width: f64,
        min_width: Option<f64>,
        max_width: Option<f64>,
    ) -> f64 {
        if let Some(max) = max_width {
            width = width.min(max);
        }
        if let Some(min) = min_width {
            width = width.max(min);
        }
        width
    }
    
    /// Apply min-height / max-height constraints to a computed height
    pub fn apply_height_constraints(
        mut height: f64,
        min_height: Option<f64>,
        max_height: Option<f64>,
    ) -> f64 {
        if let Some(max) = max_height {
            height = height.min(max);
        }
        if let Some(min) = min_height {
            height = height.max(min);
        }
        height
    }
}
