//! Event System — DOM event dispatch for vx-browser
//!
//! Manages event listeners and dispatches click/input/submit events.

use std::collections::HashMap;

/// Event types supported by vx-browser
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum EventType {
    Click,
    Input,
    Submit,
    Change,
    Focus,
    Blur,
    KeyDown,
    KeyUp,
    Load,
    DomContentLoaded,
}

impl EventType {
    pub fn from_str(s: &str) -> Option<Self> {
        match s.to_lowercase().as_str() {
            "click" => Some(EventType::Click),
            "input" => Some(EventType::Input),
            "submit" => Some(EventType::Submit),
            "change" => Some(EventType::Change),
            "focus" => Some(EventType::Focus),
            "blur" => Some(EventType::Blur),
            "keydown" => Some(EventType::KeyDown),
            "keyup" => Some(EventType::KeyUp),
            "load" => Some(EventType::Load),
            "domcontentloaded" | "DOMContentLoaded" => Some(EventType::DomContentLoaded),
            _ => None,
        }
    }
}

/// An event to be dispatched
#[derive(Debug, Clone)]
pub struct DomEvent {
    pub event_type: EventType,
    pub target_id: Option<usize>,  // Interactive element ID
    pub data: HashMap<String, String>,
    pub bubbles: bool,
    pub cancelable: bool,
}

impl DomEvent {
    pub fn click(target_id: usize) -> Self {
        Self {
            event_type: EventType::Click,
            target_id: Some(target_id),
            data: HashMap::new(),
            bubbles: true,
            cancelable: true,
        }
    }

    pub fn input(target_id: usize, value: &str) -> Self {
        let mut data = HashMap::new();
        data.insert("value".to_string(), value.to_string());
        Self {
            event_type: EventType::Input,
            target_id: Some(target_id),
            data,
            bubbles: true,
            cancelable: false,
        }
    }

    pub fn submit(target_id: usize) -> Self {
        Self {
            event_type: EventType::Submit,
            target_id: Some(target_id),
            data: HashMap::new(),
            bubbles: true,
            cancelable: true,
        }
    }
}

/// Event listener registry
pub struct EventRegistry {
    listeners: HashMap<(EventType, Option<usize>), Vec<String>>, // event+target → JS callback names
}

impl EventRegistry {
    pub fn new() -> Self {
        Self { listeners: HashMap::new() }
    }

    pub fn add_listener(&mut self, event_type: EventType, target_id: Option<usize>, callback_name: String) {
        self.listeners
            .entry((event_type, target_id))
            .or_default()
            .push(callback_name);
    }

    pub fn get_listeners(&self, event: &DomEvent) -> Vec<&str> {
        let mut result = Vec::new();

        // Exact match (element-specific)
        if let Some(listeners) = self.listeners.get(&(event.event_type.clone(), event.target_id)) {
            result.extend(listeners.iter().map(|s| s.as_str()));
        }

        // Global listeners (no specific target)
        if let Some(listeners) = self.listeners.get(&(event.event_type.clone(), None)) {
            result.extend(listeners.iter().map(|s| s.as_str()));
        }

        result
    }
}

impl Default for EventRegistry {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_click_event() {
        let event = DomEvent::click(5);
        assert_eq!(event.event_type, EventType::Click);
        assert_eq!(event.target_id, Some(5));
    }

    #[test]
    fn test_input_event() {
        let event = DomEvent::input(3, "hello");
        assert_eq!(event.data.get("value").unwrap(), "hello");
    }

    #[test]
    fn test_event_registry() {
        let mut reg = EventRegistry::new();
        reg.add_listener(EventType::Click, Some(1), "onClick1".to_string());
        reg.add_listener(EventType::Click, None, "onGlobalClick".to_string());

        let event = DomEvent::click(1);
        let listeners = reg.get_listeners(&event);
        assert_eq!(listeners.len(), 2);
    }
}
