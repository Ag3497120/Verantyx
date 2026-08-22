//! CSS Cascade module — re-exports for backward compatibility
//! The full cascade implementation is in cascade_v2.rs

pub use crate::cascade_v2::*;

// Legacy stub types that may be referenced by other modules
use std::collections::HashMap;

/// Legacy CascadeEngine placeholder (functional logic is in cascade_v2)
pub struct CascadeEngine {
    pub layer_registry: crate::cascade_v2::LayerRegistry,
}

impl CascadeEngine {
    pub fn new() -> Self {
        Self { layer_registry: crate::cascade_v2::LayerRegistry::new() }
    }
}

/// Legacy StyleSheet placeholder
pub struct StyleSheet {
    pub rules: Vec<crate::cascade_v2::CssDeclaration>,
}

impl StyleSheet {
    pub fn new() -> Self { Self { rules: Vec::new() } }
}
