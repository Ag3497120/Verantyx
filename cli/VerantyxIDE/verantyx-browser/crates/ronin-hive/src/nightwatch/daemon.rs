use crate::config::VerantyxConfig;
use crate::nightwatch::observer::NightwatchQueue;
use ronin_core::memory_bridge::spatial_index::{MemoryNode, SpatialIndex};
use ronin_core::models::provider::LlmProvider;
use std::path::{Path, PathBuf};
use tracing::{info, warn, error};

pub struct NightwatchDaemon {
    config: VerantyxConfig,
    root_dir: PathBuf,
}

impl NightwatchDaemon {
    pub fn new(config: VerantyxConfig, root_dir: PathBuf) -> Self {
        Self { config, root_dir }
    }

    pub async fn run_knowledge_distillation(&self) {
        if !self.config.nightwatch.enabled {
            return;
        }

        let mut queue = NightwatchQueue::load_or_create(&self.root_dir);
        if queue.pending_files.is_empty() {
            info!("[Nightwatch] No new structural edits detected. Returning to sleep.");
            return;
        }

        info!(
            "[Nightwatch] Awakened. Initiating Semantic Compression with SLM: {} on {} modified files.",
            self.config.nightwatch.model,
            queue.pending_files.len()
        );

        let mut spatial_index = SpatialIndex::new(self.root_dir.clone());
        let client = ronin_core::models::provider::ollama::OllamaProvider::new("127.0.0.1", 11434);

        let mut processed_files = Vec::new();

        for file_path in &queue.pending_files {
            let path = Path::new(file_path);
            if !path.exists() {
                processed_files.push(file_path.clone());
                continue;
            }

            let file_content = match tokio::fs::read_to_string(path).await {
                Ok(c) => c,
                Err(_) => {
                    processed_files.push(file_path.clone());
                    continue; // Skip binaries or unreadable
                }
            };

            let node_id = path.file_stem().unwrap_or_default().to_string_lossy().to_string();
            
            // Build Lossless Semantic Compression Prompt
            let prompt = format!(
                r#"You are a Neuro-Symbolic extraction engine. 
Analyze following code modification and extract an intermediate representation (IR) that captures the core semantic essence and logical structure of this file. Do NOT just summarize. 
Identify the precise behavior, the main logical blocks, and output ONLY valid JSON matching this schema:
{{
  "kanji_tags": ["[認:0.9]", "[鍵:0.8]"], // 1-3 Kanji tags with weights
  "concept": "Core abstract concept of the file logic",
  "abstract_level": 0.7, // 0.0 (concrete/hardcoded) to 1.0 (highly abstract interface)
  "relations": ["other_file:派生:0.9"], // E.g., target_node_id:relation_name:weight
  "content": "A high-density semantic representation of the file logic."
}}

File path: {}

Code:
```
{}
```"#,
                file_path,
                // Truncate if insanely large to fit in local SLM 8k-32k window
                if file_content.len() > 16000 {
                    let mut b = 16000;
                    while !file_content.is_char_boundary(b) && b > 0 {
                        b -= 1;
                    }
                    &file_content[..b]
                } else {
                    &file_content
                }
            );

            let request = ronin_core::models::sampling_params::InferenceRequest {
                model: self.config.nightwatch.model.clone(),
                format: ronin_core::models::sampling_params::PromptFormat::OllamaChat,
                stream: false,
                sampling: ronin_core::models::sampling_params::SamplingParams::for_heavyweight().with_temperature(0.1),
            };

            let messages = vec![
                ronin_core::models::provider::LlmMessage {
                    role: "system".to_string(),
                    content: prompt,
                }
            ];

            // Using pure generation mode for the SLM 
            match ronin_core::models::provider::LlmProvider::invoke(&client, &request, &messages).await {
                Ok(raw_json) => {
                    // Extract JSON block
                    let json_text = if raw_json.contains("```json") {
                        raw_json.split("```json").nth(1).unwrap_or("").split("```").next().unwrap_or("").trim()
                    } else if raw_json.contains("```") {
                        raw_json.split("```").nth(1).unwrap_or("").trim()
                    } else {
                        raw_json.trim()
                    };

                    match serde_json::from_str::<serde_json::Value>(json_text) {
                        Ok(json) => {
                            let mut node = MemoryNode::new_v4(&node_id, json["content"].as_str().unwrap_or(""));
                            node.concept = json["concept"].as_str().unwrap_or("Derived Concept").to_string();
                            node.abstract_level = json["abstract_level"].as_f64().unwrap_or(0.5);
                            node.env_hash = Some(path.to_string_lossy().to_string());
                            
                            // Map Kanji Tags
                            if let Some(tags) = json["kanji_tags"].as_array() {
                                for tag in tags {
                                    if let Some(t_str) = tag.as_str() {
                                        let resolved_tags = ronin_core::memory_bridge::kanji_ontology::KanjiTag::resolve(t_str);
                                        node.kanji_tags.extend(resolved_tags);
                                    }
                                }
                            }

                            // Write to JCross
                            if let Err(e) = spatial_index.write_node(node.clone()).await {
                                warn!("[Nightwatch] Failed to write node {}: {}", node_id, e);
                            } else {
                                info!("[Nightwatch] Synthesized JCross Node: {}", node_id);
                                
                                // --- Symbolic Engine Growth Loop ---
                                // Create the meta-learning node that records *how* this was analyzed
                                let meta_id = format!("meta_learning_{}", node_id);
                                let meta_content = format!(
                                    "Symbolic Extraction Log\nTarget: {}\nReasoning Delta: {}",
                                    node_id, raw_json
                                );
                                let mut meta_node = MemoryNode::new_v4(&meta_id, &meta_content);
                                meta_node.concept = "Symbolic Engine Growth Observation".to_string();
                                meta_node.abstract_level = 0.9; // Meta-learning is highly abstract
                                
                                // Tag it with [創] (Creation/Evolution)
                                meta_node.kanji_tags.extend(ronin_core::memory_bridge::kanji_ontology::KanjiTag::resolve("[創:0.9]"));
                                
                                // Link to original node
                                meta_node.relations.push(ronin_core::memory_bridge::kanji_ontology::TypedRelation {
                                    target_id: node_id.clone(),
                                    rel_type: ronin_core::memory_bridge::kanji_ontology::RelationType::Derived,
                                    strength: 1.0,
                                });

                                if let Err(e) = spatial_index.write_node(meta_node).await {
                                    warn!("[Nightwatch] Failed to write meta-learning node: {}", e);
                                } else {
                                    info!("[Nightwatch] Synthesized Symbolic Growth Context: {}", meta_id);
                                }

                                // --- CROSS-POLLINATION ADVICE ENGINE ---
                                let all_keys = spatial_index.list_all_keys();
                                for other_key in all_keys {
                                    if other_key != node_id && !other_key.starts_with("meta_") && !other_key.starts_with("recommend_") {
                                        if let Some(other_node) = spatial_index.read_node(&other_key) {
                                            let mut match_score = 0.0;
                                            for t1 in &node.kanji_tags {
                                                for t2 in &other_node.kanji_tags {
                                                    if t1.name == t2.name { match_score += t1.weight * t2.weight; }
                                                }
                                            }
                                            // Threshold for spontaneous recommendation
                                            if match_score > 1.2 {
                                                let rec_id = format!("recommend_{}_{}", node_id, other_key);
                                                let rec_concept = "Architectural Cross-Pollination / Design Reuse".to_string();
                                                let rec_content = format!("CROSS-POLLINATION ADVICE: The structures of '{}' and '{}' are highly isomorphic (Semantic Overlap: {:.2}). Consider using 'crucible' to fuse them, or repurpose their architectural IR.", node_id, other_key, match_score);
                                                
                                                let mut rec_node = MemoryNode::new_v4(&rec_id, &rec_content);
                                                rec_node.concept = rec_concept;
                                                rec_node.abstract_level = 1.0;
                                                // [薦] corresponds to Recommend/Advice
                                                rec_node.kanji_tags.extend(ronin_core::memory_bridge::kanji_ontology::KanjiTag::resolve("[薦:1.0]"));
                                                rec_node.relations.push(ronin_core::memory_bridge::kanji_ontology::TypedRelation {
                                                    target_id: node_id.clone(),
                                                    rel_type: ronin_core::memory_bridge::kanji_ontology::RelationType::Similar,
                                                    strength: match_score,
                                                });
                                                rec_node.relations.push(ronin_core::memory_bridge::kanji_ontology::TypedRelation {
                                                    target_id: other_key.clone(),
                                                    rel_type: ronin_core::memory_bridge::kanji_ontology::RelationType::Similar,
                                                    strength: match_score,
                                                });
                                                if let Ok(_) = spatial_index.write_node(rec_node).await {
                                                    info!("[Nightwatch] Spontaneous Cross-Pollination discovered between {} and {} (Score: {:.2})", node_id, other_key, match_score);
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        },
                        Err(e) => {
                            error!("[Nightwatch] Failed to strictly parse SLM JSON: {}", e);
                            // We still mark it processed so we don't get stuck in a loop over failing files
                        }
                    }
                },
                Err(e) => {
                    error!("[Nightwatch] SLM Engine failed: {}", e);
                    break; // Probably SLM is down, stop processing
                }
            }
            
            processed_files.push(file_path.clone());
        }

        // Remove processed
        for f in processed_files {
            queue.pending_files.remove(&f);
        }
        queue.save(&self.root_dir);

        // Render the Neural UI update
        super::visualizer::VeraMemoryVisualizer::generate_html(&spatial_index, &self.root_dir);

        info!("[Nightwatch] Protocol operation complete. VeraMemory updated. Returning to inactive observation.");
    }
}
