//! Sovereign Sandbox — Origin-Based Security Enforcer
//!
//! Enforces isolation across documents, workers, and storage.

use crate::origin::Origin;
use crate::csp::ContentSecurityPolicy;
use anyhow::{Result, bail};

pub struct Sandbox {
    origin: Origin,
    csp: ContentSecurityPolicy,
    flags: SandboxFlags,
}

impl Sandbox {
    pub fn new(origin: Origin, csp: ContentSecurityPolicy) -> Self {
        Self {
            origin,
            csp,
            flags: SandboxFlags::default(),
        }
    }

    /// Check if a sub-origin is allowed (Same-Origin Policy)
    pub fn allows_origin(&self, other: &Origin) -> bool {
        if self.flags.allow_same_origin {
             self.origin.is_same_origin(other)
        } else {
            // If sandboxed without 'allow-same-origin', everything is cross-origin
            false
        }
    }

    /// Check if a script execution is allowed by CSP
    pub fn allows_script(&self, source: &str, _nonce: Option<&str>) -> Result<()> {
        let origin = crate::csp::Origin::from_url(source).unwrap_or(crate::csp::Origin {
            scheme: "https".to_string(), host: source.to_string(), port: None,
        });
        let result = self.csp.allows_url(
            &crate::csp::CspDirective::ScriptSrc, source, &origin
        );
        if result.is_allowed() {
            Ok(())
        } else {
            bail!("CSP Violation: Script from {} is blocked", source)
        }
    }

    /// Check if a network connection is allowed by CSP
    pub fn allows_connect(&self, url: &str) -> Result<()> {
        let origin = crate::csp::Origin::from_url(url).unwrap_or(crate::csp::Origin {
            scheme: "https".to_string(), host: url.to_string(), port: None,
        });
        let result = self.csp.allows_url(
            &crate::csp::CspDirective::ConnectSrc, url, &origin
        );
        if result.is_allowed() {
            Ok(())
        } else {
            bail!("CSP Violation: Connection to {} is blocked", url)
        }
    }

    pub fn origin(&self) -> &Origin {
        &self.origin
    }
}

#[derive(Debug, Clone, Default)]
pub struct SandboxFlags {
    pub allow_same_origin: bool,
    pub allow_scripts: bool,
    pub allow_forms: bool,
    pub allow_popups: bool,
    pub allow_modals: bool,
    pub allow_top_navigation: bool,
}
