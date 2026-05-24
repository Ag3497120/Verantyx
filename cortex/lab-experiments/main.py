# main.py

import json
import asyncio
import subprocess
import sys
import os
import atexit
import google.generativeai as genai
from verantyx.config.settings import settings
from verantyx.brain.tools import VERANTYX_TOOLS
from verantyx.brain.dispatcher import BrainDispatcher
from verantyx.core.types import HapticPattern

# 1. Gemini の初期化
genai.configure(api_key=settings.GEMINI_API_KEY)
model = genai.GenerativeModel(
    model_name="gemini-2.5-pro", # 2026年最新モデル
    tools=VERANTYX_TOOLS
)

async def verantyx_main_loop():
    dispatcher = BrainDispatcher()
    chat = model.start_chat(enable_automatic_function_calling=False)
    
    print("🚀 Verantyx Engine v3.0 Started.")
    print("[*] Stealth Mode:", "ENABLED" if settings.STEALTH_MODE else "DISABLED")
    
    # 起動通知（iPhoneへモールス信号 V を送信）
    await dispatcher.dispatch_manual("notify_haptic", {"pattern": "morse_v", "message": "Verantyx Booted"})

    while True:
        try:
            user_input = input("\n[User] > ")
        except EOFError:
            break

        if user_input.lower() in ["exit", "quit"]:
            break

        # AIの思考プロセス開始
        response = chat.send_message(user_input)

        # AIが「手足（ツール）」を使いたいと言っている間、ループを回す
        # Note: Google SDKのレスポンス形式に応じて適切に処理
        while response.candidates and response.candidates[0].content.parts and getattr(response.candidates[0].content.parts[0], "function_call", None):
            for part in response.candidates[0].content.parts:
                if fn := getattr(part, "function_call", None):
                    # ディスパッチャー経由で物理・ネットワークアクションを実行
                    result = await dispatcher.dispatch(fn)
                    
                    # 実行結果を「感覚」として脳（AI）に送り返す
                    try:
                        response = chat.send_message(
                            genai.protos.Content(
                                parts=[genai.protos.Part(
                                    function_response=genai.protos.FunctionResponse(
                                        name=fn.name,
                                        response={'result': result}
                                    )
                                )]
                            )
                        )
                    except Exception as e:
                        print(f"[!] Engine Error sending function response: {e}")
                        break

        # 最終的な回答を表示
        if response and response.text:
            print(f"\n[Verantyx] {response.text}")

def start_bridge_server():
    server_path = os.path.join(os.path.dirname(__file__), "verantyx", "network", "bridge_server.py")
    if os.path.exists(server_path):
        print("[*] Starting Bridge Server (127.0.0.1:8000) in background...")
        # Use subprocess to run the uvicorn server in background
        proc = subprocess.Popen(
            [sys.executable, server_path],
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL
        )
        def cleanup():
            print("\n[*] Terminating Bridge Server...")
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
        atexit.register(cleanup)

if __name__ == "__main__":
    start_bridge_server()
    try:
        asyncio.run(verantyx_main_loop())
    except KeyboardInterrupt:
        print("\n[!] Verantyx Hibernating...")
