//! CSS Media Queries Level 4

use std::fmt;

/// Media type
#[derive(Debug, Clone, PartialEq)]
pub enum MediaType {
    All,
    Screen,
    Print,
    Speech,
}

impl MediaType {
    pub fn parse(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "screen" => Self::Screen,
            "print" => Self::Print,
            "speech" => Self::Speech,
            _ => Self::All,
        }
    }
}

/// A single media feature condition
#[derive(Debug, Clone, PartialEq)]
pub enum MediaFeature {
    // Viewport dimensions
    Width(f32),
    MinWidth(f32),
    MaxWidth(f32),
    Height(f32),
    MinHeight(f32),
    MaxHeight(f32),
    AspectRatio(f32, f32),
    MinAspectRatio(f32, f32),
    MaxAspectRatio(f32, f32),

    // Display quality
    Resolution(f32),  // dpi
    MinResolution(f32),
    MaxResolution(f32),
    Orientation(Orientation),
    Scan(Scan),
    Grid,
    Update(Update),
    OverflowBlock(OverflowBlock),
    OverflowInline(OverflowInline),

    // Color
    Color(u32),
    MinColor(u32),
    MaxColor(u32),
    ColorIndex(u32),
    Monochrome(u32),

    // Interaction
    PointerType(PointerType),
    AnyPointerType(PointerType),
    Hover(HoverType),
    AnyHover(HoverType),

    // User preferences
    PrefersColorScheme(ColorScheme),
    PrefersReducedMotion(ReducedMotion),
    PrefersReducedTransparency(ReducedTransparency),
    PrefersContrast(Contrast),
    ForcedColors(ForcedColors),
    InvertedColors(InvertedColors),
    DynamicRange(DynamicRange),

    // Environment
    DeviceWidth(f32),
    DeviceHeight(f32),
    DeviceAspectRatio(f32, f32),

    Unknown(String),
}

#[derive(Debug, Clone, PartialEq)] pub enum Orientation { Portrait, Landscape }
#[derive(Debug, Clone, PartialEq)] pub enum Scan { Interlace, Progressive }
#[derive(Debug, Clone, PartialEq)] pub enum Update { None, Slow, Fast }
#[derive(Debug, Clone, PartialEq)] pub enum OverflowBlock { None, Scroll, OptionalPaged, Paged }
#[derive(Debug, Clone, PartialEq)] pub enum OverflowInline { None, Scroll }
#[derive(Debug, Clone, PartialEq)] pub enum PointerType { None, Coarse, Fine }
#[derive(Debug, Clone, PartialEq)] pub enum HoverType { None, Hover }
#[derive(Debug, Clone, PartialEq)] pub enum ColorScheme { Light, Dark }
#[derive(Debug, Clone, PartialEq)] pub enum ReducedMotion { NoPreference, Reduce }
#[derive(Debug, Clone, PartialEq)] pub enum ReducedTransparency { NoPreference, Reduce }
#[derive(Debug, Clone, PartialEq)] pub enum Contrast { NoPreference, More, Less, Forced }
#[derive(Debug, Clone, PartialEq)] pub enum ForcedColors { None, Active }
#[derive(Debug, Clone, PartialEq)] pub enum InvertedColors { None, Inverted }
#[derive(Debug, Clone, PartialEq)] pub enum DynamicRange { Standard, High }

/// A media query condition node (can be negated, combined with and/or/not)
#[derive(Debug, Clone, PartialEq)]
pub enum MediaCondition {
    Feature(MediaFeature),
    Not(Box<MediaCondition>),
    And(Vec<MediaCondition>),
    Or(Vec<MediaCondition>),
    True,
    False,
}

/// A complete media query
#[derive(Debug, Clone, PartialEq)]
pub struct MediaQuery {
    pub negated: bool,
    pub media_type: MediaType,
    pub condition: Option<MediaCondition>,
}

impl MediaQuery {
    /// The 'all' media query — always matches
    pub fn all() -> Self {
        Self { negated: false, media_type: MediaType::All, condition: None }
    }

    /// Parse a media query string
    pub fn parse(s: &str) -> Self {
        let s = s.trim();
        if s.is_empty() || s == "all" {
            return Self::all();
        }

        let negated = s.starts_with("not ");
        let s = if negated { &s[4..] } else { s };

        // Simple: check for "only screen and ..."
        let s = if s.starts_with("only ") { &s[5..] } else { s };

        // Extract type and condition
        let (type_str, rest) = if let Some(pos) = s.find(" and ") {
            (&s[..pos], Some(&s[pos+5..]))
        } else if s.starts_with('(') {
            ("all", Some(s))
        } else {
            (s, None)
        };

        let media_type = MediaType::parse(type_str);
        let condition = rest.and_then(|c| parse_media_condition(c));

        Self { negated, media_type, condition }
    }

    /// Evaluate against a media context
    pub fn matches(&self, ctx: &MediaContext) -> bool {
        let type_matches = match &self.media_type {
            MediaType::All => true,
            MediaType::Screen => ctx.is_screen,
            MediaType::Print => ctx.is_print,
            MediaType::Speech => ctx.is_speech,
        };

        let condition_matches = self.condition.as_ref()
            .map(|c| c.evaluate(ctx))
            .unwrap_or(true);

        let result = type_matches && condition_matches;
        if self.negated { !result } else { result }
    }
}

/// Context for evaluating media queries
#[derive(Debug, Clone)]
pub struct MediaContext {
    pub width: f32,
    pub height: f32,
    pub device_width: f32,
    pub device_height: f32,
    pub resolution: f32,  // dpi
    pub is_screen: bool,
    pub is_print: bool,
    pub is_speech: bool,
    pub color_bits: u32,
    pub orientation: Orientation,
    pub pointer: PointerType,
    pub hover: HoverType,
    pub prefers_color_scheme: ColorScheme,
    pub prefers_reduced_motion: ReducedMotion,
    pub prefers_contrast: Contrast,
    pub forced_colors: ForcedColors,
}

impl Default for MediaContext {
    fn default() -> Self {
        Self {
            width: 1280.0,
            height: 800.0,
            device_width: 1280.0,
            device_height: 800.0,
            resolution: 96.0,
            is_screen: true,
            is_print: false,
            is_speech: false,
            color_bits: 8,
            orientation: Orientation::Landscape,
            pointer: PointerType::Fine,
            hover: HoverType::Hover,
            prefers_color_scheme: ColorScheme::Light,
            prefers_reduced_motion: ReducedMotion::NoPreference,
            prefers_contrast: Contrast::NoPreference,
            forced_colors: ForcedColors::None,
        }
    }
}

impl MediaCondition {
    pub fn evaluate(&self, ctx: &MediaContext) -> bool {
        match self {
            Self::True => true,
            Self::False => false,
            Self::Not(c) => !c.evaluate(ctx),
            Self::And(cs) => cs.iter().all(|c| c.evaluate(ctx)),
            Self::Or(cs) => cs.iter().any(|c| c.evaluate(ctx)),
            Self::Feature(f) => f.evaluate(ctx),
        }
    }
}

impl MediaFeature {
    pub fn evaluate(&self, ctx: &MediaContext) -> bool {
        match self {
            Self::Width(w) => ctx.width == *w,
            Self::MinWidth(w) => ctx.width >= *w,
            Self::MaxWidth(w) => ctx.width <= *w,
            Self::Height(h) => ctx.height == *h,
            Self::MinHeight(h) => ctx.height >= *h,
            Self::MaxHeight(h) => ctx.height <= *h,
            Self::Orientation(o) => ctx.orientation == *o,
            Self::Resolution(r) => ctx.resolution == *r,
            Self::MinResolution(r) => ctx.resolution >= *r,
            Self::MaxResolution(r) => ctx.resolution <= *r,
            Self::PrefersColorScheme(s) => ctx.prefers_color_scheme == *s,
            Self::PrefersReducedMotion(m) => ctx.prefers_reduced_motion == *m,
            Self::PrefersContrast(c) => ctx.prefers_contrast == *c,
            Self::ForcedColors(f) => ctx.forced_colors == *f,
            Self::PointerType(p) => ctx.pointer == *p,
            Self::Hover(h) => ctx.hover == *h,
            Self::Color(b) => ctx.color_bits == *b,
            Self::MinColor(b) => ctx.color_bits >= *b,
            Self::MaxColor(b) => ctx.color_bits <= *b,
            _ => true,
        }
    }
}

fn parse_media_condition(s: &str) -> Option<MediaCondition> {
    let s = s.trim();

    // Parenthesized feature
    if s.starts_with('(') && s.ends_with(')') {
        let inner = &s[1..s.len()-1];
        return parse_feature(inner).map(MediaCondition::Feature);
    }

    // And
    if s.contains(" and ") {
        let parts: Vec<&str> = s.split(" and ").collect();
        let conditions: Vec<MediaCondition> = parts.iter()
            .filter_map(|p| parse_media_condition(p))
            .collect();
        return Some(MediaCondition::And(conditions));
    }

    // Or
    if s.contains(" or ") {
        let parts: Vec<&str> = s.split(" or ").collect();
        let conditions: Vec<MediaCondition> = parts.iter()
            .filter_map(|p| parse_media_condition(p))
            .collect();
        return Some(MediaCondition::Or(conditions));
    }

    None
}

fn parse_feature(s: &str) -> Option<MediaFeature> {
    let s = s.trim();
    let colon = s.find(':')?;
    let name = s[..colon].trim().to_lowercase();
    let value = s[colon+1..].trim();

    let px = || -> f32 {
        value.trim_end_matches("px").trim().parse().unwrap_or(0.0)
    };

    Some(match name.as_str() {
        "width" => MediaFeature::Width(px()),
        "min-width" => MediaFeature::MinWidth(px()),
        "max-width" => MediaFeature::MaxWidth(px()),
        "height" => MediaFeature::Height(px()),
        "min-height" => MediaFeature::MinHeight(px()),
        "max-height" => MediaFeature::MaxHeight(px()),
        "orientation" => MediaFeature::Orientation(
            if value == "portrait" { Orientation::Portrait } else { Orientation::Landscape }
        ),
        "prefers-color-scheme" => MediaFeature::PrefersColorScheme(
            if value == "dark" { ColorScheme::Dark } else { ColorScheme::Light }
        ),
        "prefers-reduced-motion" => MediaFeature::PrefersReducedMotion(
            if value == "reduce" { ReducedMotion::Reduce } else { ReducedMotion::NoPreference }
        ),
        "prefers-contrast" => MediaFeature::PrefersContrast(match value {
            "more" => Contrast::More,
            "less" => Contrast::Less,
            "forced" => Contrast::Forced,
            _ => Contrast::NoPreference,
        }),
        "pointer" => MediaFeature::PointerType(match value {
            "none" => PointerType::None,
            "coarse" => PointerType::Coarse,
            _ => PointerType::Fine,
        }),
        "hover" => MediaFeature::Hover(
            if value == "none" { HoverType::None } else { HoverType::Hover }
        ),
        other => MediaFeature::Unknown(other.to_string()),
    })
}

/// A media query list (comma-separated)
#[derive(Debug, Clone)]
pub struct MediaQueryList {
    pub queries: Vec<MediaQuery>,
}

impl MediaQueryList {
    pub fn parse(s: &str) -> Self {
        let queries = s.split(',')
            .map(|q| MediaQuery::parse(q.trim()))
            .collect();
        Self { queries }
    }

    pub fn matches(&self, ctx: &MediaContext) -> bool {
        self.queries.iter().any(|q| q.matches(ctx))
    }

    pub fn all() -> Self {
        Self { queries: vec![MediaQuery::all()] }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_media_parse() {
        let q = MediaQuery::parse("screen and (max-width: 768px)");
        assert!(!q.negated);
        assert_eq!(q.media_type, MediaType::Screen);
    }

    #[test]
    fn test_media_matches() {
        let ctx = MediaContext::default();

        let q = MediaQuery::parse("(max-width: 1280px)");
        assert!(q.matches(&ctx));

        let q = MediaQuery::parse("(max-width: 640px)");
        assert!(!q.matches(&ctx));

        let q = MediaQuery::parse("(prefers-color-scheme: light)");
        assert!(q.matches(&ctx));

        let q = MediaQuery::parse("(prefers-color-scheme: dark)");
        assert!(!q.matches(&ctx));
    }
}
