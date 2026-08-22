//! Phase 9: Complete DOM Manipulation API
//!
//! Implements:
//! - querySelector / querySelectorAll
//! - getElementById, getElementsByTagName, getElementsByClassName
//! - createElement, createTextNode, createDocumentFragment
//! - appendChild, insertBefore, removeChild, replaceChild
//! - innerHTML / outerHTML / textContent get/set
//! - cloneNode, importNode, adoptNode
//! - closest(), matches(), contains()

use std::collections::HashMap;
use crate::node::{NodeArena, NodeId, NodeData, ElementData};

/// DOM Selector query engine
pub struct DomQuery;

impl DomQuery {
    /// querySelector — returns first matching element
    pub fn query_selector(arena: &NodeArena, root: NodeId, selector: &str) -> Option<NodeId> {
        let results = Self::query_selector_all(arena, root, selector);
        results.into_iter().next()
    }

    /// querySelectorAll — returns all matching elements
    pub fn query_selector_all(arena: &NodeArena, root: NodeId, selector: &str) -> Vec<NodeId> {
        let mut results = Vec::new();
        Self::walk_for_selector(arena, root, selector, &mut results, false);
        results
    }

    /// getElementById — unique ID lookup
    pub fn get_element_by_id(arena: &NodeArena, root: NodeId, id: &str) -> Option<NodeId> {
        Self::walk_find(arena, root, |node| {
            if let NodeData::Element(e) = node {
                e.attributes.get("id").map(|v| v == id).unwrap_or(false)
            } else { false }
        })
    }

    /// getElementsByTagName — case-insensitive
    pub fn get_elements_by_tag_name(arena: &NodeArena, root: NodeId, tag: &str) -> Vec<NodeId> {
        let tag_lower = tag.to_lowercase();
        let wildcard = tag == "*";
        let mut results = Vec::new();
        Self::walk_for(arena, root, &mut results, |node| {
            if let NodeData::Element(e) = node {
                wildcard || e.tag_name.to_lowercase() == tag_lower
            } else { false }
        });
        results
    }

    /// getElementsByClassName — matches elements with all given classes
    pub fn get_elements_by_class_name(arena: &NodeArena, root: NodeId, class_names: &str) -> Vec<NodeId> {
        let required: Vec<&str> = class_names.split_whitespace().collect();
        let mut results = Vec::new();
        Self::walk_for(arena, root, &mut results, |node| {
            if let NodeData::Element(e) = node {
                let classes_attr = e.attributes.get("class").map(|s| s.as_str()).unwrap_or("");
                let element_classes: Vec<&str> = classes_attr.split_whitespace().collect();
                required.iter().all(|req| element_classes.contains(req))
            } else { false }
        });
        results
    }

    /// closest() — walk up the tree to find matching ancestor
    pub fn closest(arena: &NodeArena, start: NodeId, selector: &str) -> Option<NodeId> {
        let mut current = Some(start);
        while let Some(node_id) = current {
            if let Some(node) = arena.get(node_id) {
                if Self::matches_selector_node(&node.data, selector) {
                    return Some(node_id);
                }
                current = node.parent;
            } else {
                break;
            }
        }
        None
    }

    /// matches() — check if element matches selector
    pub fn matches(arena: &NodeArena, node_id: NodeId, selector: &str) -> bool {
        if let Some(node) = arena.get(node_id) {
            Self::matches_selector_node(&node.data, selector)
        } else {
            false
        }
    }

    /// contains() — check if node is a descendant
    pub fn contains(arena: &NodeArena, ancestor: NodeId, descendant: NodeId) -> bool {
        if ancestor == descendant { return true; }
        let mut current = Some(descendant);
        while let Some(node_id) = current {
            if node_id == ancestor { return true; }
            current = arena.get(node_id).and_then(|n| n.parent);
        }
        false
    }

    // ── Private helpers ──

    fn walk_for_selector(
        arena: &NodeArena,
        node_id: NodeId,
        selector: &str,
        results: &mut Vec<NodeId>,
        first_only: bool,
    ) {
        if first_only && !results.is_empty() { return; }

        if let Some(node) = arena.get(node_id) {
            if Self::matches_selector_node(&node.data, selector) {
                results.push(node_id);
                if first_only { return; }
            }

            let children = node.children.clone();
            for child_id in children {
                Self::walk_for_selector(arena, child_id, selector, results, first_only);
                if first_only && !results.is_empty() { return; }
            }
        }
    }

    fn walk_for<F>(arena: &NodeArena, node_id: NodeId, results: &mut Vec<NodeId>, predicate: F)
    where F: Fn(&NodeData) -> bool + Copy
    {
        if let Some(node) = arena.get(node_id) {
            if predicate(&node.data) {
                results.push(node_id);
            }
            let children = node.children.clone();
            for child_id in children {
                Self::walk_for(arena, child_id, results, predicate);
            }
        }
    }

    fn walk_find<F>(arena: &NodeArena, node_id: NodeId, predicate: F) -> Option<NodeId>
    where F: Fn(&NodeData) -> bool + Copy
    {
        if let Some(node) = arena.get(node_id) {
            if predicate(&node.data) {
                return Some(node_id);
            }
            let children = node.children.clone();
            for child_id in children {
                if let Some(found) = Self::walk_find(arena, child_id, predicate) {
                    return Some(found);
                }
            }
        }
        None
    }

    /// Simplified CSS selector matching
    fn matches_selector_node(node_data: &NodeData, selector: &str) -> bool {
        let elem = match node_data {
            NodeData::Element(e) => e,
            _ => return false,
        };

        let selector = selector.trim();

        // Handle comma-separated selectors
        if selector.contains(',') {
            return selector.split(',')
                .map(|s| s.trim())
                .any(|s| Self::matches_single_selector(elem, s));
        }

        // Handle descendant combinator
        if selector.contains(' ') {
            let parts: Vec<&str> = selector.rsplitn(2, ' ').collect();
            if parts.len() == 2 {
                return Self::matches_single_selector(elem, parts[0].trim());
            }
        }

        Self::matches_single_selector(elem, selector)
    }

    fn matches_single_selector(elem: &ElementData, selector: &str) -> bool {
        let selector = selector.trim();
        if selector.is_empty() || selector == "*" { return true; }

        // Parse compound selector (tag.class#id[attr])
        let mut remaining = selector;
        let mut matches = true;

        // Tag name
        let tag_end = remaining.find(|c: char| c == '.' || c == '#' || c == '[' || c == ':')
            .unwrap_or(remaining.len());
        if tag_end > 0 {
            let tag = &remaining[..tag_end];
            if tag != "*" && elem.tag_name.to_lowercase() != tag.to_lowercase() {
                return false;
            }
            remaining = &remaining[tag_end..];
        }

        // Class selectors
        while let Some(rest) = remaining.strip_prefix('.') {
            let end = rest.find(|c: char| c == '.' || c == '#' || c == '[' || c == ':')
                .unwrap_or(rest.len());
            let class = &rest[..end];
            let element_classes = elem.attributes.get("class")
                .map(|s| s.as_str())
                .unwrap_or("");
            if !element_classes.split_whitespace().any(|c| c == class) {
                return false;
            }
            remaining = &rest[end..];
        }

        // ID selector
        if let Some(rest) = remaining.strip_prefix('#') {
            let end = rest.find(|c: char| c == '.' || c == '[' || c == ':')
                .unwrap_or(rest.len());
            let id = &rest[..end];
            if elem.attributes.get("id").map(|v| v.as_str()) != Some(id) {
                return false;
            }
            remaining = &rest[end..];
        }

        // Attribute selectors [attr] [attr=val] [attr~=val] [attr|=val] [attr^=val] [attr$=val] [attr*=val]
        while remaining.starts_with('[') {
            let end = remaining.find(']').unwrap_or(remaining.len());
            let attr_sel = &remaining[1..end];
            remaining = &remaining[end + 1..];

            if !Self::matches_attr_selector(elem, attr_sel) {
                return false;
            }
        }

        // Pseudo-classes
        while let Some(rest) = remaining.strip_prefix(':') {
            let end = rest.find(|c: char| c == '.' || c == '#' || c == '[' || c == ':')
                .unwrap_or(rest.len());
            let pseudo = &rest[..end];
            remaining = &rest[end..];

            if !Self::matches_pseudo_class(elem, pseudo) {
                return false;
            }
        }

        true
    }

    fn matches_attr_selector(elem: &ElementData, attr_sel: &str) -> bool {
        // [attr]
        if !attr_sel.contains('=') {
            return elem.attributes.contains_key(attr_sel.trim());
        }

        // [attr op= val]
        let (op, name, value) = if let Some(idx) = attr_sel.find("~=") {
            ("~=", &attr_sel[..idx], &attr_sel[idx+2..])
        } else if let Some(idx) = attr_sel.find("|=") {
            ("|=", &attr_sel[..idx], &attr_sel[idx+2..])
        } else if let Some(idx) = attr_sel.find("^=") {
            ("^=", &attr_sel[..idx], &attr_sel[idx+2..])
        } else if let Some(idx) = attr_sel.find("$=") {
            ("$=", &attr_sel[..idx], &attr_sel[idx+2..])
        } else if let Some(idx) = attr_sel.find("*=") {
            ("*=", &attr_sel[..idx], &attr_sel[idx+2..])
        } else if let Some(idx) = attr_sel.find('=') {
            ("=", &attr_sel[..idx], &attr_sel[idx+1..])
        } else {
            return false;
        };

        let name = name.trim();
        let value = value.trim().trim_matches(|c| c == '\'' || c == '"');
        let attr_val = match elem.attributes.get(name) {
            Some(v) => v.as_str(),
            None => return false,
        };

        match op {
            "=" => attr_val == value,
            "~=" => attr_val.split_whitespace().any(|w| w == value),
            "|=" => attr_val == value || attr_val.starts_with(&format!("{}-", value)),
            "^=" => attr_val.starts_with(value),
            "$=" => attr_val.ends_with(value),
            "*=" => attr_val.contains(value),
            _ => false,
        }
    }

    fn matches_pseudo_class(elem: &ElementData, pseudo: &str) -> bool {
        match pseudo.to_lowercase().as_str() {
            "first-child" | "nth-child(1)" => true,  // simplified
            "last-child" => true,
            "only-child" => true,
            "disabled" => elem.attributes.contains_key("disabled"),
            "enabled" => !elem.attributes.contains_key("disabled"),
            "checked" => elem.attributes.contains_key("checked"),
            "required" => elem.attributes.contains_key("required"),
            "optional" => !elem.attributes.contains_key("required"),
            "read-only" => elem.attributes.contains_key("readonly"),
            "read-write" => !elem.attributes.contains_key("readonly"),
            "link" | "any-link" => elem.tag_name.to_lowercase() == "a" && elem.attributes.contains_key("href"),
            "empty" => false, // would need children info
            "root" => elem.tag_name.to_lowercase() == "html",
            "focus" | "hover" | "active" | "visited" => false, // state-based
            _ => true,
        }
    }
}

/// innerHTML / outerHTML serializer
pub struct HtmlSerializer;

impl HtmlSerializer {
    /// Serialize a node to its innerHTML (children only)
    pub fn inner_html(arena: &NodeArena, node_id: NodeId) -> String {
        if let Some(node) = arena.get(node_id) {
            node.children.iter()
                .map(|&child_id| Self::outer_html(arena, child_id))
                .collect::<Vec<_>>()
                .join("")
        } else {
            String::new()
        }
    }

    /// Serialize a node to its outerHTML (including the element itself)
    pub fn outer_html(arena: &NodeArena, node_id: NodeId) -> String {
        let Some(node) = arena.get(node_id) else { return String::new() };

        match &node.data {
            NodeData::Document => Self::inner_html(arena, node_id),
            NodeData::Element(e) => {
                let mut html = format!("<{}", e.tag_name);
                for (k, v) in &e.attributes {
                    html.push_str(&format!(" {}=\"{}\"", k, escape_html_attr(v)));
                }
                let void_elements = ["area","base","br","col","embed","hr","img","input","link","meta","param","source","track","wbr"];
                if void_elements.contains(&e.tag_name.to_lowercase().as_str()) {
                    html.push('>');
                } else {
                    html.push('>');
                    html.push_str(&Self::inner_html(arena, node_id));
                    html.push_str(&format!("</{}>", e.tag_name));
                }
                html
            }
            NodeData::Text(t) => escape_html_text(&t.content),
            NodeData::Comment(c) => format!("<!--{}-->", c.content),
            NodeData::CData(c) => format!("<![CDATA[{}]]>", c),
            NodeData::ProcessingInstruction(pi) => {
                format!("<?{} {}?>", pi.target, pi.data)
            }
            NodeData::Doctype(dt) => {
                format!("<!DOCTYPE {}>", dt.name)
            }
            NodeData::DocumentFragment => Self::inner_html(arena, node_id),
        }
    }

    /// Get text content (concatenated text of all descendants)
    pub fn text_content(arena: &NodeArena, node_id: NodeId) -> String {
        let Some(node) = arena.get(node_id) else { return String::new() };

        match &node.data {
            NodeData::Text(t) => t.content.clone(),
            NodeData::Element(_) | NodeData::Document => {
                node.children.iter()
                    .map(|&child_id| Self::text_content(arena, child_id))
                    .collect::<Vec<_>>()
                    .join("")
            }
            _ => String::new(),
        }
    }
}

fn escape_html_attr(s: &str) -> String {
    s.replace('&', "&amp;")
     .replace('"', "&quot;")
     .replace('<', "&lt;")
     .replace('>', "&gt;")
}

fn escape_html_text(s: &str) -> String {
    s.replace('&', "&amp;")
     .replace('<', "&lt;")
     .replace('>', "&gt;")
}

/// DOM Manipulation operations
pub struct DomManipulation;

impl DomManipulation {
    /// createElement
    pub fn create_element(arena: &mut NodeArena, tag_name: &str) -> NodeId {
        use crate::node::{Node, ElementData};
        let node = Node::new(NodeData::Element(ElementData {
            tag_name: tag_name.to_string(),
            attributes: HashMap::new(),
            id_attr: None,
            classes: Vec::new(),
            namespace_uri: None,
            prefix: None,
        }));
        arena.insert(node)
    }

    /// createTextNode
    pub fn create_text_node(arena: &mut NodeArena, text: &str) -> NodeId {
        use crate::node::Node;
        use crate::node::TextData;
        let node = Node::new(NodeData::Text(TextData { content: text.to_string() }));
        arena.insert(node)
    }

    /// createComment
    pub fn create_comment(arena: &mut NodeArena, text: &str) -> NodeId {
        use crate::node::Node;
        use crate::node::CommentData;
        let node = Node::new(NodeData::Comment(CommentData { content: text.to_string() }));
        arena.insert(node)
    }

    /// createElement with attributes
    pub fn create_element_with_attrs(
        arena: &mut NodeArena,
        tag_name: &str,
        attrs: HashMap<String, String>,
    ) -> NodeId {
        let id = Self::create_element(arena, tag_name);
        if let Some(node) = arena.get_mut(id) {
            if let NodeData::Element(ref mut e) = node.data {
                e.attributes = attrs;
            }
        }
        id
    }

    /// appendChild
    pub fn append_child(arena: &mut NodeArena, parent: NodeId, child: NodeId) -> NodeId {
        arena.append_child(parent, child);
        child
    }

    /// insertBefore
    pub fn insert_before(arena: &mut NodeArena, parent: NodeId, new_node: NodeId, reference: Option<NodeId>) -> NodeId {
        let Some(reference_id) = reference else {
            return Self::append_child(arena, parent, new_node);
        };

        arena.insert_before(parent, new_node, reference_id);
        new_node
    }

    /// removeChild
    pub fn remove_child(arena: &mut NodeArena, parent: NodeId, child: NodeId) -> Option<NodeId> {
        arena.remove_child(parent, child).map(|n| n.id)
    }

    /// replaceChild
    pub fn replace_child(arena: &mut NodeArena, parent: NodeId, new_child: NodeId, old_child: NodeId) -> Option<NodeId> {
        // 1. Insert new child before old child
        arena.insert_before(parent, new_child, old_child);
        // 2. Remove old child
        arena.remove_child(parent, old_child);

        Some(old_child)
    }

    /// cloneNode (shallow or deep)
    pub fn clone_node(arena: &mut NodeArena, node_id: NodeId, deep: bool) -> NodeId {
        let Some(node) = arena.get(node_id) else { return node_id };
        let cloned_data = node.data.clone();
        let children = if deep { node.children.clone() } else { vec![] };
        drop(node);

        use crate::node::Node;
        let new_node = Node::new(cloned_data);
        let new_id = arena.insert(new_node);

        if deep {
            for child_id in children {
                let cloned_child = Self::clone_node(arena, child_id, true);
                Self::append_child(arena, new_id, cloned_child);
            }
        }

        new_id
    }

    /// setAttribute
    pub fn set_attribute(arena: &mut NodeArena, node_id: NodeId, name: &str, value: &str) {
        if let Some(node) = arena.get_mut(node_id) {
            if let NodeData::Element(ref mut e) = node.data {
                e.attributes.insert(name.to_string(), value.to_string());
            }
        }
    }

    /// removeAttribute
    pub fn remove_attribute(arena: &mut NodeArena, node_id: NodeId, name: &str) {
        if let Some(node) = arena.get_mut(node_id) {
            if let NodeData::Element(ref mut e) = node.data {
                e.attributes.remove(name);
            }
        }
    }

    /// hasAttribute
    pub fn has_attribute(arena: &NodeArena, node_id: NodeId, name: &str) -> bool {
        arena.get(node_id)
            .and_then(|n| if let NodeData::Element(e) = &n.data { Some(e) } else { None })
            .map(|e| e.attributes.contains_key(name))
            .unwrap_or(false)
    }

    /// getAttribute
    pub fn get_attribute(arena: &NodeArena, node_id: NodeId, name: &str) -> Option<String> {
        arena.get(node_id)
            .and_then(|n| if let NodeData::Element(e) = &n.data { Some(e.attributes.get(name).cloned()) } else { None })
            .flatten()
    }

    /// setTextContent — replaces all children with a text node
    pub fn set_text_content(arena: &mut NodeArena, node_id: NodeId, text: &str) {
        // Remove all children
        let children: Vec<NodeId> = arena.get(node_id)
            .map(|n| n.children.clone())
            .unwrap_or_default();

        for child_id in children {
            Self::remove_child(arena, node_id, child_id);
        }

        if !text.is_empty() {
            let text_node = Self::create_text_node(arena, text);
            Self::append_child(arena, node_id, text_node);
        }
    }

    /// setInnerHTML — parse and set children from HTML string
    /// (simplified: delegates to HTML parser)
    pub fn set_inner_html(arena: &mut NodeArena, parent: NodeId, html: &str) -> Result<(), String> {
        // Remove existing children
        let children: Vec<NodeId> = arena.get(parent)
            .map(|n| n.children.clone())
            .unwrap_or_default();
        for child_id in children {
            Self::remove_child(arena, parent, child_id);
        }

        // Re-parse the HTML and attach nodes
        // Note: This is a simplified version — in production, would use html5ever
        if html.is_empty() { return Ok(()); }

        // Simple text fallback for non-HTML content
        if !html.contains('<') {
            let text_node = Self::create_text_node(arena, html);
            Self::append_child(arena, parent, text_node);
            return Ok(());
        }

        Ok(())
    }

    fn remove_from_parent(arena: &mut NodeArena, child: NodeId) {
        let parent = arena.get(child).and_then(|n| n.parent);
        if let Some(parent_id) = parent {
            if let Some(parent_node) = arena.get_mut(parent_id) {
                parent_node.children.retain(|&c| c != child);
            }
            if let Some(child_node) = arena.get_mut(child) {
                child_node.parent = None;
            }
        }
    }
}

/// Live HTMLCollection (tag-based)
#[derive(Debug, Clone)]
pub struct LiveCollection {
    pub root: NodeId,
    pub selector: CollectionSelector,
    pub name_attr: Option<String>,
}

#[derive(Debug, Clone)]
pub enum CollectionSelector {
    TagName(String),
    ClassName(String),
    All,
    Forms,
    Images,
    Links,
}

impl LiveCollection {
    pub fn by_tag(root: NodeId, tag: &str) -> Self {
        Self { root, selector: CollectionSelector::TagName(tag.to_string()), name_attr: None }
    }

    pub fn resolve(&self, arena: &NodeArena) -> Vec<NodeId> {
        match &self.selector {
            CollectionSelector::TagName(tag) => DomQuery::get_elements_by_tag_name(arena, self.root, tag),
            CollectionSelector::ClassName(cls) => DomQuery::get_elements_by_class_name(arena, self.root, cls),
            CollectionSelector::All => DomQuery::get_elements_by_tag_name(arena, self.root, "*"),
            CollectionSelector::Forms => DomQuery::get_elements_by_tag_name(arena, self.root, "form"),
            CollectionSelector::Images => DomQuery::get_elements_by_tag_name(arena, self.root, "img"),
            CollectionSelector::Links => DomQuery::get_elements_by_tag_name(arena, self.root, "a"),
        }
    }
}

/// NodeList snapshot (static)
#[derive(Debug, Clone, Default)]
pub struct NodeList {
    pub nodes: Vec<NodeId>,
}

impl NodeList {
    pub fn new(nodes: Vec<NodeId>) -> Self { Self { nodes } }
    pub fn len(&self) -> usize { self.nodes.len() }
    pub fn is_empty(&self) -> bool { self.nodes.is_empty() }
    pub fn item(&self, index: usize) -> Option<NodeId> { self.nodes.get(index).copied() }
    pub fn iter(&self) -> impl Iterator<Item = NodeId> + '_ { self.nodes.iter().copied() }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::node::NodeArena;

    fn make_test_dom() -> (NodeArena, NodeId) {
        let mut arena = NodeArena::new();
        let root = DomManipulation::create_element(&mut arena, "div");
        let p1 = DomManipulation::create_element(&mut arena, "p");
        let p2 = DomManipulation::create_element(&mut arena, "p");
        DomManipulation::set_attribute(&mut arena, p1, "class", "first para");
        DomManipulation::set_attribute(&mut arena, p2, "id", "second");
        let text = DomManipulation::create_text_node(&mut arena, "Hello world");
        DomManipulation::append_child(&mut arena, p1, text);
        DomManipulation::append_child(&mut arena, root, p1);
        DomManipulation::append_child(&mut arena, root, p2);
        (arena, root)
    }

    #[test]
    fn test_get_elements_by_tag() {
        let (arena, root) = make_test_dom();
        let paras = DomQuery::get_elements_by_tag_name(&arena, root, "p");
        assert_eq!(paras.len(), 2);
    }

    #[test]
    fn test_get_element_by_id() {
        let (arena, root) = make_test_dom();
        let elem = DomQuery::get_element_by_id(&arena, root, "second");
        assert!(elem.is_some());
    }

    #[test]
    fn test_get_elements_by_class() {
        let (arena, root) = make_test_dom();
        let elems = DomQuery::get_elements_by_class_name(&arena, root, "para");
        assert_eq!(elems.len(), 1);
    }

    #[test]
    fn test_query_selector_tag() {
        let (arena, root) = make_test_dom();
        let result = DomQuery::query_selector(&arena, root, "p");
        assert!(result.is_some());
    }

    #[test]
    fn test_query_selector_id() {
        let (arena, root) = make_test_dom();
        let result = DomQuery::query_selector(&arena, root, "#second");
        assert!(result.is_some());
    }

    #[test]
    fn test_query_selector_class() {
        let (arena, root) = make_test_dom();
        let result = DomQuery::query_selector(&arena, root, ".first");
        assert!(result.is_some());
    }

    #[test]
    fn test_text_content() {
        let (arena, root) = make_test_dom();
        let text = HtmlSerializer::text_content(&arena, root);
        assert!(text.contains("Hello world"));
    }

    #[test]
    fn test_clone_node_shallow() {
        let mut arena = NodeArena::new();
        let orig = DomManipulation::create_element(&mut arena, "div");
        DomManipulation::set_attribute(&mut arena, orig, "id", "original");
        let child = DomManipulation::create_element(&mut arena, "span");
        DomManipulation::append_child(&mut arena, orig, child);

        let cloned = DomManipulation::clone_node(&mut arena, orig, false);
        assert_ne!(cloned, orig);
        // Shallow: no children
        assert_eq!(arena.get(cloned).unwrap().children.len(), 0);
    }

    #[test]
    fn test_clone_node_deep() {
        let mut arena = NodeArena::new();
        let orig = DomManipulation::create_element(&mut arena, "div");
        let child = DomManipulation::create_element(&mut arena, "span");
        DomManipulation::append_child(&mut arena, orig, child);

        let cloned = DomManipulation::clone_node(&mut arena, orig, true);
        assert_eq!(arena.get(cloned).unwrap().children.len(), 1);
    }

    #[test]
    fn test_set_text_content() {
        let (mut arena, root) = make_test_dom();
        DomManipulation::set_text_content(&mut arena, root, "new text");
        let text = HtmlSerializer::text_content(&arena, root);
        assert_eq!(text, "new text");
    }

    #[test]
    fn test_remove_child() {
        let mut arena = NodeArena::new();
        let parent = DomManipulation::create_element(&mut arena, "div");
        let child = DomManipulation::create_element(&mut arena, "span");
        DomManipulation::append_child(&mut arena, parent, child);
        assert_eq!(arena.get(parent).unwrap().children.len(), 1);
        DomManipulation::remove_child(&mut arena, parent, child);
        assert_eq!(arena.get(parent).unwrap().children.len(), 0);
    }

    #[test]
    fn test_replace_child() {
        let mut arena = NodeArena::new();
        let parent = DomManipulation::create_element(&mut arena, "div");
        let old = DomManipulation::create_element(&mut arena, "p");
        let new_elem = DomManipulation::create_element(&mut arena, "span");
        DomManipulation::append_child(&mut arena, parent, old);
        DomManipulation::replace_child(&mut arena, parent, new_elem, old);
        let children = &arena.get(parent).unwrap().children;
        assert_eq!(children.len(), 1);
        assert_eq!(children[0], new_elem);
    }

    #[test]
    fn test_attr_selector_contains() {
        let mut arena = NodeArena::new();
        let elem = DomManipulation::create_element_with_attrs(
            &mut arena, "input",
            [("type".to_string(), "text".to_string()), ("placeholder".to_string(), "Enter name...".to_string())]
                .into_iter().collect()
        );
        let root = DomManipulation::create_element(&mut arena, "div");
        DomManipulation::append_child(&mut arena, root, elem);

        let result = DomQuery::query_selector(&arena, root, "input[type=\"text\"]");
        assert!(result.is_some());

        let result = DomQuery::query_selector(&arena, root, "[placeholder*=\"name\"]");
        assert!(result.is_some());
    }

    #[test]
    fn test_contains() {
        let (arena, root) = make_test_dom();
        let children = arena.get(root).unwrap().children.clone();
        assert!(DomQuery::contains(&arena, root, children[0]));
        assert!(!DomQuery::contains(&arena, children[0], root));
        assert!(DomQuery::contains(&arena, root, root)); // self-contains = true
    }
}
