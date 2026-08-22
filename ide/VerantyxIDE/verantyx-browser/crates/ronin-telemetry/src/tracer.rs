use tracing::Level;
use tracing_subscriber::FmtSubscriber;
use anyhow::Result;

pub fn init_telemetry(verbose: bool) -> Result<()> {
    let level = if verbose { Level::DEBUG } else { Level::WARN };
    
    // Instead of raw printf, we use structured telemetry logging.
    // In the future this can be multiplexed to OpenTelemetry (OTLP) gRPC endpoints.
    let subscriber = FmtSubscriber::builder()
        .with_max_level(level)
        .with_file(true)
        .with_line_number(true)
        .with_thread_ids(true)
        .with_target(false)
        .finish();

    tracing::subscriber::set_global_default(subscriber)
        .map_err(|e| anyhow::anyhow!("Failed to set telemetry subscriber: {}", e))
}
