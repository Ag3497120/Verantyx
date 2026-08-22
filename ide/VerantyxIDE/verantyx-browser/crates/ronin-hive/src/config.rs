use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use crate::openclaude_ui::{OpenClaudeTheme, color_text, dim_text, rgb_ansi, ACCENT, CREAM, DIMCOL};

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct PersonaConfig {
    pub name: String,
    pub personality: String,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct SchedulerConfig {
    pub night_watch_hour: i32, // -1 means disabled, 0-23 represents the hour
}

#[derive(Serialize, Deserialize, Debug, Clone, PartialEq, Eq)]
pub enum AutomationMode {
    AutoStealth,    // Free Gemini: full auto keyboard
    AutoPremium,    // Premium Gemini: Web Sandbox loop with image pasting
    Manual,         // Human-in-the-loop manual mode
    HybridApi,      // Qwen Proxy to Gemini Cloud API
}

#[derive(Serialize, Deserialize, Debug, Clone, PartialEq, Eq)]
pub enum CloudProvider {
    Gemini,
    OpenAi,
    Anthropic,
    DeepSeek,
    OpenRouter,
    Groq,
    Together,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct PrivacyConfig {
    pub auto_sync: bool,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct NightwatchConfig {
    pub enabled: bool,
    pub model: String, // e.g., "gemma:27b" or "qwen2.5:32b"
    pub watch_dir: String, // Directory to watch, usually current project
}

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct VerantyxConfig {
    pub language: String,
    pub automation_mode: AutomationMode,
    pub persona: PersonaConfig,
    pub scheduler: SchedulerConfig,
    pub cloud_provider: CloudProvider,
    pub privacy: PrivacyConfig,
    pub nightwatch: NightwatchConfig,
    pub api_key: Option<String>,
    pub colony_swarm_size: usize,
}

impl Default for VerantyxConfig {
    fn default() -> Self {
        Self {
            language: "ja".to_string(),
            automation_mode: AutomationMode::Manual, // Safe fallback
            persona: PersonaConfig {
                name: "Verantyx Alpha".to_string(),
                personality: "冷静沈着でプロフェッショナルなハッカー・アナリスト".to_string(),
            },
            scheduler: SchedulerConfig {
                night_watch_hour: 3,
            },
            cloud_provider: CloudProvider::Gemini,
            privacy: PrivacyConfig {
                auto_sync: false, // Default opt-out
            },
            nightwatch: NightwatchConfig {
                enabled: false,
                model: "gemma2".to_string(),
                watch_dir: ".".to_string(),
            },
            api_key: None,
            colony_swarm_size: 1,
        }
    }
}

impl VerantyxConfig {
    pub fn load(cwd: &PathBuf) -> Self {
        let config_path = cwd.join(".ronin").join("agent_config.json");
        if config_path.exists() {
            if let Ok(data) = std::fs::read_to_string(&config_path) {
                if let Ok(config) = serde_json::from_str(&data) {
                    return config;
                }
            }
        }
        Self::default()
    }

    pub fn save(&self, cwd: &PathBuf) -> anyhow::Result<()> {
        let ronin_dir = cwd.join(".ronin");
        if !ronin_dir.exists() {
            std::fs::create_dir_all(&ronin_dir)?;
        }
        let config_path = ronin_dir.join("agent_config.json");
        let json = serde_json::to_string_pretty(self)?;
        std::fs::write(&config_path, json)?;
        Ok(())
    }

    /// Load the configuration, or run an interactive CLI Wizard if it doesn't exist.
    pub fn load_or_wizard(cwd: &PathBuf) -> Self {
        let config_path = cwd.join(".ronin").join("agent_config.json");
        let existing = if config_path.exists() {
            Self::load(cwd)
        } else {
            Self::default()
        };

        let languages = &["Japanese (日本語)", "English"];
        let default_lang_idx = if existing.language == "en" { 1 } else { 0 };
        let lang_idx = dialoguer::Select::with_theme(&OpenClaudeTheme)
            .with_prompt("Select Language / システム言語とAIプロンプト言語を選択してください")
            .items(languages)
            .default(default_lang_idx)
            .interact()
            .unwrap();
        let lang_str = if lang_idx == 0 { "ja".to_string() } else { "en".to_string() };

        let name: String = dialoguer::Input::with_theme(&OpenClaudeTheme)
            .with_prompt(if lang_idx == 0 { "AIの名前" } else { "AI Name" })
            .default(existing.persona.name)
            .interact_text()
            .unwrap();

        let personality_prompt = if lang_idx == 0 { "AIの人格・性格設定" } else { "AI Personality" };
        let personality: String = dialoguer::Input::with_theme(&OpenClaudeTheme)
            .with_prompt(personality_prompt)
            .default(existing.persona.personality)
            .interact_text()
            .unwrap();

        let nw_title = if lang_idx == 0 { "Night Watch (自律深夜検証・退行テスト)" } else { "Night Watch (Autonomous Regression Test)" };
        let nw_desc = if lang_idx == 0 { "毎日指定した時間帯にバックグラウンドデーモンが過去の記憶を元に自律検証します。" } else { "Background daemon autonomously runs validation tests based on past experience." };
        let nw_prompt = if lang_idx == 0 { format!("{} ({})", nw_title, dim_text(nw_desc)) } else { format!("{} ({})", nw_title, dim_text(nw_desc)) };
        
        let hour_str: String = dialoguer::Input::with_theme(&OpenClaudeTheme)
            .with_prompt(nw_prompt)
            .default(existing.scheduler.night_watch_hour.to_string())
            .interact_text()
            .unwrap();

        let night_watch_hour: i32 = hour_str.parse().unwrap_or(3);

        let auto_title = if lang_idx == 0 { "Automation Bridge Mode" } else { "Automation Bridge Mode" };
        let auto_desc = if lang_idx == 0 { "自動化レベルを選択" } else { "Choose automation level" };
        
        let auto_opts = if lang_idx == 0 { 
            &["手動モード (安全/確認あり)", "完全自動モード (無料版: AutoStealth)", "完全自動モード (ログイン版: WebSandboxループ)", "ハイブリッドAPIモード (Qwen-Shield)"]
        } else { 
            &["Manual (Safe)", "AutoStealth (Free)", "AutoPremium (Logged-in Sandbox)", "Hybrid API Mode"] 
        };
        let default_auto_idx = match existing.automation_mode {
            AutomationMode::HybridApi => 3,
            AutomationMode::AutoPremium => 2,
            AutomationMode::AutoStealth => 1,
            AutomationMode::Manual => 0,
        };
        
        let auto_idx = dialoguer::Select::with_theme(&OpenClaudeTheme)
            .with_prompt(format!("{} ({})", auto_title, dim_text(auto_desc)))
            .items(auto_opts)
            .default(default_auto_idx) 
            .interact()
            .unwrap();
            
        let automation_mode = match auto_idx {
            3 => AutomationMode::HybridApi,
            2 => AutomationMode::AutoPremium,
            1 => AutomationMode::AutoStealth,
            _ => AutomationMode::Manual,
        };

        let provider_title = if lang_idx == 0 { "Cloud Brain Model" } else { "Cloud Brain Model" };
        let provider_opts = &[
            "Google Gemini API (gemini-2.5-pro)", 
            "OpenAI API (gpt-4o, o3-mini)", 
            "Anthropic API (claude-3-5-sonnet)", 
            "DeepSeek API (deepseek-v3, r1)", 
            "OpenRouter API", 
            "Groq API (llama3-70b-8192)", 
            "Together AI / Fireworks"
        ];
        
        let default_prov_idx = match existing.cloud_provider {
            CloudProvider::Gemini => 0,
            CloudProvider::OpenAi => 1,
            CloudProvider::Anthropic => 2,
            CloudProvider::DeepSeek => 3,
            CloudProvider::OpenRouter => 4,
            CloudProvider::Groq => 5,
            CloudProvider::Together => 6,
        };

        let cloud_provider = if automation_mode == AutomationMode::HybridApi || automation_mode == AutomationMode::Manual {
            let prov_idx = dialoguer::Select::with_theme(&OpenClaudeTheme)
                .with_prompt(provider_title)
                .items(provider_opts)
                .default(default_prov_idx)
                .interact()
                .unwrap();

            match prov_idx {
                0 => CloudProvider::Gemini,
                1 => CloudProvider::OpenAi,
                2 => CloudProvider::Anthropic,
                3 => CloudProvider::DeepSeek,
                4 => CloudProvider::OpenRouter,
                5 => CloudProvider::Groq,
                6 => CloudProvider::Together,
                _ => CloudProvider::Gemini,
            }
        } else {
            CloudProvider::Gemini
        };

        let api_key = if automation_mode == AutomationMode::HybridApi || automation_mode == AutomationMode::Manual {
            let api_key_prompt = if lang_idx == 0 { "API Key (空欄で入力をスキップし、既存のもの／環境変数を維持)" } else { "API Key (Leave empty to keep existing/ENV)" };
            let key_input: String = dialoguer::Password::with_theme(&OpenClaudeTheme)
                .with_prompt(api_key_prompt)
                .allow_empty_password(true)
                .interact()
                .unwrap();
            
            if !key_input.is_empty() {
                Some(key_input)
            } else {
                existing.api_key.clone()
            }
        } else {
            existing.api_key.clone()
        };

        let privacy_title = if lang_idx == 0 { "Privacy & Community Model Export" } else { "Privacy & Community Model Export" };
        let privacy_desc = if lang_idx == 0 { "ハルシネーション制御を含む成功した推論プロセス（JCross）をコミュニティに投稿しますか？" } else { "Do you consent to automatically export successful JCross memories?" };
        
        let privacy_opts = if lang_idx == 0 { &["はい (Opt-in)", "いいえ (Opt-out)"] } else { &["Yes (Opt-in)", "No (Opt-out)"] };
        let default_priv_idx = if existing.privacy.auto_sync { 0 } else { 1 };
        let privacy_idx = dialoguer::Select::with_theme(&OpenClaudeTheme)
            .with_prompt(format!("{} ({})", privacy_title, dim_text(privacy_desc)))
            .items(privacy_opts)
            .default(default_priv_idx)
            .interact()
            .unwrap();

        let auto_sync = privacy_idx == 0;

        let watch_title = if lang_idx == 0 { "Nightwatch Protocol (Local AI File Observer)" } else { "Nightwatch Protocol (Local AI File Observer)" };
        let watch_desc = if lang_idx == 0 { "ローカルのSLMを使用して夜間にファイル変更履歴を空間記憶にロスレス圧縮しますか？" } else { "Use local SLM to losslessly compress semantic file diffs into spatial memory at night?" };
        
        let watch_opts = if lang_idx == 0 { &["はい (Opt-in)", "いいえ (Opt-out)"] } else { &["Yes (Opt-in)", "No (Opt-out)"] };
        let default_watch_idx = if existing.nightwatch.enabled { 0 } else { 1 };
        let watch_idx = dialoguer::Select::with_theme(&OpenClaudeTheme)
            .with_prompt(format!("{} ({})", watch_title, dim_text(watch_desc)))
            .items(watch_opts)
            .default(default_watch_idx)
            .interact()
            .unwrap();

        let nightwatch_enabled = watch_idx == 0;

        let nightwatch_model = if nightwatch_enabled {
            let model_prompt = if lang_idx == 0 { "利用するローカルOllamaモデル名 (例: gemma2:27b, qwen2.5:32b)" } else { "Local Ollama model name (e.g., gemma2:27b, qwen2.5:32b)" };
            dialoguer::Input::with_theme(&OpenClaudeTheme)
                .with_prompt(model_prompt)
                .default(existing.nightwatch.model)
                .interact_text()
                .unwrap()
        } else {
            existing.nightwatch.model
        };

        let watch_dir = if nightwatch_enabled {
            let dir_prompt = if lang_idx == 0 { "監視するディレクトリ (デフォルト: . ＝ 現在のプロジェクト)" } else { "Directory to watch (Default: . = current project)" };
            dialoguer::Input::with_theme(&OpenClaudeTheme)
                .with_prompt(dir_prompt)
                .default(existing.nightwatch.watch_dir)
                .interact_text()
                .unwrap()
        } else {
            existing.nightwatch.watch_dir
        };

        let swarm_prompt = if lang_idx == 0 { "Colony Swarm ワーカー数 (1 = Chief単独, 最大30)" } else { "Colony Swarm Worker Count (1 = Chief only, Max 30)" };
        let swarm_str: String = dialoguer::Input::with_theme(&OpenClaudeTheme)
            .with_prompt(swarm_prompt)
            .default(existing.colony_swarm_size.to_string())
            .interact_text()
            .unwrap();
        let mut colony_swarm_size: usize = swarm_str.parse().unwrap_or(1);
        if colony_swarm_size < 1 { colony_swarm_size = 1; }
        if colony_swarm_size > 30 { colony_swarm_size = 30; }

        let config = Self {
            language: lang_str,
            automation_mode,
            persona: PersonaConfig { name, personality },
            scheduler: SchedulerConfig { night_watch_hour },
            cloud_provider,
            privacy: PrivacyConfig { auto_sync },
            nightwatch: NightwatchConfig { enabled: nightwatch_enabled, model: nightwatch_model, watch_dir },
            api_key,
            colony_swarm_size,
        };

        if let Err(e) = config.save(cwd) {
            tracing::error!("Failed to save configuration: {}", e);
        }

        config
    }
}
