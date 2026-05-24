use ignore::WalkBuilder;
use ronin_core::models::provider::ollama::OllamaProvider;
use ronin_core::models::provider::LlmProvider;
use ronin_core::models::sampling_params::{InferenceRequest, PromptFormat, SamplingParams};
use ronin_core::memory_bridge::spatial_index::{SpatialIndex, MemoryNode};
use std::path::{Path, PathBuf};
use tracing::{info, warn, error};
use std::time::Duration;

pub struct TimeMachineIndexer {
    root_dir: PathBuf,
}

impl TimeMachineIndexer {
    pub fn new<P: AsRef<Path>>(root_dir: P) -> Self {
        Self {
            root_dir: root_dir.as_ref().to_path_buf(),
        }
    }

    pub async fn run_scan(&self, spatial_index: &mut SpatialIndex) {
        let mut target_files = Vec::new();
        
        let extensions = vec![
            "rs", "ts", "js", "py", "md", "txt", "swift", "java", "c", "cpp", "h", "hpp", "go"
        ];

        info!("[TimeMachine] Initiating Full PC Symbolic Scan starting from: {}", self.root_dir.display());

        let walker = WalkBuilder::new(&self.root_dir)
            .hidden(true)
            .git_ignore(true)
            .build();

        for result in walker {
            match result {
                Ok(entry) => {
                    let path = entry.path();
                    if path.is_file() {
                        if let Some(ext) = path.extension().and_then(|e| e.to_str()) {
                            if extensions.contains(&ext) {
                                target_files.push(path.to_path_buf());
                            }
                        }
                    }
                }
                Err(err) => warn!("[TimeMachine] Error traversing: {}", err),
            }
        }

        info!("[TimeMachine] Discovered {} symbolic-worthy files. Beginning deep compression...", target_files.len());

        let local_slm = OllamaProvider::new("127.0.0.1", 11434);

        for (idx, path) in target_files.iter().enumerate() {
            info!("[TimeMachine] [{}/{}] Compressing: {}", idx + 1, target_files.len(), path.display());
            
            let content = match std::fs::read_to_string(path) {
                Ok(c) => c,
                Err(_) => {
                    warn!("[TimeMachine] Skipping unreadable file: {}", path.display());
                    continue;
                }
            };
            
            // Limit massive files to top 1500 lines to prevent Qwen explosion
            let truncated_content = content.lines().take(1500).collect::<Vec<_>>().join("\n");
            
            let env_hash = path.to_string_lossy().to_string();
            let node_id = format!("tm_{}", uuid::Uuid::new_v4().to_string().replace("-", "")[..12].to_string());

            let file_tree = target_files.iter().map(|p| p.to_string_lossy().to_string()).collect::<Vec<_>>().join("\n");
            let truncated_tree = if file_tree.len() > 3000 { file_tree[..3000].to_string() + "\n...(truncated)" } else { file_tree };

            let prompt = format!(
                "You are an expert system. Compress the following file into the strict JSON object format requested.\n\n[Project File Tree Context (For Import Resolution)]\n{}\n\n[Target File Path]: {}\n\n[Code]:\n{}",
                truncated_tree, env_hash, truncated_content
            );

            let req = InferenceRequest {
                model: "qwen2.5:1.5b".to_string(), // In production, replace with Gemma 4:31b or DeepSeek
                sampling: SamplingParams::for_midweight(),
                format: PromptFormat::OllamaChat,
                stream: false,
            };

            let is_ja = std::env::var("LANG").unwrap_or_default().starts_with("ja");
            let sys_prompt = if is_ja {
                    r#"
以下のコードやドキュメントを読み、ロスレス意味圧縮（Lossless Semantic Compression）を施したJCrossフォーマット（JSON形式）で出力してください。
必ず以下の属性を持つJSONのみを1つ出力し、マークダウンブロック(```json)は含めないでください。

{
    "kanji_tags": ["[視:0.9]", "[認:0.8]", "[庫:1.0]"], // このファイルの役割を象徴する漢字1文字のタグとその重み（最大3つ）
    "logic_summary": "〜〜を行うシステム", // このコードの中心的な意図やアーキテクチャの役割（50文字以内）
    "abstract_level": 0.5 // 具体的な実装(0.0)か、抽象的な基盤(1.0)か
}
"#.to_string()
                } else {
                    r#"
Read the following code, and output a JSON object representing the Lossless Semantic Compression (JCross intermediate representation).
Output ONLY the JSON object, do not include markdown blocks like ```json.

{
    "kanji_tags": ["[UI:0.9]", "[Auth:0.8]", "[DB:1.0]"], // Up to 3 Kanji/Symbol tags representing logic core
    "logic_summary": "System that performs X...", // Keep under 50 chars identifying core architecture
    "abstract_level": 0.5 // 0.0 for raw implementation, 1.0 for highly abstract base trait/protocol
}
"#.to_string()
                };

            let history = vec![
                ronin_core::models::provider::LlmMessage::system(&sys_prompt),
                ronin_core::models::provider::LlmMessage::user(&prompt),
            ];

            match local_slm.invoke(&req, &history).await {
                Ok(reply) => {
                    let raw_json = reply.trim();
                    let raw_json = raw_json.trim_start_matches("```json").trim_start_matches("```").trim_end_matches("```").trim();
                    
                    match serde_json::from_str::<serde_json::Value>(raw_json) {
                        Ok(json_val) => {
                            let safe_content_snippet: String = truncated_content.chars().take(100).collect();
                            let mut node = MemoryNode::new_v4(&node_id, &safe_content_snippet);
                            
                            if let Some(summary) = json_val.get("logic_summary").and_then(|v| v.as_str()) {
                                node.concept = summary.to_string();
                            }
                            if let Some(lvl) = json_val.get("abstract_level").and_then(|v| v.as_f64()) {
                                node.abstract_level = lvl;
                            }
                            if let Some(tags) = json_val.get("kanji_tags").and_then(|v| v.as_array()) {
                                for t in tags {
                                    if let Some(tag_str) = t.as_str() {
                                        node.kanji_tags.extend(ronin_core::memory_bridge::kanji_ontology::KanjiTag::resolve(tag_str));
                                    }
                                }
                            }
                            node.env_hash = Some(env_hash.clone());
                            
                            if let Err(e) = spatial_index.write_node(node.clone()).await {
                                warn!("[TimeMachine] Failed to write node {}: {}", node_id, e);
                            }
                        },
                        Err(e) => {
                            warn!("[TimeMachine] Failed to strictly parse SLM JSON: {}", e);
                        }
                    }
                },
                Err(e) => {
                    error!("[TimeMachine] SLM Engine failed: {}", e);
                }
            }
            
            // Minimal breathing time to let CPU cool off and allow REPL responsiveness
            tokio::time::sleep(Duration::from_millis(500)).await;
        }

        info!("[TimeMachine] Scan complete. Spatial Engine is ready.");
    }
}
