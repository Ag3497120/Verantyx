//! Browser Actions — Commands that can be executed on a page
//!
//! Each action targets an interactive element by its AI-assigned ID.

use vx_render::ai_renderer::InteractiveElement;

/// A user or AI action to perform on the page
#[derive(Debug, Clone)]
pub enum BrowserAction {
    /// Click a link or button by element ID
    Click(usize),
    /// Type text into an input/textarea by element ID
    Type(usize, String),
    /// Submit a form (finds closest form to element ID)
    Submit(usize),
    /// Select an option in a dropdown by element ID
    Select(usize, String),
    /// Focus an element
    Focus(usize),
    /// Navigate to a URL
    Goto(String),
    /// Go back in history
    Back,
    /// Scroll up/down
    Scroll(ScrollDirection),
    /// Reload current page
    Reload,
    /// Show current page info
    Info,
    /// Show interactive elements list
    Elements,
    /// Quit
    Quit,
}

#[derive(Debug, Clone)]
pub enum ScrollDirection {
    Up,
    Down,
}

/// Result of executing an action
#[derive(Debug, Clone)]
pub struct ActionResult {
    pub success: bool,
    pub message: String,
    pub navigate_to: Option<String>,
    pub form_data: Option<Vec<(String, String)>>,
    pub needs_rerender: bool,
}

impl ActionResult {
    pub fn ok(msg: &str) -> Self {
        Self { success: true, message: msg.to_string(), navigate_to: None, form_data: None, needs_rerender: false }
    }

    pub fn navigate(url: &str) -> Self {
        Self { success: true, message: format!("→ {}", url), navigate_to: Some(url.to_string()), form_data: None, needs_rerender: true }
    }

    pub fn error(msg: &str) -> Self {
        Self { success: false, message: msg.to_string(), navigate_to: None, form_data: None, needs_rerender: false }
    }

    pub fn rerender(msg: &str) -> Self {
        Self { success: true, message: msg.to_string(), navigate_to: None, form_data: None, needs_rerender: true }
    }
}

/// Parse a user command string into a BrowserAction
pub fn parse_action(input: &str) -> Option<BrowserAction> {
    let input = input.trim();
    if input.is_empty() { return None; }

    let parts: Vec<&str> = input.splitn(3, ' ').collect();
    let cmd = parts[0].to_lowercase();

    match cmd.as_str() {
        "click" | "c" => {
            parts.get(1)?.parse::<usize>().ok().map(BrowserAction::Click)
        }
        "type" | "t" => {
            let id = parts.get(1)?.parse::<usize>().ok()?;
            let text = parts.get(2).unwrap_or(&"").to_string();
            Some(BrowserAction::Type(id, text))
        }
        "submit" | "s" => {
            parts.get(1)?.parse::<usize>().ok().map(BrowserAction::Submit)
        }
        "select" | "sel" => {
            let id = parts.get(1)?.parse::<usize>().ok()?;
            let val = parts.get(2).unwrap_or(&"").to_string();
            Some(BrowserAction::Select(id, val))
        }
        "focus" | "f" => {
            parts.get(1)?.parse::<usize>().ok().map(BrowserAction::Focus)
        }
        "goto" | "go" | "g" | "navigate" => {
            let url = parts.get(1)?;
            let url = if url.starts_with("http") { url.to_string() } else { format!("https://{}", url) };
            Some(BrowserAction::Goto(url))
        }
        "back" | "b" => Some(BrowserAction::Back),
        "scroll" => {
            match parts.get(1).map(|s| s.to_lowercase()).as_deref() {
                Some("up") | Some("u") => Some(BrowserAction::Scroll(ScrollDirection::Up)),
                _ => Some(BrowserAction::Scroll(ScrollDirection::Down)),
            }
        }
        "reload" | "r" => Some(BrowserAction::Reload),
        "info" | "i" => Some(BrowserAction::Info),
        "elements" | "el" | "e" => Some(BrowserAction::Elements),
        "quit" | "q" | "exit" => Some(BrowserAction::Quit),
        _ => {
            // Try as direct element ID click
            if let Ok(id) = input.parse::<usize>() {
                Some(BrowserAction::Click(id))
            } else {
                None
            }
        }
    }
}

/// Execute an action against the interactive elements
pub fn execute_action(
    action: &BrowserAction,
    elements: &[InteractiveElement],
    form_state: &mut super::form::FormState,
    current_url: &str,
) -> ActionResult {
    match action {
        BrowserAction::Click(id) => {
            if let Some(el) = elements.iter().find(|e| e.id == *id) {
                match &el.element_type {
                    vx_render::ai_renderer::ElementType::Link => {
                        if let Some(href) = &el.href {
                            let resolved = resolve_url(current_url, href);
                            ActionResult::navigate(&resolved)
                        } else {
                            ActionResult::error(&format!("Link [ID:{}] has no href", id))
                        }
                    }
                    vx_render::ai_renderer::ElementType::Button |
                    vx_render::ai_renderer::ElementType::Submit => {
                        ActionResult::ok(&format!("Clicked button [ID:{}] '{}'", id, el.label))
                    }
                    _ => ActionResult::ok(&format!("Clicked [ID:{}] '{}'", id, el.label))
                }
            } else {
                ActionResult::error(&format!("Element [ID:{}] not found", id))
            }
        }

        BrowserAction::Type(id, text) => {
            if let Some(el) = elements.iter().find(|e| e.id == *id) {
                form_state.set_value(*id, text);
                ActionResult::rerender(&format!("Typed '{}' into [ID:{}] '{}'", text, id, el.label))
            } else {
                ActionResult::error(&format!("Element [ID:{}] not found", id))
            }
        }

        BrowserAction::Submit(id) => {
            let data = form_state.get_all();
            ActionResult {
                success: true,
                message: format!("Submitted form at [ID:{}] with {} fields", id, data.len()),
                navigate_to: None,
                form_data: Some(data),
                needs_rerender: true,
            }
        }

        BrowserAction::Select(id, value) => {
            if let Some(el) = elements.iter().find(|e| e.id == *id) {
                form_state.set_value(*id, value);
                ActionResult::rerender(&format!("Selected '{}' in [ID:{}] '{}'", value, id, el.label))
            } else {
                ActionResult::error(&format!("Element [ID:{}] not found", id))
            }
        }

        BrowserAction::Focus(id) => {
            form_state.set_focus(*id);
            ActionResult::ok(&format!("Focused [ID:{}]", id))
        }

        BrowserAction::Goto(url) => ActionResult::navigate(url),
        BrowserAction::Back => ActionResult::ok("Back (not implemented — use goto)"),
        BrowserAction::Reload => ActionResult { success: true, message: "Reloading...".into(), navigate_to: None, form_data: None, needs_rerender: true },
        BrowserAction::Info => ActionResult::ok(&format!("Current URL: {}", current_url)),
        BrowserAction::Elements => ActionResult::ok("(see elements list)"),
        BrowserAction::Quit => ActionResult::ok("Goodbye"),

        _ => ActionResult::error("Unknown action"),
    }
}

/// Resolve relative URL against base
fn resolve_url(base: &str, href: &str) -> String {
    if href.starts_with("http://") || href.starts_with("https://") {
        return href.to_string();
    }
    if href.starts_with("//") {
        return format!("https:{}", href);
    }
    if let Ok(base_url) = url::Url::parse(base) {
        if let Ok(resolved) = base_url.join(href) {
            return resolved.to_string();
        }
    }
    href.to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_click() {
        assert!(matches!(parse_action("click 5"), Some(BrowserAction::Click(5))));
        assert!(matches!(parse_action("c 3"), Some(BrowserAction::Click(3))));
    }

    #[test]
    fn test_parse_type() {
        if let Some(BrowserAction::Type(id, text)) = parse_action("type 2 hello world") {
            assert_eq!(id, 2);
            assert_eq!(text, "hello world");
        } else {
            panic!("Expected Type action");
        }
    }

    #[test]
    fn test_parse_goto() {
        if let Some(BrowserAction::Goto(url)) = parse_action("goto example.com") {
            assert_eq!(url, "https://example.com");
        } else {
            panic!("Expected Goto action");
        }
    }

    #[test]
    fn test_parse_number_as_click() {
        assert!(matches!(parse_action("5"), Some(BrowserAction::Click(5))));
    }

    #[test]
    fn test_resolve_url() {
        assert_eq!(resolve_url("https://example.com/page", "/about"), "https://example.com/about");
        assert_eq!(resolve_url("https://example.com", "https://other.com"), "https://other.com");
        assert_eq!(resolve_url("https://example.com/dir/", "file.html"), "https://example.com/dir/file.html");
    }
}
