//! vx-security — Sovereign Sandbox & Content Security Policy
//!
//! Provides origin validation, CSP enforcement, and CORS validation for Verantyx Browser.

pub mod origin;
pub mod csp;
pub mod sandbox;
pub mod cors;
pub mod sri;

pub use origin::Origin;
pub use csp::ContentSecurityPolicy;
pub use sandbox::Sandbox;
pub use sandbox::SandboxFlags;
