//! CSS Properties — Complete set of all CSS properties with types

use std::fmt;
use crate::color::CssColor;
use crate::units::{Length, LengthPercentage, Percentage, CssValue};

/// A single CSS declaration
#[derive(Debug, Clone)]
pub struct Declaration {
    pub property: String,
    pub value: PropertyValue,
    pub important: bool,
}

/// A CSS property value (parsed)
#[derive(Debug, Clone, PartialEq)]
pub enum PropertyValue {
    // Global keywords
    Initial,
    Inherit,
    Unset,
    Revert,
    RevertLayer,
    // Typed value
    Color(CssColor),
    Length(Length),
    LengthPercentage(LengthPercentage),
    Percentage(Percentage),
    Number(f32),
    Integer(i32),
    Keyword(String),
    String(String),
    None,
    Auto,
    // Multi-value
    List(Vec<PropertyValue>),
    // Unresolved raw string (var(), calc() etc.)
    Raw(String),
}

impl PropertyValue {
    pub fn parse(s: &str) -> Self {
        let s = s.trim();
        match s {
            "initial" => Self::Initial,
            "inherit" => Self::Inherit,
            "unset" => Self::Unset,
            "revert" => Self::Revert,
            "revert-layer" => Self::RevertLayer,
            "none" => Self::None,
            "auto" => Self::Auto,
            _ => {
                if let Some(c) = CssColor::parse(s) {
                    return Self::Color(c);
                }
                if let Some(l) = Length::parse(s) {
                    return Self::Length(l);
                }
                if let Some(p) = Percentage::parse(s) {
                    return Self::Percentage(p);
                }
                if let Ok(n) = s.parse::<f32>() {
                    return Self::Number(n);
                }
                Self::Keyword(s.to_string())
            }
        }
    }

    pub fn as_color(&self) -> Option<&CssColor> {
        match self { Self::Color(c) => Some(c), _ => None }
    }

    pub fn as_length_px(&self, font_size: f32) -> Option<f32> {
        match self {
            Self::Length(l) => {
                use crate::units::{LengthUnit, FontContext, Viewport};
                let font = FontContext { font_size, ..Default::default() };
                Some(l.to_px(&font, &Viewport::default()))
            }
            _ => None,
        }
    }

    pub fn is_keyword(&self, kw: &str) -> bool {
        matches!(self, Self::Keyword(k) if k.eq_ignore_ascii_case(kw))
    }
}

impl fmt::Display for PropertyValue {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Initial => write!(f, "initial"),
            Self::Inherit => write!(f, "inherit"),
            Self::Unset => write!(f, "unset"),
            Self::None => write!(f, "none"),
            Self::Auto => write!(f, "auto"),
            Self::Color(c) => write!(f, "{}", c),
            Self::Length(l) => write!(f, "{}", l),
            Self::Number(n) => write!(f, "{}", n),
            Self::Keyword(k) => write!(f, "{}", k),
            _ => write!(f, "<value>"),
        }
    }
}

/// All known CSS properties
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum CssProperty {
    // Color & Background
    Color,
    BackgroundColor,
    BackgroundImage,
    BackgroundPosition,
    BackgroundSize,
    BackgroundRepeat,
    BackgroundAttachment,
    BackgroundClip,
    BackgroundOrigin,
    Background,
    Opacity,

    // Box Model
    Width, MinWidth, MaxWidth,
    Height, MinHeight, MaxHeight,
    Margin, MarginTop, MarginRight, MarginBottom, MarginLeft,
    MarginBlock, MarginBlockStart, MarginBlockEnd,
    MarginInline, MarginInlineStart, MarginInlineEnd,
    Padding, PaddingTop, PaddingRight, PaddingBottom, PaddingLeft,
    PaddingBlock, PaddingBlockStart, PaddingBlockEnd,
    PaddingInline, PaddingInlineStart, PaddingInlineEnd,
    Border, BorderTop, BorderRight, BorderBottom, BorderLeft,
    BorderWidth, BorderTopWidth, BorderRightWidth, BorderBottomWidth, BorderLeftWidth,
    BorderStyle, BorderTopStyle, BorderRightStyle, BorderBottomStyle, BorderLeftStyle,
    BorderColor, BorderTopColor, BorderRightColor, BorderBottomColor, BorderLeftColor,
    BorderRadius, BorderTopLeftRadius, BorderTopRightRadius, BorderBottomLeftRadius, BorderBottomRightRadius,
    BorderImage, BorderImageSource, BorderImageSlice, BorderImageWidth, BorderImageOutset, BorderImageRepeat,
    BoxSizing,
    BoxShadow,
    Outline, OutlineColor, OutlineStyle, OutlineWidth, OutlineOffset,

    // Display & Layout
    Display,
    Visibility,
    Overflow, OverflowX, OverflowY,
    OverscrollBehavior, OverscrollBehaviorX, OverscrollBehaviorY,
    Position,
    Top, Right, Bottom, Left,
    InsetBlock, InsetBlockStart, InsetBlockEnd,
    InsetInline, InsetInlineStart, InsetInlineEnd,
    Inset,
    ZIndex,
    Float,
    Clear,
    Clip, ClipPath,
    Transform, TransformOrigin, TransformBox, TransformStyle,
    Perspective, PerspectiveOrigin,
    BackfaceVisibility,
    WillChange,

    // Flexbox
    FlexDirection,
    FlexWrap,
    FlexFlow,
    JustifyContent,
    AlignItems,
    AlignContent,
    AlignSelf,
    JustifySelf,
    JustifyItems,
    Order,
    Flex, FlexGrow, FlexShrink, FlexBasis,
    Gap, RowGap, ColumnGap,
    PlaceContent, PlaceItems, PlaceSelf,

    // Grid
    GridTemplateColumns,
    GridTemplateRows,
    GridTemplateAreas,
    GridTemplate,
    GridAutoColumns,
    GridAutoRows,
    GridAutoFlow,
    Grid,
    GridColumn, GridColumnStart, GridColumnEnd,
    GridRow, GridRowStart, GridRowEnd,
    GridArea,

    // Typography
    FontFamily,
    FontSize,
    FontWeight,
    FontStyle,
    FontVariant, FontVariantCaps, FontVariantNumeric, FontVariantLigatures,
    FontStretch,
    FontKerning,
    FontOpticalSizing,
    FontSizeAdjust,
    Font,
    LineHeight,
    LetterSpacing,
    WordSpacing,
    TextTransform,
    TextDecoration, TextDecorationLine, TextDecorationStyle, TextDecorationColor, TextDecorationThickness,
    TextUnderlineOffset,
    TextAlign, TextAlignLast,
    TextIndent,
    TextOverflow,
    TextShadow,
    TextWrap, TextWrapMode, TextWrapStyle,
    WhiteSpace, WhiteSpaceCollapse,
    WordBreak,
    OverflowWrap, WordWrap,
    Hyphens,
    VerticalAlign,
    LineClamp,
    WebkitLineClamp,
    Direction,
    WritingMode,
    TextOrientation,

    // Lists
    ListStyle, ListStyleType, ListStyleImage, ListStylePosition,
    CounterReset, CounterSet, CounterIncrement,

    // Tables
    BorderCollapse, BorderSpacing, CaptionSide,
    EmptyCells, TableLayout,

    // Columns
    Columns, ColumnCount, ColumnWidth, ColumnGapProp,
    ColumnRule, ColumnRuleColor, ColumnRuleStyle, ColumnRuleWidth,
    ColumnFill, ColumnSpan,

    // Scroll
    ScrollBehavior,
    ScrollbarWidth, ScrollbarColor,
    ScrollSnap,
    ScrollSnapType, ScrollSnapAlign, ScrollSnapStop,
    ScrollMargin, ScrollMarginTop, ScrollMarginRight, ScrollMarginBottom, ScrollMarginLeft,
    ScrollPadding, ScrollPaddingTop, ScrollPaddingRight, ScrollPaddingBottom, ScrollPaddingLeft,

    // Animation & Transition
    Animation, AnimationName, AnimationDuration, AnimationTimingFunction,
    AnimationDelay, AnimationIterationCount, AnimationDirection,
    AnimationFillMode, AnimationPlayState, AnimationComposition,
    Transition, TransitionProperty, TransitionDuration, TransitionTimingFunction, TransitionDelay,
    Offset, OffsetPath, OffsetDistance, OffsetRotate, OffsetAnchor,

    // Appearance & UI
    Appearance, WebkitAppearance,
    Cursor,
    PointerEvents,
    UserSelect, WebkitUserSelect,
    Resize,
    Caret, CaretColor,
    AccentColor,
    ColorScheme,
    ForcedColorAdjust,

    // SVG
    Fill, FillOpacity, FillRule,
    Stroke, StrokeWidth, StrokeOpacity,
    StrokeDasharray, StrokeDashoffset,
    StrokeLinecap, StrokeLinejoin, StrokeMiterlimit,
    Marker, MarkerStart, MarkerMid, MarkerEnd,
    StopColor, StopOpacity,
    FloodColor, FloodOpacity,
    LightingColor,
    VectorEffect,
    ShapeRendering, TextRendering, ImageRendering, ColorRendering,
    ColorInterpolation, ColorInterpolationFilters,

    // Filters & Effects
    Filter, BackdropFilter,
    MixBlendMode,
    IsolationProp,

    // Masking & Shapes
    Mask, MaskImage, MaskSize, MaskPosition, MaskRepeat, MaskOrigin, MaskClip, MaskComposite, MaskMode,
    MaskBorder, MaskBorderSource, MaskBorderSlice, MaskBorderWidth, MaskBorderOutset, MaskBorderRepeat, MaskBorderMode,
    ShapeOutside, ShapeMargin, ShapeImageThreshold,

    // Content
    Content,
    Quotes,

    // Generated content & Printing
    PageBreakBefore, PageBreakAfter, PageBreakInside,
    BreakBefore, BreakAfter, BreakInside,
    Orphans, Widows,
    Page,

    // Variables / Custom Props
    Custom(String),

    /// Unknown/arbitrary property
    Unknown(String),
}

impl CssProperty {
    pub fn parse(s: &str) -> Self {
        if s.starts_with("--") {
            return Self::Custom(s.to_string());
        }
        match s.to_lowercase().as_str() {
            "color" => Self::Color,
            "background-color" => Self::BackgroundColor,
            "background-image" => Self::BackgroundImage,
            "background-position" => Self::BackgroundPosition,
            "background-size" => Self::BackgroundSize,
            "background-repeat" => Self::BackgroundRepeat,
            "background-attachment" => Self::BackgroundAttachment,
            "background-clip" => Self::BackgroundClip,
            "background-origin" => Self::BackgroundOrigin,
            "background" => Self::Background,
            "opacity" => Self::Opacity,
            "width" => Self::Width,
            "min-width" => Self::MinWidth,
            "max-width" => Self::MaxWidth,
            "height" => Self::Height,
            "min-height" => Self::MinHeight,
            "max-height" => Self::MaxHeight,
            "margin" => Self::Margin,
            "margin-top" => Self::MarginTop,
            "margin-right" => Self::MarginRight,
            "margin-bottom" => Self::MarginBottom,
            "margin-left" => Self::MarginLeft,
            "padding" => Self::Padding,
            "padding-top" => Self::PaddingTop,
            "padding-right" => Self::PaddingRight,
            "padding-bottom" => Self::PaddingBottom,
            "padding-left" => Self::PaddingLeft,
            "border" => Self::Border,
            "border-radius" => Self::BorderRadius,
            "border-top-left-radius" => Self::BorderTopLeftRadius,
            "border-top-right-radius" => Self::BorderTopRightRadius,
            "border-bottom-left-radius" => Self::BorderBottomLeftRadius,
            "border-bottom-right-radius" => Self::BorderBottomRightRadius,
            "box-sizing" => Self::BoxSizing,
            "box-shadow" => Self::BoxShadow,
            "outline" => Self::Outline,
            "display" => Self::Display,
            "visibility" => Self::Visibility,
            "overflow" => Self::Overflow,
            "overflow-x" => Self::OverflowX,
            "overflow-y" => Self::OverflowY,
            "position" => Self::Position,
            "top" => Self::Top,
            "right" => Self::Right,
            "bottom" => Self::Bottom,
            "left" => Self::Left,
            "z-index" => Self::ZIndex,
            "float" => Self::Float,
            "clear" => Self::Clear,
            "transform" => Self::Transform,
            "transform-origin" => Self::TransformOrigin,
            "will-change" => Self::WillChange,
            "flex" => Self::Flex,
            "flex-direction" => Self::FlexDirection,
            "flex-wrap" => Self::FlexWrap,
            "flex-flow" => Self::FlexFlow,
            "flex-grow" => Self::FlexGrow,
            "flex-shrink" => Self::FlexShrink,
            "flex-basis" => Self::FlexBasis,
            "justify-content" => Self::JustifyContent,
            "align-items" => Self::AlignItems,
            "align-content" => Self::AlignContent,
            "align-self" => Self::AlignSelf,
            "justify-self" => Self::JustifySelf,
            "justify-items" => Self::JustifyItems,
            "order" => Self::Order,
            "gap" => Self::Gap,
            "row-gap" => Self::RowGap,
            "column-gap" => Self::ColumnGap,
            "grid-template-columns" => Self::GridTemplateColumns,
            "grid-template-rows" => Self::GridTemplateRows,
            "grid-template-areas" => Self::GridTemplateAreas,
            "grid-auto-columns" => Self::GridAutoColumns,
            "grid-auto-rows" => Self::GridAutoRows,
            "grid-auto-flow" => Self::GridAutoFlow,
            "grid-column" => Self::GridColumn,
            "grid-column-start" => Self::GridColumnStart,
            "grid-column-end" => Self::GridColumnEnd,
            "grid-row" => Self::GridRow,
            "grid-row-start" => Self::GridRowStart,
            "grid-row-end" => Self::GridRowEnd,
            "grid-area" => Self::GridArea,
            "font-family" => Self::FontFamily,
            "font-size" => Self::FontSize,
            "font-weight" => Self::FontWeight,
            "font-style" => Self::FontStyle,
            "font-variant" => Self::FontVariant,
            "font-stretch" => Self::FontStretch,
            "font" => Self::Font,
            "line-height" => Self::LineHeight,
            "letter-spacing" => Self::LetterSpacing,
            "word-spacing" => Self::WordSpacing,
            "text-transform" => Self::TextTransform,
            "text-decoration" => Self::TextDecoration,
            "text-decoration-line" => Self::TextDecorationLine,
            "text-decoration-style" => Self::TextDecorationStyle,
            "text-decoration-color" => Self::TextDecorationColor,
            "text-align" => Self::TextAlign,
            "text-align-last" => Self::TextAlignLast,
            "text-indent" => Self::TextIndent,
            "text-overflow" => Self::TextOverflow,
            "text-shadow" => Self::TextShadow,
            "white-space" => Self::WhiteSpace,
            "word-break" => Self::WordBreak,
            "overflow-wrap" | "word-wrap" => Self::OverflowWrap,
            "hyphens" => Self::Hyphens,
            "vertical-align" => Self::VerticalAlign,
            "direction" => Self::Direction,
            "writing-mode" => Self::WritingMode,
            "list-style" => Self::ListStyle,
            "list-style-type" => Self::ListStyleType,
            "border-collapse" => Self::BorderCollapse,
            "table-layout" => Self::TableLayout,
            "cursor" => Self::Cursor,
            "pointer-events" => Self::PointerEvents,
            "user-select" | "-webkit-user-select" => Self::UserSelect,
            "resize" => Self::Resize,
            "content" => Self::Content,
            "filter" => Self::Filter,
            "backdrop-filter" => Self::BackdropFilter,
            "mix-blend-mode" => Self::MixBlendMode,
            "animation" => Self::Animation,
            "animation-name" => Self::AnimationName,
            "animation-duration" => Self::AnimationDuration,
            "animation-timing-function" => Self::AnimationTimingFunction,
            "animation-delay" => Self::AnimationDelay,
            "animation-iteration-count" => Self::AnimationIterationCount,
            "animation-direction" => Self::AnimationDirection,
            "animation-fill-mode" => Self::AnimationFillMode,
            "animation-play-state" => Self::AnimationPlayState,
            "transition" => Self::Transition,
            "transition-property" => Self::TransitionProperty,
            "transition-duration" => Self::TransitionDuration,
            "transition-timing-function" => Self::TransitionTimingFunction,
            "transition-delay" => Self::TransitionDelay,
            "fill" => Self::Fill,
            "stroke" => Self::Stroke,
            "stroke-width" => Self::StrokeWidth,
            "clip-path" => Self::ClipPath,
            "mask" => Self::Mask,
            "shape-outside" => Self::ShapeOutside,
            "scroll-behavior" => Self::ScrollBehavior,
            "accent-color" => Self::AccentColor,
            "color-scheme" => Self::ColorScheme,
            "appearance" | "-webkit-appearance" => Self::Appearance,
            other => Self::Unknown(other.to_string()),
        }
    }

    /// Is this property inherited by default?
    pub fn is_inherited(&self) -> bool {
        matches!(self,
            Self::Color | Self::FontFamily | Self::FontSize | Self::FontWeight |
            Self::FontStyle | Self::FontVariant | Self::FontStretch | Self::Font |
            Self::LineHeight | Self::LetterSpacing | Self::WordSpacing |
            Self::TextTransform | Self::TextDecoration | Self::TextAlign |
            Self::TextIndent | Self::TextShadow | Self::WhiteSpace |
            Self::WordBreak | Self::OverflowWrap | Self::Hyphens |
            Self::Direction | Self::WritingMode | Self::TextOrientation |
            Self::ListStyle | Self::ListStyleType | Self::ListStylePosition |
            Self::Visibility | Self::Cursor | Self::PointerEvents |
            Self::Fill | Self::FillOpacity | Self::Stroke | Self::StrokeWidth |
            Self::Quotes | Self::Orphans | Self::Widows |
            Self::BorderCollapse | Self::BorderSpacing | Self::CaptionSide |
            Self::EmptyCells | Self::TableLayout |
            Self::Custom(_)
        )
    }

    pub fn name(&self) -> String {
        match self {
            Self::Custom(n) => n.clone(),
            Self::Unknown(n) => n.clone(),
            other => format!("{:?}", other).to_lowercase().replace('_', "-"),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_property_parse() {
        assert_eq!(CssProperty::parse("color"), CssProperty::Color);
        assert_eq!(CssProperty::parse("font-size"), CssProperty::FontSize);
        assert_eq!(CssProperty::parse("background-color"), CssProperty::BackgroundColor);
    }

    #[test]
    fn test_inheritance() {
        assert!(CssProperty::Color.is_inherited());
        assert!(!CssProperty::Width.is_inherited());
        assert!(CssProperty::FontSize.is_inherited());
        assert!(!CssProperty::BackgroundColor.is_inherited());
    }

    #[test]
    fn test_value_parse() {
        let v = PropertyValue::parse("red");
        assert!(matches!(v, PropertyValue::Color(_)));

        let v = PropertyValue::parse("16px");
        assert!(matches!(v, PropertyValue::Length(_)));

        let v = PropertyValue::parse("none");
        assert_eq!(v, PropertyValue::None);

        let v = PropertyValue::parse("auto");
        assert_eq!(v, PropertyValue::Auto);
    }
}
