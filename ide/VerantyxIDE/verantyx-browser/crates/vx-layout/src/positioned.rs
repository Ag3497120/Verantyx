//! CSS Positioned Layout — absolute, fixed, and sticky
//! 
//! Handles elements that are taken out of the normal layout flow.
//! Implements containing block resolution and inset calculations.

use crate::box_model::BoxRect;
use vx_dom::NodeId;

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum PositionType {
    Static,
    Relative,
    Absolute,
    Fixed,
    Sticky,
}

#[derive(Debug, Clone)]
pub struct PositionedItem {
    pub node_id: NodeId,
    pub position_type: PositionType,
    pub top: Option<f32>,
    pub right: Option<f32>,
    pub bottom: Option<f32>,
    pub left: Option<f32>,
    pub z_index: i32,
    
    // Output
    pub rect: BoxRect,
}

pub struct PositionedContext {
    pub viewport: BoxRect,
    pub root_containing_block: BoxRect,
}

impl PositionedContext {
    pub fn new(width: f32, height: f32) -> Self {
        let root = BoxRect::new(0.0, 0.0, width, height);
        Self {
            viewport: root.clone(),
            root_containing_block: root,
        }
    }

    /// Resolve an out-of-flow item's position based on its containing block
    pub fn resolve_item(&self, item: &mut PositionedItem, containing_block: &BoxRect) {
        let mut rect = item.rect.clone();
        
        // 1. Resolve Horizontal
        if let Some(left) = item.left {
            rect.x = containing_block.x + left;
        } else if let Some(right) = item.right {
            rect.x = containing_block.x + containing_block.width - right - rect.width;
        }

        // 2. Resolve Vertical
        if let Some(top) = item.top {
            rect.y = containing_block.y + top;
        } else if let Some(bottom) = item.bottom {
            rect.y = containing_block.y + containing_block.height - bottom - rect.height;
        }

        // 3. Handle Fixed (relative to viewport)
        if item.position_type == PositionType::Fixed {
            if let Some(left) = item.left {
                rect.x = self.viewport.x + left;
            }
            if let Some(top) = item.top {
                rect.y = self.viewport.y + top;
            }
        }

        item.rect = rect;
    }
}
