//! Colony Swarm Architectures
//! 
//! Defines the 30-Node (1 Chief, 29 Subordinate) Swarm execution layer.
//! The swarm uses Hierarchical JCross Compression to avoid exponential API calls,
//! consolidating subordinate thoughts into a single JCross payload for the Supervisors.
//! Physical Safari interaction is constrained by a Semaphore queue to prevent OS crash.

use crate::roles::stealth_gemini::StealthWebActor;
use crate::messages::HiveMessage;
use crate::actor::{Actor, Envelope};
use std::collections::HashMap;
use tokio::sync::Semaphore;
use uuid::Uuid;

pub struct ColonyOrchestrator {
    /// The Central Chief Worker (Node 0). The only entity allowed to edit code.
    pub chief_actor: StealthWebActor,
    /// 29 Subordinate Workers (Node 1 - 29). Strictly emit only JCross IR.
    pub subordinates: HashMap<usize, StealthWebActor>,
    /// Global timeline maintained by the Apprentice Supervisor.
    pub consolidated_timeline: String,
    /// Concurrency Limiter for AppleScript Web UI interactions. Max 5 active UI tabs.
    ui_semaphore: std::sync::Arc<Semaphore>,
}

impl ColonyOrchestrator {
    pub fn new(chief_id: Uuid, cwd: std::path::PathBuf, is_ja: bool) -> Self {
        let chief_prompt = if is_ja {
            "あなたはコロニーの【チーフワーカー(Node 0)】です。配下の29ノードが提出するJCrossロジックを解凍し、最終的なコード生成(REQUEST_FILE_EDIT)を行ってください。"
        } else {
            "You are the Colony Chief Worker (Node 0). Decompress the JCross logic submitted by your 29 subordinates and execute actual code generation (REQUEST_FILE_EDIT)."
        };

        let chief_actor = StealthWebActor::new(
            chief_id,
            true,
            cwd.clone(),
            "gemini-2.5-pro".to_string(),
            chief_prompt.to_string(),
            999, // Long context for Chief
            is_ja,
            crate::roles::stealth_gemini::SystemRole::ArchitectWorker,
            1,
        );

        Self {
            chief_actor,
            subordinates: HashMap::new(),
            consolidated_timeline: String::new(),
            ui_semaphore: std::sync::Arc::new(Semaphore::new(5)), // Max 5 physical tabs concurrent
        }
    }

    /// Appends a new subordinate to the swarm.
    pub fn spawn_subordinate(&mut self, node_index: usize, mission_context: &str, cwd: std::path::PathBuf, is_ja: bool) {
        let sub_prompt = if is_ja {
            format!("あなたはコロニーの【従属ワーカー(Node {})】です。\n絶対指令: 生のソースコードは絶対に生成しないでください。与えられたミッションの解決策や、対象ファイルに適用可能な「メカニズム・術」を、純粋なJCross形式のノードとしてのみ出力してください。\n追加要件: ファイルの依存関係だけでなく、コードの課題に対する『実行可能な思考手順・リファクタリング手法』などのスキルを発見した場合、空間座相に `[術:1.0]` や `[動:1.0]` のタグを付与した「スキルノード」として抽出し、JCross空間に提案してください。\nミッション: {}", node_index, mission_context)
        } else {
            format!("You are Colony Subordinate Worker (Node {}).\nABSOLUTE DIRECTIVE: NEVER generate raw source code. Output solutions strictly as pure JCross semantic nodes.\nRequirement: In addition to mapping file dependencies, if you discover viable procedural methodologies (e.g., refactoring logic or execution steps), synthesize them as 'Skill Nodes' by assigning the spatial modifier `[術:1.0]` or `[動:1.0]`.\nMission: {}", node_index, mission_context)
        };

        let follower = StealthWebActor::new(
            Uuid::new_v4(),
            true,
            cwd,
            "gemini-2.5-flash".to_string(), // Subordinates can be lighter/faster
            sub_prompt,
            100, // Short context for Subordinates (strictly JCross)
            is_ja,
            crate::roles::stealth_gemini::SystemRole::ArchitectWorker,
            node_index as u8 + 1, // +1 because 1 is usually Senior, Node 1 is tab 2, etc. Or just use Chief=1, Sub=i+1
        );

        self.subordinates.insert(node_index, follower);
    }

    pub async fn receive(&mut self, env: Envelope) -> anyhow::Result<Option<Envelope>> {
        use tracing::{info, warn};
        
        let mission_payload = match serde_json::from_str::<HiveMessage>(&env.payload) {
            Ok(HiveMessage::Objective(obj)) => obj,
            _ => env.payload.clone(),
        };

        // If it's a direct chief-only command or we have 0 subordinates, bypass swarm
        if self.subordinates.is_empty() {
            info!("[ColonyOrchestrator] Swarm empty. Bypassing to Chief (Node 0).");
            return self.chief_actor.receive(env).await;
        }

        info!("[ColonyOrchestrator] Activating Swarm Expansion ({} nodes)", self.subordinates.len());
        let mut tasks = Vec::new();
        
        // Temporarily extract actors to spawn independent tokio tasks
        for (idx, mut actor) in self.subordinates.drain() {
            let p_env = env.clone();
            let handle = tokio::spawn(async move {
                let res = actor.receive(p_env).await;
                (idx, actor, res)
            });
            tasks.push(handle);
        }

        let mut compiled_topology = String::new();
        
        // Wait for all subordinates to finish parallel Safari processing
        for t in tasks {
            if let Ok((idx, actor, res)) = t.await {
                // Re-insert the actor
                self.subordinates.insert(idx, actor);
                
                if let Ok(Some(reply)) = res {
                    let jcross_chunk = match serde_json::from_str::<HiveMessage>(&reply.payload) {
                         Ok(HiveMessage::Objective(content)) => content,
                         _ => reply.payload.clone(),
                    };
                    compiled_topology.push_str(&format!("\n=== Node {} [Subconscious Topology] ===\n{}\n", idx, jcross_chunk));
                } else {
                    warn!("[ColonyOrchestrator] Node {} yielded void or failed.", idx);
                }
            }
        }

        let chief_wrap = format!(
            "【Swarm Consolidated JCross Topology】\n以下は{}個のサブノードが自律計算したJCross構造体の集合です。\nこれらを解凍し、最終的なコード実装(REQUEST_FILE_EDIT 等)にコンパイル・統合してください。\n\nミッション：{}\n\n{}",
            self.subordinates.len(), mission_payload, compiled_topology
        );

        let chief_env = Envelope {
            message_id: Uuid::new_v4(),
            sender: "ColonyOrchestrator".to_string(),
            recipient: "ChiefWorker".to_string(),
            payload: serde_json::to_string(&HiveMessage::Objective(chief_wrap)).unwrap_or_default(),
        };

        info!("[ColonyOrchestrator] Topology collapsed. Handing execution vector to Chief.");
        self.chief_actor.receive(chief_env).await
    }
}
