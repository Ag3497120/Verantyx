//! Page view rendering helpers
use ratatui::{style::Style, text::Line};
pub fn highlight_search(line: &str, query: &str) -> Line<'static> {
    Line::from(line.to_string())
}
