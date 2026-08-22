use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReplaceRequest {
    /// Target file relative path
    pub path: String,
    /// Exact match block (or fuzzy match block) to replace
    pub search: String,
    /// Replacement content
    pub replace: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EditResult {
    /// True if patch applied successfully
    pub success: bool,
    /// Path modified
    pub path: String,
    /// Feedback string for LLM
    pub feedback: String,
}

impl EditResult {
    pub fn ok(path: &str, feedback: impl Into<String>) -> Self {
        Self {
            success: true,
            path: path.to_string(),
            feedback: feedback.into(),
        }
    }

    pub fn err(path: &str, feedback: impl Into<String>) -> Self {
        Self {
            success: false,
            path: path.to_string(),
            feedback: feedback.into(),
        }
    }
}
