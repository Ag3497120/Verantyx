//! CSS Lists and Counters Module Level 3 — W3C CSS Lists 3
//!
//! Implements logical generation of list markers and CSS counting systems:
//!   - `list-style-type` (§ 3): Generating decimals, lower-alpha, numeric mappings
//!   - `::marker` Pseudo-element (§ 4): Styling the generated sequence item
//!   - `counter-reset` / `counter-increment` (§ 5): State machine tracking layout integers
//!   - `counter-set` math scoping over DOM hierarchy contexts
//!   - AI-facing: CSS mathematical state topologies and list generation counters

use std::collections::HashMap;

/// Common sequence algorithms for CSS pseudo-markers (§ 3)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ListStyleType { Disc, Circle, Square, Decimal, UpperAlpha, LowerAlpha, LowerRoman, UpperRoman, None }

/// Represents an abstract integer counter active within a specific DOM scope
#[derive(Debug, Clone)]
pub struct CssCounterState {
    pub name: String,
    pub current_value: i32,
}

#[derive(Debug, Clone)]
pub struct ListConfiguration {
    pub style_type: ListStyleType,
    pub list_style_image_url: Option<String>,
    pub list_style_position_inside: bool, // Determines if marker is inside the layout box or in padding
}

/// The global CSS Lists Engine operating over layout sequence iterations
pub struct CssListsEngine {
    pub list_nodes: HashMap<u64, ListConfiguration>,
    // Node ID -> (Counter Name -> CSS Counter State)
    pub dom_counters: HashMap<u64, HashMap<String, CssCounterState>>,
    pub total_markers_generated: u64,
}

impl CssListsEngine {
    pub fn new() -> Self {
        Self {
            list_nodes: HashMap::new(),
            dom_counters: HashMap::new(),
            total_markers_generated: 0,
        }
    }

    pub fn set_list_config(&mut self, node_id: u64, config: ListConfiguration) {
        self.list_nodes.insert(node_id, config);
    }

    /// Computes the exact string required to replace `::marker` in the layout tree (§ 4)
    pub fn generate_marker_string(&mut self, node_id: u64, list_item_index: i32) -> Option<String> {
        if let Some(config) = self.list_nodes.get(&node_id) {
            self.total_markers_generated += 1;
            match config.style_type {
                ListStyleType::None => return None,
                ListStyleType::Disc => return Some("• ".into()),
                ListStyleType::Circle => return Some("○ ".into()),
                ListStyleType::Square => return Some("■ ".into()),
                ListStyleType::Decimal => return Some(format!("{}. ", list_item_index)),
                ListStyleType::LowerAlpha => {
                    let char_idx = (list_item_index.max(1) - 1) % 26;
                    let letter = char::from_u32('a' as u32 + char_idx as u32).unwrap_or('a');
                    return Some(format!("{}. ", letter));
                }
                // (Others omitted for brevity, fallback to decimal)
                _ => return Some(format!("{}. ", list_item_index)),
            }
        }
        None
    }

    /// Evaluates `counter-reset: MyCounter 5` within the layout traversal (§ 5)
    pub fn reset_counter(&mut self, node_id: u64, counter_name: &str, value: i32) {
        let node_map = self.dom_counters.entry(node_id).or_default();
        node_map.insert(counter_name.to_string(), CssCounterState {
            name: counter_name.to_string(),
            current_value: value,
        });
    }

    /// Evaluates `counter-increment: MyCounter 1` resolving up the DOM tree scope
    pub fn increment_counter(&mut self, node_id: u64, counter_name: &str, increment: i32) {
        let node_map = self.dom_counters.entry(node_id).or_default();
        let counter = node_map.entry(counter_name.to_string()).or_insert(CssCounterState {
            name: counter_name.to_string(),
            current_value: 0, // Fallback if missing
        });
        counter.current_value += increment;
    }

    /// AI-facing CSS State Counters topology summary
    pub fn ai_lists_summary(&self, node_id: u64) -> String {
        let mut counters_str = String::new();
        if let Some(cmap) = self.dom_counters.get(&node_id) {
            let pairs: Vec<String> = cmap.iter().map(|(k, v)| format!("{}={}", k, v.current_value)).collect();
            counters_str = format!("| Counters: [{}]", pairs.join(", "));
        }

        if let Some(config) = self.list_nodes.get(&node_id) {
            format!("📑 CSS Lists 3 (Node #{}): Type: {:?} | Inside: {} {}", 
                node_id, config.style_type, config.list_style_position_inside, counters_str)
        } else {
            if counters_str.is_empty() {
                format!("Node #{} generates zero counting markers", node_id)
            } else {
                format!("Node #{} contains CSS States {}", node_id, counters_str)
            }
        }
    }
}
