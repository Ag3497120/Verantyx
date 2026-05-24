//! Chrome Extension Manifest V3 Parser
//!
//! Parses standard format `manifest.json` rules, setting API boundaries and
//! background service worker lifecycles for headless extensions.

use serde::{Serialize, Deserialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ManifestV3 {
    pub manifest_version: u32,
    pub name: String,
    pub version: String,
    pub permissions: Option<Vec<String>>,
    pub host_permissions: Option<Vec<String>>,
    pub background: Option<BackgroundServiceWorker>,
    pub content_scripts: Option<Vec<ContentScript>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BackgroundServiceWorker {
    pub service_worker: String,
    pub r#type: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContentScript {
    pub matches: Vec<String>,
    pub js: Option<Vec<String>>,
    pub css: Option<Vec<String>>,
    pub run_at: Option<String>,
}

impl ManifestV3 {
    pub fn parse(json: &str) -> anyhow::Result<Self> {
        let manifest: ManifestV3 = serde_json::from_str(json)?;
        if manifest.manifest_version != 3 {
            anyhow::bail!("Verantyx only supports Manifest V3 Extensions.");
        }
        Ok(manifest)
    }

    /// Verifies if the extension has explicit permissions to hook a specific tab
    pub fn has_permission(&self, perm: &str) -> bool {
        if let Some(perms) = &self.permissions {
            perms.contains(&perm.to_string())
        } else {
            false
        }
    }
}
