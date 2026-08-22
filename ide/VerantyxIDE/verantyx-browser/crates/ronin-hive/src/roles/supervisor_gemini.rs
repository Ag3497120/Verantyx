use crate::actor::{Actor, Envelope};
use crate::messages::HiveMessage;
use async_trait::async_trait;
use tracing::warn;
use uuid::Uuid;

#[derive(Debug, PartialEq, Eq)]
pub enum SupervisorRank {
    Senior,
    Apprentice,
}

pub struct SupervisorGeminiActor {
    pub id: Uuid,
    pub rank: SupervisorRank,
    pub is_ja: bool,
    pub current_turns: u8,
}

impl SupervisorGeminiActor {
    pub fn new(id: Uuid, rank: SupervisorRank, is_ja: bool) -> Self {
        Self { id, rank, is_ja, current_turns: 0 }
    }
}

#[async_trait]
impl Actor for SupervisorGeminiActor {
    fn name(&self) -> &str {
        match self.rank {
            SupervisorRank::Senior => "SeniorSupervisorGemini",
            SupervisorRank::Apprentice => "ApprenticeSupervisorGemini",
        }
    }

    async fn receive(&mut self, env: Envelope) -> anyhow::Result<Option<Envelope>> {
        let msg: HiveMessage = match serde_json::from_str(&env.payload) {
            Ok(m) => m,
            Err(e) => {
                warn!("[{}] Failed to parse payload: {}", self.name(), e);
                return Ok(None);
            }
        };

        match msg {
            HiveMessage::Objective(task_data) => {
                let role_name = if self.rank == SupervisorRank::Senior { 
                    if self.is_ja { "シニア監視版" } else { "Senior Observer" }
                } else { 
                    if self.is_ja { "弟子監視版" } else { "Apprentice Observer" }
                };
                
                let prompt = if self.is_ja {
                    format!(
                        "【{}への時系列監視・記憶および特例監査依頼】\nあなたは時系列や会話の流れを監視し記憶する役割です。\n\n[超重要・絶対遵守ルール]\n出力を生成する際、挨拶、要約、説明、過程の解説は【一切禁止】します。「了解しました」「データを監査しました」「結果を確認しました」などのテキストを含めてはなりません。プレフィックスの付与や変更は以下のルールに従ってください。\n\n1. データが「最終回答」または「編集中」のプレフィックスを持つ場合:\n決して内容を要約・修正せず、受け取ったテキストデータを『一言一句全く同じ配置・同じ文面』でそのまま出力してください。\n\n2. データが「最終回答仮」のプレフィックスを持つ場合:\n内容にハルシネーションがないか監査・編集を行ってください。その後、先頭のプレフィックスを必ず『最終回答』に変更して出力してください（例: `最終回答\\n[監査済みの結果]`）。\n\n3. データが「そのまま出力」のプレフィックスを持つ場合:\n内容にハルシネーションがないか監査・編集を行ってください。その後、先頭のプレフィックスを必ず『最終出力』に変更して出力してください。\n\n4. データに上記のどのプレフィックスも含まれていない場合（純粋な実行結果データやターミナルログなど）:\n絶対に内容を要約したり感想を述べたりせず、さらに何のプレフィックス（最終回答等）も後付けせず、『受け取ったデータの一言一句全く同じ配置・同じ文面』でそのまま出力（エコーバック）してください。本文の書き換えは厳禁です。\n\nデータ: {}", 
                        role_name, task_data
                    )
                } else {
                    format!(
                        "[Observation and Audit Request for {}]\nYou are responsible for monitoring the timeline and conversation flow.\n\n[CRITICAL RULE]\nDo NOT include greetings, summaries, explanations, or process commentaries. Phrases like \"Understood\" or \"Audit complete\" are STRICTLY PROHIBITED. Follow these prefix rules exactly:\n\n1. If data has `[FINAL_ANSWER]` or `[EDITING]` prefix:\nDo NOT summarize or modify. Output the received payload EXACTLY as is, echoing the exact phrasing and position.\n\n2. If data has `[TEMP_FINAL]` prefix:\nAudit for hallucinations and edit if necessary. Then, CHANGE the prefix to `[FINAL_ANSWER]` and output (e.g., `[FINAL_ANSWER]\\n[audited result]`).\n\n3. If data has `[RAW_OUTPUT]` prefix:\nAudit for hallucinations and edit if necessary. Then, CHANGE the prefix to `[FINAL_OUTPUT]` and output.\n\n4. If data does NOT have any of the above prefixes (e.g. pure execution log):\nDo NOT summarize, do NOT express opinions, and do NOT prepend ANY prefix like `[FINAL_ANSWER]`. Echo back the EXACT string without altering a single character. Strictly verbatim.\n\nData: {}", 
                        role_name, task_data
                    )
                };

                let prompt_title = if self.is_ja { "サブタスク" } else { "Subtask" };
                let padded_prompt = format!("===============================\n{}\n===============================", prompt.trim());
                let send_msg = if self.is_ja { format!("これから【{}】版に送ります。クリップボードに保存します...", role_name) } else { format!("Sending to {}. Copying to clipboard...", role_name) };
                let saved_msg = if self.is_ja { "保存しました！内容は以下の通りです:" } else { "Saved! Content snippet:" };

                println!("\n{}", console::style(format!("╭─ [ Verantyx: {} {} ] ──────────────────", role_name, prompt_title)).yellow().bold());
                println!("{} 📝 {}", console::style("│").yellow().bold(), send_msg);

                let _ = crate::roles::symbiotic_macos::SymbioticMacOS::set_clipboard(&padded_prompt).await;
                tokio::time::sleep(tokio::time::Duration::from_millis(500)).await;

                println!("{} ✔ {}", console::style("│").green().bold(), saved_msg);
                println!("{} {}", console::style("│").green(), console::style(padded_prompt.chars().take(150).collect::<String>() + "...").dim());
                println!("{}", console::style("╰─────────────────────────────────────────────────────").yellow().bold());

                let (window_name, pos_id) = if self.rank == SupervisorRank::Senior { 
                    if self.is_ja { ("【中央のシニア用ウィンドウ】", "middle") } else { ("[Middle Senior Window]", "middle") }
                } else { 
                    if self.is_ja { ("【右側の弟子用ウィンドウ】", "right") } else { ("[Right Apprentice Window]", "right") }
                };

                let cwd = std::env::current_dir().unwrap_or_else(|_| std::path::PathBuf::from("."));
                let cfg = crate::config::VerantyxConfig::load(&cwd);

                self.current_turns += 1;
                if self.current_turns >= 5 {
                    println!("{} Reached 5 memory turns for {}. Resetting Web Session to evade detection/context-bloat.", console::style("[SYSTEM]").cyan(), window_name);
                    let reload_js = "window.location.href = 'https://gemini.google.com/app';";
                    let _reload_script = format!(
                        r#"tell application "Safari"
                            set winList to every window
                            repeat with w in winList
                                if name of w contains "{}" or document 1 of w is not missing value then
                                    do JavaScript "{}" in document 1 of w
                                    exit repeat
                                end if
                            end repeat
                        end tell"#, 
                        "Gemini", // Fallback search term if needed though we'll just target front window easily below
                        reload_js
                    );

                    // A simpler robust way: focus the panel first, then do JavaScript
                    let _ = crate::roles::symbiotic_macos::SymbioticMacOS::focus_safari_panel(pos_id).await;
                    let reload_script_direct = format!(r#"tell application "Safari" to do JavaScript "{}" in front document"#, reload_js.replace("\"", "\\\""));
                    let _ = tokio::process::Command::new("osascript").arg("-e").arg(&reload_script_direct).output().await;
                    
                    tokio::time::sleep(tokio::time::Duration::from_secs(4)).await;
                    self.current_turns = 0;
                }

                loop {
                    println!("\n{}", console::style(if self.is_ja {"👉 クリップボード準備完了。ブラウザを開きますか？"} else {"👉 Clipboard ready. Focus browser tabs?"}).cyan().bold());
                    
                    // Step 1: Move Focus
                    if cfg.automation_mode == crate::config::AutomationMode::AutoStealth {
                        let sent_msg = format!("🚀 🤖 [AUTO-STEALTH] Focused {}. Geometric calibration executing...", window_name);
                        println!("{}", console::style(sent_msg).green().bold());
                    } else {
                        let selections = if self.is_ja { vec![" コピー完了・フォーカス移動へ", " もう一度コピー"] } else { vec![" Move Focus", " Copy Again"] };
                        let selection = dialoguer::Select::new()
                            .with_prompt(if self.is_ja { "選択" } else { "Action" })
                            .default(0).items(&selections[..]).interact().unwrap();
                        if selection != 0 {
                            let _ = crate::roles::symbiotic_macos::SymbioticMacOS::set_clipboard(&padded_prompt).await;
                            continue;
                        }
                    }

                    // Step 2: Paste and Send Information
                    if cfg.automation_mode != crate::config::AutomationMode::AutoStealth {
                        let sent_msg = format!("🚀 Focused {}. Please press Cmd+V and Send it manually!", window_name);
                        println!("{}", console::style(sent_msg).green().bold());
                    }
                    
                    let _ = crate::roles::symbiotic_macos::SymbioticMacOS::focus_safari_panel(pos_id).await;
                    tokio::time::sleep(tokio::time::Duration::from_millis(500)).await;
                    
                    if cfg.automation_mode == crate::config::AutomationMode::AutoStealth {
                        println!("{} 📝 (自動モードのため、自動ペースト＆送信を実行します...)", console::style("[AUTO]").cyan());
                        let _ = crate::roles::symbiotic_macos::SymbioticMacOS::auto_visual_calibrated_paste_and_send(&padded_prompt).await;
                    }

                    // Step 3: Wait for LLM and signal extraction
                    if cfg.automation_mode == crate::config::AutomationMode::AutoStealth {
                        let base_wait = 20; // Require decent wait for visual LLM processing
                        let char_count = padded_prompt.chars().count() as u64;
                        let dynamic_wait = char_count / 100;
                        let wait_time = std::cmp::min(base_wait + dynamic_wait, 60);
                        
                        println!("{} ⏳ Waiting {} seconds for Safari Gemini rendering...", console::style("[AUTO]").cyan(), wait_time);
                        tokio::time::sleep(tokio::time::Duration::from_secs(wait_time)).await;
                    } else {
                        let confirm_prompt = if self.is_ja { "✔ 回答が出たら Cmd+C でコピーして選択" } else { "✔ Copy answer (Cmd+C) and press Enter" };
                        let _ = dialoguer::Select::new().with_prompt(confirm_prompt)
                            .default(0).items(&[" Extraction Ready"]).interact().unwrap();
                    }
                    
                    // Step 4: Autonomous copy logic. 
                    if cfg.automation_mode == crate::config::AutomationMode::AutoStealth {
                        println!("{} ⏳ Executing autonomous visual extraction...", console::style("[SYSTEM]").cyan());
                        if let Err(e) = crate::roles::symbiotic_macos::SymbioticMacOS::auto_visual_calibrated_extract_and_cleanup().await {
                            warn!("[Supervisor] Autonomous geometric extraction EXITED WITH ERROR: {}", e);
                        }
                        tokio::time::sleep(tokio::time::Duration::from_millis(500)).await;
                    }

                    // Retrieve OS Clipboard as Final Output
                    let gemini_response = crate::roles::symbiotic_macos::SymbioticMacOS::get_clipboard().await.unwrap_or_default();
                    
                    // Validation Check: If extraction copied the prompt we just pasted, Gemini hasn't finished yet or extraction failed visually
                    if cfg.automation_mode == crate::config::AutomationMode::AutoStealth {
                        if gemini_response.trim() == padded_prompt.trim() || gemini_response.is_empty() {
                            println!("{}", console::style(if self.is_ja { "❌ 抽出エラー (Geminiが応答中か要素が見つかりません)。再試行します..." } else { "❌ Extraction overlap. Gemini hasn't finished reading. Retrying..." }).red());
                            tokio::time::sleep(tokio::time::Duration::from_millis(3000)).await;
                            continue;
                        }
                    }

                    let success_ext = if self.is_ja { format!("✔ 自動抽出完了！({}文字)", gemini_response.chars().count()) } else { format!("✔ Automated Extraction done! ({} chars)", gemini_response.chars().count()) };
                    println!("{}", console::style(success_ext).green());
                    
                    // Break the loop and return the validated response
                    let reply = HiveMessage::Objective(gemini_response);
                    return Ok(Some(Envelope {
                        message_id: Uuid::new_v4(),
                        sender: self.name().to_string(),
                        recipient: env.sender,
                        payload: serde_json::to_string(&reply)?,
                    }));
                }
            },


            _ => Ok(None)
        }
    }
}
