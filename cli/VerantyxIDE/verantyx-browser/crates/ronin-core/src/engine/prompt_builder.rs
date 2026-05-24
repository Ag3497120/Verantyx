//! Enterprise prompt construction engine.
//!
//! Assembles the full system prompt for each agent turn by layering:
//! 1. Ronin identity + role declaration
//! 2. JCross spatial memory injection (Front zone)
//! 3. Tier-based calibration directives
//! 4. Tool schema definitions (MCP-registered tools)
//! 5. Conversation history (budgeted)

use crate::domain::config::{RoninConfig, SystemLanguage};
use crate::domain::types::AgentRole;
use crate::models::tier_calibration::TierProfile;
use crate::models::context_budget::{ContextBudget, TokenLedger, estimate_tokens};
use std::fmt::Write;

// ─────────────────────────────────────────────────────────────────────────────
// Tool Schema (for system prompt embedding)
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone)]
pub struct ToolSchema {
    pub name: String,
    pub description: String,
    pub parameters: Vec<ToolParameter>,
}

#[derive(Debug, Clone)]
pub struct ToolParameter {
    pub name: String,
    pub required: bool,
    pub description: String,
}

impl ToolSchema {
    pub fn to_prompt_block(&self) -> String {
        let params = self.parameters.iter().map(|p| {
            format!(
                "  - `{}` ({}): {}",
                p.name,
                if p.required { "required" } else { "optional" },
                p.description
            )
        }).collect::<Vec<_>>().join("\n");

        format!(
            "### Tool: `{}`\n{}\n\nParameters:\n{}\n",
            self.name, self.description, params
        )
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Prompt Builder
// ─────────────────────────────────────────────────────────────────────────────

pub struct PromptBuilder<'a> {
    config: &'a RoninConfig,
    profile: &'a TierProfile,
    budget: &'a ContextBudget,
    ledger: TokenLedger,
}

impl<'a> PromptBuilder<'a> {
    pub fn new(
        config: &'a RoninConfig,
        profile: &'a TierProfile,
        budget: &'a ContextBudget,
    ) -> Self {
        Self {
            config,
            profile,
            budget,
            ledger: TokenLedger::default(),
        }
    }

    /// Builds the full system prompt string for a given agent role and context.
    pub fn build_system_prompt(
        &mut self,
        role: AgentRole,
        turn: u32,
        front_memories: &str,
        repo_map: &str,
        tools: &[ToolSchema],
    ) -> String {
        let is_ja = self.config.agent.system_language == SystemLanguage::Japanese;
        let mut prompt = String::new();

        // 1. Identity block
        writeln!(prompt, "{}", self.identity_block(role, turn, is_ja)).ok();

        // 2. Repo Map injection
        if !repo_map.is_empty() {
            writeln!(prompt, "{}", self.repo_map_block(repo_map, is_ja)).ok();
        }

        // 3. Memory injection
        if !front_memories.is_empty() && self.config.memory.auto_inject {
            writeln!(prompt, "{}", self.memory_block(front_memories, is_ja)).ok();
        }

        // 4. Tier calibration directives
        writeln!(prompt, "{}", self.profile.generate_sys_prompt()).ok();

        // 5. Tool schema
        if !tools.is_empty() {
            writeln!(prompt, "{}", self.tool_block(tools, is_ja)).ok();
        }

        // 6. Action format instructions
        writeln!(prompt, "{}", self.action_format_block(is_ja)).ok();

        self.ledger.record_system(estimate_tokens(&prompt));
        prompt
    }

    fn identity_block(&self, role: AgentRole, turn: u32, is_ja: bool) -> String {
        if is_ja {
            format!(
                "# Ronin Agent — {role}\n\
                あなたはRonin Agentシステムの **{role}** です。\n\
                現在のターン: {turn} | モデル: {model} | プロファイル: {profile}\n",
                role = role,
                turn = turn,
                model = self.config.agent.primary_model,
                profile = self.profile.name,
            )
        } else {
            format!(
                "# Ronin Agent — {role}\n\
                You are the **{role}** of the Ronin Agent system.\n\
                Turn: {turn} | Model: {model} | Profile: {profile}\n",
                role = role,
                turn = turn,
                model = self.config.agent.primary_model,
                profile = self.profile.name,
            )
        }
    }

    fn repo_map_block(&self, repo_map: &str, is_ja: bool) -> String {
        if is_ja {
            format!("## 🗺️ プロジェクト構造 (Repository AST Map)\n\n{}\n", repo_map)
        } else {
            format!("## 🗺️ Project Structure (Repository AST Map)\n\n{}\n", repo_map)
        }
    }

    fn memory_block(&self, memories: &str, is_ja: bool) -> String {
        if is_ja {
            format!("## 🧠 記憶（JCross Front Zone — 必ず読め）\n\n{memories}\n")
        } else {
            format!("## 🧠 Memory (JCross Front Zone — Read First)\n\n{memories}\n")
        }
    }

    fn tool_block(&self, tools: &[ToolSchema], is_ja: bool) -> String {
        let header = if is_ja {
            "## 🛠️ 利用可能ツール\n以下のXMLアクション構文でツールを呼び出してください。"
        } else {
            "## 🛠️ Available Tools\nInvoke tools using the XML action syntax below."
        };

        let schema_blocks = tools
            .iter()
            .map(|t| t.to_prompt_block())
            .collect::<Vec<_>>()
            .join("\n");

        format!("{header}\n\n{schema_blocks}")
    }

    fn action_format_block(&self, is_ja: bool) -> String {
        if is_ja {
            "## ⚙️ アクション構文（必須）\n\
            ツールを呼び出す時は必ず以下の形式を使用してください:\n\
            ```\n\
            <action>tool_name</action>\n\
            <payload>{\"arg\": \"value\"}</payload>\n\
            ```\n\
            完了時は `<action>finish</action>` を出力してください。".to_string()
        } else {
            "## ⚙️ Action Syntax (Required)\n\
            When calling a tool, always use this format:\n\
            ```\n\
            <action>tool_name</action>\n\
            <payload>{\"arg\": \"value\"}</payload>\n\
            ```\n\
            When complete output `<action>finish</action>`.".to_string()
        }
    }

    pub fn token_ledger(&self) -> &TokenLedger {
        &self.ledger
    }
}
