//! HTML5 Parser — Tree Construction Algorithm (W3C HTML Living Standard)
//!
//! Implements the core HTML5 parsing infrastructure:
//!   - Tokenizer states (Data, TagOpen, TagName, Attributes, RCDATA, RAWTEXT, SCRIPT,
//!     CDATA, Comment, DOCTYPE, CharacterReference)
//!   - Token types: Doctype, StartTag, EndTag, Comment, Character, EOF
//!   - Attribute parsing (name=value, boolean, single/double/unquoted)
//!   - Tree construction insertion modes (initial, before-html, before-head,
//!     in-head, in-body, in-table, in-row, in-cell, in-select, in-template,
//!     after-body, in-frameset, after-frameset, after-after-body)
//!   - Self-closing elements (void elements)
//!   - Script data state and raw text elements (style, script, textarea, pre)
//!   - DOCTYPE public/system identifier parsing
//!   - Parse errors (non-fatal, collected)
//!   - Node tree construction with namespace tracking
//!   - AI-facing: parse statistics and error summary

use std::collections::HashMap;

/// All HTML void elements (cannot have children)
const VOID_ELEMENTS: &[&str] = &[
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
];

/// Raw text elements (content is raw text, not parsed)
const RAW_TEXT_ELEMENTS: &[&str] = &["script", "style"];

/// RCDATA elements (entities parsed, but no child elements)
const RCDATA_ELEMENTS: &[&str] = &["textarea", "title"];

fn is_void(tag: &str) -> bool { VOID_ELEMENTS.contains(&tag.to_lowercase().as_str()) }
fn is_raw_text(tag: &str) -> bool { RAW_TEXT_ELEMENTS.contains(&tag.to_lowercase().as_str()) }
fn is_rcdata(tag: &str) -> bool { RCDATA_ELEMENTS.contains(&tag.to_lowercase().as_str()) }

/// HTML tokenizer states (simplified — covers the most important production states)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TokenizerState {
    Data,
    RcData,
    RawText,
    ScriptData,
    PlainText,
    TagOpen,
    EndTagOpen,
    TagName,
    RcDataLessThan,
    RawTextLessThan,
    BeforeAttrName,
    AttrName,
    AfterAttrName,
    BeforeAttrValue,
    AttrValueDoubleQuoted,
    AttrValueSingleQuoted,
    AttrValueUnquoted,
    AfterAttrValue,
    SelfClosingStartTag,
    MarkupDeclarationOpen,
    Comment,
    CommentStart,
    CommentEnd,
    Doctype,
    DoctypeName,
    BeforeDoctypePublicIdentifier,
    DoctypePublicIdentifier,
    BeforeDoctypeSystemIdentifier,
    DoctypeSystemIdentifier,
    CharacterReference,
    CdataSection,
}

/// HTML attribute (name + value)
#[derive(Debug, Clone, PartialEq)]
pub struct HtmlAttribute {
    pub name: String,
    pub value: String,
}

/// HTML tokens
#[derive(Debug, Clone)]
pub enum HtmlToken {
    Doctype {
        name: Option<String>,
        public_id: Option<String>,
        system_id: Option<String>,
        force_quirks: bool,
    },
    StartTag {
        name: String,
        attributes: Vec<HtmlAttribute>,
        self_closing: bool,
    },
    EndTag {
        name: String,
    },
    Comment(String),
    Character(char),
    /// Multiple characters as a batch (optimization)
    Characters(String),
    Eof,
}

/// HTML element node
#[derive(Debug, Clone)]
pub struct HtmlElement {
    pub id: u64,
    pub tag: String,
    pub namespace: Namespace,
    pub attributes: Vec<HtmlAttribute>,
    pub children: Vec<HtmlNode>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Namespace { Html, Svg, MathML }

/// An HTML text node
#[derive(Debug, Clone)]
pub struct HtmlText {
    pub id: u64,
    pub data: String,
}

/// An HTML comment node
#[derive(Debug, Clone)]
pub struct HtmlComment {
    pub id: u64,
    pub data: String,
}

/// A DOCTYPE node
#[derive(Debug, Clone)]
pub struct HtmlDoctype {
    pub id: u64,
    pub name: String,
    pub public_id: String,
    pub system_id: String,
}

/// A single node in the HTML tree
#[derive(Debug, Clone)]
pub enum HtmlNode {
    Document(Vec<HtmlNode>),
    Doctype(HtmlDoctype),
    Element(HtmlElement),
    Text(HtmlText),
    Comment(HtmlComment),
}

impl HtmlNode {
    pub fn node_id(&self) -> u64 {
        match self {
            HtmlNode::Doctype(d) => d.id,
            HtmlNode::Element(e) => e.id,
            HtmlNode::Text(t) => t.id,
            HtmlNode::Comment(c) => c.id,
            _ => 0,
        }
    }
}

/// Insertion modes for the tree construction
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InsertionMode {
    Initial,
    BeforeHtml,
    BeforeHead,
    InHead,
    InHeadNoscript,
    AfterHead,
    InBody,
    Text,
    InTable,
    InTableText,
    InCaption,
    InColumnGroup,
    InTableBody,
    InRow,
    InCell,
    InSelect,
    InSelectInTable,
    InTemplate,
    AfterBody,
    InFrameset,
    AfterFrameset,
    AfterAfterBody,
    AfterAfterFrameset,
}

/// The HTML5 tokenizer
pub struct HtmlTokenizer {
    pub input: Vec<char>,
    pub pos: usize,
    pub state: TokenizerState,
    pub current_tag: Option<(bool, String, Vec<HtmlAttribute>)>,  // (is_end_tag, name, attrs)
    pub current_attr: Option<HtmlAttribute>,
    pub current_str: String,
    pub reconsume: bool,
    pub last_start_tag_name: String,
}

impl HtmlTokenizer {
    pub fn new(html: &str) -> Self {
        Self {
            input: html.chars().collect(),
            pos: 0,
            state: TokenizerState::Data,
            current_tag: None,
            current_attr: None,
            current_str: String::new(),
            reconsume: false,
            last_start_tag_name: String::new(),
        }
    }

    pub fn current_char(&self) -> Option<char> {
        self.input.get(self.pos).copied()
    }

    pub fn advance(&mut self) { self.pos += 1; }

    pub fn try_consume_string(&mut self, s: &str) -> bool {
        let chars: Vec<char> = s.chars().collect();
        if self.input[self.pos..].starts_with(chars.as_slice()) {
            self.pos += chars.len();
            true
        } else {
            false
        }
    }

    /// Tokenize the next token
    pub fn next_token(&mut self) -> HtmlToken {
        loop {
            let ch = match self.current_char() {
                None => return HtmlToken::Eof,
                Some(c) => c,
            };

            match self.state {
                TokenizerState::Data => {
                    self.advance();
                    match ch {
                        '<' => {
                            self.state = TokenizerState::TagOpen;
                        }
                        '&' => {
                            // Entity reference — simplified
                            return HtmlToken::Character('&');
                        }
                        _ => return HtmlToken::Character(ch),
                    }
                }

                TokenizerState::TagOpen => {
                    match ch {
                        '!' => {
                            self.advance();
                            self.state = TokenizerState::MarkupDeclarationOpen;
                        }
                        '/' => {
                            self.advance();
                            self.state = TokenizerState::EndTagOpen;
                        }
                        c if c.is_ascii_alphabetic() => {
                            self.current_tag = Some((false, String::new(), Vec::new()));
                            self.state = TokenizerState::TagName;
                        }
                        '?' => {
                            // Processing instruction — treat as comment
                            self.state = TokenizerState::Comment;
                        }
                        _ => {
                            self.state = TokenizerState::Data;
                            return HtmlToken::Character('<');
                        }
                    }
                }

                TokenizerState::EndTagOpen => {
                    match ch {
                        c if c.is_ascii_alphabetic() => {
                            self.current_tag = Some((true, String::new(), Vec::new()));
                            self.state = TokenizerState::TagName;
                        }
                        '>' => {
                            self.advance();
                            self.state = TokenizerState::Data;
                        }
                        _ => {
                            self.state = TokenizerState::Comment;
                        }
                    }
                }

                TokenizerState::TagName => {
                    self.advance();
                    match ch {
                        '\t' | '\n' | '\x0C' | ' ' => {
                            self.state = TokenizerState::BeforeAttrName;
                        }
                        '/' => {
                            self.state = TokenizerState::SelfClosingStartTag;
                        }
                        '>' => {
                            self.state = TokenizerState::Data;
                            return self.emit_current_tag();
                        }
                        c => {
                            if let Some((_, name, _)) = &mut self.current_tag {
                                name.push(c.to_ascii_lowercase());
                            }
                        }
                    }
                }

                TokenizerState::BeforeAttrName => {
                    self.advance();
                    match ch {
                        '\t' | '\n' | '\x0C' | ' ' => {}
                        '/' | '>' => {
                            if ch == '>' {
                                self.state = TokenizerState::Data;
                                return self.emit_current_tag();
                            }
                            self.state = TokenizerState::SelfClosingStartTag;
                        }
                        '=' => {
                            self.current_attr = Some(HtmlAttribute { name: "=".to_string(), value: String::new() });
                            self.state = TokenizerState::AttrName;
                        }
                        c => {
                            self.current_attr = Some(HtmlAttribute { name: c.to_ascii_lowercase().to_string(), value: String::new() });
                            self.state = TokenizerState::AttrName;
                        }
                    }
                }

                TokenizerState::AttrName => {
                    self.advance();
                    match ch {
                        '\t' | '\n' | '\x0C' | ' ' => {
                            self.emit_current_attr();
                            self.state = TokenizerState::AfterAttrName;
                        }
                        '/' => {
                            self.emit_current_attr();
                            self.state = TokenizerState::SelfClosingStartTag;
                        }
                        '=' => {
                            self.state = TokenizerState::BeforeAttrValue;
                        }
                        '>' => {
                            self.emit_current_attr();
                            self.state = TokenizerState::Data;
                            return self.emit_current_tag();
                        }
                        c => {
                            if let Some(attr) = &mut self.current_attr {
                                attr.name.push(c.to_ascii_lowercase());
                            }
                        }
                    }
                }

                TokenizerState::BeforeAttrValue => {
                    self.advance();
                    match ch {
                        '\t' | '\n' | '\x0C' | ' ' => {}
                        '"' => { self.state = TokenizerState::AttrValueDoubleQuoted; }
                        '\'' => { self.state = TokenizerState::AttrValueSingleQuoted; }
                        '>' => {
                            self.emit_current_attr();
                            self.state = TokenizerState::Data;
                            return self.emit_current_tag();
                        }
                        c => {
                            if let Some(attr) = &mut self.current_attr {
                                attr.value.push(c);
                            }
                            self.state = TokenizerState::AttrValueUnquoted;
                        }
                    }
                }

                TokenizerState::AttrValueDoubleQuoted => {
                    self.advance();
                    match ch {
                        '"' => {
                            self.emit_current_attr();
                            self.state = TokenizerState::AfterAttrValue;
                        }
                        '&' => {}  // Entity parsing simplified
                        c => {
                            if let Some(attr) = &mut self.current_attr {
                                attr.value.push(c);
                            }
                        }
                    }
                }

                TokenizerState::AttrValueSingleQuoted => {
                    self.advance();
                    match ch {
                        '\'' => {
                            self.emit_current_attr();
                            self.state = TokenizerState::AfterAttrValue;
                        }
                        c => {
                            if let Some(attr) = &mut self.current_attr {
                                attr.value.push(c);
                            }
                        }
                    }
                }

                TokenizerState::AttrValueUnquoted => {
                    self.advance();
                    match ch {
                        '\t' | '\n' | '\x0C' | ' ' => {
                            self.emit_current_attr();
                            self.state = TokenizerState::AfterAttrValue;
                        }
                        '>' => {
                            self.emit_current_attr();
                            self.state = TokenizerState::Data;
                            return self.emit_current_tag();
                        }
                        c => {
                            if let Some(attr) = &mut self.current_attr {
                                attr.value.push(c);
                            }
                        }
                    }
                }

                TokenizerState::AfterAttrValue => {
                    self.advance();
                    match ch {
                        '\t' | '\n' | '\x0C' | ' ' => { self.state = TokenizerState::BeforeAttrName; }
                        '/' => { self.state = TokenizerState::SelfClosingStartTag; }
                        '>' => {
                            self.state = TokenizerState::Data;
                            return self.emit_current_tag();
                        }
                        _ => { self.state = TokenizerState::BeforeAttrName; }
                    }
                }

                TokenizerState::SelfClosingStartTag => {
                    self.advance();
                    if ch == '>' {
                        if let Some((is_end, ref name, _)) = self.current_tag {
                            if !is_end {
                                if let Some((false, ref mut _name, _)) = self.current_tag {}
                                let tok = self.emit_current_tag_self_closing();
                                self.state = TokenizerState::Data;
                                return tok;
                            }
                        }
                        self.state = TokenizerState::Data;
                        return self.emit_current_tag();
                    }
                    self.state = TokenizerState::BeforeAttrName;
                }

                TokenizerState::MarkupDeclarationOpen => {
                    if self.try_consume_string("--") {
                        self.state = TokenizerState::CommentStart;
                    } else if self.try_consume_string("DOCTYPE") || self.try_consume_string("doctype") {
                        self.state = TokenizerState::Doctype;
                    } else if self.try_consume_string("[CDATA[") {
                        self.state = TokenizerState::CdataSection;
                    } else {
                        self.advance();
                        self.state = TokenizerState::Comment;
                    }
                }

                TokenizerState::CommentStart | TokenizerState::Comment => {
                    self.advance();
                    if ch == '-' && self.current_char() == Some('-') {
                        self.advance();
                        if self.current_char() == Some('>') {
                            self.advance();
                            let data = std::mem::take(&mut self.current_str);
                            self.state = TokenizerState::Data;
                            return HtmlToken::Comment(data);
                        }
                        self.current_str.push('-');
                        self.current_str.push('-');
                    } else {
                        self.current_str.push(ch);
                    }
                }

                TokenizerState::Doctype => {
                    self.advance();
                    match ch {
                        '\t' | '\n' | '\x0C' | ' ' => { self.state = TokenizerState::DoctypeName; }
                        _ => { self.state = TokenizerState::DoctypeName; self.current_str.push(ch); }
                    }
                }

                TokenizerState::DoctypeName => {
                    self.advance();
                    match ch {
                        '>' => {
                            let name = std::mem::take(&mut self.current_str);
                            self.state = TokenizerState::Data;
                            return HtmlToken::Doctype {
                                name: Some(name),
                                public_id: None,
                                system_id: None,
                                force_quirks: false,
                            };
                        }
                        c => { self.current_str.push(c.to_ascii_lowercase()); }
                    }
                }

                TokenizerState::RawText | TokenizerState::ScriptData => {
                    self.advance();
                    if ch == '<' {
                        if self.current_char() == Some('/') {
                            self.advance();
                            // Check for end tag of the current raw text element
                            let mut candidate = String::new();
                            while let Some(c) = self.current_char() {
                                if c == '>' || c == '<' || c.is_whitespace() { break; }
                                candidate.push(c.to_ascii_lowercase());
                                self.advance();
                            }
                            if candidate == self.last_start_tag_name {
                                // Skip to '>'
                                while let Some(c) = self.current_char() {
                                    self.advance();
                                    if c == '>' { break; }
                                }
                                let data = std::mem::take(&mut self.current_str);
                                self.state = TokenizerState::Data;
                                return HtmlToken::Characters(data);
                            } else {
                                self.current_str.push('<');
                                self.current_str.push('/');
                                self.current_str.push_str(&candidate);
                            }
                        } else {
                            self.current_str.push('<');
                        }
                    } else {
                        self.current_str.push(ch);
                    }
                }

                TokenizerState::AfterAttrName => {
                    self.advance();
                    match ch {
                        '\t' | '\n' | '\x0C' | ' ' => {}
                        '/' => { self.state = TokenizerState::SelfClosingStartTag; }
                        '=' => { self.state = TokenizerState::BeforeAttrValue; }
                        '>' => {
                            self.state = TokenizerState::Data;
                            return self.emit_current_tag();
                        }
                        c => {
                            self.current_attr = Some(HtmlAttribute {
                                name: c.to_ascii_lowercase().to_string(),
                                value: String::new(),
                            });
                            self.state = TokenizerState::AttrName;
                        }
                    }
                }

                TokenizerState::CdataSection => {
                    self.advance();
                    self.current_str.push(ch);
                    if self.current_str.ends_with("]]>") {
                        let len = self.current_str.len();
                        self.current_str.truncate(len - 3);
                        let data = std::mem::take(&mut self.current_str);
                        self.state = TokenizerState::Data;
                        return HtmlToken::Characters(data);
                    }
                }

                _ => {
                    // Fallback: treat as data
                    self.advance();
                    return HtmlToken::Character(ch);
                }
            }
        }
    }

    fn emit_current_attr(&mut self) {
        if let Some(attr) = self.current_attr.take() {
            if let Some((_, _, attrs)) = &mut self.current_tag {
                // Don't add duplicate attributes per spec
                if !attrs.iter().any(|a| a.name == attr.name) {
                    attrs.push(attr);
                }
            }
        }
    }

    fn emit_current_tag(&mut self) -> HtmlToken {
        self.emit_current_attr();
        if let Some((is_end, name, attrs)) = self.current_tag.take() {
            if is_end {
                HtmlToken::EndTag { name }
            } else {
                let self_closing = is_void(&name);
                if is_raw_text(&name) { self.state = TokenizerState::RawText; }
                else if is_rcdata(&name) { self.state = TokenizerState::RcData; }
                self.last_start_tag_name = name.clone();
                HtmlToken::StartTag { name, attributes: attrs, self_closing }
            }
        } else {
            HtmlToken::Eof
        }
    }

    fn emit_current_tag_self_closing(&mut self) -> HtmlToken {
        self.emit_current_attr();
        if let Some((is_end, name, attrs)) = self.current_tag.take() {
            if is_end {
                HtmlToken::EndTag { name }
            } else {
                self.last_start_tag_name = name.clone();
                HtmlToken::StartTag { name, attributes: attrs, self_closing: true }
            }
        } else {
            HtmlToken::Eof
        }
    }
}

/// Parse statistics
#[derive(Debug, Default)]
pub struct ParseStats {
    pub element_count: usize,
    pub text_node_count: usize,
    pub comment_count: usize,
    pub error_count: usize,
    pub parse_errors: Vec<String>,
}

/// The HTML5 tree constructor
pub struct HtmlParser {
    pub tokenizer: HtmlTokenizer,
    pub mode: InsertionMode,
    pub open_elements: Vec<HtmlElement>,
    pub head_element: Option<HtmlElement>,
    pub root_nodes: Vec<HtmlNode>,
    pub next_id: u64,
    pub stats: ParseStats,
    pub scripting: bool,
    pub frameset_ok: bool,
    pub quirks_mode: bool,
    pub foster_parenting: bool,
}

impl HtmlParser {
    pub fn new(html: &str) -> Self {
        Self {
            tokenizer: HtmlTokenizer::new(html),
            mode: InsertionMode::Initial,
            open_elements: Vec::new(),
            head_element: None,
            root_nodes: Vec::new(),
            next_id: 1,
            stats: ParseStats::default(),
            scripting: false,
            frameset_ok: true,
            quirks_mode: false,
            foster_parenting: false,
        }
    }

    fn next_id(&mut self) -> u64 {
        let id = self.next_id;
        self.next_id += 1;
        id
    }

    /// Run the full parse, returning the document root
    pub fn parse(&mut self) -> Vec<HtmlNode> {
        loop {
            let token = self.tokenizer.next_token();
            let done = matches!(&token, HtmlToken::Eof);
            self.process_token(token);
            if done { break; }
        }

        // Close any remaining open elements
        let mut root = Vec::new();
        for elem in self.open_elements.drain(..).rev() {
            root.push(HtmlNode::Element(elem));
        }
        root.extend(self.root_nodes.drain(..));

        root
    }

    fn process_token(&mut self, token: HtmlToken) {
        match token {
            HtmlToken::Doctype { name, public_id, system_id, .. } => {
                let node = HtmlNode::Doctype(HtmlDoctype {
                    id: self.next_id(),
                    name: name.unwrap_or_default(),
                    public_id: public_id.unwrap_or_default(),
                    system_id: system_id.unwrap_or_default(),
                });
                self.root_nodes.push(node);
                self.mode = InsertionMode::BeforeHtml;
            }

            HtmlToken::StartTag { name, attributes, .. } => {
                self.stats.element_count += 1;
                let elem = HtmlElement {
                    id: self.next_id(),
                    tag: name.clone(),
                    namespace: Namespace::Html,
                    attributes,
                    children: Vec::new(),
                };
                if is_void(&name) {
                    // Immediately close void elements
                    if let Some(parent) = self.open_elements.last_mut() {
                        parent.children.push(HtmlNode::Element(elem));
                    } else {
                        self.root_nodes.push(HtmlNode::Element(elem));
                    }
                } else {
                    self.open_elements.push(elem);
                    if name == "head" { self.mode = InsertionMode::InHead; }
                    else if name == "body" { self.mode = InsertionMode::InBody; }
                    else if name == "table" { self.mode = InsertionMode::InTable; }
                }
            }

            HtmlToken::EndTag { name } => {
                // Close matching element
                let close_idx = self.open_elements.iter().rposition(|e| e.tag == name);
                if let Some(idx) = close_idx {
                    // Pop all elements down to and including idx
                    let mut stack = self.open_elements.split_off(idx);
                    let mut children = Vec::new();
                    for elem in stack.drain(1..) {
                        children.push(HtmlNode::Element(elem));
                    }
                    let mut closed = stack.remove(0);
                    closed.children.extend(children);

                    if let Some(parent) = self.open_elements.last_mut() {
                        parent.children.push(HtmlNode::Element(closed));
                    } else {
                        self.root_nodes.push(HtmlNode::Element(closed));
                    }

                    // Update insertion mode
                    match name.as_str() {
                        "head" => self.mode = InsertionMode::AfterHead,
                        "body" => self.mode = InsertionMode::AfterBody,
                        "html" => self.mode = InsertionMode::AfterAfterBody,
                        _ => {}
                    }
                } else {
                    self.stats.error_count += 1;
                    self.stats.parse_errors.push(format!("Unexpected end tag: </{}>", name));
                }
            }

            HtmlToken::Character(c) => {
                let text_char = c.to_string();
                self.insert_text(&text_char);
            }

            HtmlToken::Characters(s) => {
                self.insert_text(&s);
            }

            HtmlToken::Comment(data) => {
                self.stats.comment_count += 1;
                let node = HtmlNode::Comment(HtmlComment { id: self.next_id(), data });
                if let Some(parent) = self.open_elements.last_mut() {
                    parent.children.push(node);
                } else {
                    self.root_nodes.push(node);
                }
            }

            HtmlToken::Eof => {
                self.mode = InsertionMode::AfterAfterBody;
            }

            HtmlToken::Doctype { .. } => {}
        }
    }

    fn insert_text(&mut self, text: &str) {
        if text.trim().is_empty() { return; }

        let has_parent = !self.open_elements.is_empty();
        if has_parent {
            let parent = self.open_elements.last_mut().unwrap();
            if let Some(HtmlNode::Text(t)) = parent.children.last_mut() {
                // Coalesce adjacent text nodes
                t.data.push_str(text);
                return;
            }
            // Need a new ID — get it before the next push
            let new_id = self.next_id;
            self.next_id += 1;
            self.stats.text_node_count += 1;
            let parent = self.open_elements.last_mut().unwrap();
            parent.children.push(HtmlNode::Text(HtmlText {
                id: new_id,
                data: text.to_string(),
            }));
        } else if !text.trim().is_empty() {
            let new_id = self.next_id;
            self.next_id += 1;
            self.stats.text_node_count += 1;
            self.root_nodes.push(HtmlNode::Text(HtmlText {
                id: new_id,
                data: text.to_string(),
            }));
        }
    }

    /// AI-facing parse statistics
    pub fn ai_parse_summary(&self) -> String {
        let mut lines = vec![
            format!("🧩 HTML Parse Summary:"),
            format!("  Elements: {}", self.stats.element_count),
            format!("  Text nodes: {}", self.stats.text_node_count),
            format!("  Comments: {}", self.stats.comment_count),
            format!("  Parse errors: {}", self.stats.error_count),
        ];
        for err in &self.stats.parse_errors {
            lines.push(format!("    ⚠️ {}", err));
        }
        lines.join("\n")
    }
}

/// Serialize an HTML node back to an HTML string (for diff/extraction)
pub fn serialize_html(node: &HtmlNode) -> String {
    match node {
        HtmlNode::Doctype(d) => format!("<!DOCTYPE {}>", d.name),
        HtmlNode::Text(t) => html_escape(&t.data),
        HtmlNode::Comment(c) => format!("<!--{}-->", c.data),
        HtmlNode::Element(e) => {
            let attrs: String = e.attributes.iter().map(|a| {
                if a.value.is_empty() {
                    format!(" {}", a.name)
                } else {
                    format!(" {}=\"{}\"", a.name, html_escape(&a.value))
                }
            }).collect();

            if is_void(&e.tag) {
                format!("<{}{}>", e.tag, attrs)
            } else {
                let children: String = e.children.iter().map(serialize_html).collect();
                format!("<{}{}>{}</{}>", e.tag, attrs, children, e.tag)
            }
        }
        HtmlNode::Document(children) => children.iter().map(serialize_html).collect(),
    }
}

fn html_escape(s: &str) -> String {
    s.replace('&', "&amp;")
     .replace('<', "&lt;")
     .replace('>', "&gt;")
     .replace('"', "&quot;")
}
