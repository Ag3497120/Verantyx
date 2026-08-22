//! # ronin-sandbox
//!
//! The OS execution layer for the Ronin autonomous hacker agent.
//! 
//! Provides a fully sandboxed environment for agent-driven command execution
//! with multi-layer security policy enforcement, PTY-based interactive shell
//! control, complete process lifecycle management, and a tamper-proof audit log.
//!
//! ## Layer Architecture
//! ```
//! SandboxSession        ← entry point: exec(), policy check, env isolation
//!   └─ PolicyEngine     ← multi-layer denylist + capability gating
//!   └─ EnvironmentBuilder  ← strips secrets, injects RONIN_SANDBOX markers
//!   └─ ProcessRegistry  ← tracks live PIDs, enables kill/signal
//!   └─ AuditLog         ← ring-buffered audit trail of all events
//!
//! PtyController         ← interactive TTY shell (for REPL programs)
//!   └─ OutputWatcher    ← pattern-based output parsing & prompt detection
//! ```

pub mod audit;
pub mod isolation;
pub mod observer;
pub mod process;
pub mod pty;
