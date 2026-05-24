use std::collections::{HashMap, VecDeque};
use std::sync::atomic::{AtomicUsize, Ordering};
use serde::{Serialize, Deserialize};
use crate::events::EventTarget;

static NEXT_NODE_ID: AtomicUsize = AtomicUsize::new(1);

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, PartialOrd, Ord)]
pub struct NodeId(pub usize);

impl NodeId {
    pub fn new() -> Self {
        Self(NEXT_NODE_ID.fetch_add(1, Ordering::SeqCst))
    }
    pub fn root() -> Self { Self(0) }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum NodeType {
    Element = 1,
    Attribute = 2,
    Text = 3,
    CData = 4,
    ProcessingInstruction = 7,
    Comment = 8,
    Document = 9,
    DocumentType = 10,
    DocumentFragment = 11,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ElementData {
    pub tag_name: String,
    pub attributes: HashMap<String, String>,
    pub id_attr: Option<String>,
    pub classes: Vec<String>,
    pub namespace_uri: Option<String>,
    pub prefix: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TextData {
    pub content: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CommentData {
    pub content: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PIData {
    pub target: String,
    pub data: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DoctypeData {
    pub name: String,
    pub public_id: Option<String>,
    pub system_id: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum NodeData {
    Document,
    Element(ElementData),
    Text(TextData),
    Comment(CommentData),
    CData(String),
    ProcessingInstruction(PIData),
    Doctype(DoctypeData),
    DocumentFragment,
}

#[derive(Debug, Clone)]
pub struct Node {
    pub id: NodeId,
    pub data: NodeData,
    pub parent: Option<NodeId>,
    pub children: Vec<NodeId>,
    pub prev_sibling: Option<NodeId>,
    pub next_sibling: Option<NodeId>,
    pub owner_document: Option<NodeId>,
    pub event_target: EventTarget,
}

impl Node {
    pub fn new(data: NodeData) -> Self {
        Self {
            id: NodeId::new(),
            data,
            parent: None,
            children: Vec::new(),
            prev_sibling: None,
            next_sibling: None,
            owner_document: None,
            event_target: EventTarget::new(),
        }
    }

    pub fn node_type(&self) -> NodeType {
        match self.data {
            NodeData::Document => NodeType::Document,
            NodeData::Element(_) => NodeType::Element,
            NodeData::Text(_) => NodeType::Text,
            NodeData::Comment(_) => NodeType::Comment,
            NodeData::CData(_) => NodeType::CData,
            NodeData::ProcessingInstruction(_) => NodeType::ProcessingInstruction,
            NodeData::Doctype(_) => NodeType::DocumentType,
            NodeData::DocumentFragment => NodeType::DocumentFragment,
        }
    }

    pub fn is_element(&self) -> bool { matches!(self.data, NodeData::Element(_)) }
    pub fn is_text(&self) -> bool { matches!(self.data, NodeData::Text(_)) }
    
    pub fn tag_name(&self) -> Option<&str> {
        if let NodeData::Element(data) = &self.data {
            Some(&data.tag_name)
        } else {
            None
        }
    }
}

pub struct NodeArena {
    nodes: HashMap<NodeId, Node>,
    document_id: NodeId,
}

impl NodeArena {
    pub fn new() -> Self {
        let mut nodes = HashMap::new();
        let doc_id = NodeId(0);
        nodes.insert(doc_id, Node {
            id: doc_id,
            data: NodeData::Document,
            parent: None,
            children: Vec::new(),
            prev_sibling: None,
            next_sibling: None,
            owner_document: Some(doc_id),
            event_target: EventTarget::new(),
        });
        Self { nodes, document_id: doc_id }
    }

    pub fn get(&self, id: NodeId) -> Option<&Node> { self.nodes.get(&id) }
    pub fn get_mut(&mut self, id: NodeId) -> Option<&mut Node> { self.nodes.get_mut(&id) }
    pub fn document_id(&self) -> NodeId { self.document_id }

    pub fn insert(&mut self, node: Node) -> NodeId {
        let id = node.id;
        self.nodes.insert(id, node);
        id
    }

    /// Implement full append_child with sibling management
    pub fn append_child(&mut self, parent_id: NodeId, child_id: NodeId) {
        // 1. Remove from previous parent if exists
        self.remove_from_parent(child_id);

        // 2. Update siblings of the new child
        let last_child_id = self.nodes.get(&parent_id).and_then(|p| p.children.last().cloned());
        
        if let Some(mut child) = self.nodes.get_mut(&child_id) {
            child.parent = Some(parent_id);
            child.prev_sibling = last_child_id;
            child.next_sibling = None;
        }

        // 3. Update the former last child's next_sibling
        if let Some(last_id) = last_child_id {
            if let Some(last_node) = self.nodes.get_mut(&last_id) {
                last_node.next_sibling = Some(child_id);
            }
        }

        // 4. Record in parent's children list
        if let Some(parent) = self.nodes.get_mut(&parent_id) {
            parent.children.push(child_id);
        }
    }

    pub fn insert_before(&mut self, parent_id: NodeId, child_id: NodeId, ref_id: NodeId) {
        self.remove_from_parent(child_id);
        
        let mut prev_id = None;
        if let Some(ref_node) = self.nodes.get(&ref_id) {
            prev_id = ref_node.prev_sibling;
        }

        if let Some(child) = self.nodes.get_mut(&child_id) {
            child.parent = Some(parent_id);
            child.prev_sibling = prev_id;
            child.next_sibling = Some(ref_id);
        }

        if let Some(prev) = prev_id {
            if let Some(p_node) = self.nodes.get_mut(&prev) {
                p_node.next_sibling = Some(child_id);
            }
        }

        if let Some(ref_node) = self.nodes.get_mut(&ref_id) {
            ref_node.prev_sibling = Some(child_id);
        }

        if let Some(parent) = self.nodes.get_mut(&parent_id) {
            if let Some(pos) = parent.children.iter().position(|&x| x == ref_id) {
                parent.children.insert(pos, child_id);
            } else {
                parent.children.push(child_id);
            }
        }
    }

    pub fn remove_child(&mut self, parent_id: NodeId, child_id: NodeId) -> Option<Node> {
        let mut node = self.nodes.remove(&child_id)?;
        
        let prev = node.prev_sibling;
        let next = node.next_sibling;

        if let Some(p) = prev {
            if let Some(p_node) = self.nodes.get_mut(&p) {
                p_node.next_sibling = next;
            }
        }

        if let Some(n) = next {
            if let Some(n_node) = self.nodes.get_mut(&n) {
                n_node.prev_sibling = prev;
            }
        }

        if let Some(parent) = self.nodes.get_mut(&parent_id) {
            parent.children.retain(|&x| x != child_id);
        }

        node.parent = None;
        node.prev_sibling = None;
        node.next_sibling = None;

        Some(node)
    }

    fn remove_from_parent(&mut self, child_id: NodeId) {
        let parent_id = self.nodes.get(&child_id).and_then(|c| c.parent);
        if let Some(p_id) = parent_id {
            self.remove_child(p_id, child_id);
        }
    }
}
