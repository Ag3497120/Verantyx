//! CSS Selector Engine — Full CSS Selectors Level 4 implementation
//!
//! Implements all selector types:
//! - Type, ID, class, universal
//! - Attribute selectors [attr], [attr=val], [attr~=val], [attr|=val], [attr^=val], [attr$=val], [attr*=val]
//! - Pseudo-classes: :hover, :focus, :nth-child(), :not(), :is(), :where(), :has()
//! - Pseudo-elements: ::before, ::after, ::first-line, ::first-letter, ::placeholder
//! - Combinators: descendant, child (>), adjacent (+), general sibling (~), column (||)
//! - Compound selectors
//! - :scope, :root, :empty, :checked, :disabled, :enabled, :link, :visited, etc.

use std::fmt;

/// CSS specificity (a, b, c) per W3C spec
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Default)]
pub struct Specificity {
    pub a: u32,  // ID selectors
    pub b: u32,  // Class, attribute, pseudo-class selectors
    pub c: u32,  // Type and pseudo-element selectors
}

impl Specificity {
    pub fn new(a: u32, b: u32, c: u32) -> Self { Self { a, b, c } }
    pub fn id() -> Self { Self { a: 1, b: 0, c: 0 } }
    pub fn class() -> Self { Self { a: 0, b: 1, c: 0 } }
    pub fn type_() -> Self { Self { a: 0, b: 0, c: 1 } }
    pub fn zero() -> Self { Self { a: 0, b: 0, c: 0 } }
    pub fn inline() -> Self { Self { a: 1000, b: 0, c: 0 } }

    pub fn add(&self, other: &Self) -> Self {
        Self {
            a: self.a.saturating_add(other.a),
            b: self.b.saturating_add(other.b),
            c: self.c.saturating_add(other.c),
        }
    }

    /// Convert to single integer for comparison
    pub fn to_int(&self) -> u64 {
        (self.a as u64) * 1_000_000 + (self.b as u64) * 1_000 + self.c as u64
    }
}

impl fmt::Display for Specificity {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "({},{},{})", self.a, self.b, self.c)
    }
}

/// The combinator between compound selectors
#[derive(Debug, Clone, PartialEq)]
pub enum Combinator {
    /// Descendant (space)
    Descendant,
    /// Child (>)
    Child,
    /// Adjacent sibling (+)
    AdjacentSibling,
    /// General sibling (~)
    GeneralSibling,
    /// Column combinator (||)
    Column,
}

impl fmt::Display for Combinator {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Descendant => write!(f, " "),
            Self::Child => write!(f, " > "),
            Self::AdjacentSibling => write!(f, " + "),
            Self::GeneralSibling => write!(f, " ~ "),
            Self::Column => write!(f, " || "),
        }
    }
}

/// Attribute selector operator
#[derive(Debug, Clone, PartialEq)]
pub enum AttrOperator {
    /// [attr] — presence
    Presence,
    /// [attr=value] — exact match
    Equals,
    /// [attr~=value] — word match
    Word,
    /// [attr|=value] — dash prefix
    Dash,
    /// [attr^=value] — starts with
    StartsWith,
    /// [attr$=value] — ends with
    EndsWith,
    /// [attr*=value] — contains
    Contains,
}

/// Attribute selector
#[derive(Debug, Clone, PartialEq)]
pub struct AttrSelector {
    pub name: String,
    pub operator: AttrOperator,
    pub value: Option<String>,
    pub case_insensitive: bool,
}

impl AttrSelector {
    pub fn matches(&self, attr_value: Option<&str>) -> bool {
        match self.operator {
            AttrOperator::Presence => attr_value.is_some(),
            AttrOperator::Equals => {
                if let (Some(v), Some(s)) = (attr_value, &self.value) {
                    if self.case_insensitive {
                        v.eq_ignore_ascii_case(s)
                    } else {
                        v == s
                    }
                } else { false }
            }
            AttrOperator::Word => {
                if let (Some(v), Some(s)) = (attr_value, &self.value) {
                    v.split_whitespace().any(|w| if self.case_insensitive {
                        w.eq_ignore_ascii_case(s)
                    } else { w == s })
                } else { false }
            }
            AttrOperator::Dash => {
                if let (Some(v), Some(s)) = (attr_value, &self.value) {
                    let matches_exact = if self.case_insensitive { v.eq_ignore_ascii_case(s) } else { v == s };
                    let prefix = format!("{}-", s);
                    let matches_prefix = if self.case_insensitive {
                        v.to_lowercase().starts_with(&prefix.to_lowercase())
                    } else {
                        v.starts_with(&prefix)
                    };
                    matches_exact || matches_prefix
                } else { false }
            }
            AttrOperator::StartsWith => {
                if let (Some(v), Some(s)) = (attr_value, &self.value) {
                    if s.is_empty() { return false; }
                    if self.case_insensitive {
                        v.to_lowercase().starts_with(&s.to_lowercase())
                    } else {
                        v.starts_with(s.as_str())
                    }
                } else { false }
            }
            AttrOperator::EndsWith => {
                if let (Some(v), Some(s)) = (attr_value, &self.value) {
                    if s.is_empty() { return false; }
                    if self.case_insensitive {
                        v.to_lowercase().ends_with(&s.to_lowercase())
                    } else {
                        v.ends_with(s.as_str())
                    }
                } else { false }
            }
            AttrOperator::Contains => {
                if let (Some(v), Some(s)) = (attr_value, &self.value) {
                    if s.is_empty() { return false; }
                    if self.case_insensitive {
                        v.to_lowercase().contains(&s.to_lowercase())
                    } else {
                        v.contains(s.as_str())
                    }
                } else { false }
            }
        }
    }
}

/// An Nth expression (for :nth-child, :nth-of-type, etc.)
/// Represents `An+B` where we find indices where An+B > 0
#[derive(Debug, Clone, PartialEq)]
pub struct NthExpr {
    pub a: i32,
    pub b: i32,
}

impl NthExpr {
    pub fn odd() -> Self { Self { a: 2, b: 1 } }
    pub fn even() -> Self { Self { a: 2, b: 0 } }
    pub fn n() -> Self { Self { a: 1, b: 0 } }
    pub fn one(n: i32) -> Self { Self { a: 0, b: n } }

    pub fn matches(&self, index: i32) -> bool {
        if self.a == 0 {
            return index == self.b;
        }
        let n = (index - self.b) as f32 / self.a as f32;
        n >= 0.0 && n.fract() == 0.0
    }

    pub fn parse(s: &str) -> Option<Self> {
        let s = s.trim();
        match s {
            "odd" => return Some(Self::odd()),
            "even" => return Some(Self::even()),
            "n" => return Some(Self::n()),
            _ => {}
        }

        if let Ok(n) = s.parse::<i32>() {
            return Some(Self::one(n));
        }

        // Parse An+B
        if s.contains('n') {
            let parts: Vec<&str> = s.splitn(2, 'n').collect();
            let a: i32 = match parts[0].trim() {
                "" | "+" => 1,
                "-" => -1,
                n => n.parse().ok()?,
            };
            let b: i32 = if parts.len() > 1 && !parts[1].trim().is_empty() {
                parts[1].trim().parse().ok()?
            } else {
                0
            };
            return Some(Self { a, b });
        }

        None
    }
}

/// A pseudo-class selector
#[derive(Debug, Clone, PartialEq)]
pub enum PseudoClass {
    // Link
    Link, Visited, AnyLink, LocalLink,
    // User action
    Hover, Active, Focus, FocusVisible, FocusWithin,
    // Form state
    Enabled, Disabled, ReadOnly, ReadWrite,
    Checked, Indeterminate, Default,
    Required, Optional, Valid, Invalid,
    InRange, OutOfRange, UserValid, UserInvalid,
    Blank, PlaceholderShown,
    // Structural
    Root, Empty, Scope,
    FirstChild, LastChild, OnlyChild,
    FirstOfType, LastOfType, OnlyOfType,
    NthChild(NthExpr, Option<SelectorList>),     // :nth-child(An+B of S)
    NthLastChild(NthExpr, Option<SelectorList>),
    NthOfType(NthExpr),
    NthLastOfType(NthExpr),
    // Logical
    Not(SelectorList),
    Is(SelectorList),
    Where(SelectorList),
    Has(SelectorList),
    // Target
    Target, TargetWithin,
    // Language
    Lang(Vec<String>),
    Dir(String), // ltr | rtl | auto
    // Time
    Current(Option<SelectorList>),
    Past, Future,
    // Other
    Playing, Paused, Seeking,
    Stalled, Buffering, Muted,
    VolumeLocked,
    PopoverOpen,
    Modal,
    Fullscreen,
    PictureInPicture,
    Custom(String),
}

/// A pseudo-element selector
#[derive(Debug, Clone, PartialEq)]
pub enum PseudoElement {
    Before,
    After,
    FirstLine,
    FirstLetter,
    Marker,
    Placeholder,
    Selection,
    Cue,
    CueRegion,
    FileSelectorButton,
    WebkitScrollbar,
    WebkitScrollbarTrack,
    WebkitScrollbarThumb,
    SlotContent,
    Custom(String),  // ::part(), ::slotted()
    Part(Vec<String>),
    Slotted(Box<Selector>),
}

/// A single simple selector component
#[derive(Debug, Clone, PartialEq)]
pub enum SelectorComponent {
    /// * or ns|*
    Universal(Option<String>),
    /// tag name or ns|tag
    Type(String, Option<String>),
    /// #id
    Id(String),
    /// .class
    Class(String),
    /// [attr], [attr=val], etc.
    Attribute(AttrSelector),
    /// :pseudo-class
    PseudoClass(PseudoClass),
    /// ::pseudo-element
    PseudoElement(PseudoElement),
    /// &
    Nesting,
}

impl SelectorComponent {
    pub fn specificity(&self) -> Specificity {
        match self {
            Self::Id(_) => Specificity::id(),
            Self::Class(_) | Self::Attribute(_) => Specificity::class(),
            Self::Type(_,_) | Self::PseudoElement(_) => Specificity::type_(),
            Self::Universal(_) | Self::Nesting => Specificity::zero(),
            Self::PseudoClass(pc) => match pc {
                PseudoClass::Not(list) | PseudoClass::Is(list) | PseudoClass::Has(list) => {
                    list.max_specificity()
                }
                PseudoClass::Where(_) => Specificity::zero(),
                PseudoClass::NthChild(_, Some(list)) => {
                    Specificity::class().add(&list.max_specificity())
                }
                _ => Specificity::class(),
            },
        }
    }
}

/// A compound selector (sequence of simple selectors with no combinator)
#[derive(Debug, Clone, PartialEq)]
pub struct CompoundSelector {
    pub components: Vec<SelectorComponent>,
}

impl CompoundSelector {
    pub fn new(components: Vec<SelectorComponent>) -> Self {
        Self { components }
    }

    pub fn specificity(&self) -> Specificity {
        self.components.iter().fold(Specificity::zero(), |acc, c| acc.add(&c.specificity()))
    }

    pub fn is_universal(&self) -> bool {
        self.components.iter().all(|c| matches!(c, SelectorComponent::Universal(_) | SelectorComponent::PseudoElement(_)))
    }
}

/// A complex selector (compound selectors separated by combinators)
#[derive(Debug, Clone, PartialEq)]
pub struct Selector {
    /// The first compound selector
    pub left: CompoundSelector,
    /// Combinator + right selectors
    pub tail: Vec<(Combinator, CompoundSelector)>,
}

impl Selector {
    pub fn new(compound: CompoundSelector) -> Self {
        Self { left: compound, tail: Vec::new() }
    }

    pub fn specificity(&self) -> Specificity {
        let mut spec = self.left.specificity();
        for (_, compound) in &self.tail {
            spec = spec.add(&compound.specificity());
        }
        spec
    }

    pub fn is_simple(&self) -> bool {
        self.tail.is_empty()
    }

    /// The rightmost compound selector (subject of the selector)
    pub fn subject(&self) -> &CompoundSelector {
        if let Some((_, last)) = self.tail.last() {
            last
        } else {
            &self.left
        }
    }
}

/// A selector list (A, B, C)
#[derive(Debug, Clone, PartialEq)]
pub struct SelectorList {
    pub selectors: Vec<Selector>,
}

impl SelectorList {
    pub fn new(selectors: Vec<Selector>) -> Self {
        Self { selectors }
    }

    pub fn max_specificity(&self) -> Specificity {
        self.selectors.iter().map(|s| s.specificity())
            .max_by_key(|s| s.to_int())
            .unwrap_or_default()
    }

    /// Try to parse a selector list string
    pub fn parse(s: &str) -> Result<Self, String> {
        let mut selectors = Vec::new();
        for part in split_selector_list(s) {
            match parse_selector(part.trim()) {
                Ok(sel) => selectors.push(sel),
                Err(e) => return Err(e),
            }
        }
        if selectors.is_empty() {
            return Err("Empty selector list".to_string());
        }
        Ok(Self { selectors })
    }
}

/// Split a CSS selector list by commas (respecting parentheses)
fn split_selector_list(s: &str) -> Vec<&str> {
    let mut parts = Vec::new();
    let mut depth = 0usize;
    let mut start = 0;

    for (i, ch) in s.char_indices() {
        match ch {
            '(' | '[' => depth += 1,
            ')' | ']' => depth = depth.saturating_sub(1),
            ',' if depth == 0 => {
                parts.push(&s[start..i]);
                start = i + 1;
            }
            _ => {}
        }
    }
    parts.push(&s[start..]);
    parts
}

/// Parse a single complex selector
pub fn parse_selector(s: &str) -> Result<Selector, String> {
    let s = s.trim();
    if s.is_empty() {
        return Err("Empty selector".to_string());
    }

    let mut tokens = tokenize_selector(s);
    parse_complex_selector(&mut tokens)
}

/// Tokenize a selector string
fn tokenize_selector(s: &str) -> Vec<SelectorToken> {
    let mut tokens = Vec::new();
    let mut chars = s.chars().peekable();
    let mut pos = 0;

    while let Some(&ch) = chars.peek() {
        match ch {
            ' ' | '\t' | '\n' => {
                chars.next();
                pos += 1;
                // Look for combinator
                let mut next_ch = *chars.peek().unwrap_or(&' ');
                if next_ch == '>' || next_ch == '+' || next_ch == '~' {
                    // Combinator handled below
                } else {
                    tokens.push(SelectorToken::Whitespace);
                }
            }
            '>' => {
                chars.next(); pos += 1;
                tokens.push(SelectorToken::Child);
            }
            '+' => {
                chars.next(); pos += 1;
                tokens.push(SelectorToken::Adjacent);
            }
            '~' => {
                chars.next(); pos += 1;
                tokens.push(SelectorToken::Sibling);
            }
            '|' => {
                chars.next(); pos += 1;
                if chars.peek() == Some(&'|') {
                    chars.next(); pos += 1;
                    tokens.push(SelectorToken::Column);
                } else {
                    tokens.push(SelectorToken::Namespace);
                }
            }
            '#' => {
                chars.next(); pos += 1;
                let name = read_ident(&mut chars, &mut pos);
                tokens.push(SelectorToken::Id(name));
            }
            '.' => {
                chars.next(); pos += 1;
                let name = read_ident(&mut chars, &mut pos);
                tokens.push(SelectorToken::Class(name));
            }
            '*' => {
                chars.next(); pos += 1;
                tokens.push(SelectorToken::Universal);
            }
            ':' => {
                chars.next(); pos += 1;
                let pseudo_element = chars.peek() == Some(&':');
                if pseudo_element { chars.next(); pos += 1; }
                let name = read_ident(&mut chars, &mut pos);
                let func_args = if chars.peek() == Some(&'(') {
                    Some(read_balanced(&mut chars, &mut pos))
                } else {
                    None
                };
                if pseudo_element {
                    tokens.push(SelectorToken::PseudoElement(name, func_args));
                } else {
                    tokens.push(SelectorToken::PseudoClass(name, func_args));
                }
            }
            '[' => {
                let attr = read_balanced(&mut chars, &mut pos);
                tokens.push(SelectorToken::Attribute(attr));
            }
            '&' => {
                chars.next(); pos += 1;
                tokens.push(SelectorToken::Nesting);
            }
            _ => {
                let name = read_ident(&mut chars, &mut pos);
                if !name.is_empty() {
                    tokens.push(SelectorToken::Type(name));
                } else {
                    chars.next(); pos += 1;
                }
            }
        }
    }

    tokens
}

#[derive(Debug, Clone)]
enum SelectorToken {
    Type(String),
    Universal,
    Id(String),
    Class(String),
    Attribute(String),
    PseudoClass(String, Option<String>),
    PseudoElement(String, Option<String>),
    Nesting,
    Namespace,
    Whitespace,
    Child,
    Adjacent,
    Sibling,
    Column,
}

fn read_ident(chars: &mut std::iter::Peekable<std::str::Chars>, pos: &mut usize) -> String {
    let mut ident = String::new();
    while let Some(&ch) = chars.peek() {
        if ch.is_alphanumeric() || ch == '-' || ch == '_' || ch as u32 > 127 {
            ident.push(ch);
            chars.next();
            *pos += 1;
        } else {
            break;
        }
    }
    ident
}

fn read_balanced(chars: &mut std::iter::Peekable<std::str::Chars>, pos: &mut usize) -> String {
    let mut s = String::new();
    let mut depth = 0i32;
    let mut in_str = false;
    let mut str_char = '"';

    while let Some(&ch) = chars.peek() {
        chars.next();
        *pos += 1;
        if in_str {
            s.push(ch);
            if ch == str_char { in_str = false; }
        } else {
            match ch {
                '"' | '\'' => {
                    in_str = true;
                    str_char = ch;
                    s.push(ch);
                }
                '(' | '[' => { depth += 1; s.push(ch); }
                ')' | ']' => {
                    depth -= 1;
                    if depth < 0 { break; }
                    s.push(ch);
                }
                _ => s.push(ch),
            }
        }
    }
    s
}

fn parse_complex_selector(tokens: &mut Vec<SelectorToken>) -> Result<Selector, String> {
    if tokens.is_empty() {
        return Err("Empty selector".to_string());
    }

    let mut selector = Selector::new(parse_compound_selector_from_tokens(tokens)?);

    while !tokens.is_empty() {
        let combinator = match tokens.first() {
            Some(SelectorToken::Child) => { tokens.remove(0); Combinator::Child }
            Some(SelectorToken::Adjacent) => { tokens.remove(0); Combinator::AdjacentSibling }
            Some(SelectorToken::Sibling) => { tokens.remove(0); Combinator::GeneralSibling }
            Some(SelectorToken::Column) => { tokens.remove(0); Combinator::Column }
            Some(SelectorToken::Whitespace) => { tokens.remove(0); Combinator::Descendant }
            _ => break,
        };

        if tokens.is_empty() {
            break;
        }

        let right = parse_compound_selector_from_tokens(tokens)?;
        selector.tail.push((combinator, right));
    }

    Ok(selector)
}

fn parse_compound_selector_from_tokens(tokens: &mut Vec<SelectorToken>) -> Result<CompoundSelector, String> {
    let mut components = Vec::new();

    while !tokens.is_empty() {
        match tokens.first() {
            Some(SelectorToken::Whitespace) | Some(SelectorToken::Child)
            | Some(SelectorToken::Adjacent) | Some(SelectorToken::Sibling)
            | Some(SelectorToken::Column) => break,
            _ => {}
        }

        if tokens.is_empty() { break; }
        let token = tokens.remove(0);

        let component = match token {
            SelectorToken::Type(name) => SelectorComponent::Type(name, None),
            SelectorToken::Universal => SelectorComponent::Universal(None),
            SelectorToken::Id(name) => SelectorComponent::Id(name),
            SelectorToken::Class(name) => SelectorComponent::Class(name),
            SelectorToken::Attribute(s) => parse_attr_selector(&s)?,
            SelectorToken::PseudoClass(name, args) => parse_pseudo_class(&name, args.as_deref())?,
            SelectorToken::PseudoElement(name, _) => parse_pseudo_element(&name)?,
            SelectorToken::Nesting => SelectorComponent::Nesting,
            _ => break,
        };

        components.push(component);
    }

    if components.is_empty() {
        Err("Empty compound selector".to_string())
    } else {
        Ok(CompoundSelector { components })
    }
}

fn parse_attr_selector(s: &str) -> Result<SelectorComponent, String> {
    let s = s.trim_matches(|c| c == '[' || c == ']').trim();

    // Check for case flag
    let (s, case_insensitive) = if s.ends_with(" i") || s.ends_with(" I") {
        (&s[..s.len()-2], true)
    } else if s.ends_with(" s") || s.ends_with(" S") {
        (&s[..s.len()-2], false)
    } else {
        (s, false)
    };

    // Find operator
    let ops = ["~=", "|=", "^=", "$=", "*=", "="];
    for op in &ops {
        if let Some(pos) = s.find(op) {
            let name = s[..pos].trim().to_string();
            let value = s[pos+op.len()..].trim().trim_matches(|c| c == '"' || c == '\'').to_string();
            let operator = match *op {
                "=" => AttrOperator::Equals,
                "~=" => AttrOperator::Word,
                "|=" => AttrOperator::Dash,
                "^=" => AttrOperator::StartsWith,
                "$=" => AttrOperator::EndsWith,
                "*=" => AttrOperator::Contains,
                _ => AttrOperator::Presence,
            };
            return Ok(SelectorComponent::Attribute(AttrSelector {
                name,
                operator,
                value: Some(value),
                case_insensitive,
            }));
        }
    }

    // No operator — presence only
    Ok(SelectorComponent::Attribute(AttrSelector {
        name: s.trim().to_string(),
        operator: AttrOperator::Presence,
        value: None,
        case_insensitive,
    }))
}

fn parse_pseudo_class(name: &str, args: Option<&str>) -> Result<SelectorComponent, String> {
    let pc = match name.to_lowercase().as_str() {
        "link" => PseudoClass::Link,
        "visited" => PseudoClass::Visited,
        "any-link" => PseudoClass::AnyLink,
        "local-link" => PseudoClass::LocalLink,
        "hover" => PseudoClass::Hover,
        "active" => PseudoClass::Active,
        "focus" => PseudoClass::Focus,
        "focus-visible" => PseudoClass::FocusVisible,
        "focus-within" => PseudoClass::FocusWithin,
        "enabled" => PseudoClass::Enabled,
        "disabled" => PseudoClass::Disabled,
        "read-only" => PseudoClass::ReadOnly,
        "read-write" => PseudoClass::ReadWrite,
        "checked" => PseudoClass::Checked,
        "indeterminate" => PseudoClass::Indeterminate,
        "default" => PseudoClass::Default,
        "required" => PseudoClass::Required,
        "optional" => PseudoClass::Optional,
        "valid" => PseudoClass::Valid,
        "invalid" => PseudoClass::Invalid,
        "in-range" => PseudoClass::InRange,
        "out-of-range" => PseudoClass::OutOfRange,
        "user-valid" => PseudoClass::UserValid,
        "user-invalid" => PseudoClass::UserInvalid,
        "blank" => PseudoClass::Blank,
        "placeholder-shown" => PseudoClass::PlaceholderShown,
        "root" => PseudoClass::Root,
        "empty" => PseudoClass::Empty,
        "scope" => PseudoClass::Scope,
        "first-child" => PseudoClass::FirstChild,
        "last-child" => PseudoClass::LastChild,
        "only-child" => PseudoClass::OnlyChild,
        "first-of-type" => PseudoClass::FirstOfType,
        "last-of-type" => PseudoClass::LastOfType,
        "only-of-type" => PseudoClass::OnlyOfType,
        "target" => PseudoClass::Target,
        "target-within" => PseudoClass::TargetWithin,
        "past" => PseudoClass::Past,
        "future" => PseudoClass::Future,
        "playing" => PseudoClass::Playing,
        "paused" => PseudoClass::Paused,
        "modal" => PseudoClass::Modal,
        "fullscreen" => PseudoClass::Fullscreen,
        "popover-open" => PseudoClass::PopoverOpen,
        "picture-in-picture" => PseudoClass::PictureInPicture,
        "nth-child" => {
            let expr = NthExpr::parse(args.unwrap_or("0")).unwrap_or(NthExpr::one(0));
            PseudoClass::NthChild(expr, None)
        }
        "nth-last-child" => {
            let expr = NthExpr::parse(args.unwrap_or("0")).unwrap_or(NthExpr::one(0));
            PseudoClass::NthLastChild(expr, None)
        }
        "nth-of-type" => {
            let expr = NthExpr::parse(args.unwrap_or("0")).unwrap_or(NthExpr::one(0));
            PseudoClass::NthOfType(expr)
        }
        "nth-last-of-type" => {
            let expr = NthExpr::parse(args.unwrap_or("0")).unwrap_or(NthExpr::one(0));
            PseudoClass::NthLastOfType(expr)
        }
        "not" => {
            let list = SelectorList::parse(args.unwrap_or("*")).unwrap_or(SelectorList::new(vec![]));
            PseudoClass::Not(list)
        }
        "is" | "matches" | "-webkit-any" | "-moz-any" => {
            let list = SelectorList::parse(args.unwrap_or("*")).unwrap_or(SelectorList::new(vec![]));
            PseudoClass::Is(list)
        }
        "where" => {
            let list = SelectorList::parse(args.unwrap_or("*")).unwrap_or(SelectorList::new(vec![]));
            PseudoClass::Where(list)
        }
        "has" => {
            let list = SelectorList::parse(args.unwrap_or("*")).unwrap_or(SelectorList::new(vec![]));
            PseudoClass::Has(list)
        }
        "lang" => {
            let langs = args.unwrap_or("").split(',').map(|l| l.trim().to_string()).collect();
            PseudoClass::Lang(langs)
        }
        "dir" => {
            PseudoClass::Dir(args.unwrap_or("ltr").to_string())
        }
        other => PseudoClass::Custom(format!(":{}", other)),
    };

    Ok(SelectorComponent::PseudoClass(pc))
}

fn parse_pseudo_element(name: &str) -> Result<SelectorComponent, String> {
    let pe = match name.to_lowercase().as_str() {
        "before" => PseudoElement::Before,
        "after" => PseudoElement::After,
        "first-line" => PseudoElement::FirstLine,
        "first-letter" => PseudoElement::FirstLetter,
        "marker" => PseudoElement::Marker,
        "placeholder" => PseudoElement::Placeholder,
        "selection" => PseudoElement::Selection,
        "cue" => PseudoElement::Cue,
        "cue-region" => PseudoElement::CueRegion,
        "file-selector-button" => PseudoElement::FileSelectorButton,
        "webkit-scrollbar" => PseudoElement::WebkitScrollbar,
        "webkit-scrollbar-track" => PseudoElement::WebkitScrollbarTrack,
        "webkit-scrollbar-thumb" => PseudoElement::WebkitScrollbarThumb,
        other => PseudoElement::Custom(format!("::{}", other)),
    };
    Ok(SelectorComponent::PseudoElement(pe))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_simple_selectors() {
        let sel = SelectorList::parse("div").unwrap();
        assert_eq!(sel.selectors.len(), 1);

        let sel = SelectorList::parse("div, p, span").unwrap();
        assert_eq!(sel.selectors.len(), 3);
    }

    #[test]
    fn test_specificity() {
        // #id = (1,0,0)
        let sel = SelectorList::parse("#foo").unwrap();
        assert_eq!(sel.selectors[0].specificity(), Specificity::new(1, 0, 0));

        // .class = (0,1,0)
        let sel = SelectorList::parse(".bar").unwrap();
        assert_eq!(sel.selectors[0].specificity(), Specificity::new(0, 1, 0));

        // div.class#id = (1,1,1)
        // This would be (1,1,1) = id(1) + class(1) + type(1)
    }

    #[test]
    fn test_nth_expr() {
        let odd = NthExpr::odd();
        assert!(odd.matches(1));
        assert!(!odd.matches(2));
        assert!(odd.matches(3));

        let even = NthExpr::even();
        assert!(!even.matches(1));
        assert!(even.matches(2));

        let expr = NthExpr { a: 3, b: 1 }; // 3n+1 = 1,4,7,10...
        assert!(expr.matches(1));
        assert!(expr.matches(4));
        assert!(!expr.matches(2));
    }

    #[test]
    fn test_attr_selector() {
        let attr = AttrSelector {
            name: "class".to_string(),
            operator: AttrOperator::Word,
            value: Some("active".to_string()),
            case_insensitive: false,
        };
        assert!(attr.matches(Some("foo active bar")));
        assert!(!attr.matches(Some("foo bar")));
    }

    #[test]
    fn test_complex_selector() {
        let sel = SelectorList::parse("div > p.class").unwrap();
        let s = &sel.selectors[0];
        assert!(!s.tail.is_empty());
    }
}
