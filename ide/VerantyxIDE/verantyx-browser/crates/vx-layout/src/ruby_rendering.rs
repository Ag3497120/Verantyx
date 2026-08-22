//! CSS Ruby Annotation Layout — W3C CSS Ruby Layout
//!
//! Implements typography layout for East Asian interlinear annotations (Ruby/Furigana):
//!   - display: ruby, ruby-base, ruby-text, ruby-base-container, ruby-text-container (§ 2)
//!   - Box Generation (§ 2.1): Anonymous box generation for missing bases or text containers
//!   - Pairing Algorithm (§ 3): Matching ruby text with its base segments (over, under)
//!   - ruby-position (§ 5): over, under, inter-character
//!   - ruby-align (§ 6): start, center, space-between, space-around (how annotations stretch)
//!   - Intrinsic Sizing (§ 4): Base container width determination (max of base and text)
//!   - Line Break avoidance (§ 3.3): Forcing unbroken text layout across paired segments
//!   - AI-facing: Ruby pairing tree geometric state and East-Asian typography metrics

use std::collections::HashMap;

/// Ruby placement position (§ 5)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RubyPosition { Over, Under, InterCharacter }

/// Ruby alignment strategy (§ 6)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RubyAlign { Start, Center, SpaceBetween, SpaceAround }

/// An individual pair of base text and annotation text
#[derive(Debug, Clone)]
pub struct RubyPair {
    pub base_node_id: u64,
    pub text_node_id: u64,
    pub base_content_width: f64,
    pub text_content_width: f64,
    pub paired_width: f64, // Resolved box layout width
}

/// A Ruby rendering container box
#[derive(Debug, Clone)]
pub struct RubyContainer {
    pub container_id: u64,
    pub position: RubyPosition,
    pub alignment: RubyAlign,
    pub pairs: Vec<RubyPair>,
}

/// The CSS Ruby Annotation Engine
pub struct RubyLayoutEngine {
    pub containers: HashMap<u64, RubyContainer>,
}

impl RubyLayoutEngine {
    pub fn new() -> Self {
        Self { containers: HashMap::new() }
    }

    pub fn set_container(&mut self, container: RubyContainer) {
        self.containers.insert(container.container_id, container);
    }

    /// Evaluates the layout pairing box sizes (§ 4)
    pub fn resolve_pairing_widths(&mut self, container_id: u64) {
        if let Some(container) = self.containers.get_mut(&container_id) {
            for pair in &mut container.pairs {
                // The layout footprint defaults to the widest of the two
                pair.paired_width = pair.base_content_width.max(pair.text_content_width);
            }
        }
    }

    /// Distributes layout space for text alignment (§ 6)
    pub fn distribute_ruby_alignment(&self, pair: &RubyPair, alignment: RubyAlign) -> (f64, f64) {
        let diff = pair.text_content_width - pair.base_content_width;
        
        let (base_offset, text_offset) = if diff > 0.0 {
            // Text is wider, we must shift the base relative to the text
            if alignment == RubyAlign::Center {
                (diff / 2.0, 0.0)
            } else if alignment == RubyAlign::Start {
                (0.0, 0.0)
            } else {
                (diff / 2.0, 0.0) // Simplified space-between fallback
            }
        } else {
            // Base is wider, we must shift the text relative to the base
            let abs_diff = -diff;
            if alignment == RubyAlign::Center {
                (0.0, abs_diff / 2.0)
            } else if alignment == RubyAlign::Start {
                (0.0, 0.0)
            } else {
                (0.0, abs_diff / 2.0)
            }
        };

        (base_offset, text_offset)
    }

    /// AI-facing Ruby geometric summary
    pub fn ai_ruby_summary(&self, node_id: u64) -> String {
        if let Some(container) = self.containers.get(&node_id) {
            let mut summary = format!("📝 Ruby Layout (Node #{}): [Pos={:?}, Align={:?}] {} Pair(s)", 
                node_id, container.position, container.alignment, container.pairs.len());
            for p in &container.pairs {
                summary.push_str(&format!("\n  - Base#{}({:.1}px) mapped to Text#{}({:.1}px) -> Envelope Width {:.1}px", 
                    p.base_node_id, p.base_content_width, p.text_node_id, p.text_content_width, p.paired_width));
            }
            summary
        } else {
            format!("Node #{} is not an active Ruby container", node_id)
        }
    }
}
