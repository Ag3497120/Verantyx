use std::collections::HashMap;
use std::path::{Path, PathBuf};
use tracing::{debug, warn};
use uuid::Uuid;

pub type VirtualFileId = String;

#[derive(Debug, Clone)]
pub struct BlindGatekeeper {
    workspace_root: PathBuf,
    id_to_path: HashMap<VirtualFileId, PathBuf>,
    path_to_id: HashMap<PathBuf, VirtualFileId>,
}

impl BlindGatekeeper {
    pub fn new(workspace_root: impl AsRef<Path>) -> Self {
        Self {
            workspace_root: workspace_root.as_ref().to_path_buf(),
            id_to_path: HashMap::new(),
            path_to_id: HashMap::new(),
        }
    }

    /// Registers a real path into the VFS and returns a Virtual ID.
    /// If the path is outside the workspace root, it refuses to register it as an extra security layer.
    pub fn register(&mut self, path: impl AsRef<Path>) -> anyhow::Result<VirtualFileId> {
        let path = path.as_ref();
        
        // Ensure path is relative to workspace or inside workspace
        let abs_path = if path.is_absolute() {
            path.to_path_buf()
        } else {
            self.workspace_root.join(path)
        };

        let canon = abs_path.canonicalize().unwrap_or(abs_path);
        
        if !canon.starts_with(&self.workspace_root) {
            warn!("[Gatekeeper] Security exception: Attempt to register external path {:?}", canon);
            return Err(anyhow::anyhow!("Path outside of workspace boundaries"));
        }

        if let Some(existing_id) = self.path_to_id.get(&canon) {
            return Ok(existing_id.clone());
        }

        let new_id = format!("FID-{}", Uuid::new_v4().as_simple().to_string()[..8].to_uppercase());
        self.id_to_path.insert(new_id.clone(), canon.clone());
        self.path_to_id.insert(canon, new_id.clone());

        debug!("[Gatekeeper] Registered {} -> {:?}", new_id, path.display());
        Ok(new_id)
    }

    /// Resolves a Virtual ID back to a secure real path.
    pub fn resolve(&self, id: &str) -> anyhow::Result<PathBuf> {
        self.id_to_path.get(id)
            .cloned()
            .ok_or_else(|| anyhow::anyhow!("Invalid Virtual File ID: {}", id))
    }

    /// Checks if a raw path is safely contained within the workspace root
    pub fn is_safe(&self, path: impl AsRef<Path>) -> bool {
        let path = path.as_ref();
        let abs_path = if path.is_absolute() {
            path.to_path_buf()
        } else {
            self.workspace_root.join(path)
        };
        
        let canon = abs_path.canonicalize().unwrap_or(abs_path);
        canon.starts_with(&self.workspace_root)
    }
}
