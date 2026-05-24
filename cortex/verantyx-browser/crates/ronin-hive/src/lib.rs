pub mod actor;
pub mod hive;
pub mod roles;
pub mod messages;
pub mod error;
pub mod config;
pub mod nightwatch;
pub mod neuro_symbolic;
pub mod openclaude_ui;

pub use actor::{Actor, Envelope};
pub use hive::HiveMind;
pub use messages::HiveMessage;
