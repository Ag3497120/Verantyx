# bridge_server.py

import uvicorn
import os
import json
import uuid
import asyncio
import subprocess
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any

import tools as web_tools

from verantyx.haptic.bridge import send_haptic_to_iphone
from verantyx.core.types import HapticPattern
from verantyx.config.settings import settings

app = FastAPI(title="Verantyx Neural Bridge - JCross Edition")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

active_websockets: List[WebSocket] = []
WORKSPACE_ROOT = Path("/Users/motonishikoudai/verantyx-cli").resolve()
pending_edits: Dict[str, asyncio.Future] = {}

pending_prompts: List[Dict[str, str]] = []
prompt_futures: Dict[str, asyncio.Future] = {}

def resolve_safe_path(target_path: str) -> Path:
    p = (WORKSPACE_ROOT / target_path).resolve()
    if not str(p).startswith(str(WORKSPACE_ROOT)):
        raise HTTPException(status_code=403, detail="Access denied: Path outside workspace")
    return p

class CommandRequest(BaseModel):
    command: str
    message: str = ""

class FileEditRequest(BaseModel):
    path: str
    search: str
    replace: str

class JCrossRequest(BaseModel):
    sim_data: str

class SubprocessRequest(BaseModel):
    command: str

class WebPromptRequest(BaseModel):
    prompt: str
    task_id: str = ""

class WebResponseRequest(BaseModel):
    task_id: str
    text: str

class UnifiedToolRequest(BaseModel):
    tool: str
    parameters: Dict[str, Any] = {}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.append(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "EDIT_RESPONSE":
                    task_id = msg.get("task_id")
                    decision = msg.get("decision")
                    if task_id in pending_edits:
                        pending_edits[task_id].set_result(decision)
            except Exception:
                pass
    except WebSocketDisconnect:
        active_websockets.remove(websocket)

@app.post("/exec")
async def execute_command(req: CommandRequest):
    cmd = req.command.upper()
    print(f"[*] Received command: {cmd}")
    try:
        msg_str = json.dumps({"type": "COMMAND", "cmd": cmd})
        for ws in active_websockets:
            await ws.send_text(msg_str)
        return {"status": "success", "executed": cmd}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/file_read")
async def read_file(path: str):
    print(f"[*] Reading file: {path}")
    try:
        safe_path = resolve_safe_path(path)
        if not safe_path.exists() or not safe_path.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        content = safe_path.read_text(encoding="utf-8")
        return {"status": "success", "content": content}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/jcross_sim")
async def jcross_sim(req: JCrossRequest):
    print("[*] JCross Simulation Data incoming...")
    try:
        msg = {
            "type": "JCROSS_SIM",
            "payload": req.sim_data
        }
        for ws in active_websockets:
            await ws.send_text(json.dumps(msg))
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ask_web_gemini")
async def ask_web_gemini(req: WebPromptRequest):
    task_id = str(uuid.uuid4())
    future = asyncio.get_event_loop().create_future()
    prompt_futures[task_id] = future
    
    pending_prompts.append({
        "task_id": task_id,
        "prompt": req.prompt
    })
    
    print(f"[*] Dispatching prompt to Web Gemini RPA [{task_id}]...")
    try:
        response_text = await asyncio.wait_for(future, timeout=120.0)
        return {"status": "success", "text": response_text}
    except asyncio.TimeoutError:
        if task_id in prompt_futures:
            del prompt_futures[task_id]
        print(f"[!] Web Gemini Prompt TIMEOUT [{task_id}]")
        raise HTTPException(status_code=408, detail="Web Gemini did not respond in time.")

@app.get("/pull_prompt")
async def pull_prompt():
    if pending_prompts:
        prompt = pending_prompts.pop(0)
        return {"status": "success", "task_id": prompt["task_id"], "prompt": prompt["prompt"]}
    return {"status": "empty"}

@app.post("/submit_gemini_response")
async def submit_gemini_response(req: WebResponseRequest):
    print(f"[*] Received fully typed response from Web Gemini [{req.task_id}]")
    if req.task_id in prompt_futures:
        prompt_futures[req.task_id].set_result(req.text)
        del prompt_futures[req.task_id]
        return {"status": "success"}
    else:
        raise HTTPException(status_code=404, detail="Task ID not found or already resolved.")

@app.post("/execute_tool")
async def execute_tool(req: UnifiedToolRequest):
    print(f"[*] Executing Unified Tool: {req.tool}")
    try:
        if req.tool == "BashTool":
            command = req.parameters.get("command", "")
            output = web_tools.bash_tool(command)
        elif req.tool == "FileReadTool":
            path = req.parameters.get("path", "")
            start = req.parameters.get("start_line")
            end = req.parameters.get("end_line")
            output = web_tools.file_read_tool(path, start, end)
        elif req.tool == "FileEditTool":
            path = req.parameters.get("path", "")
            search = req.parameters.get("search", "")
            replace = req.parameters.get("replace", "")
            output = web_tools.file_edit_tool(path, search, replace)
        elif req.tool == "GlobTool":
            pattern = req.parameters.get("pattern", "")
            output = web_tools.glob_tool(pattern)
        elif req.tool == "GrepTool":
            pattern = req.parameters.get("pattern", "")
            path = req.parameters.get("path", ".")
            output = web_tools.grep_tool(pattern, path)
        elif req.tool == "MemorySearchTool":
            query = req.parameters.get("query", "")
            output = web_tools.memory_search_tool(query)
        elif req.tool == "MemoryWriteTool":
            title = req.parameters.get("title", "Untitled")
            content = req.parameters.get("content", "")
            zone = req.parameters.get("zone", "near")
            output = web_tools.memory_write_tool(title, content, zone)
        elif req.tool == "BrowserNavigateTool":
            url = req.parameters.get("url", "")
            output = web_tools.browser_navigate(url)
        elif req.tool == "BrowserClickTool":
            id = req.parameters.get("id", 0)
            output = web_tools.browser_click(id)
        elif req.tool == "BrowserTypeTool":
            id = req.parameters.get("id", 0)
            text = req.parameters.get("text", "")
            output = web_tools.browser_type(id, text)
        elif req.tool == "BrowserVisionTool":
            output = web_tools.browser_get_vision()
        else:
            raise HTTPException(status_code=400, detail=f"Unknown Tool: {req.tool}")
            
        return {"status": "success", "output": output}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/file_edit")
async def edit_file(req: FileEditRequest):
    print(f"[*] Editing file: {req.path}")
    try:
        safe_path = resolve_safe_path(req.path)
        if not safe_path.exists() or not safe_path.is_file():
            raise HTTPException(status_code=404, detail="File not found")

        content = safe_path.read_text(encoding="utf-8")
        if req.search not in content:
            raise HTTPException(status_code=400, detail="Search block not found in file. Ensure exact match.")

        task_id = str(uuid.uuid4())
        future = asyncio.get_event_loop().create_future()
        pending_edits[task_id] = future

        approval_msg = {
            "type": "APPROVAL_REQUEST",
            "task_id": task_id,
            "path": req.path,
            "search": req.search,
            "replace": req.replace
        }
        
        for ws in active_websockets:
            await ws.send_text(json.dumps(approval_msg))
            
        try:
            print(f"[*] WAITING FOR HUMAN APPROVAL on iPhone (task: {task_id})...")
            decision = await asyncio.wait_for(future, timeout=60.0)
        except asyncio.TimeoutError:
            del pending_edits[task_id]
            raise HTTPException(status_code=408, detail="Approval timed out")

        del pending_edits[task_id]

        if decision != "APPROVE":
            print(f"[!] Edit DENIED by Human for {req.path}")
            raise HTTPException(status_code=403, detail="Edit rejected by human")

        print(f"[*] APPROVED! Overwriting {req.path}")
        new_content = content.replace(req.search, req.replace, 1)
        safe_path.write_text(new_content, encoding="utf-8")
        
        success_msg = {"type": "COMMAND", "cmd": "VIBRATE_SUCCESS"}
        for ws in active_websockets:
            await ws.send_text(json.dumps(success_msg))

        return {"status": "success", "message": f"Successfully updated {req.path}"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/exec_brain")
async def exec_brain(req: SubprocessRequest):
    print(f"[*] External Brain RCE Request: {req.command}")
    try:
        if not req.command.startswith("python3 "):
            raise HTTPException(status_code=403, detail="Only 'python3' commands are permitted.")
        
        allowed_dirs = [
            str(WORKSPACE_ROOT),
            "/Users/motonishikoudai/verantyx_v6/arc-agi-3/ARC-AGI-3-Agents"
        ]
        
        args = req.command.split(" ")
        
        # どんなに不要な日本語やゴミが末尾にくっついてきても、強制的に拡張子で切断する
        if ".py" in args[1]:
            args[1] = args[1][:args[1].index(".py") + 3]
        elif ".sh" in args[1]:
            args[1] = args[1][:args[1].index(".sh") + 3]
        
        target_file = args[1]
        target_path = Path(target_file).expanduser().resolve()
        # チルダ(~)をsubprocessは展開しないため、絶対パスで上書きする
        args[1] = str(target_path)
        
        safe = False
        for ad in allowed_dirs:
            if str(target_path).startswith(ad):
                safe = True
                break
                
        if not safe:
            raise HTTPException(status_code=403, detail="Execution target is outside the safe sandbox.")
            
        working_dir = target_path.parent
        # ARC-AGI-3 などの専用環境 (.venv) があれば、システムのPythonではなくそちらを使う
        venv_python = working_dir / ".venv" / "bin" / "python"
        if args[0] in ["python", "python3"] and venv_python.exists():
            args[0] = str(venv_python)
            
        print(f"[*] Executing Command Sandbox [{req.command}] in [{working_dir}]...")
        result = subprocess.run(args, cwd=str(working_dir), capture_output=True, text=True, timeout=120)
        
        stdout_txt = result.stdout or ""
        stderr_txt = result.stderr or ""
        
        combined = ""
        if stdout_txt: combined += f"[STDOUT]\n{stdout_txt}\n"
        if stderr_txt: combined += f"[STDERR]\n{stderr_txt}\n"
        if not combined: combined = "[No Output]"
        
        return {"status": "success", "output": combined, "exit_code": result.returncode}
        
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail="Script execution timed out (Limit 120s)")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

html_content = """
<!DOCTYPE html>
<html>
<head>
    <title>Verantyx Neural Control</title>
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=0">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <style>
        body { background-color: #050505; color: #00ff00; font-family: monospace; display: flex; flex-direction: column; align-items: center; justify-content: flex-start; height: 100vh; margin: 0; padding: 20px; box-sizing: border-box; transition: background-color 0.1s; overflow: hidden; }
        #status { font-size: 1.2em; margin-bottom: 20px; text-shadow: 0 0 10px #00ff00; text-align: center; }
        .btn-connect { background: #00ff00; color: #000; border: none; padding: 20px 40px; font-size: 1.2em; font-weight: bold; cursor: pointer; border-radius: 5px; box-shadow: 0 0 20px #00ff00; margin-top: 50px; }
        .btn-connect:active { transform: scale(0.95); }
        .log-container { margin-top: 20px; width: 100%; flex-grow: 1; overflow-y: auto; border: 1px dashed #00ff00; padding: 10px; opacity: 0.8; font-size: 0.8em; margin-bottom: 20px; }
        .log { margin: 5px 0; border-bottom: 1px dotted #004400; padding-bottom: 2px; }
        
        #modal, #jcross-modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.9); z-index: 1000; flex-direction: column; align-items: center; justify-content: center; padding: 20px; box-sizing: border-box; backdrop-filter: blur(5px); }
        .modal-content { background: #111; border: 2px solid #00ff00; padding: 20px; border-radius: 10px; width: 100%; max-width: 500px; box-shadow: 0 0 30px #005500; }
        .modal-title { font-size: 1.2em; margin-bottom: 10px; color: #ff0055; text-shadow: 0 0 10px #ff0055; font-weight: bold; text-align: center; }
        
        /* Edit Modal Specifics */
        .diff-box { background: #000; padding: 10px; margin: 10px 0; border: 1px solid #333; height: 150px; overflow-y: auto; font-size: 0.8em; white-space: pre-wrap; word-wrap: break-word; }
        .diff-search { color: #ff5555; }
        .diff-replace { color: #55ff55; }
        .btn-row { display: flex; justify-content: space-between; margin-top: 20px; }
        .btn-approve { background: #00ff00; color: #000; padding: 15px; font-weight: bold; border: none; border-radius: 5px; flex-grow: 1; margin-right: 10px; cursor:pointer;}
        .btn-deny { background: #ff0055; color: #fff; padding: 15px; font-weight: bold; border: none; border-radius: 5px; cursor:pointer; width: 100px; }
        
        /* JCross Live Monitor Specifics */
        #jcross-modal .modal-content { border-color: #0088ff; box-shadow: 0 0 40px #004488; background: #0a1128; }
        #jcross-modal .modal-title { color: #00aaff; text-shadow: 0 0 15px #00aaff; font-family: 'Courier New', Courier, monospace; letter-spacing: 2px;}
        .jcross-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(80px, 1fr)); gap: 8px; margin-top: 15px; max-height: 50vh; overflow-y: auto; padding-right: 5px;}
        .jcell { padding: 15px 5px; text-align: center; font-size: 0.75em; font-weight: bold; border-radius: 4px; color: #000; text-transform: uppercase; word-break: break-all; box-shadow: inset 0 0 10px rgba(255,255,255,0.2); animation: pulse 2s infinite alternate;}
        .jcell.safe { background-color: #00ff00; box-shadow: 0 0 15px #00ff00; }
        .jcell.alert { background-color: #ff0000; color: #fff; box-shadow: 0 0 20px #ff0000; font-weight: 900; animation: blink 0.5s infinite alternate; }
        .jcell.impact { background-color: #ffaa00; box-shadow: 0 0 15px #ffaa00; }
        .jcell.unknown { background-color: #444; color: #aaa; border: 1px dashed #888; box-shadow: none; animation: none;}
        
        .btn-ack { background: #00aaff; color: #000; padding: 15px; width: 100%; font-weight: bold; border: none; border-radius: 5px; cursor:pointer; margin-top: 20px; box-shadow: 0 0 15px #00aaff;}
        .btn-ack:active { transform: scale(0.95); }

        @keyframes pulse { from { opacity: 0.8; } to { opacity: 1; } }
        @keyframes blink { from { opacity: 0.4; } to { opacity: 1; } }
    </style>
</head>
<body>
    <div id="status">AWAITING NEURAL SYNC<br><span style="font-size: 0.5em; opacity: 0.7;">(Tap to activate PWA)</span></div>
    <button class="btn-connect" id="connectBtn">ACTIVATE LINK</button>
    <div class="log-container" id="logs"></div>

    <!-- File Edit Modal -->
    <div id="modal">
        <div class="modal-content">
            <div class="modal-title">⚠️ AGENT OVERRIDE REQUEST</div>
            <div style="font-size: 0.9em; margin-bottom: 5px;">File modification request:</div>
            <div id="modal-path" style="color: #ffcc00; font-weight: bold; font-size: 0.9em; margin-bottom: 10px; word-break: break-all;"></div>
            
            <div style="font-size: 0.8em;">SEARCH (-):</div>
            <div class="diff-box diff-search" id="modal-search"></div>
            
            <div style="font-size: 0.8em;">REPLACE (+):</div>
            <div class="diff-box diff-replace" id="modal-replace"></div>
            
            <div class="btn-row">
                <button class="btn-approve" id="btnApprove">APPROVE EDIT</button>
                <button class="btn-deny" id="btnDeny">DENY</button>
            </div>
        </div>
    </div>

    <!-- JCross Tactical Grid Modal -->
    <div id="jcross-modal">
        <div class="modal-content">
            <div class="modal-title">🌐 JCROSS TACTICAL MONITOR</div>
            <div style="font-size: 0.8em; color: #aaa; text-align: center; margin-bottom: 10px;">Live Code Impact Simulation Engine</div>
            <div class="jcross-grid" id="jcross-grid-container">
                <!-- Cells injected dynamically here -->
            </div>
            <button class="btn-ack" id="btnJCrossAck">ACKNOWLEDGE (DISMISS)</button>
        </div>
    </div>

    <script>
        const connectBtn = document.getElementById('connectBtn');
        const statusEl = document.getElementById('status');
        const logsEl = document.getElementById('logs');
        const modal = document.getElementById('modal');
        const jcrossModal = document.getElementById('jcross-modal');
        const jcrossGrid = document.getElementById('jcross-grid-container');
        
        let ws;
        let audioCtx;
        let pendingTaskId = null;

        function log(msg) {
            const d = document.createElement('div');
            d.className = 'log';
            d.innerText = `[${new Date().toLocaleTimeString('en-US', {hour12:false})}] ${msg}`;
            logsEl.prepend(d);
        }

        function playHapticBeep(durations, freq = 300, type = 'square') {
            if (!audioCtx) return;
            let time = audioCtx.currentTime;
            durations.forEach(d => {
                if (d > 0) {
                    const osc = audioCtx.createOscillator();
                    const gain = audioCtx.createGain();
                    osc.type = type; 
                    osc.frequency.setValueAtTime(freq, time);
                    osc.connect(gain);
                    gain.connect(audioCtx.destination);
                    osc.start(time);
                    gain.gain.setValueAtTime(0, time);
                    gain.gain.linearRampToValueAtTime(1, time + 0.01);
                    gain.gain.exponentialRampToValueAtTime(0.01, time + (d/1000));
                    osc.stop(time + (d/1000));
                }
                time += Math.abs(d) / 1000 + 0.1; 
            });
        }

        function triggerVisual(color) {
            document.body.style.backgroundColor = color;
            document.body.style.boxShadow = `inset 0 0 50px ${color}`;
            setTimeout(() => {
                document.body.style.backgroundColor = '#050505';
                document.body.style.boxShadow = 'none';
            }, 150);
        }

        connectBtn.addEventListener('click', () => {
            audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            const osc = audioCtx.createOscillator();
            osc.connect(audioCtx.destination);
            osc.start(0); osc.stop(0);

            connectBtn.style.display = 'none';
            statusEl.innerHTML = 'NEURAL LINK ACTIVE<br><span style="font-size: 0.5em; opacity:0.7;">Human-in-the-Loop Protocol</span>';
            log('Audio & Haptics Engaged.');
            triggerVisual('#00ff00');
            
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = protocol + '//' + window.location.host + '/ws';
            
            ws = new WebSocket(wsUrl);
            ws.onopen = () => { log('Websocket Connected.'); playHapticBeep([50]); };
            ws.onclose = () => { 
                log('ERROR: Connection Lost.'); 
                statusEl.innerHTML = 'LINK LOST<br><span style="font-size: 0.5em; opacity: 0.7;">Refresh to reconnect.</span>';
                statusEl.style.color = '#ff0000'; 
            };
            
            ws.onmessage = (event) => {
                let msg;
                try {
                    msg = JSON.parse(event.data);
                } catch(e) {
                    msg = { type: "COMMAND", cmd: event.data };
                }
                
                if (msg.type === "COMMAND") {
                    const cmd = msg.cmd;
                    log('COMMAND: ' + cmd);
                    if (cmd === 'VIBRATE_V') { playHapticBeep([100, 100, 100, 400]); triggerVisual('#00ff00'); }
                    else if (cmd === 'VIBRATE_SUCCESS') { playHapticBeep([250]); triggerVisual('#0088ff'); }
                    else if (cmd === 'VIBRATE_ALERT') { playHapticBeep([100,-50,100,-50,100]); triggerVisual('#ff0000'); setTimeout(()=>triggerVisual('#ff0000'), 200); }
                    else if (cmd === 'VIBRATE_APPROVAL') { playHapticBeep([200,-100,200]); triggerVisual('#ffff00'); }
                } 
                else if (msg.type === "APPROVAL_REQUEST") {
                    log('OVERRIDE DETECTED >> Awaiting Approval');
                    playHapticBeep([200, -50, 200, -50, 400]); 
                    triggerVisual('#ff0055');
                    
                    document.getElementById('modal-path').innerText = msg.path;
                    document.getElementById('modal-search').innerText = msg.search;
                    document.getElementById('modal-replace').innerText = msg.replace;
                    pendingTaskId = msg.task_id;
                    modal.style.display = "flex";
                }
                else if (msg.type === "JCROSS_SIM") {
                    log('JCROSS TACTICAL SIMULATION INCOMING >> Pabuuuuu!!!');
                    // Futuristic sweeping beep for JCross Grid
                    playHapticBeep([50, 50, 50, 50, 50, 50, 200], 800, 'sawtooth');
                    triggerVisual('#0088ff');
                    
                    renderJCrossGrid(msg.payload);
                    jcrossModal.style.display = "flex";
                }
            };
        });

        // Parse JCross text block and generate CSS Grid Cells
        function renderJCrossGrid(textContent) {
            jcrossGrid.innerHTML = "";
            const lines = textContent.split('\\n');
            let hasAlert = false;
            
            lines.forEach(line => {
                const text = line.trim();
                if (!text) return;
                
                const cell = document.createElement('div');
                cell.className = 'jcell';
                
                const upperText = text.toUpperCase();
                if (upperText.includes('SAFE') || upperText.includes('GREEN') || upperText.includes('OKAY')) {
                    cell.classList.add('safe');
                } 
                else if (upperText.includes('ALERT') || upperText.includes('RED') || upperText.includes('FAIL') || upperText.includes('ERROR')) {
                    cell.classList.add('alert');
                    hasAlert = true;
                }
                else if (upperText.includes('IMPACT') || upperText.includes('YELLOW') || upperText.includes('WARN')) {
                    cell.classList.add('impact');
                }
                else {
                    cell.classList.add('unknown');
                }
                
                // If text contains colon "Module: SAFE", render beautifully
                if (text.includes(':')) {
                    const parts = text.split(':');
                    cell.innerHTML = `<div>${parts[0].trim()}</div><div style="font-size:1.5em;margin-top:5px;">${parts[1].trim()}</div>`;
                } else {
                    cell.innerText = text.length > 20 ? text.substring(0,20)+"..." : text;
                }
                
                jcrossGrid.appendChild(cell);
            });
            
            if (hasAlert) {
                // Flash red rapidly if there's an alert block
                triggerVisual('#ff0000'); setTimeout(()=>triggerVisual('#ff0000'), 200);
            }
        }

        document.getElementById('btnJCrossAck').addEventListener('click', () => {
             log("JCROSS MONITOR DISMISSED");
             playHapticBeep([100], 500);
             jcrossModal.style.display = "none";
        });

        document.getElementById('btnApprove').addEventListener('click', () => {
            if (ws && pendingTaskId) {
                ws.send(JSON.stringify({ type: "EDIT_RESPONSE", task_id: pendingTaskId, decision: "APPROVE" }));
                log("APPROVAL SENT");
            }
            modal.style.display = "none";
            pendingTaskId = null;
        });

        document.getElementById('btnDeny').addEventListener('click', () => {
            if (ws && pendingTaskId) {
                ws.send(JSON.stringify({ type: "EDIT_RESPONSE", task_id: pendingTaskId, decision: "DENY" }));
                log("DENIAL SENT");
            }
            modal.style.display = "none";
            pendingTaskId = null;
        });
    </script>
</body>
</html>
"""

@app.get("/pwa")
async def get_pwa():
    return HTMLResponse(content=html_content)

@app.get("/health")
async def health_check():
    return {"status": "online"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
