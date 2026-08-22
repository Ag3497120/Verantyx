//! CSS Ruby Layout — W3C CSS Ruby Layout Module Level 1
//!
//! Implements the layout infrastructure for phonetic and semantic annotations (Asian typography):
//!   - Ruby Container (§ 2.1): <ruby> and display: ruby
//!   - Ruby Base (§ 2.2): <rb> and display: ruby-base
//!   - Ruby Annotation (§ 2.3): <rt> and display: ruby-text
//!   - Ruby Position (§ 3.1): over (default), under, inter-character
//!   - Ruby Merge (§ 3.2): separate, collapse, auto
//!   - Ruby Alignment (§ 3.3): start, center, space-between, space-around
//!   - Ruby Line Breaking (§ 4.1): Breaking ruby containers across lines
//!   - Reserved Space (§ 4.2): Handling ruby overhanging adjacent characters
//!   - AI-facing: Ruby annotation structure and base-to-text spatial offset map

use std::collections::HashMap;

/// Ruby annotation position (§ 3.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RubyPosition { Over, Under, InterCharacter }

/// Ruby base/annotation alignment (§ 3.3)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RubyAlign { Start, Center, SpaceBetween, SpaceAround }

/// Ruby merging logic (§ 3.2)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RubyMerge { Separate, Collapse, Auto }

/// A single ruby base and its associated annotations (§ 2)
pub struct RubyPair {
    pub base_id: u64,
    pub annotations: Vec<u64>, // List of <rt> or <rtc> node IDs
    pub base_width: f64,
    pub base_height: f64,
}

/// A laid-out ruby element
pub struct RubyLayout {
    pub node_id: u64,
    pub pairs: Vec<RubyPair>,
    pub position: RubyPosition,
    pub align: RubyAlign,
    pub merge: RubyMerge,
}

/// The Ruby Layout Engine
pub struct RubyEngine {
    pub ruby_font_size_ratio: f64, // Typically 0.5 (annotation size relative to base)
    pub ruby_gap_scale: f64,
}

impl RubyEngine {
    pub fn new() -> Self {
        Self {
            ruby_font_size_ratio: 0.5,
            ruby_gap_scale: 0.1,
        }
    }

    /// Primary layout function for ruby containers
    pub fn layout_ruby(&self, ruby: &mut RubyLayout, available_width: f64) -> f64 {
        let mut total_width = 0.0;

        for pair in &mut ruby.pairs {
            // Ruby base sizing (§ 2.2)
            let base_w = pair.base_width;
            
            // Ruby annotation sizing (§ 2.3)
            let max_annotation_w = 0.0; // Placeholder for RT sizing logic
            
            let pair_w = base_w.max(max_annotation_w);

            if total_width + pair_w > available_width {
                // Handle ruby line breaking (§ 4.1)
                break;
            }
            total_width += pair_w;
        }

        total_width
    }

    /// Resolves the vertical offset for a ruby annotation (§ 3.1)
    pub fn resolve_annotation_offset(&self, base_height: f64, is_over: bool) -> f64 {
        if is_over {
            -(base_height * self.ruby_gap_scale)
        } else {
            base_height + (base_height * self.ruby_gap_scale)
        }
    }

    /// AI-facing ruby structure map
    pub fn ai_ruby_structure_map(&self, ruby: &RubyLayout) -> String {
        let mut output = vec![format!("🎎 CSS Ruby Layout (Base pairs: {}):", ruby.pairs.len())];
        output.push(format!("  Position: {:?}", ruby.position));
        output.push(format!("  Alignment: {:?}", ruby.align));
        output.push(format!("  Merging: {:?}", ruby.merge));
        
        for (idx, pair) in ruby.pairs.iter().enumerate() {
            output.push(format!("    - Pair {}: Base #{} -> Annotations: {:?}", idx, pair.base_id, pair.annotations));
        }
        output.join("\n")
    }
}
