import os
from huggingface_hub import HfApi

token = "HF_TOKEN_REMOVED"
space_id = "kofdai/verantyx-demo"
api = HfApi(token=token)

f = "phase17_static/app.js"
print(f"Uploading {f}...")
api.upload_file(
    path_or_fileobj=f,
    path_in_repo=f,
    repo_id=space_id,
    repo_type="space"
)
print("Done!")
