import json
import time
import sys
import os
import asyncio
from typing import List, Dict, Any
import tools as web_tools

class CliGeminiAgent:
    """
    Autonomous AI Agent that uses Verantyx Browser Limbs to navigate the web.
    """
    def __init__(self):
        self.context = []
        self.current_url = "about:blank"
        self.vision_cache = ""

    async def run(self, initial_goal: str):
        print(f"[*] Verantyx Neural Agent Starting...")
        print(f"[*] GOAL: {initial_goal}")
        
        # 1. Initial Vision
        self.vision_cache = await web_tools.browser_get_vision()
        
        while True:
            # In a real scenario, we'd send this to the Gemini API (LLM)
            # Here we simulate the reasoning loop
            
            print("\n" + "="*50)
            print(f"[*] CURRENT VIEWPORT ({self.current_url}):")
            print(self.vision_cache)
            print("="*50)
            
            # Milestone 1: Login Heuristic reasoning
            if "login.html" in self.current_url:
                print("[*] THOUGHT: I see a login form. I'll enter the credentials.")
                # We'd parse the [ID:X] from the [Top] and [Sidebar] vision markdown
                # For this demo, let's assume the agent scans for 'email' and 'password' labels
                
                # Assume ID 1 = email, ID 2 = password, ID 3 = login-btn
                print(f"[*] ACTION: Typing email into input...")
                await web_tools.browser_type(1, "demo-user@verantyx.com")
                print(f"[*] ACTION: Typing password into input...")
                await web_tools.browser_type(2, "secure-password-1234")
                print(f"[*] ACTION: Clicking 'Sign In' button...")
                await web_tools.browser_click(3)
                
                print("[*] SUCCESS: Milestone 1 Reached. Login initiated.")
                break

            elif "about:blank" in self.current_url:
                print("[*] THOUGHT: Navigating to the local login demonstration page.")
                local_path = f"file://{os.path.abspath('login.html')}"
                res = await web_tools.browser_navigate(local_path)
                print(f"[*] ACTION: Navigate -> {res}")
                self.current_url = "login.html"
            
            else:
                print("[*] THOUGHT: Goal reached or unknown state.")
                break

            # Update vision
            await asyncio.sleep(1)
            self.vision_cache = await web_tools.browser_get_vision()

if __name__ == "__main__":
    goal = sys.argv[1] if len(sys.argv) > 1 else "Login to Verantyx"
    agent = CliGeminiAgent()
    try:
        asyncio.run(agent.run(goal))
    except (KeyboardInterrupt, SystemExit):
        print("\n[*] Shutting down...")
    finally:
        web_tools.BrowserLimb().stop()
