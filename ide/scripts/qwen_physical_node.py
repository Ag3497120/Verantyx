import sys
import io
import argparse
import struct
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
import logging

# バイナリ通信のノイズを防ぐため、ログはすべて stderr に出力する
logging.basicConfig(stream=sys.stderr, level=logging.INFO, format='[Node %(name)s] %(message)s')

MODEL_ID = "Qwen/Qwen1.5-0.5B"

def send_tensor(tensor, stream):
    """テンソルをバイナリ化してストリームに書き込む"""
    buffer = io.BytesIO()
    torch.save(tensor, buffer)
    data = buffer.getvalue()
    size_bytes = struct.pack("!I", len(data))
    stream.write(size_bytes)
    stream.write(data)
    stream.flush()

def recv_tensor(stream, device):
    """ストリームからバイナリを受け取りテンソルに復元する"""
    size_bytes = stream.read(4)
    if not size_bytes or len(size_bytes) < 4:
        return None
    size = struct.unpack("!I", size_bytes)[0]
    data = stream.read(size)
    if len(data) < size:
        return None
    buffer = io.BytesIO(data)
    tensor = torch.load(buffer, map_location=device)
    return tensor

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--node_id", type=int, required=True, help="Node ID (0=Commander, 1-8=Worker, 9=Final)")
    parser.add_argument("--prompt", type=str, default="Swarm testing", help="Initial prompt for Commander")
    args = parser.parse_args()
    node_id = args.node_id
    prompt = args.prompt
    
    logger = logging.getLogger(str(node_id))
    logger.info("Initializing...")

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        torch_dtype=torch.float16,
        device_map=device,
        low_cpu_mem_usage=True
    )
    model.eval()
    for param in model.parameters():
        param.requires_grad = False

    logger.info("Ready.")

    # バイナリ入出力を直接扱うためのバッファ
    stdin_bin = sys.stdin.buffer
    stdout_bin = sys.stdout.buffer

    import swarm_harness

    SYSTEM_PROMPT = """You are a node in a Swarm. You can use tools if necessary to complete the task.
To use a tool, output exactly: [TOOL_CALL] {"action": "read_file", "path": "filename"} [/TOOL_CALL]
Available actions: read_file, write_file, list_directory
If you do not need tools, just continue thinking or output the final result."""

    if node_id == 0:
        # Commander: テキストを受け取り、思考ベクトル(Hidden States)を生成
        logger.info(f"Generating initial thought vector for prompt: '{prompt}'")
        full_prompt = f"{SYSTEM_PROMPT}\\nUser: {prompt}\\nAssistant:"
        inputs = tokenizer(full_prompt, return_tensors="pt").to(device)
        with torch.no_grad():
            outputs = model(**inputs, output_hidden_states=True)
            initial_hidden = outputs.hidden_states[-1] # 最後の層の出力
            
        send_tensor(initial_hidden, stdout_bin)
        logger.info("Sent initial thought vector to Node 1.")
            
    elif node_id < 9:
        # Worker: ベクトルを受信し、自律的にツールを使うか判断してからベクトルを送信
        while True:
            hidden_states = recv_tensor(stdin_bin, device)
            if hidden_states is None:
                break # EOF
            
            logger.info("Received thought vector. Checking for autonomous tool use...")
            
            with torch.no_grad():
                # まず、ベクトルから少しだけテキストを生成して意図をチェック
                generated_ids = model.generate(
                    inputs_embeds=hidden_states,
                    max_new_tokens=40,
                    pad_token_id=tokenizer.eos_token_id
                )
                text_intention = tokenizer.decode(generated_ids[0], skip_special_tokens=True)
                
                tool_req = swarm_harness.parse_tool_call(text_intention)
                
                if tool_req:
                    # ツール実行
                    tool_result = swarm_harness.execute_tool(tool_req["action"], tool_req)
                    logger.info(f"Tool executed. Result length: {len(tool_result)}")
                    
                    # 結果をコンテキスト（ベクトル）に追加
                    result_text = f"\\n[TOOL_RESULT] {tool_result} [/TOOL_RESULT]\\n"
                    result_inputs = tokenizer(result_text, return_tensors="pt").to(device)
                    result_embeds = model.get_input_embeddings()(result_inputs.input_ids)
                    
                    # 元の思考ベクトルと結合
                    new_hidden = torch.cat([hidden_states, result_embeds], dim=1)
                else:
                    logger.info("No tool required. Advancing thought...")
                    # ツールを使わない場合は層を通過させる
                    outputs = model(inputs_embeds=hidden_states, output_hidden_states=True)
                    new_hidden = outputs.hidden_states[-1]
            
            # テンソルを次のノードへリレー
            send_tensor(new_hidden, stdout_bin)
            logger.info("Sent thought vector to next node.")

    else:
        # Final Node (Node 9): ベクトルを受信し、自然言語にデコード
        while True:
            hidden_states = recv_tensor(stdin_bin, device)
            if hidden_states is None:
                break
            
            logger.info("Received final thought vector. Decoding to natural language...")
            with torch.no_grad():
                # inputs_embeds から文章生成を開始
                generated_ids = model.generate(
                    inputs_embeds=hidden_states,
                    max_new_tokens=50,
                    pad_token_id=tokenizer.eos_token_id
                )
            
            text = tokenizer.decode(generated_ids[0], skip_special_tokens=True)
            # 最終結果は通常の stdout にテキストで出力
            sys.stdout.write(f"\\n[Final Output]: {text}\\n")
            sys.stdout.flush()
            logger.info("Decoding complete.")

if __name__ == "__main__":
    main()
