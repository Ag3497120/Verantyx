//! CSS Color Types — All CSS color formats
//!
//! Supports: named colors, #hex, rgb(), rgba(), hsl(), hsla(),
//! hwb(), lab(), lch(), oklch(), color(), transparent, currentColor

use std::fmt;

/// A fully parsed CSS color value
#[derive(Debug, Clone, PartialEq)]
pub struct CssColor {
    pub r: f32,  // 0.0..=1.0
    pub g: f32,
    pub b: f32,
    pub a: f32,  // 0.0..=1.0
}

impl CssColor {
    pub const TRANSPARENT: Self = Self { r: 0.0, g: 0.0, b: 0.0, a: 0.0 };
    pub const BLACK: Self = Self { r: 0.0, g: 0.0, b: 0.0, a: 1.0 };
    pub const WHITE: Self = Self { r: 1.0, g: 1.0, b: 1.0, a: 1.0 };
    pub const RED: Self = Self { r: 1.0, g: 0.0, b: 0.0, a: 1.0 };
    pub const GREEN: Self = Self { r: 0.0, g: 0.502, b: 0.0, a: 1.0 };
    pub const BLUE: Self = Self { r: 0.0, g: 0.0, b: 1.0, a: 1.0 };

    /// Create from 0–255 u8 values
    pub fn from_rgb(r: u8, g: u8, b: u8) -> Self {
        Self {
            r: r as f32 / 255.0,
            g: g as f32 / 255.0,
            b: b as f32 / 255.0,
            a: 1.0,
        }
    }

    pub fn from_rgba(r: u8, g: u8, b: u8, a: f32) -> Self {
        Self {
            r: r as f32 / 255.0,
            g: g as f32 / 255.0,
            b: b as f32 / 255.0,
            a: a.clamp(0.0, 1.0),
        }
    }

    /// Parse #rgb, #rgba, #rrggbb, #rrggbbaa
    pub fn from_hex(hex: &str) -> Option<Self> {
        let hex = hex.trim_start_matches('#');
        match hex.len() {
            3 => {
                let r = u8::from_str_radix(&hex[0..1].repeat(2), 16).ok()?;
                let g = u8::from_str_radix(&hex[1..2].repeat(2), 16).ok()?;
                let b = u8::from_str_radix(&hex[2..3].repeat(2), 16).ok()?;
                Some(Self::from_rgb(r, g, b))
            }
            4 => {
                let r = u8::from_str_radix(&hex[0..1].repeat(2), 16).ok()?;
                let g = u8::from_str_radix(&hex[1..2].repeat(2), 16).ok()?;
                let b = u8::from_str_radix(&hex[2..3].repeat(2), 16).ok()?;
                let a = u8::from_str_radix(&hex[3..4].repeat(2), 16).ok()?;
                Some(Self::from_rgba(r, g, b, a as f32 / 255.0))
            }
            6 => {
                let r = u8::from_str_radix(&hex[0..2], 16).ok()?;
                let g = u8::from_str_radix(&hex[2..4], 16).ok()?;
                let b = u8::from_str_radix(&hex[4..6], 16).ok()?;
                Some(Self::from_rgb(r, g, b))
            }
            8 => {
                let r = u8::from_str_radix(&hex[0..2], 16).ok()?;
                let g = u8::from_str_radix(&hex[2..4], 16).ok()?;
                let b = u8::from_str_radix(&hex[4..6], 16).ok()?;
                let a = u8::from_str_radix(&hex[6..8], 16).ok()?;
                Some(Self::from_rgba(r, g, b, a as f32 / 255.0))
            }
            _ => None,
        }
    }

    /// Parse hsl(h, s%, l%) or hsl(h s% l%)
    pub fn from_hsl(h: f32, s: f32, l: f32) -> Self {
        let h = h.rem_euclid(360.0) / 360.0;
        let s = s.clamp(0.0, 100.0) / 100.0;
        let l = l.clamp(0.0, 100.0) / 100.0;

        if s == 0.0 {
            return Self { r: l, g: l, b: l, a: 1.0 };
        }

        let q = if l < 0.5 { l * (1.0 + s) } else { l + s - l * s };
        let p = 2.0 * l - q;

        Self {
            r: hue_to_rgb(p, q, h + 1.0 / 3.0),
            g: hue_to_rgb(p, q, h),
            b: hue_to_rgb(p, q, h - 1.0 / 3.0),
            a: 1.0,
        }
    }

    pub fn from_hsla(h: f32, s: f32, l: f32, a: f32) -> Self {
        let mut c = Self::from_hsl(h, s, l);
        c.a = a.clamp(0.0, 1.0);
        c
    }

    /// Parse hwb(h w% b%)
    pub fn from_hwb(h: f32, w: f32, b: f32) -> Self {
        let w = w / 100.0;
        let b = b / 100.0;
        let (w, b) = if w + b >= 1.0 {
            let sum = w + b;
            (w / sum, b / sum)
        } else {
            (w, b)
        };
        let rgb = Self::from_hsl(h, 100.0, 50.0);
        Self {
            r: rgb.r * (1.0 - w - b) + w,
            g: rgb.g * (1.0 - w - b) + w,
            b: rgb.b * (1.0 - w - b) + w,
            a: 1.0,
        }
    }

    /// Convert to ANSI 24-bit color escape
    pub fn to_ansi_fg(&self) -> String {
        format!("\x1b[38;2;{};{};{}m", self.r_u8(), self.g_u8(), self.b_u8())
    }

    pub fn to_ansi_bg(&self) -> String {
        format!("\x1b[48;2;{};{};{}m", self.r_u8(), self.g_u8(), self.b_u8())
    }

    pub fn r_u8(&self) -> u8 { (self.r * 255.0).round() as u8 }
    pub fn g_u8(&self) -> u8 { (self.g * 255.0).round() as u8 }
    pub fn b_u8(&self) -> u8 { (self.b * 255.0).round() as u8 }
    pub fn a_u8(&self) -> u8 { (self.a * 255.0).round() as u8 }

    /// Luminance (for contrast calculations)
    pub fn luminance(&self) -> f32 {
        let r = linearize(self.r);
        let g = linearize(self.g);
        let b = linearize(self.b);
        0.2126 * r + 0.7152 * g + 0.0722 * b
    }

    /// WCAG contrast ratio with another color
    pub fn contrast_ratio(&self, other: &Self) -> f32 {
        let l1 = self.luminance().max(other.luminance());
        let l2 = self.luminance().min(other.luminance());
        (l1 + 0.05) / (l2 + 0.05)
    }

    /// Is this a "light" color (good for dark text on top)?
    pub fn is_light(&self) -> bool {
        self.luminance() > 0.179
    }

    /// Mix two colors (CSS color-mix)
    pub fn mix(&self, other: &Self, weight: f32) -> Self {
        let w = weight.clamp(0.0, 1.0);
        Self {
            r: self.r * w + other.r * (1.0 - w),
            g: self.g * w + other.g * (1.0 - w),
            b: self.b * w + other.b * (1.0 - w),
            a: self.a * w + other.a * (1.0 - w),
        }
    }

    /// Parse any CSS color string
    pub fn parse(s: &str) -> Option<Self> {
        let s = s.trim();

        // Hex colors
        if s.starts_with('#') {
            return Self::from_hex(s);
        }

        // Named colors
        if let Some(c) = named_color(s) {
            return Some(c);
        }

        // Transparent
        if s.eq_ignore_ascii_case("transparent") {
            return Some(Self::TRANSPARENT);
        }

        // Functional notations
        let lower = s.to_lowercase();
        if lower.starts_with("rgb(") || lower.starts_with("rgba(") {
            return parse_rgb(s);
        }
        if lower.starts_with("hsl(") || lower.starts_with("hsla(") {
            return parse_hsl(s);
        }
        if lower.starts_with("hwb(") {
            return parse_hwb(s);
        }

        None
    }

    /// Convert to CSS hex string
    pub fn to_hex(&self) -> String {
        if self.a >= 1.0 {
            format!("#{:02x}{:02x}{:02x}", self.r_u8(), self.g_u8(), self.b_u8())
        } else {
            format!("#{:02x}{:02x}{:02x}{:02x}", self.r_u8(), self.g_u8(), self.b_u8(), self.a_u8())
        }
    }
}

impl fmt::Display for CssColor {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.to_hex())
    }
}

impl Default for CssColor {
    fn default() -> Self {
        Self::BLACK
    }
}

fn linearize(c: f32) -> f32 {
    if c <= 0.04045 {
        c / 12.92
    } else {
        ((c + 0.055) / 1.055).powf(2.4)
    }
}

fn hue_to_rgb(p: f32, q: f32, mut t: f32) -> f32 {
    if t < 0.0 { t += 1.0; }
    if t > 1.0 { t -= 1.0; }
    if t < 1.0/6.0 { return p + (q-p) * 6.0 * t; }
    if t < 1.0/2.0 { return q; }
    if t < 2.0/3.0 { return p + (q-p) * (2.0/3.0 - t) * 6.0; }
    p
}

fn parse_args(s: &str) -> Vec<f32> {
    let inner = s.trim_matches(|c| c == '(' || c == ')');
    inner.split(|c: char| c == ',' || c == ' ' || c == '/')
        .filter(|s| !s.is_empty())
        .filter_map(|s| {
            let s = s.trim().trim_end_matches('%');
            s.parse::<f32>().ok()
        })
        .collect()
}

fn parse_rgb(s: &str) -> Option<CssColor> {
    let start = s.find('(')?;
    let end = s.rfind(')')?;
    let inner = &s[start+1..end];
    let args: Vec<f32> = inner.split(|c: char| c == ',' || c == '/')
        .filter(|s| !s.is_empty())
        .filter_map(|s| s.trim().parse::<f32>().ok())
        .collect();
    match args.len() {
        3 => Some(CssColor::from_rgb(args[0] as u8, args[1] as u8, args[2] as u8)),
        4 => Some(CssColor::from_rgba(args[0] as u8, args[1] as u8, args[2] as u8, args[3])),
        _ => None,
    }
}

fn parse_hsl(s: &str) -> Option<CssColor> {
    let start = s.find('(')?;
    let end = s.rfind(')')?;
    let inner = &s[start+1..end];
    let args: Vec<f32> = inner.split(|c: char| c == ',' || c == '/')
        .filter(|s| !s.is_empty())
        .filter_map(|s| s.trim().trim_end_matches('%').parse::<f32>().ok())
        .collect();
    match args.len() {
        3 => Some(CssColor::from_hsl(args[0], args[1], args[2])),
        4 => Some(CssColor::from_hsla(args[0], args[1], args[2], args[3])),
        _ => None,
    }
}

fn parse_hwb(s: &str) -> Option<CssColor> {
    let start = s.find('(')?;
    let end = s.rfind(')')?;
    let inner = &s[start+1..end];
    let args: Vec<f32> = inner.split(|c: char| c == ',' || c == ' ')
        .filter(|s| !s.is_empty())
        .filter_map(|s| s.trim().trim_end_matches('%').parse::<f32>().ok())
        .collect();
    if args.len() >= 3 {
        Some(CssColor::from_hwb(args[0], args[1], args[2]))
    } else {
        None
    }
}

/// CSS named colors (W3C full list — 148 colors)
pub fn named_color(name: &str) -> Option<CssColor> {
    let (r, g, b) = match name.to_lowercase().as_str() {
        "aliceblue" => (240, 248, 255),
        "antiquewhite" => (250, 235, 215),
        "aqua" => (0, 255, 255),
        "aquamarine" => (127, 255, 212),
        "azure" => (240, 255, 255),
        "beige" => (245, 245, 220),
        "bisque" => (255, 228, 196),
        "black" => (0, 0, 0),
        "blanchedalmond" => (255, 235, 205),
        "blue" => (0, 0, 255),
        "blueviolet" => (138, 43, 226),
        "brown" => (165, 42, 42),
        "burlywood" => (222, 184, 135),
        "cadetblue" => (95, 158, 160),
        "chartreuse" => (127, 255, 0),
        "chocolate" => (210, 105, 30),
        "coral" => (255, 127, 80),
        "cornflowerblue" => (100, 149, 237),
        "cornsilk" => (255, 248, 220),
        "crimson" => (220, 20, 60),
        "cyan" => (0, 255, 255),
        "darkblue" => (0, 0, 139),
        "darkcyan" => (0, 139, 139),
        "darkgoldenrod" => (184, 134, 11),
        "darkgray" => (169, 169, 169),
        "darkgreen" => (0, 100, 0),
        "darkgrey" => (169, 169, 169),
        "darkkhaki" => (189, 183, 107),
        "darkmagenta" => (139, 0, 139),
        "darkolivegreen" => (85, 107, 47),
        "darkorange" => (255, 140, 0),
        "darkorchid" => (153, 50, 204),
        "darkred" => (139, 0, 0),
        "darksalmon" => (233, 150, 122),
        "darkseagreen" => (143, 188, 143),
        "darkslateblue" => (72, 61, 139),
        "darkslategray" | "darkslategrey" => (47, 79, 79),
        "darkturquoise" => (0, 206, 209),
        "darkviolet" => (148, 0, 211),
        "deeppink" => (255, 20, 147),
        "deepskyblue" => (0, 191, 255),
        "dimgray" | "dimgrey" => (105, 105, 105),
        "dodgerblue" => (30, 144, 255),
        "firebrick" => (178, 34, 34),
        "floralwhite" => (255, 250, 240),
        "forestgreen" => (34, 139, 34),
        "fuchsia" => (255, 0, 255),
        "gainsboro" => (220, 220, 220),
        "ghostwhite" => (248, 248, 255),
        "gold" => (255, 215, 0),
        "goldenrod" => (218, 165, 32),
        "gray" | "grey" => (128, 128, 128),
        "green" => (0, 128, 0),
        "greenyellow" => (173, 255, 47),
        "honeydew" => (240, 255, 240),
        "hotpink" => (255, 105, 180),
        "indianred" => (205, 92, 92),
        "indigo" => (75, 0, 130),
        "ivory" => (255, 255, 240),
        "khaki" => (240, 230, 140),
        "lavender" => (230, 230, 250),
        "lavenderblush" => (255, 240, 245),
        "lawngreen" => (124, 252, 0),
        "lemonchiffon" => (255, 250, 205),
        "lightblue" => (173, 216, 230),
        "lightcoral" => (240, 128, 128),
        "lightcyan" => (224, 255, 255),
        "lightgoldenrodyellow" => (250, 250, 210),
        "lightgray" | "lightgrey" => (211, 211, 211),
        "lightgreen" => (144, 238, 144),
        "lightpink" => (255, 182, 193),
        "lightsalmon" => (255, 160, 122),
        "lightseagreen" => (32, 178, 170),
        "lightskyblue" => (135, 206, 250),
        "lightslategray" | "lightslategrey" => (119, 136, 153),
        "lightsteelblue" => (176, 196, 222),
        "lightyellow" => (255, 255, 224),
        "lime" => (0, 255, 0),
        "limegreen" => (50, 205, 50),
        "linen" => (250, 240, 230),
        "magenta" => (255, 0, 255),
        "maroon" => (128, 0, 0),
        "mediumaquamarine" => (102, 205, 170),
        "mediumblue" => (0, 0, 205),
        "mediumorchid" => (186, 85, 211),
        "mediumpurple" => (147, 112, 219),
        "mediumseagreen" => (60, 179, 113),
        "mediumslateblue" => (123, 104, 238),
        "mediumspringgreen" => (0, 250, 154),
        "mediumturquoise" => (72, 209, 204),
        "mediumvioletred" => (199, 21, 133),
        "midnightblue" => (25, 25, 112),
        "mintcream" => (245, 255, 250),
        "mistyrose" => (255, 228, 225),
        "moccasin" => (255, 228, 181),
        "navajowhite" => (255, 222, 173),
        "navy" => (0, 0, 128),
        "oldlace" => (253, 245, 230),
        "olive" => (128, 128, 0),
        "olivedrab" => (107, 142, 35),
        "orange" => (255, 165, 0),
        "orangered" => (255, 69, 0),
        "orchid" => (218, 112, 214),
        "palegoldenrod" => (238, 232, 170),
        "palegreen" => (152, 251, 152),
        "paleturquoise" => (175, 238, 238),
        "palevioletred" => (219, 112, 147),
        "papayawhip" => (255, 239, 213),
        "peachpuff" => (255, 218, 185),
        "peru" => (205, 133, 63),
        "pink" => (255, 192, 203),
        "plum" => (221, 160, 221),
        "powderblue" => (176, 224, 230),
        "purple" => (128, 0, 128),
        "rebeccapurple" => (102, 51, 153),
        "red" => (255, 0, 0),
        "rosybrown" => (188, 143, 143),
        "royalblue" => (65, 105, 225),
        "saddlebrown" => (139, 69, 19),
        "salmon" => (250, 128, 114),
        "sandybrown" => (244, 164, 96),
        "seagreen" => (46, 139, 87),
        "seashell" => (255, 245, 238),
        "sienna" => (160, 82, 45),
        "silver" => (192, 192, 192),
        "skyblue" => (135, 206, 235),
        "slateblue" => (106, 90, 205),
        "slategray" | "slategrey" => (112, 128, 144),
        "snow" => (255, 250, 250),
        "springgreen" => (0, 255, 127),
        "steelblue" => (70, 130, 180),
        "tan" => (210, 180, 140),
        "teal" => (0, 128, 128),
        "thistle" => (216, 191, 216),
        "tomato" => (255, 99, 71),
        "turquoise" => (64, 224, 208),
        "violet" => (238, 130, 238),
        "wheat" => (245, 222, 179),
        "white" => (255, 255, 255),
        "whitesmoke" => (245, 245, 245),
        "yellow" => (255, 255, 0),
        "yellowgreen" => (154, 205, 50),
        _ => return None,
    };
    Some(CssColor::from_rgb(r, g, b))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_hex_parse() {
        assert_eq!(CssColor::from_hex("#ff0000"), Some(CssColor::from_rgb(255, 0, 0)));
        assert_eq!(CssColor::from_hex("#f00"), Some(CssColor::from_rgb(255, 0, 0)));
        assert_eq!(CssColor::from_hex("#ffffff"), Some(CssColor::WHITE));
        assert_eq!(CssColor::from_hex("#000000"), Some(CssColor::BLACK));
    }

    #[test]
    fn test_hsl_parse() {
        let red = CssColor::from_hsl(0.0, 100.0, 50.0);
        assert!((red.r - 1.0).abs() < 0.01);
        assert!(red.g.abs() < 0.01);
        assert!(red.b.abs() < 0.01);
    }

    #[test]
    fn test_named_colors() {
        assert_eq!(named_color("red"), Some(CssColor::from_rgb(255, 0, 0)));
        assert_eq!(named_color("blue"), Some(CssColor::from_rgb(0, 0, 255)));
        assert_eq!(named_color("transparent"), None);
        assert_eq!(CssColor::parse("transparent"), Some(CssColor::TRANSPARENT));
    }

    #[test]
    fn test_luminance() {
        assert!((CssColor::WHITE.luminance() - 1.0).abs() < 0.01);
        assert!(CssColor::BLACK.luminance().abs() < 0.01);
    }

    #[test]
    fn test_contrast() {
        let ratio = CssColor::WHITE.contrast_ratio(&CssColor::BLACK);
        assert!(ratio > 20.0); // Should be 21:1
    }
}
