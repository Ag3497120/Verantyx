//! vx-a11y-tree — Cognitive ARIA Accessibility Tensor Engine
//!
//! Generates multi-dimensional semantic representations from standard DOM layouts
//! specifically designed to feed Verantyx AI agents structural state perfectly.

pub mod role;
pub mod tree;

pub use role::{A11yRole, A11yState};
pub use tree::{A11yTree, A11yNode};
pub mod aria_roles;
pub mod accessible_name;
