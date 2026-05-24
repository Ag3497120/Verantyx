use anyhow::Result;
use tracing::{info, warn};
use uuid::Uuid;
use chrono::{Local, Timelike, Duration};
use ronin_hive::actor::{Actor, Envelope};
use ronin_hive::roles::{commander::CommanderActor, stealth_gemini::{StealthWebActor, SystemRole}};
use tokio::time::sleep;

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt::init();

    info!("\n=== [ AI_SYS ] RONIN NIGHT WATCH DAEMON BOOT SEQUENCE ===");
    info!("The Night Watch scheduler is now active. It will autonomously spin up the Cross Space Engine while you are sleeping to perform UI Regression checks and self-evolution.");

    // Load Configuration or Spawn Interactive Setup Wizard
    let cwd = std::env::current_dir().unwrap();
    let config = ronin_hive::config::VerantyxConfig::load_or_wizard(&cwd);

    let target_hour = config.scheduler.night_watch_hour as u32;

    if config.scheduler.night_watch_hour < 0 {
        warn!("⏸️ [NIGHT_WATCH] Scheduler has been disabled by User Config (Night Watch Hour = -1).");
        warn!("The Daemon will remain alive but will NOT execute autonomous sweeps.");
        loop {
            sleep(std::time::Duration::from_secs(86400)).await;
        }
    }

    // Loop indefinitely
    loop {
        // 1. Calculate Time until Target Local Time
        let now = Local::now();
        
        let mut next_run = now.date_naive().and_hms_opt(target_hour, 0, 0).unwrap();
        if now.time().hour() >= target_hour {
            // It's past 3 AM today, so schedule for tomorrow 3 AM
            next_run += Duration::days(1);
        }
        
        let next_run_dt = next_run.and_local_timezone(Local).unwrap();
        let sleep_duration = (next_run_dt - now).to_std().unwrap_or(std::time::Duration::from_secs(1));

        // For testing/demonstration if the user runs the cargo command explicitly, we will execute immediately on first boot!
        static mut FIRST_BOOT: bool = true;
        let is_first = unsafe { FIRST_BOOT };
        unsafe { FIRST_BOOT = false };

        if is_first {
            info!("⚙️ [NIGHT_WATCH] First Boot Override: Running Immediate Verification Sweep...");
        } else {
            let hours = sleep_duration.as_secs() / 3600;
            let mins = (sleep_duration.as_secs() % 3600) / 60;
            info!("⏳ [NIGHT_WATCH] Entering Hibernate Mode. Next autonomous UI check scheduled in {} hours {} minutes (at {}).", hours, mins, next_run_dt);
            sleep(sleep_duration).await;
        }

        info!("\n--- [NIGHT_WATCH] INITIATING DIAGNOSTIC REGRESSION SWEEP ---");

        let cwd = std::env::current_dir().unwrap();
        let experience_path = cwd.join(".ronin").join("experience.jcross");

        let mut objective = String::from("Google Geminiで「おはよう」と挨拶して送信してください。");
        
        if experience_path.exists() {
            let ex = std::fs::read_to_string(&experience_path).unwrap_or_default();
            if !ex.is_empty() {
                info!("📚 [NIGHT_WATCH] Experience File Found. Verifying past operational successes against live DOM...");
                objective = format!("【リグレッションテスト】過去に見つけた成功体験（以下のJCross記憶空間内容）が現在も有効か検証し、動作確認を行ってください。\nもし失敗した場合は別のアプローチに自己進化して記憶を更新してください。\n\n{}", ex.chars().take(2000).collect::<String>());
            }
        } else {
            warn!("⚠️ [NIGHT_WATCH] No experience.jcross found. Executing default seed mission.");
        }

        // 2. Spin up the Core Engine
        let mut commander = CommanderActor;
        
        let complex_task = ronin_hive::messages::HiveMessage::Objective(objective);

        let initial_env = Envelope {
            message_id: Uuid::new_v4(),
            sender: "NightWatchTimer".to_string(),
            recipient: "Commander".to_string(),
            payload: serde_json::to_string(&complex_task)?,
        };

        info!("🧠 [NIGHT_WATCH] Dispatching Commander...");
        let commander_reply: Envelope = commander.receive(initial_env).await?.unwrap();

        if commander_reply.recipient == "StealthGeminiWorker" {
            let dispatch_msg: ronin_hive::messages::HiveMessage = serde_json::from_str(&commander_reply.payload)?;
            let subagent_id = match dispatch_msg.clone() {
                ronin_hive::messages::HiveMessage::SpawnSubAgent { id, .. } => id,
                _ => panic!("Expected SpawnSubAgent message!"),
            };

            let mut stealth_worker = StealthWebActor::new(
                subagent_id,
                true, 
                cwd.clone(), 
                "gemma-2-test".to_string(), 
                "Hybrid Night Watch Mode".to_string(), 
                15, // High turn limit for overnight brute-forcing
                false, 
                SystemRole::SeniorObserver, 
                10
            );

            // Execute the worker until it finishes
            let turn_env = Envelope {
                message_id: Uuid::new_v4(),
                sender: "NightWatchTimer".to_string(),
                recipient: "StealthGeminiWorker".to_string(),
                payload: serde_json::to_string(&dispatch_msg)?,
            };

            info!("🕸️ [NIGHT_WATCH] Engaging Stealth Web Gemini for Live DOM Evaluation...");
            if let Ok(Some(reply)) = stealth_worker.receive(turn_env).await {
                info!("✅ [NIGHT_WATCH] SubAgent Regression Test Completed.");
                info!("📝 Final Knowledge Render:\n{}", reply.payload);
            } else {
                warn!("⚠️ [NIGHT_WATCH] SubAgent failed to complete verification.");
            }
        }

        info!("💤 [NIGHT_WATCH] Sweep Complete. Returning to hibernate mode.");
    }
}
