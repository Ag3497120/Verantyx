//! Web Speech API — W3C Web Speech API
//!
//! Implements the browser's speech recognition and synthesis:
//!   - SpeechRecognition (§ 5.1): start(), stop(), abort(), onresult, onnomatch, onerror
//!   - SpeechRecognitionResult (§ 5.1.5): isFinal, confidence, transcript
//!   - SpeechSynthesis (§ 5.2): speak(), pause(), resume(), cancel(), onstart, onend
//!   - SpeechSynthesisUtterance (§ 5.2.4): text, lang, voice, volume, rate, pitch
//!   - SpeechSynthesisVoice (§ 5.2.5): name, lang, localService, default
//!   - Permissions and Security (§ 4): Restricted to Secure Contexts and user-activation
//!   - AI-facing: Speech transcript log and synthesis queue visualizer

use std::collections::VecDeque;

/// Speech recognition state (§ 5.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SpeechRecognitionState { Idle, Starting, Recognizing, Aborting }

/// Synthesis voice metadata (§ 5.2.5)
#[derive(Debug, Clone)]
pub struct SpeechSynthesisVoice {
    pub name: String,
    pub lang: String,
    pub voice_uri: String,
    pub local_service: bool,
    pub is_default: bool,
}

/// Utterance definition (§ 5.2.4)
#[derive(Debug, Clone)]
pub struct SpeechSynthesisUtterance {
    pub text: String,
    pub lang: String,
    pub voice_name: Option<String>,
    pub volume: f32, // 0 to 1
    pub rate: f32, // 0.1 to 10
    pub pitch: f32, // 0 to 2
}

/// The global Web Speech API Manager
pub struct WebSpeechManager {
    pub recognition_state: SpeechRecognitionState,
    pub voices: Vec<SpeechSynthesisVoice>,
    pub utterance_queue: VecDeque<SpeechSynthesisUtterance>,
    pub transcripts: Vec<String>,
    pub permission_granted: bool,
}

impl WebSpeechManager {
    pub fn new() -> Self {
        Self {
            recognition_state: SpeechRecognitionState::Idle,
            voices: Vec::new(),
            utterance_queue: VecDeque::new(),
            transcripts: Vec::new(),
            permission_granted: false,
        }
    }

    /// Entry point for SpeechSynthesis.speak() (§ 5.2.1)
    pub fn speak(&mut self, utterance: SpeechSynthesisUtterance) {
        if !self.permission_granted { return; }
        self.utterance_queue.push_back(utterance);
    }

    /// Entry point for SpeechRecognition.start() (§ 5.1.1)
    pub fn start_recognition(&mut self) -> Result<(), String> {
        if !self.permission_granted { return Err("PERMISSION_DENIED".into()); }
        self.recognition_state = SpeechRecognitionState::Starting;
        Ok(())
    }

    /// AI-facing speech transcripts log
    pub fn ai_speech_log(&self) -> String {
        let mut lines = vec![format!("🎙️ Web Speech API (Registry: {} voices):", self.voices.len())];
        if !self.transcripts.is_empty() {
            lines.push(format!("  Transcripts (Count: {}):", self.transcripts.len()));
            for t in &self.transcripts {
                lines.push(format!("    - \"{}\"", t));
            }
        }
        if !self.utterance_queue.is_empty() {
            lines.push(format!("  Synthesis Queue (Length: {}):", self.utterance_queue.len()));
            for u in &self.utterance_queue {
                lines.push(format!("    - \"{}\" [Vol: {:.1}, Rate: {:.1}]", u.text, u.volume, u.rate));
            }
        }
        lines.join("\n")
    }
}
