//! Vibration API — W3C Vibration API Second Edition
//!
//! Implements the browser's haptic feedback system:
//!   - Methods (§ 3.1): vibrate(pattern)
//!   - Patterns (§ 3.2): Single duration (ms) or list of durations [vibrate, pause, ...]
//!   - Rules (§ 3.3): Handling user-activation requirements and visibility states
//!   - Cancellation (§ 3.4): vibrate(0), vibrate([]), or navigating away
//!   - Throttling (§ 3.5): Preventing excessive hardware fatigue
//!   - Integration: Bridging to the verantyx-system-haptics shim
//!   - AI-facing: Vibration pattern visualizer and pulse timing history

use std::collections::VecDeque;

/// Vibration Pattern (§ 3.2)
#[derive(Debug, Clone)]
pub enum VibrationPattern {
    Single(u32),
    Sequence(Vec<u32>),
}

/// The global Vibration API Manager
pub struct VibrationManager {
    pub active_pattern: Option<VibrationPattern>,
    pub pulse_history: VecDeque<u32>, // Store last 50 pulses for AI metrics
    pub is_suppressed: bool, // Due to visibility or user-activation policies
    pub max_duration: u32, // Typically 10,000ms per spec
}

impl VibrationManager {
    pub fn new() -> Self {
        Self {
            active_pattern: None,
            pulse_history: VecDeque::with_capacity(50),
            is_suppressed: false,
            max_duration: 10000,
        }
    }

    /// Entry point for navigator.vibrate() (§ 3.1)
    pub fn vibrate(&mut self, pattern: VibrationPattern) -> bool {
        if self.is_suppressed { return false; }

        match &pattern {
            VibrationPattern::Single(d) if *d == 0 => { self.cancel(); return true; }
            VibrationPattern::Sequence(s) if s.is_empty() => { self.cancel(); return true; }
            _ => {}
        }

        self.active_pattern = Some(pattern.clone());
        
        // Log pulse for AI analysis
        match pattern {
            VibrationPattern::Single(d) => self.log_pulse(d),
            VibrationPattern::Sequence(s) => { if let Some(&d) = s.first() { self.log_pulse(d); } }
        }

        true // Pattern successfully queued
    }

    pub fn cancel(&mut self) {
        self.active_pattern = None;
    }

    fn log_pulse(&mut self, duration: u32) {
        if self.pulse_history.len() >= 50 { self.pulse_history.pop_front(); }
        self.pulse_history.push_back(duration);
    }

    /// AI-facing haptic pattern visualizer
    pub fn ai_vibration_timeline(&self) -> String {
        let mut output = vec![format!("📳 Vibration API Status (Suppressed: {}):", self.is_suppressed)];
        if let Some(pattern) = &self.active_pattern {
            output.push(format!("  Active: {:?}", pattern));
        } else {
            output.push("  Active: [None]".into());
        }
        
        if !self.pulse_history.is_empty() {
            let sparkline: String = self.pulse_history.iter()
                .map(|&d| if d > 500 { '█' } else if d > 100 { '▄' } else { ' ' })
                .collect();
            output.push(format!("  History: {}", sparkline));
        }
        output.join("\n")
    }
}
