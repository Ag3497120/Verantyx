//! Web Speech API — W3C Speech Recognition
//!
//! Implements hardware microphone ingestion extracting linguistics bounds:
//!   - `SpeechRecognition` (§ 1): The acoustic mapping engine interface
//!   - Permission mediation (Audio capture OS security)
//!   - `result` event structures (`SpeechRecognitionResult` geometries)
//!   - `interimResults` dynamic prediction streams
//!   - AI-facing: Raw acoustic stream semantics ingestion topologies

use std::collections::HashMap;

/// Denotes the current state of the acoustic pipeline connected to the OS (§ 1.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RecognitionState { Idle, Listening, Processing, Error }

/// An extracted sentence mapping bound to confidence margins (§ 1.3)
#[derive(Debug, Clone)]
pub struct RecognitionHypothesis {
    pub transcript: String,
    pub confidence: f64, // 0.0 to 1.0 mapping
    pub is_final: bool, // False means the user is still speaking and the neural net is adjusting
}

/// High-level OS tracker for an active instance
#[derive(Debug, Clone)]
pub struct SpeechRecognitionSession {
    pub lang: String, // e.g. 'en-US'
    pub continuous: bool,
    pub interim_results: bool,
    pub state: RecognitionState,
    pub transcripts_emitted: u64,
}

/// The global Constraint Resolver governing acoustic hardware streams to linguistics mappings
pub struct WebSpeechRecognitionEngine {
    // Document ID -> (Session ID -> Session)
    pub active_sessions: HashMap<u64, HashMap<u64, SpeechRecognitionSession>>,
    pub next_session_id: u64,
    pub has_microphone_permission: bool,
    pub global_words_extracted: u64,
}

impl WebSpeechRecognitionEngine {
    pub fn new() -> Self {
        Self {
            active_sessions: HashMap::new(),
            next_session_id: 1,
            has_microphone_permission: false, // Governed by W3C Permissions bounds
            global_words_extracted: 0,
        }
    }

    /// JS execution: `recognition.start()` (§ 1.1)
    pub fn start_listening(&mut self, document_id: u64, lang: &str, continuous: bool, interim: bool) -> Result<u64, String> {
        if !self.has_microphone_permission {
            return Err("NotAllowedError: Acoustic capture permission denied by user".into());
        }

        let sid = self.next_session_id;
        self.next_session_id += 1;

        let docs = self.active_sessions.entry(document_id).or_default();
        docs.insert(sid, SpeechRecognitionSession {
            lang: lang.to_string(),
            continuous,
            interim_results: interim,
            state: RecognitionState::Listening,
            transcripts_emitted: 0,
        });

        // Instructs the underlying OS Neural Network/Microphone driver to wake up
        Ok(sid)
    }

    /// JS execution: `recognition.stop()` and `recognition.abort()`
    pub fn stop_listening(&mut self, document_id: u64, session_id: u64) {
        if let Some(docs) = self.active_sessions.get_mut(&document_id) {
            if let Some(session) = docs.get_mut(&session_id) {
                // Stop allows processing whatever is buffered. Abort kills the buffer.
                session.state = RecognitionState::Processing;
            }
        }
    }

    /// OS Callback: Underlying acoustic parser returns a guessed string
    pub fn simulate_acoustic_result(&mut self, document_id: u64, session_id: u64, transcript: &str, is_final: bool) -> Option<RecognitionHypothesis> {
        if let Some(docs) = self.active_sessions.get_mut(&document_id) {
            if let Some(session) = docs.get_mut(&session_id) {
                if !is_final && !session.interim_results {
                    return None; // Spec says don't send interim streams if JS didn't request them
                }

                session.transcripts_emitted += 1;
                self.global_words_extracted += transcript.split_whitespace().count() as u64;

                if is_final && !session.continuous {
                    session.state = RecognitionState::Idle;
                }

                return Some(RecognitionHypothesis {
                    transcript: transcript.to_string(),
                    confidence: 0.95,
                    is_final,
                });
                // In reality, this dispatches a `result` Event onto the DOM Object
            }
        }
        None
    }

    /// AI-facing Acoustic pipeline topographies
    pub fn ai_speech_summary(&self, document_id: u64) -> String {
        let active = self.active_sessions.get(&document_id).map_or(0, |s| s.len());
        format!("🎙️ Web Speech API (Doc #{}): {} Active Sessions | Listening Permission: {} | Global Words Parsed: {}", 
            document_id, active, self.has_microphone_permission, self.global_words_extracted)
    }
}
