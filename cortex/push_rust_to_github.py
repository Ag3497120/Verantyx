#!/usr/bin/env python3
"""Upload Ronin Rust and Python source files to GitHub via API."""
import subprocess, base64, os

REPO = "Ag3497120/ronin-cli"
BASE_DIR = "/Users/motonishikoudai/verantyx-cli"
UPLOAD_DIRS = ["verantyx-browser/crates", "verantyx-browser/Cargo.toml", "README.md", "package.json", "JCross_v4_Specification_JA.md"]
INCLUDE_EXTS = {".rs", ".toml", ".py", ".json", ".md", ".html", ".js"}

def get_sha(path):
    r = subprocess.run(
        ["gh", "api", f"repos/{REPO}/contents/{path}", "--jq", ".sha"],
        capture_output=True, text=True
    )
    return r.stdout.strip() if r.returncode == 0 else None

def upload_file(path_abs, path_rel):
    try:
        with open(path_abs, "rb") as f:
            content = base64.b64encode(f.read()).decode()
    except Exception as e:
        print(f"  ❌ Skipping {path_rel}: {e}")
        return

    sha = get_sha(path_rel)
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
for target in UPLOAD_DIRS:
    full_target = os.path.join(BASE_DIR, target)
    if os.path.isfile(full_target):
        ext = os.path.splitext(full_target)[1]
        if ext in INCLUDE_EXTS or os.path.basename(full_target) == "Cargo.toml":
            rel_path = os.path.relpath(full_target, BASE_DIR)
            upload_file(full_target, rel_path)
            count += 1
    elif os.path.isdir(full_target):
        for root, dirs, files in os.walk(full_target):
            dirs[:] = [d for d in dirs if d not in ("target", "__pycache__", "node_modules", "dist")]
            for fname in files:
                ext = os.path.splitext(fname)[1]
                if ext in INCLUDE_EXTS or fname == "Cargo.toml":
                    abs_path = os.path.join(root, fname)
                    rel_path = os.path.relpath(abs_path, BASE_DIR)
                    upload_file(abs_path, rel_path)
                    count += 1

print(f"\n🦀 Done! Uploaded {count} files.")
