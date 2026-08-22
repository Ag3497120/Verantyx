import sys
import json
import asyncio
import threading
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_ID = "Qwen/Qwen1.5-0.5B-Chat"

# ゼロ知識・ツール駆動を強制するシステムプロンプト
SYSTEM_PROMPT = """You are a core component of a Swarm Intelligence.
You possess ZERO prior knowledge. You must not rely on any internal facts, lore, or general knowledge.
Your sole purpose is logical reasoning and generating structured outputs (HTML, JSON, Code, Tool Calls) based ONLY on the context provided to you.
Do not output conversational filler. Output only the logical result or the required code structure.
"""

class QwenSwarmNode:
    def __init__(self):
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        # 初回起動時に重みが無ければ自動ダウンロードされる
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
        self.model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID,
            torch_dtype=torch.float16,
            device_map=self.device,
            low_cpu_mem_usage=True
        )
        self.model.eval()
        for param in self.model.parameters():
            param.requires_grad = False
        
        # Generation用スレッドロック (MPS/GPUへの同時アクセス衝突防止)
        self.lock = threading.Lock()

    def generate_response(self, task_id, messages, role="worker"):
        # 強制的にシステムプロンプトを注入
        formatted_messages = [
            {"role": "system", "content": SYSTEM_PROMPT + f"\\nYour role in this swarm is: {role}"}
        ]
        formatted_messages.extend(messages)

        text = self.tokenizer.apply_chat_template(
            formatted_messages,
            tokenize=False,
            add_generation_prompt=True
        )
        model_inputs = self.tokenizer([text], return_tensors="pt").to(self.device)

        with self.lock:
            with torch.no_grad():
                generated_ids = self.model.generate(
                    model_inputs.input_ids,
                    max_new_tokens=1024,
                    temperature=0.1,
                    do_sample=True,
                    pad_token_id=self.tokenizer.eos_token_id
                )
        
        # 生成部分のみを抽出
        generated_ids = [
            output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
        ]
        response_text = self.tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]

        return {
            "task_id": task_id,
            "status": "success",
            "role": role,
            "response": response_text
        }

async def handle_request(node, raw_line):
    try:
        req = json.loads(raw_line)
        task_id = req.get("task_id", "unknown")
        messages = req.get("messages", [])
        role = req.get("role", "worker")

        # 非同期スレッドで推論を実行
        result = await asyncio.to_thread(node.generate_response, task_id, messages, role)
        
    except Exception as e:
        result = {
            "task_id": req.get("task_id", "unknown") if 'req' in locals() else "unknown",
            "status": "error",
            "error": str(e)
        }

    # 標準出力へJSON形式で返却
    sys.stdout.write(json.dumps(result) + "\\n")
    sys.stdout.flush()

async def main_loop():
    # 1. モデルの自動ダウンロードとロード
    sys.stderr.write("[*] Booting embedded Qwen Swarm Backend...\\n")
    sys.stderr.flush()
    
    node = QwenSwarmNode()
    
    # 起動完了の合図（IDE側がこれを見てパイプ通信を開始する）
    sys.stdout.write(json.dumps({"status": "ready", "message": "Qwen Swarm Embedded Node is Ready."}) + "\\n")
    sys.stdout.flush()

    # 2. 標準入力の非同期リスンループ
    loop = asyncio.get_running_loop()
    
    # 標準入力からの非同期読み取り用のキュー
    # stdin_readline はブロッキングなので executor で回す
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            break # EOF (IDE側がプロセスを終了した)
            
        line = line.strip()
        if not line:
            continue
            
        # タスクを非同期に走らせる（最大20並列などはIDE側からのリクエスト次第）
        asyncio.create_task(handle_request(node, line))

if __name__ == "__main__":
    asyncio.run(main_loop())
