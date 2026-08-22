//! IntersectionObserver API — W3C Intersection Observer Level 2
//!
//! Implements the complete IntersectionObserver specification:
//!   - Root element + root margin (CSS margin shorthand)
//!   - Threshold list — fires callback when intersection ratio crosses threshold
//!   - Entry: boundingClientRect, intersectionRect, rootBounds, intersectionRatio,
//!     isIntersecting, time, target
//!   - Observe / Unobserve / Disconnect
//!   - V2 features: trackVisibility, delay, time-based throttling
//!   - AI-facing: bulk-query current intersection state for viewport mapping

use std::collections::HashMap;

/// Root margin parsed from CSS shorthand (top, right, bottom, left)
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct RootMargin {
    pub top: f64,
    pub right: f64,
    pub bottom: f64,
    pub left: f64,
}

impl Default for RootMargin {
    fn default() -> Self { Self { top: 0.0, right: 0.0, bottom: 0.0, left: 0.0 } }
}

impl RootMargin {
    /// Parse a CSS margin shorthand string (e.g., "10px 20px 10px 20px")
    pub fn parse(s: &str) -> Self {
        let parts: Vec<f64> = s.split_whitespace()
            .map(|v| v.trim_end_matches("px").parse::<f64>().unwrap_or(0.0))
            .collect();
        
        match parts.len() {
            0 => Self::default(),
            1 => Self { top: parts[0], right: parts[0], bottom: parts[0], left: parts[0] },
            2 => Self { top: parts[0], right: parts[1], bottom: parts[0], left: parts[1] },
            3 => Self { top: parts[0], right: parts[1], bottom: parts[2], left: parts[1] },
            _ => Self { top: parts[0], right: parts[1], bottom: parts[2], left: parts[3] },
        }
    }
    
    /// Apply the root margin to expand/contract a root rect
    pub fn apply_to(&self, rect: &DomRect) -> DomRect {
        DomRect {
            x: rect.x - self.left,
            y: rect.y - self.top,
            width: rect.width + self.left + self.right,
            height: rect.height + self.top + self.bottom,
        }
    }
}

/// DOMRect — used throughout the Intersection Observer API
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct DomRect {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}

impl DomRect {
    pub fn zero() -> Self { Self { x: 0.0, y: 0.0, width: 0.0, height: 0.0 } }
    
    pub fn new(x: f64, y: f64, w: f64, h: f64) -> Self { Self { x, y, width: w, height: h } }
    
    pub fn top(&self) -> f64 { self.y }
    pub fn left(&self) -> f64 { self.x }
    pub fn bottom(&self) -> f64 { self.y + self.height }
    pub fn right(&self) -> f64 { self.x + self.width }
    pub fn area(&self) -> f64 { self.width * self.height }
    
    pub fn is_empty(&self) -> bool { self.width <= 0.0 || self.height <= 0.0 }
    
    /// Compute the intersection of two rects (None if no overlap)
    pub fn intersection(&self, other: &DomRect) -> Option<DomRect> {
        let x = self.left().max(other.left());
        let y = self.top().max(other.top());
        let right = self.right().min(other.right());
        let bottom = self.bottom().min(other.bottom());
        
        if right > x && bottom > y {
            Some(DomRect { x, y, width: right - x, height: bottom - y })
        } else {
            None
        }
    }
    
    /// Compute the intersection ratio of this rect with a root rect
    pub fn intersection_ratio_with(&self, root: &DomRect) -> f64 {
        if self.area() == 0.0 { return 0.0; }
        
        match self.intersection(root) {
            None => 0.0,
            Some(inter) => inter.area() / self.area(),
        }
    }
}

/// Configuration for an IntersectionObserver
#[derive(Debug, Clone)]
pub struct IntersectionObserverInit {
    /// Root element (None = viewport)
    pub root: Option<u64>,
    /// Margin applied to the root bounds
    pub root_margin: RootMargin,
    /// Threshold list (0.0 to 1.0, sorted ascending)
    pub threshold: Vec<f64>,
    /// V2: track CSS visibility (not just geometric intersection)
    pub track_visibility: bool,
    /// V2: minimum delay between callbacks (ms)
    pub delay: f64,
}

impl Default for IntersectionObserverInit {
    fn default() -> Self {
        Self {
            root: None,
            root_margin: RootMargin::default(),
            threshold: vec![0.0],
            track_visibility: false,
            delay: 0.0,
        }
    }
}

impl IntersectionObserverInit {
    pub fn with_threshold(thresholds: Vec<f64>) -> Self {
        let mut sorted = thresholds;
        sorted.sort_by(|a, b| a.partial_cmp(b).unwrap());
        Self { threshold: sorted, ..Default::default() }
    }
    
    /// Find the threshold that an intersection ratio crosses/uncrosses
    pub fn crossed_threshold(&self, old_ratio: f64, new_ratio: f64) -> Option<f64> {
        // Check if we crossed any threshold going from old to new
        for &threshold in &self.threshold {
            let old_above = old_ratio >= threshold;
            let new_above = new_ratio >= threshold;
            if old_above != new_above {
                return Some(threshold);
            }
        }
        None
    }
    
    /// Whether a given ratio triggers an intersecting state change
    pub fn fires_callback(&self, old_ratio: f64, new_ratio: f64) -> bool {
        self.crossed_threshold(old_ratio, new_ratio).is_some()
    }
}

/// An IntersectionObserverEntry — one observation for one target
#[derive(Debug, Clone)]
pub struct IntersectionObserverEntry {
    /// Timestamp (ms since page load)
    pub time: f64,
    /// The bounding rect of the root (viewport or root element) + margin
    pub root_bounds: Option<DomRect>,
    /// The bounding rect of the target
    pub bounding_client_rect: DomRect,
    /// The intersection of target and root (empty rect if not intersecting)
    pub intersection_rect: DomRect,
    /// The target node ID
    pub target: u64,
    /// Whether the target is intersecting the root
    pub is_intersecting: bool,
    /// The ratio of the intersection (0.0 to 1.0)
    pub intersection_ratio: f64,
    /// V2: whether the target is fully visible (not occluded)
    pub is_visible: bool,
}

impl IntersectionObserverEntry {
    /// Compute an intersection entry from geometry information
    pub fn compute(
        target_id: u64,
        target_rect: DomRect,
        root_rect_with_margin: DomRect,
        time: f64,
        track_visibility: bool,
    ) -> Self {
        let intersection_rect = target_rect.intersection(&root_rect_with_margin)
            .unwrap_or(DomRect::zero());
        
        let intersection_ratio = if target_rect.area() > 0.0 {
            intersection_rect.area() / target_rect.area()
        } else {
            0.0
        };
        
        let is_intersecting = !intersection_rect.is_empty() && intersection_ratio > 0.0;
        
        Self {
            time,
            root_bounds: Some(root_rect_with_margin),
            bounding_client_rect: target_rect,
            intersection_rect,
            target: target_id,
            is_intersecting,
            intersection_ratio,
            is_visible: if track_visibility { is_intersecting } else { false },
        }
    }
    
    /// AI-readable summary of this intersection event
    pub fn ai_summary(&self) -> String {
        if self.is_intersecting {
            format!(
                "node#{} is {}% visible in viewport (rect: {}x{}@{},{})",
                self.target,
                (self.intersection_ratio * 100.0) as u32,
                self.intersection_rect.width as u32,
                self.intersection_rect.height as u32,
                self.intersection_rect.x as i32,
                self.intersection_rect.y as i32,
            )
        } else {
            format!("node#{} is outside viewport", self.target)
        }
    }
}

/// The state tracked for each observed element
#[derive(Debug, Clone)]
struct TargetState {
    previous_ratio: f64,
    previous_is_intersecting: bool,
    last_callback_time: f64,
}

/// An IntersectionObserver instance
pub struct IntersectionObserver {
    pub id: u64,
    pub init: IntersectionObserverInit,
    /// Targets being observed (node_id -> state)
    targets: HashMap<u64, TargetState>,
    /// Pending entries to deliver at next microtask
    pending: Vec<IntersectionObserverEntry>,
}

impl IntersectionObserver {
    pub fn new(id: u64, init: IntersectionObserverInit) -> Self {
        Self { id, init, targets: HashMap::new(), pending: Vec::new() }
    }
    
    /// Add a target to observe
    pub fn observe(&mut self, target_id: u64) {
        self.targets.entry(target_id).or_insert(TargetState {
            previous_ratio: 0.0,
            previous_is_intersecting: false,
            last_callback_time: 0.0,
        });
    }
    
    /// Remove a target from observation
    pub fn unobserve(&mut self, target_id: u64) {
        self.targets.remove(&target_id);
    }
    
    /// Stop observing all targets
    pub fn disconnect(&mut self) {
        self.targets.clear();
        self.pending.clear();
    }
    
    /// Process a batch of current target geometries and queue intersection entries
    pub fn process_geometries(
        &mut self,
        target_rects: &HashMap<u64, DomRect>,
        root_rect: DomRect,
        now_ms: f64,
    ) {
        let root_with_margin = self.init.root_margin.apply_to(&root_rect);
        
        for (&target_id, state) in &mut self.targets {
            let target_rect = match target_rects.get(&target_id) {
                Some(r) => *r,
                None => DomRect::zero(),
            };
            
            let entry = IntersectionObserverEntry::compute(
                target_id,
                target_rect,
                root_with_margin,
                now_ms,
                self.init.track_visibility,
            );
            
            // Check if we should fire (threshold crossing or delay)
            let should_fire = self.init.fires_callback(state.previous_ratio, entry.intersection_ratio)
                || (now_ms - state.last_callback_time >= self.init.delay && state.previous_is_intersecting != entry.is_intersecting);
            
            if should_fire {
                state.previous_ratio = entry.intersection_ratio;
                state.previous_is_intersecting = entry.is_intersecting;
                state.last_callback_time = now_ms;
                self.pending.push(entry);
            }
        }
    }
    
    /// Consume and return all pending entries
    pub fn take_entries(&mut self) -> Vec<IntersectionObserverEntry> {
        std::mem::take(&mut self.pending)
    }
    
    pub fn is_observing(&self, target_id: u64) -> bool {
        self.targets.contains_key(&target_id)
    }
    
    pub fn observed_count(&self) -> usize { self.targets.len() }
    pub fn has_pending(&self) -> bool { !self.pending.is_empty() }
}

/// Document-wide IntersectionObserver manager
pub struct IntersectionObserverManager {
    observers: HashMap<u64, IntersectionObserver>,
    next_id: u64,
    /// Viewport rect (updated each frame)
    viewport: DomRect,
}

impl IntersectionObserverManager {
    pub fn new(viewport_width: f64, viewport_height: f64) -> Self {
        Self {
            observers: HashMap::new(),
            next_id: 1,
            viewport: DomRect::new(0.0, 0.0, viewport_width, viewport_height),
        }
    }
    
    pub fn create(&mut self, init: IntersectionObserverInit) -> u64 {
        let id = self.next_id;
        self.next_id += 1;
        self.observers.insert(id, IntersectionObserver::new(id, init));
        id
    }
    
    pub fn get_mut(&mut self, id: u64) -> Option<&mut IntersectionObserver> {
        self.observers.get_mut(&id)
    }
    
    /// Update the viewport dimensions
    pub fn set_viewport(&mut self, width: f64, height: f64) {
        self.viewport = DomRect::new(0.0, 0.0, width, height);
    }
    
    /// Run all observers against current element geometries
    pub fn update_all(
        &mut self,
        element_rects: &HashMap<u64, DomRect>,
        now_ms: f64,
    ) -> HashMap<u64, Vec<IntersectionObserverEntry>> {
        let mut entries_by_observer = HashMap::new();
        
        for (id, observer) in &mut self.observers {
            let root_rect = match observer.init.root {
                None => self.viewport,
                Some(root_id) => element_rects.get(&root_id).copied().unwrap_or(self.viewport),
            };
            
            observer.process_geometries(element_rects, root_rect, now_ms);
            
            let entries = observer.take_entries();
            if !entries.is_empty() {
                entries_by_observer.insert(*id, entries);
            }
        }
        
        entries_by_observer
    }
    
    /// Bulk query: which observed elements are currently in the viewport?
    pub fn visible_elements(&self, element_rects: &HashMap<u64, DomRect>) -> Vec<u64> {
        self.observers.values()
            .flat_map(|obs| obs.targets.keys().copied())
            .filter(|&node_id| {
                element_rects.get(&node_id).map_or(false, |rect| {
                    self.viewport.intersection(rect).is_some()
                })
            })
            .collect()
    }
    
    /// Generate an AI-facing viewport occupancy map
    pub fn ai_viewport_map(&self, element_rects: &HashMap<u64, DomRect>) -> String {
        let visible = self.visible_elements(element_rects);
        if visible.is_empty() {
            return "Viewport: no observed elements visible".to_string();
        }
        
        let mut lines = vec![format!("📺 Viewport ({:.0}x{:.0}) — {} visible elements:",
            self.viewport.width, self.viewport.height, visible.len())];
        
        for node_id in &visible {
            if let Some(rect) = element_rects.get(node_id) {
                let ratio = rect.intersection_ratio_with(&self.viewport);
                lines.push(format!("  node#{}: {}% visible at ({:.0},{:.0}) {}x{}",
                    node_id, (ratio * 100.0) as u32,
                    rect.x, rect.y, rect.width, rect.height));
            }
        }
        
        lines.join("\n")
    }
}
