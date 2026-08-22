//! vx-spatial — Sovereign Cognitive Mapping for Verantyx Browser
//!
//! Translates technical layout data into the JCross spatial memory format.
//! This is the "Visual-Spatial Bridge" for autonomous AI navigation.

use std::collections::HashMap;
use vx_dom::NodeId;
use vx_layout::box_model::BoxRect;
use serde::{Serialize, Deserialize};
use chrono::prelude::*;

pub mod jcross_v2;

/// A Point of Interest (POI) in the browser's spatial map
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PointOfInterest {
    pub label: String,
    pub bounds: BoxRect,
    pub node_id: NodeId,
    pub intent: String,
    pub metadata: HashMap<String, String>,
}

/// A spatial axis represents a cognitive "layer" (FRONT, NEAR, MID, DEEP)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SpatialAxis {
    pub name: String, // e.g., FRONT (interactive), NEAR (structural)
    pub entries: HashMap<String, String>,
    pub description: String,
}

/// The complete spatial map of the browser state
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SpatialMap {
    pub axes: Vec<SpatialAxis>,
    pub timestamp: DateTime<Utc>,
}

impl SpatialMap {
    pub fn new() -> Self {
        Self {
            axes: Vec::new(),
            timestamp: Utc::now(),
        }
    }

    pub fn add_axis(&mut self, axis: SpatialAxis) {
        self.axes.push(axis);
    }

    /// Serialize to JCross format
    pub fn to_jcross(&self) -> String {
        let mut lines = Vec::new();
        lines.push("# Verantyx Sovereign Spatial Map".to_string());
        lines.push(format!("# Generated: {}", self.timestamp.format("%Y-%m-%d %H:%M:%S")));
        lines.push("# Purpose: Point of Interest (POI) map for autonomous AI agents.".to_string());
        lines.push("".to_string());
        lines.push("CROSS spatial_browser_map {".to_string());

        for axis in &self.axes {
            lines.push("".to_string());
            lines.push(format!("    AXIS {} {{", axis.name));
            
            // Sort entries for deterministic output
            let mut keys: Vec<&String> = axis.entries.keys().collect();
            keys.sort();

            for key in keys {
                let value = axis.entries.get(key).unwrap();
                lines.push(format!("        {}: \"{}\",", key, value.replace("\"", "\\\"")));
            }

            if !axis.description.is_empty() {
                lines.push(format!("        description: \"{}\"", axis.description.replace("\"", "\\\"")));
            }
            lines.push("    }".to_string());
        }

        lines.push("}".to_string());
        lines.join("\n")
    }
}

/// Utility for clustering interactive elements into semantic units
pub struct SpatialClusterer;

impl SpatialClusterer {
    pub fn cluster(pois: &[PointOfInterest]) -> Vec<PointOfInterest> {
        // Simplified clustering for this pass: group by proximity
        // In the 300k scale engine, this would use a spatial hashing or R-tree
        pois.to_vec()
    }
}
pub mod memory_map;
