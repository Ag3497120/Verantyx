// background.js

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.type === "SEND_COMMAND") {
        fetch(request.url, {
            method: request.method,
            headers: request.headers,
            body: request.body
        })
        .then(response => response.json())
        .then(data => sendResponse({ success: true, data: data }))
        .catch(error => sendResponse({ success: false, error: error.toString() }));
        return true; 
    }
    
    if (request.type === "READ_FILE") {
        fetch(`http://127.0.0.1:8000/file_read?path=${encodeURIComponent(request.path)}`)
        .then(response => response.json())
        .then(data => sendResponse({ success: true, data: data }))
        .catch(error => sendResponse({ success: false, error: error.toString() }));
        return true;
    }

    if (request.type === "EXEC_FILE_EDIT") {
        fetch('http://127.0.0.1:8000/file_edit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                path: request.data.path,
                search: request.data.search,
                replace: request.data.replace
            })
        })
        .then(response => response.json())
        .then(data => sendResponse({ success: true, data: data }))
        .catch(error => sendResponse({ success: false, error: error.toString() }));
        return true;
    }

    // 新規: JCrossシミュレーションパケット中継
    if (request.type === "EXEC_JCROSS_SIM") {
        fetch('http://127.0.0.1:8000/jcross_sim', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                sim_data: request.data.sim_data
            })
        })
        .then(response => response.json())
        .then(data => sendResponse({ success: true, data: data }))
        .catch(error => sendResponse({ success: false, error: error.toString() }));
        return true;
    }

    // 新規: External Brain Execution中継
    if (request.type === "EXEC_BRAIN") {
        fetch('http://127.0.0.1:8000/exec_brain', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                command: request.data.command
            })
        })
        .then(response => response.json())
        .then(data => sendResponse({ success: true, data: data }))
        .catch(error => sendResponse({ success: false, error: error.toString() }));
        return true;
    }

    // 新規: Unified Tool Call 中継 (claw-code 互換)
    if (request.type === "EXEC_UNIFIED_TOOL") {
        fetch('http://127.0.0.1:8000/execute_tool', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(request.data)
        })
        .then(response => response.json())
        .then(data => sendResponse({ success: true, data: data }))
        .catch(error => sendResponse({ success: false, error: error.toString() }));
        return true;
    }

    // 新規: Web RPA用のプロンプトポーリング
    if (request.type === "PULL_PROMPT") {
        fetch('http://127.0.0.1:8000/pull_prompt')
        .then(response => response.json())
        .then(data => sendResponse({ success: true, data: data }))
        .catch(error => sendResponse({ success: false, error: error.toString() }));
        return true;
    }

    // 新規: Web RPA用の回答送信
    if (request.type === "SUBMIT_RESPONSE") {
        fetch('http://127.0.0.1:8000/submit_gemini_response', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                task_id: request.data.task_id,
                text: request.data.text
            })
        })
        .then(response => response.json())
        .then(data => sendResponse({ success: true, data: data }))
        .catch(error => sendResponse({ success: false, error: error.toString() }));
        return true;
    }
});
