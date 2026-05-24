import asyncio
import json
import logging
try:
    import websockets
except ImportError:
    import os
    os.system("pip3 install websockets")
    import websockets

logger = logging.getLogger("BrowserBridge")

class VerantyxBrowserBridge:
    """
    Python WebSocket client that bridges Gemini's logic engine directly
    into the Rust `vx-browser` CDP server on port 9222.
    """
    def __init__(self, port=9222):
        self.uri = f"ws://127.0.0.1:{port}"
        self.connection = None

    async def connect(self):
        try:
            self.connection = await websockets.connect(self.uri)
            logger.info(f"[*] Successfully connected to Verantyx Engine CDP at {self.uri}")
        except ConnectionRefusedError:
            logger.error("[!] Connection Refused. Is the Rust `verantyx-browser --bridge` engine running?")
            raise

    async def send_command(self, method: str, params: dict = None) -> dict:
        if not self.connection:
            raise RuntimeError("BrowserBridge is not connected.")

        payload = {
            "method": method,
            "params": params or {}
        }
        
        await self.connection.send(json.dumps(payload))
        
        # Wait for the parsed JSON response from Rust
        response = await self.connection.recv()
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return {"error": "Invalid JSON returned from engine", "raw": response}

    async def close(self):
        if self.connection:
            await self.connection.close()

# Example Autonomous Tool Endpoints for Gemini to Invoke
async def navigate(url: str):
    bridge = VerantyxBrowserBridge()
    await bridge.connect()
    res = await bridge.send_command("Browser.navigate", {"url": url})
    await bridge.close()
    return res

async def fetch_a11y_tree():
    bridge = VerantyxBrowserBridge()
    await bridge.connect()
    res = await bridge.send_command("DOM.getA11yTree")
    await bridge.close()
    return res
