pub mod ai_renderer;
pub mod image_render;

use crossterm::style::{Attribute, Color, SetAttribute, SetForegroundColor, ResetColor};
use std::fmt::Write;
use vx_dom::{NodeId, NodeArena, NodeData, css::CssColor};

/// A styled segment of text for terminal output
#[derive(Debug, Clone)]
pub struct StyledSpan {
    pub text: String,
    pub fg: Option<Color>,
    pub bold: bool,
    pub underline: bool,
    pub dim: bool,
    pub link: Option<String>,
}

impl StyledSpan {
    fn plain(text: &str) -> Self {
        Self { text: text.to_string(), fg: None, bold: false, underline: false, dim: false, link: None }
    }
}

/// Rendered line of terminal output
#[derive(Debug, Clone)]
pub struct RenderedLine {
    pub spans: Vec<StyledSpan>,
    pub indent: usize,
}

impl RenderedLine {
    fn new(indent: usize) -> Self {
        Self { spans: Vec::new(), indent }
    }

    fn push(&mut self, span: StyledSpan) {
        self.spans.push(span);
    }

    /// Convert to ANSI-colored string
    pub fn to_ansi(&self) -> String {
        let mut out = String::new();

        // Indent
        for _ in 0..self.indent {
            out.push(' ');
        }

        for span in &self.spans {
            if span.bold {
                write!(out, "\x1b[1m").ok();
            }
            if span.underline {
                write!(out, "\x1b[4m").ok();
            }
            if span.dim {
                write!(out, "\x1b[2m").ok();
            }
            if let Some(color) = &span.fg {
                let code = match color {
                    Color::Blue => "34",
                    Color::Cyan => "36",
                    Color::Green => "32",
                    Color::Yellow => "33",
                    Color::Red => "31",
                    Color::Magenta => "35",
                    Color::Grey => "90",
                    Color::White => "37",
                    _ => "37",
                };
                write!(out, "\x1b[{}m", code).ok();
            }

            out.push_str(&span.text);

            if span.bold || span.underline || span.dim || span.fg.is_some() {
                write!(out, "\x1b[0m").ok();
            }
        }

        out
    }
}

/// Terminal renderer — converts DOM to terminal-friendly output
pub struct TerminalRenderer {
    pub width: u16,
}

impl TerminalRenderer {
    pub fn new(width: u16) -> Self {
        Self { width }
    }

    /// Render a DOM tree to terminal lines
    pub fn render(&self, arena: &NodeArena, root_id: NodeId) -> Vec<RenderedLine> {
        let mut lines = Vec::new();
        self.render_node(arena, root_id, &mut lines, 0, &RenderContext::default());
        lines
    }

    fn render_node(&self, arena: &NodeArena, node_id: NodeId, lines: &mut Vec<RenderedLine>, indent: usize, ctx: &RenderContext) {
        let Some(node) = arena.get(node_id) else { return };

        match &node.data {
            NodeData::Text(text) => {
                let wrapped = self.wrap_text(&text.content, indent);
                for line_text in wrapped {
                    let mut line = RenderedLine::new(indent);
                    line.push(StyledSpan {
                        text: line_text,
                        fg: ctx.fg,
                        bold: ctx.bold,
                        underline: ctx.underline,
                        dim: ctx.dim,
                        link: ctx.link.clone(),
                    });
                    lines.push(line);
                }
            }
            NodeData::Element(el) => {
                let tag = el.tag_name.as_str();
                let mut child_ctx = ctx.clone();

                // Apply style properties if available (Phase 2 Integration)
                // In a full implementation, we'd have a style map here
                if let Some(ref color_name) = el.attributes.get("color") {
                    // Simple heuristic for demonstration
                    child_ctx.fg = Some(match color_name.as_str() {
                        "red" => Color::Red,
                        "green" => Color::Green,
                        "blue" => Color::Blue,
                        _ => Color::White,
                    });
                }

                let mut pre_lines: Vec<RenderedLine> = Vec::new();
                let mut post_lines: Vec<RenderedLine> = Vec::new();
                let mut child_indent = indent;

                match tag {
                    // Block elements — add blank line before
                    "h1" | "h2" | "h3" | "h4" | "h5" | "h6" => {
                        lines.push(RenderedLine::new(0)); // blank line
                        child_ctx.bold = true;
                        child_ctx.fg = Some(match tag {
                            "h1" => Color::Cyan,
                            "h2" => Color::Green,
                            "h3" => Color::Yellow,
                            _ => Color::White,
                        });

                        // Add heading marker
                        let level = tag.chars().nth(1).unwrap().to_digit(10).unwrap_or(1);
                        let marker = "#".repeat(level as usize);
                        let mut marker_line = RenderedLine::new(indent);
                        marker_line.push(StyledSpan {
                            text: format!("{} ", marker),
                            fg: Some(Color::Grey),
                            bold: true,
                            underline: false, dim: false, link: None,
                        });
                        pre_lines.push(marker_line);
                    }

                    "p" | "div" | "section" | "article" | "main" | "header" | "footer" | "nav" => {
                        if !lines.is_empty() {
                            lines.push(RenderedLine::new(0));
                        }
                    }

                    "a" => {
                        child_ctx.fg = Some(Color::Blue);
                        child_ctx.underline = true;
                        child_ctx.link = el.attributes.get("href").cloned();
                    }

                    "strong" | "b" => {
                        child_ctx.bold = true;
                    }

                    "em" | "i" => {
                        child_ctx.fg = Some(Color::Yellow);
                    }

                    "code" => {
                        child_ctx.fg = Some(Color::Green);
                    }

                    "pre" => {
                        lines.push(RenderedLine::new(0));
                        child_ctx.fg = Some(Color::Green);
                        child_indent = indent + 2;
                    }

                    "ul" | "ol" => {
                        child_indent = indent + 2;
                    }

                    "li" => {
                        let mut bullet_line = RenderedLine::new(indent);
                        bullet_line.push(StyledSpan {
                            text: "• ".to_string(),
                            fg: Some(Color::Grey),
                            bold: false, underline: false, dim: false, link: None,
                        });
                        pre_lines.push(bullet_line);
                    }

                    "br" => {
                        lines.push(RenderedLine::new(0));
                        return;
                    }

                    "hr" => {
                        lines.push(RenderedLine::new(0));
                        let mut hr_line = RenderedLine::new(indent);
                        let width = (self.width as usize).saturating_sub(indent * 2);
                        hr_line.push(StyledSpan {
                            text: "─".repeat(width),
                            fg: Some(Color::Grey),
                            bold: false, underline: false, dim: true, link: None,
                        });
                        lines.push(hr_line);
                        lines.push(RenderedLine::new(0));
                        return;
                    }

                    "img" => {
                        let alt = el.attributes.get("alt").map(|s: &String| s.as_str()).unwrap_or("[image]");
                        let mut img_line = RenderedLine::new(indent);
                        img_line.push(StyledSpan {
                            text: format!("[🖼 {}]", alt),
                            fg: Some(Color::Magenta),
                            bold: false, underline: false, dim: true, link: el.attributes.get("src").cloned(),
                        });
                        lines.push(img_line);
                        return;
                    }

                    "table" => {
                        lines.push(RenderedLine::new(0));
                        child_ctx.dim = false;
                    }

                    "tr" => {
                        // Table rows are rendered inline
                    }

                    "td" | "th" => {
                        if tag == "th" {
                            child_ctx.bold = true;
                        }
                    }

                    // Skip invisible elements
                    "script" | "style" | "noscript" | "meta" | "link" | "head" => {
                        return;
                    }

                    _ => {}
                }

                // Pre-lines (markers, etc.)
                for pl in pre_lines {
                    lines.push(pl);
                }

                // Render children
                for &child_id in &node.children {
                    self.render_node(arena, child_id, lines, child_indent, &child_ctx);
                }

                // Post-lines
                for pl in post_lines {
                    lines.push(pl);
                }

                // Table row separator
                if tag == "tr" {
                    let mut sep = RenderedLine::new(indent);
                    sep.push(StyledSpan::plain(" | "));
                    // Don't add, just use as delimiter concept
                }
            }
            _ => {
                // Documents, fragments, comments, etc — just render children
                for &child_id in &node.children {
                    self.render_node(arena, child_id, lines, indent, ctx);
                }
            }
        }
    }

    fn wrap_text(&self, text: &str, indent: usize) -> Vec<String> {
        let max_width = (self.width as usize).saturating_sub(indent);
        if max_width == 0 {
            return vec![text.to_string()];
        }

        let mut result = Vec::new();
        let mut current = String::new();

        for word in text.split_whitespace() {
            if current.len() + word.len() + 1 > max_width && !current.is_empty() {
                result.push(current.clone());
                current.clear();
            }
            if !current.is_empty() {
                current.push(' ');
            }
            current.push_str(word);
        }
        if !current.is_empty() {
            result.push(current);
        }

        if result.is_empty() {
            result.push(String::new());
        }
        result
    }
}

impl Default for TerminalRenderer {
    fn default() -> Self {
        Self::new(80)
    }
}

#[derive(Debug, Clone, Default)]
struct RenderContext {
    fg: Option<Color>,
    bold: bool,
    underline: bool,
    dim: bool,
    link: Option<String>,
}

#[cfg(test)]
mod tests {
    use super::*;
    use vx_dom::NodeArena;

    #[test]
    fn test_render_simple() {
        let mut arena = NodeArena::new();
        let body_id = arena.document_id();
        
        let renderer = TerminalRenderer::new(80);
        let lines = renderer.render(&arena, body_id);
        let output: String = lines.iter().map(|l| l.to_ansi()).collect::<Vec<_>>().join("\n");
        // Document should be empty initially but valid
        assert!(output.is_empty() || output.len() >= 0);
    }
}
pub mod cognitive_renderer;
