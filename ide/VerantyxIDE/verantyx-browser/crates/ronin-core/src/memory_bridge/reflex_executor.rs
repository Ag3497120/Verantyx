use crate::domain::error::Result;
use crate::memory_bridge::spatial_index::MemoryNode;
use tracing::{info, warn};

#[derive(Debug, Clone, PartialEq)]
pub enum SafetyLevel {
    Low,
    Medium,
    High,
}

#[derive(Debug, Clone)]
pub enum ReflexType {
    Bash,
    FilePatch,
    ApiCall,
}

#[derive(Debug, Clone)]
pub struct ReflexAction {
    pub action_type: ReflexType,
    pub safe: SafetyLevel,
    pub idempotent: bool,
    pub cmd_or_payload: String,
    pub verify_cmd: Option<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub enum ReflexExecutionMode {
    /// 確信度 0.95以上 & 過去複数回の成功 & ファイル操作等安全なもの
    FullyAutomatic,
    /// 確信度 0.90〜0.94 または 副作用があるため初回確認
    PromptOnce,
    /// 確信度 < 0.90 または 未知の強力なコマンド
    RequireExplicitApproval,
}

pub struct ReflexResult {
    pub success: bool,
    pub logs: String,
}

impl ReflexResult {
    pub fn success(logs: &str) -> Self {
        Self { success: true, logs: logs.to_string() }
    }
    
    pub fn failure(logs: &str) -> Self {
        Self { success: false, logs: logs.to_string() }
    }
}

/// Parses the custom Reflex DSL from the JCross text payload
pub fn parse_reflex_block(raw_block: &str) -> Result<Vec<ReflexAction>> {
    let mut actions = Vec::new();

    let lines: Vec<&str> = raw_block.lines().collect();
    let mut i = 0;
    
    let mut action_type = ReflexType::Bash;
    let mut safe = SafetyLevel::High;
    let mut idempotent = false;
    let mut cmd = String::new();
    let mut verify: Option<String> = None;
    
    let mut in_cmd = false;
    let mut in_verify = false;

    while i < lines.len() {
        let line = lines[i].trim();
        
        if line.starts_with("TYPE:") {
            action_type = match line.replace("TYPE:", "").trim().to_lowercase().as_str() {
                "file" => ReflexType::FilePatch,
                "api" => ReflexType::ApiCall,
                _ => ReflexType::Bash,
            };
        } else if line.starts_with("SAFE:") {
            safe = match line.replace("SAFE:", "").trim().to_lowercase().as_str() {
                "low" => SafetyLevel::Low,
                "medium" => SafetyLevel::Medium,
                _ => SafetyLevel::High,
            };
        } else if line.starts_with("IDEMPOTENT:") {
            idempotent = line.replace("IDEMPOTENT:", "").trim().to_lowercase() == "true";
        } else if line.starts_with("CMD:") {
            in_cmd = true;
            in_verify = false;
        } else if line.starts_with("VERIFY:") {
            in_verify = true;
            in_cmd = false;
        } else if !line.is_empty() {
            if in_cmd {
                cmd.push_str(line);
                cmd.push('\n');
            } else if in_verify {
                let mut v = verify.unwrap_or_default();
                v.push_str(line);
                v.push('\n');
                verify = Some(v);
            }
        }
        i += 1;
    }

    if !cmd.is_empty() {
        actions.push(ReflexAction {
            action_type,
            safe,
            idempotent,
            cmd_or_payload: cmd.trim().to_string(),
            verify_cmd: verify.map(|v| v.trim().to_string()),
        });
    }

    Ok(actions)
}

/// Evaluates node physics to determine execution mode
pub fn determine_execution_mode(node: &MemoryNode, current_env_hash: Option<&str>) -> ReflexExecutionMode {
    let mut mode = if node.confidence >= 0.95 && node.weight >= 3.0 {
        ReflexExecutionMode::FullyAutomatic
    } else if node.confidence >= 0.90 {
        ReflexExecutionMode::PromptOnce
    } else {
        ReflexExecutionMode::RequireExplicitApproval
    };

    // Environment matching is required for fully automatic reflexes
    if let (Some(saved_hash), Some(current_hash)) = (&node.env_hash, current_env_hash) {
        if saved_hash != current_hash && mode == ReflexExecutionMode::FullyAutomatic {
            info!("🔄 Reflex Audit: Environment hash mismatch. Downgrading to PromptOnce.");
            mode = ReflexExecutionMode::PromptOnce;
        }
    } else if node.env_hash.is_some() && mode == ReflexExecutionMode::FullyAutomatic {
        mode = ReflexExecutionMode::PromptOnce;
    }

    mode
}

pub async fn execute_reflex(node: &MemoryNode, current_env_hash: Option<&str>) -> Result<ReflexResult> {
    let mode = determine_execution_mode(node, current_env_hash);
    
    let raw_payload = match &node.reflex_action {
        Some(p) => p,
        None => return Ok(ReflexResult::failure("No reflex payload found.")),
    };

    let actions = parse_reflex_block(raw_payload)?;
    let mut total_logs = String::new();

    for action in actions {
        match (&mode, &action.action_type) {
            (ReflexExecutionMode::FullyAutomatic, ReflexType::FilePatch) => {
                info!("🔄 Reflex [Auto-Patch]: Applying file modifications deterministically.");
                // Execute Patch
                total_logs.push_str(&format!("Applied patch: {}\n", action.cmd_or_payload));
            }
            (_, ReflexType::Bash) => {
                if mode == ReflexExecutionMode::RequireExplicitApproval || 
                   (mode == ReflexExecutionMode::PromptOnce && action.safe == SafetyLevel::High) {
                    
                    warn!("🔄 Reflex Audit: Verification required for command.");
                    eprintln!("========================================");
                    eprintln!("⚠️ CONFIRM REFLEX BASH EXECUTION");
                    eprintln!("Command: \n{}", action.cmd_or_payload);
                    eprintln!("Confidence: {:.1}%", node.confidence * 100.0);
                    eprintln!("Weight (Successes): {}", node.weight);
                    eprintln!("========================================");
                    
                    // In real implementation, this would halt and await a prompt.
                    // For the skeletal architecture of the CLI, we log it and reject auto-run for safety.
                    return Ok(ReflexResult::failure("Execution halted: Requires explicit user approval in prompt mode."));
                }
                
                info!("🔄 Reflex [Executing]: {}", action.cmd_or_payload);
                // Execute Bash
                total_logs.push_str(&format!("Executed bash: {}\n", action.cmd_or_payload));
            }
            _ => {
                info!("🔄 Reflex [Fallback]: Evaluated action but bypassed execution for safety.");
            }
        }
    }

    Ok(ReflexResult::success(&total_logs))
}
