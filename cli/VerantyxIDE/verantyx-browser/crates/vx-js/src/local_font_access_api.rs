//! Local Font Access API — WICG Local Font Access
//!
//! Implements mapping of native OS locally installed typographies:
//!   - `queryLocalFonts()` (§ 4): Requesting native font descriptors (e.g., Arial, Helvetica)
//!   - `FontData.blob()` (§ 5): Extracting the raw `.ttf` byte buffers securely
//!   - Permission Mediation (Fingerprint vector constraints)
//!   - AI-facing: System capability ingestion topologies

use std::collections::HashMap;

/// Maps a specific OS-installed typography instance
#[derive(Debug, Clone)]
pub struct FontDataDescriptor {
    pub postscript_name: String,
    pub full_name: String,
    pub family: String,
    pub style: String,
}

/// The global Constraint Resolver governing OS font bridging
pub struct LocalFontAccessEngine {
    // Top-Level Frame ID -> Has Requested Permissions
    pub permissions_state: HashMap<u64, bool>, 
    pub total_fonts_accessed: u64,
}

impl LocalFontAccessEngine {
    pub fn new() -> Self {
        Self {
            permissions_state: HashMap::new(),
            total_fonts_accessed: 0,
        }
    }

    /// JS execution: `await window.queryLocalFonts({ postscriptNames: ['MarkerFelt-Thin'] })` (§ 4)
    pub fn query_fonts(&mut self, document_id: u64, postscript_filters: Option<Vec<String>>) -> Result<Vec<FontDataDescriptor>, String> {
        let has_permission = self.permissions_state.get(&document_id).cloned().unwrap_or(false);
        if !has_permission {
            // In a real browser, this triggers the `<browser> wants to access your fonts` prompt
            return Err("NotAllowedError: Permissions not granted".into());
        }

        // Mocking the bridge to CoreText (macOS) / DirectWrite (Windows) enumeration
        let mut all_fonts = vec![
            FontDataDescriptor { postscript_name: "Arial-BoldMT".into(), full_name: "Arial Bold".into(), family: "Arial".into(), style: "Bold".into() },
            FontDataDescriptor { postscript_name: "TimesNewRomanPSMT".into(), full_name: "Times New Roman".into(), family: "Times New Roman".into(), style: "Regular".into() },
            FontDataDescriptor { postscript_name: "SanFrancisco-Regular".into(), full_name: "SF Pro".into(), family: "SF Pro".into(), style: "Regular".into() },
        ];

        if let Some(filters) = postscript_filters {
            all_fonts.retain(|f| filters.contains(&f.postscript_name));
        }

        self.total_fonts_accessed += all_fonts.len() as u64;

        Ok(all_fonts)
    }

    /// Simulates resolving the `.ttf` byte buffer parsing
    pub fn fetch_binary_blob(&self, postscript_name: &str) -> Vec<u8> {
        // Bridges to the OS backend returning actual binary font representations
        format!("MOCK_TTF_HEADER:{}", postscript_name).into_bytes()
    }

    /// Invoked externally when User grants permission via prompt
    pub fn grant_permission(&mut self, document_id: u64) {
        self.permissions_state.insert(document_id, true);
    }

    /// AI-facing Hardware Extradition mapper
    pub fn ai_font_access_summary(&self, document_id: u64) -> String {
        let perm = self.permissions_state.get(&document_id).cloned().unwrap_or(false);
        format!("🔡 Local Font Access API (Doc #{}): Permission: {} | Global Font Extraditions: {}", 
            document_id, perm, self.total_fonts_accessed)
    }
}
