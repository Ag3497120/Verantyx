//! CSS Text Module Level 4 — W3C CSS Text 4
//!
//! Implements advanced multi-lingual and aesthetic typographic bounding matrices:
//!   - `text-wrap: balance / pretty` (§ 7): Preventing widow lines and balancing line geometries
//!   - `text-spacing-trim` (§ 8): CJK (Chinese, Japanese, Korean) punctuation kerning optimizations
//!   - `hyphenate-limit-chars` (§ 6): Controlling text fragmentation at line boundaries
//!   - AI-facing: CSS Typographic formatting intent mapping

use std::collections::HashMap;

/// Controls the line-breaking geometry algorithms
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TextWrapStyle { Wrap, NoWrap, Balance, Pretty }

/// Advanced structural kerning rules for non-Latin script parsing
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TextSpacingTrimConfig { Normal, SpaceAll, SpaceFirst, TrimStart }

/// Extracted Configuration for a specific Text Node
#[derive(Debug, Clone)]
pub struct TextFormattingConfiguration {
    pub wrap_style: TextWrapStyle,
    pub spacing_trim: TextSpacingTrimConfig,
    pub hyphenate_limit_before: u8,
    pub hyphenate_limit_after: u8,
}

impl Default for TextFormattingConfiguration {
    fn default() -> Self {
        Self {
            wrap_style: TextWrapStyle::Wrap,
            spacing_trim: TextSpacingTrimConfig::Normal,
            hyphenate_limit_before: 2,
            hyphenate_limit_after: 2,
        }
    }
}

/// The global Constraint Resolver bridging CSS parsed properties to the physical Line-Breaker (HarfBuzz/ICU)
pub struct CssText4Engine {
    pub node_typographics: HashMap<u64, TextFormattingConfiguration>,
    pub total_balanced_blocks: u64,
}

impl CssText4Engine {
    pub fn new() -> Self {
        Self {
            node_typographics: HashMap::new(),
            total_balanced_blocks: 0,
        }
    }

    pub fn set_text_config(&mut self, node_id: u64, decl: TextFormattingConfiguration) {
        if decl.wrap_style == TextWrapStyle::Balance || decl.wrap_style == TextWrapStyle::Pretty {
            self.total_balanced_blocks += 1;
        }
        self.node_typographics.insert(node_id, decl);
    }

    /// Executed by `vx-layout` Line-Box generation.
    /// Determines if a standard greedy layout algorithm is used, or if a Knuth-Plass
    /// style multi-pass optimization is required to balance physical line widths.
    pub fn requires_algorithmic_balancing(&self, node_id: u64) -> bool {
        if let Some(config) = self.node_typographics.get(&node_id) {
            return config.wrap_style == TextWrapStyle::Balance || config.wrap_style == TextWrapStyle::Pretty;
        }
        false
    }
    
    /// Evaluator for CJK (Japanese/Chinese) ideographic space collapsing at line starts
    pub fn compute_CJK_kerning_trim(&self, node_id: u64, is_start_of_line: bool) -> bool {
        if let Some(config) = self.node_typographics.get(&node_id) {
            match config.spacing_trim {
                TextSpacingTrimConfig::TrimStart => return is_start_of_line, // Delete the extra half-width space visually
                TextSpacingTrimConfig::SpaceFirst => return !is_start_of_line,
                _ => return false,
            }
        }
        false
    }

    /// AI-facing Aesthetic CSS Reading bounds
    pub fn ai_text_formatting_summary(&self, node_id: u64) -> String {
        if let Some(config) = self.node_typographics.get(&node_id) {
            format!("🖋️ CSS Text 4 (Node #{}): Wrap Metric: {:?} | CJK Trim: {:?} | Hyphen Limits: {}/{} | Global Balanced Paragraphs: {}", 
                node_id, config.wrap_style, config.spacing_trim, config.hyphenate_limit_before, config.hyphenate_limit_after, self.total_balanced_blocks)
        } else {
            format!("Node #{} executes native greedy word-break wrapping geometries", node_id)
        }
    }
}
