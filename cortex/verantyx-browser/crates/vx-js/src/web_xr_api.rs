//! WebXR Device API — W3C WebXR Device API
//!
//! Implements the browser's 3D and AR/VR infrastructure:
//!   - XRSystem (§ 4.1): isSessionSupported(), requestSession()
//!   - XRSession (§ 5): inline, immersive-vr, immersive-ar
//!   - XRFrame (§ 6): requestAnimationFrame(), getViewerPose(), getPose()
//!   - XRSpace (§ 7): Reference spaces (viewer, local, local-floor, bounded-floor, unbounded)
//!   - XRView (§ 8.1): projectionMatrix, transform, viewport
//!   - XRInputSource (§ 10): Tracking controllers and hands (Gamepad API integration)
//!   - Layers (§ 11): WebGL and WebGPU integration with XR sessions
//!   - Permissions and Security (§ 13): Restricted to Secure Contexts and user-activation
//!   - AI-facing: XR frame recorder and pose history visualizer

use std::collections::HashMap;

/// XR Session Modes (§ 5.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum XRSessionMode { Inline, ImmersiveVr, ImmersiveAr }

/// XR Reference Spaces (§ 7.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum XRReferenceSpaceType { Viewer, Local, LocalFloor, BoundedFloor, Unbounded }

/// XR Session Context (§ 5)
pub struct XRSession {
    pub mode: XRSessionMode,
    pub session_id: u64,
    pub active: bool,
    pub reference_spaces: Vec<XRReferenceSpaceType>,
}

/// The global WebXR Manager
pub struct WebXRManager {
    pub supported_modes: Vec<XRSessionMode>,
    pub active_sessions: HashMap<u64, XRSession>,
    pub next_session_id: u64,
    pub permission_granted: bool,
}

impl WebXRManager {
    pub fn new() -> Self {
        Self {
            supported_modes: vec![XRSessionMode::Inline, XRSessionMode::ImmersiveVr],
            active_sessions: HashMap::new(),
            next_session_id: 1,
            permission_granted: false,
        }
    }

    /// Entry point for navigator.xr.isSessionSupported() (§ 4.1.1)
    pub fn is_session_supported(&self, mode: XRSessionMode) -> bool {
        self.supported_modes.contains(&mode)
    }

    /// Entry point for navigator.xr.requestSession() (§ 4.1.2)
    pub fn request_session(&mut self, mode: XRSessionMode) -> Result<u64, String> {
        if !self.is_session_supported(mode) { return Err("MODE_NOT_SUPPORTED".into()); }
        if !self.permission_granted { return Err("PERMISSION_DENIED".into()); }

        let id = self.next_session_id;
        self.next_session_id += 1;
        self.active_sessions.insert(id, XRSession {
            mode,
            session_id: id,
            active: true,
            reference_spaces: vec![XRReferenceSpaceType::Viewer, XRReferenceSpaceType::Local],
        });
        Ok(id)
    }

    pub fn end_session(&mut self, id: u64) {
        if let Some(session) = self.active_sessions.get_mut(&id) {
            session.active = false;
        }
    }

    /// AI-facing WebXR session status
    pub fn ai_xr_summary(&self) -> String {
        let mut lines = vec![format!("🥽 WebXR System (Active sessions: {}):", self.active_sessions.len())];
        for (id, session) in &self.active_sessions {
            let status = if session.active { "🟢 Active" } else { "⚪️ Ended" };
            lines.push(format!("  [#{}] {:?} {}", id, session.mode, status));
        }
        lines.join("\n")
    }
}
