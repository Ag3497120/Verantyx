//! Dynamic context window budget manager.
//! 
//! This is one of Ronin's most critical subsystems for local LLM operation.
//! Unlike cloud-hosted models with 128K+ token limits, local models (Gemma 7B-27B)
//! have hard context windows. Exceeding this window causes severe quality degradation
//! or outright truncation. This module manages the token economy across a session.

use serde::{Deserialize, Serialize};

// ─────────────────────────────────────────────────────────────────────────────
// Context Slot Allocation
// ─────────────────────────────────────────────────────────────────────────────

/// Defines how the total context window is partitioned.
/// The sum of all allocated slots must not exceed the model's real limit.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContextBudget {
    /// Hard limit imposed by the model architecture
    pub model_max_tokens: usize,
    /// Reserved for the system prompt (memory injection + directives)
    pub system_reserved: usize,
    /// Reserved for each turn's user instruction
    pub user_turn_reserved: usize,
    /// Budget for the rolling conversation history
    pub history_budget: usize,
    /// Budget allocated to a single generation step
    pub generation_budget: usize,
}

impl ContextBudget {
    /// Standard budget for 8B models (e.g. Gemma 7B, Llama 3 8B).
    /// Context window is typically 8192 tokens. We run conservatively.
    pub fn for_8b() -> Self {
        Self {
            model_max_tokens: 8192,
            system_reserved: 1024,
            user_turn_reserved: 512,
            history_budget: 4096,
            generation_budget: 1024,
        }
    }

    /// Budget for 27B models (Gemma 27B, Mistral 24B, etc.)
    pub fn for_27b() -> Self {
        Self {
            model_max_tokens: 32768,
            system_reserved: 4096,
            user_turn_reserved: 2048,
            history_budget: 20000,
            generation_budget: 4096,
        }
    }

    /// Budget for 70B+ models or cloud providers.
    pub fn for_70b_plus() -> Self {
        Self {
            model_max_tokens: 128000,
            system_reserved: 16000,
            user_turn_reserved: 4096,
            history_budget: 90000,
            generation_budget: 16000,
        }
    }

    /// Returns the max tokens available for history loading.
    pub fn usable_history_tokens(&self) -> usize {
        self.history_budget
    }

    /// True if adding `additional` tokens would overflow the budget.
    pub fn would_overflow(&self, current_used: usize, additional: usize) -> bool {
        current_used + additional > self.model_max_tokens
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Context Compressor
// ─────────────────────────────────────────────────────────────────────────────

/// Strategies for compressing context when the budget is near-full.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum CompactionStrategy {
    /// Drop the oldest messages first (FIFO eviction)
    DropOldest,
    /// Summarize early conversation turns using a cheap local model
    SummarizeWithLocalModel,
    /// Keep only system + last N user/assistant turn pairs
    KeepLastNTurns(usize),
}

/// Token usage tracker for a live session.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct TokenLedger {
    pub system_used: usize,
    pub history_used: usize,
    pub current_generation_used: usize,
}

impl TokenLedger {
    pub fn total_used(&self) -> usize {
        self.system_used + self.history_used + self.current_generation_used
    }

    pub fn record_system(&mut self, tokens: usize) {
        self.system_used += tokens;
    }

    pub fn record_turn(&mut self, tokens: usize) {
        self.history_used += tokens;
    }

    pub fn reset_generation(&mut self) {
        self.current_generation_used = 0;
    }
}

/// Estimates token count using a rough character-to-token approximation.
/// Actual tokenization requires the model's specific tokenizer.
/// We use the UTF-8 character count / 3.5 heuristic (conservative for CJK).
pub fn estimate_tokens(text: &str) -> usize {
    let char_count = text.chars().count();
    let cjk_count = text.chars().filter(|c| is_cjk(*c)).count();
    let latin_count = char_count - cjk_count;
    // CJK characters average ~1.3 tokens each; latin averages ~0.25
    ((latin_count as f64 * 0.25) + (cjk_count as f64 * 1.3)).ceil() as usize + 1
}

fn is_cjk(c: char) -> bool {
    matches!(c,
        '\u{4E00}'..='\u{9FFF}' |   // CJK Unified Ideographs
        '\u{3040}'..='\u{309F}' |   // Hiragana
        '\u{30A0}'..='\u{30FF}'     // Katakana
    )
}
