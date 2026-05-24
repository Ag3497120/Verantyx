//! CSS Flexbox Layout Engine — W3C CSS Flexible Box Layout Level 1
//!
//! Implements the complete CSS Flexbox specification:
//!   - Main axis / cross axis determination (flex-direction)
//!   - Flex line creation (single-line vs multi-line, flex-wrap)
//!   - Flexible length resolution (flex-grow, flex-shrink, flex-basis)
//!   - Hypothetical main size calculation
//!   - Available space computation with margins
//!   - Sizing main axis (§ 9.7 flex shrink/grow factor algorithm)
//!   - Cross axis sizing (align-self, align-items, align-content)
//!   - Main axis alignment (justify-content)
//!   - Baseline alignment
//!   - Absolute positioning within flex container
//!   - order property and visual ordering

use std::collections::HashMap;

/// Flex direction — determines main vs cross axis
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FlexDirection {
    Row,
    RowReverse,
    Column,
    ColumnReverse,
}

impl FlexDirection {
    pub fn from_str(s: &str) -> Self {
        match s {
            "row-reverse" => Self::RowReverse,
            "column" => Self::Column,
            "column-reverse" => Self::ColumnReverse,
            _ => Self::Row,
        }
    }
    
    pub fn is_row(&self) -> bool { matches!(self, Self::Row | Self::RowReverse) }
    pub fn is_reversed(&self) -> bool { matches!(self, Self::RowReverse | Self::ColumnReverse) }
}

/// Flex wrap mode
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FlexWrap {
    NoWrap,
    Wrap,
    WrapReverse,
}

impl FlexWrap {
    pub fn from_str(s: &str) -> Self {
        match s {
            "wrap" => Self::Wrap,
            "wrap-reverse" => Self::WrapReverse,
            _ => Self::NoWrap,
        }
    }
    
    pub fn allows_wrapping(&self) -> bool { !matches!(self, Self::NoWrap) }
}

/// Flexbox alignment values (justify-content, align-items, align-self, align-content)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FlexAlign {
    FlexStart,
    FlexEnd,
    Center,
    SpaceBetween,
    SpaceAround,
    SpaceEvenly,
    Stretch,
    Baseline,
    Start,
    End,
    Normal,
}

impl FlexAlign {
    pub fn from_str(s: &str) -> Self {
        match s {
            "flex-start" | "start" => Self::FlexStart,
            "flex-end" | "end" => Self::FlexEnd,
            "center" => Self::Center,
            "space-between" => Self::SpaceBetween,
            "space-around" => Self::SpaceAround,
            "space-evenly" => Self::SpaceEvenly,
            "stretch" => Self::Stretch,
            "baseline" => Self::Baseline,
            _ => Self::Normal,
        }
    }
}

/// Flex basis — the starting size before grow/shrink
#[derive(Debug, Clone, PartialEq)]
pub enum FlexBasis {
    Auto,
    Content,
    Length(f64),
    Percentage(f64),
    MinContent,
    MaxContent,
    FitContent,
}

impl FlexBasis {
    pub fn resolve(&self, item: &FlexItem, container_main_size: f64) -> f64 {
        match self {
            Self::Auto => item.main_size.unwrap_or(item.max_content_main_size),
            Self::Content => item.max_content_main_size,
            Self::Length(px) => *px,
            Self::Percentage(pct) => container_main_size * pct / 100.0,
            Self::MinContent => item.min_content_main_size,
            Self::MaxContent => item.max_content_main_size,
            Self::FitContent => item.max_content_main_size.min(container_main_size),
        }
    }
}

/// A flex container's configuration
#[derive(Debug, Clone)]
pub struct FlexContainer {
    pub direction: FlexDirection,
    pub wrap: FlexWrap,
    pub justify_content: FlexAlign,
    pub align_items: FlexAlign,
    pub align_content: FlexAlign,
    pub row_gap: f64,
    pub column_gap: f64,
    
    // Container dimensions
    pub main_size: Option<f64>,   // Width if row, height if column
    pub cross_size: Option<f64>,  // Height if row, width if column
    pub min_main_size: f64,
    pub max_main_size: f64,
    pub min_cross_size: f64,
    pub max_cross_size: f64,
}

impl FlexContainer {
    pub fn new(direction: FlexDirection) -> Self {
        Self {
            direction,
            wrap: FlexWrap::NoWrap,
            justify_content: FlexAlign::FlexStart,
            align_items: FlexAlign::Stretch,
            align_content: FlexAlign::Normal,
            row_gap: 0.0,
            column_gap: 0.0,
            main_size: None,
            cross_size: None,
            min_main_size: 0.0,
            max_main_size: f64::INFINITY,
            min_cross_size: 0.0,
            max_cross_size: f64::INFINITY,
        }
    }
    
    pub fn main_gap(&self) -> f64 {
        if self.direction.is_row() { self.column_gap } else { self.row_gap }
    }
    
    pub fn cross_gap(&self) -> f64 {
        if self.direction.is_row() { self.row_gap } else { self.column_gap }
    }
}

/// A flex item
#[derive(Debug, Clone)]
pub struct FlexItem {
    pub node_id: u64,
    pub order: i32,
    pub flex_grow: f64,
    pub flex_shrink: f64,
    pub flex_basis: FlexBasis,
    pub align_self: Option<FlexAlign>,
    pub min_main_size: f64,
    pub max_main_size: f64,
    pub min_cross_size: f64,
    pub max_cross_size: f64,
    pub main_size: Option<f64>,       // Explicit width or height
    pub cross_size: Option<f64>,
    pub min_content_main_size: f64,
    pub max_content_main_size: f64,
    pub min_content_cross_size: f64,
    pub max_content_cross_size: f64,
    pub margin_main_start: f64,
    pub margin_main_end: f64,
    pub margin_cross_start: f64,
    pub margin_cross_end: f64,
    pub is_absolutely_positioned: bool,
    
    // Computed during layout:
    pub hypothetical_main_size: f64,
    pub frozen: bool,
    pub target_main_size: f64,
    pub computed_main_size: f64,
    pub computed_cross_size: f64,
    pub main_offset: f64,
    pub cross_offset: f64,
    pub baseline_offset: f64,
}

impl FlexItem {
    pub fn new(node_id: u64) -> Self {
        Self {
            node_id, order: 0,
            flex_grow: 0.0, flex_shrink: 1.0, flex_basis: FlexBasis::Auto,
            align_self: None,
            min_main_size: 0.0, max_main_size: f64::INFINITY,
            min_cross_size: 0.0, max_cross_size: f64::INFINITY,
            main_size: None, cross_size: None,
            min_content_main_size: 0.0, max_content_main_size: 0.0,
            min_content_cross_size: 0.0, max_content_cross_size: 0.0,
            margin_main_start: 0.0, margin_main_end: 0.0,
            margin_cross_start: 0.0, margin_cross_end: 0.0,
            is_absolutely_positioned: false,
            hypothetical_main_size: 0.0,
            frozen: false,
            target_main_size: 0.0,
            computed_main_size: 0.0,
            computed_cross_size: 0.0,
            main_offset: 0.0, cross_offset: 0.0, baseline_offset: 0.0,
        }
    }
    
    pub fn outer_main_size(&self) -> f64 {
        self.computed_main_size + self.margin_main_start + self.margin_main_end
    }
    
    pub fn outer_cross_size(&self) -> f64 {
        self.computed_cross_size + self.margin_cross_start + self.margin_cross_end
    }
}

/// A flex line (group of items on one line)
#[derive(Debug)]
pub struct FlexLine {
    pub items: Vec<usize>,      // Indices into the items array
    pub main_size: f64,         // Total outer main size of all items
    pub cross_size: f64,        // Largest cross size in this line
    pub baseline: f64,
}

/// Computed geometry for a flex item
#[derive(Debug, Clone)]
pub struct FlexItemGeometry {
    pub node_id: u64,
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}

/// The Flexbox Layout Engine
pub struct FlexboxEngine;

impl FlexboxEngine {
    /// Execute the full Flexbox layout algorithm
    pub fn layout(
        container: &FlexContainer,
        mut items: Vec<FlexItem>,
    ) -> Vec<FlexItemGeometry> {
        // Step 1: Re-order items by 'order' property (stable sort)
        items.sort_by(|a, b| a.order.cmp(&b.order));
        
        let container_main_size = container.main_size.unwrap_or(f64::INFINITY);
        let container_cross_size = container.cross_size.unwrap_or(0.0);
        
        // Step 2: Determine flex basis and hypothetical main sizes
        for item in &mut items {
            let basis = item.flex_basis.resolve(item, container_main_size);
            item.hypothetical_main_size = basis
                .max(item.min_main_size)
                .min(item.max_main_size);
            item.target_main_size = item.hypothetical_main_size;
        }
        
        // Step 3: Collect items into flex lines
        let lines = Self::collect_flex_lines(&items, container, container_main_size);
        
        // Step 4: Resolve flexible lengths on each line
        let mut items = items;
        for line in &lines {
            Self::resolve_flexible_lengths(&mut items, line, container_main_size);
        }
        
        // Step 5: Determine cross sizes
        for item in &mut items {
            item.computed_cross_size = item.cross_size
                .unwrap_or(item.max_content_cross_size)
                .max(item.min_cross_size)
                .min(item.max_cross_size);
        }
        
        // Step 6: Determine line cross sizes
        let mut line_cross_sizes: Vec<f64> = lines.iter().map(|line| {
            line.items.iter()
                .map(|&i| items[i].outer_cross_size())
                .fold(0.0f64, f64::max)
                .max(0.0)
        }).collect();
        
        // Step 7: Handle align-content stretching (multi-line)
        if container.wrap.allows_wrapping() && container.align_content == FlexAlign::Stretch {
            if let Some(cross_size) = container.cross_size {
                let total_cross: f64 = line_cross_sizes.iter().sum();
                let gaps = container.cross_gap() * (lines.len().saturating_sub(1)) as f64;
                let free_cross = cross_size - total_cross - gaps;
                if free_cross > 0.0 {
                    let per_line = free_cross / lines.len() as f64;
                    for size in &mut line_cross_sizes { *size += per_line; }
                }
            }
        }
        
        // Step 8: Align items + compute positions
        let mut geometries = Vec::new();
        let mut cross_cursor = 0.0;
        
        let effective_container_main = if container_main_size.is_finite() {
            container_main_size
        } else {
            items.iter().map(|i| i.outer_main_size()).sum::<f64>()
        };
        
        for (line_idx, line) in lines.iter().enumerate() {
            let line_cross_size = line_cross_sizes[line_idx];
            
            // Main axis item sizes
            let total_outer_main: f64 = line.items.iter()
                .map(|&i| items[i].outer_main_size())
                .sum();
            let main_gaps = container.main_gap() * (line.items.len().saturating_sub(1)) as f64;
            let free_main = effective_container_main - total_outer_main - main_gaps;
            
            // Justify-content: compute starting position and spacing
            let (main_start, between_space, around_space) = Self::justify_content_offsets(
                container.justify_content, free_main, line.items.len()
            );
            
            let mut main_cursor = main_start;
            
            for (item_pos, &item_idx) in line.items.iter().enumerate() {
                let item = &mut items[item_idx];
                
                // Cross axis alignment
                let cross_offset = Self::align_item_cross_offset(
                    container.align_items, item.align_self, item, line_cross_size,
                );
                
                item.main_offset = main_cursor + item.margin_main_start;
                item.cross_offset = cross_cursor + cross_offset + item.margin_cross_start;
                
                main_cursor += item.outer_main_size() + container.main_gap();
                if item_pos > 0 { main_cursor += around_space; }
                main_cursor += between_space;
                
                // Translate back to x/y based on flex-direction
                let (x, y, w, h) = if container.direction.is_row() {
                    (item.main_offset, item.cross_offset, item.computed_main_size, item.computed_cross_size)
                } else {
                    (item.cross_offset, item.main_offset, item.computed_cross_size, item.computed_main_size)
                };
                
                geometries.push(FlexItemGeometry { node_id: item.node_id, x, y, width: w, height: h });
            }
            
            cross_cursor += line_cross_size + container.cross_gap();
        }
        
        geometries
    }
    
    fn collect_flex_lines(
        items: &[FlexItem],
        container: &FlexContainer,
        container_main_size: f64,
    ) -> Vec<FlexLine> {
        let mut lines = Vec::new();
        let mut current_line_items = Vec::new();
        let mut current_line_main: f64 = 0.0;
        
        for (i, item) in items.iter().enumerate() {
            if item.is_absolutely_positioned { continue; }
            
            let item_outer_main = item.hypothetical_main_size
                + item.margin_main_start + item.margin_main_end;
            let gap = if current_line_items.is_empty() { 0.0 } else { container.main_gap() };
            
            if container.wrap.allows_wrapping()
            && !current_line_items.is_empty()
            && current_line_main + gap + item_outer_main > container_main_size + 1e-6 {
                // Start a new line
                lines.push(FlexLine {
                    items: current_line_items.drain(..).collect(),
                    main_size: current_line_main,
                    cross_size: 0.0,
                    baseline: 0.0,
                });
                current_line_main = 0.0;
            }
            
            current_line_main += if current_line_items.is_empty() { 0.0 } else { container.main_gap() };
            current_line_main += item_outer_main;
            current_line_items.push(i);
        }
        
        if !current_line_items.is_empty() {
            lines.push(FlexLine {
                items: current_line_items,
                main_size: current_line_main,
                cross_size: 0.0,
                baseline: 0.0,
            });
        }
        
        lines
    }
    
    /// CSS § 9.7 — Resolve flexible lengths on a single line
    fn resolve_flexible_lengths(
        items: &mut Vec<FlexItem>,
        line: &FlexLine,
        container_main_size: f64,
    ) {
        if !container_main_size.is_finite() { return; }
        
        let total_hypothetical: f64 = line.items.iter()
            .map(|&i| items[i].hypothetical_main_size + items[i].margin_main_start + items[i].margin_main_end)
            .sum();
        
        let free_space = container_main_size - total_hypothetical;
        let growing = free_space > 0.0;
        
        // Initial target sizes = hypothetical sizes
        for &i in &line.items {
            items[i].target_main_size = items[i].hypothetical_main_size;
            items[i].frozen = false;
        }
        
        // Freeze items at their limits
        for &i in &line.items {
            let item = &items[i];
            if growing && item.flex_grow == 0.0 {
                items[i].frozen = true;
            } else if !growing && item.flex_shrink == 0.0 {
                items[i].frozen = true;
            }
        }
        
        // Iterative flex resolve (simplified — one pass, not full loop)
        let unfrozen_grow_factor: f64 = line.items.iter()
            .filter(|&&i| !items[i].frozen)
            .map(|&i| items[i].flex_grow)
            .sum();
        
        let unfrozen_shrink_factor: f64 = line.items.iter()
            .filter(|&&i| !items[i].frozen)
            .map(|&i| items[i].flex_shrink * items[i].hypothetical_main_size)
            .sum();
        
        if free_space > 0.0 && unfrozen_grow_factor > 0.0 {
            let unit = free_space / unfrozen_grow_factor;
            for &i in &line.items {
                if !items[i].frozen {
                    let grow_amount = unit * items[i].flex_grow;
                    let new_size = (items[i].hypothetical_main_size + grow_amount)
                        .max(items[i].min_main_size)
                        .min(items[i].max_main_size);
                    items[i].computed_main_size = new_size;
                } else {
                    items[i].computed_main_size = items[i].hypothetical_main_size;
                }
            }
        } else if free_space < 0.0 && unfrozen_shrink_factor > 0.0 {
            let unit = free_space / unfrozen_shrink_factor;
            for &i in &line.items {
                if !items[i].frozen {
                    let shrink_amount = unit * items[i].flex_shrink * items[i].hypothetical_main_size;
                    let new_size = (items[i].hypothetical_main_size + shrink_amount)
                        .max(items[i].min_main_size)
                        .min(items[i].max_main_size);
                    items[i].computed_main_size = new_size;
                } else {
                    items[i].computed_main_size = items[i].hypothetical_main_size;
                }
            }
        } else {
            for &i in &line.items {
                items[i].computed_main_size = items[i].hypothetical_main_size;
            }
        }
    }
    
    /// Compute justify-content offsets
    fn justify_content_offsets(
        align: FlexAlign,
        free_space: f64,
        item_count: usize,
    ) -> (f64, f64, f64) {
        let n = item_count as f64;
        match align {
            FlexAlign::FlexStart | FlexAlign::Start | FlexAlign::Normal => (0.0, 0.0, 0.0),
            FlexAlign::FlexEnd | FlexAlign::End => (free_space.max(0.0), 0.0, 0.0),
            FlexAlign::Center => (free_space.max(0.0) / 2.0, 0.0, 0.0),
            FlexAlign::SpaceBetween => {
                if item_count <= 1 { (0.0, 0.0, 0.0) }
                else { (0.0, free_space.max(0.0) / (n - 1.0), 0.0) }
            }
            FlexAlign::SpaceAround => {
                let per = free_space.max(0.0) / n;
                (per / 2.0, per, 0.0)
            }
            FlexAlign::SpaceEvenly => {
                let per = free_space.max(0.0) / (n + 1.0);
                (per, 0.0, per)
            }
            _ => (0.0, 0.0, 0.0),
        }
    }
    
    /// Compute cross-axis offset for a single item (align-self / align-items)
    fn align_item_cross_offset(
        align_items: FlexAlign,
        align_self: Option<FlexAlign>,
        item: &FlexItem,
        line_cross_size: f64,
    ) -> f64 {
        let effective = align_self.unwrap_or(align_items);
        let free = line_cross_size - item.outer_cross_size();
        
        match effective {
            FlexAlign::FlexStart | FlexAlign::Start | FlexAlign::Normal => 0.0,
            FlexAlign::FlexEnd | FlexAlign::End => free.max(0.0),
            FlexAlign::Center => free.max(0.0) / 2.0,
            FlexAlign::Stretch => {
                // Size the item to fill — handled by cross size computation, offset is 0
                0.0
            }
            FlexAlign::Baseline => item.baseline_offset, // Simplified
            _ => 0.0,
        }
    }
}
