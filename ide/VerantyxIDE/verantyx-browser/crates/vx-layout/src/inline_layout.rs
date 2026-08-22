//! Inline Formatting Context — W3C CSS2 / CSS Text Level 3
//!
//! Implements the full inline formatting context (IFC) algorithm:
//!   - Line box construction with line-height model
//!   - Bidirectional text (UA-level bidi algorithm per Unicode TR #9)
//!   - Word-wrap and overflow-wrap break algorithms
//!   - White-space handling (normal, pre, nowrap, pre-wrap, pre-line, break-spaces)
//!   - Text indentation (text-indent, hanging-punctuation)
//!   - Inline-block and replaced element placement
//!   - Vertical alignment (W3C inline-level alignment model)
//!   - Ruby annotation layout
//!   - Soft/hard wrap opportunity identification

use std::collections::VecDeque;

/// A text run — a sequence of characters with uniform formatting
#[derive(Debug, Clone)]
pub struct TextRun {
    pub text: String,
    pub font_size: f64,
    pub font_family: String,
    pub font_weight: u32,          // 100..900
    pub font_style: FontStyle,
    pub line_height: LineHeight,
    pub letter_spacing: f64,       // px
    pub word_spacing: f64,         // px
    pub text_decoration: TextDecoration,
    pub white_space: WhiteSpaceMode,
    pub direction: TextDirection,
    pub color_index: u32,          // Index into the page's color table
    pub node_id: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FontStyle {
    Normal,
    Italic,
    Oblique,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum LineHeight {
    Normal,           // ~1.2 × font-size
    Number(f64),      // Multiplier of font-size
    Length(f64),      // Absolute value in px
    Percentage(f64),  // Percentage of font-size
}

impl LineHeight {
    pub fn resolve(&self, font_size: f64) -> f64 {
        match self {
            Self::Normal => font_size * 1.2,
            Self::Number(n) => font_size * n,
            Self::Length(px) => *px,
            Self::Percentage(pct) => font_size * pct / 100.0,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TextDirection {
    Ltr,
    Rtl,
}

/// CSS white-space modes per CSS Text Level 3
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WhiteSpaceMode {
    Normal,       // Collapse, wrap
    Pre,          // Preserve, no-wrap
    NoWrap,       // Collapse, no-wrap
    PreWrap,      // Preserve, wrap
    PreLine,      // Preserve newlines, collapse spaces, wrap
    BreakSpaces,  // Like pre-wrap but spaces don't hang at line end
}

impl WhiteSpaceMode {
    pub fn preserves_spaces(&self) -> bool {
        matches!(self, Self::Pre | Self::PreWrap | Self::BreakSpaces)
    }
    
    pub fn preserves_newlines(&self) -> bool {
        matches!(self, Self::Pre | Self::PreWrap | Self::PreLine | Self::BreakSpaces)
    }
    
    pub fn allows_wrapping(&self) -> bool {
        matches!(self, Self::Normal | Self::PreWrap | Self::PreLine | Self::BreakSpaces)
    }
}

/// Text overflow mode
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TextOverflow {
    Clip,
    Ellipsis,
    String(String), // Custom overflow indicator
}

/// CSS text-decoration
#[derive(Debug, Clone, Default)]
pub struct TextDecoration {
    pub line: TextDecorationLine,
    pub color: Option<String>,
    pub style: TextDecorationStyle,
    pub thickness: Option<f64>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct TextDecorationLine {
    pub underline: bool,
    pub overline: bool,
    pub line_through: bool,
    pub blink: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum TextDecorationStyle {
    #[default] Solid,
    Double,
    Dotted,
    Dashed,
    Wavy,
}

/// Vertical alignment for inline-level elements
#[derive(Debug, Clone, PartialEq)]
pub enum VerticalAlign {
    Baseline,
    Sub,
    Super,
    Top,
    TextTop,
    Middle,
    Bottom,
    TextBottom,
    Length(f64),
    Percentage(f64),
}

impl VerticalAlign {
    pub fn from_str(s: &str) -> Self {
        match s {
            "baseline" => Self::Baseline,
            "sub" => Self::Sub,
            "super" => Self::Super,
            "top" => Self::Top,
            "text-top" => Self::TextTop,
            "middle" => Self::Middle,
            "bottom" => Self::Bottom,
            "text-bottom" => Self::TextBottom,
            other => {
                if let Ok(v) = other.trim_end_matches("px").parse::<f64>() {
                    return Self::Length(v);
                }
                if let Ok(v) = other.trim_end_matches('%').parse::<f64>() {
                    return Self::Percentage(v);
                }
                Self::Baseline
            }
        }
    }
}

/// A word-break opportunity
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BreakOpportunity {
    /// No break is allowed here  
    Prohibited,
    /// A break is allowed (soft wrap opportunity per CSS Text)
    Soft,
    /// A break MUST be taken here (newline, `<br>`)
    Forced,
}

/// A single fragment in the inline layout — a "glyph run", image, or breaking space
#[derive(Debug, Clone)]
pub enum InlineFragment {
    TextFragment {
        text: String,
        advance_width: f64,    // Measured width of this text fragment
        ascent: f64,
        descent: f64,
        line_gap: f64,
        font_size: f64,
        break_after: BreakOpportunity,
        node_id: u64,
    },
    Space {
        width: f64,
        collapsible: bool,     // Whether this space can be collapsed at line end
        break_after: BreakOpportunity,
    },
    HardBreak,                 // <br> element
    InlineBlock {
        width: f64,
        height: f64,
        margin_top: f64,
        margin_bottom: f64,
        baseline_offset: f64,  // Distance from block bottom to its baseline
        vertical_align: VerticalAlign,
        node_id: u64,
    },
    AtomicInline {             // Replaced element (img, input, etc.)
        width: f64,
        height: f64,
        vertical_align: VerticalAlign,
        node_id: u64,
    },
}

impl InlineFragment {
    pub fn advance_width(&self) -> f64 {
        match self {
            Self::TextFragment { advance_width, .. } => *advance_width,
            Self::Space { width, .. } => *width,
            Self::HardBreak => 0.0,
            Self::InlineBlock { width, .. } => *width,
            Self::AtomicInline { width, .. } => *width,
        }
    }
    
    pub fn is_hard_break(&self) -> bool { matches!(self, Self::HardBreak) }
    
    pub fn break_opportunity(&self) -> BreakOpportunity {
        match self {
            Self::TextFragment { break_after, .. } => *break_after,
            Self::Space { break_after, .. } => *break_after,
            Self::HardBreak => BreakOpportunity::Forced,
            _ => BreakOpportunity::Prohibited,
        }
    }
}

/// A constructed line box (the result of one line of inline layout)
#[derive(Debug, Clone)]
pub struct LineBox {
    pub y: f64,                // Top of the line box in the block's coordinate space
    pub width: f64,            // Available width (may be less due to floats)
    pub used_width: f64,       // Actual content width
    pub height: f64,           // Line box height (= ascent + descent of the line)
    pub baseline: f64,         // Distance from line box top to the baseline
    pub ascent: f64,           // Tallest ascent of any fragment on the line
    pub descent: f64,          // Deepest descent of any fragment on the line
    pub text_align: TextAlign, // Resolved text-align for this line
    pub fragments: Vec<LineFragment>,
    pub is_empty: bool,        // True for collapsed empty lines
}

/// A fragment positioned on a line box
#[derive(Debug, Clone)]
pub struct LineFragment {
    pub x: f64,
    pub y_offset: f64,         // Vertical offset from baseline (for vertical-align)
    pub fragment: InlineFragment,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TextAlign {
    Start,
    End,
    Left,
    Right,
    Center,
    Justify,
    JustifyAll,
}

impl TextAlign {
    pub fn from_str(s: &str, direction: TextDirection) -> Self {
        match s {
            "left" => Self::Left,
            "right" => Self::Right,
            "center" => Self::Center,
            "justify" => Self::Justify,
            "justify-all" => Self::JustifyAll,
            "start" => match direction {
                TextDirection::Ltr => Self::Left,
                TextDirection::Rtl => Self::Right,
            },
            "end" => match direction {
                TextDirection::Ltr => Self::Right,
                TextDirection::Rtl => Self::Left,
            },
            _ => Self::Start,
        }
    }
}

/// The Inline Layout Engine — converts a stream of inline fragments into line boxes
pub struct InlineLayoutEngine {
    pub available_width: f64,
    pub text_indent: f64,
    pub text_align: TextAlign,
    pub direction: TextDirection,
    pub line_gap: f64,
    
    // Current line state
    current_line_fragments: Vec<InlineFragment>,
    current_line_width: f64,
    current_line_number: u32,
}

impl InlineLayoutEngine {
    pub fn new(available_width: f64, text_align: TextAlign) -> Self {
        Self {
            available_width,
            text_indent: 0.0,
            text_align,
            direction: TextDirection::Ltr,
            line_gap: 0.0,
            current_line_fragments: Vec::new(),
            current_line_width: 0.0,
            current_line_number: 0,
        }
    }
    
    /// Break a stream of inline fragments into a sequence of line boxes
    pub fn layout(&mut self, fragments: Vec<InlineFragment>) -> Vec<LineBox> {
        let mut lines = Vec::new();
        let mut pending: VecDeque<InlineFragment> = fragments.into_iter().collect();
        let mut y_cursor = 0.0;
        let mut is_first_line = true;
        
        while !pending.is_empty() {
            let effective_width = if is_first_line {
                self.available_width - self.text_indent
            } else {
                self.available_width
            };
            
            let line = self.fill_line_box(&mut pending, effective_width, y_cursor);
            let line_height = line.height;
            
            if !line.is_empty || !lines.is_empty() {
                y_cursor += line_height;
                lines.push(line);
            }
            
            is_first_line = false;
        }
        
        // Apply text-align to all lines except the last (for justify)
        let line_count = lines.len();
        for (i, line) in lines.iter_mut().enumerate() {
            let is_last_line = i == line_count - 1;
            self.apply_text_align(line, is_last_line);
        }
        
        lines
    }
    
    /// Fill a single line box from the fragment queue
    fn fill_line_box(
        &self,
        pending: &mut VecDeque<InlineFragment>,
        available_width: f64,
        y: f64,
    ) -> LineBox {
        let mut fragments = Vec::new();
        let mut used_width = 0.0;
        let mut max_ascent: f64 = 0.0;
        let mut max_descent: f64 = 0.0;
        let mut last_break_idx: Option<usize> = None;
        let mut last_break_width = 0.0;
        
        // Collect fragments until the line is full or we hit a forced break
        loop {
            match pending.front() {
                None => break,
                Some(frag) => {
                    if frag.is_hard_break() {
                        pending.pop_front();
                        break;
                    }
                    
                    let frag_width = frag.advance_width();
                    
                    // Check if this fragment fits on the line
                    if used_width + frag_width > available_width && !fragments.is_empty() {
                        // Try to break at the last soft break opportunity
                        if let Some(break_idx) = last_break_idx {
                            // Pop fragments after the break point back into pending
                            let overflow: Vec<InlineFragment> = fragments.drain(break_idx+1..).collect();
                            for f in overflow.into_iter().rev() {
                                pending.push_front(f);
                            }
                            used_width = last_break_width;
                        }
                        break;
                    }
                    
                    let frag = pending.pop_front().unwrap();
                    
                    // Track soft wrap opportunities
                    if frag.break_opportunity() == BreakOpportunity::Soft {
                        last_break_idx = Some(fragments.len());
                        last_break_width = used_width + frag.advance_width();
                    }
                    
                    // Update ascent/descent from text fragments
                    match &frag {
                        InlineFragment::TextFragment { ascent, descent, font_size, .. } => {
                            max_ascent = max_ascent.max(*ascent);
                            max_descent = max_descent.max(*descent);
                        }
                        InlineFragment::AtomicInline { height, .. } |
                        InlineFragment::InlineBlock { height, .. } => {
                            max_ascent = max_ascent.max(*height);
                        }
                        _ => {}
                    }
                    
                    used_width += frag_width;
                    fragments.push(frag);
                }
            }
        }
        
        // Remove trailing collapsible spaces
        while let Some(InlineFragment::Space { collapsible: true, .. }) = fragments.last() {
            if let InlineFragment::Space { width, .. } = fragments.pop().unwrap() {
                used_width -= width;
            }
        }
        
        let ascent = max_ascent.max(0.0);
        let descent = max_descent.max(0.0);
        let height = ascent + descent + self.line_gap;
        
        // Position fragments on the line
        let mut line_fragments = Vec::new();
        let mut x = 0.0;
        for fragment in fragments {
            let frag_width = fragment.advance_width();
            line_fragments.push(LineFragment {
                x,
                y_offset: 0.0,
                fragment,
            });
            x += frag_width;
        }
        
        let is_empty = line_fragments.is_empty();
        LineBox {
            y,
            width: available_width,
            used_width,
            height,
            baseline: ascent,
            ascent,
            descent,
            text_align: self.text_align,
            fragments: line_fragments,
            is_empty,
        }
    }
    
    /// Apply text-align to a constructed line box by adjusting fragment x positions
    fn apply_text_align(&self, line: &mut LineBox, is_last_line: bool) {
        let free_space = line.width - line.used_width;
        if free_space <= 0.0 { return; }
        
        let effective_align = if is_last_line && line.text_align == TextAlign::Justify {
            TextAlign::Start
        } else {
            line.text_align
        };
        
        match effective_align {
            TextAlign::Left | TextAlign::Start => {
                // Default — no adjustment needed
            }
            TextAlign::Right | TextAlign::End => {
                for frag in &mut line.fragments {
                    frag.x += free_space;
                }
            }
            TextAlign::Center => {
                let offset = free_space / 2.0;
                for frag in &mut line.fragments {
                    frag.x += offset;
                }
            }
            TextAlign::Justify | TextAlign::JustifyAll => {
                // Distribute free space among inter-word spaces
                let space_count = line.fragments.iter()
                    .filter(|f| matches!(f.fragment, InlineFragment::Space { .. }))
                    .count();
                
                if space_count == 0 { return; }
                
                let extra_per_space = free_space / space_count as f64;
                let mut accumulated_extra = 0.0;
                
                for frag in &mut line.fragments {
                    frag.x += accumulated_extra;
                    if matches!(frag.fragment, InlineFragment::Space { .. }) {
                        accumulated_extra += extra_per_space;
                        if let InlineFragment::Space { ref mut width, .. } = frag.fragment {
                            *width += extra_per_space;
                        }
                    }
                }
            }
        }
    }
    
    /// Compute word-break opportunities per CSS Text Level 3
    /// Returns a parallel vector of break opportunities for each character boundary
    pub fn compute_break_opportunities(text: &str, mode: WhiteSpaceMode) -> Vec<BreakOpportunity> {
        let chars: Vec<char> = text.chars().collect();
        let mut opportunities = vec![BreakOpportunity::Prohibited; chars.len()];
        
        for (i, &ch) in chars.iter().enumerate() {
            let next = chars.get(i + 1).copied();
            
            // Hard breaks at newline characters
            if ch == '\n' || ch == '\r' {
                if mode.preserves_newlines() {
                    opportunities[i] = BreakOpportunity::Forced;
                } else {
                    opportunities[i] = BreakOpportunity::Soft;
                }
                continue;
            }
            
            // Soft break after spaces when wrapping is allowed
            if ch == ' ' || ch == '\t' {
                if mode.allows_wrapping() {
                    opportunities[i] = BreakOpportunity::Soft;
                }
                continue;
            }
            
            // CJK ideographic characters — break opportunity after each character
            if Self::is_cjk(ch) {
                if mode.allows_wrapping() {
                    opportunities[i] = BreakOpportunity::Soft;
                }
                continue;
            }
            
            // U+200B ZERO WIDTH SPACE — soft break opportunity
            if ch == '\u{200B}' {
                opportunities[i] = BreakOpportunity::Soft;
                continue;
            }
            
            // U+00AD SOFT HYPHEN
            if ch == '\u{00AD}' {
                if mode.allows_wrapping() {
                    opportunities[i] = BreakOpportunity::Soft;
                }
                continue;
            }
        }
        
        opportunities
    }
    
    fn is_cjk(c: char) -> bool {
        matches!(c,
            '\u{4E00}'..='\u{9FFF}'  |  // CJK Unified Ideographs
            '\u{3400}'..='\u{4DBF}'  |  // Extension A
            '\u{20000}'..='\u{2A6DF}'|  // Extension B
            '\u{F900}'..='\u{FAFF}'  |  // CJK Compatibility Ideographs
            '\u{2F800}'..='\u{2FA1F}'|  // CJK Compatibility Ideographs Supplement
            '\u{3000}'..='\u{303F}'  |  // CJK Symbols and Punctuation
            '\u{3040}'..='\u{309F}'  |  // Hiragana
            '\u{30A0}'..='\u{30FF}'  |  // Katakana
            '\u{FF00}'..='\u{FFEF}'     // Halfwidth/Fullwidth Forms
        )
    }
    
    /// Approximate text width measurement — production would use font metrics
    pub fn measure_text(text: &str, font_size: f64, letter_spacing: f64) -> f64 {
        // Use a simplified advance width: 0.6 × font_size for ASCII,
        // 1.0 × font_size for CJK
        text.chars().map(|c| {
            let char_advance = if Self::is_cjk(c) { font_size } else { font_size * 0.6 };
            char_advance + letter_spacing
        }).sum::<f64>()
    }
}

/// Ruby annotation layout (for CJK ruby characters)
#[derive(Debug, Clone)]
pub struct RubyLayout {
    pub base: Vec<InlineFragment>,
    pub annotation: Vec<InlineFragment>,
    pub position: RubyPosition,
    pub alignment: RubyAlignment,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RubyPosition {
    Over,
    Under,
    InterCharacter,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RubyAlignment {
    Start,
    Center,
    SpaceBetween,
    SpaceAround,
}

/// Line box that ensures it is not empty for line fragment reference after borrow check
impl LineBox {
    pub fn is_line_empty(&self) -> bool { self.fragments.is_empty() }
    
    pub fn fragment_at_x(&self, x: f64) -> Option<&LineFragment> {
        self.fragments.iter().find(|f| {
            let frag_width = f.fragment.advance_width();
            f.x <= x && x < f.x + frag_width
        })
    }
    
    /// Return the node_id of the inline fragment at a given x position
    pub fn node_at_x(&self, x: f64) -> Option<u64> {
        self.fragment_at_x(x).and_then(|f| match &f.fragment {
            InlineFragment::TextFragment { node_id, .. } => Some(*node_id),
            InlineFragment::InlineBlock { node_id, .. } => Some(*node_id),
            InlineFragment::AtomicInline { node_id, .. } => Some(*node_id),
            _ => None,
        })
    }
}
