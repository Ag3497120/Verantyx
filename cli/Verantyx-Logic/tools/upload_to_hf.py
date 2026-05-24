import os
from huggingface_hub import HfApi, create_repo

token = "HF_TOKEN_REMOVED"
repo_name = "verantyx-logic-math"
local_dir = "/Users/motonishikoudai/avh_math"

api = HfApi(token=token)

try:
    # 1. Get User Info
    user = api.whoami()["name"]
    repo_id = f"{user}/{repo_name}"
    print(f"Target Repository: {repo_id}")

    # 2. Create Repo (if not exists)
    try:
        create_repo(repo_id, token=token, exist_ok=True, repo_type="model")
        print(f"Repository created/found: https://huggingface.co/{repo_id}")
    except Exception as e:
        print(f"Repo creation warning: {e}")

    # 3. Upload Folder
    print("Uploading files... this may take a while.")

    # Ignore patterns to keep the repo clean
    ignore_patterns = [
        ".git*", ".DS_Store", "__pycache__", "*.pyc", 
        "venv", ".env", "*.log", "tmp", ".gemini",
        "server_v2.log", "server_v3.log", "server.log",
        "tools/upload_to_hf.py" # Exclude self to protect token
    ]

    api.upload_folder(
        folder_path=local_dir,
        repo_id=repo_id,
        repo_type="model",
        ignore_patterns=ignore_patterns,
        commit_message="Initial upload of Verantyx Logic Engine (v1.0)"
    )

    print("Upload complete!")

except Exception as e:
    print(f"Upload failed: {e}")
