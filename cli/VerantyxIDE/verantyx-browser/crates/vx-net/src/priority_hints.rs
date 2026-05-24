//! Priority Hints API — W3C Priority Hints
//!
//! Implements explicit developer control over resource loading prioritization:
//!   - `fetchpriority` attribute (§ 2): "high", "low", "auto" (default)
//!   - Fetch API integration (§ 3): `fetch(url, { priority: 'high' })`
//!   - Preload Integration: Bumping render-blocking font/script priority
//!   - Network Request Queue execution modeling based on `fetchpriority`
//!   - AI-facing: Resource fetch queue prioritization metrics

use std::collections::{BinaryHeap, HashMap};
use std::cmp::Ordering;

/// Developer signaled fetching priority for a resource (§ 2.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum FetchPriorityHint { Low = 1, Auto = 2, High = 3 }

/// Heuristic-determined baseline priority based on resource type (e.g. CSS > Image)
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum BaseResourceTypePriority {
    Idle = 10,
    Image = 20,
    ScriptAsync = 30,
    ScriptSync = 40,
    Stylesheet = 50,
    Document = 60,
}

#[derive(Debug, Clone)]
pub struct PrioritizedFetchTask {
    pub task_id: u64,
    pub url: String,
    pub base_priority: BaseResourceTypePriority,
    pub hint: FetchPriorityHint,
    pub insertion_order: u64, // Used for FIFO tie-breaking
}

// Orchestrating a Max-Heap for the network scheduler
impl PartialEq for PrioritizedFetchTask {
    fn eq(&self, other: &Self) -> bool { self.task_id == other.task_id }
}
impl Eq for PrioritizedFetchTask {}
impl PartialOrd for PrioritizedFetchTask {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> { Some(self.cmp(other)) }
}
impl Ord for PrioritizedFetchTask {
    fn cmp(&self, other: &Self) -> Ordering {
        // Priority calculation: Base Priority gets boosted/penalized by the Fetch Hint
        let self_score = (self.base_priority as i32) + match self.hint {
            FetchPriorityHint::High => 15,
            FetchPriorityHint::Auto => 0,
            FetchPriorityHint::Low => -15,
        };
        let other_score = (other.base_priority as i32) + match other.hint {
            FetchPriorityHint::High => 15,
            FetchPriorityHint::Auto => 0,
            FetchPriorityHint::Low => -15,
        };

        self_score.cmp(&other_score)
            .then_with(|| other.insertion_order.cmp(&self.insertion_order)) // Lower insertion is older (execute first)
    }
}

/// The global Resource Fetch Scheduling Engine
pub struct PriorityHintsEngine {
    pub execution_queue: BinaryHeap<PrioritizedFetchTask>,
    pub next_task_id: u64,
    pub fetch_history: Vec<(String, i32)>, // URL, Calculated Score
}

impl PriorityHintsEngine {
    pub fn new() -> Self {
        Self {
            execution_queue: BinaryHeap::new(),
            next_task_id: 1,
            fetch_history: Vec::new(),
        }
    }

    /// Entry point from HTML parser (`<img fetchpriority="high">`) or `fetch()` JS
    pub fn queue_resource(&mut self, url: &str, base: BaseResourceTypePriority, hint: FetchPriorityHint) {
        let task = PrioritizedFetchTask {
            task_id: self.next_task_id,
            url: url.to_string(),
            base_priority: base,
            hint,
            insertion_order: self.next_task_id,
        };
        self.next_task_id += 1;
        self.execution_queue.push(task);
    }

    /// Simulates the network daemon popping the most critical resource request to fire
    pub fn dequeue_next_fetch(&mut self) -> Option<String> {
        if let Some(task) = self.execution_queue.pop() {
            let score = (task.base_priority as i32) + match task.hint {
                FetchPriorityHint::High => 15,
                FetchPriorityHint::Auto => 0,
                FetchPriorityHint::Low => -15,
            };
            self.fetch_history.push((task.url.clone(), score));
            Some(task.url)
        } else {
            None
        }
    }

    /// AI-facing Fetch Queue orchestration summary
    pub fn ai_priority_summary(&self) -> String {
        format!("🚦 Priority Hints Scheduling: {} resources waiting in queue | Head of queue score approx: {}", 
            self.execution_queue.len(), 
            self.execution_queue.peek().map_or(0, |t| t.base_priority as i32))
    }
}
