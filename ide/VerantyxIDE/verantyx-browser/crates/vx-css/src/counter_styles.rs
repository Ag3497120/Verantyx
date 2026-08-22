//! CSS Counters & @counter-style — W3C CSS Lists & Counters Level 3
//!
//! Implements:
//!   - CSS counter() and counters() functional notation
//!   - Counter scope (nesting with counters() separator)
//!   - counter-reset, counter-increment, counter-set properties
//!   - @counter-style at-rule descriptors:
//!       system: cyclic, numeric, alphabetic, symbolic, additive, fixed, extends
//!       symbols: (literal or url())
//!       additive-symbols: <weight> <symbol> pairs
//!       negative: (prefix, suffix)
//!       prefix, suffix
//!       pad: (minimum length, pad char)
//!       fallback: <ident>
//!       range: auto | <range>+
//!       speak-as: auto | bullets | numbers | words | spell-out
//!   - Built-in counter styles: decimal, decimal-leading-zero, lower-roman, upper-roman,
//!       lower-latin, upper-latin, lower-alpha, upper-alpha, lower-greek,
//!       disc, circle, square, none, cjk-decimal, hiragana, katakana, hebrew
//!   - Counter inheritance and element scoping

use std::collections::HashMap;

/// @counter-style system
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CounterSystem {
    Cyclic,
    Numeric,
    Alphabetic,
    Symbolic,
    Additive,
    Fixed(i32),        // starts at N
    Extends(String),   // extends another counter style
}

/// The speak-as descriptor for accessibility
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SpeakAs {
    Auto,
    Bullets,
    Numbers,
    Words,
    SpellOut,
    CustomIdent(String),
}

/// An additive symbol entry (weight, symbol)
#[derive(Debug, Clone)]
pub struct AdditiveSymbol {
    pub weight: u32,
    pub symbol: String,
}

/// A fully defined @counter-style rule
#[derive(Debug, Clone)]
pub struct CounterStyle {
    pub name: String,
    pub system: CounterSystem,
    pub symbols: Vec<String>,
    pub additive_symbols: Vec<AdditiveSymbol>,
    pub negative_prefix: String,
    pub negative_suffix: String,
    pub prefix: String,
    pub suffix: String,
    pub pad_min_length: usize,
    pub pad_char: String,
    pub fallback: String,
    pub range: CounterRange,
    pub speak_as: SpeakAs,
}

#[derive(Debug, Clone, PartialEq)]
pub enum CounterRange {
    Auto,
    Bounds(Vec<(i32, i32)>),   // (min, max) pairs
}

impl CounterStyle {
    /// Convert a counter value to its string representation for this style
    pub fn counter_to_string(&self, value: i32, styles: &CounterStyleRegistry) -> String {
        // Check range
        if !self.in_range(value) {
            return self.fallback_string(value, styles);
        }

        let abs_value = value.unsigned_abs() as usize;

        let raw = match &self.system {
            CounterSystem::Cyclic => {
                if self.symbols.is_empty() { return "•".to_string(); }
                let idx = (abs_value.saturating_sub(1)) % self.symbols.len();
                self.symbols[idx].clone()
            }
            CounterSystem::Numeric => {
                if self.symbols.is_empty() { return value.to_string(); }
                Self::to_numeric_system(abs_value, &self.symbols)
            }
            CounterSystem::Alphabetic => {
                if self.symbols.is_empty() { return value.to_string(); }
                Self::to_alphabetic_system(abs_value, &self.symbols)
            }
            CounterSystem::Symbolic => {
                if self.symbols.is_empty() { return "•".to_string(); }
                let idx = (abs_value.saturating_sub(1)) % self.symbols.len();
                let repeat_count = (abs_value.saturating_sub(1)) / self.symbols.len() + 1;
                self.symbols[idx].repeat(repeat_count)
            }
            CounterSystem::Additive => {
                Self::to_additive_system(abs_value, &self.additive_symbols)
                    .unwrap_or_else(|| self.fallback_string(value, styles))
            }
            CounterSystem::Fixed(start) => {
                let offset = value - start;
                if offset >= 0 && (offset as usize) < self.symbols.len() {
                    self.symbols[offset as usize].clone()
                } else {
                    return self.fallback_string(value, styles);
                }
            }
            CounterSystem::Extends(base_name) => {
                if let Some(base) = styles.get(base_name) {
                    return base.counter_to_string(value, styles);
                }
                return value.to_string();
            }
        };

        // Apply negative sign
        let with_sign = if value < 0 {
            format!("{}{}{}", self.negative_prefix, raw, self.negative_suffix)
        } else {
            raw
        };

        // Apply padding
        let padded = if with_sign.len() < self.pad_min_length {
            let pad_count = self.pad_min_length - with_sign.len();
            format!("{}{}", self.pad_char.repeat(pad_count), with_sign)
        } else {
            with_sign
        };

        // Apply prefix/suffix
        format!("{}{}{}", self.prefix, padded, self.suffix)
    }

    fn in_range(&self, value: i32) -> bool {
        match &self.range {
            CounterRange::Auto => {
                match &self.system {
                    CounterSystem::Cyclic | CounterSystem::Numeric |
                    CounterSystem::Alphabetic | CounterSystem::Symbolic => true,
                    CounterSystem::Additive | CounterSystem::Fixed(_) => value >= 0,
                    _ => true,
                }
            }
            CounterRange::Bounds(ranges) => {
                ranges.iter().any(|(min, max)| value >= *min && value <= *max)
            }
        }
    }

    fn fallback_string(&self, value: i32, styles: &CounterStyleRegistry) -> String {
        if let Some(fallback) = styles.get(&self.fallback) {
            fallback.counter_to_string(value, styles)
        } else {
            value.to_string()
        }
    }

    /// Convert using a numeric positional system (like decimal, but customizable base)
    fn to_numeric_system(value: usize, symbols: &[String]) -> String {
        if value == 0 { return symbols[0].clone(); }
        let base = symbols.len();
        let mut n = value;
        let mut digits = Vec::new();
        while n > 0 {
            digits.push(symbols[n % base].clone());
            n /= base;
        }
        digits.iter().rev().cloned().collect()
    }

    /// Convert using an alphabetic counting system (like a, b, c → aa, ab)
    fn to_alphabetic_system(value: usize, symbols: &[String]) -> String {
        if value == 0 { return String::new(); }
        let base = symbols.len();
        let mut n = value;
        let mut chars = Vec::new();
        while n > 0 {
            n -= 1;
            chars.push(symbols[n % base].clone());
            n /= base;
        }
        chars.iter().rev().cloned().collect()
    }

    /// Convert using an additive system (like roman numerals)
    fn to_additive_system(value: usize, pairs: &[AdditiveSymbol]) -> Option<String> {
        if pairs.is_empty() { return None; }
        let mut remaining = value;
        let mut result = String::new();
        for pair in pairs {
            if pair.weight == 0 { break; }
            while remaining >= pair.weight as usize {
                result.push_str(&pair.symbol);
                remaining -= pair.weight as usize;
            }
        }
        if remaining == 0 { Some(result) } else { None }
    }
}

/// Built-in counter style registry
pub struct CounterStyleRegistry {
    styles: HashMap<String, CounterStyle>,
}

impl CounterStyleRegistry {
    pub fn new() -> Self {
        let mut reg = Self { styles: HashMap::new() };
        reg.register_builtins();
        reg
    }

    pub fn get(&self, name: &str) -> Option<&CounterStyle> {
        self.styles.get(name)
    }

    pub fn register(&mut self, style: CounterStyle) {
        self.styles.insert(style.name.clone(), style);
    }

    fn make(name: &str, system: CounterSystem, symbols: Vec<&str>, prefix: &str, suffix: &str) -> CounterStyle {
        CounterStyle {
            name: name.to_string(),
            system,
            symbols: symbols.into_iter().map(String::from).collect(),
            additive_symbols: Vec::new(),
            negative_prefix: "-".to_string(),
            negative_suffix: String::new(),
            prefix: prefix.to_string(),
            suffix: suffix.to_string(),
            pad_min_length: 0,
            pad_char: "0".to_string(),
            fallback: "decimal".to_string(),
            range: CounterRange::Auto,
            speak_as: SpeakAs::Auto,
        }
    }

    fn make_additive(name: &str, pairs: Vec<(u32, &str)>) -> CounterStyle {
        CounterStyle {
            name: name.to_string(),
            system: CounterSystem::Additive,
            symbols: Vec::new(),
            additive_symbols: pairs.into_iter().map(|(w, s)| AdditiveSymbol { weight: w, symbol: s.to_string() }).collect(),
            negative_prefix: "-".to_string(),
            negative_suffix: String::new(),
            prefix: String::new(),
            suffix: ". ".to_string(),
            pad_min_length: 0,
            pad_char: "0".to_string(),
            fallback: "decimal".to_string(),
            range: CounterRange::Bounds(vec![(1, 3999)]),
            speak_as: SpeakAs::Numbers,
        }
    }

    fn register_builtins(&mut self) {
        // decimal
        self.styles.insert("decimal".to_string(), CounterStyle {
            name: "decimal".to_string(),
            system: CounterSystem::Numeric,
            symbols: vec!["0","1","2","3","4","5","6","7","8","9"].into_iter().map(String::from).collect(),
            additive_symbols: Vec::new(),
            negative_prefix: "-".to_string(), negative_suffix: String::new(),
            prefix: String::new(), suffix: ". ".to_string(),
            pad_min_length: 0, pad_char: "0".to_string(),
            fallback: "decimal".to_string(),
            range: CounterRange::Auto, speak_as: SpeakAs::Numbers,
        });

        // decimal-leading-zero
        let mut dlz = self.styles["decimal"].clone();
        dlz.name = "decimal-leading-zero".to_string();
        dlz.pad_min_length = 2;
        self.styles.insert("decimal-leading-zero".to_string(), dlz);

        // lower-latin / lower-alpha
        let lower_alpha = Self::make("lower-latin", CounterSystem::Alphabetic,
            vec!["a","b","c","d","e","f","g","h","i","j","k","l","m",
                 "n","o","p","q","r","s","t","u","v","w","x","y","z"],
            "", ". ");
        self.styles.insert("lower-latin".to_string(), lower_alpha.clone());
        self.styles.insert("lower-alpha".to_string(), lower_alpha);

        // upper-latin / upper-alpha
        let upper_alpha = Self::make("upper-latin", CounterSystem::Alphabetic,
            vec!["A","B","C","D","E","F","G","H","I","J","K","L","M",
                 "N","O","P","Q","R","S","T","U","V","W","X","Y","Z"],
            "", ". ");
        self.styles.insert("upper-latin".to_string(), upper_alpha.clone());
        self.styles.insert("upper-alpha".to_string(), upper_alpha);

        // lower-roman
        let lower_roman = Self::make_additive("lower-roman", vec![
            (1000,"m"),(900,"cm"),(500,"d"),(400,"cd"),(100,"c"),
            (90,"xc"),(50,"l"),(40,"xl"),(10,"x"),(9,"ix"),
            (5,"v"),(4,"iv"),(1,"i"),
        ]);
        self.styles.insert("lower-roman".to_string(), lower_roman);

        // upper-roman
        let upper_roman = Self::make_additive("upper-roman", vec![
            (1000,"M"),(900,"CM"),(500,"D"),(400,"CD"),(100,"C"),
            (90,"XC"),(50,"L"),(40,"XL"),(10,"X"),(9,"IX"),
            (5,"V"),(4,"IV"),(1,"I"),
        ]);
        self.styles.insert("upper-roman".to_string(), upper_roman);

        // lower-greek
        let lower_greek = Self::make("lower-greek", CounterSystem::Alphabetic,
            vec!["α","β","γ","δ","ε","ζ","η","θ","ι","κ","λ","μ",
                 "ν","ξ","ο","π","ρ","σ","τ","υ","φ","χ","ψ","ω"],
            "", ". ");
        self.styles.insert("lower-greek".to_string(), lower_greek);

        // disc, circle, square (list markers)
        self.styles.insert("disc".to_string(), Self::make("disc", CounterSystem::Cyclic, vec!["•"], "", " "));
        self.styles.insert("circle".to_string(), Self::make("circle", CounterSystem::Cyclic, vec!["◦"], "", " "));
        self.styles.insert("square".to_string(), Self::make("square", CounterSystem::Cyclic, vec!["▪"], "", " "));

        // none
        self.styles.insert("none".to_string(), CounterStyle {
            name: "none".to_string(),
            system: CounterSystem::Cyclic,
            symbols: vec![String::new()],
            additive_symbols: Vec::new(),
            negative_prefix: String::new(), negative_suffix: String::new(),
            prefix: String::new(), suffix: String::new(),
            pad_min_length: 0, pad_char: String::new(),
            fallback: "none".to_string(),
            range: CounterRange::Auto, speak_as: SpeakAs::Bullets,
        });

        // cjk-decimal
        let cjk = Self::make("cjk-decimal", CounterSystem::Numeric,
            vec!["〇","一","二","三","四","五","六","七","八","九"], "", "、");
        self.styles.insert("cjk-decimal".to_string(), cjk);

        // hiragana
        let hiragana = Self::make("hiragana", CounterSystem::Alphabetic,
            vec!["あ","い","う","え","お","か","き","く","け","こ",
                 "さ","し","す","せ","そ","た","ち","つ","て","と",
                 "な","に","ぬ","ね","の","は","ひ","ふ","へ","ほ",
                 "ま","み","む","め","も","や","ゆ","よ","ら","り",
                 "る","れ","ろ","わ","ゐ","ゑ","を"],
            "", "、");
        self.styles.insert("hiragana".to_string(), hiragana);

        // katakana
        let katakana = Self::make("katakana", CounterSystem::Alphabetic,
            vec!["ア","イ","ウ","エ","オ","カ","キ","ク","ケ","コ",
                 "サ","シ","ス","セ","ソ","タ","チ","ツ","テ","ト",
                 "ナ","ニ","ヌ","ネ","ノ","ハ","ヒ","フ","ヘ","ホ",
                 "マ","ミ","ム","メ","モ","ヤ","ユ","ヨ","ラ","リ",
                 "ル","レ","ロ","ワ","ヲ"],
            "", "、");
        self.styles.insert("katakana".to_string(), katakana);
    }
}

/// Per-element CSS counter state
#[derive(Debug, Clone, Default)]
pub struct CounterScope {
    /// counter name -> current value
    counters: HashMap<String, i32>,
}

impl CounterScope {
    pub fn get(&self, name: &str) -> i32 {
        self.counters.get(name).copied().unwrap_or(0)
    }

    pub fn reset(&mut self, name: &str, value: i32) {
        self.counters.insert(name.to_string(), value);
    }

    pub fn increment(&mut self, name: &str, amount: i32) {
        *self.counters.entry(name.to_string()).or_insert(0) += amount;
    }

    pub fn set(&mut self, name: &str, value: i32) {
        self.counters.insert(name.to_string(), value);
    }
}

/// Per-document counter manager (manages scope chain per element tree)
pub struct CounterManager {
    pub registry: CounterStyleRegistry,
    /// Stack of counter scopes (element → scope)
    scopes: Vec<(u64, CounterScope)>,   // (node_id, scope)
}

impl CounterManager {
    pub fn new() -> Self {
        Self {
            registry: CounterStyleRegistry::new(),
            scopes: Vec::new(),
        }
    }

    pub fn push_scope(&mut self, node_id: u64) {
        self.scopes.push((node_id, CounterScope::default()));
    }

    pub fn pop_scope(&mut self) {
        self.scopes.pop();
    }

    pub fn reset_counter(&mut self, name: &str, value: i32) {
        if let Some((_, scope)) = self.scopes.last_mut() {
            scope.reset(name, value);
        }
    }

    pub fn increment_counter(&mut self, name: &str, amount: i32) {
        // Find nearest ancestor scope that has this counter or the current scope
        for (_, scope) in self.scopes.iter_mut().rev() {
            if scope.counters.contains_key(name) {
                scope.increment(name, amount);
                return;
            }
        }
        // Not found — create in current scope
        if let Some((_, scope)) = self.scopes.last_mut() {
            scope.increment(name, amount);
        }
    }

    pub fn set_counter(&mut self, name: &str, value: i32) {
        for (_, scope) in self.scopes.iter_mut().rev() {
            if scope.counters.contains_key(name) {
                scope.set(name, value);
                return;
            }
        }
        if let Some((_, scope)) = self.scopes.last_mut() {
            scope.set(name, value);
        }
    }

    /// Resolve counter(name, style) — returns the formatted counter string
    pub fn resolve_counter(&self, name: &str, style_name: &str) -> String {
        // Find nearest scope with this counter
        let value = self.scopes.iter().rev()
            .find_map(|(_, scope)| scope.counters.get(name).copied())
            .unwrap_or(0);

        let style = self.registry.get(style_name).or_else(|| self.registry.get("decimal"));
        if let Some(s) = style {
            s.counter_to_string(value, &self.registry)
        } else {
            value.to_string()
        }
    }

    /// Resolve counters(name, separator, style) — concatenates all nested counter values
    pub fn resolve_counters(&self, name: &str, separator: &str, style_name: &str) -> String {
        let values: Vec<i32> = self.scopes.iter()
            .filter_map(|(_, scope)| scope.counters.get(name).copied())
            .collect();

        let style = self.registry.get(style_name).or_else(|| self.registry.get("decimal"));
        if let Some(s) = style {
            values.iter()
                .map(|&v| s.counter_to_string(v, &self.registry))
                .collect::<Vec<_>>()
                .join(separator)
        } else {
            values.iter().map(|v| v.to_string()).collect::<Vec<_>>().join(separator)
        }
    }
}
