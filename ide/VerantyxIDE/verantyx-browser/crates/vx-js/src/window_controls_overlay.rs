//! Window Controls Overlay API — W3C WCO
//!
//! Implements native desktop PWA integration, allowing web content into the app title bar:
//!   - `navigator.windowControlsOverlay` (§ 4): Assessing bounding rect of OS controls
//!   - `<meta name="theme-color">` mappings to desktop title-bar painting
//!   - Titlebar Area Rectangles (§ 5): Generating standard DOMRect geometric mapping arrays
//!   - CSS `env(titlebar-area-x)` environment variable emulation metrics
//!   - AI-facing: Desktop OS window chrome topology

use std::collections::HashMap;

/// The physical coordinates of the OS-level system buttons (minimize, maximize, close)
#[derive(Debug, Clone, Copy)]
pub struct DOMRect {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}

/// The overlay tracking state mapped to a specific web application
#[derive(Debug, Clone)]
pub struct WindowOverlayState {
    pub is_visible: bool, // Evaluates to true if display-mode is 'window-controls-overlay'
    pub titlebar_height: f64,
    pub os_controls: DOMRect, // The physical location of the red/yellow/green Mac buttons or Win buttons
    pub user_theme_color: Option<String>,
}

/// The global Engine managing PWA desktop layout integration
pub struct WindowControlsOverlayEngine {
    pub document_states: HashMap<u64, WindowOverlayState>,
}

impl WindowControlsOverlayEngine {
    pub fn new() -> Self {
        Self {
            document_states: HashMap::new(),
        }
    }

    pub fn enable_overlay_for_document(&mut self, document_id: u64, is_mac: bool) {
        // Mac typically has buttons on the left, Windows on the right
        let os_controls = if is_mac {
            DOMRect { x: 0.0, y: 0.0, width: 80.0, height: 32.0 } // macOS Traffic lights
        } else {
            DOMRect { x: 1920.0 - 140.0, y: 0.0, width: 140.0, height: 32.0 } // Windows right-aligned buttons (assuming 1920 width)
        };

        self.document_states.insert(document_id, WindowOverlayState {
            is_visible: true,
            titlebar_height: 32.0,
            os_controls,
            user_theme_color: None,
        });
    }

    /// Executed by JS: `navigator.windowControlsOverlay.getTitlebarAreaRect()` (§ 5)
    pub fn get_titlebar_area_rect(&self, document_id: u64) -> Option<DOMRect> {
        if let Some(state) = self.document_states.get(&document_id) {
            if state.is_visible {
                // Return the rectangle *not* obscured by OS buttons
                // Simply returning the full title bar minus the button width for simulation
                if state.os_controls.x == 0.0 {
                    // Mac style
                    return Some(DOMRect {
                        x: state.os_controls.width,
                        y: 0.0,
                        width: 1920.0 - state.os_controls.width,
                        height: state.titlebar_height,
                    });
                } else {
                    // Windows style
                    return Some(DOMRect {
                        x: 0.0,
                        y: 0.0,
                        width: state.os_controls.x,
                        height: state.titlebar_height,
                    });
                }
            }
        }
        None
    }

    /// Provides values injected into the CSS parsing layer for `env(titlebar-area-*)` parsing
    pub fn get_css_env_variables(&self, document_id: u64) -> HashMap<String, String> {
        let mut map = HashMap::new();
        if let Some(rect) = self.get_titlebar_area_rect(document_id) {
            map.insert("titlebar-area-x".to_string(), format!("{}px", rect.x));
            map.insert("titlebar-area-y".to_string(), format!("{}px", rect.y));
            map.insert("titlebar-area-width".to_string(), format!("{}px", rect.width));
            map.insert("titlebar-area-height".to_string(), format!("{}px", rect.height));
        }
        map
    }

    /// AI-facing Window Controls metrics
    pub fn ai_wco_summary(&self, document_id: u64) -> String {
        if let Some(state) = self.document_states.get(&document_id) {
            format!("🪟 Window Controls Overlay API (Doc #{}): Active: {} | OS Chrome Rect: X:{}/W:{}", 
                document_id, state.is_visible, state.os_controls.x, state.os_controls.width)
        } else {
            format!("Document #{} runs as a standard browser tab (no WCO enabled)", document_id)
        }
    }
}
