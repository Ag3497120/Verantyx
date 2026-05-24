#!/usr/bin/env python3
"""Upload Ronin source files to GitHub via API."""
import subprocess, base64, os, sys

REPO = "Ag3497120/ronin-cli"
BASE_DIR = "/Users/motonishikoudai/verantyx-cli"
UPLOAD_DIRS = ["src/verantyx", "src/cli"]
INCLUDE_EXTS = {".ts", ".js", ".json", ".md", ".py", ".rs"}

def get_token():
    r = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True)
    return r.stdout.strip()

def get_sha(token, path):
    r = subprocess.run(
        ["gh", "api", f"repos/{REPO}/contents/{path}", "--jq", ".sha"],
        capture_output=True, text=True
    )
    return r.stdout.strip() if r.returncode == 0 else None

def upload_file(path_abs, path_rel):
    with open(path_abs, "rb") as f:
        content = base64.b64encode(f.read()).decode()
    sha = get_sha(None, path_rel)
    cmd = ["gh", "api", "--method", "PUT", f"repos/{REPO}/contents/{path_rel}",
           "-f", f"message=feat: add {path_rel}",
           "-f", f"content={content}"]
    if sha:
        cmd += ["-f", f"sha={sha}"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode == 0:
        print(f"  ✅ {path_rel}")
    else:
        print(f"  ❌ {path_rel}: {r.stderr[:100]}")

count = 0
for upload_dir in UPLOAD_DIRS:
    full_dir = os.path.join(BASE_DIR, upload_dir)
    for root, dirs, files in os.walk(full_dir):
        # Skip node_modules and dist
        dirs[:] = [d for d in dirs if d not in ("node_modules", "dist", "__pycache__", "target")]
        for fname in files:
            ext = os.path.splitext(fname)[1]
            if ext in INCLUDE_EXTS:
                abs_path = os.path.join(root, fname)
                rel_path = os.path.relpath(abs_path, BASE_DIR)
                upload_file(abs_path, rel_path)
                count += 1

print(f"\n🐺 Done! Uploaded {count} files.")
