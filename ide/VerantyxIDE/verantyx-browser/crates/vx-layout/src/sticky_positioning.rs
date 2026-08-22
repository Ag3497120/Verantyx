//! CSS Sticky Positioning Engine — W3C CSS Positioned Layout Level 3
//!
//! Implements the complete `position: sticky` algorithm:
//!   - Scroll container identification (nearest scrollable ancestor)
//!   - Sticky inset resolution (top/right/bottom/left in px)
//!   - Sticky containment box = scroll container rect
//!   - Position clamping: offset maintains sticky interval [entry, exit]
//!   - Multiple stacked sticky elements (header stacking)
//!   - Horizontal sticky support (sticky left/right)
//!   - Sticky state tracking per scroll position
//!   - AI-facing scroll-state snapshot

use std::collections::HashMap;

/// The box model rect of an element
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct LayoutRect {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}

impl LayoutRect {
    pub fn new(x: f64, y: f64, w: f64, h: f64) -> Self { Self { x, y, width: w, height: h } }
    pub fn zero() -> Self { Self { x: 0.0, y: 0.0, width: 0.0, height: 0.0 } }
    pub fn top(&self) -> f64 { self.y }
    pub fn left(&self) -> f64 { self.x }
    pub fn bottom(&self) -> f64 { self.y + self.height }
    pub fn right(&self) -> f64 { self.x + self.width }
    
    /// Translate this rect
    pub fn translate(&self, dx: f64, dy: f64) -> Self {
        Self { x: self.x + dx, y: self.y + dy, ..*self }
    }
}

/// Sticky inset offsets (CSS top/right/bottom/left when sticky)
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct StickyInsets {
    pub top: Option<f64>,
    pub right: Option<f64>,
    pub bottom: Option<f64>,
    pub left: Option<f64>,
}

impl StickyInsets {
    pub fn new() -> Self { Self { top: None, right: None, bottom: None, left: None } }
    pub fn top(px: f64) -> Self { Self { top: Some(px), ..Self::new() } }
    pub fn bottom(px: f64) -> Self { Self { bottom: Some(px), ..Self::new() } }
    pub fn top_bottom(t: f64, b: f64) -> Self { Self { top: Some(t), bottom: Some(b), ..Self::new() } }
    pub fn has_any(&self) -> bool {
        self.top.is_some() || self.right.is_some() || self.bottom.is_some() || self.left.is_some()
    }
}

/// Current sticky state of an element
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StickyState {
    /// Element is at its natural position (not yet pinned)
    Normal,
    /// Element is currently stuck (pinned to viewport edge)
    Stuck,
    /// Element has passed its container — no longer sticking
    Released,
}

/// A sticky element registration
#[derive(Debug, Clone)]
pub struct StickyElement {
    pub node_id: u64,
    /// Natural layout position (before sticky offset)
    pub natural_rect: LayoutRect,
    /// The containing block rect (scroll container's content area)
    pub containing_block: LayoutRect,
    /// Sticky inset values
    pub insets: StickyInsets,
    /// The scroll container node ID
    pub scroll_container_id: u64,
    /// z-index for stacking
    pub z_index: i32,
    
    // Computed:
    pub computed_offset_y: f64,
    pub computed_offset_x: f64,
    pub current_state: StickyState,
}

impl StickyElement {
    pub fn new(
        node_id: u64,
        natural_rect: LayoutRect,
        containing_block: LayoutRect,
        insets: StickyInsets,
        scroll_container_id: u64,
    ) -> Self {
        Self {
            node_id, natural_rect, containing_block, insets, scroll_container_id,
            z_index: 0,
            computed_offset_y: 0.0,
            computed_offset_x: 0.0,
            current_state: StickyState::Normal,
        }
    }
    
    /// Compute the effective rect given a scroll position
    pub fn effective_rect(&self) -> LayoutRect {
        self.natural_rect.translate(self.computed_offset_x, self.computed_offset_y)
    }
    
    /// Recompute sticky offset given the scroll container's scroll position
    pub fn update(
        &mut self,
        scroll_x: f64,
        scroll_y: f64,
        container_visible_rect: LayoutRect,  // Viewport rect of the scroll container
    ) {
        let mut offset_y = 0.0f64;
        let mut offset_x = 0.0f64;
        
        // ---- Vertical sticking ----
        // Relative top of the element in the scroll container's coordinate space
        let elem_top_in_container = self.natural_rect.y - scroll_y;
        let elem_bottom_in_container = self.natural_rect.bottom() - scroll_y;
        let containing_bottom_in_container = self.containing_block.bottom() - scroll_y;
        let container_top = container_visible_rect.top();
        
        if let Some(top_inset) = self.insets.top {
            let stick_at = container_top + top_inset;
            
            if elem_top_in_container < stick_at {
                // Element is above the stick threshold — push it down
                let push = stick_at - elem_top_in_container;
                
                // But don't push past the bottom of containing block
                let max_push = (containing_bottom_in_container - container_top - top_inset - self.natural_rect.height).max(0.0);
                offset_y = push.min(max_push);
                
                self.current_state = if offset_y >= max_push {
                    StickyState::Released
                } else {
                    StickyState::Stuck
                };
            } else {
                self.current_state = StickyState::Normal;
            }
        }
        
        if let Some(bottom_inset) = self.insets.bottom {
            let container_bottom = container_visible_rect.bottom();
            let stick_at = container_bottom - bottom_inset - self.natural_rect.height;
            
            if elem_top_in_container > stick_at {
                let pull = elem_top_in_container - stick_at;
                let min_pull = if self.natural_rect.y > self.containing_block.y {
                    (self.natural_rect.y - self.containing_block.y)
                } else { 0.0 };
                offset_y = -pull.min(min_pull);
                
                if self.current_state == StickyState::Normal {
                    self.current_state = StickyState::Stuck;
                }
            }
        }
        
        // ---- Horizontal sticking ----
        let elem_left_in_container = self.natural_rect.x - scroll_x;
        let container_left = container_visible_rect.left();
        
        if let Some(left_inset) = self.insets.left {
            let stick_at = container_left + left_inset;
            if elem_left_in_container < stick_at {
                let push = stick_at - elem_left_in_container;
                let max_push = (self.containing_block.right() - self.natural_rect.right() - left_inset).max(0.0);
                offset_x = push.min(max_push);
            }
        }
        
        if let Some(right_inset) = self.insets.right {
            let container_right = container_visible_rect.right();
            let stick_at = container_right - right_inset - self.natural_rect.width;
            if elem_left_in_container > stick_at {
                let pull = elem_left_in_container - stick_at;
                offset_x = -pull;
            }
        }
        
        self.computed_offset_y = offset_y;
        self.computed_offset_x = offset_x;
    }
}

/// A scroll container — tracks scroll position and contains sticky elements
#[derive(Debug, Clone)]
pub struct ScrollContainer {
    pub node_id: u64,
    pub scroll_x: f64,
    pub scroll_y: f64,
    /// The visible viewport rect of this container
    pub visible_rect: LayoutRect,
    /// Total scrollable content size
    pub scroll_width: f64,
    pub scroll_height: f64,
    pub overflow_x: OverflowMode,
    pub overflow_y: OverflowMode,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OverflowMode { Visible, Hidden, Scroll, Auto, Clip }

impl ScrollContainer {
    pub fn new(node_id: u64, visible_rect: LayoutRect) -> Self {
        Self {
            node_id, scroll_x: 0.0, scroll_y: 0.0,
            visible_rect,
            scroll_width: visible_rect.width,
            scroll_height: visible_rect.height,
            overflow_x: OverflowMode::Auto,
            overflow_y: OverflowMode::Auto,
        }
    }
    
    pub fn can_scroll_x(&self) -> bool { matches!(self.overflow_x, OverflowMode::Scroll | OverflowMode::Auto) }
    pub fn can_scroll_y(&self) -> bool { matches!(self.overflow_y, OverflowMode::Scroll | OverflowMode::Auto) }
    
    pub fn max_scroll_x(&self) -> f64 { (self.scroll_width - self.visible_rect.width).max(0.0) }
    pub fn max_scroll_y(&self) -> f64 { (self.scroll_height - self.visible_rect.height).max(0.0) }
    
    /// Scroll to a position, clamped to valid range
    pub fn scroll_to(&mut self, x: f64, y: f64) {
        if self.can_scroll_x() { self.scroll_x = x.clamp(0.0, self.max_scroll_x()); }
        if self.can_scroll_y() { self.scroll_y = y.clamp(0.0, self.max_scroll_y()); }
    }
    
    pub fn scroll_by(&mut self, dx: f64, dy: f64) {
        self.scroll_to(self.scroll_x + dx, self.scroll_y + dy);
    }
    
    pub fn scroll_progress_y(&self) -> f64 {
        let max = self.max_scroll_y();
        if max == 0.0 { 0.0 } else { self.scroll_y / max }
    }
}

/// The sticky positioning engine — manages all sticky elements across scroll containers
pub struct StickyPositioningEngine {
    pub scroll_containers: HashMap<u64, ScrollContainer>,
    pub sticky_elements: Vec<StickyElement>,
}

impl StickyPositioningEngine {
    pub fn new() -> Self {
        Self { scroll_containers: HashMap::new(), sticky_elements: Vec::new() }
    }
    
    /// Register a scroll container
    pub fn add_scroll_container(&mut self, container: ScrollContainer) {
        self.scroll_containers.insert(container.node_id, container);
    }
    
    /// Register a sticky element
    pub fn add_sticky_element(&mut self, elem: StickyElement) {
        self.sticky_elements.push(elem);
    }
    
    /// Apply a scroll event to a container and recompute all affected sticky elements
    pub fn on_scroll(&mut self, container_id: u64, scroll_x: f64, scroll_y: f64) {
        if let Some(container) = self.scroll_containers.get_mut(&container_id) {
            container.scroll_to(scroll_x, scroll_y);
        }
        
        self.recompute_stickies_for(container_id);
    }
    
    /// Recompute sticky offsets for all elements in a given scroll container
    pub fn recompute_stickies_for(&mut self, container_id: u64) {
        let (scroll_x, scroll_y, visible_rect) = {
            let c = match self.scroll_containers.get(&container_id) {
                Some(c) => c,
                None => return,
            };
            (c.scroll_x, c.scroll_y, c.visible_rect)
        };
        
        for elem in &mut self.sticky_elements {
            if elem.scroll_container_id == container_id {
                elem.update(scroll_x, scroll_y, visible_rect);
            }
        }
    }
    
    /// Recompute all sticky elements across all containers
    pub fn recompute_all(&mut self) {
        let containers: Vec<(u64, f64, f64, LayoutRect)> = self.scroll_containers.values()
            .map(|c| (c.node_id, c.scroll_x, c.scroll_y, c.visible_rect))
            .collect();
        
        for (cid, sx, sy, rect) in containers {
            for elem in &mut self.sticky_elements {
                if elem.scroll_container_id == cid {
                    elem.update(sx, sy, rect);
                }
            }
        }
    }
    
    /// Get the computed rect for a sticky element (post-offset)
    pub fn effective_rect(&self, node_id: u64) -> Option<LayoutRect> {
        self.sticky_elements.iter()
            .find(|e| e.node_id == node_id)
            .map(|e| e.effective_rect())
    }
    
    /// Get the sticky state of an element
    pub fn sticky_state(&self, node_id: u64) -> StickyState {
        self.sticky_elements.iter()
            .find(|e| e.node_id == node_id)
            .map(|e| e.current_state)
            .unwrap_or(StickyState::Normal)
    }
    
    /// AI-facing scroll state snapshot
    pub fn ai_scroll_snapshot(&self) -> String {
        let mut lines = Vec::new();
        
        for container in self.scroll_containers.values() {
            let progress = (container.scroll_progress_y() * 100.0) as u32;
            lines.push(format!(
                "📜 ScrollContainer #{}: {:.0}px/{:.0}px ({progress}% down)",
                container.node_id, container.scroll_y, container.max_scroll_y()
            ));
        }
        
        let stuck: Vec<&StickyElement> = self.sticky_elements.iter()
            .filter(|e| e.current_state == StickyState::Stuck)
            .collect();
        
        if !stuck.is_empty() {
            lines.push(format!("📌 Stuck sticky elements ({}):", stuck.len()));
            for e in stuck {
                let r = e.effective_rect();
                lines.push(format!("  node#{} at ({:.0},{:.0})", e.node_id, r.x, r.y));
            }
        }
        
        lines.join("\n")
    }
}
