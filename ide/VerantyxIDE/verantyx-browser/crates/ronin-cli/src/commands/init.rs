//! `ronin init` — initializes a Ronin project in the current directory.
//!
//! Creates:
//!   - `ronin.toml`            (project config with sensible defaults)
//!   - `.ronin/memory/front/`  (JCross Front zone directory)
//!   - `.ronin/memory/near/`   (JCross Near zone directory)
//!   - `.ronin/backups/`       (diff-ux backup directory)
//!   - `.gitignore` entries    (backups, audit logs)
//!   - `RONIN.md`              (project-level memory seed)

use anyhow::{Context, Result};
use clap::Args;
use console::style;
use dialoguer::{Input, Select, Confirm};
use std::path::{Path, PathBuf};

#[derive(Args, Debug)]
pub struct InitArgs {
    /// Directory to initialize (defaults to current directory)
    #[arg(value_name = "DIR", default_value = ".")]
    pub dir: PathBuf,

    /// Ollama model to use (e.g. gemma3:27b)
    #[arg(short, long, default_value = "gemma3:27b")]
    pub model: String,

    /// Initialize for English (default: ja)
    #[arg(long)]
    pub english: bool,

    /// Skip creating RONIN.md memory seed
    #[arg(long = "no-seed")]
    pub no_seed: bool,
}

pub async fn execute(args: InitArgs) -> Result<()> {
    let root = args.dir.canonicalize().unwrap_or(args.dir.clone());
    
    println!(
        "\n{} Initializing Ronin project Setup Wizard in {}",
        style("⚡").cyan(),
        style(root.display()).bold()
    );

    // Interactive Wizard for Execution Mode
    let mode_options = &[
        "API Mode (Fast, Paid APIs via Anthropic/Gemini)",
        "Fully Free Mode (Browser-based Gemini automation)"
    ];
    let selected_mode_idx = Select::new()
        .with_prompt("Select execution mode")
        .items(mode_options)
        .default(0)
        .interact()?;
    let cloud_fallback = if selected_mode_idx == 0 { "api" } else { "browser_hitl" };

    // Interactive Wizard for Model
    let default_model = "gemma3:27b";
    
    let mut selected_model = default_model.to_string();
    if let Some(mut models) = fetch_ollama_models().await {
        println!("{}", style("Found local Ollama models!").green());
        models.push("Import new model (Drag & Drop .safetensors/.gguf)".to_string());
        models.push("Other (type manually)".to_string());
        
        let sel_idx = Select::new()
            .with_prompt("Select an installed model")
            .items(&models)
            .default(0)
            .interact()?;
            
        if sel_idx == models.len() - 1 {
            // Other
            selected_model = Input::new()
                .with_prompt("Type your model name")
                .default(args.model.clone())
                .interact_text()?;
        } else if sel_idx == models.len() - 2 {
            // Import new model
            println!("\n{}", style("📦 Ronin Model Importer").cyan().bold());
            let path_input: String = Input::new()
                .with_prompt("Drag and drop your .safetensors or .gguf file here, then press Enter")
                .interact_text()?;

            let mut path_str = path_input.trim().to_string();
            if path_str.starts_with('\'') && path_str.ends_with('\'') {
                path_str = path_str[1..path_str.len()-1].to_string();
            } else if path_str.starts_with('"') && path_str.ends_with('"') {
                path_str = path_str[1..path_str.len()-1].to_string();
            }
            path_str = path_str.trim().to_string().replace("\\ ", " ");

            let path = Path::new(&path_str);
            if !path.exists() {
                anyhow::bail!("File not found: {}", path.display());
            }

            let base_name = path.file_stem().unwrap_or_default().to_string_lossy().to_string();
            let new_model_name: String = Input::new()
                .with_prompt("What should we name this model in Ollama?")
                .default(base_name)
                .interact_text()?;

            let temp_dir = std::env::temp_dir();
            let modelfile_path = temp_dir.join(format!("Modelfile_ronin_{}", new_model_name));
            let content = format!("FROM \"{}\"\n", path.canonicalize()?.display());
            tokio::fs::write(&modelfile_path, content).await?;

            println!("\n{} Executing `ollama create {} -f ...`\n", style("⚡").cyan(), new_model_name);

            let mut child = tokio::process::Command::new("ollama")
                .arg("create")
                .arg(&new_model_name)
                .arg("-f")
                .arg(&modelfile_path)
                .stdout(std::process::Stdio::inherit())
                .stderr(std::process::Stdio::inherit())
                .spawn()
                .context("Failed to execute `ollama`. Is it installed and in your PATH?")?;

            let status = child.wait().await?;
            let _ = tokio::fs::remove_file(&modelfile_path).await;

            if status.success() {
                println!("\n{} Successfully imported {} into Ollama!\n", style("✅").green(), style(&new_model_name).bold());
                selected_model = new_model_name;
            } else {
                anyhow::bail!("Failed to import model. Command exited with status: {}", status);
            }
        } else {
            selected_model = models[sel_idx].clone();
        }
    } else {
        selected_model = Input::new()
            .with_prompt("Which provider/model would you like to use?")
            .default(args.model.clone())
            .interact_text()?;
    }

    // Interactive Wizard for Language
    let language_options = &["Japanese (ja)", "English (en)"];
    let default_lang_idx = if args.english { 1 } else { 0 };
    let selected_lang_idx = Select::new()
        .with_prompt("Select your system language")
        .items(language_options)
        .default(default_lang_idx)
        .interact()?;
        
    let is_english = selected_lang_idx == 1;
    let lang = if is_english { "en" } else { "ja" };

    // Interactive Confirm for Seed
    let setup_seed = Confirm::new()
        .with_prompt("Do you want to scaffold the default RONIN.md memory seed?")
        .default(!args.no_seed)
        .interact()?;

    // Interactive Wizard for Global Access Scope
    let scope_options = &[
        "Project Only Scope (Safe - sandbox restricted to current dir)",
        "Global OS Access Scope (God Mode - AI has full access to the Mac)",
    ];
    let selected_scope_idx = Select::new()
        .with_prompt("Select Agent File System Access Policy")
        .items(scope_options)
        .default(0)
        .interact()?;
    let allow_escape = selected_scope_idx == 1;

    println!("\n{} Applying configuration...", style("🔨").magenta());

    // Create directory structure
    let dirs = [
        ".ronin/memory/front",
        ".ronin/memory/near",
        ".ronin/memory/mid",
        ".ronin/memory/deep",
        ".ronin/backups",
        ".ronin/audit",
    ];
    for dir in &dirs {
        tokio::fs::create_dir_all(root.join(dir)).await?;
        println!("  {} Created {}", style("├─").dim(), style(dir).dim());
    }

    // Write ronin.toml
    let config_content = format!(
        r#"# Ronin Agent Configuration
# Generated by `ronin init`

[agent]
model       = "{}"
max_steps   = 12
hitl        = true
language    = "{}"
cloud_fallback = "{}"

[ollama]
host = "127.0.0.1"
port = 11434

[memory]
auto_inject      = true
front_max_tokens = 4096

[sandbox]
timeout_secs   = 60
allow_escape   = {}
"#,
        selected_model, lang, cloud_fallback, allow_escape
    );
    tokio::fs::write(root.join("ronin.toml"), &config_content).await?;
    println!("  {} Created {}", style("├─").dim(), style("ronin.toml").green());

    // Write RONIN.md seed
    if setup_seed {
        let seed = format!(
            "# Project Memory Seed\n\n\
            This file is automatically injected into the Ronin agent's \
            Front memory zone on every session.\n\n\
            ## Project Overview\n\n\
            > Describe your project here so Ronin understands its context.\n\n\
            ## Key Conventions\n\n\
            - Language: {}\n\
            - Primary Model: {}\n\
            - Working Directory: {}\n",
            if is_english { "English" } else { "日本語" },
            selected_model,
            root.display()
        );
        tokio::fs::write(root.join("RONIN.md"), &seed).await?;
        println!("  {} Created {}", style("├─").dim(), style("RONIN.md").green());

        // Copy seed into Front memory zone
        tokio::fs::copy(
            root.join("RONIN.md"),
            root.join(".ronin/memory/front/project_seed.md"),
        ).await?;
        println!("  {} Seeded {}", style("├─").dim(), style(".ronin/memory/front/project_seed.md").dim());
    }

    // Append to .gitignore
    let gitignore_path = root.join(".gitignore");
    let entries = "\n# Ronin\n.ronin/backups/\n.ronin/audit/\n";
    let existing = tokio::fs::read_to_string(&gitignore_path).await.unwrap_or_default();
    if !existing.contains(".ronin/backups") {
        tokio::fs::write(
            &gitignore_path,
            format!("{}{}", existing, entries),
        ).await?;
        println!("  {} Updated {}", style("└─").dim(), style(".gitignore").dim());
    }

    println!(
        "\n{} Ronin project initialized!\n",
        style("✅").green().bold()
    );
    println!(
        "  Run {}  to start the agent REPL",
        style("ronin start").cyan().bold()
    );
    println!(
        "  Run {}  to execute a single task\n",
        style("ronin run \"<task>\"").cyan().bold()
    );

    Ok(())
}

async fn fetch_ollama_models() -> Option<Vec<String>> {
    let client = reqwest::Client::new();
    let resp = client.get("http://127.0.0.1:11434/api/tags")
        .timeout(std::time::Duration::from_secs(2))
        .send()
        .await
        .ok()?;
        
    #[derive(serde::Deserialize)]
    struct TagsResp { models: Vec<ModelItem> }
    #[derive(serde::Deserialize)]
    struct ModelItem { name: String }
    
    let tags: TagsResp = resp.json().await.ok()?;
    let names: Vec<String> = tags.models.into_iter().map(|m| m.name).collect();
    if names.is_empty() {
        None
    } else {
        Some(names)
    }
}
