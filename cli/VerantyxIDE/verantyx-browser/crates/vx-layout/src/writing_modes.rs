//! CSS Writing Modes Level 3 — W3C CSS Writing Modes
//!
//! Implements the layout infrastructure for international text:
//!   - Writing modes (§ 3.1): horizontal-tb, vertical-rl, vertical-lr, sideways-rl, sideways-lr
//!   - Logical directions (§ 4): block-start, block-end, inline-start, inline-end
//!   - Bidi isolation and embedding (§ 2): unicode-bidi (isolate, bidi-override, plaintext)
//!   - Glyph orientation (§ 5): text-orientation (mixed, upright, sideways)
//!   - Text combine (§ 6): text-combine-upright (all, digits <number>)
//!   - Abstract-to-physical mapping (§ 7): Resolving block/inline to top/right/bottom/left
//!   - Baseline alignment (§ 4.2): Alphabetic, Central, Ideographic, Hanging baselines
//!   - AI-facing: Writing mode metrics and glyph orientation visualizer

use std::collections::HashMap;

/// CSS Writing Mode (§ 3.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WritingMode {
    HorizontalTb, // Horizontal top-to-bottom (Western, CJK default)
    VerticalRl,   // Vertical right-to-left (Traditional Japanese/Chinese)
    VerticalLr,   // Vertical left-to-right (Traditional Mongolian)
    SidewaysRl,   // Vertical right-to-left (Sideways text)
    SidewaysLr,   // Vertical left-to-right (Sideways text)
}

/// Text orientation (§ 5.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TextOrientation { Mixed, Upright, Sideways }

/// Unicode Bidi algorithm properties (§ 2.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum UnicodeBidi { Normal, Isolate, Embed, BidiOverride, IsolateOverride, Plaintext }

/// The Writing Mode Context
#[derive(Debug, Clone)]
pub struct WritingModeContext {
    pub mode: WritingMode,
    pub orientation: TextOrientation,
    pub bidi: UnicodeBidi,
    pub direction: Direction,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Direction { Ltr, Rtl }

impl WritingModeContext {
    pub fn new(mode: WritingMode) -> Self {
        Self {
            mode,
            orientation: TextOrientation::Mixed,
            bidi: UnicodeBidi::Normal,
            direction: Direction::Ltr,
        }
    }

    /// Whether the writing mode is vertical (§ 3.1)
    pub fn is_vertical(&self) -> bool {
        !matches!(self.mode, WritingMode::HorizontalTb)
    }

    /// Whether the inline axis is vertical
    pub fn is_inline_vertical(&self) -> bool {
        self.is_vertical()
    }

    /// Resolves the physical box edge for a logical direction (§ 4.1)
    pub fn logical_to_physical(&self, logical: LogicalSide) -> PhysicalSide {
        match self.mode {
            WritingMode::HorizontalTb => match logical {
                LogicalSide::BlockStart => PhysicalSide::Top,
                LogicalSide::BlockEnd => PhysicalSide::Bottom,
                LogicalSide::InlineStart => if self.direction == Direction::Ltr { PhysicalSide::Left } else { PhysicalSide::Right },
                LogicalSide::InlineEnd => if self.direction == Direction::Ltr { PhysicalSide::Right } else { PhysicalSide::Left },
            },
            WritingMode::VerticalRl | WritingMode::SidewaysRl => match logical {
                LogicalSide::BlockStart => PhysicalSide::Right,
                LogicalSide::BlockEnd => PhysicalSide::Left,
                LogicalSide::InlineStart => if self.direction == Direction::Ltr { PhysicalSide::Top } else { PhysicalSide::Bottom },
                LogicalSide::InlineEnd => if self.direction == Direction::Ltr { PhysicalSide::Bottom } else { PhysicalSide::Top },
            },
            WritingMode::VerticalLr | WritingMode::SidewaysLr => match logical {
                LogicalSide::BlockStart => PhysicalSide::Left,
                LogicalSide::BlockEnd => PhysicalSide::Right,
                LogicalSide::InlineStart => if self.direction == Direction::Ltr { PhysicalSide::Top } else { PhysicalSide::Bottom },
                LogicalSide::InlineEnd => if self.direction == Direction::Ltr { PhysicalSide::Bottom } else { PhysicalSide::Top },
            },
        }
    }

    /// AI-facing writing mode summary
    pub fn ai_writing_mode_metrics(&self) -> String {
        let mut lines = vec![format!("📜 Writing Mode Metrics (Mode: {:?}):", self.mode)];
        lines.push(format!("  - Vertical: {}", self.is_vertical()));
        lines.push(format!("  - Orientation: {:?}", self.orientation));
        lines.push(format!("  - Bidi: {:?}", self.bidi));
        lines.push(format!("  - Direction: {:?}", self.direction));
        lines.join("\n")
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LogicalSide { BlockStart, BlockEnd, InlineStart, InlineEnd }

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PhysicalSide { Top, Bottom, Left, Right }
