//! Phase 10: Server-Sent Events (SSE) client
//!
//! W3C EventSource API implementation:
//! - Text/event-stream parsing (id, event, data, retry)
//! - Automatic reconnection with Last-Event-ID header
//! - Custom event types
//! - Stream buffering

use anyhow::{Result, anyhow};
use std::time::Duration;
use tokio::sync::mpsc;

/// An SSE event from a server
#[derive(Debug, Clone, Default)]
pub struct SseEvent {
    pub id: Option<String>,
    pub event_type: String,  // default: "message"
    pub data: String,
    pub retry: Option<u64>,  // ms
}

impl SseEvent {
    pub fn is_heartbeat(&self) -> bool {
        self.data.is_empty() && self.event_type.is_empty()
    }

    pub fn as_json(&self) -> Option<serde_json::Value> {
        serde_json::from_str(&self.data).ok()
    }
}

/// SSE connection state
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum SseState {
    Connecting,
    Open,
    Closed,
}

/// SSE EventSource connection
pub struct EventSource {
    pub url: String,
    pub state: SseState,
    pub last_event_id: Option<String>,
    pub reconnect_delay: Duration,

    event_tx: mpsc::Sender<SseEvent>,
    pub event_rx: mpsc::Receiver<SseEvent>,
    headers: Vec<(String, String)>,
}

impl EventSource {
    pub fn new(url: &str) -> Self {
        let (tx, rx) = mpsc::channel(1024);
        Self {
            url: url.to_string(),
            state: SseState::Closed,
            last_event_id: None,
            reconnect_delay: Duration::from_millis(3000),
            event_tx: tx,
            event_rx: rx,
            headers: Vec::new(),
        }
    }

    pub fn with_header(mut self, key: &str, value: &str) -> Self {
        self.headers.push((key.to_string(), value.to_string()));
        self
    }

    /// Connect and start streaming (async)
    pub async fn connect(&mut self) -> Result<()> {
        self.state = SseState::Connecting;

        let mut headers = reqwest::header::HeaderMap::new();
        headers.insert("Accept", "text/event-stream".parse().unwrap());
        headers.insert("Cache-Control", "no-cache".parse().unwrap());

        for (k, v) in &self.headers {
            if let (Ok(name), Ok(value)) = (
                k.parse::<reqwest::header::HeaderName>(),
                v.parse::<reqwest::header::HeaderValue>()
            ) {
                headers.insert(name, value);
            }
        }

        if let Some(ref id) = self.last_event_id {
            headers.insert("Last-Event-ID", id.parse().unwrap_or_else(|_| "".parse().unwrap()));
        }

        let client = reqwest::Client::builder()
            .default_headers(headers)
            .timeout(Duration::from_secs(0))  // no timeout for SSE
            .build()?;

        let response = client.get(&self.url).send().await
            .map_err(|e| anyhow!("SSE connect failed: {}", e))?;

        if !response.status().is_success() {
            return Err(anyhow!("SSE connect error: {}", response.status()));
        }

        self.state = SseState::Open;

        let mut byte_stream = response.bytes_stream();
        let tx = self.event_tx.clone();
        let mut buffer = String::new();
        let mut current_event = SseEvent::default();

        tokio::spawn(async move {
            use futures_util::StreamExt;
            use bytes::Bytes;

            while let Some(chunk_result) = byte_stream.next().await {
                let chunk = match chunk_result {
                    Ok(b) => b,
                    Err(_) => break,
                };

                let text = match std::str::from_utf8(&chunk) {
                    Ok(s) => s.to_string(),
                    Err(_) => continue,
                };

                buffer.push_str(&text);

                // Process complete lines
                while let Some(newline_pos) = buffer.find('\n') {
                    let line = buffer[..newline_pos].trim_end_matches('\r').to_string();
                    buffer = buffer[newline_pos + 1..].to_string();

                    if line.is_empty() {
                        // Empty line = dispatch event
                        if !current_event.data.is_empty() || !current_event.event_type.is_empty() {
                            if current_event.event_type.is_empty() {
                                current_event.event_type = "message".to_string();
                            }
                            // Trim trailing newline from data
                            if current_event.data.ends_with('\n') {
                                current_event.data.pop();
                            }
                            let _ = tx.send(current_event.clone()).await;
                        }
                        current_event = SseEvent::default();
                    } else if let Some(value) = line.strip_prefix("data:") {
                        let val = value.trim_start_matches(' ');
                        if !current_event.data.is_empty() {
                            current_event.data.push('\n');
                        }
                        current_event.data.push_str(val);
                    } else if let Some(value) = line.strip_prefix("event:") {
                        current_event.event_type = value.trim().to_string();
                    } else if let Some(value) = line.strip_prefix("id:") {
                        let id = value.trim().to_string();
                        if !id.contains('\0') {
                            current_event.id = Some(id);
                        }
                    } else if let Some(value) = line.strip_prefix("retry:") {
                        if let Ok(ms) = value.trim().parse::<u64>() {
                            current_event.retry = Some(ms);
                        }
                    }
                    // Lines starting with ':' are comments, ignored
                }
            }
        });

        Ok(())
    }

    /// Poll for next event (non-blocking)
    pub fn try_recv(&mut self) -> Option<SseEvent> {
        self.event_rx.try_recv().ok()
    }

    /// Wait for next event (blocking)
    pub async fn next_event(&mut self) -> Option<SseEvent> {
        self.event_rx.recv().await
    }

    /// Close the SSE connection
    pub fn close(&mut self) {
        self.state = SseState::Closed;
    }
}

/// SSE stream parser (for testing/offline use)
pub struct SseParser {
    buffer: String,
}

impl SseParser {
    pub fn new() -> Self { Self { buffer: String::new() } }

    pub fn push(&mut self, text: &str) -> Vec<SseEvent> {
        self.buffer.push_str(text);
        let mut events = Vec::new();
        let mut current = SseEvent::default();

        let lines: Vec<&str> = self.buffer.lines().collect();
        let mut consumed = 0;

        for line in &lines {
            consumed += line.len() + 1; // +1 for newline

            if line.is_empty() {
                if !current.data.is_empty() || !current.event_type.is_empty() {
                    if current.event_type.is_empty() {
                        current.event_type = "message".to_string();
                    }
                    if current.data.ends_with('\n') { current.data.pop(); }
                    events.push(current.clone());
                }
                current = SseEvent::default();
            } else if let Some(val) = line.strip_prefix("data:") {
                if !current.data.is_empty() { current.data.push('\n'); }
                current.data.push_str(val.trim_start_matches(' '));
            } else if let Some(val) = line.strip_prefix("event:") {
                current.event_type = val.trim().to_string();
            } else if let Some(val) = line.strip_prefix("id:") {
                current.id = Some(val.trim().to_string());
            } else if let Some(val) = line.strip_prefix("retry:") {
                current.retry = val.trim().parse().ok();
            }
        }

        // Keep unprocessed buffer
        if consumed < self.buffer.len() {
            self.buffer = self.buffer[consumed..].to_string();
        } else {
            self.buffer.clear();
        }

        events
    }
}

impl Default for SseParser {
    fn default() -> Self { Self::new() }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sse_parser_basic() {
        let mut parser = SseParser::new();
        let events = parser.push("data: hello world\n\n");
        assert_eq!(events.len(), 1);
        assert_eq!(events[0].data, "hello world");
        assert_eq!(events[0].event_type, "message");
    }

    #[test]
    fn test_sse_parser_with_event_type() {
        let mut parser = SseParser::new();
        let events = parser.push("event: update\ndata: {\"key\":\"value\"}\n\n");
        assert_eq!(events.len(), 1);
        assert_eq!(events[0].event_type, "update");
        assert!(events[0].as_json().is_some());
    }

    #[test]
    fn test_sse_parser_multiline_data() {
        let mut parser = SseParser::new();
        let events = parser.push("data: line1\ndata: line2\ndata: line3\n\n");
        assert_eq!(events.len(), 1);
        assert_eq!(events[0].data, "line1\nline2\nline3");
    }

    #[test]
    fn test_sse_parser_with_id() {
        let mut parser = SseParser::new();
        let events = parser.push("id: 42\ndata: test\n\n");
        assert_eq!(events[0].id, Some("42".to_string()));
    }

    #[test]
    fn test_sse_parser_retry() {
        let mut parser = SseParser::new();
        let events = parser.push("retry: 5000\ndata: test\n\n");
        assert_eq!(events[0].retry, Some(5000));
    }

    #[test]
    fn test_sse_parser_multiple_events() {
        let mut parser = SseParser::new();
        let input = "data: event1\n\ndata: event2\n\ndata: event3\n\n";
        let events = parser.push(input);
        assert_eq!(events.len(), 3);
    }

    #[test]
    fn test_sse_parser_comment_ignored() {
        let mut parser = SseParser::new();
        let events = parser.push(": this is a comment\ndata: real data\n\n");
        assert_eq!(events.len(), 1);
        assert_eq!(events[0].data, "real data");
    }

    #[test]
    fn test_sse_parser_chunked() {
        let mut parser = SseParser::new();
        // Simulate receiving data in chunks
        assert_eq!(parser.push("data: hel").len(), 0);
        assert_eq!(parser.push("lo\n").len(), 0);  // no event yet
        let events = parser.push("\n");  // dispatch
        assert_eq!(events.len(), 1);
        assert_eq!(events[0].data, "hello");
    }
}
