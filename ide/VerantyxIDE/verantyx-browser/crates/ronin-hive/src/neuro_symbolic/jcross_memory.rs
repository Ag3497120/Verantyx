use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JCrossMemory {
    pub concept: String,
    pub context: String,
    pub time: f64,
    pub confidence: f64,
    pub utility: f64,
    pub relations: Vec<String>,
}

impl JCrossMemory {
    pub fn new(concept: &str, context: &str) -> Self {
        Self {
            concept: concept.to_string(),
            context: context.to_string(),
            time: 0.0, // 0 = now
            confidence: 1.0, // verified hypothesis
            utility: 1.0, // highest current value
            relations: Vec::new(),
        }
    }

    /// Renders the 6-axis structure to the targeted JCross spatial format
    pub fn to_jcross_string(&self) -> String {
        let relations_str = if self.relations.is_empty() {
            "[]".to_string()
        } else {
            let quoted: Vec<String> = self.relations.iter().map(|r| format!("\"{}\"", r)).collect();
            format!("[{}]", quoted.join(", "))
        };

        format!(
            "@JCross.Memory\nConcept: \"{}\"\nContext: \"{}\"\nTime: {:.1}\nConfidence: {:.1}\nUtility: {:.1}\nRelations: {}\n",
            self.concept, self.context, self.time, self.confidence, self.utility, relations_str
        )
    }
}
