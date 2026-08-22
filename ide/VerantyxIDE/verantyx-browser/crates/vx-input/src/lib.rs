//! vx-input — User interaction layer for vx-browser
//!
//! Manages form state, element focus, and user actions.
//! Actions are dispatched by interactive element ID (from AI renderer).
//!
//! Commands:
//!   click <id>         — Click a button or link
//!   type <id> <text>   — Type text into an input field
//!   submit <id>        — Submit a form
//!   select <id> <val>  — Select an option
//!   focus <id>         — Focus an element
//!   scroll up|down     — Scroll the page
//!   back               — Navigate back
//!   goto <url>         — Navigate to URL

pub mod action;
pub mod form;

pub use action::{BrowserAction, ActionResult};
pub use form::FormState;
pub mod event_system;
