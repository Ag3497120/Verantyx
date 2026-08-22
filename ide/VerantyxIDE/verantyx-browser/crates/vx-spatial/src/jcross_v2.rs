//! JCross v2 — Browser-Specific Spatial Memory Axis Definitions
//!
//! Provides structured cognitive layers optimized for browser-based AI autonomy.

use crate::{SpatialMap, SpatialAxis};
use std::collections::HashMap;

/// Standard axes for browser cognitive mapping
pub enum BrowserAxis {
    Front,  // Immediate interaction (POIs in view)
    Near,   // Tab state and structural summary
    Mid,    // Historical context or background tabs
    Deep,   // Long-term page knowledge/archives
}

impl BrowserAxis {
    pub fn as_str(&self) -> &'static str {
        match self {
            BrowserAxis::Front => "FRONT",
            BrowserAxis::Near => "NEAR",
            BrowserAxis::Mid => "MID",
            BrowserAxis::Deep => "DEEP",
        }
    }
}

pub struct BrowserSpatialBridge;

impl BrowserSpatialBridge {
    /// Create a standard AXIS FRONT for interactive elements
    pub fn create_front_axis(elements: &[(usize, String, f32, f32)]) -> SpatialAxis {
        let mut entries = HashMap::new();
        for (id, label, x, y) in elements {
            let key = format!("poi_{}", id);
            let value = format!("\"{}\" at ({:.0}, {:.0})", label, x, y);
            entries.insert(key, value);
        }

        SpatialAxis {
            name: BrowserAxis::Front.as_str().to_string(),
            entries,
            description: "High-priority interactive elements in the current viewport.".to_string(),
        }
    }

    /// Create a standard AXIS NEAR for current tab context
    pub fn create_near_axis(url: &str, title: &str, summary: &str) -> SpatialAxis {
        let mut entries = HashMap::new();
        entries.insert("url".to_string(), url.to_string());
        entries.insert("title".to_string(), title.to_string());
        entries.insert("semantic_summary".to_string(), summary.to_string());

        SpatialAxis {
            name: BrowserAxis::Near.as_str().to_string(),
            entries,
            description: "Active tab metadata and high-level page structure.".to_string(),
        }
    }
}

/// Extension for SpatialMap to support quick browser axis injection
pub trait BrowserSpatialExt {
    fn inject_browser_state(&mut self, url: &str, title: &str, summary: &str);
}

impl BrowserSpatialExt for SpatialMap {
    fn inject_browser_state(&mut self, url: &str, title: &str, summary: &str) {
        self.add_axis(BrowserSpatialBridge::create_near_axis(url, title, summary));
    }
}
