//! Console output formatting for terminal display

use crate::runtime::{ConsoleMessage, ConsoleLevel};

/// Format console messages for terminal display
pub fn format_console_output(messages: &[ConsoleMessage]) -> Vec<String> {
    messages.iter().map(|msg| {
        let prefix = match msg.level {
            ConsoleLevel::Log => "\x1b[37m[log]\x1b[0m",
            ConsoleLevel::Warn => "\x1b[33m[warn]\x1b[0m",
            ConsoleLevel::Error => "\x1b[31m[error]\x1b[0m",
            ConsoleLevel::Info => "\x1b[36m[info]\x1b[0m",
            ConsoleLevel::Debug => "\x1b[90m[debug]\x1b[0m",
        };
        format!("{} {}", prefix, msg.message)
    }).collect()
}

/// Format console messages for AI (no ANSI)
pub fn format_console_for_ai(messages: &[ConsoleMessage]) -> String {
    if messages.is_empty() {
        return String::new();
    }

    let mut out = String::from("<!-- Console Output -->\n");
    for msg in messages {
        let level = match msg.level {
            ConsoleLevel::Log => "LOG",
            ConsoleLevel::Warn => "WARN",
            ConsoleLevel::Error => "ERROR",
            ConsoleLevel::Info => "INFO",
            ConsoleLevel::Debug => "DEBUG",
        };
        out.push_str(&format!("[{}] {}\n", level, msg.message));
    }
    out
}
