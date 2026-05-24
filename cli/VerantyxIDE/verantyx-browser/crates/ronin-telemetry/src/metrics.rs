use std::sync::atomic::{AtomicUsize, Ordering};
use tracing::info;

/// Global atomic metric for tracking API token costs across the entire hive
pub struct TokenMeter {
    prompt_tokens: AtomicUsize,
    completion_tokens: AtomicUsize,
}

impl TokenMeter {
    pub const fn new() -> Self {
        Self {
            prompt_tokens: AtomicUsize::new(0),
            completion_tokens: AtomicUsize::new(0),
        }
    }

    pub fn record(&self, prompt: usize, completion: usize) {
        self.prompt_tokens.fetch_add(prompt, Ordering::SeqCst);
        self.completion_tokens.fetch_add(completion, Ordering::SeqCst);
        
        info!(
            target: "ronin_metrics",
            prompt = prompt,
            completion = completion,
            total_session_prompt = self.prompt_tokens.load(Ordering::SeqCst),
            total_session_completion = self.completion_tokens.load(Ordering::SeqCst),
            "Token consumption recorded"
        );
    }
}

pub struct PipelineTrace {
    pub name: String,
    start_time: std::time::Instant,
}

impl PipelineTrace {
    pub fn start(name: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            start_time: std::time::Instant::now(),
        }
    }

    pub fn end(self) {
        let elapsed = self.start_time.elapsed();
        info!(
            target: "ronin_pipeline_trace",
            pipeline_name = %self.name,
            duration_ms = elapsed.as_millis(),
            "Pipeline completed"
        );
    }
}
