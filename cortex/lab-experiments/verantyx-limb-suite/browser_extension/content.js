// content.js
(function() {
    'use strict';

    const BRIDGE_URL = 'http://127.0.0.1:8000/exec';
    console.log("%c[Verantyx Eye Agent] DOM-Safe Universal Polling & File Edit active...", "color: #ff0055; font-weight: bold; background-color: #1a1a1a; padding: 2px 5px; border-radius: 4px;");

    const executedCounts = {};
    const executedEdits = new Set();
    const executedReads = new Set();
    let pollInterval = null;

    function injectTextToChat(content) {
        const inputBox = document.querySelector('rich-textarea p, [contenteditable="true"], [role="textbox"]');
        if (inputBox) {
            inputBox.focus();
            const success = document.execCommand('insertText', false, content);
            if (!success) {
                navigator.clipboard.writeText(content).then(() => alert("[Verantyx System] Injected to Clipboard! Press Cmd+V."));
            }
        } else {
            navigator.clipboard.writeText(content).then(() => alert("[Verantyx System] Injected to Clipboard! Press Cmd+V."));
        }
    }

    function safeSendMessage(payload, callback) {
        try {
            chrome.runtime.sendMessage(payload, callback);
        } catch (e) {
            if (e.message.includes("Extension context invalidated")) {
                console.error("[Verantyx Eye] 🛑 Extension was updated. This old script is dying. Please REFRESH the page (F5)!");
                if (pollInterval) clearInterval(pollInterval);
            } else {
                console.error("[Verantyx Eye] sendMessage error:", e);
            }
        }
    }

    function sendCommand(cmdStr, message = "") {
        console.log(`%c[Verantyx Eye Agent] Dispatching command: ${cmdStr}`, "color: #00acee;");
        safeSendMessage({
            type: "SEND_COMMAND",
            url: BRIDGE_URL,
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command: cmdStr, message: message })
        }, (response) => {
            if (response && response.success) {
                console.log("Server Response:", response.data);
            }
        });
    }

    pollInterval = setInterval(() => {
        let allText = document.body.textContent || "";
        
        const bubbles = document.querySelectorAll('message-content, .message-content, .model-response-text, [class*="message"], [class*="response"], custom-message');
        for (let b of bubbles) {
            allText += "\n" + (b.innerText || b.textContent || "");
            if (b.shadowRoot) {
                allText += "\n" + (b.shadowRoot.textContent || "");
            }
        }
        
        // 1. VX_CMD
        const cmdMatches = [...allText.matchAll(/VX_CMD:([A-Z_]+)/g)];
        const currentCounts = {};
        for (const match of cmdMatches) {
            const cmd = match[1];
            currentCounts[cmd] = (currentCounts[cmd] || 0) + 1;
        }
        
        Object.keys(currentCounts).forEach(cmd => {
            const prevCount = executedCounts[cmd] || 0;
            const newCount = currentCounts[cmd];
            if (newCount > prevCount) {
                for(let i=0; i < (newCount - prevCount); i++) {
                    sendCommand(cmd, "Captured from live DOM");
                }
                executedCounts[cmd] = newCount;
            }
        });

        // 2. VX_FILE_EDIT 
        // [重要修正] 絵文字や句読点がファイル名に混入しないよう、英数字とパス記号のみに厳密化
        const editRegex = /VX_FILE_EDIT:\s*`?([\w\.\/\-\\]+)`?\s*<<<< SEARCH\s*([\s\S]*?)\s*==== REPLACE\s*([\s\S]*?)\s*>>>>/g;
        const editMatches = [...allText.matchAll(editRegex)];
        for (const match of editMatches) {
            const rawBlock = match[0].trim();
            if (!executedEdits.has(rawBlock)) {
                executedEdits.add(rawBlock);
                const path = match[1];
                const searchTxt = match[2];
                const replaceTxt = match[3];

                console.log(`[Verantyx Eye Agent] DETECTED File Edit for ${path}. Routing to PC Backend...`);
                safeSendMessage({
                    type: "EXEC_FILE_EDIT",
                    data: { path: path, search: searchTxt, replace: replaceTxt }
                }, (response) => {
                    if (response && response.success && response.data.status === "success") {
                        console.log("Edit Applied via PWA:", response.data.message);
                        injectTextToChat(`> ✅ [SYSTEM: PWA Approved] Verified and updated \`${path}\`\n\n`);
                    } else {
                        console.error("Edit Failed/Denied:", response?.error || response?.data?.detail);
                        injectTextToChat(`> ❌ [SYSTEM: Error or PWA Denied] Edit failed: ${response?.error || response?.data?.detail}\n\n`);
                    }
                });
            }
        }

        // 3. VX_FILE_READ
        // [重要修正] 絵文字や句読点がファイル名に混入しないよう、英数字とパス記号のみに厳密化
        const readRegex = /VX_FILE_READ:\s*`?([\w\.\/\-\\]+)`?/g;
        const readMatches = [...allText.matchAll(readRegex)];
        for (const match of readMatches) {
            const rawLine = match[0].trim();
            if (!executedReads.has(rawLine)) {
                executedReads.add(rawLine);
                const path = match[1];
                console.log(`[Verantyx Eye Agent] DETECTED File Read request: ${path}`);
                safeSendMessage({
                    type: "READ_FILE",
                    path: path
                }, (response) => {
                    if (response && response.success && response.data.status === "success") {
                        const fileContent = response.data.content;
                        const injectString = `<<FILE_CONTENT_OF: ${path}>>\n\`\`\`\n${fileContent}\n\`\`\`\n`;
                        injectTextToChat(injectString);
                    } else {
                        injectTextToChat(`> ❌ [SYSTEM: Error] Failed to read ${path}: ${response?.error || response?.data?.detail}\n\n`);
                    }
                });
            }
        }
        // 4. VX_JCROSS_SIM
        const jcrossRegex = /VX_JCROSS_SIM:[\s\S]*?```(?:jcross|text|md|markdown)?\s*\n([\s\S]*?)```/g;
        const jcrossMatches = [...allText.matchAll(jcrossRegex)];
        for (const match of jcrossMatches) {
            const rawBlock = match[0].trim();
            if (!executedReads.has(rawBlock)) {
                executedReads.add(rawBlock);
                const simData = match[1];
                
                console.log(`[Verantyx Eye Agent] DETECTED JCross Sim Protocol. Routing to PC Backend...`);
                safeSendMessage({
                    type: "EXEC_JCROSS_SIM",
                    data: { sim_data: simData }
                }, (response) => {
                    if (response && response.success) {
                         console.log("JCross Payload successfully broadcasted to PWA.");
                    }
                });
            }
        }

        // 5. VX_EXEC_BRAIN (Backtick REQUIRED to prevent streaming infinite loops)
        const execRegex = /VX_EXEC_BRAIN:\s*`([^\n`]+)`/g;
        const execMatches = [...allText.matchAll(execRegex)];
        for (const match of execMatches) {
            const rawBlock = match[0].trim();
            if (!executedReads.has(rawBlock)) {
                executedReads.add(rawBlock);
                const cmd = match[1].trim();
                
                console.log(`[Verantyx Eye Agent] DETECTED External Brain execution: ${cmd}`);
                safeSendMessage({
                    type: "EXEC_BRAIN",
                    data: { command: cmd }
                }, (response) => {
                    if (response && response.success && response.data.status === "success") {
                        const fileContent = response.data.output;
                        const injectString = `<<BRAIN_SIMULATION_RESULT>>\n\`\`\`\n${fileContent}\n\`\`\`\n`;
                        injectTextToChat(injectString);
                    } else {
                        injectTextToChat(`> ❌ [SYSTEM: Brain Error] Failed to execute ${cmd}: ${response?.error || response?.data?.detail}\n\n`);
                    }
                });
            }
        }
        // 6. Unified Tool Call (claw-code compatibility)
        const toolCallRegex = /<tool_call>([\s\S]*?)<\/tool_call>/g;
        const toolMatches = [...allText.matchAll(toolCallRegex)];
        for (const match of toolMatches) {
            const rawBlock = match[0].trim();
            if (!executedReads.has(rawBlock)) {
                executedReads.add(rawBlock);
                try {
                    let innerTxt = match[1].trim();
                    // LLMが <tool_call> の内側にマークダウンを書式付けした対策等
                    innerTxt = innerTxt.replace(/```[a-z]*/gi, "").replace(/```/g, "");
                    innerTxt = innerTxt.replace(/[\u200B-\u200D\uFEFF]/g, ''); // ゼロ幅スペース等を除去
                    innerTxt = innerTxt.replace(/[\u201C\u201D\u201E\u201F\u2033\u2036]/g, '"'); // スマートクォートを直す
                    innerTxt = innerTxt.trim();
                    
                    const toolData = JSON.parse(innerTxt);
                    console.log(`[Verantyx Eye Agent] DETECTED Unified Tool Call: ${toolData.tool}`);
                    safeSendMessage({
                        type: "EXEC_UNIFIED_TOOL",
                        data: toolData
                    }, (response) => {
                        if (response && response.success && response.data.status === "success") {
                            injectTextToChat(`> ✅ [SYSTEM: Tool Executed] ${toolData.tool}\n\`\`\`\n${response.data.output}\n\`\`\`\n`);
                        } else {
                            injectTextToChat(`> ❌ [SYSTEM: Tool Error] ${toolData.tool} failed: ${response?.error || response?.data?.detail}\n\n`);
                        }
                    });
                } catch(e) {
                    console.error("Failed to parse tool call JSON", e);
                    let innerTxtSafe = "undefined";
                    try { innerTxtSafe = match[1].trim() } catch(e2) {}
                    injectTextToChat(`> ❌ [SYSTEM: Parse Error] Failed to parse tool call JSON inside <tool_call> tag.\nError: ${e.message}\nPayload:\n\`\`\`text\n${innerTxtSafe}\n\`\`\`\n\n`);
                }
            }
        }
        
        // 7. Web RPA Polling (Gemini <- Bridge)
        if (!activeWebTaskId && !isWaitingForResponseEnd) {
            safeSendMessage({ type: "PULL_PROMPT" }, (response) => {
                if (response && response.success && response.data.status === "success" && response.data.prompt) {
                    executePromptInject(response.data.task_id, response.data.prompt);
                }
            });
        }

    }, 1000);

    // --- Web RPA Execution Logic (Ported from verantyx_eye) ---
    let activeWebTaskId = null;
    let isWaitingForResponseEnd = false;

    function executePromptInject(taskId, promptText) {
        console.log(`%c[Verantyx Eye RPA] Injecting Prompt for Task: ${taskId}`, "color: #ffaa00; font-weight: bold;");
        activeWebTaskId = taskId;

        // あらゆるパターンの入力欄を網羅的に探索する強靭なセレクタ
        let editor = document.querySelector('rich-textarea p') 
                  || document.querySelector('[role="textbox"] p')
                  || document.querySelector('rich-textarea') 
                  || document.querySelector('[role="textbox"][contenteditable="true"]') 
                  || document.querySelector('textarea:not([hidden])');

        if (!editor) {
            console.error("[Verantyx Eye] Could not find the chat editor element.");
            activeWebTaskId = null;
            return;
        }

        // 確実なテキスト注入
        if (editor.tagName === 'TEXTAREA') {
            editor.value = promptText;
        } else {
            if (editor.tagName === 'RICH-TEXTAREA' && !editor.querySelector('p')) {
                editor.innerHTML = `<p>${promptText}</p>`;
            } else if (editor.tagName === 'RICH-TEXTAREA' && editor.querySelector('p')) {
                editor.querySelector('p').innerText = promptText;
            } else {
                editor.innerText = promptText;
            }
        }
        
        // React/Angularのフレームワークに文字が入ったことを強制認識させるイベント発火
        editor.dispatchEvent(new Event('input', { bubbles: true }));
        editor.dispatchEvent(new Event('change', { bubbles: true }));
        if (editor.parentElement) {
            editor.parentElement.dispatchEvent(new Event('input', { bubbles: true }));
        }

        // 送信ボタンのクリック処理（認識のラグを考慮して1.5秒待つ）
        setTimeout(() => {
            const buttons = Array.from(document.querySelectorAll('button'));
            const sendBtn = buttons.find(b => b.ariaLabel && 
                (b.ariaLabel.toLowerCase().includes('send') || 
                 b.ariaLabel.toLowerCase().includes('submit') || 
                 b.ariaLabel.toLowerCase().includes('message'))
            ) || document.querySelector('.send-button');

            if (sendBtn && !sendBtn.disabled) {
                sendBtn.click();
                isWaitingForResponseEnd = true;
                console.log("[Verantyx Eye RPA] Prompt Sent! Waiting for AI response...");
                
                // MutationObserverの代わりに、より確実なポーリングで完了状態を監視する
                checkResponseCompletion(taskId);
            } else {
                console.error("[Verantyx Eye] Could not find or click the Send button.");
                activeWebTaskId = null;
            }
        }, 1500);
    }

    function checkResponseCompletion(taskId) {
        let attempts = 0;
        let hasStartedGenerating = false;
        let lastTextLength = 0;
        let stableCount = 0;

        const checkInterval = setInterval(() => {
            attempts++;

            // 1. UIの生成中フラグを確認
            const stopBtn = Array.from(document.querySelectorAll('button')).find(
                b => b.ariaLabel && (
                    b.ariaLabel.toLowerCase().includes('stop') || 
                    b.ariaLabel.includes('停止') || 
                    b.ariaLabel.includes('回答を停止')
                )
            );
            const isGeneratingUi = !!document.querySelector('.generating-animation, [class*="generating"], .message-pending, [class*="streaming"]');
            const isGenerating = stopBtn || isGeneratingUi;

            if (isGenerating) {
                hasStartedGenerating = true; 
            }

            // 2. テキストが安定しているか（文字数が増えなくなってから3秒経過したか）を確認するためのフォールバック
            let currentTextLength = 0;
            const msgs = document.querySelectorAll('model-message, .model-response-text, .response-container, custom-message, message-content');
            if (msgs.length > 0) currentTextLength = (msgs[msgs.length - 1].innerText || "").length;
            
            if (currentTextLength > 0 && currentTextLength === lastTextLength) {
                stableCount++;
            } else {
                stableCount = 0;
            }
            lastTextLength = currentTextLength;

            // 【完了条件】生成開始後に非生成状態になった、もしくはテキストが連続3秒以上増えなくなった場合（フォールバック）
            if ((hasStartedGenerating && !isGenerating) || (attempts > 5 && stableCount >= 3)) {
                clearInterval(checkInterval);
                console.log("[Verantyx Eye RPA] Hit UI completion target or text stability. Waiting 1.5 seconds for DOM to settle...");
                setTimeout(() => {
                    extractAndSubmit(taskId);
                }, 1500);
            }

            if (attempts > 110) {
                clearInterval(checkInterval);
                console.error("[Verantyx Eye RPA] Generation timed out on browser side.");
                isWaitingForResponseEnd = false;
                activeWebTaskId = null;
            }
        }, 1000);
    }

    function extractAndSubmit(taskId) {
        // クライアントUI上の最下部のメッセージオブジェクト（モデルの回答全体を包むタグ）を取得
        // GeminiのUI構造に対応し、すべてのテキストを結合して取得する
        const messageContainers = document.querySelectorAll('model-message, .model-response-text, .response-container, custom-message, message-content');
        
        if (messageContainers.length > 0) {
            // 最下部にある親コンテナを優先的に探す
            let lastMessage = messageContainers[messageContainers.length - 1];
            
            // 親を遡ってモデルメッセージ全体を取得できた方が確実
            const parentModel = lastMessage.closest('model-message, [class*="response-container"]');
            if (parentModel) {
                lastMessage = parentModel;
            }

            const currentText = lastMessage.innerText || lastMessage.textContent;
            submitGeminiResponse(taskId, currentText);
        } else {
            console.error("[Verantyx Eye RPA] Unparseable DOM!");
            submitGeminiResponse(taskId, "Error: Could not extract message from Gemini DOM.");
        }
    }

    function submitGeminiResponse(taskId, text) {
        console.log(`%c[Verantyx Eye RPA] Submitting RPA Response for Task: ${taskId}`, "color: #ff00ff; font-weight: bold;");
        // ... (文字数をログに出して確認)
        console.log(`[Extracted Response Length: ${text.length} chars]`);
        
        safeSendMessage({ 
            type: "SUBMIT_RESPONSE", 
            data: { task_id: taskId, text: text } 
        }, (response) => {
            if (response && response.success) {
                console.log("[Verantyx Eye RPA] Successfully returned response to Bridge.");
                activeWebTaskId = null;
                isWaitingForResponseEnd = false;
            }
        });
    }

})();
