use super::jcross_memory::JCrossMemory;

pub struct MemoryQuery {
    pub concept: String,
    pub context: String,
}

pub struct Navigator;

impl Navigator {
    /// f_score: Core JCross multi-axis spatial distance function
    pub fn score(mem: &JCrossMemory, query: &MemoryQuery) -> f64 {
        // Concept similarity (mock generic substring logic; replace with IR graph matching later)
        let concept_match = if mem.concept.contains(&query.concept) || query.concept.contains(&mem.concept) { 1.0 } else { 0.1 };
        let context_match = if mem.context == query.context { 1.0 } else { 0.2 };
        
        // Time decay (higher time = older memory -> shifts farther away)
        let time_decay = mem.time * 0.1;
        
        (concept_match * 0.4) +
        (context_match * 0.2) +
        (mem.confidence * 0.2) +
        (mem.utility * 0.2) -
        time_decay
    }

    /// Spatial Shifting Strategy: Pushes low-priority memory away instead of deleting to prevent hallucination cycles
    pub fn shift_away(mem: &mut JCrossMemory) {
        mem.confidence *= 0.5; // lose certainty
        mem.utility *= 0.2; // severely drop usefulness
        mem.time += 1.0; // age memory
    }

    /// Promote memory that was successfully utilized in resolving the logic puzzle
    pub fn promote(mem: &mut JCrossMemory) {
        mem.confidence = (mem.confidence + 1.0).min(1.0);
        mem.utility = (mem.utility + 1.0).min(1.0);
        mem.time = 0.0; // reset to 'now'
    }
}
