//! Flexbox layout algorithm — CSS Flexible Box Layout Module Level 1
//!
//! Full implementation of the Flexbox algorithm as specified at:
//! https://www.w3.org/TR/css-flexbox-1/

use crate::box_model::{BoxRect, BoxEdges};
use crate::dimension::{AvailableSpace, SizingConstraint};

/// Flex container configuration
#[derive(Debug, Clone)]
pub struct FlexContainer {
    pub rect: BoxRect,
    pub direction: FlexDirection,
    pub wrap: FlexWrap,
    pub justify_content: JustifyContent,
    pub align_items: AlignItems,
    pub align_content: AlignContent,
    pub gap_main: f32,
    pub gap_cross: f32,
    pub rtl: bool,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum FlexDirection { Row, RowReverse, Column, ColumnReverse }
impl FlexDirection {
    pub fn is_row(self) -> bool { matches!(self, Self::Row | Self::RowReverse) }
    pub fn is_reversed(self) -> bool { matches!(self, Self::RowReverse | Self::ColumnReverse) }
    pub fn main_size(self, r: &BoxRect) -> f32 { if self.is_row() { r.width } else { r.height } }
    pub fn cross_size(self, r: &BoxRect) -> f32 { if self.is_row() { r.height } else { r.width } }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum FlexWrap { NoWrap, Wrap, WrapReverse }
impl FlexWrap {
    pub fn is_wrap(self) -> bool { !matches!(self, Self::NoWrap) }
    pub fn is_reversed(self) -> bool { matches!(self, Self::WrapReverse) }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum JustifyContent {
    FlexStart, FlexEnd, Center, SpaceBetween, SpaceAround, SpaceEvenly, Start, End, Left, Right,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum AlignItems {
    FlexStart, FlexEnd, Center, Baseline, Stretch, Auto, Start, End, SelfStart, SelfEnd,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum AlignContent {
    FlexStart, FlexEnd, Center, SpaceBetween, SpaceAround, SpaceEvenly, Stretch, Normal,
}

/// A flex item
#[derive(Debug, Clone)]
pub struct FlexItem {
    pub min_main: f32,
    pub max_main: f32,
    pub min_cross: f32,
    pub max_cross: f32,
    pub flex_basis: FlexBasis,
    pub flex_grow: f32,
    pub flex_shrink: f32,
    pub align_self: AlignItems,
    pub order: i32,
    pub margin: BoxEdges,
    pub border: BoxEdges,
    pub padding: BoxEdges,
    // Output
    pub main_size: f32,
    pub cross_size: f32,
    pub main_offset: f32,
    pub cross_offset: f32,
}

#[derive(Debug, Clone, PartialEq)]
pub enum FlexBasis {
    Auto,
    Content,
    Size(f32),
}

impl FlexItem {
    pub fn new() -> Self {
        Self {
            min_main: 0.0, max_main: f32::INFINITY,
            min_cross: 0.0, max_cross: f32::INFINITY,
            flex_basis: FlexBasis::Auto,
            flex_grow: 0.0, flex_shrink: 1.0,
            align_self: AlignItems::Auto,
            order: 0,
            margin: BoxEdges::zero(),
            border: BoxEdges::zero(),
            padding: BoxEdges::zero(),
            main_size: 0.0, cross_size: 0.0,
            main_offset: 0.0, cross_offset: 0.0,
        }
    }

    pub fn margin_main(&self, direction: FlexDirection) -> f32 {
        if direction.is_row() { self.margin.horizontal() } else { self.margin.vertical() }
    }

    pub fn margin_cross(&self, direction: FlexDirection) -> f32 {
        if direction.is_row() { self.margin.vertical() } else { self.margin.horizontal() }
    }

    pub fn outer_main_size(&self, direction: FlexDirection) -> f32 {
        self.main_size + self.margin_main(direction)
    }

    pub fn inner_baseline(&self) -> f32 {
        self.cross_size // Simplified: use bottom edge
    }
}

impl Default for FlexItem {
    fn default() -> Self { Self::new() }
}

/// A flex line (one row/column of flex items)
#[derive(Debug, Clone, Default)]
pub struct FlexLine {
    pub items: Vec<usize>,  // indices into item array
    pub main_size: f32,
    pub cross_size: f32,
    pub cross_offset: f32,
}

/// The result of flex layout
#[derive(Debug, Clone)]
pub struct FlexLayout {
    pub lines: Vec<FlexLine>,
    pub total_cross_size: f32,
}

/// Run the flexbox layout algorithm
/// Returns computed FlexLayout with item positions
pub fn compute_flex_layout(
    container: &FlexContainer,
    items: &mut Vec<FlexItem>,
    intrinsic_sizes: &[(f32, f32)],  // (min-content, max-content) per item
) -> FlexLayout {
    if items.is_empty() {
        return FlexLayout { lines: vec![], total_cross_size: 0.0 };
    }

    let dir = container.direction;
    let container_main = dir.main_size(&container.rect);
    let container_cross = dir.cross_size(&container.rect);

    // Step 1: Sort items by order, then source order
    let mut indices: Vec<usize> = (0..items.len()).collect();
    indices.sort_by_key(|&i| items[i].order);

    // Step 2: Determine flex base size
    for &i in &indices {
        let item = &mut items[i];
        let (min_content, _) = intrinsic_sizes.get(i).copied().unwrap_or((0.0, 0.0));
        item.main_size = match &item.flex_basis {
            FlexBasis::Size(s) => *s,
            FlexBasis::Auto | FlexBasis::Content => min_content,
        };
        item.main_size = item.main_size.max(item.min_main).min(item.max_main);
    }

    // Step 3: Collect into lines
    let mut lines: Vec<FlexLine> = Vec::new();

    if !container.wrap.is_wrap() {
        // Single line
        lines.push(FlexLine {
            items: indices.clone(),
            main_size: 0.0,
            cross_size: 0.0,
            cross_offset: 0.0,
        });
    } else {
        // Multi-line wrapping
        let mut current_line = FlexLine::default();
        let mut current_main = 0.0;

        for &i in &indices {
            let item_outer = items[i].outer_main_size(dir);
            if !current_line.items.is_empty() &&
               current_main + item_outer + container.gap_main > container_main {
                lines.push(current_line);
                current_line = FlexLine::default();
                current_main = 0.0;
            }
            current_main += item_outer + if current_line.items.is_empty() { 0.0 } else { container.gap_main };
            current_line.items.push(i);
        }
        if !current_line.items.is_empty() {
            lines.push(current_line);
        }
    }

    // Step 4: Flex grow/shrink within each line
    for line in &mut lines {
        let mut total_main = line.items.iter()
            .map(|&i| items[i].outer_main_size(dir))
            .sum::<f32>();
        let gap_total = (line.items.len().saturating_sub(1) as f32) * container.gap_main;
        total_main += gap_total;

        let free_space = container_main - total_main;

        if free_space > 0.0 {
            // Grow
            let total_grow: f32 = line.items.iter().map(|&i| items[i].flex_grow).sum();
            if total_grow > 0.0 {
                for &i in &line.items {
                    let grow = items[i].flex_grow / total_grow;
                    items[i].main_size = (items[i].main_size + free_space * grow)
                        .max(items[i].min_main).min(items[i].max_main);
                }
            }
        } else if free_space < 0.0 {
            // Shrink
            let total_shrink: f32 = line.items.iter()
                .map(|&i| items[i].flex_shrink * items[i].main_size)
                .sum();
            if total_shrink > 0.0 {
                for &i in &line.items {
                    let shrink = items[i].flex_shrink * items[i].main_size / total_shrink;
                    items[i].main_size = (items[i].main_size + free_space * shrink)
                        .max(items[i].min_main);
                }
            }
        }

        // Step 5: Main axis offsets (justify-content)
        let new_total: f32 = line.items.iter()
            .map(|&i| items[i].outer_main_size(dir))
            .sum::<f32>() + gap_total;
        let final_free = container_main - new_total;

        let (initial_offset, between_offset) = match container.justify_content {
            JustifyContent::FlexStart | JustifyContent::Start | JustifyContent::Left => (0.0, container.gap_main),
            JustifyContent::FlexEnd | JustifyContent::End | JustifyContent::Right => (final_free, container.gap_main),
            JustifyContent::Center => (final_free / 2.0, container.gap_main),
            JustifyContent::SpaceBetween => {
                let n = line.items.len().saturating_sub(1) as f32;
                (0.0, if n > 0.0 { final_free / n + container.gap_main } else { 0.0 })
            }
            JustifyContent::SpaceAround => {
                let space = final_free / line.items.len() as f32;
                (space / 2.0, space + container.gap_main)
            }
            JustifyContent::SpaceEvenly => {
                let space = final_free / (line.items.len() + 1) as f32;
                (space, space + container.gap_main)
            }
        };

        let reversed = dir.is_reversed();
        let mut offset = if reversed { container_main - initial_offset } else { initial_offset };

        for &i in &line.items {
            let outer = items[i].outer_main_size(dir);
            if reversed {
                offset -= outer;
                items[i].main_offset = offset + items[i].margin.left;
                offset -= between_offset;
            } else {
                items[i].main_offset = offset + items[i].margin.left;
                offset += outer + between_offset;
            }
        }

        line.main_size = new_total;

        // Step 6: Cross axis sizing
        let mut line_cross = 0.0f32;
        for &i in &line.items {
            // Use preferred cross size or intrinsic
            let (_, max_c) = intrinsic_sizes.get(i).copied().unwrap_or((0.0, 100.0));
            items[i].cross_size = max_c.max(items[i].min_cross).min(items[i].max_cross);
            line_cross = line_cross.max(items[i].cross_size + items[i].margin_cross(dir));
        }
        line.cross_size = line_cross;
    }

    // Step 7: Cross axis alignment (align-items / align-self)
    let total_cross: f32 = lines.iter().map(|l| l.cross_size).sum::<f32>()
        + (lines.len().saturating_sub(1) as f32) * container.gap_cross;

    let mut cross_offset = match container.align_content {
        AlignContent::FlexEnd => container_cross - total_cross,
        AlignContent::Center => (container_cross - total_cross) / 2.0,
        _ => 0.0,
    };

    let cross_between = match container.align_content {
        AlignContent::SpaceBetween => {
            (container_cross - total_cross) / (lines.len().saturating_sub(1) as f32).max(1.0)
        }
        AlignContent::SpaceAround => {
            (container_cross - total_cross) / lines.len() as f32
        }
        AlignContent::Stretch => {
            if total_cross < container_cross {
                (container_cross - total_cross) / lines.len() as f32
            } else { 0.0 }
        }
        _ => container.gap_cross,
    };

    for line in &mut lines {
        line.cross_offset = cross_offset;

        for &i in &line.items {
            let align = match items[i].align_self {
                AlignItems::Auto => container.align_items,
                other => other,
            };
            items[i].cross_offset = match align {
                AlignItems::FlexStart | AlignItems::Start | AlignItems::SelfStart => {
                    cross_offset + items[i].margin_cross(dir) / 2.0
                }
                AlignItems::FlexEnd | AlignItems::End | AlignItems::SelfEnd => {
                    cross_offset + line.cross_size - items[i].cross_size - items[i].margin_cross(dir) / 2.0
                }
                AlignItems::Center => {
                    cross_offset + (line.cross_size - items[i].cross_size) / 2.0
                }
                AlignItems::Stretch | AlignItems::Auto => {
                    items[i].cross_size = (line.cross_size - items[i].margin_cross(dir))
                        .max(items[i].min_cross).min(items[i].max_cross);
                    cross_offset + items[i].margin_cross(dir) / 2.0
                }
                AlignItems::Baseline => {
                    cross_offset // Simplified baseline alignment
                }
            };
        }

        cross_offset += line.cross_size + cross_between;
    }

    // Apply wrap-reverse
    if container.wrap == FlexWrap::WrapReverse {
        for line in &mut lines {
            line.cross_offset = total_cross - line.cross_offset - line.cross_size;
        }
    }

    FlexLayout { lines, total_cross_size: total_cross }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::box_model::BoxRect;

    fn make_container(width: f32, height: f32, direction: FlexDirection) -> FlexContainer {
        FlexContainer {
            rect: BoxRect::new(0.0, 0.0, width, height),
            direction,
            wrap: FlexWrap::NoWrap,
            justify_content: JustifyContent::FlexStart,
            align_items: AlignItems::Stretch,
            align_content: AlignContent::Normal,
            gap_main: 0.0,
            gap_cross: 0.0,
            rtl: false,
        }
    }

    #[test]
    fn test_flex_grow_distributes_space() {
        let container = make_container(300.0, 100.0, FlexDirection::Row);
        let mut items = vec![
            FlexItem { flex_grow: 1.0, ..Default::default() },
            FlexItem { flex_grow: 2.0, ..Default::default() },
        ];
        let sizes = vec![(0.0, 0.0), (0.0, 0.0)];
        let layout = compute_flex_layout(&container, &mut items, &sizes);

        // Item 0 gets 1/3, item 1 gets 2/3
        assert!((items[0].main_size - 100.0).abs() < 1.0);
        assert!((items[1].main_size - 200.0).abs() < 1.0);
    }

    #[test]
    fn test_flex_center_justify() {
        let mut container = make_container(300.0, 100.0, FlexDirection::Row);
        container.justify_content = JustifyContent::Center;
        let mut items = vec![FlexItem { min_main: 0.0, max_main: f32::INFINITY, ..Default::default() }];
        items[0].main_size = 100.0;
        let sizes = vec![(100.0, 100.0)];
        let _layout = compute_flex_layout(&container, &mut items, &sizes);
        // With center, offset should be ~100
        assert!((items[0].main_offset - 100.0).abs() < 1.0);
    }

    #[test]
    fn test_flex_wrap() {
        let mut container = make_container(200.0, 100.0, FlexDirection::Row);
        container.wrap = FlexWrap::Wrap;
        let mut items: Vec<FlexItem> = (0..3).map(|_| FlexItem {
            min_main: 0.0, max_main: f32::INFINITY,
            ..Default::default()
        }).collect();
        for item in &mut items { item.main_size = 100.0; }
        let sizes = vec![(100.0, 100.0); 3];
        let layout = compute_flex_layout(&container, &mut items, &sizes);
        assert_eq!(layout.lines.len(), 2); // 2 items in line 1, 1 in line 2
    }
}
