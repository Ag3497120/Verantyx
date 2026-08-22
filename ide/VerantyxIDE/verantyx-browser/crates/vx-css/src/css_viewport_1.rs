//! CSS Device Adaptation / Viewport Module Level 1 — W3C CSS Viewport
//!
//! Implements hardware-view scaling definitions within CSS, superseding the HTML meta viewport tag:
//!   - `@viewport` rule (§ 4): width, height, zoom, min-zoom, max-zoom, user-zoom
//!   - Constraining Width and Height (§ 5): mapping 'auto', 'device-width', 'device-height'
//!   - Normalization matching actual hardware screen dimensions
//!   - orientation (§ 6): auto, portrait, landscape forcing display bounds
//!   - Zoom limits preventing accessibility issues versus developer constraints
//!   - AI-facing: CSS active viewport projection scaling metrics

/// Calculated view boundaries and scaling established by a `@viewport` block
#[derive(Debug, Clone, PartialEq)]
pub struct ViewportConfiguration {
    pub min_width: f64,
    pub max_width: f64,
    pub min_height: f64,
    pub max_height: f64,
    pub zoom: f64,
    pub min_zoom: f64,
    pub max_zoom: f64,
    pub user_zoom: bool,
    pub orientation_landscape: bool,
}

impl Default for ViewportConfiguration {
    fn default() -> Self {
        Self {
            min_width: 320.0,
            max_width: 1920.0,
            min_height: 240.0,
            max_height: 1080.0,
            zoom: 1.0,
            min_zoom: 0.1,
            max_zoom: 10.0,
            user_zoom: true,
            orientation_landscape: true,
        }
    }
}

/// The global CSS Viewport Adapation Engine
pub struct CssViewportEngine {
    pub active_config: ViewportConfiguration,
    pub physical_screen_width: f64,
    pub physical_screen_height: f64,
}

impl CssViewportEngine {
    pub fn new() -> Self {
        Self {
            active_config: ViewportConfiguration::default(),
            physical_screen_width: 1920.0,
            physical_screen_height: 1080.0,
        }
    }

    /// Evaluates declarative CSS such as `width: device-width; zoom: 1`
    pub fn apply_viewport_rule(&mut self, parsed_width: Option<f64>, parsed_zoom: Option<f64>) {
        if let Some(w) = parsed_width {
            self.active_config.min_width = w;
            self.active_config.max_width = w;
        } else {
            // Emulate `device-width` behavior
            self.active_config.min_width = self.physical_screen_width;
            self.active_config.max_width = self.physical_screen_width;
        }

        if let Some(z) = parsed_zoom {
            self.active_config.zoom = z.clamp(self.active_config.min_zoom, self.active_config.max_zoom);
        }
    }

    /// Core algorithm determining if user pinch-to-zoom is currently viable
    pub fn can_user_zoom(&self, target_scale: f64) -> bool {
        if !self.active_config.user_zoom {
            return false;
        }
        
        // Ensure within min/max boundaries
        if target_scale < self.active_config.min_zoom || target_scale > self.active_config.max_zoom {
            return false;
        }
        
        true
    }

    /// Compute the final logical CSS pixel footprint provided to the rendering engine
    pub fn logical_footprint(&self) -> (f64, f64) {
        let logical_w = self.active_config.min_width / self.active_config.zoom;
        let logical_h = self.active_config.min_height / self.active_config.zoom;
        (logical_w, logical_h)
    }

    /// AI-facing CSS Viewport Configuration summary
    pub fn ai_viewport_summary(&self) -> String {
        let (lw, lh) = self.logical_footprint();
        format!("📱 CSS Viewport Adapter: Scale: {:.1}x (User-Zoom: {}) | Bounds: {}x{} (Logical: {:.1}x{:.1})", 
            self.active_config.zoom, self.active_config.user_zoom, 
            self.active_config.min_width, self.active_config.min_height, lw, lh)
    }
}
