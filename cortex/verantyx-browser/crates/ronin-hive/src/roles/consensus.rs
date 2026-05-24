use ronin_core::models::provider::{LlmProvider, LlmMessage};
use ronin_core::models::provider::ollama::OllamaProvider;
use ronin_core::models::sampling_params::{InferenceRequest, SamplingParams, PromptFormat};
use tracing::{info, warn};

pub struct LocalConsensusActor {
    provider: OllamaProvider,
    model_name: String,
}

impl LocalConsensusActor {
    pub fn new(host: String, port: u16, model: String) -> Self {
        Self {
            provider: OllamaProvider::new(&host, port),
            model_name: model,
        }
    }

    /// Read both observation strings and use Local LLM to merge them into a single timeline state summary.
    pub async fn merge_observations(&self, obs_a: &str, obs_b: &str) -> String {
        let req = InferenceRequest {
            model: self.model_name.clone(),
            sampling: SamplingParams::for_lightweight().with_max_tokens(1024),
            format: PromptFormat::OllamaChat,
            stream: false,
        };

        let hist = vec![
            LlmMessage::system("You are the Consensus Synthesizer for a Hive-mind AI swarm. Two different observers have reported their analysis to you. Merge both of their observations into a single, unified, objective, chronological log entry. Correct any discrepancies. Output ONLY the synthesized markdown log, nothing else."),
            LlmMessage::user(&format!("Observer A Reported:\n{}\n\nObserver B Reported:\n{}", obs_a, obs_b))
        ];

        match self.provider.invoke(&req, &hist).await {
            Ok(merged) => {
                info!("[ConsensusActor] Successfully merged dual observations.");
                merged
            },
            Err(e) => {
                warn!("[ConsensusActor] Failed to synthesize: {}. Returning concat.", e);
                // Fallback to simple concatenation if LLM fails
                format!("-- Observer A --\n{}\n-- Observer B --\n{}", obs_a, obs_b)
            }
        }
    }
}
