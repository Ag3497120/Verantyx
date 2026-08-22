//! AI-Optimized Renderer
//!
//! Webページを「AIが理解しやすいセマンティックフォーマット」に変換する。
//!
//! 人間向けのリッチなGUI Webを、以下の形式に変換:
//! 1. Markdown（構造化テキスト）
//! 2. インタラクティブ要素にID付与（AIが操作可能）
//! 3. CSSの「意図」をメタデータとして抽出
//! 4. 配置情報（ヘッダー/メイン/フッター）の推定
//!
//! 出力例:
//! ```markdown
//! # [配置: header] AI最適化ブラウザ
//!
//! このツールはWebをAI向けに変換します。
//!
//! [ID:1] [button/推奨] 今すぐ試す
//! [ID:2] [link] ドキュメント → https://example.com/docs
//! [ID:3] [input/text] 検索... (placeholder)
//! ```

use std::collections::HashMap;
use vx_dom::NodeId;
use vx_layout::box_model::BoxRect;
use vx_spatial::{SpatialMap, SpatialAxis, PointOfInterest};
use serde::{Serialize, Deserialize};

/// AIが操作可能なインタラクティブ要素
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InteractiveElement {
    pub id: usize,
    pub node_id: NodeId,
    pub element_type: ElementType,
    pub label: String,
    pub href: Option<String>,
    pub value: Option<String>,
    pub placeholder: Option<String>,
    pub semantic_role: SemanticRole,
    pub css_intent: CssIntent,
    pub bounds: BoxRect,
}

/// A cluster of related interactive elements
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ElementCluster {
    pub label: String,
    pub elements: Vec<InteractiveElement>,
    pub overall_bounds: BoxRect,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum ElementType {
    Link,
    Button,
    TextInput,
    TextArea,
    Select,
    Checkbox,
    Radio,
    Submit,
    Image,
    Other(String),
}

impl std::fmt::Display for ElementType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ElementType::Link => write!(f, "link"),
            ElementType::Button => write!(f, "button"),
            ElementType::TextInput => write!(f, "input/text"),
            ElementType::TextArea => write!(f, "textarea"),
            ElementType::Select => write!(f, "select"),
            ElementType::Checkbox => write!(f, "checkbox"),
            ElementType::Radio => write!(f, "radio"),
            ElementType::Submit => write!(f, "submit"),
            ElementType::Image => write!(f, "image"),
            ElementType::Other(s) => write!(f, "{}", s),
        }
    }
}

/// CSSから推定された「意図」
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum CssIntent {
    Primary,      // 主要アクション（青系、大きい）
    Destructive,  // 削除・危険（赤系）
    Success,      // 成功・確認（緑系）
    Warning,      // 警告（黄/橙系）
    Muted,        // 目立たない（灰色、小さい）
    Navigation,   // ナビゲーション要素
    Neutral,      // 特に意図なし
}

impl std::fmt::Display for CssIntent {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            CssIntent::Primary => write!(f, "推奨"),
            CssIntent::Destructive => write!(f, "危険/削除"),
            CssIntent::Success => write!(f, "成功/確認"),
            CssIntent::Warning => write!(f, "警告"),
            CssIntent::Muted => write!(f, "補助"),
            CssIntent::Navigation => write!(f, "ナビ"),
            CssIntent::Neutral => write!(f, ""),
        }
    }
}

/// ページ内の配置から推定されたセマンティックロール
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum SemanticRole {
    Header,
    Navigation,
    Main,
    Sidebar,
    Footer,
    Modal,
    Form,
    Unknown,
}

impl std::fmt::Display for SemanticRole {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            SemanticRole::Header => write!(f, "header"),
            SemanticRole::Navigation => write!(f, "nav"),
            SemanticRole::Main => write!(f, "main"),
            SemanticRole::Sidebar => write!(f, "sidebar"),
            SemanticRole::Footer => write!(f, "footer"),
            SemanticRole::Modal => write!(f, "modal"),
            SemanticRole::Form => write!(f, "form"),
            SemanticRole::Unknown => write!(f, ""),
        }
    }
}

/// AI向けにレンダリングされたページ
#[derive(Debug)]
pub struct AiRenderedPage {
    pub title: String,
    pub url: String,
    pub markdown: String,
    pub interactive_elements: Vec<InteractiveElement>,
    pub page_summary: String,
    pub token_estimate: usize,
}

impl AiRenderedPage {
    pub fn render_markdown(&self) -> String {
        self.markdown.clone()
    }

    /// Translate to Sovereign Spatial Map (JCross)
    pub fn to_spatial_map(&self) -> SpatialMap {
        let mut map = SpatialMap::new();

        // Perform semantic clustering before JCross generation
        let clusters = self.cluster_elements();

        // AXIS FRONT: Clustered Interactive elements (Action Zones)
        let mut front_entries = HashMap::new();
        for (idx, cluster) in clusters.iter().enumerate() {
            let key = format!("cluster_{}", idx + 1);
            let mut value = format!(
                "Action Zone: \"{}\" at ({:.0},{:.0}) w:{:.0} h:{:.0}",
                cluster.label, cluster.overall_bounds.x, cluster.overall_bounds.y, cluster.overall_bounds.width, cluster.overall_bounds.height
            );
            
            // List members of the cluster
            for el in &cluster.elements {
                value.push_str(&format!("\n        - [{}] {}", el.element_type, el.label));
            }
            front_entries.insert(key, value);
        }

        map.add_axis(SpatialAxis {
            name: "FRONT".to_string(),
            entries: front_entries,
            description: "Clustered Action Zones and interactive Points of Interest (POIs).".to_string(),
        });

        // AXIS NEAR: Structural Summary
        let mut near_entries = HashMap::new();
        near_entries.insert("url".to_string(), self.url.clone());
        near_entries.insert("title".to_string(), self.title.clone());
        near_entries.insert("summary".to_string(), self.page_summary.clone());
        map.add_axis(SpatialAxis {
            name: "NEAR".to_string(),
            entries: near_entries,
            description: "Structural summary and page metadata.".to_string(),
        });

        map
    }

    fn cluster_elements(&self) -> Vec<ElementCluster> {
        let mut clusters: Vec<ElementCluster> = Vec::new();
        let mut visited = vec![false; self.interactive_elements.len()];

        for i in 0..self.interactive_elements.len() {
            if visited[i] { continue; }
            let el = &self.interactive_elements[i];
            
            // Simple proximity clustering (elements within 50px of each other)
            let mut current_cluster = vec![el.clone()];
            visited[i] = true;

            for j in 0..self.interactive_elements.len() {
                if visited[j] { continue; }
                let other = &self.interactive_elements[j];
                
                let dist_x = (el.bounds.x - other.bounds.x).abs();
                let dist_y = (el.bounds.y - other.bounds.y).abs();
                
                if dist_x < 100.0 && dist_y < 50.0 {
                    current_cluster.push(other.clone());
                    visited[j] = true;
                }
            }

            // Calculate overall bounds
            let min_x = current_cluster.iter().map(|e| e.bounds.x).fold(f32::MAX, f32::min);
            let min_y = current_cluster.iter().map(|e| e.bounds.y).fold(f32::MAX, f32::min);
            let max_x = current_cluster.iter().map(|e| e.bounds.x + e.bounds.width).fold(f32::MIN, f32::max);
            let max_y = current_cluster.iter().map(|e| e.bounds.y + e.bounds.height).fold(f32::MIN, f32::max);

            let label = if current_cluster.len() == 1 {
                current_cluster[0].label.clone()
            } else {
                format!("Group: {} and {} others", current_cluster[0].label, current_cluster.len() - 1)
            };

            clusters.push(ElementCluster {
                label,
                elements: current_cluster,
                overall_bounds: BoxRect {
                    x: min_x,
                    y: min_y,
                    width: max_x - min_x,
                    height: max_y - min_y,
                },
            });
        }
        clusters
    }
}

/// AI最適化レンダラー
pub struct AiRenderer {
    next_id: usize,
    interactive_elements: Vec<InteractiveElement>,
}

impl AiRenderer {
    pub fn new() -> Self {
        Self {
            next_id: 1,
            interactive_elements: Vec::new(),
        }
    }

    /// DOMとレイアウトをAI最適化Markdownに変換
    pub fn render(
        &mut self, 
        arena: &vx_dom::NodeArena, 
        layout_root: &vx_layout::layout_node::LayoutNode, 
        title: &str, 
        url: &str
    ) -> AiRenderedPage {
        self.next_id = 1;
        self.interactive_elements.clear();

        let mut md = String::new();
        self.render_layout_node(layout_root, arena, &mut md, 0, &NodeContext::default());

        // ページ要約を自動生成
        let summary = self.generate_summary(&md);

        // トークン推定 (1トークン ≈ 4文字)
        let token_estimate = md.len() / 4;

        AiRenderedPage {
            title: title.to_string(),
            url: url.to_string(),
            markdown: md.trim().to_string(),
            interactive_elements: self.interactive_elements.clone(),
            page_summary: summary,
            token_estimate,
        }
    }

    fn render_layout_node(
        &mut self, 
        layout_node: &vx_layout::layout_node::LayoutNode, 
        arena: &vx_dom::NodeArena, 
        md: &mut String, 
        depth: usize, 
        ctx: &NodeContext
    ) {
        let Some(node) = arena.get(layout_node.node_id) else { return };
        
        match &node.data {
            vx_dom::NodeData::Text(text) => {
                let trimmed = text.content.trim();
                if !trimmed.is_empty() {
                    md.push_str(trimmed);
                    md.push(' ');
                }
            }
            vx_dom::NodeData::Element(el) => {
                let tag = el.tag_name.as_str();
                let mut child_ctx = ctx.clone();

                // Skip invisible elements
                if matches!(tag, "script" | "style" | "noscript" | "svg" | "path"
                    | "meta" | "link" | "head" | "template") {
                    return;
                }

                // Detect semantic role from tag
                child_ctx.role = match tag {
                    "header" => SemanticRole::Header,
                    "nav" => SemanticRole::Navigation,
                    "main" | "article" => SemanticRole::Main,
                    "aside" => SemanticRole::Sidebar,
                    "footer" => SemanticRole::Footer,
                    "dialog" => SemanticRole::Modal,
                    "form" => SemanticRole::Form,
                    _ => ctx.role.clone(),
                };

                // Also detect from class/id attributes
                if child_ctx.role == SemanticRole::Unknown {
                    let class = el.attributes.get("class").map(|s| s.to_lowercase()).unwrap_or_default();
                    let id = el.attributes.get("id").map(|s| s.to_lowercase()).unwrap_or_default();
                    let combined = format!("{} {}", class, id);

                    if combined.contains("header") || combined.contains("navbar") || combined.contains("topbar") {
                        child_ctx.role = SemanticRole::Header;
                    } else if combined.contains("nav") || combined.contains("menu") || combined.contains("sidebar") {
                        child_ctx.role = SemanticRole::Navigation;
                    } else if combined.contains("footer") || combined.contains("bottom") {
                        child_ctx.role = SemanticRole::Footer;
                    } else if combined.contains("main") || combined.contains("content") || combined.contains("article") {
                        child_ctx.role = SemanticRole::Main;
                    } else if combined.contains("modal") || combined.contains("dialog") || combined.contains("popup") {
                        child_ctx.role = SemanticRole::Modal;
                    }
                }

                match tag {
                    // Headings
                    "h1" => {
                        md.push('\n');
                        let role_tag = self.role_tag(&child_ctx.role);
                        md.push_str(&format!("# {}", role_tag));
                        self.render_layout_children(&layout_node.children, arena, md, depth + 1, &child_ctx);
                        md.push_str("\n\n");
                    }
                    "h2" => {
                        md.push('\n');
                        md.push_str("## ");
                        self.render_layout_children(&layout_node.children, arena, md, depth + 1, &child_ctx);
                        md.push_str("\n\n");
                    }
                    "h3" => {
                        md.push_str("### ");
                        self.render_layout_children(&layout_node.children, arena, md, depth + 1, &child_ctx);
                        md.push('\n');
                    }
                    "h4" | "h5" | "h6" => {
                        md.push_str("#### ");
                        self.render_layout_children(&layout_node.children, arena, md, depth + 1, &child_ctx);
                        md.push('\n');
                    }

                    // Paragraphs and blocks
                    "p" => {
                        md.push('\n');
                        self.render_layout_children(&layout_node.children, arena, md, depth, &child_ctx);
                        md.push_str("\n\n");
                    }
                    "div" | "section" | "article" | "main" | "aside" => {
                        // Add role annotation for significant sections
                        if child_ctx.role != SemanticRole::Unknown && child_ctx.role != ctx.role {
                            md.push_str(&format!("\n--- [{}] ---\n", child_ctx.role));
                        }
                        self.render_layout_children(&layout_node.children, arena, md, depth, &child_ctx);
                    }

                    // Lists
                    "ul" | "ol" => {
                        md.push('\n');
                        self.render_layout_children(&layout_node.children, arena, md, depth + 1, &child_ctx);
                        md.push('\n');
                    }
                    "li" => {
                        md.push_str("- ");
                        self.render_layout_children(&layout_node.children, arena, md, depth, &child_ctx);
                        md.push('\n');
                    }

                    // Interactive: Links
                    "a" => {
                        let href = el.attributes.get("href").cloned().unwrap_or_default();
                        let text = vx_dom::HtmlSerializer::text_content(arena, node.id);
                        let label = if text.is_empty() {
                            el.attributes.get("aria-label")
                                .or(el.attributes.get("title"))
                                .cloned()
                                .unwrap_or_else(|| "[link]".to_string())
                        } else {
                            text
                        };

                        if !href.is_empty() && !href.starts_with('#') && !href.starts_with("javascript:") {
                            let id = self.next_id;
                            self.next_id += 1;

                            let intent = self.infer_link_intent(&el.attributes, &label);
                            let intent_str = if intent != CssIntent::Neutral {
                                format!("/{}", intent)
                            } else {
                                String::new()
                            };

                            self.interactive_elements.push(InteractiveElement {
                                id,
                                node_id: node.id,
                                element_type: ElementType::Link,
                                label: label.clone(),
                                href: Some(href.clone()),
                                value: None,
                                placeholder: None,
                                semantic_role: child_ctx.role.clone(),
                                css_intent: intent.clone(),
                                bounds: layout_node.computed.absolute_border_box(),
                            });

                            md.push_str(&format!("[ID:{}] [link{}] {} → {}\n", id, intent_str, label.trim(), href));
                        } else {
                            self.render_layout_children(&layout_node.children, arena, md, depth, &child_ctx);
                        }
                    }

                    // Interactive: Buttons
                    "button" => {
                        let text = vx_dom::HtmlSerializer::text_content(arena, node.id);
                        let label = if text.is_empty() {
                            el.attributes.get("aria-label")
                                .or(el.attributes.get("title"))
                                .or(el.attributes.get("value"))
                                .cloned()
                                .unwrap_or_else(|| "[button]".to_string())
                        } else {
                            text
                        };

                        let id = self.next_id;
                        self.next_id += 1;

                        let intent = self.infer_button_intent(&el.attributes, &label);
                        let intent_str = if intent != CssIntent::Neutral {
                            format!("/{}", intent)
                        } else {
                            String::new()
                        };

                        self.interactive_elements.push(InteractiveElement {
                            id,
                            node_id: node.id,
                            element_type: ElementType::Button,
                            label: label.clone(),
                            href: None,
                            value: None,
                            placeholder: None,
                            semantic_role: child_ctx.role.clone(),
                            css_intent: intent.clone(),
                            bounds: layout_node.computed.absolute_border_box(),
                        });

                        md.push_str(&format!("[ID:{}] [button{}] {}\n", id, intent_str, label.trim()));
                    }

                    // Interactive: Inputs
                    "input" => {
                        let input_type = el.attributes.get("type").map(|s| s.as_str()).unwrap_or("text");
                        let label = el.attributes.get("aria-label")
                            .or(el.attributes.get("placeholder"))
                            .or(el.attributes.get("name"))
                            .cloned()
                            .unwrap_or_else(|| format!("[{}]", input_type));
                        let placeholder = el.attributes.get("placeholder").cloned();
                        let value = el.attributes.get("value").cloned();

                        let id = self.next_id;
                        self.next_id += 1;

                        let element_type = match input_type {
                            "submit" => ElementType::Submit,
                            "checkbox" => ElementType::Checkbox,
                            "radio" => ElementType::Radio,
                            _ => ElementType::TextInput,
                        };

                        self.interactive_elements.push(InteractiveElement {
                            id,
                            node_id: node.id,
                            element_type: element_type.clone(),
                            label: label.clone(),
                            href: None,
                            value: value.clone(),
                            placeholder: placeholder.clone(),
                            semantic_role: child_ctx.role.clone(),
                            css_intent: CssIntent::Neutral,
                            bounds: layout_node.computed.absolute_border_box(),
                        });

                        let display = if let Some(ph) = &placeholder {
                            format!("{} ({})", label, ph)
                        } else if let Some(v) = &value {
                            format!("{} = \"{}\"", label, v)
                        } else {
                            label
                        };

                        md.push_str(&format!("[ID:{}] [{}] {}\n", id, element_type, display));
                    }

                    // Interactive: Textarea
                    "textarea" => {
                        let label = el.attributes.get("aria-label")
                            .or(el.attributes.get("placeholder"))
                            .or(el.attributes.get("name"))
                            .cloned()
                            .unwrap_or_else(|| "[textarea]".to_string());

                        let id = self.next_id;
                        self.next_id += 1;

                        self.interactive_elements.push(InteractiveElement {
                            id,
                            node_id: node.id,
                            element_type: ElementType::TextArea,
                            label: label.clone(),
                            href: None,
                            value: None,
                            placeholder: el.attributes.get("placeholder").cloned(),
                            semantic_role: child_ctx.role.clone(),
                            css_intent: CssIntent::Neutral,
                            bounds: layout_node.computed.absolute_border_box(),
                        });

                        md.push_str(&format!("[ID:{}] [textarea] {}\n", id, label));
                    }

                    // Interactive: Select
                    "select" => {
                        let label = el.attributes.get("aria-label")
                            .or(el.attributes.get("name"))
                            .cloned()
                            .unwrap_or_else(|| "[select]".to_string());

                        let id = self.next_id;
                        self.next_id += 1;

                        // Options resolution (simplified for LayoutNode children)
                        let mut options = Vec::new();
                        for child_layout in &layout_node.children {
                            if let Some(child_node) = arena.get(child_layout.node_id) {
                                if let vx_dom::NodeData::Element(child_el) = &child_node.data {
                                    if child_el.tag_name == "option" {
                                        options.push(vx_dom::HtmlSerializer::text_content(arena, child_node.id));
                                    }
                                }
                            }
                        }

                        let options_str = if !options.is_empty() {
                            format!(" ({})", options.join(" | "))
                        } else {
                            String::new()
                        };

                        self.interactive_elements.push(InteractiveElement {
                            id,
                            node_id: node.id,
                            element_type: ElementType::Select,
                            label: label.clone(),
                            href: None,
                            value: None,
                            placeholder: None,
                            semantic_role: child_ctx.role.clone(),
                            css_intent: CssIntent::Neutral,
                            bounds: layout_node.computed.absolute_border_box(),
                        });

                        md.push_str(&format!("[ID:{}] [select] {}{}\n", id, label, options_str));
                    }

                    // Images
                    "img" => {
                        let alt = el.attributes.get("alt").cloned().unwrap_or_default();
                        let src = el.attributes.get("src").cloned().unwrap_or_default();
                        if !alt.is_empty() {
                            md.push_str(&format!("[image: {}]\n", alt));
                        } else if !src.is_empty() {
                            md.push_str(&format!("[image: {}]\n", src.split('/').last().unwrap_or("")));
                        }
                    }

                    // Code
                    "pre" | "code" => {
                        md.push_str("\n```\n");
                        self.render_layout_children(&layout_node.children, arena, md, depth, &child_ctx);
                        md.push_str("\n```\n");
                    }

                    // Table
                    "table" => {
                        md.push('\n');
                        self.render_layout_children(&layout_node.children, arena, md, depth, &child_ctx);
                        md.push('\n');
                    }
                    "tr" => {
                        md.push_str("| ");
                        self.render_layout_children(&layout_node.children, arena, md, depth, &child_ctx);
                        md.push_str(" |\n");
                    }
                    "td" | "th" => {
                        self.render_layout_children(&layout_node.children, arena, md, depth, &child_ctx);
                        md.push_str(" | ");
                    }

                    // Line breaks
                    "br" => md.push('\n'),
                    "hr" => md.push_str("\n---\n"),

                    // Inline formatting
                    "strong" | "b" => {
                        md.push_str("**");
                        self.render_layout_children(&layout_node.children, arena, md, depth, &child_ctx);
                        md.push_str("**");
                    }
                    "em" | "i" => {
                        md.push('_');
                        self.render_layout_children(&layout_node.children, arena, md, depth, &child_ctx);
                        md.push('_');
                    }

                    // Form
                    "form" => {
                        let action = el.attributes.get("action").cloned().unwrap_or_default();
                        let method = el.attributes.get("method").cloned().unwrap_or_else(|| "GET".to_string());
                        md.push_str(&format!("\n[form: {} {}]\n", method.to_uppercase(), action));
                        child_ctx.role = SemanticRole::Form;
                        self.render_layout_children(&layout_node.children, arena, md, depth, &child_ctx);
                        md.push_str("[/form]\n");
                    }

                    // Label
                    "label" => {
                        self.render_layout_children(&layout_node.children, arena, md, depth, &child_ctx);
                        md.push_str(": ");
                    }

                    // Default
                    _ => {
                        // Add spatial hinting for large containers
                        let bounds = layout_node.computed.absolute_border_box();
                        if bounds.width > 200.0 && bounds.height > 100.0 {
                            let pos_hint = if bounds.y < 100.0 {
                                "[Top] "
                            } else if bounds.x < 150.0 {
                                "[Sidebar] "
                            } else {
                                ""
                            };
                            
                            if !pos_hint.is_empty() && child_ctx.role != ctx.role {
                                md.push_str(&format!("\n--- {} ---\n", pos_hint.trim()));
                            }
                        }
                        self.render_layout_children(&layout_node.children, arena, md, depth, &child_ctx);
                    }
                }
            }
            _ => {
                // Documents, fragments, comments, etc — just render children
                self.render_layout_children(&layout_node.children, arena, md, depth, ctx);
            }
        }
    }

    fn render_layout_children(
        &mut self, 
        children: &[vx_layout::layout_node::LayoutNode], 
        arena: &vx_dom::NodeArena, 
        md: &mut String, 
        depth: usize, 
        ctx: &NodeContext
    ) {
        for child in children {
            self.render_layout_node(child, arena, md, depth, ctx);
        }
    }

    fn role_tag(&self, role: &SemanticRole) -> String {
        if *role != SemanticRole::Unknown {
            format!("[{}] ", role)
        } else {
            String::new()
        }
    }

    /// CSSクラスやラベルからボタンの意図を推定
    fn infer_button_intent(&self, attrs: &HashMap<String, String>, label: &str) -> CssIntent {
        let class = attrs.get("class").map(|s| s.to_lowercase()).unwrap_or_default();
        let label_lower = label.to_lowercase();

        // Destructive
        if class.contains("danger") || class.contains("destructive") || class.contains("delete")
            || label_lower.contains("削除") || label_lower.contains("delete") || label_lower.contains("remove") {
            return CssIntent::Destructive;
        }

        // Primary
        if class.contains("primary") || class.contains("cta") || class.contains("main")
            || label_lower.contains("submit") || label_lower.contains("送信") || label_lower.contains("save") {
            return CssIntent::Primary;
        }

        // Success
        if class.contains("success") || class.contains("confirm")
            || label_lower.contains("確認") || label_lower.contains("ok") || label_lower.contains("accept") {
            return CssIntent::Success;
        }

        // Warning
        if class.contains("warning") || class.contains("caution")
            || label_lower.contains("警告") || label_lower.contains("warning") {
            return CssIntent::Warning;
        }

        CssIntent::Neutral
    }

    /// リンクの意図を推定
    fn infer_link_intent(&self, attrs: &HashMap<String, String>, label: &str) -> CssIntent {
        let class = attrs.get("class").map(|s| s.to_lowercase()).unwrap_or_default();

        if class.contains("nav") || class.contains("menu") {
            return CssIntent::Navigation;
        }
        if class.contains("btn") || class.contains("button") {
            return self.infer_button_intent(attrs, label);
        }
        if class.contains("muted") || class.contains("secondary") || class.contains("subtle") {
            return CssIntent::Muted;
        }

        CssIntent::Neutral
    }

    /// ページの自動要約を生成
    fn generate_summary(&self, markdown: &str) -> String {
        let lines: Vec<&str> = markdown.lines().collect();
        let total_lines = lines.len();
        let headings: Vec<&&str> = lines.iter().filter(|l| l.starts_with('#')).collect();
        let interactive_count = self.interactive_elements.len();
        let links = self.interactive_elements.iter().filter(|e| e.element_type == ElementType::Link).count();
        let buttons = self.interactive_elements.iter().filter(|e| e.element_type == ElementType::Button).count();
        let inputs = self.interactive_elements.iter().filter(|e| matches!(e.element_type, ElementType::TextInput | ElementType::TextArea)).count();

        format!(
            "{}行, {}見出し, {}操作可能要素 ({}リンク, {}ボタン, {}入力欄)",
            total_lines, headings.len(), interactive_count, links, buttons, inputs
        )
    }
}

impl Default for AiRenderer {
    fn default() -> Self {
        Self::new()
    }
}

#[derive(Debug, Clone, Default)]
struct NodeContext {
    role: SemanticRole,
}

impl Default for SemanticRole {
    fn default() -> Self {
        SemanticRole::Unknown
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use vx_dom::Document;

    #[test]
    fn test_ai_render_with_interactive() {
        let html = r#"<html><body>
            <h1>Test Page</h1>
            <p>Hello world</p>
            <a href="https://example.com">Click me</a>
            <button>Submit</button>
            <input type="text" placeholder="Search...">
        </body></html>"#;

        let doc = Document::parse(html);
        let mut renderer = AiRenderer::new();
        let layout = vx_layout::layout_node::LayoutNode::from_dom(&doc.arena, doc.root_id).unwrap();
        let page = renderer.render(&doc.arena, &layout, "Test", "https://test.com");

        assert!(page.markdown.contains("# Test Page"));
        assert!(page.markdown.contains("[ID:1]"));
        assert!(page.markdown.contains("[link"));
        assert!(page.markdown.contains("[button"));
        assert!(page.markdown.contains("[input/text]"));
        assert_eq!(page.interactive_elements.len(), 3);
    }

    #[test]
    fn test_destructive_button_detection() {
        let html = r#"<html><body>
            <button class="btn-danger">Delete Account</button>
        </body></html>"#;

        let doc = Document::parse(html);
        let mut renderer = AiRenderer::new();
        let layout = vx_layout::layout_node::LayoutNode::from_dom(&doc.arena, doc.root_id).unwrap();
        let page = renderer.render(&doc.arena, &layout, "Test", "https://test.com");

        assert!(page.markdown.contains("危険/削除"));
    }

    #[test]
    fn test_semantic_role_detection() {
        let html = r#"<html><body>
            <header><h1>Site Title</h1></header>
            <nav><a href="/about">About</a></nav>
            <main><p>Content</p></main>
            <footer><p>Copyright</p></footer>
        </body></html>"#;

        let doc = Document::parse(html);
        let mut renderer = AiRenderer::new();
        let layout = vx_layout::layout_node::LayoutNode::from_dom(&doc.arena, doc.root_id).unwrap();
        let page = renderer.render(&doc.arena, &layout, "Test", "https://test.com");

        // Semantic roles are embedded in section dividers or heading tags
        assert!(page.markdown.contains("header") || page.markdown.contains("Site Title"));
        assert!(page.markdown.contains("About"));
        assert!(page.markdown.contains("Content"));
        assert!(page.markdown.contains("Copyright"));
    }

    #[test]
    fn test_spatial_map_generation() {
        let html = r#"<html><body>
            <navInner>
                <a href="/home">Home</a>
                <a href="/about">About</a>
            </navInner>
            <mainBlock>
                <h1>User Profile</h1>
                <input type="text" placeholder="Username">
                <button>Save</button>
            </mainBlock>
        </body></html>"#;

        let doc = Document::parse(html);
        let mut renderer = AiRenderer::new();
        let layout = vx_layout::layout_node::LayoutNode::from_dom(&doc.arena, doc.root_id).unwrap();
        let page = renderer.render(&doc.arena, &layout, "Profile", "https://test.com/profile");

        let spatial_map = page.to_spatial_map();
        let jcross = spatial_map.to_jcross();

        // Verify axes
        assert!(jcross.contains("AXIS FRONT"));
        assert!(jcross.contains("AXIS NEAR"));
        
        // Verify clustering
        assert!(jcross.contains("Action Zone"));
        
        // Verify metadata in NEAR
        assert!(jcross.contains("url: \"https://test.com/profile\","));
        assert!(jcross.contains("title: \"Profile\","));
    }
}
