import shutil
import os

src_base = "."
dst_base = "verantyx_ios/src/verantyx"

print("Copying files to iOS project...")

# 1. Copy verantyx_engine.py & config.json
if os.path.exists("verantyx_engine.py"):
    shutil.copy("verantyx_engine.py", dst_base)
if os.path.exists("config.json"):
    shutil.copy("config.json", dst_base)

# 2. Copy verantyx_model.bin
if os.path.exists("verantyx_model.bin"):
    print("Copying model bin...")
    shutil.copy("verantyx_model.bin", dst_base)
else:
    print("Warning: verantyx_model.bin not found!")

# 3. Copy avh_math package
dest_pkg = os.path.join(dst_base, "avh_math")
if os.path.exists(dest_pkg):
    shutil.rmtree(dest_pkg)

def ignore_filter(path, names):
    ignored = []
    # Essential DB files
    whitelist = {
        "word_memory.json", "semantic_patterns.jsonl",
        "kb_offsets.json", "kb_index.json", "kb_meta.json",
        "foundation_kb.jsonl"
    }
    
    for n in names:
        if n == "__pycache__" or n == ".DS_Store" or ".git" in n:
            ignored.append(n)
            continue
        
        # Exclude huge files
        if n.endswith(".bin") or n.endswith(".pdf"):
            ignored.append(n)
            continue
            
        if n.endswith(".jsonl") or n.endswith(".json"):
            if n in whitelist: continue
            if "foundation_kb" in n and n != "foundation_kb.jsonl": ignored.append(n)
            if "phase" in n or "dedup" in n or "cross" in n or "log" in n or "backup" in n or "all.jsonl" == n:
                ignored.append(n)
    return ignored

print("Copying avh_math package...")
shutil.copytree("avh_math", dest_pkg, ignore=ignore_filter)
print("Done.")
