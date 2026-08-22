//! AI Cognitive Renderer — Visual Serialization for LLM Grounding
//!
//! Converts the layout engine output (BoxModel + A11y Tree) into multiple
//! representation formats that work best with Large Language Models:
//!   1. ASCII Spatial Map — ASCII art layout grid for spatial reasoning
//!   2. Semantic Tensor JSON — Structured JSON of all meaningful elements
//!   3. Interaction Blueprint — All clickable/typeable elements with coordinates
//!   4. Visual Density Heatmap — Token-optimized density map for AI attention
//!   5. Markdown Viewport — Human-readable markdown for general reasoning

use std::collections::HashMap;
use serde::{Serialize, Deserialize};

/// Represents a single rendered element in the AI's cognitive workspace
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CognitiveElement {
    /// Stable AI-facing ID for interaction commands (e.g., "click [ID:7]")
    pub ai_id: u32,
    
    /// ARIA role for semantic understanding
    pub role: String,
    
    /// Human-visible text content
    pub text_content: String,
    
    /// Accessible name/label
    pub accessible_name: Option<String>,
    
    /// Whether the AI can interact with this element
    pub is_interactive: bool,
    
    /// Whether the element is currently visible (not occluded)
    pub is_visible: bool,
    
    /// Bounding box in viewport coordinates (x, y, width, height)
    pub bounds: [f64; 4],
    
    /// CSS display type
    pub display: String,
    
    /// Element's tag name
    pub tag_name: String,
    
    /// Relevant attributes (href, src, type, value, placeholder, etc.)
    pub attributes: HashMap<String, String>,
    
    /// Child element IDs 
    pub children: Vec<u32>,
    
    /// Parent element ID
    pub parent: Option<u32>,
    
    /// Interaction type classification
    pub interaction_type: InteractionType,
    
    /// Computed z-index stack position
    pub z_index: i32,
    
    /// Nesting depth from the root
    pub depth: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum InteractionType {
    None,
    Clickable,
    Typeable,
    Selectable,
    Draggable,
    Scrollable,
    Focusable,
    Submittable,
}

/// The full cognitive render output sent to the AI
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CognitivePage {
    pub url: String,
    pub title: String,
    pub viewport_width: f64,
    pub viewport_height: f64,
    
    /// All elements indexed by AI ID
    pub elements: HashMap<u32, CognitiveElement>,
    
    /// The root element ID
    pub root_id: u32,
    
    /// Pre-rendered ASCII spatial map
    pub ascii_map: String,
    
    /// Markdown viewport representation  
    pub markdown_view: String,
    
    /// Focused element ID (if any)
    pub focused_element: Option<u32>,
    
    /// Number of interactive elements
    pub interactive_count: u32,
    
    /// Page load state
    pub load_state: LoadState,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum LoadState {
    Loading,
    DomContentLoaded,
    Complete,
    NetworkError(String),
}

/// The AI Cognitive Renderer — the "eyes" of the AI agent
pub struct AiCognitiveRenderer {
    next_ai_id: u32,
    viewport_width: f64,
    viewport_height: f64,
    
    /// ASCII canvas for spatial map rendering
    ascii_cols: usize,
    ascii_rows: usize,
}

impl AiCognitiveRenderer {
    pub fn new(viewport_width: f64, viewport_height: f64) -> Self {
        Self {
            next_ai_id: 1,
            viewport_width,
            viewport_height,
            ascii_cols: 120,
            ascii_rows: 40,
        }
    }
    
    fn allocate_id(&mut self) -> u32 {
        let id = self.next_ai_id;
        self.next_ai_id += 1;
        id
    }
    
    /// Render a page into a full CognitivePage representation
    pub fn render_page(&mut self, url: &str, title: &str) -> CognitivePage {
        let mut elements = HashMap::new();
        
        // Root element
        let root_id = self.allocate_id();
        elements.insert(root_id, CognitiveElement {
            ai_id: root_id,
            role: "rootWebArea".to_string(),
            text_content: String::new(),
            accessible_name: Some(title.to_string()),
            is_interactive: false,
            is_visible: true,
            bounds: [0.0, 0.0, self.viewport_width, self.viewport_height],
            display: "block".to_string(),
            tag_name: "document".to_string(),
            attributes: HashMap::new(),
            children: Vec::new(),
            parent: None,
            interaction_type: InteractionType::Scrollable,
            z_index: 0,
            depth: 0,
        });
        
        let ascii_map = self.render_ascii_map(&elements);
        let markdown_view = self.render_markdown_view(url, title, &elements);
        
        CognitivePage {
            url: url.to_string(),
            title: title.to_string(),
            viewport_width: self.viewport_width,
            viewport_height: self.viewport_height,
            interactive_count: elements.values()
                .filter(|e| e.is_interactive)
                .count() as u32,
            elements,
            root_id,
            ascii_map,
            markdown_view,
            focused_element: None,
            load_state: LoadState::Complete,
        }
    }
    
    /// Build an ASCII spatial map — allows LLMs to reason about layout
    fn render_ascii_map(&self, elements: &HashMap<u32, CognitiveElement>) -> String {
        let mut grid = vec![vec![' '; self.ascii_cols]; self.ascii_rows];
        
        // Scale factors: map viewport coordinates to ASCII grid
        let x_scale = self.ascii_cols as f64 / self.viewport_width;
        let y_scale = self.ascii_rows as f64 / self.viewport_height;
        
        // Render elements by z-index order (painter's algorithm)
        let mut sorted: Vec<&CognitiveElement> = elements.values()
            .filter(|e| e.is_visible && e.bounds[2] > 0.0 && e.bounds[3] > 0.0)
            .collect();
        sorted.sort_by_key(|e| e.z_index);
        
        for el in sorted {
            let [x, y, w, h] = el.bounds;
            let col_start = ((x * x_scale) as usize).min(self.ascii_cols - 1);
            let col_end = (((x + w) * x_scale) as usize).min(self.ascii_cols);
            let row_start = ((y * y_scale) as usize).min(self.ascii_rows - 1);
            let row_end = (((y + h) * y_scale) as usize).min(self.ascii_rows);
            
            // Draw borders
            let border_char = Self::border_char_for_role(&el.role);
            
            for row in row_start..row_end.min(self.ascii_rows) {
                for col in col_start..col_end.min(self.ascii_cols) {
                    if row == row_start || row == row_end.saturating_sub(1)
                    || col == col_start || col == col_end.saturating_sub(1) {
                        grid[row][col] = border_char;
                    } else if row == row_start + 1 && (col_end - col_start) > 2 {
                        // Write element label on first inner row
                        let label: Vec<char> = format!("[{}:{}]", el.ai_id, el.role)
                            .chars().collect();
                        if col - col_start - 1 < label.len() {
                            grid[row][col] = label[col - col_start - 1];
                        }
                    }
                }
            }
        }
        
        // Convert grid to string
        let mut output = String::with_capacity(self.ascii_rows * (self.ascii_cols + 1));
        for row in &grid {
            output.extend(row);
            output.push('\n');
        }
        output
    }
    
    fn border_char_for_role(role: &str) -> char {
        match role {
            "button" => '#',
            "link" => '~',
            "textbox" | "input" => '_',
            "heading" => '=',
            "img" | "image" => '*',
            "navigation" => '|',
            "main" => '+',
            "banner" | "header" => '^',
            "contentinfo" | "footer" => 'v',
            _ => '-',
        }
    }
    
    /// Build a rich Markdown representation for LLM reasoning
    fn render_markdown_view(
        &self,
        url: &str,
        title: &str,
        elements: &HashMap<u32, CognitiveElement>
    ) -> String {
        let mut md = String::new();
        
        md.push_str(&format!("# 🌐 {}\n", title));
        md.push_str(&format!("**URL**: {}\n\n", url));
        md.push_str(&format!("**Viewport**: {}×{}\n\n", self.viewport_width, self.viewport_height));
        md.push_str("---\n\n");
        
        // Collect interactive elements
        let mut interactives: Vec<&CognitiveElement> = elements.values()
            .filter(|e| e.is_interactive && e.is_visible)
            .collect();
        interactives.sort_by_key(|e| (e.bounds[1] as i64, e.bounds[0] as i64));
        
        if !interactives.is_empty() {
            md.push_str("## 🎯 Interactive Elements\n\n");
            for el in &interactives {
                let interaction_emoji = match el.interaction_type {
                    InteractionType::Clickable => "🖱️",
                    InteractionType::Typeable => "⌨️",
                    InteractionType::Selectable => "☑️",
                    InteractionType::Submittable => "📤",
                    _ => "●",
                };
                
                md.push_str(&format!(
                    "{} **[ID:{}]** `<{}>` — {}\n",
                    interaction_emoji,
                    el.ai_id,
                    el.tag_name,
                    if el.text_content.is_empty() {
                        el.accessible_name.as_deref().unwrap_or("(no label)")
                    } else {
                        &el.text_content
                    }
                ));
                
                if let Some(href) = el.attributes.get("href") {
                    md.push_str(&format!("   → Links to: `{}`\n", href));
                }
                if let Some(placeholder) = el.attributes.get("placeholder") {
                    md.push_str(&format!("   → Placeholder: *{}*\n", placeholder));
                }
            }
            md.push('\n');
        }
        
        md.push_str("## 📄 Page Content\n\n");
        // Walk elements by document order
        let mut content_elements: Vec<&CognitiveElement> = elements.values()
            .filter(|e| e.is_visible && !e.text_content.is_empty())
            .collect();
        content_elements.sort_by_key(|e| (e.bounds[1] as i64, e.bounds[0] as i64));
        
        for el in content_elements {
            let indent = "  ".repeat(el.depth as usize);
            match el.role.as_str() {
                "heading" => md.push_str(&format!("{}### {}\n", indent, el.text_content)),
                "paragraph" => md.push_str(&format!("{}{}\n\n", indent, el.text_content)),
                "listitem" => md.push_str(&format!("{}• {}\n", indent, el.text_content)),
                "link" => md.push_str(&format!(
                    "{}[{}]({})\n",
                    indent,
                    el.text_content,
                    el.attributes.get("href").map_or("#", |s| s)
                )),
                "img" => md.push_str(&format!(
                    "{}![{}]({})\n",
                    indent,
                    el.accessible_name.as_deref().unwrap_or(""),
                    el.attributes.get("src").map_or("", |s| s)
                )),
                _ => {
                    if !el.text_content.trim().is_empty() {
                        md.push_str(&format!("{}{}\n", indent, el.text_content.trim()));
                    }
                }
            }
        }
        
        md
    }
}
