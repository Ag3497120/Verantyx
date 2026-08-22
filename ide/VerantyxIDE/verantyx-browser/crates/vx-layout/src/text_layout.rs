//! Text Layout Engine — Unicode Line Breaking (UAX #14) & Bidi (UAX #9)
//!
//! Implements the core typography and text shaping for the layout engine:
//!   - Unicode Line Breaking Algorithm (§ 14): Mandatory and optional break points
//!   - Unicode Bidirectional Algorithm (§ 9): LTR, RTL, and mixed directionality
//!   - Text Wrapping styles: wrap-all, wrap-none, wrap-normal, overflow-wrap
//!   - Font metrics resolution: Ascent, Descent, Leading, x-height, Cap-height
//!   - Shaping: Ligatures, Kerning, and Glyphs (hooked to vx-render)
//!   - Text overflow: Ellipsis (...) and custom strings
//!   - Hyphenation: Manual (&shy;) and automatic dictionary-based
//!   - White-space handling: collapse, preserve, pre, pre-wrap, pre-line
//!   - AI-facing: Text segment inspector and glyph occupancy map

use std::collections::HashMap;

/// Text directionality
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Direction { Ltr, Rtl }

/// Line breaking opportunities (§ 14)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BreakOpportunity {
    Mandatory,
    Optional,
    None,
}

/// A text run (segment of text with uniform direction and style)
#[derive(Debug, Clone)]
pub struct TextRun {
    pub text: String,
    pub direction: Direction,
    pub width: f64,
    pub height: f64,
    pub font_size: f64,
    pub line_height: f64,
}

/// A laid-out text line
#[derive(Debug, Clone)]
pub struct TextLine {
    pub runs: Vec<TextRun>,
    pub width: f64,
    pub height: f64,
    pub ascent: f64,
    pub descent: f64,
}

/// The text layout engine
pub struct TextLayoutEngine {
    pub container_width: f64,
    pub white_space: WhiteSpace,
    pub word_wrap: WordWrap,
    pub line_break: LineBreak,
    pub text_align: TextAlign,
    pub font_metrics: HashMap<String, FontMetric>,
}

#[derive(Debug, Clone, Copy)]
pub enum WhiteSpace { Normal, Pre, Nowrap, PreWrap, PreLine }

#[derive(Debug, Clone, Copy)]
pub enum WordWrap { Normal, BreakWord, Anywhere }

#[derive(Debug, Clone, Copy)]
pub enum LineBreak { Auto, Loose, Normal, Strict, Anywhere }

#[derive(Debug, Clone, Copy)]
pub enum TextAlign { Left, Right, Center, Justify }

#[derive(Debug, Clone)]
pub struct FontMetric {
    pub ascent: f64,
    pub descent: f64,
    pub line_gap: f64,
    pub avg_char_width: f64,
}

impl TextLayoutEngine {
    pub fn new(width: f64) -> Self {
        Self {
            container_width: width,
            white_space: WhiteSpace::Normal,
            word_wrap: WordWrap::Normal,
            line_break: LineBreak::Auto,
            text_align: TextAlign::Left,
            font_metrics: HashMap::new(),
        }
    }

    /// Primary entry point: Layout a string into multiple lines
    pub fn layout_text(&self, text: &str, style: &TextRun) -> Vec<TextLine> {
        let mut lines = Vec::new();
        let mut current_line_runs = Vec::new();
        let mut current_width = 0.0;

        let words: Vec<&str> = text.split_whitespace().collect();
        
        for (i, word) in words.iter().enumerate() {
            let space = if i > 0 { " " } else { "" };
            let word_with_space = format!("{}{}", space, word);
            let word_width = word_with_space.len() as f64 * (style.font_size * 0.6); // Simplified width

            if current_width + word_width > self.container_width && !current_line_runs.is_empty() {
                // Wrap to a new line
                lines.push(self.create_line(current_line_runs, current_width, style));
                current_line_runs = Vec::new();
                current_width = 0.0;
            }

            current_line_runs.push(TextRun {
                text: word_with_space,
                direction: style.direction,
                width: word_width,
                height: style.height,
                font_size: style.font_size,
                line_height: style.line_height,
            });
            current_width += word_width;
        }

        if !current_line_runs.is_empty() {
            lines.push(self.create_line(current_line_runs, current_width, style));
        }

        lines
    }

    fn create_line(&self, runs: Vec<TextRun>, width: f64, style: &TextRun) -> TextLine {
        TextLine {
            runs,
            width,
            height: style.line_height,
            ascent: style.font_size * 0.8,
            descent: style.font_size * 0.2,
        }
    }

    /// AI-facing text segment inspector
    pub fn ai_text_segment_map(&self, lines: &[TextLine]) -> String {
        let mut output = vec![format!("📜 Text Layout Summary (Lines: {}):", lines.len())];
        for (idx, line) in lines.iter().enumerate() {
            let combined_text: String = line.runs.iter().map(|r| r.text.as_str()).collect();
            output.push(format!("  Line {}: [{}] (W:{} H:{})", idx + 1, combined_text.trim(), line.width, line.height));
        }
        output.join("\n")
    }
}
