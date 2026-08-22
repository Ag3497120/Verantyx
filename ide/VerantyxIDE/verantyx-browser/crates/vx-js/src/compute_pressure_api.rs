//! Compute Pressure API — W3C Compute Pressure
//!
//! Implements hardware utilization tracking for adaptive web application logic:
//!   - `PressureObserver` (§ 3): Emitting records when CPU pressure thresholds change
//!   - `PressureRecord` (§ 4): Nominal, Fair, Serious, and Critical states
//!   - OS-level Kernel integration mapping CPU throttling events
//!   - Frame-rate or video-adaptation heuristics
//!   - AI-facing: Real-time hardware thermal/compute limits

use std::collections::HashMap;

/// Represents the high-level semantic status of the underlying hardware (§ 4)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PressureState { Nominal, Fair, Serious, Critical }

/// Source of the pressure causing the state change
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PressureSource { Cpu, Thermal, Memory }

/// A discrete measurement emitted to active observers
#[derive(Debug, Clone)]
pub struct PressureRecord {
    pub state: PressureState,
    pub source: PressureSource,
    pub time_epoch_ms: f64, // DOMHighResTimeStamp
}

/// The global Compute Pressure Engine monitoring OS kernel boundaries
pub struct ComputePressureEngine {
    // Simulated global hardware state
    pub current_cpu_state: PressureState,
    pub current_thermal_state: PressureState,
    
    // Document ID -> (Observer ID -> Last Emitted Record)
    pub observers: HashMap<u64, HashMap<u64, PressureRecord>>,
    pub total_records_emitted: u64,
}

impl ComputePressureEngine {
    pub fn new() -> Self {
        Self {
            current_cpu_state: PressureState::Nominal,
            current_thermal_state: PressureState::Nominal,
            observers: HashMap::new(),
            total_records_emitted: 0,
        }
    }

    /// JS execution: `observer.observe('cpu')`
    pub fn register_observer(&mut self, document_id: u64, observer_id: u64, source: PressureSource) {
        let doc_observers = self.observers.entry(document_id).or_default();
        
        let initial_state = match source {
            PressureSource::Cpu => self.current_cpu_state,
            PressureSource::Thermal => self.current_thermal_state,
            PressureSource::Memory => PressureState::Fair,
        };

        doc_observers.insert(observer_id, PressureRecord {
            state: initial_state,
            source,
            time_epoch_ms: 0.0, // Instantly resolves to current time
        });
    }

    /// OS Kernel Callback: When the CPU governor engages throttling
    pub fn update_hardware_pressure(&mut self, state: PressureState, source: PressureSource, timestamp: f64) {
        match source {
            PressureSource::Cpu => self.current_cpu_state = state,
            PressureSource::Thermal => self.current_thermal_state = state,
            _ => {}
        }

        // Broadcast to relevant observers
        for doc_observers in self.observers.values_mut() {
            for (_, record) in doc_observers.iter_mut() {
                if record.source == source && record.state != state {
                    record.state = state;
                    record.time_epoch_ms = timestamp;
                    self.total_records_emitted += 1;
                    // Internally triggers the JS Callback queue
                }
            }
        }
    }

    /// JS execution: `observer.unobserve('cpu')`
    pub fn remove_observer(&mut self, document_id: u64, observer_id: u64) {
        if let Some(doc_observers) = self.observers.get_mut(&document_id) {
            doc_observers.remove(&observer_id);
        }
    }

    /// AI-facing Compute Pressure topologies
    pub fn ai_compute_pressure_summary(&self, document_id: u64) -> String {
        let count = self.observers.get(&document_id).map_or(0, |o| o.len());
        format!("🌡️ Compute Pressure API (Doc #{}): {} Active Observers | OS State - CPU: {:?} / Thermal: {:?} | Records Evicted: {}", 
            document_id, count, self.current_cpu_state, self.current_thermal_state, self.total_records_emitted)
    }
}
