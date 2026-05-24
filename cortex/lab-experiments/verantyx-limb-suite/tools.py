import subprocess
import glob as pyglob
import re
from pathlib import Path
import json
import threading
import queue
import time

WORKSPACE = Path("/Users/motonishikoudai")

def safe_path(p: str) -> Path:
    rp = Path(p).expanduser().resolve()
    # No strict jail to keep flexibility, or jail to WORKSPACE
    return rp

def bash_tool(command: str) -> str:
    # Danger warning could be handled at server level
    try:
        res = subprocess.run(command, shell=True, cwd=str(WORKSPACE), capture_output=True, text=True, timeout=120)
        return (res.stdout + "\n" + res.stderr).strip() or "Command executed successfully (no output)."
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 120s."
    except Exception as e:
        return f"Error: {e}"

def file_read_tool(path: str, start_line: int = None, end_line: int = None) -> str:
    try:
        p = safe_path(path)
        if not p.is_file(): return "Error: File not found."
        lines = p.read_text("utf-8").splitlines()
        
        # Blind Gatekeeper Logic (VFS Limit)
        max_lines_allowed = 500
        
        s = max(0, start_line - 1) if start_line else 0
        e = min(len(lines), end_line) if end_line else len(lines)
        
        # Enforce reading limits
        if (e - s) > max_lines_allowed:
            e = s + max_lines_allowed
            subset = lines[s:e]
            return "\n".join(subset) + f"\n\n[システム警告: ファイルが長すぎるため、最初の{max_lines_allowed}行だけを表示しました。続きは start_line と end_line を使って読み取ってください。総行数: {len(lines)}行]"
        
        subset = lines[s:e]
        return "\n".join(subset)
    except Exception as e:
        return f"Error: {e}"

def file_edit_tool(path: str, search: str, replace: str) -> str:
    try:
        p = safe_path(path)
        if not p.is_file(): return "Error: File not found."
        content = p.read_text("utf-8")
        if search not in content:
            return "Error: EXACT search string not found in file. Check whitespace and context."
        
        new_content = content.replace(search, replace, 1)
        p.write_text(new_content, "utf-8")
        return f"Successfully edited {path}."
    except Exception as e:
        return f"Error: {e}"

def glob_tool(pattern: str) -> str:
    try:
        from glob import glob
        import os
        old = os.getcwd()
        os.chdir(str(WORKSPACE))
        res = glob(pattern, recursive=True)
        os.chdir(old)
        return "\n".join(res[:100]) or "No matches found."
    except Exception as e:
        return f"Error: {e}"

def grep_tool(pattern: str, path: str = ".") -> str:
    try:
        res = subprocess.run(["rg", "-n", pattern, path], cwd=str(WORKSPACE), capture_output=True, text=True, timeout=30)
        return res.stdout.strip() or "No matches found."
    except Exception as e:
        # Fallback if rg not installed
        res = subprocess.run(["grep", "-rnE", pattern, path], cwd=str(WORKSPACE), capture_output=True, text=True, timeout=30)
        return res.stdout.strip() or "No matches found."

def memory_search_tool(query: str) -> str:
    try:
        from spatial_engine import MEMORY_ROOT
        mid_dir = MEMORY_ROOT / "mid"
        deep_dir = MEMORY_ROOT / "deep"
        matches = []
        for d in [mid_dir, deep_dir]:
            if not d.exists(): continue
            for file in d.rglob("*.md"):
                content = file.read_text("utf-8")
                if query.lower() in content.lower():
                    matches.append(f"--- [MEMORY FOUND IN {d.name.upper()}: {file.name}] ---\n{content}\n")
        
        return "\n".join(matches) or f"No memories found matching query: {query}"
    except Exception as e:
        return f"Error: {e}"

def memory_write_tool(title: str, content: str, zone: str = "near") -> str:
    try:
        from spatial_engine import _ensure_structure, MEMORY_ROOT
        if zone not in ["front", "near", "mid", "deep"]:
            return "Error: Invalid zone. Select from 'front', 'near', 'mid', 'deep'."
        _ensure_structure()
        filename = title.replace(" ", "_").lower()
        if not filename.endswith(".md"): filename += ".md"
        
        filepath = MEMORY_ROOT / zone / filename
        filepath.write_text(content, "utf-8")
        return f"Successfully saved memory to {zone}/{filename}."
    except Exception as e:
        return f"Error: {e}"
class BrowserLimb:
    """
    Hands and Feet for the AI: Controls the Rust verantyx-browser engine.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(BrowserLimb, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized: return
        self.process = None
        self.stdout_queue = queue.Queue()
        self.stderr_queue = queue.Queue()
        self.browser_path = Path("/Users/motonishikoudai/verantyx-cli/verantyx-browser/target/debug/verantyx-browser")
        self._initialized = True

    def ensure_started(self):
        import asyncio
        if self.process and self.process.poll() is None:
            return
        
        print(f"[*] Starting Verantyx Browser Engine at {self.browser_path}...")
        self.process = subprocess.Popen(
            [str(self.browser_path), "--bridge"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(self.browser_path.parent.parent)
        )
        time.sleep(2) # Allow CDP Server to bind

    def _reader(self, pipe, q):
        for line in iter(pipe.readline, ''):
            q.put(line)

    async def execute(self, method: str, params: dict):
        self.ensure_started()
        from browser_bridge import VerantyxBrowserBridge
        bridge = VerantyxBrowserBridge()
        await bridge.connect()
        res = await bridge.send_command(method, params)
        await bridge.close()
        return res

    def stop(self):
        if self.process:
            self.process.terminate()
            self.process = None

# Global Instance
_limb = BrowserLimb()

async def browser_navigate(url: str) -> str:
    res = await _limb.execute("Browser.navigate", {"url": url})
    return f"Navigated to {url}. Network State: {res}"

async def browser_click(element_id: int) -> str:
    res = await _limb.execute("DOM.click", {"id": element_id})
    return f"Clicked element {element_id}. State: {res}"

async def browser_type(element_id: int, text: str) -> str:
    res = await _limb.execute("DOM.type", {"id": element_id, "text": text})
    return f"Typed '{text}'. State: {res}"

async def browser_get_vision() -> str:
    res = await _limb.execute("DOM.getA11yTree", {})
    return f"A11Y TENSOR VISION:\n{json.dumps(res, indent=2)}"
