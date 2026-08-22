//! CSS Style Resolution
//!
//! Parses inline styles and <style> blocks, resolves computed styles per element.
//! Converts CSS color/font properties to terminal-friendly representations.

use std::collections::HashMap;

/// Resolved CSS properties for a single element
#[derive(Debug, Clone, Default)]
pub struct ComputedStyle {
    pub color: Option<CssColor>,
    pub background_color: Option<CssColor>,
    pub font_weight: FontWeight,
    pub font_style: FontStyle,
    pub text_decoration: TextDecoration,
    pub display: Display,
    pub visibility: Visibility,
    pub font_size: FontSize,
    pub text_align: TextAlign,
    pub opacity: f32,
}

#[derive(Debug, Clone, PartialEq)]
pub struct CssColor {
    pub r: u8,
    pub g: u8,
    pub b: u8,
    pub a: f32,
}

impl CssColor {
    pub fn new(r: u8, g: u8, b: u8) -> Self {
        Self { r, g, b, a: 1.0 }
    }

    pub fn with_alpha(r: u8, g: u8, b: u8, a: f32) -> Self {
        Self { r, g, b, a }
    }

    /// Convert to closest ANSI 16-color
    pub fn to_ansi_code(&self) -> u8 {
        // Simple mapping based on dominant channel
        let (r, g, b) = (self.r, self.g, self.b);
        let bright = (r as u16 + g as u16 + b as u16) > 384;

        if r < 50 && g < 50 && b < 50 { return 30; } // black
        if r > 200 && g < 100 && b < 100 { return if bright { 91 } else { 31 }; } // red
        if r < 100 && g > 200 && b < 100 { return if bright { 92 } else { 32 }; } // green
        if r > 200 && g > 200 && b < 100 { return if bright { 93 } else { 33 }; } // yellow
        if r < 100 && g < 100 && b > 200 { return if bright { 94 } else { 34 }; } // blue
        if r > 200 && g < 100 && b > 200 { return if bright { 95 } else { 35 }; } // magenta
        if r < 100 && g > 200 && b > 200 { return if bright { 96 } else { 36 }; } // cyan
        if r > 200 && g > 200 && b > 200 { return if bright { 97 } else { 37 }; } // white
        if bright { 37 } else { 90 } // default to grey/white
    }

    /// Infer semantic intent from color
    pub fn semantic_intent(&self) -> &'static str {
        let (r, g, b) = (self.r, self.g, self.b);
        if r > 180 && g < 80 && b < 80 { return "danger"; }
        if r < 80 && g > 180 && b < 80 { return "success"; }
        if r < 80 && g < 80 && b > 180 { return "primary"; }
        if r > 180 && g > 150 && b < 80 { return "warning"; }
        if r > 150 && g > 150 && b > 150 { return "muted"; }
        "neutral"
    }
}

#[derive(Debug, Clone, PartialEq, Default)]
pub enum FontWeight {
    #[default]
    Normal,
    Bold,
    Light,
    Numeric(u16), // 100-900
}

impl FontWeight {
    pub fn is_bold(&self) -> bool {
        match self {
            FontWeight::Bold => true,
            FontWeight::Numeric(n) => *n >= 700,
            _ => false,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Default)]
pub enum FontStyle {
    #[default]
    Normal,
    Italic,
}

#[derive(Debug, Clone, PartialEq, Default)]
pub enum TextDecoration {
    #[default]
    None,
    Underline,
    LineThrough,
}

#[derive(Debug, Clone, PartialEq, Default)]
pub enum Display {
    #[default]
    Block,
    Inline,
    InlineBlock,
    Flex,
    Grid,
    None,
    Other(String),
}

#[derive(Debug, Clone, PartialEq, Default)]
pub enum Visibility {
    #[default]
    Visible,
    Hidden,
    Collapse,
}

#[derive(Debug, Clone, PartialEq, Default)]
pub enum FontSize {
    #[default]
    Medium,
    Small,
    Large,
    XLarge,
    XXLarge,
    Px(f32),
    Em(f32),
    Rem(f32),
}

impl FontSize {
    /// Estimate heading level from font size (1=largest, 6=smallest)
    pub fn heading_level(&self) -> Option<u8> {
        match self {
            FontSize::XXLarge => Some(1),
            FontSize::XLarge => Some(2),
            FontSize::Large => Some(3),
            FontSize::Px(px) if *px >= 32.0 => Some(1),
            FontSize::Px(px) if *px >= 24.0 => Some(2),
            FontSize::Px(px) if *px >= 20.0 => Some(3),
            FontSize::Px(px) if *px >= 18.0 => Some(4),
            FontSize::Em(em) if *em >= 2.0 => Some(1),
            FontSize::Em(em) if *em >= 1.5 => Some(2),
            FontSize::Rem(rem) if *rem >= 2.0 => Some(1),
            FontSize::Rem(rem) if *rem >= 1.5 => Some(2),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Default)]
pub enum TextAlign {
    #[default]
    Left,
    Center,
    Right,
    Justify,
}

/// Parse inline style string into ComputedStyle
pub fn parse_inline_style(style: &str) -> ComputedStyle {
    let mut computed = ComputedStyle::default();
    computed.opacity = 1.0;

    for declaration in style.split(';') {
        let declaration = declaration.trim();
        if declaration.is_empty() { continue; }

        let parts: Vec<&str> = declaration.splitn(2, ':').collect();
        if parts.len() != 2 { continue; }

        let property = parts[0].trim().to_lowercase();
        let value = parts[1].trim().to_lowercase();

        match property.as_str() {
            "color" => computed.color = parse_color(&value),
            "background-color" | "background" => computed.background_color = parse_color(&value),

            "font-weight" => {
                computed.font_weight = match value.as_str() {
                    "bold" => FontWeight::Bold,
                    "normal" => FontWeight::Normal,
                    "lighter" | "light" => FontWeight::Light,
                    _ => {
                        if let Ok(n) = value.parse::<u16>() {
                            FontWeight::Numeric(n)
                        } else {
                            FontWeight::Normal
                        }
                    }
                };
            }

            "font-style" => {
                computed.font_style = if value == "italic" || value == "oblique" {
                    FontStyle::Italic
                } else {
                    FontStyle::Normal
                };
            }

            "text-decoration" | "text-decoration-line" => {
                computed.text_decoration = if value.contains("underline") {
                    TextDecoration::Underline
                } else if value.contains("line-through") {
                    TextDecoration::LineThrough
                } else {
                    TextDecoration::None
                };
            }

            "display" => {
                computed.display = match value.as_str() {
                    "none" => Display::None,
                    "inline" => Display::Inline,
                    "inline-block" => Display::InlineBlock,
                    "flex" => Display::Flex,
                    "grid" => Display::Grid,
                    "block" => Display::Block,
                    _ => Display::Other(value.clone()),
                };
            }

            "visibility" => {
                computed.visibility = match value.as_str() {
                    "hidden" => Visibility::Hidden,
                    "collapse" => Visibility::Collapse,
                    _ => Visibility::Visible,
                };
            }

            "font-size" => {
                computed.font_size = if value.ends_with("px") {
                    value.trim_end_matches("px").parse::<f32>()
                        .map(FontSize::Px).unwrap_or(FontSize::Medium)
                } else if value.ends_with("em") {
                    value.trim_end_matches("em").parse::<f32>()
                        .map(FontSize::Em).unwrap_or(FontSize::Medium)
                } else if value.ends_with("rem") {
                    value.trim_end_matches("rem").parse::<f32>()
                        .map(FontSize::Rem).unwrap_or(FontSize::Medium)
                } else {
                    match value.as_str() {
                        "small" | "x-small" | "xx-small" => FontSize::Small,
                        "large" => FontSize::Large,
                        "x-large" => FontSize::XLarge,
                        "xx-large" => FontSize::XXLarge,
                        _ => FontSize::Medium,
                    }
                };
            }

            "text-align" => {
                computed.text_align = match value.as_str() {
                    "center" => TextAlign::Center,
                    "right" => TextAlign::Right,
                    "justify" => TextAlign::Justify,
                    _ => TextAlign::Left,
                };
            }

            "opacity" => {
                computed.opacity = value.parse::<f32>().unwrap_or(1.0);
            }

            _ => {}
        }
    }

    computed
}

/// Parse CSS color value
fn parse_color(value: &str) -> Option<CssColor> {
    let v = value.trim();

    // Hex: #rgb, #rrggbb
    if v.starts_with('#') {
        let hex = &v[1..];
        return match hex.len() {
            3 => {
                let r = u8::from_str_radix(&hex[0..1].repeat(2), 16).ok()?;
                let g = u8::from_str_radix(&hex[1..2].repeat(2), 16).ok()?;
                let b = u8::from_str_radix(&hex[2..3].repeat(2), 16).ok()?;
                Some(CssColor::new(r, g, b))
            }
            6 => {
                let r = u8::from_str_radix(&hex[0..2], 16).ok()?;
                let g = u8::from_str_radix(&hex[2..4], 16).ok()?;
                let b = u8::from_str_radix(&hex[4..6], 16).ok()?;
                Some(CssColor::new(r, g, b))
            }
            8 => {
                let r = u8::from_str_radix(&hex[0..2], 16).ok()?;
                let g = u8::from_str_radix(&hex[2..4], 16).ok()?;
                let b = u8::from_str_radix(&hex[4..6], 16).ok()?;
                let a = u8::from_str_radix(&hex[6..8], 16).ok()?;
                Some(CssColor::with_alpha(r, g, b, a as f32 / 255.0))
            }
            _ => None,
        };
    }

    // rgb(r, g, b) / rgba(r, g, b, a)
    if v.starts_with("rgb") {
        let inner = v.trim_start_matches("rgba(")
            .trim_start_matches("rgb(")
            .trim_end_matches(')');
        let parts: Vec<&str> = inner.split(',').collect();
        if parts.len() >= 3 {
            let r = parts[0].trim().parse::<u8>().ok()?;
            let g = parts[1].trim().parse::<u8>().ok()?;
            let b = parts[2].trim().parse::<u8>().ok()?;
            let a = if parts.len() >= 4 {
                parts[3].trim().parse::<f32>().unwrap_or(1.0)
            } else {
                1.0
            };
            return Some(CssColor::with_alpha(r, g, b, a));
        }
    }

    // Named colors
    match v {
        "red" => Some(CssColor::new(255, 0, 0)),
        "green" => Some(CssColor::new(0, 128, 0)),
        "blue" => Some(CssColor::new(0, 0, 255)),
        "white" => Some(CssColor::new(255, 255, 255)),
        "black" => Some(CssColor::new(0, 0, 0)),
        "yellow" => Some(CssColor::new(255, 255, 0)),
        "orange" => Some(CssColor::new(255, 165, 0)),
        "purple" => Some(CssColor::new(128, 0, 128)),
        "cyan" => Some(CssColor::new(0, 255, 255)),
        "magenta" => Some(CssColor::new(255, 0, 255)),
        "gray" | "grey" => Some(CssColor::new(128, 128, 128)),
        "pink" => Some(CssColor::new(255, 192, 203)),
        "brown" => Some(CssColor::new(165, 42, 42)),
        "navy" => Some(CssColor::new(0, 0, 128)),
        "teal" => Some(CssColor::new(0, 128, 128)),
        "silver" => Some(CssColor::new(192, 192, 192)),
        "transparent" => Some(CssColor::with_alpha(0, 0, 0, 0.0)),
        _ => None,
    }
}

/// Extract all <style> blocks from HTML and collect inline styles
pub fn extract_style_blocks(html: &str) -> Vec<String> {
    let mut styles = Vec::new();
    let mut pos = 0;

    while let Some(start) = html[pos..].find("<style") {
        let start = pos + start;
        if let Some(content_start) = html[start..].find('>') {
            let content_start = start + content_start + 1;
            if let Some(end) = html[content_start..].find("</style>") {
                let end = content_start + end;
                styles.push(html[content_start..end].to_string());
                pos = end + 8;
            } else {
                break;
            }
        } else {
            break;
        }
    }

    styles
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_hex_color() {
        let color = parse_color("#ff0000").unwrap();
        assert_eq!(color.r, 255);
        assert_eq!(color.g, 0);
        assert_eq!(color.b, 0);
    }

    #[test]
    fn test_parse_short_hex() {
        let color = parse_color("#f00").unwrap();
        assert_eq!(color.r, 255);
        assert_eq!(color.g, 0);
        assert_eq!(color.b, 0);
    }

    #[test]
    fn test_parse_rgb() {
        let color = parse_color("rgb(0, 128, 255)").unwrap();
        assert_eq!(color.r, 0);
        assert_eq!(color.g, 128);
        assert_eq!(color.b, 255);
    }

    #[test]
    fn test_parse_named_color() {
        let color = parse_color("red").unwrap();
        assert_eq!(color.r, 255);
    }

    #[test]
    fn test_semantic_intent() {
        assert_eq!(CssColor::new(255, 0, 0).semantic_intent(), "danger");
        assert_eq!(CssColor::new(0, 200, 0).semantic_intent(), "success");
        assert_eq!(CssColor::new(0, 0, 255).semantic_intent(), "primary");
    }

    #[test]
    fn test_inline_style() {
        let style = parse_inline_style("color: red; font-weight: bold; display: none");
        assert!(style.font_weight.is_bold());
        assert_eq!(style.display, Display::None);
        assert_eq!(style.color.unwrap().r, 255);
    }

    #[test]
    fn test_font_size_heading() {
        assert_eq!(FontSize::Px(36.0).heading_level(), Some(1));
        assert_eq!(FontSize::Px(24.0).heading_level(), Some(2));
        assert_eq!(FontSize::Px(14.0).heading_level(), None);
    }
}
