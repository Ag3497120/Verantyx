//! Visual Viewport API — W3C Visual Viewport
//!
//! Implements the browser's abstraction for the visual viewport:
//!   - VisualViewport interface (§ 3): offsetLeft, offsetTop, pageLeft, pageTop, width, height, scale
//!   - Coordinate Spaces (§ 2): Distinguishing the layout viewport from the visual viewport
//!   - Pinch-zoom interaction (§ 4): Handling scale factors and dynamic panning
//!   - On-Screen Keyboard (OSK) Occlusion (§ 2.1): Resizing the visual viewport when the keyboard opens
//!   - Events (§ 5): Dispatching 'resize' and 'scroll' events on the window.visualViewport
//!   - AI-facing: Visual viewport geometry visualizer and pinch-zoom state metrics

/// Geometry of the Visual Viewport (§ 3)
#[derive(Debug, Clone)]
pub struct VisualViewport {
    pub offset_left: f64,
    pub offset_top: f64,
    pub page_left: f64,
    pub page_top: f64,
    pub width: f64,
    pub height: f64,
    pub scale: f64,
}

impl Default for VisualViewport {
    fn default() -> Self {
        Self {
            offset_left: 0.0,
            offset_top: 0.0,
            page_left: 0.0,
            page_top: 0.0,
            width: 1920.0, // Default 1080p width
            height: 1080.0, // Default 1080p height
            scale: 1.0,
        }
    }
}

/// The global Visual Viewport Manager
pub struct VisualViewportManager {
    pub current_state: VisualViewport,
    pub layout_viewport_width: f64,
    pub layout_viewport_height: f64,
}

impl VisualViewportManager {
    pub fn new(layout_w: f64, layout_h: f64) -> Self {
        Self {
            current_state: VisualViewport {
                width: layout_w,
                height: layout_h,
                ..Default::default()
            },
            layout_viewport_width: layout_w,
            layout_viewport_height: layout_h,
        }
    }

    /// Handles a pinch-zoom operation from the OS or touch screen (§ 4)
    pub fn apply_pinch_zoom(&mut self, new_scale: f64, focal_x: f64, focal_y: f64) {
        // Enforce scale limits
        let clamped_scale = new_scale.max(0.1).min(10.0);
        let ratio = clamped_scale / self.current_state.scale;
        
        self.current_state.scale = clamped_scale;
        
        // Recalculate physical dimensions based on scale
        self.current_state.width = self.layout_viewport_width / clamped_scale;
        self.current_state.height = self.layout_viewport_height / clamped_scale;

        // Simplified focal point translation
        self.current_state.offset_left += focal_x * (1.0 - 1.0 / ratio);
        self.current_state.offset_top += focal_y * (1.0 - 1.0 / ratio);

        // Clamp offsets to layout boundaries
        self.clamp_offsets();
    }

    /// Triggers when the On-Screen Keyboard (OSK) opens or closes (§ 2.1)
    pub fn apply_osk_occlusion(&mut self, keyboard_height_px: f64) {
        // The visual viewport height shrinks by exactly the physical height of the keyboard
        // scaled by the current zoom level.
        self.current_state.height = (self.layout_viewport_height - keyboard_height_px) / self.current_state.scale;
        self.clamp_offsets();
    }

    fn clamp_offsets(&mut self) {
        let max_left = (self.layout_viewport_width - self.current_state.width).max(0.0);
        let max_top = (self.layout_viewport_height - self.current_state.height).max(0.0);

        self.current_state.offset_left = self.current_state.offset_left.clamp(0.0, max_left);
        self.current_state.offset_top = self.current_state.offset_top.clamp(0.0, max_top);
    }

    /// AI-facing Visual Viewport metrics
    pub fn ai_viewport_summary(&self) -> String {
        format!("👁️ Visual Viewport API: {}x{} @ {:.2}x zoom (Translates to px: {:.1}, {:.1})",
            self.current_state.width, self.current_state.height, self.current_state.scale,
            self.current_state.offset_left, self.current_state.offset_top)
    }
}
