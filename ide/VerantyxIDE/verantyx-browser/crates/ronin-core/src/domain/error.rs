use thiserror::Error;

#[derive(Error, Debug)]
pub enum RoninError {
    #[error("Network infrastructure failure: {0}")]
    Network(#[from] reqwest::Error),
    
    #[error("Fatal XML Stream Error while parsing ReAct output: {0}")]
    XmlStreamParse(String),
    
    #[error("Context window overflow in ReAct loop. Max tokens allowed: {max}, Utilized: {used}")]
    ContextOverflow { max: usize, used: usize },
    
    #[error("State Machine deadlocked at node: {state_node}")]
    FsmDeadlock { state_node: String },
    
    #[error("Model unauthorized or unsupported by current Tier Profile: {0}")]
    ModelUnsupported(String),
    
    #[error("Failed to execute tool chain: {0}")]
    ToolExecution(String),

    #[error("I/O failure during sandbox interaction: {0}")]
    Io(#[from] std::io::Error),
}

pub type Result<T> = std::result::Result<T, RoninError>;
