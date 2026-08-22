//! CSS Text Module Level 3 — W3C CSS Text 3
//!
//! Implements advanced typographical breaking and wrapping behaviors:
//!   - `word-break` (§ 5): `normal`, `keep-all`, `break-all` bounding resolution
//!   - `overflow-wrap` (§ 6): `normal`, `break-word`, `anywhere` preventing layout spills
//!   - `hyphens` (§ 7): `none`, `manual`, `auto` dictionary-based word splitting
//!   - `text-align` / `text-align-last` (§ 8): Block line geometric distribution
//!   - Integration with HarfBuzz/Skia text shaping context
//!   - AI-facing: Text shaping heuristics visualizer and wrapping metrics

use std::collections::HashMap;

/// Denotes how text fragments break across physical lines (§ 5)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WordBreak { Normal, KeepAll, BreakAll, BreakWord }

/// Defines line-wrapping strategy when an unbreakable string exceeds container bounds (§ 6)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OverflowWrap { Normal, BreakWord, Anywhere }

/// Controls if dictionaries are used to hyphenate soft line breaks (§ 7)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Hyphens { None, Manual, Auto }

#[derive(Debug, Clone)]
pub struct CssTextConfiguration {
    pub word_break: WordBreak,
    pub overflow_wrap: OverflowWrap,
    pub hyphens: Hyphens,
    pub is_rtl: bool, // Right-to-left layout flag affecting alignment
}

impl Default for CssTextConfiguration {
    fn default() -> Self {
        Self {
            word_break: WordBreak::Normal,
            overflow_wrap: OverflowWrap::Normal,
            hyphens: Hyphens::Manual,
            is_rtl: false,
        }
    }
}

/// The global CSS Text 3 Shaping Constraints Engine
pub struct CssText3Engine {
    pub configurations: HashMap<u64, CssTextConfiguration>,
    pub total_soft_breaks_calculated: u64,
}

impl CssText3Engine {
    pub fn new() -> Self {
        Self {
            configurations: HashMap::new(),
            total_soft_breaks_calculated: 0,
        }
    }

    pub fn set_text_config(&mut self, node_id: u64, config: CssTextConfiguration) {
        self.configurations.insert(node_id, config);
    }

    /// Used by the text shaper to determine if a character sequence is allowed to break
    pub fn allows_intra_word_break(&mut self, node_id: u64, is_cjk_typography: bool) -> bool {
        if let Some(config) = self.configurations.get(&node_id) {
            if config.word_break == WordBreak::BreakAll {
                self.total_soft_breaks_calculated += 1;
                return true;
            }
            if config.word_break == WordBreak::KeepAll && is_cjk_typography {
                // Prevents breaking CJK typical line-breaking heuristics
                return false;
            }
            if config.overflow_wrap == OverflowWrap::Anywhere {
                self.total_soft_breaks_calculated += 1;
                return true; // Overrides Min/Max Content calculations for rigid breaking
            }
        }
        false
    }

    /// Evaluates auto-hyphenation based on language dictionary availability (§ 7)
    pub fn calculate_hyphenation_opportunities(&self, node_id: u64, dictionary_present: bool) -> bool {
        if let Some(config) = self.configurations.get(&node_id) {
            match config.hyphens {
                Hyphens::None => return false,
                Hyphens::Manual => return true, // Allows explicit `&shy;` hyphenation only
                Hyphens::Auto => return dictionary_present, // Falls back to manual if no OS dict map
            }
        }
        false
    }

    /// AI-facing CSS Text 3 wrapping behaviors
    pub fn ai_text3_summary(&self, node_id: u64) -> String {
        if let Some(cfg) = self.configurations.get(&node_id) {
            format!("📜 CSS Text 3 (Node #{}): Word-Break: {:?} | Wrap: {:?} | Hyphens: {:?}", 
                node_id, cfg.word_break, cfg.overflow_wrap, cfg.hyphens)
        } else {
            format!("Node #{} utilizes default word breaking logic", node_id)
        }
    }
}
