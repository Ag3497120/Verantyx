import subprocess
import sys
import argparse
import socket
import threading
import json
import time

def monitor_node_stdout(node_id, process, sys_stdout):
    """各ノードの標準出力を監視し、JSON-RPCリクエストならIDE(Swift)へ中継する"""
    for line in iter(process.stdout.readline, b''):
        decoded_line = line.decode('utf-8').strip()
        if decoded_line:
            # sys.stderr.write(f"[Orchestrator] Node {node_id} stdout: {decoded_line}\\n")
            try:
                # JSON-RPCリクエストかどうかチェック
                data = json.loads(decoded_line)
                if "jsonrpc" in data:
                    # Swift IDE のために標準出力へ流す
                    sys_stdout.write(decoded_line + "\\n")
                    sys_stdout.flush()
            except Exception:
                pass # JSONパース失敗時は無視

def monitor_ide_stdin(processes, sys_stdin):
    """IDE(Swift)からの標準入力(JSON-RPCレスポンス)を監視し、該当ノードへ中継する"""
    while True:
        line = sys_stdin.readline()
        if not line:
            break
        decoded_line = line.strip()
        if decoded_line:
            try:
                data = json.loads(decoded_line)
                node_id = data.get("id")
                if node_id is not None and 0 <= node_id < len(processes):
                    # 該当ノードの標準入力へレスポンスを流す
                    node_process = processes[node_id]
                    node_process.stdin.write((decoded_line + "\\n").encode('utf-8'))
                    node_process.stdin.flush()
            except Exception as e:
                sys.stderr.write(f"[Orchestrator] Error parsing IDE input: {e}\\n")

def main():
    parser = argparse.ArgumentParser(description="Start Socket-based JCross Vector Pipeline Swarm")
    parser.add_argument("--prompt", type=str, default="A simple HTML button with red text.", help="Initial prompt for Commander")
    parser.add_argument("--nodes", type=int, default=10, help="Total number of physical nodes to launch")
    parser.add_argument("--base_port", type=int, default=10000, help="Base port for socket communication")
    args = parser.parse_args()

    num_nodes = args.nodes
    prompt = args.prompt
    base_port = args.base_port

    sys.stderr.write(f"[*] Starting {num_nodes} physical Qwen 0.5B processes (Socket IPC)...\\n")

    processes = []
    
    # ノードを起動
    for i in range(num_nodes):
        listen_port = base_port + i
        send_port = base_port + i + 1
        
        cmd = ["python3", "cli/scripts/qwen_physical_node_socket.py", 
               "--node_id", str(i), 
               "--listen_port", str(listen_port), 
               "--send_port", str(send_port)]
        
        # stdin, stdout をキャプチャしてRPC通信を仲介できるようにする
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr)
        processes.append(p)
        
        # ノードのstdout監視スレッドを開始
        t = threading.Thread(target=monitor_node_stdout, args=(i, p, sys.stdout), daemon=True)
        t.start()

    # IDEからのstdin監視スレッドを開始
    ide_t = threading.Thread(target=monitor_ide_stdin, args=(processes, sys.stdin), daemon=True)
    ide_t.start()

    # Node 0がリッスン開始するのを少し待つ
    time.sleep(5)
    
    # 最終ノード(Node 9)の出力を受け取るためのサーバーソケットを起動
    final_port = base_port + num_nodes
    final_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    final_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    final_server.bind(('127.0.0.1', final_port))
    final_server.listen(1)

    # Node 0 (Commander) に初期プロンプトを送信
    try:
        commander_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        commander_client.connect(('127.0.0.1', base_port))
        commander_client.sendall(prompt.encode('utf-8'))
        commander_client.close()
    except Exception as e:
        sys.stderr.write(f"[*] Failed to connect to Commander: {e}\\n")
        return

    # 最終結果の受信待機
    sys.stderr.write("[*] Pipeline is running. Waiting for final result...\\n")
    conn, addr = final_server.accept()
    final_text = conn.recv(4096).decode('utf-8')
    
    # 最終結果をIDE(Swift)へJSONで返す
    final_response = {
        "status": "success",
        "result": final_text
    }
    sys.stdout.write(json.dumps(final_response) + "\\n")
    sys.stdout.flush()

    sys.stderr.write("\\n[*] Swarm Pipeline execution completed.\\n")
    
    # 終了処理
    for p in processes:
        p.terminate()

if __name__ == "__main__":
    main()
