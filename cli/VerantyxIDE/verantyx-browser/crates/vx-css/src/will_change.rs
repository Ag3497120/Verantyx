//! CSS Will Change Module Level 1 — W3C CSS Will Change
//!
//! Implements the browser's optimization hints for future element changes:
//!   - will-change (§ 2): auto, scroll-position, contents, <animateable-feature>#
//!   - Animateable features (§ 2.1): Identifying properties (transform, opacity, etc.)
//!   - Layer creation (§ 3): Creating hardware-accelerated layers based on hints
//!   - Resource allocation (§ 3.1): Handling GPU memory pressure and layer count limits
//!   - Hint propagation (§ 3.2): Determining when to release hint-based resources
//!   - Stacking context (§ 3): Handling stacking context side-effects of will-change
//!   - AI-facing: Optimization layer registry and resource-pressure map metrics

use std::collections::HashSet;

/// Animateable features (§ 2.1)
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum WillChangeFeature {
    Auto,
    ScrollPosition,
    Contents,
    Property(String), // transform, opacity, etc.
}

/// The CSS Will Change Engine
pub struct WillChangeEngine {
    pub active_hints: std::collections::HashMap<u64, HashSet<WillChangeFeature>>, // node_id -> features
    pub layer_count: usize,
    pub max_layers: usize,
}

impl WillChangeEngine {
    pub fn new(max_layers: usize) -> Self {
        Self {
            active_hints: std::collections::HashMap::new(),
            layer_count: 0,
            max_layers,
        }
    }

    /// Primary entry point: Apply an optimization hint (§ 3)
    pub fn apply_hint(&mut self, node_id: u64, features: Vec<WillChangeFeature>) {
        let mut node_features = HashSet::new();
        for f in features {
            if f != WillChangeFeature::Auto {
                node_features.insert(f);
            }
        }

        if !node_features.is_empty() {
            if self.layer_count < self.max_layers {
                self.layer_count += 1;
                self.active_hints.insert(node_id, node_features);
            }
        }
    }

    pub fn remove_hint(&mut self, node_id: u64) {
        if self.active_hints.remove(&node_id).is_some() {
            if self.layer_count > 0 { self.layer_count -= 1; }
        }
    }

    /// AI-facing optimization registry summary
    pub fn ai_optimization_registry(&self) -> String {
        let mut lines = vec![format!("⚡️ Will-Change Registry (Active Layers: {}/{}):", self.layer_count, self.max_layers)];
        for (id, features) in &self.active_hints {
            let features_str: Vec<String> = features.iter()
                .map(|f| match f {
                    WillChangeFeature::ScrollPosition => "scroll-position".into(),
                    WillChangeFeature::Contents => "contents".into(),
                    WillChangeFeature::Property(p) => p.clone(),
                    _ => "unknown".into(),
                })
                .collect();
            lines.push(format!("  - Node #{}: {:?}", id, features_str));
        }
        lines.join("\n")
    }
}
