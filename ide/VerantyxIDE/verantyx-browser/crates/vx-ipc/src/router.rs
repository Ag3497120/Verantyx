//! Chromium-Style Mojo Multiplexing Router
//!
//! Handles massive connection scaling without blocking. Emulates the Chrome IPC Broker
//! routing node which sits in the browser process orchestrating isolated renderer processes.

use crate::message::{IpcEnvelope, RouteId};
use crate::channel::IpcChannel;
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::{Mutex, mpsc};

pub struct RoutedConnection {
    pub process_id: u32,
    pub tx: mpsc::Sender<IpcEnvelope>,
}

pub struct IpcRouter {
    // Hash map grouping thousands of renderer endpoints 
    // mapped generically via random secure tokens.
    routes: Arc<Mutex<HashMap<RouteId, RoutedConnection>>>,
}

impl IpcRouter {
    pub fn new() -> Self {
        Self {
            routes: Arc::new(Mutex::new(HashMap::new())),
        }
    }

    /// Registers a newly sandboxed Renderer Process securely into the IPC Broker 
    pub async fn register_route(&self, route: RouteId, process_id: u32) -> mpsc::Receiver<IpcEnvelope> {
        let (tx, rx) = mpsc::channel(1000); // Massive internal buffer for UI repaints
        
        let mut map = self.routes.lock().await;
        map.insert(route, RoutedConnection { process_id, tx });
        
        rx
    }

    /// Primary multiplexing node. Spawns an async listener task specifically
    /// attached to a raw incoming channel, decoding Bincode onto the Tokyo MPSC bus.
    pub async fn multiplex(&self, raw_channel: IpcChannel) {
        let routes = self.routes.clone();
        
        tokio::spawn(async move {
            loop {
                // Poll crossbeam wrapper concurrently
                match raw_channel.try_recv() {
                    Ok(Some(envelope)) => {
                        let map = routes.lock().await;
                        if let Some(conn) = map.get(&envelope.route_id) {
                            if let Err(e) = conn.tx.send(envelope).await {
                                eprintln!("Broker Send Failed: {}", e);
                            }
                        }
                    }
                    Ok(None) => tokio::task::yield_now().await,
                    Err(_) => {
                        // Connection severed (Renderer Crash Simulation)
                        break;
                    }
                }
            }
        });
    }

    pub async fn broadcast(&self, envelope: IpcEnvelope) {
        let map = self.routes.lock().await;
        for (_, conn) in map.iter() {
            let _ = conn.tx.send(envelope.clone()).await;
        }
    }
}
