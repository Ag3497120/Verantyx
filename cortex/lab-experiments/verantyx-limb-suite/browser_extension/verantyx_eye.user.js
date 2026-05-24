// ==UserScript==
// @name         Verantyx Eye: Gemini-to-Limb Bridge
// @namespace    http://tampermonkey.net/
// @version      3.1
// @description  Geminiの回答から不可視コマンドを検出し、ローカルのVerantyxサーバーに送信する
// @author       kofdai (Verantyx Project)
// @match        https://gemini.google.com/*
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// ==/UserScript==

(function() {
    'use strict';

    const BRIDGE_URL = 'http://127.0.0.1:8000/exec';
    console.log("%c[Verantyx Eye] Neural link established. Monitoring Gemini...", "color: #00ff00; font-weight: bold;");

    const hasInvisibleTrigger = (text) => text.includes('\u200B');

    // HTTPS(Gemini)から HTTP(ローカル)への通信を許可するため GM_xmlhttpRequest を使用
    function sendCommand(command, message = "") {
        console.log(`%c[Verantyx Eye] Dispatching command: ${command}`, "color: #00acee;");
        
        GM_xmlhttpRequest({
            method: "POST",
            url: BRIDGE_URL,
            headers: { "Content-Type": "application/json" },
            data: JSON.stringify({ command, message }),
            onload: function(response) {
                console.log("[Verantyx Eye] Server response:", response.responseText);
            },
            onerror: function(error) {
                console.error("[Verantyx Eye] Connection failed. Is bridge_server.py running?", error);
            }
        });
    }

    // --- Web RPA Execution Logic ---
    let activeWebTaskId = null;
    let isWaitingForResponseEnd = false;
    let responseTextBuffer = "";

    function pollPrompts() {
        if (activeWebTaskId || isWaitingForResponseEnd) return; // Busy

        GM_xmlhttpRequest({
            method: "GET",
            url: "http://127.0.0.1:8000/pull_prompt",
            onload: function(response) {
                try {
                    let data = JSON.parse(response.responseText);
                    if (data.status === "success" && data.prompt) {
                        executePromptInject(data.task_id, data.prompt);
                    }
                } catch(e) {}
            }
        });
    }

    function executePromptInject(taskId, promptText) {
        console.log(`%c[Verantyx Eye RPA] Injecting Prompt for Task: ${taskId}`, "color: #ffaa00; font-weight: bold;");
        activeWebTaskId = taskId;

        // Try to locate the text editor
        const editor = document.querySelector('rich-textarea p') || document.querySelector('.ql-editor p');
        if (!editor) {
            console.error("[Verantyx Eye] Could not find the chat editor element.");
            activeWebTaskId = null;
            return;
        }

        // Inject the text
        editor.innerText = promptText;
        editor.dispatchEvent(new Event('input', { bubbles: true }));
        editor.parentElement.dispatchEvent(new Event('input', { bubbles: true }));

        // Click the send button after a slight delay
        setTimeout(() => {
            // Find "Send" icon button
            const sendBtn = Array.from(document.querySelectorAll('button')).find(
                b => b.ariaLabel && (b.ariaLabel.toLowerCase().includes('send') || b.ariaLabel.toLowerCase().includes('submit'))
            ) || document.querySelector('.send-button');

            if (sendBtn && !sendBtn.disabled) {
                sendBtn.click();
                isWaitingForResponseEnd = true;
                console.log("[Verantyx Eye RPA] Prompt Sent! Waiting for AI response...");
            } else {
                console.error("[Verantyx Eye] Could not find or click the Send button.");
                activeWebTaskId = null;
            }
        }, 800);
    }

    function submitGeminiResponse(taskId, text) {
        console.log(`%c[Verantyx Eye RPA] Submitting RPA Response for Task: ${taskId}`, "color: #ff00ff; font-weight: bold;");
        GM_xmlhttpRequest({
            method: "POST",
            url: "http://127.0.0.1:8000/submit_gemini_response",
            headers: { "Content-Type": "application/json" },
            data: JSON.stringify({ task_id: taskId, text: text }),
            onload: function() {
                console.log("[Verantyx Eye RPA] Successfully returned response to Bridge.");
                activeWebTaskId = null;
                isWaitingForResponseEnd = false;
            }
        });
    }

    // --- Mutation Observer ---
    const observer = new MutationObserver((mutations) => {
        // 1. Invisible Command Trigger Handling
        const messages = document.querySelectorAll('.message-content, .model-response-text, .response-container');
        if (messages.length > 0) {
            const lastMessage = messages[messages.length - 1];

            if (!lastMessage.dataset.verantyxProcessed) {
                const content = lastMessage.innerText || lastMessage.textContent;

                if (hasInvisibleTrigger(content)) {
                    sendCommand("VIBRATE_V", "Invisible trigger detected");
                }

                const cmdMatch = content.match(/VX_CMD:([A-Z_]+)/);
                if (cmdMatch) {
                    sendCommand(cmdMatch[1], "Visible command detected");
                }
                
                // Do NOT mark as processed immediately if we are waiting for RPA completion
                if (!isWaitingForResponseEnd) {
                   lastMessage.dataset.verantyxProcessed = "true";
                }
            }
            
            // 2. Web RPA Completion Handling (Look for "Stop Generating" to disappear)
            if (isWaitingForResponseEnd && activeWebTaskId) {
                const stopBtn = Array.from(document.querySelectorAll('button')).find(
                    b => b.ariaLabel && b.ariaLabel.toLowerCase().includes('stop generating')
                );
                
                // Check if the stream has finished and the UI settled
                // Also ensure there is some text in the last message
                const currentText = lastMessage.innerText || lastMessage.textContent;
                
                if (!stopBtn && currentText.trim().length > 5 && !document.querySelector('.generating-animation')) {
                    // It settled!
                    submitGeminiResponse(activeWebTaskId, currentText);
                    lastMessage.dataset.verantyxProcessed = "true";
                }
            }
        }
    });

    observer.observe(document.body, { childList: true, subtree: true });
    
    // Start Poller
    setInterval(pollPrompts, 1500);

})();
