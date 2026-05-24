from huggingface_hub import HF_TOKEN_REMOVED_download
import shutil
import os

def download_db():
    print("Downloading DB from kofdai/verantyx-logic-math...")
    repo_id = "kofdai/verantyx-logic-math"
    
    try:
        # DB (jsonl) is inside avh_math/db/ in the repo
        file_path = HF_TOKEN_REMOVED_download(repo_id=repo_id, filename="avh_math/db/foundation_kb.jsonl", repo_type="model")
        
        # Target location
        target_dir = "avh_math/db"
        os.makedirs(target_dir, exist_ok=True)
        shutil.copy(file_path, f"{target_dir}/foundation_kb.jsonl")
        print("Downloaded foundation_kb.jsonl")
        
    except Exception as e:
        print(f"Failed to download DB: {e}")
        # Fallback: empty file creation to prevent crash
        if not os.path.exists("avh_math/db/foundation_kb.jsonl"):
            with open("avh_math/db/foundation_kb.jsonl", "w") as f:
                f.write("")

if __name__ == "__main__":
    download_db()
