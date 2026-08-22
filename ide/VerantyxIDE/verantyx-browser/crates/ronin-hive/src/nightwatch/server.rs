use tokio::net::TcpListener;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use std::sync::{Arc, Mutex};
use tracing::{info, error, warn};
use std::process::Command;

pub struct VeraUiBridge {
    pub crucible_command_queue: Arc<Mutex<Option<String>>>,
}

impl VeraUiBridge {
    pub fn new() -> Self {
        Self {
            crucible_command_queue: Arc::new(Mutex::new(None)),
        }
    }

    pub async fn start(self_arc: Arc<Self>) {
        let listener = TcpListener::bind("127.0.0.1:3030").await.unwrap();
        info!("[VeraBridge] Listening on HTTP 127.0.0.1:3030 for UI interactions");

        loop {
            match listener.accept().await {
                Ok((mut socket, _addr)) => {
                    let bridge = self_arc.clone();
                    tokio::spawn(async move {
                        let mut buf = [0; 1024];
                        if let Ok(n) = socket.read(&mut buf).await {
                            if n == 0 { return; }
                            let request = String::from_utf8_lossy(&buf[..n]);
                            if let Some(line) = request.lines().next() {
                                let parts: Vec<&str> = line.split_whitespace().collect();
                                if parts.len() >= 2 && parts[0] == "GET" {
                                    let path = parts[1];
                                    
                                    if path.starts_with("/cat?file=") {
                                        let file_target = path.replace("/cat?file=", "");
                                        let decoded_file = urlencoding::decode(&file_target).unwrap_or_else(|_| std::borrow::Cow::Borrowed(&file_target));
                                        
                                        if let Ok(content) = std::fs::read_to_string(decoded_file.as_ref()) {
                                            let response = format!("HTTP/1.1 200 OK\r\nAccess-Control-Allow-Origin: *\r\nContent-Type: text/plain\r\nContent-Length: {}\r\n\r\n{}", content.len(), content);
                                            let _ = socket.write_all(response.as_bytes()).await;
                                        } else {
                                            let err = "HTTP/1.1 404 Not Found\r\nAccess-Control-Allow-Origin: *\r\nContent-Length: 9\r\n\r\nNot Found";
                                            let _ = socket.write_all(err.as_bytes()).await;
                                        }
                                        return;
                                    }

                                    // CORS OK Response for UI commands
                                    let response = "HTTP/1.1 200 OK\r\nAccess-Control-Allow-Origin: *\r\nContent-Length: 2\r\n\r\nOK";
                                    let _ = socket.write_all(response.as_bytes()).await;

                                    if path.starts_with("/open?file=") {
                                        let file_target = path.replace("/open?file=", "");
                                        let decoded_file = urlencoding::decode(&file_target).unwrap_or_else(|_| std::borrow::Cow::Borrowed(&file_target));
                                        info!("[VeraBridge] Opening file in IDE: {}", decoded_file);
                                        // Attempt to open in cursor, fallback to VSCode
                                        if let Err(e) = Command::new("cursor").arg(decoded_file.as_ref()).spawn() {
                                            warn!("Could not start 'cursor' ({}). Trying 'code'...", e);
                                            let _ = Command::new("code").arg(decoded_file.as_ref()).spawn();
                                        }
                                    } else if path.starts_with("/crucible?") {
                                        let query = path.replace("/crucible?", "");
                                        let params: Vec<&str> = query.split('&').collect();
                                        let mut files = Vec::new();
                                        for p in params {
                                            if p.starts_with("f=") {
                                                files.push(urlencoding::decode(&p[2..]).unwrap_or_default().to_string());
                                            }
                                        }

                                        if !files.is_empty() {
                                            info!("[VeraBridge] Dropped {} files into Crucible", files.len());
                                            let cmd = format!("crucible {}", files.join(" "));
                                            if let Ok(mut queue) = bridge.crucible_command_queue.lock() {
                                                *queue = Some(cmd);
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    });
                }
                Err(e) => {
                    error!("[VeraBridge] Failed to accept connection: {}", e);
                }
            }
        }
    }
}
