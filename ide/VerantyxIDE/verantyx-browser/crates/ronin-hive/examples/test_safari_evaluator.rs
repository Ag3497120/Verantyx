use ronin_hive::actor::{Actor, Envelope};
use ronin_hive::messages::HiveMessage;
use ronin_hive::roles::safari_evaluator::SafariEvaluatorActor;
use uuid::Uuid;

#[tokio::main]
async fn main() {
    // 1. Setup local variables
    let id = Uuid::new_v4();
    let cwd = std::env::current_dir().unwrap();
    let is_japanese_mode = true;

    // 2. Write a mock JCross Intent for Diff Verification testing
    let intent_jcross = "@JCross.Intent\nExpectedState: Sign In, Verify\nStatus: Pending\nTimestamp: 2026-04-05\n";
    let _ = std::fs::create_dir_all(cwd.join(".ronin"));
    let _ = std::fs::write(cwd.join(".ronin").join("intent.jcross"), intent_jcross);

    // 3. Spool up the Safari Markdown & Geometric Verifier
    let mut actor = SafariEvaluatorActor::new(id, cwd, is_japanese_mode);

    // 4. Request an ad-hoc action from the user via the AppleScript Bridge
    let payload = serde_json::to_string(&HiveMessage::Objective("Analyze the current Safari context & find matching intent.".into())).unwrap();

    println!("Passing control to SafariEvaluator...");
    let _ = actor.receive(Envelope {
        message_id: Uuid::new_v4(),
        sender: Uuid::nil().to_string(),
        recipient: id.to_string(),
        payload,
    }).await;
    
    println!("Safari Evaluator test suite finished.");
}
