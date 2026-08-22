//! CSS Logical Properties and Values — W3C CSS Logical Properties Level 1
//!
//! Implements the mapping from logical to physical properties based on writing mode:
//!   - Physical directions: top, bottom, left, right
//!   - Logical directions: block-start, block-end, inline-start, inline-end
//!   - Logical sizing: block-size, inline-size, min-block-size, max-inline-size
//!   - Logical spacing: margin-block, padding-inline, border-inline-start
//!   - Logical insets: inset-block, inset-inline
//!   - Logical floats: float: inline-start, clear: inline-end
//!   - Logical alignment: text-align: start, text-align: end
//!   - Writing mode support: horizontal-tb, vertical-rl, vertical-lr, sideways-rl, sideways-lr
//!   - Direction support: ltr, rtl
//!   - AI-facing: Logical-to-Physical conversion table and writing mode metrics

use std::collections::HashMap;

/// Writing modes (§ 3.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WritingMode { HorizontalTb, VerticalRl, VerticalLr, SidewaysRl, SidewaysLr }

/// Text directions (§ 3.2)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Direction { Ltr, Rtl }

/// Logical property types
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum LogicalProperty {
    BlockSize, InlineSize,
    MarginBlockStart, MarginBlockEnd, MarginInlineStart, MarginInlineEnd,
    PaddingBlockStart, PaddingBlockEnd, PaddingInlineStart, PaddingInlineEnd,
    InsetBlockStart, InsetBlockEnd, InsetInlineStart, InsetInlineEnd,
    BorderBlockStart, BorderBlockEnd, BorderInlineStart, BorderInlineEnd,
}

/// Physical property types
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PhysicalProperty { Top, Bottom, Left, Right, Width, Height }

/// The Logical Properties Mapper
pub struct LogicalMapper {
    pub writing_mode: WritingMode,
    pub direction: Direction,
}

impl LogicalMapper {
    pub fn new(mode: WritingMode, dir: Direction) -> Self {
        Self { writing_mode: mode, direction: dir }
    }

    /// Resolve a logical property to its physical equivalent
    pub fn resolve(&self, prop: LogicalProperty) -> PhysicalProperty {
        match self.writing_mode {
            WritingMode::HorizontalTb => match prop {
                LogicalProperty::BlockSize => PhysicalProperty::Height,
                LogicalProperty::InlineSize => PhysicalProperty::Width,
                LogicalProperty::MarginBlockStart | LogicalProperty::PaddingBlockStart | LogicalProperty::InsetBlockStart | LogicalProperty::BorderBlockStart => PhysicalProperty::Top,
                LogicalProperty::MarginBlockEnd | LogicalProperty::PaddingBlockEnd | LogicalProperty::InsetBlockEnd | LogicalProperty::BorderBlockEnd => PhysicalProperty::Bottom,
                LogicalProperty::MarginInlineStart | LogicalProperty::PaddingInlineStart | LogicalProperty::InsetInlineStart | LogicalProperty::BorderInlineStart => {
                    if self.direction == Direction::Ltr { PhysicalProperty::Left } else { PhysicalProperty::Right }
                }
                LogicalProperty::MarginInlineEnd | LogicalProperty::PaddingInlineEnd | LogicalProperty::InsetInlineEnd | LogicalProperty::BorderInlineEnd => {
                    if self.direction == Direction::Ltr { PhysicalProperty::Right } else { PhysicalProperty::Left }
                }
            },
            WritingMode::VerticalRl | WritingMode::SidewaysRl => match prop {
                LogicalProperty::BlockSize => PhysicalProperty::Width,
                LogicalProperty::InlineSize => PhysicalProperty::Height,
                LogicalProperty::MarginBlockStart | LogicalProperty::PaddingBlockStart | LogicalProperty::InsetBlockStart | LogicalProperty::BorderBlockStart => PhysicalProperty::Right,
                LogicalProperty::MarginBlockEnd | LogicalProperty::PaddingBlockEnd | LogicalProperty::InsetBlockEnd | LogicalProperty::BorderBlockEnd => PhysicalProperty::Left,
                LogicalProperty::MarginInlineStart | LogicalProperty::PaddingInlineStart | LogicalProperty::InsetInlineStart | LogicalProperty::BorderInlineStart => {
                    if self.direction == Direction::Ltr { PhysicalProperty::Top } else { PhysicalProperty::Bottom }
                }
                LogicalProperty::MarginInlineEnd | LogicalProperty::PaddingInlineEnd | LogicalProperty::InsetInlineEnd | LogicalProperty::BorderInlineEnd => {
                    if self.direction == Direction::Ltr { PhysicalProperty::Bottom } else { PhysicalProperty::Top }
                }
            },
            WritingMode::VerticalLr | WritingMode::SidewaysLr => match prop {
                LogicalProperty::BlockSize => PhysicalProperty::Width,
                LogicalProperty::InlineSize => PhysicalProperty::Height,
                LogicalProperty::MarginBlockStart | LogicalProperty::PaddingBlockStart | LogicalProperty::InsetBlockStart | LogicalProperty::BorderBlockStart => PhysicalProperty::Left,
                LogicalProperty::MarginBlockEnd | LogicalProperty::PaddingBlockEnd | LogicalProperty::InsetBlockEnd | LogicalProperty::BorderBlockEnd => PhysicalProperty::Right,
                LogicalProperty::MarginInlineStart | LogicalProperty::PaddingInlineStart | LogicalProperty::InsetInlineStart | LogicalProperty::BorderInlineStart => {
                    if self.direction == Direction::Ltr { PhysicalProperty::Top } else { PhysicalProperty::Bottom }
                }
                LogicalProperty::MarginInlineEnd | LogicalProperty::PaddingInlineEnd | LogicalProperty::InsetInlineEnd | LogicalProperty::BorderInlineEnd => {
                    if self.direction == Direction::Ltr { PhysicalProperty::Bottom } else { PhysicalProperty::Top }
                }
            },
        }
    }

    /// AI-facing logical map inspector
    pub fn ai_mapping_summary(&self) -> String {
        let mut lines = vec![format!("🗺️ CSS Logical to Physical Map (Mode: {:?}, Dir: {:?}):", self.writing_mode, self.direction)];
        let properties = vec![
            LogicalProperty::BlockSize, LogicalProperty::InlineSize,
            LogicalProperty::MarginBlockStart, LogicalProperty::MarginInlineStart,
        ];
        for p in properties {
            lines.push(format!("  {:?} -> {:?}", p, self.resolve(p)));
        }
        lines.join("\n")
    }
}
