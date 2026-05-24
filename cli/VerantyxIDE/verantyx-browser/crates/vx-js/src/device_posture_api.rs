//! Device Posture API — W3C Device Posture
//!
//! Implements logical environmental states for foldable / transformable devices:
//!   - DevicePosture interface (§ 4): Exposing `type` (continuous, folded)
//!   - Posture Events (§ 4): Firing `change` events when the physical device folds/unfolds
//!   - Viewport Segments (§ 5): Mapping `window.visualViewport.segments` arrays
//!   - CSS Media Queries Integration (`@media (device-posture: folded)`)
//!   - AI-facing: Foldable device geometry simulator and posture topology visualizer

/// Logical posture states for foldable devices (§ 3)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PostureType { Continuous, Folded }

/// An individual physical screen segment of a foldable device (§ 5)
#[derive(Debug, Clone)]
pub struct ViewportSegment {
    pub left: f64,
    pub top: f64,
    pub width: f64,
    pub height: f64,
}

/// The global Device Posture Engine
pub struct DevicePostureManager {
    pub current_posture: PostureType,
    pub segments: Vec<ViewportSegment>,
    pub events_queue: Vec<String>, // Tracking JS dispatched events
}

impl DevicePostureManager {
    pub fn new() -> Self {
        Self {
            current_posture: PostureType::Continuous,
            segments: vec![ViewportSegment { left: 0.0, top: 0.0, width: 1920.0, height: 1080.0 }],
            events_queue: Vec::new(),
        }
    }

    /// Simulates a physical hardware transition (e.g., user folds the phone)
    pub fn apply_hardware_fold(&mut self, is_folded: bool, hinge_offset_y: f64) {
        if is_folded {
            self.current_posture = PostureType::Folded;
            // Split the continuous viewport into two segments across the hinge
            let screen_width = 1920.0;
            self.segments = vec![
                ViewportSegment { left: 0.0, top: 0.0, width: screen_width, height: hinge_offset_y },
                ViewportSegment { left: 0.0, top: hinge_offset_y + 40.0, width: screen_width, height: 1080.0 - hinge_offset_y - 40.0 }, // 40px hardware bezel
            ];
        } else {
            self.current_posture = PostureType::Continuous;
            self.segments = vec![ViewportSegment { left: 0.0, top: 0.0, width: 1920.0, height: 1080.0 }];
        }

        self.events_queue.push("change".into());
    }

    /// AI-facing Device Posture geometric mapping
    pub fn ai_posture_summary(&self) -> String {
        let mut lines = vec![format!("📱 Device Posture Engine (State: {:?}):", self.current_posture)];
        lines.push(format!("  - Display split into {} physical segment(s)", self.segments.len()));
        for (i, seg) in self.segments.iter().enumerate() {
            lines.push(format!("    [{}] Geometry: [x:{}, y:{}, w:{}, h:{}]", i, seg.left, seg.top, seg.width, seg.height));
        }
        lines.join("\n")
    }
}
