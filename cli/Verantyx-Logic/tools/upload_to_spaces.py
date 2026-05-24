import os
from huggingface_hub import HfApi, create_repo

token = "HF_TOKEN_REMOVED"
space_name = "verantyx-demo"
local_dir = "/Users/motonishikoudai/avh_math"

api = HfApi(token=token)
user = api.whoami()["name"]
repo_id = f"{user}/{space_name}"

print(f"Target Space: {repo_id}")

try:
    # Create Space (Docker SDK)
    create_repo(
        repo_id, 
        token=token, 
        exist_ok=True, 
        repo_type="space", 
        space_sdk="docker"
    )
    print(f"Space created/found: https://huggingface.co/spaces/{repo_id}")
except Exception as e:
    print(f"Space creation warning: {e}")

# Upload
ignore_patterns = [
    ".git*", ".DS_Store", "__pycache__", "*.pyc", 
    "venv", ".env", "*.log", "tmp", ".gemini",
    "server_v2.log", "server_v3.log", "server.log",
    "tools/upload_to_hf.py", "tools/upload_to_spaces.py",
    "verantyx_model.bin", "*.jsonl.bak*", "*.dedup.jsonl",
    "avh_math/db/foundation_kb_gen/",
    "avh_math/db/foundation_kb.jsonl" # Exclude large DB (downloaded in Dockerfile)
]

print("Uploading to Space...")
api.upload_folder(
    folder_path=local_dir,
    repo_id=repo_id,
    repo_type="space",
    ignore_patterns=ignore_patterns,
    commit_message="Deploy Verantyx to Spaces"
)
print("Done!")
