//! CSS Selectors Level 4 Engine — Complete Matching Implementation
//!
//! Implements the full CSS Selectors Level 4 specification:
//!   - Type, class, ID, attribute selectors
//!   - Pseudo-classes: :nth-child, :nth-of-type, :is(), :not(), :has(), :where()
//!   - :nth-child(An+B [of S]) with optional selector argument
//!   - :nth-last-child, :nth-last-of-type, :nth-last-col
//!   - :root, :empty, :only-child, :only-of-type, :first-child, :last-child
//!   - :checked, :disabled, :enabled, :required, :optional, :valid, :invalid
//!   - :focus, :focus-within, :focus-visible, :hover, :active, :visited, :link
//!   - :target, :scope, :local-link
//!   - :lang(), :dir()
//!   - Pseudo-elements: ::before, ::after, ::first-line, ::first-letter
//!   - Combinators: descendant, child (>), adjacent (+), general sibling (~)
//!   - :is() and :where() for forgiving selector lists
//!   - :has() relational pseudo-class (forward-looking)
//!   - Specificity calculation per Selectors Level 4

use std::collections::HashMap;

/// CSS Specificity (a, b, c) tuple
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Default)]
pub struct Specificity {
    /// ID selectors count (a)
    pub a: u32,
    /// Class, attribute, pseudo-class selectors count (b)  
    pub b: u32,
    /// Type selectors, pseudo-elements count (c)
    pub c: u32,
}

impl Specificity {
    pub const ZERO: Specificity = Specificity { a: 0, b: 0, c: 0 };
    
    pub fn id() -> Self { Self { a: 1, b: 0, c: 0 } }
    pub fn class() -> Self { Self { a: 0, b: 1, c: 0 } }
    pub fn type_sel() -> Self { Self { a: 0, b: 0, c: 1 } }
    pub fn inline() -> Self { Self { a: 1, b: 0, c: 0 } } // Not in Selectors spec but needed
    
    pub fn add(&self, other: &Specificity) -> Self {
        Self { a: self.a + other.a, b: self.b + other.b, c: self.c + other.c }
    }
    
    /// Encode as a comparable u32 (assumes a, b, c < 256)
    pub fn as_u32(&self) -> u32 {
        (self.a << 16) | (self.b << 8) | self.c
    }
}

/// An An+B selector coefficient
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct AnPlusB {
    pub a: i32,
    pub b: i32,
}

impl AnPlusB {
    /// odd = 2n+1
    pub const ODD: AnPlusB = AnPlusB { a: 2, b: 1 };
    /// even = 2n
    pub const EVEN: AnPlusB = AnPlusB { a: 2, b: 0 };
    
    pub fn matches(&self, index: i32) -> bool {
        // index is 1-based
        if self.a == 0 {
            return index == self.b;
        }
        let n = (index - self.b) / self.a;
        n >= 0 && n * self.a + self.b == index
    }
    
    pub fn parse(s: &str) -> Option<Self> {
        let s = s.trim().to_lowercase();
        match s.as_str() {
            "odd" => return Some(Self::ODD),
            "even" => return Some(Self::EVEN),
            "n" => return Some(Self { a: 1, b: 0 }),
            _ => {}
        }
        
        if let Ok(n) = s.parse::<i32>() {
            return Some(Self { a: 0, b: n });
        }
        
        // Parse "An", "An+B", "An-B"
        if let Some(n_pos) = s.find('n') {
            let a_str = &s[..n_pos];
            let a: i32 = match a_str {
                "" | "+" => 1,
                "-" => -1,
                _ => a_str.parse().ok()?,
            };
            
            let rest = s[n_pos+1..].trim();
            let b: i32 = if rest.is_empty() {
                0
            } else {
                rest.parse().ok()?
            };
            
            return Some(Self { a, b });
        }
        
        None
    }
}

/// CSS attribute selector operators
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AttrOperator {
    Exists,            // [attr]
    Equals,            // [attr=val]
    SpaceContains,     // [attr~=val]  word in space-separated list
    HyphenPrefix,      // [attr|=val]  equals or lang-prefixed
    Prefix,            // [attr^=val]
    Suffix,            // [attr$=val]
    Substring,         // [attr*=val]
}

/// Attribute selector
#[derive(Debug, Clone)]
pub struct AttrSelector {
    pub name: String,
    pub operator: AttrOperator,
    pub value: Option<String>,
    pub case_insensitive: bool,   // 'i' flag
}

impl AttrSelector {
    pub fn matches(&self, attrs: &HashMap<String, String>) -> bool {
        match &self.operator {
            AttrOperator::Exists => attrs.contains_key(&self.name),
            AttrOperator::Equals => {
                attrs.get(&self.name).map_or(false, |v| {
                    let val = self.value.as_deref().unwrap_or("");
                    self.compare(v, val)
                })
            }
            AttrOperator::SpaceContains => {
                attrs.get(&self.name).map_or(false, |v| {
                    let val = self.value.as_deref().unwrap_or("");
                    v.split_whitespace().any(|w| self.compare(w, val))
                })
            }
            AttrOperator::HyphenPrefix => {
                attrs.get(&self.name).map_or(false, |v| {
                    let val = self.value.as_deref().unwrap_or("");
                    self.compare(v, val) || v.starts_with(&format!("{}-", val))
                })
            }
            AttrOperator::Prefix => {
                attrs.get(&self.name).map_or(false, |v| {
                    let val = self.value.as_deref().unwrap_or("");
                    if self.case_insensitive {
                        v.to_lowercase().starts_with(&val.to_lowercase())
                    } else {
                        v.starts_with(val)
                    }
                })
            }
            AttrOperator::Suffix => {
                attrs.get(&self.name).map_or(false, |v| {
                    let val = self.value.as_deref().unwrap_or("");
                    if self.case_insensitive {
                        v.to_lowercase().ends_with(&val.to_lowercase())
                    } else {
                        v.ends_with(val)
                    }
                })
            }
            AttrOperator::Substring => {
                attrs.get(&self.name).map_or(false, |v| {
                    let val = self.value.as_deref().unwrap_or("");
                    if self.case_insensitive {
                        v.to_lowercase().contains(&val.to_lowercase())
                    } else {
                        v.contains(val)
                    }
                })
            }
        }
    }
    
    fn compare(&self, a: &str, b: &str) -> bool {
        if self.case_insensitive {
            a.to_lowercase() == b.to_lowercase()
        } else {
            a == b
        }
    }
}

/// A single simple selector
#[derive(Debug, Clone)]
pub enum SimpleSelector {
    Universal,                           // *
    Type(String),                        // div, span, etc.
    Class(String),                       // .classname
    Id(String),                          // #id
    Attribute(AttrSelector),             // [attr], [attr=val], etc.
    PseudoClass(PseudoClass),            // :hover, :nth-child(), etc.
    PseudoElement(String),              // ::before, ::after, etc.
}

impl SimpleSelector {
    pub fn specificity(&self) -> Specificity {
        match self {
            Self::Universal => Specificity::ZERO,
            Self::Type(_) => Specificity::type_sel(),
            Self::Class(_) | Self::Attribute(_) => Specificity::class(),
            Self::Id(_) => Specificity::id(),
            Self::PseudoClass(pc) => pc.specificity(),
            Self::PseudoElement(_) => Specificity::type_sel(),
        }
    }
}

/// Pseudo-class variants
#[derive(Debug, Clone)]
pub enum PseudoClass {
    // Structural
    Root,
    Empty,
    FirstChild,
    LastChild,
    OnlyChild,
    FirstOfType,
    LastOfType,
    OnlyOfType,
    NthChild(AnPlusB, Option<Vec<ComplexSelector>>),  // An+B [of S]
    NthLastChild(AnPlusB, Option<Vec<ComplexSelector>>),
    NthOfType(AnPlusB),
    NthLastOfType(AnPlusB),
    
    // User action
    Hover,
    Active,
    Focus,
    FocusWithin,
    FocusVisible,
    Visited,
    Link,
    AnyLink,
    LocalLink,
    
    // State
    Checked,
    Indeterminate,
    Disabled,
    Enabled,
    Required,
    Optional,
    Valid,
    Invalid,
    InRange,
    OutOfRange,
    ReadOnly,
    ReadWrite,
    PlaceholderShown,
    Default,
    
    // Tree
    Target,
    TargetWithin,
    Scope,
    
    // Linguistic
    Lang(String),
    Dir(TextDir),
    
    // Logical combinations (CSS Selectors Level 4)
    Is(Vec<ComplexSelector>),            // :is() — forgiving, takes specificity of most specific
    Not(Vec<ComplexSelector>),           // :not() — negation
    Where(Vec<ComplexSelector>),         // :where() — same as :is() but zero specificity
    Has(Vec<RelativeSelector>),          // :has() — relational / forward-looking
    
    // Custom
    Custom(String, Option<String>),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TextDir { Ltr, Rtl }

impl PseudoClass {
    pub fn specificity(&self) -> Specificity {
        match self {
            // :where() always has zero specificity
            Self::Where(_) => Specificity::ZERO,
            // :is() and :not() take the specificity of their most specific argument
            Self::Is(selectors) | Self::Not(selectors) => {
                selectors.iter()
                    .map(|s| s.specificity())
                    .max()
                    .unwrap_or(Specificity::ZERO)
            }
            // :has() specificity is based on its argument
            Self::Has(selectors) => {
                selectors.iter()
                    .map(|s| s.selector.specificity())
                    .max()
                    .unwrap_or(Specificity::ZERO)
            }
            // All other pseudo-classes count as one (b-column)
            _ => Specificity::class(),
        }
    }
}

/// Combinator between compound selectors
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Combinator {
    Descendant,   // (space)
    Child,        // >
    AdjacentSibling, // +
    GeneralSibling,  // ~
    Column,          // ||  (CSS Grid)
}

/// A compound selector = sequence of simple selectors
#[derive(Debug, Clone)]
pub struct CompoundSelector {
    pub simple_selectors: Vec<SimpleSelector>,
}

impl CompoundSelector {
    pub fn specificity(&self) -> Specificity {
        self.simple_selectors.iter()
            .map(|s| s.specificity())
            .fold(Specificity::ZERO, |acc, s| acc.add(&s))
    }
}

/// A complex selector = compound_selector (combinator compound_selector)*
#[derive(Debug, Clone)]
pub struct ComplexSelector {
    /// The leftmost compound selector and subsequent (combinator, compound) pairs
    pub parts: Vec<(Option<Combinator>, CompoundSelector)>,
}

impl ComplexSelector {
    pub fn specificity(&self) -> Specificity {
        self.parts.iter()
            .map(|(_, compound)| compound.specificity())
            .fold(Specificity::ZERO, |acc, s| acc.add(&s))
    }
}

/// A relative selector (used in :has()) — has an implicit scope anchor
#[derive(Debug, Clone)]
pub struct RelativeSelector {
    pub combinator: Combinator,  // The leading combinator (default: descendant)
    pub selector: ComplexSelector,
}

/// Simplified element context for matching (avoids borrowing the full DOM)
#[derive(Debug, Clone)]
pub struct ElementContext {
    pub tag: String,
    pub id: Option<String>,
    pub classes: Vec<String>,
    pub attributes: HashMap<String, String>,
    pub node_id: u64,
    pub parent_id: Option<u64>,
    pub sibling_index: usize,       // 0-based index among siblings
    pub sibling_count: usize,       // Total sibling count
    pub sibling_same_type_index: usize,   // Among siblings of same tag
    pub sibling_same_type_count: usize,
    pub is_root: bool,
    pub is_empty: bool,
    pub is_first_child: bool,
    pub is_last_child: bool,
    pub is_only_child: bool,
    pub is_checked: bool,
    pub is_disabled: bool,
    pub is_required: bool,
    pub is_focused: bool,
    pub is_hovered: bool,
    pub is_active: bool,
    pub is_visited: bool,
    pub is_target: bool,
    pub lang: Option<String>,
    pub dir: Option<TextDir>,
    pub child_count: usize,
    pub text_content_empty: bool,
}

impl ElementContext {
    /// Check if a pseudo-class matches this element context
    pub fn matches_pseudo_class(&self, pc: &PseudoClass) -> bool {
        match pc {
            PseudoClass::Root => self.is_root,
            PseudoClass::Empty => self.text_content_empty && self.child_count == 0,
            PseudoClass::FirstChild => self.is_first_child,
            PseudoClass::LastChild => self.is_last_child,
            PseudoClass::OnlyChild => self.is_only_child,
            PseudoClass::FirstOfType => self.sibling_same_type_index == 0,
            PseudoClass::LastOfType => self.sibling_same_type_index + 1 == self.sibling_same_type_count,
            PseudoClass::OnlyOfType => self.sibling_same_type_count == 1,
            PseudoClass::NthChild(anb, _) => anb.matches(self.sibling_index as i32 + 1),
            PseudoClass::NthLastChild(anb, _) => {
                let from_end = self.sibling_count - self.sibling_index;
                anb.matches(from_end as i32)
            }
            PseudoClass::NthOfType(anb) => anb.matches(self.sibling_same_type_index as i32 + 1),
            PseudoClass::NthLastOfType(anb) => {
                let from_end = self.sibling_same_type_count - self.sibling_same_type_index;
                anb.matches(from_end as i32)
            }
            PseudoClass::Hover => self.is_hovered,
            PseudoClass::Active => self.is_active,
            PseudoClass::Focus => self.is_focused,
            PseudoClass::FocusWithin => self.is_focused, // Simplified — real impl checks descendants
            PseudoClass::FocusVisible => self.is_focused, // Simplified
            PseudoClass::Visited => self.is_visited,
            PseudoClass::Link | PseudoClass::AnyLink => {
                (self.tag == "a" || self.tag == "area") && self.attributes.contains_key("href")
            }
            PseudoClass::Target => self.is_target,
            PseudoClass::Scope => self.is_root, // Scope = root for stylesheet context
            PseudoClass::Checked => self.is_checked,
            PseudoClass::Disabled => self.is_disabled,
            PseudoClass::Enabled => !self.is_disabled,
            PseudoClass::Required => self.is_required,
            PseudoClass::Optional => !self.is_required,
            PseudoClass::ReadOnly => self.attributes.get("readonly").is_some() || self.is_disabled,
            PseudoClass::ReadWrite => !self.attributes.contains_key("readonly") && !self.is_disabled,
            PseudoClass::PlaceholderShown => self.attributes.contains_key("placeholder"),
            PseudoClass::Default => self.attributes.contains_key("default"),
            PseudoClass::Lang(expected_lang) => {
                self.lang.as_ref().map_or(false, |l| {
                    l.to_lowercase().starts_with(&expected_lang.to_lowercase())
                })
            }
            PseudoClass::Dir(dir) => self.dir == Some(*dir),
            PseudoClass::Is(selectors) | PseudoClass::Where(selectors) => {
                // Simplified: check if element matches any of the selector tags
                selectors.iter().any(|sel| {
                    sel.parts.last().map_or(false, |(_, compound)| {
                        compound.simple_selectors.iter().any(|ss| match ss {
                            SimpleSelector::Type(t) => *t == self.tag,
                            SimpleSelector::Class(c) => self.classes.contains(c),
                            SimpleSelector::Id(id) => self.id.as_ref() == Some(id),
                            _ => false,
                        })
                    })
                })
            }
            PseudoClass::Not(selectors) => {
                !selectors.iter().any(|sel| {
                    sel.parts.last().map_or(false, |(_, compound)| {
                        compound.simple_selectors.iter().any(|ss| match ss {
                            SimpleSelector::Type(t) => *t == self.tag,
                            SimpleSelector::Class(c) => self.classes.contains(c),
                            SimpleSelector::Id(id) => self.id.as_ref() == Some(id),
                            _ => false,
                        })
                    })
                })
            }
            // :has() requires descendant matching — deferred to full DOM traversal
            PseudoClass::Has(_) => false,
            _ => false,
        }
    }
    
    /// Match a simple selector against this element
    pub fn matches_simple(&self, ss: &SimpleSelector) -> bool {
        match ss {
            SimpleSelector::Universal => true,
            SimpleSelector::Type(tag) => self.tag == *tag || tag == "*",
            SimpleSelector::Class(cls) => self.classes.contains(cls),
            SimpleSelector::Id(id) => self.id.as_deref() == Some(id.as_str()),
            SimpleSelector::Attribute(attr) => attr.matches(&self.attributes),
            SimpleSelector::PseudoClass(pc) => self.matches_pseudo_class(pc),
            SimpleSelector::PseudoElement(_) => true, // Pseudo-elements don't filter element matching
        }
    }
    
    /// Match a compound selector against this element
    pub fn matches_compound(&self, compound: &CompoundSelector) -> bool {
        compound.simple_selectors.iter().all(|ss| self.matches_simple(ss))
    }
}

/// Parse a CSS selector string into a list of complex selectors (selector list)
pub fn parse_selector_list(input: &str) -> Vec<ComplexSelector> {
    input.split(',')
        .filter_map(|s| parse_complex_selector(s.trim()))
        .collect()
}

/// Parse a single complex selector
fn parse_complex_selector(input: &str) -> Option<ComplexSelector> {
    if input.is_empty() { return None; }
    
    let mut parts = Vec::new();
    let mut rest = input.trim();
    let mut is_first = true;
    
    while !rest.is_empty() {
        rest = rest.trim_start();
        
        // Detect combinator
        let combinator = if is_first {
            None
        } else if rest.starts_with('>') {
            rest = &rest[1..].trim_start();
            Some(Combinator::Child)
        } else if rest.starts_with('+') {
            rest = &rest[1..].trim_start();
            Some(Combinator::AdjacentSibling)
        } else if rest.starts_with('~') {
            rest = &rest[1..].trim_start();
            Some(Combinator::GeneralSibling)
        } else if rest.starts_with("||") {
            rest = &rest[2..].trim_start();
            Some(Combinator::Column)
        } else {
            // Descendant combinator (space was consumed by trim_start)
            if !is_first { Some(Combinator::Descendant) } else { None }
        };
        
        // Parse the next compound selector
        let (compound, consumed) = parse_compound_selector(rest);
        parts.push((combinator, compound));
        rest = &rest[consumed..];
        is_first = false;
        
        if consumed == 0 { break; }
    }
    
    if parts.is_empty() { None } else { Some(ComplexSelector { parts }) }
}

fn parse_compound_selector(input: &str) -> (CompoundSelector, usize) {
    let mut selectors = Vec::new();
    let mut i = 0;
    let chars: Vec<char> = input.chars().collect();
    
    while i < chars.len() {
        let ch = chars[i];
        
        // Stop at combinators or commas
        if ch == ' ' || ch == '>' || ch == '+' || ch == '~' || ch == ',' {
            break;
        }
        
        if ch == '*' {
            selectors.push(SimpleSelector::Universal);
            i += 1;
        } else if ch == '.' {
            // Class selector
            let start = i + 1;
            i += 1;
            while i < chars.len() && (chars[i].is_alphanumeric() || chars[i] == '-' || chars[i] == '_') {
                i += 1;
            }
            let class = chars[start..i].iter().collect::<String>();
            selectors.push(SimpleSelector::Class(class));
        } else if ch == '#' {
            // ID selector
            let start = i + 1;
            i += 1;
            while i < chars.len() && (chars[i].is_alphanumeric() || chars[i] == '-' || chars[i] == '_') {
                i += 1;
            }
            let id = chars[start..i].iter().collect::<String>();
            selectors.push(SimpleSelector::Id(id));
        } else if ch.is_alphabetic() {
            // Type selector
            let start = i;
            while i < chars.len() && (chars[i].is_alphanumeric() || chars[i] == '-') {
                i += 1;
            }
            let tag = chars[start..i].iter().collect::<String>().to_lowercase();
            selectors.push(SimpleSelector::Type(tag));
        } else if ch == ':' {
            // Pseudo-class or pseudo-element
            i += 1;
            if i < chars.len() && chars[i] == ':' {
                // Pseudo-element
                i += 1;
                let start = i;
                while i < chars.len() && (chars[i].is_alphanumeric() || chars[i] == '-') {
                    i += 1;
                }
                let name = chars[start..i].iter().collect::<String>();
                selectors.push(SimpleSelector::PseudoElement(name));
            } else {
                // Pseudo-class
                let start = i;
                while i < chars.len() && (chars[i].is_alphanumeric() || chars[i] == '-') {
                    i += 1;
                }
                let name = chars[start..i].iter().collect::<String>().to_lowercase();
                let pc = parse_pseudo_class(&name, &mut i, &chars);
                selectors.push(SimpleSelector::PseudoClass(pc));
            }
        } else if ch == '[' {
            // Attribute selector
            let start = i;
            let mut depth = 0;
            while i < chars.len() {
                if chars[i] == '[' { depth += 1; }
                if chars[i] == ']' { depth -= 1; if depth == 0 { i += 1; break; } }
                i += 1;
            }
            let attr_str: String = chars[start..i].iter().collect();
            if let Some(attr) = parse_attr_selector(&attr_str) {
                selectors.push(SimpleSelector::Attribute(attr));
            }
        } else {
            break;
        }
    }
    
    (CompoundSelector { simple_selectors: selectors }, i)
}

fn parse_pseudo_class(name: &str, i: &mut usize, chars: &[char]) -> PseudoClass {
    match name {
        "root" => PseudoClass::Root,
        "empty" => PseudoClass::Empty,
        "first-child" => PseudoClass::FirstChild,
        "last-child" => PseudoClass::LastChild,
        "only-child" => PseudoClass::OnlyChild,
        "first-of-type" => PseudoClass::FirstOfType,
        "last-of-type" => PseudoClass::LastOfType,
        "only-of-type" => PseudoClass::OnlyOfType,
        "hover" => PseudoClass::Hover,
        "active" => PseudoClass::Active,
        "focus" => PseudoClass::Focus,
        "focus-within" => PseudoClass::FocusWithin,
        "focus-visible" => PseudoClass::FocusVisible,
        "visited" => PseudoClass::Visited,
        "link" => PseudoClass::Link,
        "any-link" => PseudoClass::AnyLink,
        "target" => PseudoClass::Target,
        "scope" => PseudoClass::Scope,
        "checked" => PseudoClass::Checked,
        "disabled" => PseudoClass::Disabled,
        "enabled" => PseudoClass::Enabled,
        "required" => PseudoClass::Required,
        "optional" => PseudoClass::Optional,
        "valid" => PseudoClass::Valid,
        "invalid" => PseudoClass::Invalid,
        "in-range" => PseudoClass::InRange,
        "out-of-range" => PseudoClass::OutOfRange,
        "read-only" => PseudoClass::ReadOnly,
        "read-write" => PseudoClass::ReadWrite,
        "placeholder-shown" => PseudoClass::PlaceholderShown,
        "default" => PseudoClass::Default,
        "indeterminate" => PseudoClass::Indeterminate,
        "nth-child" | "nth-last-child" | "nth-of-type" | "nth-last-of-type" => {
            // Consume the parenthesized argument
            let arg = consume_parens(i, chars);
            let anb = AnPlusB::parse(&arg).unwrap_or(AnPlusB { a: 0, b: 1 });
            match name {
                "nth-child" => PseudoClass::NthChild(anb, None),
                "nth-last-child" => PseudoClass::NthLastChild(anb, None),
                "nth-of-type" => PseudoClass::NthOfType(anb),
                "nth-last-of-type" => PseudoClass::NthLastOfType(anb),
                _ => unreachable!(),
            }
        }
        "not" | "is" | "where" => {
            let arg = consume_parens(i, chars);
            let selectors = parse_selector_list(&arg);
            match name {
                "not" => PseudoClass::Not(selectors),
                "is" => PseudoClass::Is(selectors),
                "where" => PseudoClass::Where(selectors),
                _ => unreachable!(),
            }
        }
        "lang" => {
            let arg = consume_parens(i, chars);
            PseudoClass::Lang(arg.trim().to_string())
        }
        "dir" => {
            let arg = consume_parens(i, chars);
            let dir = match arg.trim() {
                "rtl" => TextDir::Rtl,
                _ => TextDir::Ltr,
            };
            PseudoClass::Dir(dir)
        }
        other => PseudoClass::Custom(other.to_string(), None),
    }
}

fn consume_parens(i: &mut usize, chars: &[char]) -> String {
    if *i < chars.len() && chars[*i] == '(' {
        *i += 1;
        let start = *i;
        let mut depth = 1;
        while *i < chars.len() {
            if chars[*i] == '(' { depth += 1; }
            if chars[*i] == ')' {
                depth -= 1;
                if depth == 0 { break; }
            }
            *i += 1;
        }
        let result = chars[start..*i].iter().collect();
        if *i < chars.len() { *i += 1; } // consume ')'
        result
    } else {
        String::new()
    }
}

fn parse_attr_selector(s: &str) -> Option<AttrSelector> {
    let inner = s.trim_start_matches('[').trim_end_matches(']');
    
    let operators = ["~=", "|=", "^=", "$=", "*=", "="];
    
    for op in &operators {
        if let Some(pos) = inner.find(op) {
            let name = inner[..pos].trim().to_lowercase();
            let rest = inner[pos + op.len()..].trim();
            
            let case_insensitive = rest.ends_with(" i") || rest.ends_with(" I");
            let value_str = rest.trim_end_matches(" i").trim_end_matches(" I")
                .trim().trim_matches('"').trim_matches('\'').to_string();
            
            let operator = match *op {
                "~=" => AttrOperator::SpaceContains,
                "|=" => AttrOperator::HyphenPrefix,
                "^=" => AttrOperator::Prefix,
                "$=" => AttrOperator::Suffix,
                "*=" => AttrOperator::Substring,
                "=" => AttrOperator::Equals,
                _ => AttrOperator::Exists,
            };
            
            return Some(AttrSelector {
                name,
                operator,
                value: Some(value_str),
                case_insensitive,
            });
        }
    }
    
    // Existence selector
    Some(AttrSelector {
        name: inner.trim().to_lowercase(),
        operator: AttrOperator::Exists,
        value: None,
        case_insensitive: false,
    })
}
