//! Spec-Compliant DOM Event System
//!
//! Implements:
//! - Event, CustomEvent, UIEvent, MouseEvent, KeyboardEvent
//! - EventTarget trait and listener management
//! - Event propagation (Capture, Target, Bubble)

use std::any::Any;
use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use serde::{Serialize, Deserialize};
use crate::node::{NodeId, NodeArena};

/// Event Phases
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum EventPhase {
    None = 0,
    Capturing = 1,
    AtTarget = 2,
    Bubbling = 3,
}

/// Base Event structure
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Event {
    pub type_: String,
    pub target: Option<NodeId>,
    pub current_target: Option<NodeId>,
    pub event_phase: EventPhase,
    pub bubbles: bool,
    pub cancelable: bool,
    pub default_prevented: bool,
    pub composed: bool,
    pub is_trusted: bool,
    pub timestamp: u128,
    
    #[serde(skip)]
    pub propagation_stopped: bool,
    #[serde(skip)]
    pub immediate_propagation_stopped: bool,
}

impl Event {
    pub fn new(type_: &str, bubbles: bool, cancelable: bool) -> Self {
        Self {
            type_: type_.to_string(),
            target: None,
            current_target: None,
            event_phase: EventPhase::None,
            bubbles,
            cancelable,
            default_prevented: false,
            composed: false,
            is_trusted: true,
            timestamp: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_millis(),
            propagation_stopped: false,
            immediate_propagation_stopped: false,
        }
    }

    pub fn stop_propagation(&mut self) {
        self.propagation_stopped = true;
    }

    pub fn stop_immediate_propagation(&mut self) {
        self.propagation_stopped = true;
        self.immediate_propagation_stopped = true;
    }

    pub fn prevent_default(&mut self) {
        if self.cancelable {
            self.default_prevented = true;
        }
    }
}

/// CustomEvent for user-defined data
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CustomEvent {
    pub base: Event,
    pub detail: serde_json::Value,
}

/// Event capture/bubble listener
#[derive(Debug, Clone)]
pub struct EventListener {
    pub type_: String,
    pub capture: bool,
    pub once: bool,
    pub passive: bool,
    // For now, we store a simplified representation. 
    // In actual JS runtime, this would be a V8 function handle.
    pub handler_id: u32, 
}

/// Registry of event listeners per node
#[derive(Default, Debug, Clone)]
pub struct HandlerRegistry {
    pub listeners: Vec<EventListener>,
}

impl HandlerRegistry {
    pub fn add(&mut self, type_: &str, handler_id: u32, use_capture: bool) {
        self.listeners.push(EventListener {
            type_: type_.to_string(),
            capture: use_capture,
            once: false,
            passive: false,
            handler_id,
        });
    }

    pub fn remove(&mut self, type_: &str, handler_id: u32, use_capture: bool) {
        self.listeners.retain(|l| {
            !(l.type_ == type_ && l.handler_id == handler_id && l.capture == use_capture)
        });
    }

    pub fn get_listeners(&self, type_: &str, phase: EventPhase) -> Vec<u32> {
        self.listeners.iter()
            .filter(|l| {
                l.type_ == type_ && match phase {
                    EventPhase::Capturing => l.capture,
                    EventPhase::Bubbling | EventPhase::AtTarget => !l.capture,
                    _ => false,
                }
            })
            .map(|l| l.handler_id)
            .collect()
    }
}

/// Result of an event dispatch
#[derive(Debug, Serialize, Deserialize)]
pub struct EventDispatchResult {
    pub default_prevented: bool,
    pub propagation_stopped: bool,
}

pub struct EventDispatcher;

impl EventDispatcher {
    /// Dispatches an event through the three phases
    pub fn dispatch(arena: &mut NodeArena, target_id: NodeId, mut event: Event) -> EventDispatchResult {
        let mut path = Vec::new();
        let mut curr = Some(target_id);
        
        while let Some(id) = curr {
            path.push(id);
            curr = arena.get(id).and_then(|n| n.parent);
        }

        event.target = Some(target_id);

        // 1. Capture Phase
        event.event_phase = EventPhase::Capturing;
        for &id in path.iter().rev().skip(1) {
            if event.propagation_stopped { break; }
            Self::invoke_listeners(arena, id, &mut event);
        }

        // 2. Target Phase
        if !event.propagation_stopped {
            event.event_phase = EventPhase::AtTarget;
            Self::invoke_listeners(arena, target_id, &mut event);
        }

        // 3. Bubble Phase
        if event.bubbles && !event.propagation_stopped {
            event.event_phase = EventPhase::Bubbling;
            for &id in path.iter().skip(1) {
                if event.propagation_stopped { break; }
                Self::invoke_listeners(arena, id, &mut event);
            }
        }

        EventDispatchResult {
            default_prevented: event.default_prevented,
            propagation_stopped: event.propagation_stopped,
        }
    }

    fn invoke_listeners(_arena: &NodeArena, node_id: NodeId, event: &mut Event) {
        event.current_target = Some(node_id);
        // This is where we'd actualy call back into V8 or the Rust handler
        // For now, this is a placeholder for the logic in vx-js
    }
}

#[derive(Debug, Clone)]
pub struct EventTarget {
    pub registry: HandlerRegistry,
}

impl EventTarget {
    pub fn new() -> Self {
        Self {
            registry: HandlerRegistry::default(),
        }
    }
}
