import os
from huggingface_hub import HfApi

token = "HF_TOKEN_REMOVED"
space_id = "kofdai/verantyx-demo"
api = HfApi(token=token)

print(f"Target Space: {space_id}")

# Upload specific files
files_to_upload = [
    "Dockerfile",
    "requirements.txt",
    "phase17_ui_server.py",
    "cli.py",
    "verantyx_engine.py",
    "config.json",
    "README.md",
    "tools/download_db_for_space.py"
]

folders_to_upload = [
    "phase17_static",
    "avh_math"
]

def upload_file(local_path):
    print(f"Uploading {local_path}...")
    try:
        api.upload_file(
            path_or_fileobj=local_path,
            path_in_repo=local_path,
            repo_id=space_id,
            repo_type="space"
        )
    except Exception as e:
        print(f"Failed to upload {local_path}: {e}")

# 1. Upload root files
for f in files_to_upload:
    if os.path.exists(f):
        upload_file(f)

# 2. Upload folders recursively with strict filtering
for folder in folders_to_upload:
    for root, dirs, files in os.walk(folder):
        for file in files:
            local_path = os.path.join(root, file)
            
            # Filters
            if "__pycache__" in local_path or ".DS_Store" in local_path: continue
            if local_path.endswith(".bin"): continue
            if "foundation_kb.jsonl" in local_path: continue # Exclude huge DB
            if ".bak" in local_path: continue
            if ".dedup" in local_path: continue
            if "foundation_kb_gen" in local_path: continue
            
            upload_file(local_path)

print("Selective upload complete!")
