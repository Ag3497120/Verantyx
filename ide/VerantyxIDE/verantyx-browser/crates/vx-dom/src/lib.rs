pub mod css;
pub mod node;
pub mod events;
pub mod manipulation;
pub mod w3c_tokenizer;
pub mod tree_builder;

pub use node::{NodeId, NodeData, NodeArena, NodeType, ElementData, TextData, CommentData, DoctypeData};
pub use events::{Event, EventTarget, EventDispatcher, EventPhase, EventListener};
pub use manipulation::{DomQuery, DomManipulation, HtmlSerializer, LiveCollection, NodeList};

use std::collections::HashMap;
use html5ever::tendril::TendrilSink;
use html5ever::{parse_document, ParseOpts};
use markup5ever_rcdom::{RcDom, NodeData as RcNodeData, Handle};

pub struct Document {
    pub arena: NodeArena,
    pub root_id: NodeId,
}

impl Document {
    pub fn parse(html: &str) -> Self {
        let mut arena = NodeArena::new();
        let dom = parse_document(RcDom::default(), ParseOpts::default())
            .from_utf8()
            .read_from(&mut html.as_bytes())
            .unwrap();

        let root_id = arena.document_id();
        Self::walk_rcdom(&dom.document, root_id, &mut arena);

        Self { arena, root_id }
    }

    fn walk_rcdom(rc_node: &Handle, parent_id: NodeId, arena: &mut NodeArena) {
        let node_id = match &rc_node.data {
            RcNodeData::Document => parent_id,
            RcNodeData::Doctype { name, public_id, system_id } => {
                let data = DoctypeData {
                    name: name.to_string(),
                    public_id: Some(public_id.to_string()),
                    system_id: Some(system_id.to_string()),
                };
                let id = arena.insert(node::Node::new(NodeData::Doctype(data)));
                arena.append_child(parent_id, id);
                id
            }
            RcNodeData::Text { contents } => {
                let text = contents.borrow().to_string();
                let id = arena.insert(node::Node::new(NodeData::Text(TextData { content: text })));
                arena.append_child(parent_id, id);
                id
            }
            RcNodeData::Comment { contents } => {
                let id = arena.insert(node::Node::new(NodeData::Comment(CommentData { content: contents.to_string() })));
                arena.append_child(parent_id, id);
                id
            }
            RcNodeData::Element { name, attrs, .. } => {
                let mut attributes = HashMap::new();
                for attr in attrs.borrow().iter() {
                    attributes.insert(attr.name.local.to_string(), attr.value.to_string());
                }
                let data = ElementData {
                    tag_name: name.local.to_string(),
                    attributes,
                    id_attr: None, // Will be populated by DomManipulation or similar
                    classes: Vec::new(), // Same
                    namespace_uri: Some(name.ns.to_string()),
                    prefix: None,
                };
                let id = arena.insert(node::Node::new(NodeData::Element(data)));
                arena.append_child(parent_id, id);
                id
            }
            _ => return,
        };

        for child in rc_node.children.borrow().iter() {
            Self::walk_rcdom(child, node_id, arena);
        }
    }
}
pub mod dom_parser;
