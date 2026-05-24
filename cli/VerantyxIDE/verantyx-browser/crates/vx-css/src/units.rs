//! CSS Units & Values — Complete Length/Percentage/Angle/Time types
//!
//! Implements CSS Values and Units Module Level 4
//! https://www.w3.org/TR/css-values-4/

use std::fmt;

/// Viewport dimensions (needed for vh/vw resolution)
#[derive(Debug, Clone, Copy)]
pub struct Viewport {
    pub width: f32,
    pub height: f32,
    pub dpr: f32,  // Device pixel ratio
}

impl Default for Viewport {
    fn default() -> Self {
        Self { width: 1280.0, height: 800.0, dpr: 1.0 }
    }
}

/// Font context (needed for em/rem/ex resolution)
#[derive(Debug, Clone, Copy)]
pub struct FontContext {
    pub font_size: f32,        // current element's font-size (px)
    pub root_font_size: f32,   // root element's font-size (px)
    pub x_height: f32,         // ex unit (typically 0.5em)
    pub cap_height: f32,       // cap unit
    pub ch_width: f32,         // ch unit (0 character width)
    pub ic_width: f32,         // ic unit (水 character width)
    pub line_height: f32,      // lh unit
    pub root_line_height: f32, // rlh unit
}

impl Default for FontContext {
    fn default() -> Self {
        Self {
            font_size: 16.0,
            root_font_size: 16.0,
            x_height: 8.0,
            cap_height: 11.0,
            ch_width: 9.6,
            ic_width: 16.0,
            line_height: 19.2,
            root_line_height: 19.2,
        }
    }
}

/// A CSS length unit
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum LengthUnit {
    // Absolute
    Px,
    Pt,
    Pc,
    In,
    Cm,
    Mm,
    Q,   // quarter-mm

    // Relative to font
    Em,
    Rem,
    Ex,
    Rex,
    Cap,
    Rcap,
    Ch,
    Rch,
    Ic,
    Ric,
    Lh,
    Rlh,

    // Viewport-relative
    Vw,
    Vh,
    Vmin,
    Vmax,
    Vb,
    Vi,
    Svw,  // Small viewport
    Svh,
    Dvw,  // Dynamic viewport
    Dvh,
    Lvw,  // Large viewport
    Lvh,
    Cqw,  // Container query
    Cqh,
    Cqi,
    Cqb,
    Cqmin,
    Cqmax,
}

impl fmt::Display for LengthUnit {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let s = match self {
            LengthUnit::Px => "px", LengthUnit::Pt => "pt",
            LengthUnit::Pc => "pc", LengthUnit::In => "in",
            LengthUnit::Cm => "cm", LengthUnit::Mm => "mm",
            LengthUnit::Q => "Q",
            LengthUnit::Em => "em", LengthUnit::Rem => "rem",
            LengthUnit::Ex => "ex", LengthUnit::Rex => "rex",
            LengthUnit::Cap => "cap", LengthUnit::Rcap => "rcap",
            LengthUnit::Ch => "ch", LengthUnit::Rch => "rch",
            LengthUnit::Ic => "ic", LengthUnit::Ric => "ric",
            LengthUnit::Lh => "lh", LengthUnit::Rlh => "rlh",
            LengthUnit::Vw => "vw", LengthUnit::Vh => "vh",
            LengthUnit::Vmin => "vmin", LengthUnit::Vmax => "vmax",
            LengthUnit::Vb => "vb", LengthUnit::Vi => "vi",
            LengthUnit::Svw => "svw", LengthUnit::Svh => "svh",
            LengthUnit::Dvw => "dvw", LengthUnit::Dvh => "dvh",
            LengthUnit::Lvw => "lvw", LengthUnit::Lvh => "lvh",
            LengthUnit::Cqw => "cqw", LengthUnit::Cqh => "cqh",
            LengthUnit::Cqi => "cqi", LengthUnit::Cqb => "cqb",
            LengthUnit::Cqmin => "cqmin", LengthUnit::Cqmax => "cqmax",
        };
        write!(f, "{}", s)
    }
}

impl LengthUnit {
    pub fn parse(s: &str) -> Option<Self> {
        match s.to_lowercase().as_str() {
            "px" => Some(Self::Px),
            "pt" => Some(Self::Pt),
            "pc" => Some(Self::Pc),
            "in" => Some(Self::In),
            "cm" => Some(Self::Cm),
            "mm" => Some(Self::Mm),
            "q" => Some(Self::Q),
            "em" => Some(Self::Em),
            "rem" => Some(Self::Rem),
            "ex" => Some(Self::Ex),
            "rex" => Some(Self::Rex),
            "cap" => Some(Self::Cap),
            "rcap" => Some(Self::Rcap),
            "ch" => Some(Self::Ch),
            "rch" => Some(Self::Rch),
            "ic" => Some(Self::Ic),
            "ric" => Some(Self::Ric),
            "lh" => Some(Self::Lh),
            "rlh" => Some(Self::Rlh),
            "vw" => Some(Self::Vw),
            "vh" => Some(Self::Vh),
            "vmin" => Some(Self::Vmin),
            "vmax" => Some(Self::Vmax),
            "vb" => Some(Self::Vb),
            "vi" => Some(Self::Vi),
            "svw" => Some(Self::Svw),
            "svh" => Some(Self::Svh),
            "dvw" => Some(Self::Dvw),
            "dvh" => Some(Self::Dvh),
            "lvw" => Some(Self::Lvw),
            "lvh" => Some(Self::Lvh),
            "cqw" => Some(Self::Cqw),
            "cqh" => Some(Self::Cqh),
            "cqi" => Some(Self::Cqi),
            "cqb" => Some(Self::Cqb),
            "cqmin" => Some(Self::Cqmin),
            "cqmax" => Some(Self::Cqmax),
            _ => None,
        }
    }

    /// Is this unit absolute (does not depend on context)?
    pub fn is_absolute(&self) -> bool {
        matches!(self, Self::Px | Self::Pt | Self::Pc | Self::In | Self::Cm | Self::Mm | Self::Q)
    }
}

/// A CSS length value
#[derive(Debug, Clone, PartialEq)]
pub struct Length {
    pub value: f32,
    pub unit: LengthUnit,
}

impl Length {
    pub fn px(value: f32) -> Self { Self { value, unit: LengthUnit::Px } }
    pub fn em(value: f32) -> Self { Self { value, unit: LengthUnit::Em } }
    pub fn rem(value: f32) -> Self { Self { value, unit: LengthUnit::Rem } }
    pub fn vw(value: f32) -> Self { Self { value, unit: LengthUnit::Vw } }
    pub fn vh(value: f32) -> Self { Self { value, unit: LengthUnit::Vh } }
    pub fn zero() -> Self { Self::px(0.0) }

    /// Resolve to pixels given context
    pub fn to_px(&self, font: &FontContext, viewport: &Viewport) -> f32 {
        match self.unit {
            // Absolute
            LengthUnit::Px => self.value,
            LengthUnit::Pt => self.value * 4.0 / 3.0,
            LengthUnit::Pc => self.value * 16.0,
            LengthUnit::In => self.value * 96.0,
            LengthUnit::Cm => self.value * 96.0 / 2.54,
            LengthUnit::Mm => self.value * 96.0 / 25.4,
            LengthUnit::Q => self.value * 96.0 / 101.6,

            // Font-relative
            LengthUnit::Em => self.value * font.font_size,
            LengthUnit::Rem => self.value * font.root_font_size,
            LengthUnit::Ex | LengthUnit::Rex => self.value * font.x_height,
            LengthUnit::Cap | LengthUnit::Rcap => self.value * font.cap_height,
            LengthUnit::Ch | LengthUnit::Rch => self.value * font.ch_width,
            LengthUnit::Ic | LengthUnit::Ric => self.value * font.ic_width,
            LengthUnit::Lh => self.value * font.line_height,
            LengthUnit::Rlh => self.value * font.root_line_height,

            // Viewport
            LengthUnit::Vw | LengthUnit::Svw | LengthUnit::Dvw | LengthUnit::Lvw => {
                self.value * viewport.width / 100.0
            }
            LengthUnit::Vh | LengthUnit::Svh | LengthUnit::Dvh | LengthUnit::Lvh => {
                self.value * viewport.height / 100.0
            }
            LengthUnit::Vmin => self.value * viewport.width.min(viewport.height) / 100.0,
            LengthUnit::Vmax => self.value * viewport.width.max(viewport.height) / 100.0,
            LengthUnit::Vi => self.value * viewport.width / 100.0,  // horizontal by default
            LengthUnit::Vb => self.value * viewport.height / 100.0, // vertical by default
            // Container queries — fall back to viewport for now
            LengthUnit::Cqw | LengthUnit::Cqi => self.value * viewport.width / 100.0,
            LengthUnit::Cqh | LengthUnit::Cqb => self.value * viewport.height / 100.0,
            LengthUnit::Cqmin => self.value * viewport.width.min(viewport.height) / 100.0,
            LengthUnit::Cqmax => self.value * viewport.width.max(viewport.height) / 100.0,
        }
    }

    /// Parse a length string like "10px", "2em", "50%", "0"
    pub fn parse(s: &str) -> Option<Self> {
        let s = s.trim();
        if s == "0" {
            return Some(Self::zero());
        }

        // Find where the number ends
        let split_pos = s.find(|c: char| c.is_alphabetic()).unwrap_or(s.len());
        let num_str = &s[..split_pos];
        let unit_str = &s[split_pos..];

        let value: f32 = num_str.parse().ok()?;
        let unit = LengthUnit::parse(unit_str)?;

        Some(Self { value, unit })
    }
}

impl fmt::Display for Length {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}{}", self.value, self.unit)
    }
}

/// CSS percentage
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Percentage(pub f32);

impl Percentage {
    pub fn to_fraction(self) -> f32 { self.0 / 100.0 }
    pub fn of(self, base: f32) -> f32 { base * self.to_fraction() }
    pub fn parse(s: &str) -> Option<Self> {
        s.trim_end_matches('%').parse::<f32>().ok().map(Self)
    }
}

impl fmt::Display for Percentage {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}%", self.0)
    }
}

/// CSS angle
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Angle {
    Deg(f32),
    Rad(f32),
    Grad(f32),
    Turn(f32),
}

impl Angle {
    pub fn to_deg(self) -> f32 {
        match self {
            Angle::Deg(v) => v,
            Angle::Rad(v) => v * 180.0 / std::f32::consts::PI,
            Angle::Grad(v) => v * 0.9,
            Angle::Turn(v) => v * 360.0,
        }
    }

    pub fn to_rad(self) -> f32 {
        self.to_deg() * std::f32::consts::PI / 180.0
    }

    pub fn parse(s: &str) -> Option<Self> {
        let s = s.trim();
        if let Some(v) = s.strip_suffix("deg") {
            return v.trim().parse().ok().map(Angle::Deg);
        }
        if let Some(v) = s.strip_suffix("rad") {
            return v.trim().parse().ok().map(Angle::Rad);
        }
        if let Some(v) = s.strip_suffix("grad") {
            return v.trim().parse().ok().map(Angle::Grad);
        }
        if let Some(v) = s.strip_suffix("turn") {
            return v.trim().parse().ok().map(Angle::Turn);
        }
        None
    }
}

/// CSS time
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Time {
    S(f32),
    Ms(f32),
}

impl Time {
    pub fn to_ms(self) -> f32 {
        match self {
            Time::S(v) => v * 1000.0,
            Time::Ms(v) => v,
        }
    }

    pub fn parse(s: &str) -> Option<Self> {
        let s = s.trim();
        if let Some(v) = s.strip_suffix("ms") {
            return v.trim().parse().ok().map(Time::Ms);
        }
        if let Some(v) = s.strip_suffix('s') {
            return v.trim().parse().ok().map(Time::S);
        }
        None
    }
}

/// CSS resolution
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Resolution {
    Dpi(f32),
    Dpcm(f32),
    Dppx(f32),
}

impl Resolution {
    pub fn to_dppx(self) -> f32 {
        match self {
            Resolution::Dpi(v) => v / 96.0,
            Resolution::Dpcm(v) => v / 37.8,
            Resolution::Dppx(v) => v,
        }
    }
}

/// CSS <length-percentage>
#[derive(Debug, Clone, PartialEq)]
pub enum LengthPercentage {
    Length(Length),
    Percentage(Percentage),
    Calc(Box<CalcExpr>),
}

impl LengthPercentage {
    pub fn zero() -> Self { Self::Length(Length::zero()) }
    pub fn auto() -> Self { Self::Length(Length::px(0.0)) } // placeholder

    pub fn to_px(&self, containing: f32, font: &FontContext, viewport: &Viewport) -> f32 {
        match self {
            Self::Length(l) => l.to_px(font, viewport),
            Self::Percentage(p) => p.of(containing),
            Self::Calc(expr) => expr.resolve(containing, font, viewport),
        }
    }

    pub fn parse(s: &str) -> Option<Self> {
        let s = s.trim();
        if s.ends_with('%') {
            Percentage::parse(s).map(Self::Percentage)
        } else if s.starts_with("calc(") {
            // Basic calc support
            Some(Self::Length(Length::zero())) // TODO: full calc
        } else {
            Length::parse(s).map(Self::Length)
        }
    }
}

/// A CSS calc() expression
#[derive(Debug, Clone, PartialEq)]
pub enum CalcExpr {
    Length(Length),
    Percentage(Percentage),
    Add(Box<CalcExpr>, Box<CalcExpr>),
    Sub(Box<CalcExpr>, Box<CalcExpr>),
    Mul(Box<CalcExpr>, f32),
    Div(Box<CalcExpr>, f32),
    Min(Vec<CalcExpr>),
    Max(Vec<CalcExpr>),
    Clamp(Box<CalcExpr>, Box<CalcExpr>, Box<CalcExpr>),
}

impl CalcExpr {
    pub fn resolve(&self, containing: f32, font: &FontContext, viewport: &Viewport) -> f32 {
        match self {
            Self::Length(l) => l.to_px(font, viewport),
            Self::Percentage(p) => p.of(containing),
            Self::Add(a, b) => a.resolve(containing, font, viewport) + b.resolve(containing, font, viewport),
            Self::Sub(a, b) => a.resolve(containing, font, viewport) - b.resolve(containing, font, viewport),
            Self::Mul(a, f) => a.resolve(containing, font, viewport) * f,
            Self::Div(a, f) => if *f != 0.0 { a.resolve(containing, font, viewport) / f } else { 0.0 },
            Self::Min(exprs) => exprs.iter().map(|e| e.resolve(containing, font, viewport)).fold(f32::INFINITY, f32::min),
            Self::Max(exprs) => exprs.iter().map(|e| e.resolve(containing, font, viewport)).fold(f32::NEG_INFINITY, f32::max),
            Self::Clamp(min, val, max) => {
                val.resolve(containing, font, viewport)
                    .max(min.resolve(containing, font, viewport))
                    .min(max.resolve(containing, font, viewport))
            }
        }
    }
}

/// A general CSS value
#[derive(Debug, Clone, PartialEq)]
pub enum CssValue {
    Length(Length),
    Percentage(Percentage),
    LengthPercentage(LengthPercentage),
    Number(f32),
    Integer(i32),
    Angle(Angle),
    Time(Time),
    Resolution(Resolution),
    Keyword(String),
    String(String),
    Url(String),
    None,
    Auto,
    Initial,
    Inherit,
    Unset,
    Revert,
    RevertLayer,
    /// calc(), min(), max(), clamp()
    Calc(CalcExpr),
    /// var(--custom)
    Var(String, Option<Box<CssValue>>),
    /// env(VARIABLE)
    Env(String),
}

impl CssValue {
    pub fn parse(s: &str) -> Option<Self> {
        let s = s.trim();
        match s {
            "none" => return Some(Self::None),
            "auto" => return Some(Self::Auto),
            "initial" => return Some(Self::Initial),
            "inherit" => return Some(Self::Inherit),
            "unset" => return Some(Self::Unset),
            "revert" => return Some(Self::Revert),
            "revert-layer" => return Some(Self::RevertLayer),
            _ => {}
        }

        if let Some(l) = Length::parse(s) {
            return Some(Self::Length(l));
        }
        if let Some(p) = Percentage::parse(s) {
            return Some(Self::Percentage(p));
        }
        if let Some(a) = Angle::parse(s) {
            return Some(Self::Angle(a));
        }
        if let Some(t) = Time::parse(s) {
            return Some(Self::Time(t));
        }
        if let Ok(n) = s.parse::<f32>() {
            return Some(Self::Number(n));
        }
        if let Ok(i) = s.parse::<i32>() {
            return Some(Self::Integer(i));
        }
        if s.starts_with("var(--") {
            let name = s.trim_start_matches("var(").trim_end_matches(')');
            return Some(Self::Var(name.to_string(), None));
        }
        if s.starts_with('"') || s.starts_with('\'') {
            return Some(Self::String(s.trim_matches(|c| c == '"' || c == '\'').to_string()));
        }
        if s.starts_with("url(") {
            let url = s.trim_start_matches("url(").trim_end_matches(')').trim_matches(|c| c == '"' || c == '\'');
            return Some(Self::Url(url.to_string()));
        }

        // Keyword fallback
        Some(Self::Keyword(s.to_string()))
    }
}

impl fmt::Display for CssValue {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Length(l) => write!(f, "{}", l),
            Self::Percentage(p) => write!(f, "{}", p),
            Self::Number(n) => write!(f, "{}", n),
            Self::Integer(i) => write!(f, "{}", i),
            Self::Keyword(k) => write!(f, "{}", k),
            Self::None => write!(f, "none"),
            Self::Auto => write!(f, "auto"),
            Self::Initial => write!(f, "initial"),
            Self::Inherit => write!(f, "inherit"),
            Self::Unset => write!(f, "unset"),
            _ => write!(f, "<css-value>"),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_length_parse() {
        assert_eq!(Length::parse("10px"), Some(Length::px(10.0)));
        assert_eq!(Length::parse("2em"), Some(Length::em(2.0)));
        assert_eq!(Length::parse("0"), Some(Length::zero()));
    }

    #[test]
    fn test_length_resolve() {
        let font = FontContext::default();
        let viewport = Viewport::default();
        assert_eq!(Length::px(10.0).to_px(&font, &viewport), 10.0);
        assert_eq!(Length::em(2.0).to_px(&font, &viewport), 32.0);
        assert!((Length { value: 50.0, unit: LengthUnit::Vw }.to_px(&font, &viewport) - 640.0).abs() < 0.1);
    }

    #[test]
    fn test_angle_parse() {
        assert_eq!(Angle::parse("90deg").map(|a| a.to_deg()), Some(90.0));
        let rad = Angle::parse("1rad").unwrap().to_deg();
        assert!((rad - 57.295).abs() < 0.01);
    }

    #[test]
    fn test_time_parse() {
        assert_eq!(Time::parse("500ms").map(|t| t.to_ms()), Some(500.0));
        assert_eq!(Time::parse("1s").map(|t| t.to_ms()), Some(1000.0));
    }
}
