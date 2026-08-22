use serde::{Deserialize, Serialize};
use crate::models::sampling_params::SamplingParams;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum InferenceTier {
    Lightweight,
    Midweight,
    Heavyweight,
}

impl InferenceTier {
    pub fn numeric_weight(&self) -> u8 {
        match self {
            Self::Lightweight => 1,
            Self::Midweight => 2,
            Self::Heavyweight => 3,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TierProfile {
    pub name: String,
    pub max_parallel_tools: u8,
    pub max_web_subagents: u8,
    pub strict_atomic_enforcement: bool,
    pub max_context_tokens: usize,
    pub temperature: f32,
    pub system_directive_preset: PresetStrategy,
    pub sampling_params: SamplingParams,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum PresetStrategy {
    AtomicObservation,
    StandardBatch,
    UnboundParallel,
}

impl TierProfile {
    pub fn extrapolate_from_model(model_name: &str) -> Self {
        // Safe extraction of parameters
        let params = if let Some(idx) = model_name.find('b') {
            let num_str: String = model_name[..idx].chars().rev().take_while(|c| c.is_ascii_digit()).collect();
            let parsed_num: String = num_str.chars().rev().collect();
            parsed_num.parse::<u32>().unwrap_or(0)
        } else {
            // Default assumes a standard midweight if unknown
            27
        };

        if params <= 10 {
            Self {
                name: format!("Tier 1 ({}B) - High Strictness", params),
                max_parallel_tools: 1,
                max_web_subagents: 1, // Only 1 external worker
                strict_atomic_enforcement: true,
                max_context_tokens: 8192,
                temperature: 0.1,
                system_directive_preset: PresetStrategy::AtomicObservation,
                sampling_params: SamplingParams::for_lightweight(),
            }
        } else if params <= 35 {
            Self {
                name: format!("Tier 2 ({}B) - Standard Execution", params),
                max_parallel_tools: 3,
                max_web_subagents: 5, // A small swarm of external workers
                strict_atomic_enforcement: false,
                max_context_tokens: 32768,
                temperature: 0.3,
                system_directive_preset: PresetStrategy::StandardBatch,
                sampling_params: SamplingParams::for_midweight(),
            }
        } else {
            Self {
                name: format!("Tier 3 ({}B) - Unbound Orchestration", params),
                max_parallel_tools: 15,
                max_web_subagents: 15, // Free multi-swarm capabilities
                strict_atomic_enforcement: false,
                max_context_tokens: 128000,
                temperature: 0.5,
                system_directive_preset: PresetStrategy::UnboundParallel,
                sampling_params: SamplingParams::for_heavyweight(),
            }
        }
    }

    pub fn generate_sys_prompt(&self) -> String {
        match self.system_directive_preset {
            PresetStrategy::AtomicObservation => "
[RONIN NEURAL LINK: ATOMIC MODE]
Your context limit and reasoning parameters require strict serialization.
Action -> Observation must be a 1-to-1 ratio. NEVER chain multiple actions.
Wait for the resulting `stderr`/`stdout` before planning your next step.
".trim().to_string(),
            PresetStrategy::StandardBatch => "
[RONIN NEURAL LINK: STANDARD BATCH]
Standard OS delegation authorized. You may bundle highly correlated tool invocations 
within a single turn, provided they do not conflict in OS state.
".trim().to_string(),
            PresetStrategy::UnboundParallel => "
[RONIN NEURAL LINK: UNBOUND]
Full parallel capacity unleashed. Execute massive multi-file edits or heavy MCP polling 
simultaneously. System memory handles deep AST context merging autonomously.
".trim().to_string(),
        }
    }
}
