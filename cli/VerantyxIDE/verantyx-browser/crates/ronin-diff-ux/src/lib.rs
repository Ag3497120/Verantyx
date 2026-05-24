//! # ronin-diff-ux
//!
//! Enterprise-grade diff visualization, HITL approval workflow, and patch
//! application engine for the Ronin autonomous hacker agent framework.
//! 
//! Implements the Aider/Cline philosophy of "never touch a file without showing
//! the human exactly what will change" — rebuilt from scratch.

pub mod diff;
pub mod tui;
pub mod patch;
pub mod git;
