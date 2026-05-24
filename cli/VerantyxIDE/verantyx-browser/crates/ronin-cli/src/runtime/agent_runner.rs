//! Agent runner — the central integration bridge that ties all Ronin crates together.
//!
//! This is where `ronin-core`, `ronin-sandbox`, `ronin-diff-ux`, and `ronin-synapse`
//! converge into a single, coherent execution pipeline. The AgentRunner manages
//! the full lifecycle of a task: model selection → prompt construction → ReAct loop
//! → tool dispatch → HITL approval → observation → loop.

use anyhow::Result;
use console::style;
use indicatif::{ProgressBar, ProgressStyle};
use ronin_core::{
    domain::config::RoninConfig,
    engine::{
        prompt_builder::{PromptBuilder, ToolSchema},
        reactor::RoninReactor,
        tool_dispatcher::{ToolDispatcher, ToolResult},
    },
    memory_bridge::{
        context_injector::{ContextInjector, InjectorConfig},
        spatial_index::SpatialIndex,
    },
    models::{
        context_budget::ContextBudget,
        sampling_params::{InferenceRequest, SamplingParams},
        provider::{
            ollama::OllamaProvider, anthropic::AnthropicProvider,
            gemini::GeminiProvider, LlmProvider, LlmMessage,
        },
        tier_calibration::TierProfile,
    },
};
use ronin_sandbox::{
    isolation::policy::SandboxPolicy,
    process::session::SandboxSession,
};
use ronin_hive::actor::Actor;
use std::path::PathBuf;
use std::sync::Arc;
use tokio::sync::Mutex;
use tracing::{debug, info, warn};

// ─────────────────────────────────────────────────────────────────────────────
// Runner Configuration
// ─────────────────────────────────────────────────────────────────────────────

pub struct RunnerConfig {
    pub task: String,
    pub model_override: Option<String>,
    pub hitl_override: Option<bool>,
    pub force_stealth: bool,
    pub api_mode: bool,
    pub cwd: PathBuf,
    pub max_steps: Option<u32>,
}

// ─────────────────────────────────────────────────────────────────────────────
// Run Result
// ─────────────────────────────────────────────────────────────────────────────

pub struct RunResult {
    pub task: String,
    pub final_response: String,
    pub steps_taken: u32,
    pub commands_executed: usize,
    pub files_modified: Vec<PathBuf>,
    pub success: bool,
}

// ─────────────────────────────────────────────────────────────────────────────
// Agent Runner
// ─────────────────────────────────────────────────────────────────────────────

enum ActiveAgent {
    Hybrid(ronin_hive::roles::hybrid_api::HybridApiActor),
    Stealth(ronin_hive::roles::stealth_gemini::StealthWebActor),
}

impl ActiveAgent {
    async fn receive(&mut self, env: ronin_hive::actor::Envelope) -> anyhow::Result<Option<ronin_hive::actor::Envelope>> {
        use ronin_hive::actor::Actor;
        match self {
            Self::Hybrid(a) => a.receive(env).await,
            Self::Stealth(a) => a.receive(env).await,
        }
    }

    fn current_turns(&self) -> u8 {
        match self {
            Self::Hybrid(a) => a.current_turns,
            Self::Stealth(a) => a.current_turns,
        }
    }

    fn turn_limit(&self) -> u8 {
        match self {
            Self::Hybrid(a) => a.turn_limit,
            Self::Stealth(a) => a.turn_limit,
        }
    }
    
    fn set_role_senior(&mut self) {
        match self {
            Self::Hybrid(a) => a.role = ronin_hive::roles::stealth_gemini::SystemRole::SeniorObserver,
            Self::Stealth(a) => a.role = ronin_hive::roles::stealth_gemini::SystemRole::SeniorObserver,
        }
    }
}

pub struct AgentRunner {
    config: RoninConfig,
}

impl AgentRunner {
    pub fn new(config: RoninConfig) -> Self {
        Self { config }
    }

    pub async fn run(&self, mut runner_cfg: RunnerConfig) -> Result<RunResult> {
        let model = runner_cfg.model_override
            .as_deref()
            .unwrap_or(&self.config.agent.primary_model)
            .to_string();

        let hitl = runner_cfg.hitl_override
            .unwrap_or(self.config.agent.hitl_enabled);

        let max_steps = runner_cfg.max_steps
            .unwrap_or(self.config.agent.max_steps);

        let display_task: String = runner_cfg.task.chars().take(80).collect();
        info!("[Runner] Task: {}", display_task);
        info!("[Runner] Model: {} | HITL: {} | MaxSteps: {}", model, hitl, max_steps);

        // 1. Derive tier profile from model name
        let profile = TierProfile::extrapolate_from_model(&model);
        let budget = match profile.max_context_tokens {
            n if n <= 8192  => ContextBudget::for_8b(),
            n if n <= 32768 => ContextBudget::for_27b(),
            _               => ContextBudget::for_70b_plus(),
        };

        // 2. Setup autonomous Git workspace overlay
        if let Ok(git) = ronin_git::GitEngine::new(&runner_cfg.cwd) {
            let task_id = uuid::Uuid::new_v4().as_simple().to_string()[..8].to_string();
            let branch_name = format!("ronin/task-{}", task_id);
            let _ = git.checkout_branch(&branch_name);
            info!("[Runner] Switched to autonomous branch: {}", branch_name);
        }

        // 3. Hydrate JCross memory
        let mut spatial_index = SpatialIndex::new(self.config.memory.root_dir.clone());
        let hydrated = spatial_index.hydrate().await.unwrap_or(0);
        info!("[Runner] Memory: hydrated {} nodes", hydrated);

        let injector_cfg = InjectorConfig::from_budget(&budget);
        let injector = ContextInjector::new(&spatial_index, injector_cfg);
        let memory_block = injector.build_injection_block();

        // Capture Start Time to exclude pre-existing unstaged git changes from audit
        let run_start_time = std::time::SystemTime::now();

        // 4. Pre-Flight Intent Router (Local SLM Analysis)
        let provider = self.build_provider(&model);
        println!("\n{} Analyzing Objective Intent...", style("🧠").magenta().bold());

        let lang_desc = match self.config.agent.system_language {
            ronin_core::domain::config::SystemLanguage::Japanese => "プロンプト言語は必ず「日本語」で出力してください。",
            ronin_core::domain::config::SystemLanguage::English => "Ensure the generated prompts are written strictly in English.",
        };

        let meta_prompt = format!("
You are the Ronin Intent Router. 
User Prompt: {}
Decompose the context and purpose. If the prompt asks to 'analyze', 'look into', 'investigate' or implies scanning the project, generate a dedicated system prompt for the Local SLM to analyze the file hierarchy (PureThrough mode), AND a contextual framework for the Observer AI (Gemini) that will run afterwards. NOTE: Gemini is ONLY an observer, it DOES NOT run commands. DO NOT generate git, shell, or execution commands for Gemini!
{}
Output ONLY valid JSON matching this schema:
{{
    \"needs_mapping\": true,
    \"target_directory\": \"/path/to/extracted/absolute/directory/if/present/in/prompt (optional)\",
    \"local_analysis_prompt\": \"Prompt telling local SLM how to summarize the repository tree\",
    \"gemini_directive_prompt\": \"Context instructions for Gemini to observe the objective. Do NOT include shell commands.\"
}}
If no mapping is needed, set needs_mapping to false.
", runner_cfg.task, lang_desc);

        let req = InferenceRequest {
            model: model.clone(),
            format: ronin_core::models::sampling_params::PromptFormat::OllamaChat,
            stream: false,
            sampling: SamplingParams::for_midweight().with_max_tokens(1500).with_temperature(0.2),
        };
        let history = vec![
            LlmMessage { role: "system".to_string(), content: "You return only JSON.".to_string() },
            LlmMessage { role: "user".to_string(), content: meta_prompt }
        ];
        
        let mut final_objective = runner_cfg.task.clone();

        if let Ok(json_res) = provider.invoke(&req, &history).await {
            // Primitive JS-style JSON stripping
            let clean_json = json_res.replace("```json", "").replace("```", "");
            #[derive(serde::Deserialize)]
            struct IntentRoute {
                needs_mapping: bool,
                target_directory: Option<String>,
                local_analysis_prompt: Option<String>,
                gemini_directive_prompt: Option<String>,
            }

            if let Ok(route) = serde_json::from_str::<IntentRoute>(&clean_json) {
                // Dynamically intercept path shifts if the prompt asked to analyze a specific absolute path
                if let Some(mut target_dir) = route.target_directory {
                    target_dir = target_dir.trim().to_string();
                    let p = std::path::Path::new(&target_dir);
                    if p.is_absolute() && p.exists() {
                        runner_cfg.cwd = p.to_path_buf();
                        println!("{} Redirecting context to: {}", console::style("[SYSTEM]").dim(), target_dir);
                    }
                }
                if route.needs_mapping {
                    println!("{} Intent [MAP_AND_EXECUTE] Detected.", style("[SYSTEM]").dim());
                    
                    let mut repo_map = "No Map".to_string();
                    if let Ok(generator) = ronin_repomap::RepoMapGenerator::new(&runner_cfg.cwd).generate() {
                        repo_map = generator.render();
                    }
                    
                    let analysis_prompt = route.local_analysis_prompt.unwrap_or_else(|| "Summarize this repo.".to_string());
                    println!("{} Executing PureThrough Analysis...", style("[SLM]").cyan());
                    
                    let pt_req = InferenceRequest {
                        model: model.clone(),
                        format: ronin_core::models::sampling_params::PromptFormat::OllamaChat,
                        stream: false,
                        sampling: SamplingParams::for_midweight().with_max_tokens(2000).with_temperature(0.2),
                    };
                    let pt_hist = vec![
                        LlmMessage { role: "system".to_string(), content: "You are the PureThrough spatial analyzer. Output a Markdown explanation of the repository structure.".to_string() },
                        LlmMessage { role: "user".to_string(), content: format!("{}\n\nTree:\n{}", analysis_prompt, repo_map) }
                    ];
                    
                    if let Ok(pt_res) = provider.invoke(&pt_req, &pt_hist).await {
                        let memory_dir = runner_cfg.cwd.join(".ronin/memory/front");
                        let _ = tokio::fs::create_dir_all(&memory_dir).await;
                        let out_file = memory_dir.join("purethrough_map.md");
                        let pt_content = format!("# PureThrough Spatial Map\n\n{}\n\n## Auto-Generated AST Map\n```\n{}\n```", pt_res, repo_map);
                        let _ = tokio::fs::write(&out_file, pt_content).await;
                        println!("{} Spatial Map anchored into Memory.", style("[SYSTEM]").green().bold());

                        let pt_distilled = format!("# ローカルLLMのリポジトリ分析結果\n\n{}", pt_res);
                        // Automatically inject the distilled map into Gemini's objective
                        final_objective = format!("{}\n\n[SYSTEM REPOSITORY MAP]\n```\n{}\n```", route.gemini_directive_prompt.unwrap_or(final_objective), pt_distilled);
                    } else {
                        final_objective = route.gemini_directive_prompt.unwrap_or(final_objective);
                    }
                } else {
                    println!("{} Intent [EXECUTE_DIRECTLY] Detected.", style("[SYSTEM]").dim());
                    final_objective = route.gemini_directive_prompt.unwrap_or(final_objective);
                }
            } else {
                warn!("[Router] Failed to parse SLM JSON: {}", clean_json);
            }
        } else {
            warn!("[Router] LLM execution failed.");
        }

        // 5. Initialize Multi-Agent Hive Network
        info!("[Runner] Booting Ronin Multi-Agent Hive System...");
        
        let hive_config = ronin_hive::config::VerantyxConfig::load(&runner_cfg.cwd);
        if hive_config.automation_mode == ronin_hive::config::AutomationMode::AutoStealth 
            || hive_config.automation_mode == ronin_hive::config::AutomationMode::AutoPremium 
            || runner_cfg.force_stealth
            || std::env::var("RONIN_VIZ_BROWSER").is_ok()
        {
            println!("{} Orchestrating Dual-Browser Spawning for Gemini Agents...", style("[SYSTEM]").cyan().bold());
            let split_screen_js = r#"
            do shell script "open -a Safari"
            delay 1.5
            
            tell application "Finder"
                set bnd to bounds of window of desktop
                set screenWidth to item 3 of bnd
                set screenHeight to item 4 of bnd
            end tell
            
            set winHeight to (screenHeight * 0.85) as integer
            set topMargin to 50
            set winWidth to (screenWidth * 0.65) as integer
            
            tell application "Safari"
                activate
                delay 0.5
                
                make new document with properties {URL:"https://gemini.google.com/app"}
                set _w1 to front window
                set bounds of _w1 to {10, topMargin, 10 + winWidth, topMargin + winHeight}
                
                make new document with properties {URL:"https://gemini.google.com/app"}
                set _w2 to front window
                set bounds of _w2 to {100, topMargin, 100 + winWidth, topMargin + winHeight}
                
                make new document with properties {URL:"https://gemini.google.com/app"}
                set _w3 to front window
                set bounds of _w3 to {200, topMargin, 200 + winWidth, topMargin + winHeight}
            end tell
            "#;
            let _ = tokio::process::Command::new("osascript")
                .arg("-e")
                .arg(split_screen_js)
                .output()
                .await;
            
            // Give Safari a moment to render the newly created windows
            tokio::time::sleep(tokio::time::Duration::from_millis(2000)).await;
        }

        let spinner = Self::make_spinner("[SYSTEM] Synchronizing Autonomous Hive Network...");
        
        let mut commander_actor = ronin_hive::roles::commander::CommanderActor;
        let mut planner_actor = ronin_hive::roles::planner::PlannerActor::new(&self.config.memory.root_dir);
        let mut coder_actor = ronin_hive::roles::coder::CoderActor::new(&runner_cfg.cwd);
        let mut reviewer_actor = ronin_hive::roles::reviewer::ReviewerActor::new(&runner_cfg.cwd);
        let consensus_actor = ronin_hive::roles::consensus::LocalConsensusActor::new(
            self.config.providers.ollama.host.clone(),
            self.config.providers.ollama.port,
            self.config.agent.primary_model.clone()
        );

        let mut worker_actor = if runner_cfg.api_mode {
            ActiveAgent::Hybrid(ronin_hive::roles::hybrid_api::HybridApiActor::new(
                uuid::Uuid::new_v4(),
                self.config.sandbox.allow_filesystem_escape,
                runner_cfg.cwd.clone(),
                self.config.agent.primary_model.clone(),
                self.config.providers.ollama.host.clone(),
                self.config.providers.ollama.port,
                self.config.agent.system_language == ronin_core::domain::config::SystemLanguage::Japanese,
                ronin_hive::roles::stealth_gemini::SystemRole::ArchitectWorker,
                1,
                self.config.providers.gemini.as_ref().map(|g| g.api_key.clone()).unwrap_or_default(),
            ))
        } else {
            ActiveAgent::Stealth(ronin_hive::roles::stealth_gemini::StealthWebActor::new(
                uuid::Uuid::new_v4(),
                self.config.sandbox.allow_filesystem_escape,
                runner_cfg.cwd.clone(),
                self.config.agent.primary_model.clone(),
                self.config.providers.ollama.host.clone(),
                self.config.providers.ollama.port,
                self.config.agent.system_language == ronin_core::domain::config::SystemLanguage::Japanese,
                ronin_hive::roles::stealth_gemini::SystemRole::ArchitectWorker,
                1,
            ))
        };

        let mut senior_actor = if runner_cfg.api_mode {
            ActiveAgent::Hybrid(ronin_hive::roles::hybrid_api::HybridApiActor::new(
                uuid::Uuid::new_v4(),
                self.config.sandbox.allow_filesystem_escape,
                runner_cfg.cwd.clone(),
                self.config.agent.primary_model.clone(),
                self.config.providers.ollama.host.clone(),
                self.config.providers.ollama.port,
                self.config.agent.system_language == ronin_core::domain::config::SystemLanguage::Japanese,
                ronin_hive::roles::stealth_gemini::SystemRole::SeniorObserver,
                2,
                self.config.providers.gemini.as_ref().map(|g| g.api_key.clone()).unwrap_or_default(),
            ))
        } else {
            ActiveAgent::Stealth(ronin_hive::roles::stealth_gemini::StealthWebActor::new(
                uuid::Uuid::new_v4(),
                self.config.sandbox.allow_filesystem_escape,
                runner_cfg.cwd.clone(),
                self.config.agent.primary_model.clone(),
                self.config.providers.ollama.host.clone(),
                self.config.providers.ollama.port,
                self.config.agent.system_language == ronin_core::domain::config::SystemLanguage::Japanese,
                ronin_hive::roles::stealth_gemini::SystemRole::SeniorObserver,
                2,
            ))
        };

        let mut junior_actor = if runner_cfg.api_mode {
            Some(ActiveAgent::Hybrid(ronin_hive::roles::hybrid_api::HybridApiActor::new(
                uuid::Uuid::new_v4(),
                self.config.sandbox.allow_filesystem_escape,
                runner_cfg.cwd.clone(),
                self.config.agent.primary_model.clone(),
                self.config.providers.ollama.host.clone(),
                self.config.providers.ollama.port,
                self.config.agent.system_language == ronin_core::domain::config::SystemLanguage::Japanese,
                ronin_hive::roles::stealth_gemini::SystemRole::JuniorObserver,
                3,
                self.config.providers.gemini.as_ref().map(|g| g.api_key.clone()).unwrap_or_default(),
            )))
        } else {
            Some(ActiveAgent::Stealth(ronin_hive::roles::stealth_gemini::StealthWebActor::new(
                uuid::Uuid::new_v4(),
                self.config.sandbox.allow_filesystem_escape,
                runner_cfg.cwd.clone(),
                self.config.agent.primary_model.clone(),
                self.config.providers.ollama.host.clone(),
                self.config.providers.ollama.port,
                self.config.agent.system_language == ronin_core::domain::config::SystemLanguage::Japanese,
                ronin_hive::roles::stealth_gemini::SystemRole::JuniorObserver,
                3,
            )))
        };

        if runner_cfg.force_stealth {
            final_objective = format!("[STEALTH_FORCE] {}", final_objective);
        }

        let extract_output = |opt_env: Option<ronin_hive::actor::Envelope>| -> String {
            if let Some(env) = opt_env {
                if let Ok(ronin_hive::messages::HiveMessage::SubAgentResult { output, .. }) = serde_json::from_str(&env.payload) {
                    return output;
                }
            }
            String::new()
        };

        // 5. Run the Triple-Helix Swarm Network
        info!("[Runner] Injecting Objective into Triple-Helix Swarm...");
        let mut final_response = String::new();
        let mut step_count = 0;
        let mut current_objective = final_objective;
        let mut next_tab_index = 3; // Junior will spawn on tab 3

        // Spawning JCross Concept Simulator Canvas
        let current_exe = std::env::current_exe().unwrap_or_else(|_| std::path::PathBuf::from("cargo"));
        
        let mut sim_process = if current_exe.file_name().and_then(|n| n.to_str()) == Some("cargo") {
            std::process::Command::new("cargo")
                .arg("run")
                .arg("-p")
                .arg("vx-browser")
                .arg("--")
                .arg("--simulator")
                .stdin(std::process::Stdio::piped())
                .spawn()
                .ok()
        } else {
            std::process::Command::new(&current_exe)
                .arg("--simulator")
                .stdin(std::process::Stdio::piped())
                .spawn()
                .ok()
        };
            
        let mut sim_stdin = sim_process.as_mut().and_then(|p| p.stdin.take());

        loop {
            step_count += 1;
            
            // Check Sliding Window Expiration
            if worker_actor.current_turns() >= worker_actor.turn_limit() {
                info!("[Runner] Memory limit reached. Handing over Swarm tokens and purging old memory context...");
                
                // Junior promotes to Senior
                if let Some(mut j) = junior_actor.take() {
                    j.set_role_senior();
                    senior_actor = j;
                }
                
                // Spawn new Junior
                junior_actor = if runner_cfg.api_mode {
                    Some(ActiveAgent::Hybrid(ronin_hive::roles::hybrid_api::HybridApiActor::new(
                        uuid::Uuid::new_v4(),
                        self.config.sandbox.allow_filesystem_escape,
                        runner_cfg.cwd.clone(),
                        self.config.agent.primary_model.clone(),
                        self.config.providers.ollama.host.clone(),
                        self.config.providers.ollama.port,
                        self.config.agent.system_language == ronin_core::domain::config::SystemLanguage::Japanese,
                        ronin_hive::roles::stealth_gemini::SystemRole::JuniorObserver,
                        next_tab_index,
                        self.config.providers.gemini.as_ref().map(|g| g.api_key.clone()).unwrap_or_default(),
                    )))
                } else {
                    Some(ActiveAgent::Stealth(ronin_hive::roles::stealth_gemini::StealthWebActor::new(
                        uuid::Uuid::new_v4(),
                        self.config.sandbox.allow_filesystem_escape,
                        runner_cfg.cwd.clone(),
                        self.config.agent.primary_model.clone(),
                        self.config.providers.ollama.host.clone(),
                        self.config.providers.ollama.port,
                        self.config.agent.system_language == ronin_core::domain::config::SystemLanguage::Japanese,
                        ronin_hive::roles::stealth_gemini::SystemRole::JuniorObserver,
                        next_tab_index,
                    )))
                };
                next_tab_index = if next_tab_index == 2 { 3 } else { 2 };
            }

            // Stop spinner permanently before entering concurrent TUI interaction steps
            spinner.finish_and_clear();

            // Run Worker first
            let env_worker = ronin_hive::actor::Envelope {
                message_id: uuid::Uuid::new_v4(),
                sender: "System".to_string(),
                recipient: "ArchitectWorker".to_string(),
                payload: serde_json::to_string(&ronin_hive::messages::HiveMessage::Objective(current_objective.clone()))?,
            };
            
            info!("[Runner] Executing Worker Actor...");
            let res_worker = worker_actor.receive(env_worker).await;
            let out_w = extract_output(res_worker?);

            if out_w.contains("[TASK_COMPLETE]") || out_w.contains("[FINAL_ANSWER]") {
                info!("[Runner] Task Complete Signal Received from Worker.");
                final_response = format!("Final Answer:\n{}", out_w);
                break;
            }

            // Observers analyze the worker's execution path and logs
            let env_senior = ronin_hive::actor::Envelope {
                message_id: uuid::Uuid::new_v4(),
                sender: "System".to_string(),
                recipient: "SeniorGemini".to_string(),
                payload: serde_json::to_string(&ronin_hive::messages::HiveMessage::Objective(out_w.clone()))?,
            };

            let env_junior = ronin_hive::actor::Envelope {
                message_id: uuid::Uuid::new_v4(),
                sender: "System".to_string(),
                recipient: "JuniorGemini".to_string(),
                payload: serde_json::to_string(&ronin_hive::messages::HiveMessage::Objective(out_w.clone()))?,
            };

            // Run observers sequentially to avoid CLI Mutex deadlocks during human-in-the-loop interactions
            info!("[Runner] Executing Senior Observer...");
            let res_senior = senior_actor.receive(env_senior).await;
            let out_s = extract_output(res_senior?);
            
            let out_j = if let Some(ref mut j) = junior_actor {
                info!("[Runner] Executing Junior Observer...");
                let res_j = j.receive(env_junior).await;
                extract_output(res_j?)
            } else {
                String::new()
            };

            // Fan In: Merge Consensus
            if junior_actor.is_some() {
                info!("[Runner] Consolidating Dual-Observer Reports...");
                let merged = consensus_actor.merge_observations(&out_s, &out_j).await;
                
                // Overwrite the timeline file with pure chronological reality
                let timeline_path = runner_cfg.cwd.join(".ronin").join("timeline.md");
                let mut current_timeline = String::new();
                if timeline_path.exists() {
                    current_timeline = tokio::fs::read_to_string(&timeline_path).await.unwrap_or_default();
                }
                current_timeline.push_str(&format!("\n\n-- TURN {} --\n{}", step_count, merged));
                let _ = tokio::fs::write(&timeline_path, current_timeline).await;
                
                // Assign new unified reality as the objective context for next worker turn
                current_objective = format!("Local System Unified Context:\n{}", merged);
            }

            // Sync structural nodes to AGI Visual Simulator Canvas
            if let Some(stdin) = &mut sim_stdin {
                let mut nodes = Vec::new();
                let mut links = Vec::new();
                
                // Construct basic JCross graph anchors
                nodes.push(serde_json::json!({"id": "Worker", "label": "Architect Worker", "axis": "FRONT"}));
                nodes.push(serde_json::json!({"id": "Senior", "label": "Senior Validator", "axis": "NEAR"}));
                nodes.push(serde_json::json!({"id": "Junior", "label": "Junior Apprentice", "axis": "NEAR"}));
                
                // Read .ronin/memory/*.jcross and map them to JSON structural graph
                let cwd = runner_cfg.cwd.clone();
                let intents_path = cwd.join(".ronin/intent.jcross");
                if let Ok(content) = std::fs::read_to_string(&intents_path) {
                    for (i, part) in content.split("@JCross.Intent").enumerate() {
                        if part.trim().is_empty() { continue; }
                        let node_id = format!("intent_{}_{}", step_count, i);
                        let clean = part.chars().take(20).collect::<String>().replace("\n", " ");
                        nodes.push(serde_json::json!({"id": node_id, "label": clean, "axis": "MID"}));
                        links.push(serde_json::json!({"source": "Worker", "target": node_id}));
                    }
                }

                let experience_path = cwd.join(".ronin/experience.jcross");
                if let Ok(content) = std::fs::read_to_string(&experience_path) {
                    for (i, part) in content.split("✅ [成功体験]:").enumerate() {
                        if part.trim().is_empty() { continue; }
                        let node_id = format!("exp_{}_{}", step_count, i);
                        nodes.push(serde_json::json!({"id": node_id, "label": "Success Strategy", "axis": "DEEP"}));
                        links.push(serde_json::json!({"source": "Senior", "target": node_id}));
                    }
                }
                
                let stealth_path = cwd.join(".ronin/stealth.jcross");
                if let Ok(content) = std::fs::read_to_string(&stealth_path) {
                    for (i, part) in content.split("❌").enumerate() {
                        if part.trim().is_empty() { continue; }
                        let node_id = format!("err_{}_{}", step_count, i);
                        nodes.push(serde_json::json!({"id": node_id, "label": "Anti-Pattern", "axis": "FRONT"}));
                        links.push(serde_json::json!({"source": "Junior", "target": node_id}));
                    }
                }
                
                let payload = serde_json::json!({
                    "nodes": nodes,
                    "links": links
                });
                
                let _ = std::io::Write::write_all(stdin, format!("{}\n", payload.to_string()).as_bytes());
                let _ = std::io::Write::flush(stdin);
            }
        }
        
        if final_response.is_empty() {
            final_response = "Execution completed asynchronously with no final callback to User_CLI.".to_string();
        }

        spinner.finish_and_clear();
        let steps = step_count;
        let commands_executed = 0; // Handled by ReviewerActor internally

        let mut files_modified_final = vec![];

        // 6. Output Validation & Diff Approval (HITL)
        let inspector = ronin_diff_ux::git::inspector::GitInspector::detect(&runner_cfg.cwd);
        if inspector.is_git_repo() {
            let modified = inspector.modified_files();
            if !modified.is_empty() {
                println!("\n{} Post-Run Audit: Reviewing Diffs...", console::style("⚡").cyan().bold());
                let engine = ronin_diff_ux::diff::engine::DiffEngine::new(ronin_diff_ux::diff::engine::DiffGranularity::Line);
                let mut prompt = ronin_diff_ux::tui::approval_prompt::ApprovalSession::new();

                for path in modified {
                    // Check if file was actually modified DURING this run
                    if let Ok(meta) = std::fs::metadata(&path) {
                        if let Ok(mod_time) = meta.modified() {
                            if mod_time < run_start_time {
                                continue;
                            }
                        }
                    }

                    let relative = path.strip_prefix(&runner_cfg.cwd).unwrap_or(&path);
                    if let Ok(out) = std::process::Command::new("git")
                        .args(["show", &format!("HEAD:{}", relative.display())])
                        .current_dir(&runner_cfg.cwd)
                        .output() 
                    {
                        let old_text = String::from_utf8_lossy(&out.stdout).to_string();
                        let new_text = std::fs::read_to_string(&path).unwrap_or_default();
                        
                        let diff_result = engine.compute(&path.to_string_lossy(), &old_text, &new_text);
                        if diff_result.has_changes() {
                            let decision = prompt.prompt(&diff_result);
                            
                            if decision == ronin_diff_ux::tui::approval_prompt::ApprovalDecision::Reject 
                               || decision == ronin_diff_ux::tui::approval_prompt::ApprovalDecision::RejectAll {
                                // Revert specific file!
                                let _ = std::process::Command::new("git")
                                    .args(["checkout", "HEAD", "--", &relative.to_string_lossy()])
                                    .current_dir(&runner_cfg.cwd)
                                    .output();
                                println!("{} Reverted {}", console::style("🚫").red(), relative.display());
                            } else {
                                files_modified_final.push(std::path::PathBuf::from(relative));
                            }
                        }
                    }
                }
            }
        }

        if !files_modified_final.is_empty() {
            if let Ok(git) = ronin_git::GitEngine::new(&runner_cfg.cwd) {
                let _ = git.commit_all("Ronin: Auto Patch Apply", "Ronin Agent", "ronin@verantyx.com");
            }
        }

        Ok(RunResult {
            task: runner_cfg.task,
            final_response,
            steps_taken: steps,
            commands_executed: 0,
            files_modified: files_modified_final,
            success: true,
        })
    }

    fn build_provider(&self, model: &str) -> Box<dyn LlmProvider> {
        // Cloud fallback routing
        if model.starts_with("claude") {
            if let Some(cred) = &self.config.providers.anthropic {
                return Box::new(AnthropicProvider::new(&cred.api_key));
            }
        }
        if model.starts_with("gemini") {
            if let Some(cred) = &self.config.providers.gemini {
                return Box::new(GeminiProvider::new(&cred.api_key));
            }
        }
        // Default: local Ollama
        Box::new(OllamaProvider::new(
            &self.config.providers.ollama.host,
            self.config.providers.ollama.port,
        ))
    }

    fn default_tool_schemas() -> Vec<ToolSchema> {
        vec![
            ToolSchema {
                name: "shell_exec".to_string(),
                description: "Run a bash command in the sandboxed working directory".to_string(),
                parameters: vec![
                    ronin_core::engine::prompt_builder::ToolParameter {
                        name: "command".to_string(),
                        required: true,
                        description: "The bash command to execute".to_string(),
                    },
                ],
            },
            ToolSchema {
                name: "read_file".to_string(),
                description: "Read the contents of a file".to_string(),
                parameters: vec![
                    ronin_core::engine::prompt_builder::ToolParameter {
                        name: "path".to_string(),
                        required: true,
                        description: "Relative or absolute path to the file".to_string(),
                    },
                ],
            },
            ToolSchema {
                name: "write_file".to_string(),
                description: "Write or overwrite a file with new contents (triggers HITL approval)".to_string(),
                parameters: vec![
                    ronin_core::engine::prompt_builder::ToolParameter {
                        name: "path".to_string(),
                        required: true,
                        description: "Path to write to".to_string(),
                    },
                    ronin_core::engine::prompt_builder::ToolParameter {
                        name: "content".to_string(),
                        required: true,
                        description: "Full file content to write".to_string(),
                    },
                ],
            },
            ToolSchema {
                name: "replace_block".to_string(),
                description: "SAFELY edit an existing file using Aider Search/Replace Block protocol. You must match the 'search' block precisely. ALWAYS prefer this over shell_exec + sed.".to_string(),
                parameters: vec![
                    ronin_core::engine::prompt_builder::ToolParameter {
                        name: "path".to_string(),
                        required: true,
                        description: "Relative path to target file".to_string(),
                    },
                    ronin_core::engine::prompt_builder::ToolParameter {
                        name: "search".to_string(),
                        required: true,
                        description: "EXACT code chunk to be replaced (include leading indents)".to_string(),
                    },
                    ronin_core::engine::prompt_builder::ToolParameter {
                        name: "replace".to_string(),
                        required: true,
                        description: "New code chunk to insert".to_string(),
                    },
                ],
            },
            ToolSchema {
                name: "finish".to_string(),
                description: "Signal that the task is complete. Include a summary of what was done.".to_string(),
                parameters: vec![],
            },
            ToolSchema {
                name: "ask_gemini_browser".to_string(),
                description: "Ask Gemini via a private browser when you lack knowledge on a topic. VERY SLOW, use only as last resort.".to_string(),
                parameters: vec![
                    ronin_core::engine::prompt_builder::ToolParameter {
                        name: "question".to_string(),
                        required: true,
                        description: "The specific question or task to ask Gemini".to_string(),
                    },
                ],
            },
        ]
    }

    fn make_spinner(message: &str) -> ProgressBar {
        let pb = ProgressBar::new_spinner();
        pb.set_style(
            ProgressStyle::with_template("{spinner:.cyan.bold} {msg}")
                .unwrap()
                .tick_strings(&["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]),
        );
        pb.set_message(message.to_string());
        pb.enable_steady_tick(std::time::Duration::from_millis(80));
        pb
    }
}
