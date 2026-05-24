use crate::domain::error::{Result, RoninError};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum FsmState {
    /// Initializing context and loading environment variables
    Booting,
    
    /// Agent is analyzing observation data or user input
    Thinking { turn: u32 },
    
    /// Awaiting tool execution or OS interaction
    Acting { turn: u32, tool_name: String },
    
    /// Collecting stdout/stderr from Sandbox
    Observing { turn: u32 },
    
    /// Agent hit error condition and is preparing to self-correct
    SelfCorrecting { cause: String },
    
    /// Final condition reached, success and termination
    Completed(String),
}

pub struct ReActStateMachine {
    pub current_state: FsmState,
    pub enforce_strict_atomic: bool,
}

impl ReActStateMachine {
    pub fn new(strict_mode: bool) -> Self {
        Self {
            current_state: FsmState::Booting,
            enforce_strict_atomic: strict_mode,
        }
    }

    pub fn transition(&mut self, next_event: Event) -> Result<()> {
        match (&self.current_state, next_event) {
            (FsmState::Booting, Event::StartTurn(t)) => {
                self.current_state = FsmState::Thinking { turn: t };
            }
            (FsmState::Thinking { turn }, Event::EmitAction(tool)) => {
                self.current_state = FsmState::Acting { turn: *turn, tool_name: tool };
            }
            (FsmState::Thinking { .. }, Event::Finish(result)) => {
                self.current_state = FsmState::Completed(result);
            }
            (FsmState::Acting { turn, .. }, Event::ObservationReceived) => {
                self.current_state = FsmState::Observing { turn: *turn };
            }
            (FsmState::Observing { turn }, Event::Analyze) => {
                // Return to thinking phase for next logic block
                self.current_state = FsmState::Thinking { turn: *turn + 1 };
            }
            (_state, Event::Error(e)) => {
                self.current_state = FsmState::SelfCorrecting { cause: e };
            }
            (FsmState::SelfCorrecting { .. }, Event::Recover(t)) => {
                self.current_state = FsmState::Thinking { turn: t };
            }
            (current_state, event) => {
                return Err(RoninError::FsmDeadlock {
                    state_node: format!("Cannot process {:?} from {:?}", event, current_state),
                });
            }
        }
        Ok(())
    }
}

#[derive(Debug, Clone)]
pub enum Event {
    StartTurn(u32),
    EmitAction(String),
    ObservationReceived,
    Analyze,
    Finish(String),
    Error(String),
    Recover(u32),
}
