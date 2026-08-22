use crate::domain::error::Result;
use crate::models::provider::{LlmProvider, LlmMessage};
use crate::models::tier_calibration::TierProfile;
use crate::models::sampling_params::{InferenceRequest, PromptFormat};
use crate::engine::state_machine::{ReActStateMachine, Event, FsmState};
use crate::engine::xml_parser::parse_llm_stream;
use crate::engine::tool_dispatcher::ToolDispatcher;
use crate::engine::validator::{SandboxValidator, ValidationDecision};

pub struct RoninReactor {
    pub profile: TierProfile,
    pub fsm: ReActStateMachine,
    pub history: Vec<LlmMessage>,
    provider: Box<dyn LlmProvider>,
    dispatcher: ToolDispatcher,
    validator: SandboxValidator,
}

impl RoninReactor {
    pub fn new(profile: TierProfile, provider: Box<dyn LlmProvider>, dispatcher: ToolDispatcher) -> Self {
        let enforce_atomic = profile.strict_atomic_enforcement;
        Self {
            profile,
            fsm: ReActStateMachine::new(enforce_atomic),
            history: Vec::new(),
            provider,
            dispatcher,
            validator: SandboxValidator::default(),
        }
    }

    pub async fn dispatch_turn(&mut self, instruction: &str) -> Result<String> {
        // Boot process to analyze and inject user directive
        self.fsm.transition(Event::StartTurn(1))?;
        
        self.history.push(LlmMessage {
            role: "user".to_string(),
            content: instruction.to_string(),
        });

        loop {
            // FSM Check
            if let FsmState::Completed(res) = &self.fsm.current_state {
                return Ok(res.clone());
            }

            // LLM Generation Step
            let request = InferenceRequest {
                model: "gemma3:27b".to_string(),
                sampling: self.profile.sampling_params.clone(),
                format: PromptFormat::OllamaChat,
                stream: false,
            };
            let response = self.provider.invoke(
                &request,
                &self.history,
            ).await?;

            self.history.push(LlmMessage {
                role: "assistant".to_string(),
                content: response.clone(),
            });

            // Extract Action Node via Nom Parser
            match parse_llm_stream(&response) {
                Ok(payload) => {
                    let payload_content = payload.content.trim();
                    let (action_name, _action_payload) = if payload_content.starts_with("<payload>") {
                        // This logic requires better XML parsing, but for now we expect payload to be flat or just command execution
                        ("shell_exec", payload_content)
                    } else if payload_content.starts_with("<?xml") || payload_content.starts_with("<") {
                        ("shell_exec", payload_content)
                    } else {
                        (payload_content, "")
                    };

                    let action = action_name.to_string();
                    if action == "finish" || payload_content == "finish" {
                        self.fsm.transition(Event::Finish("Execution terminated by Commander.".to_string()))?;
                    } else {
                        self.fsm.transition(Event::EmitAction(action.clone()))?;
                        
                        // Wait for Observation logic
                        self.fsm.transition(Event::ObservationReceived)?;
                        
                        let mut args = std::collections::HashMap::new();
                        args.insert("command".to_string(), serde_json::Value::String(payload_content.to_string()));
                        
                        let tool_call = crate::engine::tool_dispatcher::ToolCall {
                            tool_name: action.clone(),
                            args,
                            raw_payload: payload_content.to_string(),
                        };
                        
                        let res = self.dispatcher.dispatch(tool_call).await;
                        
                        // Simple text parsing to check if it's an error exit
                        let observation = if res.output.contains("❌ EXIT") || res.output.contains("Command timed out") {
                            match self.validator.record_failure(&res.output) {
                                ValidationDecision::ContinueSelfCorrection => res.output.clone(),
                                ValidationDecision::RequireHigherTierAudit(_errors) => {
                                    format!("{} \n\n[SYSTEM] Critical recursive failure detected by SandboxValidator. Initiating autonomous Gemini Audit: Calling ask_gemini_browser with error logs...", res.output)
                                }
                            }
                        } else {
                            self.validator.record_success();
                            res.output.clone()
                        };

                        // Inject Observation back
                        self.history.push(LlmMessage {
                            role: "user".to_string(),
                            content: format!("[OBSERVATION]: {}", observation),
                        });
                        
                        self.fsm.transition(Event::Analyze)?;
                    }
                }
                Err(e) => {
                    self.fsm.transition(Event::Error(e.to_string()))?;
                    self.history.push(LlmMessage {
                        role: "user".to_string(),
                        content: format!("[SYSTEM ERROR]: {}", e.to_string()),
                    });
                    
                    if let FsmState::SelfCorrecting { .. } = self.fsm.current_state {
                        // Recover into a next iteration pass
                        self.fsm.transition(Event::Recover(99))?;
                    }
                }
            }
        }
    }
}
