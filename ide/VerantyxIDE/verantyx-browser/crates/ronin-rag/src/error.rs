use thiserror::Error;

#[derive(Error, Debug)]
pub enum RagError {
    #[error("Failed to chunk file due to malformed utf8: {0}")]
    MalformedEncoding(String),

    #[error("Embedding provider timeout: {0}")]
    ProviderTimeout(String),
    
    #[error("Storage engine I/O failure: {0}")]
    StorageIo(#[from] std::io::Error),
}
