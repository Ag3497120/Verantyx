import os
import shutil
from huggingface_hub import HfApi

token = "HF_TOKEN_REMOVED"
space_id = "kofdai/verantyx-demo"
api = HfApi(token=token)
staging_dir = "tmp_space_upload"

print(f"Preparing files in {staging_dir}...")

if os.path.exists(staging_dir):
    shutil.rmtree(staging_dir)
os.makedirs(staging_dir)

# Define copy list
files_to_copy = [
    "Dockerfile",
    "requirements.txt",
    "phase17_ui_server.py",
    "phase32_explain.py",
    "phase33_proof_store.py",
    "proof_sketch.py",
    "proof_trace.py",
    "cli.py",
    "verantyx_engine.py",
    "config.json",
    "README.md",
    "tools/download_db_for_space.py"
]

folders_to_copy = [
    "phase17_static",
    "avh_math"
]

# Copy files
for f in files_to_copy:
    if os.path.exists(f):
        dest_path = os.path.join(staging_dir, f)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        shutil.copy(f, dest_path)

# Copy folders with filter
def ignore_patterns(path, names):
    ignored = []
    
    # 実行に必要な最小限のDBファイル
    allowed_db = {
        "word_memory.json", "semantic_patterns.jsonl",
        "kb_offsets.json", "kb_index.json", "kb_meta.json",
        "boundary_graph.json"
    }

    for n in names:
        if n == "__pycache__" or n == ".DS_Store" or ".git" in n or "venv" in n:
            ignored.append(n)
            continue
            
        # 巨大ファイル・不要ファイルの徹底除外
        if n.endswith(".bin") or n.endswith(".pdf") or ".bak" in n or "~" in n:
            ignored.append(n)
            continue

        # DB関連のフィルタリング
        if n.endswith(".jsonl") or n.endswith(".json"):
            # 許可リストにあるなら除外しない
            if n in allowed_db:
                continue
            
            # foundation_kb 関連はバックアップ含めすべて除外（本体はビルド時にDL）
            if "foundation_kb" in n:
                ignored.append(n)
                continue
                
            # 中間ファイル・ログ群を除外
            if "phase" in n or "dedup" in n or "cross" in n or "patch" in n or "log" in n or "all.jsonl" == n or "backup" in n or "seed" in n:
                ignored.append(n)
                continue
                
            # その他不明な巨大JSONLも念のため除外（ホワイトリスト方式に近づける）
            # ただし直下のファイルなどは通すかもしれないので、サイズチェックができればベストだが
            # ここではファイル名パターンで弾く
            if "gen_" in n or "test" in n:
                ignored.append(n)

    return ignored

for folder in folders_to_copy:
    src = folder
    dst = os.path.join(staging_dir, folder)
    if os.path.exists(src):
        shutil.copytree(src, dst, ignore=ignore_patterns)

# Calculate size
total_size = 0
for root, dirs, files in os.walk(staging_dir):
    for f in files:
        fp = os.path.join(root, f)
        total_size += os.path.getsize(fp)
print(f"Total upload size: {total_size / 1024 / 1024:.2f} MB")

print("Uploading folder...")
try:
    api.upload_folder(
        folder_path=staging_dir,
        repo_id=space_id,
        repo_type="space",
        commit_message="Deploy Verantyx (Optimized)"
    )
    print("Upload complete!")
finally:
    # Cleanup
    if os.path.exists(staging_dir):
        shutil.rmtree(staging_dir)
