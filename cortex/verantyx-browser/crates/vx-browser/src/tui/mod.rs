//! Phase 11: TUI Application — ratatui-based browser UI
//!
//! Layout:
//! ┌─────────────────────────────────────────────────────┐
//! │ 🔒 https://example.com              [Tab 1] [Tab 2] │ ← Address bar
//! ├─────────────────────────────────────────────────────┤
//! │                                                     │
//! │  Page content (scrollable, semantic Markdown)       │ ← Page view
//! │                                                     │
//! ├──────────────────────┬──────────────────────────────┤
//! │ Console / Network    │ Interactive Elements         │ ← Dev panel
//! │ [log] Hello world    │ [1] 🔗 Login                 │
//! │ [err] Script failed  │ [2] 📝 Email input           │
//! │                      │ [3] ▶ Submit button          │
//! └──────────────────────┴──────────────────────────────┘

pub mod app;
pub mod layout;
pub mod page_view;
pub mod address_bar;
pub mod dev_panel;
pub mod elements_panel;
pub mod mouse;
pub mod themes;
pub mod events;
pub mod status_bar;

pub use app::{TuiApp, TuiState};
pub use themes::Theme;
