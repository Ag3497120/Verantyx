use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum EngineTier {
    Lightweight, // <= 10B parameters
    Midweight,   // 11B - 35B parameters
    Heavyweight, // > 35B parameters or Cloud
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CalibrationProfile {
    pub name: String,
    pub max_parallel_tools: u8,
    pub enforce_atomic_react: bool,
    pub system_prompt_preset: String,
}

impl CalibrationProfile {
    /// Derives the calibration profile purely based on billion-parameter count
    pub fn derive_from_params(params: u32) -> Self {
        if params <= 10 {
            Self {
                name: "Lightweight Engine".to_string(),
                max_parallel_tools: 1,
                enforce_atomic_react: true,
                system_prompt_preset: "lightweight".to_string(),
            }
        } else if params <= 35 {
            Self {
                name: "Midweight Engine".to_string(),
                max_parallel_tools: 2,
                enforce_atomic_react: false,
                system_prompt_preset: "standard".to_string(),
            }
        } else {
            Self {
                name: "Heavyweight Engine".to_string(),
                max_parallel_tools: 10,
                enforce_atomic_react: false,
                system_prompt_preset: "unbound".to_string(),
            }
        }
    }

    /// Extrapolates parameter count from standard model identifier strings like "gemma:27b"
    pub fn parse_model_id(model_id: &str) -> Self {
        let params = if let Some(idx) = model_id.find('b') {
            let num_str: String = model_id[..idx].chars().rev().take_while(|c| c.is_ascii_digit()).collect();
            let parsed_num: String = num_str.chars().rev().collect();
            parsed_num.parse::<u32>().unwrap_or(0)
        } else {
            0
        };
        Self::derive_from_params(params)
    }

    pub fn generate_system_directives(&self) -> String {
        match self.system_prompt_preset.as_str() {
            "lightweight" => "[RONIN CORE SYSTEM]\n\
                              Your parameter size dictates strict atomic execution.\n\
                              1. DO NOT parallelize tasks.\n\
                              2. Execute ONE <action> at a time.\n\
                              3. ALWAYS wait for the <observation> shell output before proceeding.\n\
                              Failure to do so will result in an OS logic deadlock."
                .to_string(),
            "standard" => "[RONIN CORE SYSTEM]\n\
                           Standard execution confirmed. You may bundle multiple related shell modifications per turn if safe.\n\
                           Prioritize [Diff Review] validation for critical files."
                .to_string(),
            _ => "[RONIN CORE SYSTEM - UNBOUND]\n\
                  Maximum capability unlocked. You possess full multi-threaded tool orchestration capabilities.\n\
                  Execute dynamic MCP chains or bulk shell changes as you see fit."
                .to_string(),
        }
    }
}
