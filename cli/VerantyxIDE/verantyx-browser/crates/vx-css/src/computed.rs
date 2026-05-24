//! Computed CSS Style — Resolved property values for an element

use std::collections::HashMap;
use crate::color::CssColor;
use crate::units::{Length, LengthPercentage, Percentage};
use crate::properties::{CssProperty, PropertyValue, Declaration};

/// Display value (CSS display property)
#[derive(Debug, Clone, PartialEq)]
pub enum Display {
    Inline,
    Block,
    InlineBlock,
    Flex,
    InlineFlex,
    Grid,
    InlineGrid,
    Table,
    InlineTable,
    TableRow,
    TableCell,
    TableRowGroup,
    TableHeaderGroup,
    TableFooterGroup,
    TableColumn,
    TableColumnGroup,
    TableCaption,
    ListItem,
    RunIn,
    FlowRoot,
    Contents,
    None,
    Other(String),
}

impl Display {
    pub fn parse(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "inline" => Self::Inline,
            "block" => Self::Block,
            "inline-block" => Self::InlineBlock,
            "flex" => Self::Flex,
            "inline-flex" => Self::InlineFlex,
            "grid" => Self::Grid,
            "inline-grid" => Self::InlineGrid,
            "table" => Self::Table,
            "inline-table" => Self::InlineTable,
            "table-row" => Self::TableRow,
            "table-cell" => Self::TableCell,
            "table-row-group" => Self::TableRowGroup,
            "table-header-group" => Self::TableHeaderGroup,
            "table-footer-group" => Self::TableFooterGroup,
            "table-column" => Self::TableColumn,
            "table-column-group" => Self::TableColumnGroup,
            "table-caption" => Self::TableCaption,
            "list-item" => Self::ListItem,
            "run-in" => Self::RunIn,
            "flow-root" => Self::FlowRoot,
            "contents" => Self::Contents,
            "none" => Self::None,
            other => Self::Other(other.to_string()),
        }
    }

    pub fn is_block_level(&self) -> bool {
        matches!(self,
            Self::Block | Self::Flex | Self::Grid | Self::Table | Self::ListItem |
            Self::FlowRoot | Self::TableRowGroup | Self::TableHeaderGroup |
            Self::TableFooterGroup | Self::TableRow | Self::TableColumn |
            Self::TableColumnGroup | Self::TableCaption
        )
    }

    pub fn is_flex_container(&self) -> bool {
        matches!(self, Self::Flex | Self::InlineFlex)
    }

    pub fn is_grid_container(&self) -> bool {
        matches!(self, Self::Grid | Self::InlineGrid)
    }
}

/// CSS position value
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Position {
    Static,
    Relative,
    Absolute,
    Fixed,
    Sticky,
}

impl Position {
    pub fn parse(s: &str) -> Self {
        match s {
            "relative" => Self::Relative,
            "absolute" => Self::Absolute,
            "fixed" => Self::Fixed,
            "sticky" => Self::Sticky,
            _ => Self::Static,
        }
    }

    pub fn is_positioned(&self) -> bool {
        !matches!(self, Self::Static)
    }

    pub fn creates_stacking_context(&self) -> bool {
        matches!(self, Self::Absolute | Self::Relative | Self::Fixed | Self::Sticky)
    }
}

/// CSS float value
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Float {
    None,
    Left,
    Right,
    InlineStart,
    InlineEnd,
}

impl Float {
    pub fn parse(s: &str) -> Self {
        match s {
            "left" => Self::Left,
            "right" => Self::Right,
            "inline-start" => Self::InlineStart,
            "inline-end" => Self::InlineEnd,
            _ => Self::None,
        }
    }
}

/// CSS overflow value
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Overflow {
    Visible,
    Hidden,
    Scroll,
    Auto,
    Clip,
}

impl Overflow {
    pub fn parse(s: &str) -> Self {
        match s {
            "hidden" => Self::Hidden,
            "scroll" => Self::Scroll,
            "auto" => Self::Auto,
            "clip" => Self::Clip,
            _ => Self::Visible,
        }
    }

    pub fn clips_content(&self) -> bool {
        matches!(self, Self::Hidden | Self::Scroll | Self::Auto | Self::Clip)
    }
}

/// CSS font-weight
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum FontWeight {
    Normal,    // 400
    Bold,      // 700
    Lighter,
    Bolder,
    Value(u16),
}

impl FontWeight {
    pub fn parse(s: &str) -> Self {
        match s {
            "normal" => Self::Normal,
            "bold" => Self::Bold,
            "lighter" => Self::Lighter,
            "bolder" => Self::Bolder,
            _ => s.parse::<u16>().map(Self::Value).unwrap_or(Self::Normal),
        }
    }

    pub fn to_number(&self) -> u16 {
        match self {
            Self::Normal => 400,
            Self::Bold => 700,
            Self::Lighter => 300,
            Self::Bolder => 700,
            Self::Value(n) => *n,
        }
    }

    pub fn is_bold(&self) -> bool {
        self.to_number() >= 700
    }
}

/// CSS font-style
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum FontStyle {
    Normal,
    Italic,
    Oblique(f32), // angle
}

/// CSS text-align
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum TextAlign {
    Left, Right, Center, Justify,
    Start, End,
    MatchParent,
    JustifyAll,
}

impl TextAlign {
    pub fn parse(s: &str) -> Self {
        match s {
            "right" => Self::Right,
            "center" => Self::Center,
            "justify" => Self::Justify,
            "start" => Self::Start,
            "end" => Self::End,
            _ => Self::Left,
        }
    }
}

/// CSS text-decoration-line flags
#[derive(Debug, Clone, PartialEq, Default)]
pub struct TextDecorationLine {
    pub underline: bool,
    pub overline: bool,
    pub line_through: bool,
    pub blink: bool,
}

impl TextDecorationLine {
    pub fn parse(s: &str) -> Self {
        let mut d = Self::default();
        for token in s.split_whitespace() {
            match token {
                "underline" => d.underline = true,
                "overline" => d.overline = true,
                "line-through" => d.line_through = true,
                "blink" => d.blink = true,
                _ => {}
            }
        }
        d
    }

    pub fn none() -> Self { Self::default() }
    pub fn has_any(&self) -> bool {
        self.underline || self.overline || self.line_through || self.blink
    }
}

/// CSS white-space value
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum WhiteSpace {
    Normal,
    Pre,
    NoWrap,
    PreWrap,
    BreakSpaces,
    PreLine,
}

impl WhiteSpace {
    pub fn parse(s: &str) -> Self {
        match s {
            "pre" => Self::Pre,
            "nowrap" => Self::NoWrap,
            "pre-wrap" => Self::PreWrap,
            "break-spaces" => Self::BreakSpaces,
            "pre-line" => Self::PreLine,
            _ => Self::Normal,
        }
    }

    pub fn preserves_whitespace(&self) -> bool {
        matches!(self, Self::Pre | Self::PreWrap | Self::BreakSpaces | Self::PreLine)
    }

    pub fn allows_wrapping(&self) -> bool {
        !matches!(self, Self::NoWrap | Self::Pre)
    }
}

/// CSS visibility
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Visibility {
    Visible,
    Hidden,
    Collapse,
}

impl Visibility {
    pub fn parse(s: &str) -> Self {
        match s {
            "hidden" => Self::Hidden,
            "collapse" => Self::Collapse,
            _ => Self::Visible,
        }
    }
}

/// An inset (top/right/bottom/left) with auto support
#[derive(Debug, Clone, PartialEq)]
pub enum SideValue {
    Auto,
    Length(LengthPercentage),
}

impl SideValue {
    pub fn auto() -> Self { Self::Auto }
    pub fn zero() -> Self { Self::Length(LengthPercentage::zero()) }
    pub fn parse(s: &str) -> Self {
        if s == "auto" { Self::Auto }
        else { LengthPercentage::parse(s).map(Self::Length).unwrap_or(Self::Auto) }
    }
}

/// Box shadow definition
#[derive(Debug, Clone, PartialEq)]
pub struct BoxShadow {
    pub offset_x: Length,
    pub offset_y: Length,
    pub blur: Length,
    pub spread: Length,
    pub color: CssColor,
    pub inset: bool,
}

/// CSS transform function
#[derive(Debug, Clone, PartialEq)]
pub enum TransformFunction {
    Translate(LengthPercentage, LengthPercentage),
    TranslateX(LengthPercentage),
    TranslateY(LengthPercentage),
    TranslateZ(Length),
    Translate3d(LengthPercentage, LengthPercentage, Length),
    Scale(f32, f32),
    ScaleX(f32), ScaleY(f32), ScaleZ(f32),
    Scale3d(f32, f32, f32),
    Rotate(f32),  // deg
    RotateX(f32), RotateY(f32), RotateZ(f32),
    Rotate3d(f32, f32, f32, f32),
    Skew(f32, f32),
    SkewX(f32), SkewY(f32),
    Perspective(Length),
    Matrix(f32, f32, f32, f32, f32, f32),
    Matrix3d([f32; 16]),
}

/// Flex-direction value
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum FlexDirection {
    Row, RowReverse, Column, ColumnReverse,
}

impl FlexDirection {
    pub fn parse(s: &str) -> Self {
        match s {
            "row-reverse" => Self::RowReverse,
            "column" => Self::Column,
            "column-reverse" => Self::ColumnReverse,
            _ => Self::Row,
        }
    }
    pub fn is_column(&self) -> bool {
        matches!(self, Self::Column | Self::ColumnReverse)
    }
}

/// Flex-wrap value
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum FlexWrap {
    NoWrap, Wrap, WrapReverse,
}

impl FlexWrap {
    pub fn parse(s: &str) -> Self {
        match s {
            "wrap" => Self::Wrap,
            "wrap-reverse" => Self::WrapReverse,
            _ => Self::NoWrap,
        }
    }
}

/// Justify-content / align-content
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum AlignContent {
    FlexStart, FlexEnd, Center, SpaceBetween, SpaceAround, SpaceEvenly,
    Start, End, Stretch, Baseline, Normal,
}

impl AlignContent {
    pub fn parse(s: &str) -> Self {
        match s {
            "flex-end" | "end" => Self::FlexEnd,
            "center" => Self::Center,
            "space-between" => Self::SpaceBetween,
            "space-around" => Self::SpaceAround,
            "space-evenly" => Self::SpaceEvenly,
            "start" => Self::Start,
            "stretch" => Self::Stretch,
            "baseline" => Self::Baseline,
            _ => Self::FlexStart,
        }
    }
}

/// AlignItems / AlignSelf
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum AlignItems {
    FlexStart, FlexEnd, Center, Baseline, Stretch, Normal, Auto,
    Start, End, SelfStart, SelfEnd,
    AnchorCenter,
}

impl AlignItems {
    pub fn parse(s: &str) -> Self {
        match s {
            "flex-end" | "end" => Self::FlexEnd,
            "center" => Self::Center,
            "baseline" => Self::Baseline,
            "stretch" => Self::Stretch,
            "auto" => Self::Auto,
            "start" => Self::Start,
            "self-start" => Self::SelfStart,
            "self-end" => Self::SelfEnd,
            _ => Self::FlexStart,
        }
    }
}

/// The fully computed style of an element
#[derive(Debug, Clone)]
pub struct ComputedStyle {
    // Color
    pub color: CssColor,
    pub background_color: CssColor,
    pub opacity: f32,

    // Box Model
    pub width: SideValue,
    pub min_width: SideValue,
    pub max_width: SideValue,
    pub height: SideValue,
    pub min_height: SideValue,
    pub max_height: SideValue,
    pub margin_top: SideValue,
    pub margin_right: SideValue,
    pub margin_bottom: SideValue,
    pub margin_left: SideValue,
    pub padding_top: LengthPercentage,
    pub padding_right: LengthPercentage,
    pub padding_bottom: LengthPercentage,
    pub padding_left: LengthPercentage,
    pub border_top_width: Length,
    pub border_right_width: Length,
    pub border_bottom_width: Length,
    pub border_left_width: Length,
    pub border_top_color: CssColor,
    pub border_right_color: CssColor,
    pub border_bottom_color: CssColor,
    pub border_left_color: CssColor,
    pub box_sizing: BoxSizing,

    // Layout
    pub display: Display,
    pub position: Position,
    pub float: Float,
    pub visibility: Visibility,
    pub overflow_x: Overflow,
    pub overflow_y: Overflow,
    pub z_index: ZIndex,
    pub top: SideValue,
    pub right: SideValue,
    pub bottom: SideValue,
    pub left: SideValue,

    // Flex
    pub flex_direction: FlexDirection,
    pub flex_wrap: FlexWrap,
    pub justify_content: AlignContent,
    pub align_items: AlignItems,
    pub align_content: AlignContent,
    pub align_self: AlignItems,
    pub flex_grow: f32,
    pub flex_shrink: f32,
    pub flex_basis: SideValue,
    pub order: i32,
    pub row_gap: LengthPercentage,
    pub column_gap: LengthPercentage,

    // Grid (simplified)
    pub grid_template_columns: String,
    pub grid_template_rows: String,
    pub grid_template_areas: String,
    pub grid_auto_flow: String,
    pub grid_column: String,
    pub grid_row: String,

    // Typography
    pub font_family: Vec<String>,
    pub font_size: f32,  // px
    pub font_weight: FontWeight,
    pub font_style: FontStyle,
    pub line_height: LineHeight,
    pub letter_spacing: LetterSpacing,
    pub word_spacing: WordSpacing,
    pub text_transform: TextTransform,
    pub text_decoration_line: TextDecorationLine,
    pub text_decoration_color: CssColor,
    pub text_align: TextAlign,
    pub text_indent: LengthPercentage,
    pub text_overflow: TextOverflow,
    pub white_space: WhiteSpace,
    pub word_break: WordBreak,
    pub overflow_wrap: OverflowWrap,
    pub vertical_align: VerticalAlign,
    pub direction: Direction,

    // Transforms
    pub transform: Vec<TransformFunction>,
    pub transform_origin: (LengthPercentage, LengthPercentage),

    // Misc
    pub cursor: String,
    pub pointer_events: PointerEvents,
    pub user_select: UserSelect,
    pub resize: Resize,
    pub box_shadow: Vec<BoxShadow>,
    pub outline_color: CssColor,
    pub outline_style: BorderStyle,
    pub outline_width: Length,
    pub outline_offset: Length,

    // Content
    pub content: ContentValue,

    // Custom properties
    pub custom: HashMap<String, String>,
}

// ── Supporting types ──

#[derive(Debug, Clone, Copy, PartialEq)] pub enum BoxSizing { ContentBox, BorderBox }
impl BoxSizing { pub fn parse(s: &str) -> Self { if s == "border-box" { Self::BorderBox } else { Self::ContentBox } } }

#[derive(Debug, Clone, PartialEq)]
pub enum ZIndex { Auto, Integer(i32) }
impl ZIndex { pub fn parse(s: &str) -> Self { if s == "auto" { Self::Auto } else { s.parse().map(Self::Integer).unwrap_or(Self::Auto) } } }

#[derive(Debug, Clone, PartialEq)]
pub enum LineHeight { Normal, Number(f32), Length(Length), Percentage(Percentage) }
impl LineHeight { pub fn parse(s: &str) -> Self { if s == "normal" { Self::Normal } else if let Some(l) = Length::parse(s) { Self::Length(l) } else if let Ok(n) = s.parse::<f32>() { Self::Number(n) } else { Self::Normal } } }

#[derive(Debug, Clone, PartialEq)]
pub enum LetterSpacing { Normal, Length(Length) }
impl LetterSpacing { pub fn parse(s: &str) -> Self { if s == "normal" { Self::Normal } else { Length::parse(s).map(Self::Length).unwrap_or(Self::Normal) } } }

#[derive(Debug, Clone, PartialEq)]
pub enum WordSpacing { Normal, Length(Length) }
impl WordSpacing { pub fn parse(s: &str) -> Self { if s == "normal" { Self::Normal } else { Length::parse(s).map(Self::Length).unwrap_or(Self::Normal) } } }

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum TextTransform { None, Uppercase, Lowercase, Capitalize, FullWidth, FullSizeKana }
impl TextTransform { pub fn parse(s: &str) -> Self { match s { "uppercase" => Self::Uppercase, "lowercase" => Self::Lowercase, "capitalize" => Self::Capitalize, _ => Self::None } } }

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum TextOverflow { Clip, Ellipsis }
impl TextOverflow { pub fn parse(s: &str) -> Self { if s == "ellipsis" { Self::Ellipsis } else { Self::Clip } } }

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum WordBreak { Normal, BreakAll, KeepAll, BreakWord, AutoPhrase }
impl WordBreak { pub fn parse(s: &str) -> Self { match s { "break-all" => Self::BreakAll, "keep-all" => Self::KeepAll, "break-word" => Self::BreakWord, _ => Self::Normal } } }

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum OverflowWrap { Normal, Anywhere, BreakWord }
impl OverflowWrap { pub fn parse(s: &str) -> Self { match s { "anywhere" => Self::Anywhere, "break-word" => Self::BreakWord, _ => Self::Normal } } }

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum VerticalAlign { Baseline, Sub, Super, TextTop, TextBottom, Middle, Top, Bottom, Length(i32) }
impl VerticalAlign { pub fn parse(s: &str) -> Self { match s { "sub" => Self::Sub, "super" => Self::Super, "text-top" => Self::TextTop, "text-bottom" => Self::TextBottom, "middle" => Self::Middle, "top" => Self::Top, "bottom" => Self::Bottom, _ => Self::Baseline } } }

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Direction { Ltr, Rtl }
impl Direction { pub fn parse(s: &str) -> Self { if s == "rtl" { Self::Rtl } else { Self::Ltr } } }

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum PointerEvents { Auto, None, All, Fill, Stroke, Painted, Visible, VisibleFill, VisibleStroke, VisiblePainted, BoundingBox }
impl PointerEvents { pub fn parse(s: &str) -> Self { match s { "none" => Self::None, "all" => Self::All, _ => Self::Auto } } }

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum UserSelect { Auto, None, Text, All, Contain }
impl UserSelect { pub fn parse(s: &str) -> Self { match s { "none" => Self::None, "text" => Self::Text, "all" => Self::All, _ => Self::Auto } } }

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Resize { None, Both, Horizontal, Vertical, Block, Inline }
impl Resize { pub fn parse(s: &str) -> Self { match s { "both" => Self::Both, "horizontal" => Self::Horizontal, "vertical" => Self::Vertical, _ => Self::None } } }

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum BorderStyle { None, Hidden, Solid, Dashed, Dotted, Double, Groove, Ridge, Inset, Outset }
impl BorderStyle { pub fn parse(s: &str) -> Self { match s { "solid" => Self::Solid, "dashed" => Self::Dashed, "dotted" => Self::Dotted, "double" => Self::Double, "groove" => Self::Groove, "ridge" => Self::Ridge, "inset" => Self::Inset, "outset" => Self::Outset, "hidden" => Self::Hidden, _ => Self::None } } }

#[derive(Debug, Clone, PartialEq)]
pub enum ContentValue { None, Normal, String(String), Url(String), Counters(String, String), OpenQuote, CloseQuote, Counter(String) }

impl ComputedStyle {
    /// Initial (browser default) values
    pub fn initial() -> Self {
        Self {
            color: CssColor::BLACK,
            background_color: CssColor::TRANSPARENT,
            opacity: 1.0,
            width: SideValue::Auto,
            min_width: SideValue::Length(LengthPercentage::zero()),
            max_width: SideValue::Auto,
            height: SideValue::Auto,
            min_height: SideValue::Length(LengthPercentage::zero()),
            max_height: SideValue::Auto,
            margin_top: SideValue::zero(),
            margin_right: SideValue::zero(),
            margin_bottom: SideValue::zero(),
            margin_left: SideValue::zero(),
            padding_top: LengthPercentage::zero(),
            padding_right: LengthPercentage::zero(),
            padding_bottom: LengthPercentage::zero(),
            padding_left: LengthPercentage::zero(),
            border_top_width: Length::zero(),
            border_right_width: Length::zero(),
            border_bottom_width: Length::zero(),
            border_left_width: Length::zero(),
            border_top_color: CssColor::BLACK,
            border_right_color: CssColor::BLACK,
            border_bottom_color: CssColor::BLACK,
            border_left_color: CssColor::BLACK,
            box_sizing: BoxSizing::ContentBox,
            display: Display::Block,
            position: Position::Static,
            float: Float::None,
            visibility: Visibility::Visible,
            overflow_x: Overflow::Visible,
            overflow_y: Overflow::Visible,
            z_index: ZIndex::Auto,
            top: SideValue::Auto,
            right: SideValue::Auto,
            bottom: SideValue::Auto,
            left: SideValue::Auto,
            flex_direction: FlexDirection::Row,
            flex_wrap: FlexWrap::NoWrap,
            justify_content: AlignContent::FlexStart,
            align_items: AlignItems::Stretch,
            align_content: AlignContent::Normal,
            align_self: AlignItems::Auto,
            flex_grow: 0.0,
            flex_shrink: 1.0,
            flex_basis: SideValue::Auto,
            order: 0,
            row_gap: LengthPercentage::zero(),
            column_gap: LengthPercentage::zero(),
            grid_template_columns: "none".to_string(),
            grid_template_rows: "none".to_string(),
            grid_template_areas: "none".to_string(),
            grid_auto_flow: "row".to_string(),
            grid_column: "auto".to_string(),
            grid_row: "auto".to_string(),
            font_family: vec!["serif".to_string()],
            font_size: 16.0,
            font_weight: FontWeight::Normal,
            font_style: FontStyle::Normal,
            line_height: LineHeight::Normal,
            letter_spacing: LetterSpacing::Normal,
            word_spacing: WordSpacing::Normal,
            text_transform: TextTransform::None,
            text_decoration_line: TextDecorationLine::none(),
            text_decoration_color: CssColor::BLACK,
            text_align: TextAlign::Left,
            text_indent: LengthPercentage::zero(),
            text_overflow: TextOverflow::Clip,
            white_space: WhiteSpace::Normal,
            word_break: WordBreak::Normal,
            overflow_wrap: OverflowWrap::Normal,
            vertical_align: VerticalAlign::Baseline,
            direction: Direction::Ltr,
            transform: Vec::new(),
            transform_origin: (
                LengthPercentage::Percentage(Percentage(50.0)),
                LengthPercentage::Percentage(Percentage(50.0)),
            ),
            cursor: "auto".to_string(),
            pointer_events: PointerEvents::Auto,
            user_select: UserSelect::Auto,
            resize: Resize::None,
            box_shadow: Vec::new(),
            outline_color: CssColor::BLACK,
            outline_style: BorderStyle::None,
            outline_width: Length::px(3.0),
            outline_offset: Length::zero(),
            content: ContentValue::Normal,
            custom: HashMap::new(),
        }
    }

    /// Inherit values from parent style
    pub fn inherit_from(&mut self, parent: &ComputedStyle) {
        self.color = parent.color.clone();
        self.font_family = parent.font_family.clone();
        self.font_size = parent.font_size;
        self.font_weight = parent.font_weight;
        self.font_style = parent.font_style;
        self.line_height = parent.line_height.clone();
        self.letter_spacing = parent.letter_spacing.clone();
        self.word_spacing = parent.word_spacing.clone();
        self.text_transform = parent.text_transform;
        self.text_decoration_line = parent.text_decoration_line.clone();
        self.text_decoration_color = parent.text_decoration_color.clone();
        self.text_align = parent.text_align;
        self.text_indent = parent.text_indent.clone();
        self.text_overflow = parent.text_overflow;
        self.white_space = parent.white_space;
        self.word_break = parent.word_break;
        self.overflow_wrap = parent.overflow_wrap;
        self.vertical_align = parent.vertical_align;
        self.direction = parent.direction;
        self.visibility = parent.visibility;
        self.cursor = parent.cursor.clone();
        self.pointer_events = parent.pointer_events;
        // Inherit custom properties
        for (k, v) in &parent.custom {
            self.custom.entry(k.clone()).or_insert_with(|| v.clone());
        }
    }

    /// Apply a single declaration to this computed style
    pub fn apply_declaration(&mut self, decl: &Declaration) {
        use crate::properties::CssProperty;
        let prop = CssProperty::parse(&decl.property);
        let val = &decl.value;

        match prop {
            CssProperty::Color => {
                if let Some(c) = val.as_color() { self.color = c.clone(); }
            }
            CssProperty::BackgroundColor => {
                if let Some(c) = val.as_color() { self.background_color = c.clone(); }
                else if val.is_keyword("transparent") { self.background_color = CssColor::TRANSPARENT; }
            }
            CssProperty::Opacity => {
                if let PropertyValue::Number(n) = val { self.opacity = n.clamp(0.0, 1.0); }
            }
            CssProperty::Display => {
                if let PropertyValue::Keyword(k) = val { self.display = Display::parse(k); }
                else if matches!(val, PropertyValue::None) { self.display = Display::None; }
            }
            CssProperty::Position => {
                if let PropertyValue::Keyword(k) = val { self.position = Position::parse(k); }
            }
            CssProperty::Float => {
                if let PropertyValue::Keyword(k) = val { self.float = Float::parse(k); }
                else if matches!(val, PropertyValue::None) { self.float = Float::None; }
            }
            CssProperty::Visibility => {
                if let PropertyValue::Keyword(k) = val { self.visibility = Visibility::parse(k); }
            }
            CssProperty::Overflow => {
                if let PropertyValue::Keyword(k) = val {
                    let ov = Overflow::parse(k);
                    self.overflow_x = ov;
                    self.overflow_y = ov;
                }
            }
            CssProperty::OverflowX => {
                if let PropertyValue::Keyword(k) = val { self.overflow_x = Overflow::parse(k); }
            }
            CssProperty::OverflowY => {
                if let PropertyValue::Keyword(k) = val { self.overflow_y = Overflow::parse(k); }
            }
            CssProperty::FontSize => {
                // Named sizes
                if let PropertyValue::Keyword(k) = val {
                    self.font_size = named_font_size(k);
                } else if let Some(px) = val.as_length_px(self.font_size) {
                    self.font_size = px;
                } else if let PropertyValue::Percentage(p) = val {
                    self.font_size *= p.0 / 100.0;
                }
            }
            CssProperty::FontWeight => {
                if let PropertyValue::Keyword(k) = val { self.font_weight = FontWeight::parse(k); }
                else if let PropertyValue::Number(n) = val { self.font_weight = FontWeight::Value(*n as u16); }
            }
            CssProperty::FontStyle => {
                if let PropertyValue::Keyword(k) = val {
                    self.font_style = match k.as_str() {
                        "italic" => FontStyle::Italic,
                        "oblique" => FontStyle::Oblique(14.0),
                        _ => FontStyle::Normal,
                    };
                }
            }
            CssProperty::LineHeight => {
                if let PropertyValue::Keyword(k) = val { self.line_height = LineHeight::parse(k); }
                else if let PropertyValue::Number(n) = val { self.line_height = LineHeight::Number(*n); }
                else if let PropertyValue::Length(l) = val { self.line_height = LineHeight::Length(l.clone()); }
            }
            CssProperty::TextAlign => {
                if let PropertyValue::Keyword(k) = val { self.text_align = TextAlign::parse(k); }
            }
            CssProperty::TextTransform => {
                if let PropertyValue::Keyword(k) = val { self.text_transform = TextTransform::parse(k); }
            }
            CssProperty::WhiteSpace => {
                if let PropertyValue::Keyword(k) = val { self.white_space = WhiteSpace::parse(k); }
            }
            CssProperty::WordBreak => {
                if let PropertyValue::Keyword(k) = val { self.word_break = WordBreak::parse(k); }
            }
            CssProperty::Cursor => {
                if let PropertyValue::Keyword(k) = val { self.cursor = k.clone(); }
            }
            CssProperty::PointerEvents => {
                if let PropertyValue::Keyword(k) = val { self.pointer_events = PointerEvents::parse(k); }
                else if matches!(val, PropertyValue::None) { self.pointer_events = PointerEvents::None; }
            }
            CssProperty::UserSelect => {
                if let PropertyValue::Keyword(k) = val { self.user_select = UserSelect::parse(k); }
            }
            CssProperty::ZIndex => {
                if let PropertyValue::Keyword(k) = val { self.z_index = ZIndex::parse(k); }
                else if let PropertyValue::Integer(n) = val { self.z_index = ZIndex::Integer(*n); }
                else if let PropertyValue::Number(n) = val { self.z_index = ZIndex::Integer(*n as i32); }
            }
            CssProperty::FlexDirection => {
                if let PropertyValue::Keyword(k) = val { self.flex_direction = FlexDirection::parse(k); }
            }
            CssProperty::FlexWrap => {
                if let PropertyValue::Keyword(k) = val { self.flex_wrap = FlexWrap::parse(k); }
            }
            CssProperty::JustifyContent => {
                if let PropertyValue::Keyword(k) = val { self.justify_content = AlignContent::parse(k); }
            }
            CssProperty::AlignItems => {
                if let PropertyValue::Keyword(k) = val { self.align_items = AlignItems::parse(k); }
            }
            CssProperty::FlexGrow => {
                if let PropertyValue::Number(n) = val { self.flex_grow = *n; }
            }
            CssProperty::FlexShrink => {
                if let PropertyValue::Number(n) = val { self.flex_shrink = *n; }
            }
            CssProperty::Order => {
                if let PropertyValue::Integer(n) = val { self.order = *n; }
                else if let PropertyValue::Number(n) = val { self.order = *n as i32; }
            }
            CssProperty::BoxSizing => {
                if let PropertyValue::Keyword(k) = val { self.box_sizing = BoxSizing::parse(k); }
            }
            CssProperty::Custom(name) => {
                self.custom.insert(name, val.to_string());
            }
            _ => {} // Other properties handled elsewhere
        }
    }
}

fn named_font_size(name: &str) -> f32 {
    match name {
        "xx-small" => 9.0,
        "x-small" => 10.0,
        "small" => 13.0,
        "medium" => 16.0,
        "large" => 18.0,
        "x-large" => 24.0,
        "xx-large" => 32.0,
        "xxx-large" => 48.0,
        "smaller" => 13.0,
        "larger" => 19.0,
        _ => 16.0,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_initial_style() {
        let style = ComputedStyle::initial();
        assert_eq!(style.opacity, 1.0);
        assert_eq!(style.font_size, 16.0);
        assert!(matches!(style.display, Display::Block));
    }

    #[test]
    fn test_display_parse() {
        assert!(Display::parse("flex").is_flex_container());
        assert!(Display::parse("grid").is_grid_container());
        assert!(Display::parse("block").is_block_level());
        assert!(!Display::parse("flex").is_block_level());
    }

    #[test]
    fn test_font_weight() {
        assert!(FontWeight::Bold.is_bold());
        assert!(!FontWeight::Normal.is_bold());
        assert!(FontWeight::Value(800).is_bold());
        assert!(!FontWeight::Value(400).is_bold());
    }

    #[test]
    fn test_inherit_color() {
        let mut parent = ComputedStyle::initial();
        parent.color = CssColor::from_hex("#ff0000").unwrap();

        let mut child = ComputedStyle::initial();
        child.inherit_from(&parent);

        assert_eq!(child.color, parent.color);
    }

    #[test]
    fn test_apply_declaration() {
        let mut style = ComputedStyle::initial();
        let decl = Declaration {
            property: "display".to_string(),
            value: PropertyValue::Keyword("flex".to_string()),
            important: false,
        };
        style.apply_declaration(&decl);
        assert!(style.display.is_flex_container());
    }
}
