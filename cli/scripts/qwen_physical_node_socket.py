import sys
import argparse
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
import logging
import json

import swarm_harness
from swarm_socket_util import send_tensor_socket, recv_tensor_socket, create_server_socket, connect_to_server

# ログはstderrに出力（オーケストレータ側で見えるように）
logging.basicConfig(stream=sys.stderr, level=logging.INFO, format='[Node %(name)s] %(message)s')

MODEL_ID = "Qwen/Qwen1.5-0.5B"

SYSTEM_PROMPT = """You are a node in a Swarm. You can use tools if necessary to complete the task.
To use a tool, output exactly: [TOOL_CALL] {"action": "read_file", "path": "filename"} [/TOOL_CALL]
Available actions: read_file, write_file, list_directory
If you do not need tools, just continue thinking or output the final result."""

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--node_id", type=int, required=True, help="Node ID (0=Commander, 1-8=Worker, 9=Final)")
    parser.add_argument("--listen_port", type=int, required=True, help="Port to listen for incoming data")
    parser.add_argument("--send_port", type=int, required=True, help="Port to send outgoing data to")
    args = parser.parse_args()
    
    node_id = args.node_id
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

    logger.info(f"Ready. Listening on port {args.listen_port}, sending to port {args.send_port}")

    # 受信待機
    server_sock = create_server_socket(args.listen_port)
    conn, addr = server_sock.accept()
    logger.info(f"Accepted connection from {addr}")

    if node_id == 0:
        # Commander: オーケストレータからテキストプロンプトを受信
        data = conn.recv(4096).decode('utf-8')
        prompt = data.strip()
        logger.info(f"Generating initial thought vector for prompt: '{prompt}'")
        
        full_prompt = f"{SYSTEM_PROMPT}\\nUser: {prompt}\\nAssistant:"
        inputs = tokenizer(full_prompt, return_tensors="pt").to(device)
        with torch.no_grad():
            outputs = model(**inputs, output_hidden_states=True)
            initial_hidden = outputs.hidden_states[-1]
            
        send_sock = connect_to_server(args.send_port)
        send_tensor_socket(initial_hidden, send_sock)
        logger.info("Sent initial thought vector.")
        send_sock.close()
        
    elif node_id < 9:
        # Worker: ベクトルを受信し、自律的にツールを使うか判断してからベクトルを送信
        send_sock = connect_to_server(args.send_port)
        while True:
            hidden_states = recv_tensor_socket(conn, device)
            if hidden_states is None:
                break
            
            logger.info("Received thought vector. Checking for autonomous tool use...")
            with torch.no_grad():
                generated_ids = model.generate(
                    inputs_embeds=hidden_states,
                    max_new_tokens=40,
                    pad_token_id=tokenizer.eos_token_id
                )
                text_intention = tokenizer.decode(generated_ids[0], skip_special_tokens=True)
                
                tool_req = swarm_harness.parse_tool_call(text_intention)
                
                if tool_req:
                    # Swift IDEへJSON-RPC経由でツール実行を依頼する
                    # 自身の標準出力（stdout）にJSONを書き、標準入力（stdin）から結果を受け取る
                    rpc_request = {
                        "jsonrpc": "2.0",
                        "method": tool_req["action"],
                        "params": tool_req,
                        "id": node_id
                    }
                    sys.stdout.write(json.dumps(rpc_request) + "\\n")
                    sys.stdout.flush()
                    
                    # Swift（親プロセス）からの返答を待つ
                    response_line = sys.stdin.readline()
                    try:
                        response_data = json.loads(response_line)
                        tool_result = response_data.get("result", "Error: No result")
                    except Exception as e:
                        tool_result = f"Error parsing RPC response: {e}"
                        
                    logger.info(f"RPC Tool executed. Result length: {len(str(tool_result))}")
                    
                    result_text = f"\\n[TOOL_RESULT] {tool_result} [/TOOL_RESULT]\\n"
                    result_inputs = tokenizer(result_text, return_tensors="pt").to(device)
                    result_embeds = model.get_input_embeddings()(result_inputs.input_ids)
                    
                    new_hidden = torch.cat([hidden_states, result_embeds], dim=1)
                else:
                    logger.info("No tool required. Advancing thought...")
                    outputs = model(inputs_embeds=hidden_states, output_hidden_states=True)
                    new_hidden = outputs.hidden_states[-1]
            
            send_tensor_socket(new_hidden, send_sock)
            logger.info("Sent thought vector to next node.")
            break # 1回のバケツリレーで終了とする（POC用）
            
        send_sock.close()

    else:
        # Final Node: ベクトルを受信し、自然言語にデコードしてオーケストレータへ返す
        send_sock = connect_to_server(args.send_port)
        while True:
            hidden_states = recv_tensor_socket(conn, device)
            if hidden_states is None:
                break
            
            logger.info("Received final thought vector. Decoding...")
            with torch.no_grad():
                generated_ids = model.generate(
                    inputs_embeds=hidden_states,
                    max_new_tokens=50,
                    pad_token_id=tokenizer.eos_token_id
                )
            
            text = tokenizer.decode(generated_ids[0], skip_special_tokens=True)
            # オーケストレータへテキストを送信
            send_sock.sendall(text.encode('utf-8'))
            logger.info("Sent final output.")
            break
            
        send_sock.close()

    conn.close()
    server_sock.close()

if __name__ == "__main__":
    main()
