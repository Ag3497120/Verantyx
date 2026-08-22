import subprocess
import sys
import argparse

def main():
    parser = argparse.ArgumentParser(description="Start JCross Vector Pipeline Swarm")
    parser.add_argument("--prompt", type=str, default="A simple HTML button with red text.", help="Initial prompt for Commander")
    parser.add_argument("--nodes", type=int, default=10, help="Total number of physical nodes to launch")
    args = parser.parse_args()

    num_nodes = args.nodes
    prompt = args.prompt

    print(f"[*] Starting {num_nodes} physical Qwen 0.5B processes for Vector Pipeline Swarm...")
    print(f"[*] Initial Prompt: '{prompt}'\\n")

    processes = []
    
    # 最初のノード (Node 0: Commander)
    # 標準入力を受け付けず、プロンプトから思考ベクトルを生成し標準出力に流す
    cmd0 = ["python3", "cli/scripts/qwen_physical_node.py", "--node_id", "0", "--prompt", prompt]
    p0 = subprocess.Popen(cmd0, stdout=subprocess.PIPE, stderr=sys.stderr)
    processes.append(p0)

    # 中間ノードと最終ノード
    prev_stdout = p0.stdout
    for i in range(1, num_nodes):
        cmd = ["python3", "cli/scripts/qwen_physical_node.py", "--node_id", str(i)]
        
        # 最終ノードは結果をそのままコンソール (stdout) に出すため、標準出力を繋がない
        if i == num_nodes - 1:
            pi = subprocess.Popen(cmd, stdin=prev_stdout, stderr=sys.stderr)
        else:
            pi = subprocess.Popen(cmd, stdin=prev_stdout, stdout=subprocess.PIPE, stderr=sys.stderr)
            
        processes.append(pi)
        
        # 次のプロセスへのパイプをセットしたら、親プロセス側からはファイルディスクリプタを閉じる
        if prev_stdout:
            prev_stdout.close()
        
        if i < num_nodes - 1:
            prev_stdout = pi.stdout

    # 最終ノードの完了を待つ
    processes[-1].communicate()
    
    print("\\n[*] Swarm Pipeline execution completed.")

if __name__ == "__main__":
    main()
