import shutil
import os

src_base = "."
dst_base = "verantyx_ios/src/verantyx"

print("Preparing iOS project files...")

# 1. Copy verantyx_engine.py & config.json
if os.path.exists("verantyx_engine.py"):
    shutil.copy("verantyx_engine.py", dst_base)
if os.path.exists("config.json"):
    shutil.copy("config.json", dst_base)

# 2. Copy verantyx_model.bin
if os.path.exists("verantyx_model.bin"):
    print("Copying model bin (this may take a moment)...")
    shutil.copy("verantyx_model.bin", dst_base)
else:
    print("Warning: verantyx_model.bin not found! You must add it later.")

# 3. Copy avh_math package
dest_pkg = os.path.join(dst_base, "avh_math")
if os.path.exists(dest_pkg):
    shutil.rmtree(dest_pkg)

def ignore_filter(path, names):
    ignored = []
    # Essential DB files
    whitelist = {
        "foundation_kb.jsonl", # Need this one inside the package logic? 
        # Actually verantyx_engine loads from bin, but let's keep minimal DB structure just in case
        "word_memory.json", "semantic_patterns.jsonl",
        "kb_offsets.json", "kb_index.json", "kb_meta.json"
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
            # Exclude everything else to save space
            if "foundation_kb" in n: ignored.append(n) # The bin has the KB
            if "phase" in n or "dedup" in n or "cross" in n or "log" in n or "backup" in n or "all.jsonl" == n:
                ignored.append(n)
    return ignored

print("Copying avh_math package...")
shutil.copytree("avh_math", dest_pkg, ignore=ignore_filter)

# 4. Create ZIP
print("Zipping project...")
shutil.make_archive("verantyx_ios_project", "zip", "verantyx_ios")
print("Created verantyx_ios_project.zip")
