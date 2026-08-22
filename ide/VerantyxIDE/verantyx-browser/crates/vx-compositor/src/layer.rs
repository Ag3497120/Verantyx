//! Layer Tree Structure
//!
//! Separates overlapping elements, fixed positioning, and z-indexes into distinct
//! Paint Layers, establishing the core hit-testing surface for the AI engine.

use vx_dom::NodeId;

#[derive(Debug, Clone)]
pub struct CompositingLayer {
    pub id: u64,
    pub node_id: Option<NodeId>,
    pub z_index: i32,
    pub is_fixed: bool,
    pub opacity: f32,
    pub bounds: LayerBounds,
    pub child_layers: Vec<u64>,
}

#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct LayerBounds {
    pub x: f32,
    pub y: f32,
    pub width: f32,
    pub height: f32,
}

impl LayerBounds {
    pub fn intersects(&self, other: &LayerBounds) -> bool {
        self.x < other.x + other.width &&
        self.x + self.width > other.x &&
        self.y < other.y + other.height &&
        self.y + self.height > other.y
    }
}

pub struct LayerTree {
    pub root_layer_id: u64,
    pub layers: std::collections::HashMap<u64, CompositingLayer>,
    next_layer_id: u64,
}

impl LayerTree {
    pub fn new() -> Self {
        Self {
            root_layer_id: 0,
            layers: std::collections::HashMap::new(),
            next_layer_id: 1,
        }
    }

    pub fn create_layer(&mut self, node_id: Option<NodeId>, bounds: LayerBounds, z_index: i32) -> u64 {
        let id = self.next_layer_id;
        self.next_layer_id += 1;

        let layer = CompositingLayer {
            id,
            node_id,
            z_index,
            is_fixed: false,
            opacity: 1.0,
            bounds,
            child_layers: Vec::new(),
        };

        self.layers.insert(id, layer);
        id
    }

    /// Primary Hit Testing logic utilized by the AI Agent to determine
    /// what is physically visible vs obscured purely by z-index mechanics.
    pub fn hit_test(&self, x: f32, y: f32) -> Option<u64> {
        let mut hit: Option<u64> = None;
        let mut current_z = i32::MIN;

        for layer in self.layers.values() {
            if x >= layer.bounds.x && x <= layer.bounds.x + layer.bounds.width &&
               y >= layer.bounds.y && y <= layer.bounds.y + layer.bounds.height {
                if layer.z_index >= current_z {
                    current_z = layer.z_index;
                    hit = Some(layer.id);
                }
            }
        }
        hit
    }
}
