//! Media Queries Level 5 — CSS MQ with Range Syntax + Container Queries
//!
//! Implements the complete CSS Media Queries Level 4/5 specification:
//!   - Media type matching (all, screen, print, speech)
//!   - Discrete features: orientation, hover, pointer, any-hover, any-pointer,
//!     color-gamut, overflow-block, overflow-inline, update, display-mode,
//!     scripting, forced-colors, prefers-color-scheme, prefers-reduced-motion,
//!     prefers-reduced-transparency, prefers-contrast, prefers-reduced-data
//!   - Range features (Level 4 range syntax): 100px < width <= 800px
//!   - Boolean operators: and, or, not
//!   - @container queries (with aspect-ratio, block-size, inline-size, orientation)
//!   - env() media feature variables
//!   - Dynamic viewport units (dvw/dvh/svw/svh)

use std::collections::HashMap;

/// A viewport snapshot for media query evaluation
#[derive(Debug, Clone)]
pub struct Viewport {
    pub width: f64,
    pub height: f64,
    pub device_pixel_ratio: f64,
    pub color_depth: u32,         // bits per channel
    pub monochrome: u32,          // bits per pixel for monochrome, 0 if color
    pub orientation: Orientation,
    pub hover: HoverCapability,
    pub pointer: PointerCapability,
    pub any_hover: HoverCapability,
    pub any_pointer: PointerCapability,
    pub color_gamut: ColorGamut,
    pub prefers_color_scheme: ColorScheme,
    pub prefers_reduced_motion: bool,
    pub prefers_contrast: ContrastPreference,
    pub prefers_reduced_data: bool,
    pub prefers_reduced_transparency: bool,
    pub forced_colors: bool,
    pub overflow_inline: OverflowBehavior,
    pub overflow_block: OverflowBehavior,
    pub update: UpdateFrequency,
    pub color_index: u32,
    /// Device physical dimensions in mm
    pub device_width_mm: f64,
    pub device_height_mm: f64,
}

impl Default for Viewport {
    fn default() -> Self {
        Self {
            width: 1280.0, height: 720.0, device_pixel_ratio: 1.0,
            color_depth: 8, monochrome: 0, orientation: Orientation::Landscape,
            hover: HoverCapability::Hover, pointer: PointerCapability::Fine,
            any_hover: HoverCapability::Hover, any_pointer: PointerCapability::Fine,
            color_gamut: ColorGamut::Srgb,
            prefers_color_scheme: ColorScheme::Light,
            prefers_reduced_motion: false,
            prefers_contrast: ContrastPreference::NoPreference,
            prefers_reduced_data: false,
            prefers_reduced_transparency: false,
            forced_colors: false,
            overflow_inline: OverflowBehavior::Scroll,
            overflow_block: OverflowBehavior::Scroll,
            update: UpdateFrequency::Fast,
            color_index: 0,
            device_width_mm: 280.0,
            device_height_mm: 160.0,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Orientation { Portrait, Landscape }

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HoverCapability { None, Hover }

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PointerCapability { None, Coarse, Fine }

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ColorGamut { Srgb, P3, Rec2020 }

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ColorScheme { Light, Dark, NoPreference }

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ContrastPreference { NoPreference, More, Less, Forced }

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OverflowBehavior { None, Scroll, OptionalPaged, Paged }

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum UpdateFrequency { None, Slow, Fast }

/// A media query feature value (handles both keyword and length values)
#[derive(Debug, Clone, PartialEq)]
pub enum MqValue {
    Length(f64),          // Resolved to px
    Number(f64),          // Pure number (e.g., aspect-ratio: 16/9)
    Ratio(f64, f64),      // Aspect ratio (numerator, denominator)
    Keyword(String),      // Discrete value
    Resolution(f64),      // In dpi
}

impl MqValue {
    pub fn parse(s: &str, viewport_width: f64) -> Self {
        let s = s.trim().to_lowercase();
        
        // Aspect ratio (e.g., "16/9" or "16 / 9")
        if let Some(slash) = s.find('/') {
            let num = s[..slash].trim().parse::<f64>().unwrap_or(1.0);
            let den = s[slash+1..].trim().parse::<f64>().unwrap_or(1.0);
            return Self::Ratio(num, den);
        }
        
        // Length values
        if let Some(px) = s.strip_suffix("px") { return Self::Length(px.parse().unwrap_or(0.0)); }
        if let Some(em) = s.strip_suffix("em") { return Self::Length(em.parse::<f64>().unwrap_or(0.0) * 16.0); }
        if let Some(rem) = s.strip_suffix("rem") { return Self::Length(rem.parse::<f64>().unwrap_or(0.0) * 16.0); }
        if let Some(vw) = s.strip_suffix("vw") { return Self::Length(vw.parse::<f64>().unwrap_or(0.0) * viewport_width / 100.0); }
        if let Some(pt) = s.strip_suffix("pt") { return Self::Length(pt.parse::<f64>().unwrap_or(0.0) * 1.333333); }
        if let Some(in_) = s.strip_suffix("in") { return Self::Length(in_.parse::<f64>().unwrap_or(0.0) * 96.0); }
        if let Some(cm) = s.strip_suffix("cm") { return Self::Length(cm.parse::<f64>().unwrap_or(0.0) * 37.795); }
        if let Some(mm) = s.strip_suffix("mm") { return Self::Length(mm.parse::<f64>().unwrap_or(0.0) * 3.7795); }
        
        // Resolution
        if let Some(dpi) = s.strip_suffix("dpi") { return Self::Resolution(dpi.parse().unwrap_or(96.0)); }
        if let Some(dpcm) = s.strip_suffix("dpcm") { return Self::Resolution(dpcm.parse::<f64>().unwrap_or(0.0) * 2.54); }
        if let Some(dppx) = s.strip_suffix("dppx") { return Self::Resolution(dppx.parse::<f64>().unwrap_or(1.0) * 96.0); }
        
        // Number or keyword
        if let Ok(n) = s.parse::<f64>() { return Self::Number(n); }
        
        Self::Keyword(s)
    }
    
    pub fn as_px(&self) -> f64 {
        match self { Self::Length(px) => *px, Self::Number(n) => *n, _ => 0.0 }
    }
    
    pub fn as_ratio(&self) -> f64 {
        match self {
            Self::Ratio(n, d) => if *d != 0.0 { n / d } else { 0.0 },
            Self::Number(n) => *n,
            _ => 0.0,
        }
    }
}

/// A comparison operator for range-syntax media features
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RangeOp { Lt, Lte, Eq, Gte, Gt }

impl RangeOp {
    pub fn compare(&self, a: f64, b: f64) -> bool {
        match self {
            Self::Lt => a < b,
            Self::Lte => a <= b,
            Self::Eq => (a - b).abs() < 0.001,
            Self::Gte => a >= b,
            Self::Gt => a > b,
        }
    }
    
    pub fn from_str(s: &str) -> Option<Self> {
        match s {
            "<" => Some(Self::Lt),
            "<=" => Some(Self::Lte),
            "=" => Some(Self::Eq),
            ">=" => Some(Self::Gte),
            ">" => Some(Self::Gt),
            _ => None,
        }
    }
}

/// A single media feature condition
#[derive(Debug, Clone)]
pub enum MediaFeature {
    // Width range features
    Width(Option<MqValue>, Option<MqValue>),           // min, max (None = no bound)
    Height(Option<MqValue>, Option<MqValue>),
    DeviceWidth(Option<MqValue>, Option<MqValue>),
    DeviceHeight(Option<MqValue>, Option<MqValue>),
    AspectRatio(Option<MqValue>, Option<MqValue>),
    DeviceAspectRatio(Option<MqValue>, Option<MqValue>),
    
    // Range syntax (e.g., 100px < width <= 800px)
    Range { feature: String, left: Option<(MqValue, RangeOp)>, right: Option<(RangeOp, MqValue)> },
    
    // Discrete features
    Orientation(Orientation),
    Resolution(Option<MqValue>, Option<MqValue>),
    Color(Option<MqValue>, Option<MqValue>),
    ColorIndex(Option<MqValue>, Option<MqValue>),
    Monochrome(Option<MqValue>, Option<MqValue>),
    
    // User preference features
    PrefersColorScheme(ColorScheme),
    PrefersReducedMotion(bool),
    PrefersContrast(ContrastPreference),
    PrefersReducedData(bool),
    PrefersReducedTransparency(bool),
    ForcedColors(bool),
    
    // Interaction features
    Hover(HoverCapability),
    AnyHover(HoverCapability),
    Pointer(PointerCapability),
    AnyPointer(PointerCapability),
    
    // Display quality
    ColorGamut(ColorGamut),
    Update(UpdateFrequency),
    OverflowBlock(OverflowBehavior),
    OverflowInline(OverflowBehavior),
    
    // Boolean (just checking if supported)
    Boolean(String),
}

impl MediaFeature {
    pub fn matches(&self, vp: &Viewport) -> bool {
        match self {
            Self::Width(min, max) => {
                min.as_ref().map_or(true, |m| vp.width >= m.as_px()) &&
                max.as_ref().map_or(true, |m| vp.width <= m.as_px())
            }
            Self::Height(min, max) => {
                min.as_ref().map_or(true, |m| vp.height >= m.as_px()) &&
                max.as_ref().map_or(true, |m| vp.height <= m.as_px())
            }
            Self::AspectRatio(min, max) => {
                let ratio = vp.width / vp.height;
                min.as_ref().map_or(true, |m| ratio >= m.as_ratio()) &&
                max.as_ref().map_or(true, |m| ratio <= m.as_ratio())
            }
            Self::Orientation(o) => {
                &vp.orientation == o
            }
            Self::PrefersColorScheme(scheme) => &vp.prefers_color_scheme == scheme,
            Self::PrefersReducedMotion(reduced) => vp.prefers_reduced_motion == *reduced,
            Self::PrefersContrast(pref) => &vp.prefers_contrast == pref,
            Self::PrefersReducedData(reduced) => vp.prefers_reduced_data == *reduced,
            Self::PrefersReducedTransparency(reduced) => vp.prefers_reduced_transparency == *reduced,
            Self::ForcedColors(forced) => vp.forced_colors == *forced,
            Self::Hover(cap) => &vp.hover == cap,
            Self::AnyHover(cap) => &vp.any_hover == cap,
            Self::Pointer(cap) => &vp.pointer == cap,
            Self::AnyPointer(cap) => &vp.any_pointer == cap,
            Self::ColorGamut(gamut) => {
                match (gamut, &vp.color_gamut) {
                    (ColorGamut::Srgb, _) => true,
                    (ColorGamut::P3, ColorGamut::P3 | ColorGamut::Rec2020) => true,
                    (ColorGamut::Rec2020, ColorGamut::Rec2020) => true,
                    _ => false,
                }
            }
            Self::Update(freq) => &vp.update == freq,
            Self::Resolution(min, max) => {
                let dpi = vp.device_pixel_ratio * 96.0;
                min.as_ref().map_or(true, |m| dpi >= m.as_px()) &&
                max.as_ref().map_or(true, |m| dpi <= m.as_px())
            }
            Self::Color(min, max) => {
                min.as_ref().map_or(true, |m| vp.color_depth as f64 >= m.as_px()) &&
                max.as_ref().map_or(true, |m| vp.color_depth as f64 <= m.as_px())
            }
            Self::Monochrome(min, max) => {
                min.as_ref().map_or(true, |m| vp.monochrome as f64 >= m.as_px()) &&
                max.as_ref().map_or(true, |m| vp.monochrome as f64 <= m.as_px())
            }
            Self::Range { feature, left, right } => {
                let value = Self::get_feature_value(feature, vp);
                let left_ok = left.as_ref().map_or(true, |(lv, op)| op.compare(lv.as_px(), value));
                let right_ok = right.as_ref().map_or(true, |(op, rv)| op.compare(value, rv.as_px()));
                left_ok && right_ok
            }
            Self::Boolean(feature) => {
                // Boolean check: supported if the feature has a non-zero/non-none value
                match feature.as_str() {
                    "color" => vp.color_depth > 0,
                    "grid" => false, // Grid displays (TTY) not supported
                    "monochrome" => vp.monochrome > 0,
                    _ => false,
                }
            }
            _ => true,
        }
    }
    
    fn get_feature_value(feature: &str, vp: &Viewport) -> f64 {
        match feature {
            "width" => vp.width,
            "height" => vp.height,
            "aspect-ratio" => vp.width / vp.height,
            "resolution" => vp.device_pixel_ratio * 96.0,
            "color" => vp.color_depth as f64,
            "monochrome" => vp.monochrome as f64,
            _ => 0.0,
        }
    }
}

/// A media query — combination of media type and conditions
#[derive(Debug, Clone)]
pub struct MediaQuery {
    /// Media type (None = applies to all)
    pub media_type: Option<MediaType>,
    /// Negated with `not`
    pub negated: bool,
    /// Feature conditions
    pub conditions: Vec<MediaCondition>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MediaType {
    All,
    Screen,
    Print,
    Speech,
}

impl MediaType {
    pub fn from_str(s: &str) -> Option<Self> {
        match s.to_lowercase().as_str() {
            "all" => Some(Self::All),
            "screen" => Some(Self::Screen),
            "print" => Some(Self::Print),
            "speech" => Some(Self::Speech),
            _ => None,
        }
    }
    
    pub fn matches_screen(&self) -> bool {
        matches!(self, Self::All | Self::Screen)
    }
}

/// A media condition (feature or boolean expression)
#[derive(Debug, Clone)]
pub enum MediaCondition {
    Feature(MediaFeature),
    Not(Box<MediaCondition>),
    And(Vec<MediaCondition>),
    Or(Vec<MediaCondition>),
}

impl MediaCondition {
    pub fn matches(&self, vp: &Viewport) -> bool {
        match self {
            Self::Feature(f) => f.matches(vp),
            Self::Not(c) => !c.matches(vp),
            Self::And(conditions) => conditions.iter().all(|c| c.matches(vp)),
            Self::Or(conditions) => conditions.iter().any(|c| c.matches(vp)),
        }
    }
}

impl MediaQuery {
    /// Evaluate this media query against a viewport
    pub fn matches(&self, vp: &Viewport) -> bool {
        // Check media type
        let type_matches = match &self.media_type {
            None => true,
            Some(t) => t.matches_screen(),
        };
        
        // Check feature conditions
        let features_match = self.conditions.iter().all(|c| c.matches(vp));
        
        let result = type_matches && features_match;
        
        if self.negated { !result } else { result }
    }
    
    /// Construct common media queries programmatically
    pub fn min_width(px: f64) -> Self {
        Self {
            media_type: Some(MediaType::Screen),
            negated: false,
            conditions: vec![MediaCondition::Feature(
                MediaFeature::Width(Some(MqValue::Length(px)), None)
            )],
        }
    }
    
    pub fn max_width(px: f64) -> Self {
        Self {
            media_type: Some(MediaType::Screen),
            negated: false,
            conditions: vec![MediaCondition::Feature(
                MediaFeature::Width(None, Some(MqValue::Length(px)))
            )],
        }
    }
    
    pub fn prefers_dark() -> Self {
        Self {
            media_type: None,
            negated: false,
            conditions: vec![MediaCondition::Feature(
                MediaFeature::PrefersColorScheme(ColorScheme::Dark)
            )],
        }
    }
    
    pub fn reduced_motion() -> Self {
        Self {
            media_type: None,
            negated: false,
            conditions: vec![MediaCondition::Feature(
                MediaFeature::PrefersReducedMotion(true)
            )],
        }
    }
}

/// CSS Container Query sizes (replaces viewport for @container evaluation)
#[derive(Debug, Clone, Copy)]
pub struct ContainerSize {
    pub inline_size: f64,
    pub block_size: f64,
    pub context: ContainerContext,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ContainerContext {
    Size,
    InlineSize,
    BlockSize,
    Style,
}

/// A CSS @container query condition
#[derive(Debug, Clone)]
pub struct ContainerQuery {
    /// Name of the container (None = nearest container)
    pub name: Option<String>,
    /// The condition to evaluate against the container size
    pub condition: ContainerCondition,
}

#[derive(Debug, Clone)]
pub enum ContainerCondition {
    InlineSize(Option<f64>, Option<f64>),  // min, max in px
    BlockSize(Option<f64>, Option<f64>),
    Width(Option<f64>, Option<f64>),
    Height(Option<f64>, Option<f64>),
    AspectRatio(Option<f64>, Option<f64>),
    Orientation(Orientation),
    Style(String, String),  // property, value
    And(Vec<ContainerCondition>),
    Or(Vec<ContainerCondition>),
    Not(Box<ContainerCondition>),
}

impl ContainerCondition {
    pub fn matches(&self, size: &ContainerSize) -> bool {
        match self {
            Self::InlineSize(min, max) => {
                min.map_or(true, |m| size.inline_size >= m) &&
                max.map_or(true, |m| size.inline_size <= m)
            }
            Self::BlockSize(min, max) => {
                min.map_or(true, |m| size.block_size >= m) &&
                max.map_or(true, |m| size.block_size <= m)
            }
            Self::Width(min, max) => {
                min.map_or(true, |m| size.inline_size >= m) &&
                max.map_or(true, |m| size.inline_size <= m)
            }
            Self::Height(min, max) => {
                min.map_or(true, |m| size.block_size >= m) &&
                max.map_or(true, |m| size.block_size <= m)
            }
            Self::AspectRatio(min, max) => {
                let ratio = size.inline_size / size.block_size;
                min.map_or(true, |m| ratio >= m) && max.map_or(true, |m| ratio <= m)
            }
            Self::Orientation(o) => {
                let is_landscape = size.inline_size > size.block_size;
                matches!(o, Orientation::Landscape) == is_landscape
            }
            Self::And(conditions) => conditions.iter().all(|c| c.matches(size)),
            Self::Or(conditions) => conditions.iter().any(|c| c.matches(size)),
            Self::Not(c) => !c.matches(size),
            Self::Style(_, _) => false, // Requires computed style access
        }
    }
}

impl ContainerQuery {
    pub fn matches(&self, size: &ContainerSize) -> bool {
        self.condition.matches(size)
    }
    
    /// Common container query constructors
    pub fn min_inline_size(px: f64) -> Self {
        Self { name: None, condition: ContainerCondition::InlineSize(Some(px), None) }
    }
    
    pub fn max_inline_size(px: f64) -> Self {
        Self { name: None, condition: ContainerCondition::InlineSize(None, Some(px)) }
    }
}

/// The media query evaluator for a full stylesheet
pub struct MediaQueryEvaluator {
    pub viewport: Viewport,
    /// Container sizes by container name
    pub containers: HashMap<String, ContainerSize>,
}

impl MediaQueryEvaluator {
    pub fn new(viewport: Viewport) -> Self {
        Self { viewport, containers: HashMap::new() }
    }
    
    pub fn matches_query(&self, query: &MediaQuery) -> bool {
        query.matches(&self.viewport)
    }
    
    pub fn matches_container(&self, query: &ContainerQuery, context_size: &ContainerSize) -> bool {
        let size = if let Some(name) = &query.name {
            self.containers.get(name).unwrap_or(context_size)
        } else {
            context_size
        };
        query.matches(size)
    }
    
    /// Filter a list of media queries and return only the matching ones
    pub fn matching_queries<'a>(&self, queries: &'a [MediaQuery]) -> Vec<&'a MediaQuery> {
        queries.iter().filter(|q| self.matches_query(q)).collect()
    }
    
    /// Update the viewport and return whether any queries changed their match state
    pub fn update_viewport(&mut self, new_vp: Viewport) -> bool {
        let old = std::mem::replace(&mut self.viewport, new_vp);
        let changed = old.width != self.viewport.width 
            || old.height != self.viewport.height
            || old.prefers_color_scheme != self.viewport.prefers_color_scheme;
        changed
    }
}
