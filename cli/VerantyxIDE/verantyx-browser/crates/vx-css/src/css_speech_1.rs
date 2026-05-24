//! CSS Speech Module Level 1 — W3C CSS Speech
//!
//! Implements declarative non-visual acoustic topologies for Text-To-Speech (TTS) flows:
//!   - `voice-family` (§ 3): Selecting male/female/specific synthesized voices
//!   - `speak` (§ 2): Replaces `display: none` for audio (`auto`, `always`, `none`)
//!   - `pause-before` / `pause-after` (§ 7): Punctuation acoustic rhythm structures
//!   - AI-facing: CSS Acoustic synthesized boundary metrics

use std::collections::HashMap;

/// Determines if the block is processed by the acoustic pipeline (§ 2)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SpeakState { Auto, None, Always }

/// Represents the temporal silence before or after a node is vocalized (§ 7)
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct AcousticPause {
    pub duration_seconds: f64, 
}

/// The declarative CSS configuration parsed from the node
#[derive(Debug, Clone)]
pub struct CssSpeechConfiguration {
    pub speak: SpeakState,
    pub voice_family: String, // e.g. "female", "alex", "preserve"
    pub voice_volume: f64, // Normalized 0.0 to 1.0 mapping
    pub pause_before: Option<AcousticPause>,
    pub pause_after: Option<AcousticPause>,
}

impl Default for CssSpeechConfiguration {
    fn default() -> Self {
        Self {
            speak: SpeakState::Auto,
            voice_family: "default".into(),
            voice_volume: 0.8,
            pause_before: None,
            pause_after: None,
        }
    }
}

/// Global Engine compiling CSS Trees into an Audio-TTS Synthesizer Stream
pub struct CssSpeechEngine {
    pub acoustic_nodes: HashMap<u64, CssSpeechConfiguration>,
    pub total_nodes_ingested: u64,
}

impl CssSpeechEngine {
    pub fn new() -> Self {
        Self {
            acoustic_nodes: HashMap::new(),
            total_nodes_ingested: 0,
        }
    }

    pub fn set_speech_config(&mut self, node_id: u64, config: CssSpeechConfiguration) {
        self.acoustic_nodes.insert(node_id, config);
    }

    /// Evaluator executed by the TTS Screen Reader engine parsing DOM trees sequentially
    pub fn compute_vocalization_stream(&mut self, node_id: u64, text_content: &str) -> Option<(String, String, f64, f64, f64)> {
        // Output Tuple: (VoiceFamily, TextToRead, Volume, PauseBeforeX, PauseAfterY)
        
        let default_config = CssSpeechConfiguration::default();
        let config = self.acoustic_nodes.get(&node_id).unwrap_or(&default_config);

        if config.speak == SpeakState::None {
            return None; // Element muted
        }

        self.total_nodes_ingested += 1;

        let p_before = config.pause_before.unwrap_or(AcousticPause { duration_seconds: 0.0 }).duration_seconds;
        let p_after = config.pause_after.unwrap_or(AcousticPause { duration_seconds: 0.0 }).duration_seconds;

        Some((
            config.voice_family.clone(),
            text_content.to_string(),
            config.voice_volume,
            p_before,
            p_after
        ))
    }

    /// AI-facing Declarative Acoustics topology tracker
    pub fn ai_speech_css_summary(&self, node_id: u64) -> String {
        if let Some(config) = self.acoustic_nodes.get(&node_id) {
            format!("🗣️ CSS Speech 1 (Node #{}): Speak: {:?} | Voice: {} | Vol: {} | Global Utterances Processed: {}", 
                node_id, config.speak, config.voice_family, config.voice_volume, self.total_nodes_ingested)
        } else {
            format!("Node #{} employs OS default acoustic parameters", node_id)
        }
    }
}
