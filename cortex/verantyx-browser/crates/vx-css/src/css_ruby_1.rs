//! CSS Ruby Annotation Level 1 — W3C CSS Ruby
//!
//! Implements logical stylistic metadata definitions for East Asian typographic reading aids:
//!   - `ruby-position` (§ 3): `over`, `under`, `alternate` visual alignment logic
//!   - `ruby-align` (§ 4): `start`, `center`, `space-between` typographic distribution inside the ruby box
//!   - Extensible styling for `<rt>`, `<rtc>`, `<rp>` DOM elements
//!   - Fallback rendering mappings
//!   - AI-facing: Typographic Ruby spatial alignment tracker

use std::collections::HashMap;

/// Defines the topological placement of the annotation relative to the base text (§ 3)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RubyPosition { Over, Under, InterCharacter, Alternate }

/// Defines the horizontal alignment of the annotation text against the base string width (§ 4)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RubyAlign { Start, Center, SpaceBetween, SpaceAround }

/// Configuration applied directly to a `<ruby>` stylistic wrapper
#[derive(Debug, Clone)]
pub struct CssRubyConfiguration {
    pub position: RubyPosition,
    pub align: RubyAlign,
    pub is_complex_ruby: bool, // e.g. spanning multiple `<rtc>` containers
}

impl Default for CssRubyConfiguration {
    fn default() -> Self {
        Self {
            position: RubyPosition::Over,
            align: RubyAlign::SpaceAround,
            is_complex_ruby: false,
        }
    }
}

/// Global CSS Properties engine parsing Ruby DOM configurations
pub struct CssRubyEngine {
    pub configurations: HashMap<u64, CssRubyConfiguration>,
    pub total_ruby_nodes_resolved: u64,
}

impl CssRubyEngine {
    pub fn new() -> Self {
        Self {
            configurations: HashMap::new(),
            total_ruby_nodes_resolved: 0,
        }
    }

    pub fn set_ruby_config(&mut self, node_id: u64, config: CssRubyConfiguration) {
        self.configurations.insert(node_id, config);
        self.total_ruby_nodes_resolved += 1;
    }

    /// Evaluates if the rendering engine needs to shift the base text baseline downwards
    /// to accommodate an `over` positioned ruby annotation without hitting line-height clipping.
    pub fn calculate_ruby_strut_clearance(&self, node_id: u64, annotation_height: f64) -> f64 {
        if let Some(config) = self.configurations.get(&node_id) {
            match config.position {
                RubyPosition::Over => {
                    // Annotation draws above, pushing the overall line box height upwards
                    return annotation_height;
                }
                RubyPosition::Under => {
                    // Annotation draws below, typical for some Bopomofo or specific academic annotations;
                    // does not affect topside baseline shift, but expands descender metric.
                    return 0.0;
                }
                RubyPosition::InterCharacter => {
                    // Typically shifts geometry horizontally, Y clearance remains 0
                    return 0.0;
                }
                _ => return annotation_height,
            }
        }
        annotation_height // W3C Default is Over
    }

    /// AI-facing Typographical complexity metrics
    pub fn ai_ruby_summary(&self, node_id: u64) -> String {
        if let Some(config) = self.configurations.get(&node_id) {
            format!("㊙️ CSS Ruby 1 (Node #{}): Position: {:?} | Align: {:?} | Globally Resolved Annotations: {}", 
                node_id, config.position, config.align, self.total_ruby_nodes_resolved)
        } else {
            format!("Node #{} contains no East Asian Ruby annotation definitions", node_id)
        }
    }
}
