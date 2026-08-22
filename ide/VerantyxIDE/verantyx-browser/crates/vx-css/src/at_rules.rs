//! CSS At-rules — @layer, @keyframes, @font-face, @import, @supports, @counter-style

/// @layer statement definition
#[derive(Debug, Clone)]
pub struct LayerStatement {
    pub names: Vec<String>,
}

/// @counter-style rule
#[derive(Debug, Clone)]
pub struct CounterStyle {
    pub name: String,
    pub system: CounterSystem,
    pub symbols: Vec<String>,
    pub additive_symbols: Vec<(u32, String)>,
    pub negative: Option<(String, String)>,
    pub prefix: String,
    pub suffix: String,
    pub range: CounterRange,
    pub pad: Option<(u32, String)>,
    pub fallback: String,
    pub speak_as: SpeakAs,
}

#[derive(Debug, Clone, PartialEq)]
pub enum CounterSystem {
    Cyclic, Numeric, Alphabetic, Symbolic, Additive, Fixed(u32), Extends(String),
}

#[derive(Debug, Clone)]
pub enum CounterRange {
    Auto,
    Ranges(Vec<(i32, i32)>),
    Infinite,
}

#[derive(Debug, Clone)]
pub enum SpeakAs {
    Auto, Bullets, Numbers, Words, SpellOut, Custom(String),
}

/// Format a counter value using a counter style
pub fn format_counter(value: i32, style: &str) -> String {
    match style {
        "decimal" => value.to_string(),
        "decimal-leading-zero" => format!("{:02}", value),
        "lower-alpha" | "lower-latin" => int_to_alpha(value, false),
        "upper-alpha" | "upper-latin" => int_to_alpha(value, true),
        "lower-roman" => to_roman(value, false),
        "upper-roman" => to_roman(value, true),
        "lower-greek" => int_to_greek(value),
        "disc" => "•".to_string(),
        "circle" => "◦".to_string(),
        "square" => "▪".to_string(),
        "none" => String::new(),
        _ => value.to_string(),
    }
}

fn int_to_alpha(mut n: i32, upper: bool) -> String {
    if n <= 0 { return n.to_string(); }
    let mut result = String::new();
    while n > 0 {
        n -= 1;
        let c = (b'a' + (n % 26) as u8) as char;
        result.insert(0, if upper { c.to_uppercase().next().unwrap() } else { c });
        n /= 26;
    }
    result
}

fn to_roman(n: i32, upper: bool) -> String {
    if n <= 0 { return n.to_string(); }
    let vals = [(1000, "m"), (900, "cm"), (500, "d"), (400, "cd"),
                (100, "c"), (90, "xc"), (50, "l"), (40, "xl"),
                (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")];
    let mut result = String::new();
    let mut n = n;
    for (val, sym) in &vals {
        while n >= *val {
            result.push_str(sym);
            n -= val;
        }
    }
    if upper { result.to_uppercase() } else { result }
}

fn int_to_greek(n: i32) -> String {
    let letters = ["α","β","γ","δ","ε","ζ","η","θ","ι","κ","λ","μ",
                   "ν","ξ","ο","π","ρ","σ","τ","υ","φ","χ","ψ","ω"];
    if n >= 1 && n <= letters.len() as i32 {
        letters[(n-1) as usize].to_string()
    } else {
        n.to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_decimal() {
        assert_eq!(format_counter(1, "decimal"), "1");
        assert_eq!(format_counter(42, "decimal"), "42");
    }

    #[test]
    fn test_roman() {
        assert_eq!(format_counter(4, "upper-roman"), "IV");
        assert_eq!(format_counter(9, "upper-roman"), "IX");
        assert_eq!(format_counter(1994, "upper-roman"), "MCMXCIV");
    }

    #[test]
    fn test_alpha() {
        assert_eq!(format_counter(1, "lower-alpha"), "a");
        assert_eq!(format_counter(26, "lower-alpha"), "z");
        assert_eq!(format_counter(27, "lower-alpha"), "aa");
    }
}
