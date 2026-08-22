//! Form State Management
//!
//! Tracks input values, focus state, and form data across interactions.

use std::collections::HashMap;

/// Tracks the state of all form inputs on a page
#[derive(Debug, Default)]
pub struct FormState {
    /// Input values by element ID
    values: HashMap<usize, String>,
    /// Currently focused element ID
    focused: Option<usize>,
    /// Checkbox/radio checked state
    checked: HashMap<usize, bool>,
}

impl FormState {
    pub fn new() -> Self {
        Self::default()
    }

    /// Set the value of an input element
    pub fn set_value(&mut self, id: usize, value: &str) {
        self.values.insert(id, value.to_string());
    }

    /// Get the value of an input element
    pub fn get_value(&self, id: usize) -> Option<&str> {
        self.values.get(&id).map(|s| s.as_str())
    }

    /// Set focus to an element
    pub fn set_focus(&mut self, id: usize) {
        self.focused = Some(id);
    }

    /// Get currently focused element
    pub fn get_focus(&self) -> Option<usize> {
        self.focused
    }

    /// Toggle checkbox/radio
    pub fn toggle(&mut self, id: usize) {
        let current = self.checked.get(&id).copied().unwrap_or(false);
        self.checked.insert(id, !current);
    }

    /// Check if checkbox/radio is checked
    pub fn is_checked(&self, id: usize) -> bool {
        self.checked.get(&id).copied().unwrap_or(false)
    }

    /// Get all form values as key-value pairs
    pub fn get_all(&self) -> Vec<(String, String)> {
        self.values.iter()
            .map(|(id, val)| (format!("field_{}", id), val.clone()))
            .collect()
    }

    /// Clear all state
    pub fn clear(&mut self) {
        self.values.clear();
        self.focused = None;
        self.checked.clear();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_form_state() {
        let mut form = FormState::new();
        form.set_value(1, "hello");
        form.set_value(2, "world");
        assert_eq!(form.get_value(1), Some("hello"));
        assert_eq!(form.get_all().len(), 2);
    }

    #[test]
    fn test_focus() {
        let mut form = FormState::new();
        assert_eq!(form.get_focus(), None);
        form.set_focus(3);
        assert_eq!(form.get_focus(), Some(3));
    }

    #[test]
    fn test_checkbox() {
        let mut form = FormState::new();
        assert!(!form.is_checked(1));
        form.toggle(1);
        assert!(form.is_checked(1));
        form.toggle(1);
        assert!(!form.is_checked(1));
    }
}
