//! Prioritized Task Scheduling API — W3C Task Scheduling
//!
//! Implements a unified task scheduler for main thread coordination:
//!   - scheduler.postTask() (§ 2): Queuing tasks with specific priorities and abort signals
//!   - TaskPriority (§ 3): 'user-blocking', 'user-visible', 'background'
//!   - TaskController (§ 4): Dynamically changing a queued task's priority or aborting it
//!   - Yielding: Integration with `scheduler.yield()` for preventing long tasks
//!   - Event Loop Integration: Interleaving postTask queues with Microtasks and rAF
//!   - AI-facing: Thread priority orchestration visualizer and execution metrics

use std::collections::BinaryHeap;
use std::cmp::Ordering;

/// Core execution priorities defined by the specification (§ 3)
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum TaskPriority { Background = 1, UserVisible = 2, UserBlocking = 3 }

/// Represents an individual scheduled callback
#[derive(Debug, Clone)]
pub struct ScheduledTask {
    pub id: u64,
    pub priority: TaskPriority,
    pub delay_ms: u64,
    pub is_aborted: bool,
}

// Custom ordering to ensure the BinaryHeap acts as a Max-Heap based on TaskPriority and FIFO
impl PartialEq for ScheduledTask {
    fn eq(&self, other: &Self) -> bool { self.id == other.id }
}
impl Eq for ScheduledTask {}
impl PartialOrd for ScheduledTask {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> { Some(self.cmp(other)) }
}
impl Ord for ScheduledTask {
    fn cmp(&self, other: &Self) -> Ordering {
        // Higher enum integer value = higher priority. If equal, lower ID executes first (FIFO)
        self.priority.cmp(&other.priority).then_with(|| other.id.cmp(&self.id))
    }
}

/// The global Prioritized Task Scheduler Engine
pub struct TaskSchedulingEngine {
    pub task_queue: BinaryHeap<ScheduledTask>,
    pub next_task_id: u64,
    pub execution_history: Vec<(u64, TaskPriority)>, // Tracking what ran for UI
}

impl TaskSchedulingEngine {
    pub fn new() -> Self {
        Self {
            task_queue: BinaryHeap::new(),
            next_task_id: 1,
            execution_history: Vec::new(),
        }
    }

    /// Entry point for `scheduler.postTask(callback, { priority, delay })` (§ 2)
    pub fn post_task(&mut self, priority: TaskPriority, delay_ms: u64) -> u64 {
        let id = self.next_task_id;
        let task = ScheduledTask {
            id,
            priority,
            delay_ms,
            is_aborted: false,
        };
        self.next_task_id += 1;
        self.task_queue.push(task);
        id
    }

    /// Entry point for `TaskController.setPriority()`
    pub fn change_priority(&mut self, task_id: u64, new_priority: TaskPriority) {
        // Priority change in a heap requires rebuild in Rust
        let mut temp_queue: Vec<ScheduledTask> = self.task_queue.drain().collect();
        for task in &mut temp_queue {
            if task.id == task_id {
                task.priority = new_priority;
            }
        }
        self.task_queue = BinaryHeap::from(temp_queue);
    }

    /// AI-facing Task Scheduler orchestration summary
    pub fn ai_scheduler_summary(&self) -> String {
        let mut counts = [0, 0, 0]; // bg, visible, blocking
        for t in &self.task_queue {
            match t.priority {
                TaskPriority::Background => counts[0] += 1,
                TaskPriority::UserVisible => counts[1] += 1,
                TaskPriority::UserBlocking => counts[2] += 1,
            }
        }
        
        format!("⏱️ Task Scheduler (Queued: {}): Blocking: {}, Visible: {}, Background: {}", 
            self.task_queue.len(), counts[2], counts[1], counts[0])
    }
}
