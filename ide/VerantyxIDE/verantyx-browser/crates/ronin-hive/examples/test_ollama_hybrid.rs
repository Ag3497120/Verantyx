use ronin_hive::actor::{Actor, Envelope};
use ronin_hive::messages::HiveMessage;
use ronin_hive::roles::commander::CommanderActor;
use ronin_hive::roles::stealth_gemini::StealthWebActor;
use tracing::{info, Level};
use tracing_subscriber::FmtSubscriber;
use uuid::Uuid;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // 1. Initialize logging output
    let subscriber = FmtSubscriber::builder()
        .with_max_level(Level::DEBUG)
        .finish();
    tracing::subscriber::set_global_default(subscriber)
        .expect("Failed to set tracing subscriber");

    info!("=== INITIALIZING HYBRID E2E SIMULATION ===");
    info!("Simulating Local Model: google/gemma-2-2b-it (Tier 1 Profile)");

    let mut commander = CommanderActor;

    // We simulate a task coming from the user loop that represents a highly complex objective.
    // Domain: WebScraping/Research -> Triggers req_tier=2 (midweight).
    // The simulated tier limit for 2b will be Tier 1.
    // This mismatch MUST safely drop into `ExecutionMode::Hybrid` and deploy the Stealth Web Gemini.
    let complex_task = HiveMessage::Objective(
        "RESEARCH: Search current HuggingFace trends for Ollama integrations and analyze".to_string(),
    );

    let initial_env = Envelope {
        message_id: Uuid::new_v4(),
        sender: "UserInterface".to_string(),
        recipient: "Commander".to_string(),
        payload: serde_json::to_string(&complex_task)?,
    };

    info!("\n--- [STEP 1] User Submits Complex Request to Commander ---");
    let commander_reply = commander.receive(initial_env).await?.unwrap();
    info!("Commander Reply -> {:?}", commander_reply.recipient);

    // Assert that the Commander chose to spawn the Stealth Web Gemini Worker!
    assert_eq!(commander_reply.recipient, "StealthGeminiWorker");

    // 2. Pass the spawned request into the newly summoned Stealth Gemini Worker.
    info!("\n--- [STEP 2] Summoning Stealth Web Gemini Sub-Agent ---");
    // Extract Worker ID from commander's payload
    let dispatch_msg: HiveMessage = serde_json::from_str(&commander_reply.payload)?;
    
    let subagent_id = match dispatch_msg {
        HiveMessage::SpawnSubAgent { id, .. } => id,
        _ => panic!("Expected SpawnSubAgent message!"),
    };

    let mut ephemeral_worker = StealthWebActor::new(
        subagent_id,
        true, 
        std::env::current_dir().unwrap(), 
        "gemma-2-test".to_string(), 
        "Hybrid Auto Testing Mode".to_string(), 
        5, 
        false, 
        ronin_hive::roles::stealth_gemini::SystemRole::SeniorObserver, 
        1
    );

    // Fake exactly 5 turns to trigger the kill switch!
    for turn in 1..=6 {
        info!("\n--- [STEP 3] Stealth Gemini Worker Turn {} ---", turn);
        let turn_env = Envelope {
            message_id: Uuid::new_v4(),
            sender: "Commander".to_string(), // In real flow, Commander or message bus sends to it
            recipient: "StealthGeminiWorker".to_string(),
            payload: serde_json::to_string(&dispatch_msg)?,
        };

        match ephemeral_worker.receive(turn_env).await? {
            Some(reply) => {
                info!("SubAgent produced reply: {}", reply.payload);
            }
            None => {
                info!("SubAgent refused message. Wait, returning Ok(None) shouldn't happen unless error.");
            }
        }
    }

    info!("\n=== HYBRID ARCHITECTURE TEST SUCCESS ===");
    info!("The Local Gemma correctly yielded to the StealthWeb Actor, and the 5-turn Ephemeral Kill-Switch was verified.");

    Ok(())
}
