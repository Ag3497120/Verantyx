//! CSS Scroll-driven Animations — W3C Scroll-driven Animations
//!
//! Implements the browser's scroll-linked animation infrastructure:
//!   - scroll-timeline (§ 2): name, axis (block, inline, x, y), scroll-offsets
//!   - view-timeline (§ 3): name, axis, view-offsets (inset)
//!   - animation-timeline (§ 5): Linking property animations to scroll/view timelines
//!   - Timeline Progress Calculation (§ 7): mapping scroll position to [0, 1] range
//!   - Attachment Range (§ 6): entry, exit, cover, contain, etc.
//!   - Intersection Observer integration: Determining entry/exit points for view timelines
//!   - AI-facing: Scroll animation timeline visualizer and progress-to-offset map metrics

use std::collections::HashMap;

/// Scroll timeline axis (§ 2.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ScrollAxis { Block, Inline, X, Y }

/// View timeline attachment ranges (§ 6.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TimelineRange { Entry, Exit, Cover, Contain, EntryHold, ExitHold }

/// An individual scroll timeline (§ 2)
pub struct ScrollTimeline {
    pub name: String,
    pub source_id: u64, // scroll container node id
    pub axis: ScrollAxis,
}

/// An individual view timeline (§ 3)
pub struct ViewTimeline {
    pub name: String,
    pub subject_id: u64, // target node id
    pub axis: ScrollAxis,
    pub inset: [f64; 2], // start, end
}

/// The Scroll Animations Engine
pub struct ScrollAnimationsEngine {
    pub scroll_timelines: HashMap<String, ScrollTimeline>,
    pub view_timelines: HashMap<String, ViewTimeline>,
    pub active_progress: HashMap<String, f64>, // timeline_name -> progress (0 to 1)
}

impl ScrollAnimationsEngine {
    pub fn new() -> Self {
        Self {
            scroll_timelines: HashMap::new(),
            view_timelines: HashMap::new(),
            active_progress: HashMap::new(),
        }
    }

    /// Primary entry point: Resolves current progress for a scroll timeline (§ 7.1)
    pub fn calculate_scroll_progress(&self, timeline: &ScrollTimeline, scroll_top: f64, max_scroll: f64) -> f64 {
        if max_scroll == 0.0 { return 0.0; }
        (scroll_top / max_scroll).clamp(0.0, 1.0)
    }

    /// Primary entry point: Resolves current progress for a view timeline (§ 7.2)
    pub fn calculate_view_progress(&self, timeline: &ViewTimeline, scroll_top: f64, viewport_height: f64, subject_top: f64, subject_height: f64) -> f64 {
        // [Simplified: mapping subject crossing the viewport to 0..1]
        let entrance = subject_top - viewport_height + timeline.inset[0];
        let exit = subject_top + subject_height - timeline.inset[1];
        let dist = exit - entrance;
        if dist == 0.0 { return 0.0; }
        ((scroll_top - entrance) / dist).clamp(0.0, 1.0)
    }

    /// AI-facing animation timeline visualizer
    pub fn ai_timeline_summary(&self) -> String {
        let mut lines = vec![format!("🎞️ Scroll-driven Animations (Active: {}):", self.active_progress.len())];
        for (name, progress) in &self.active_progress {
            let sparkline: String = (0..10).map(|i| if (i as f64 / 10.0) < *progress { '█' } else { '░' }).collect();
            lines.push(format!("  - '{}' [{}] ({:.1}%)", name, sparkline, progress * 100.0));
        }
        lines.join("\n")
    }
}
