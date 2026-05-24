use thiserror::Error;

#[derive(Error, Debug)]
pub enum HiveError {
    #[error("Message serialization failed: {0}")]
    Serialization(#[from] serde_json::Error),

    #[error("Agent {0} not found in hive")]
    AgentNotFound(String),

    #[error("Hive channel capacity exceeded limit")]
    ChannelOverflow,

    #[error("Unrecognized objective directive")]
    InvalidObjective,
}
