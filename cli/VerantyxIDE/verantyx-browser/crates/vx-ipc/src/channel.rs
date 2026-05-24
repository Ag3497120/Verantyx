//! Asynchronous IPC Channel
//!
//! Provides the primary connection abstraction between the Browser Process and
//! a Renderer Process. Maps Mojo-like pipes over Tokio async channels.

use anyhow::Result;
use crossbeam_channel::{unbounded, Sender, Receiver};
use std::sync::Arc;
use tokio::sync::Mutex;
use crate::message::IpcEnvelope;

/// Core IPC Channel connection bounding two operating system processes.
pub struct IpcChannel {
    pub process_id: u32,
    tx: Sender<Vec<u8>>,
    rx: Receiver<Vec<u8>>,
    is_connected: Arc<Mutex<bool>>,
}

impl IpcChannel {
    /// Creates a mocked local-pipe pair simulating a UNIX domain socket / Named Pipe
    /// for massive scale process bridging.
    pub fn create_pair(process_id: u32) -> (Self, Self) {
        let (tx1, rx1) = unbounded();
        let (tx2, rx2) = unbounded();

        let connected = Arc::new(Mutex::new(true));

        let host = Self {
            process_id,
            tx: tx1,
            rx: rx2,
            is_connected: connected.clone(),
        };

        let client = Self {
            process_id,
            tx: tx2,
            rx: rx1,
            is_connected: connected,
        };

        (host, client)
    }

    /// Send a typed IPC envelope, bypassing deep serialization for simulation speed
    /// while validating the pipeline constraints.
    pub fn send(&self, envelope: &IpcEnvelope) -> Result<()> {
        let payload = envelope.serialize()?;
        self.tx.send(payload).map_err(|e| anyhow::anyhow!("IPC Send Failure: {}", e))?;
        Ok(())
    }

    /// Synchronously receive an IPC Envelope. In Chrome, this runs on an IO thread.
    pub fn try_recv(&self) -> Result<Option<IpcEnvelope>> {
        match self.rx.try_recv() {
            Ok(bytes) => {
                let env = IpcEnvelope::deserialize(&bytes)?;
                Ok(Some(env))
            }
            Err(crossbeam_channel::TryRecvError::Empty) => Ok(None),
            Err(e) => Err(anyhow::anyhow!("IPC Disconnected: {}", e)),
        }
    }

    pub async fn shutdown(&self) {
        let mut conn = self.is_connected.lock().await;
        *conn = false;
    }
}
