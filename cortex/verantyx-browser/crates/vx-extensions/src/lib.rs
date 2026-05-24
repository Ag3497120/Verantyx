//! vx-extensions — Chrome Manifest V3 Compatibility API
//!
//! Enables Verantyx to securely host, parse, and execute raw Chrome Extensions
//! (like uBlock Origin, Web3 Wallets), extending the behavioral capabilities of the AI Agent.

pub mod manifest;
pub mod api_tabs;
pub mod api_storage;

pub use manifest::ManifestV3;
pub use api_tabs::{ChromeTabsApi, ExtensionTab};
pub use api_storage::ChromeStorageApi;
