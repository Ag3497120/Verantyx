import json
import os
import hashlib
from datetime import datetime

CHALLENGE_FILE = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/data/longmemeval_oracle.json"
JCROSS_DIR = "/Users/motonishikoudai/verantyx-cli/jcross_v4"

def make_jcross_v5(text, index):
    node_id = hashlib.md5(text.encode('utf-8')).hexdigest()[:12]
    
    tags = "[探:0.5] [新:0.8]"
    domain = "personal_memory"
    
    if "car" in text.lower() or "bike" in text.lower() or "service" in text.lower():
        # Only tag as car if it's not generic "customer service"
        if "customer service" not in text.lower():
            tags += " [車:1.0] [機:0.8]"
        else:
            tags += " [事:0.6]" # Generic Business/Task
            
    if "date" in text.lower() or "time" in text.lower() or "month" in text.lower():
        tags += " [時:1.0]"
        
    # Extract concept
    concept = text.strip()[:2000].replace('\n', ' ')

    template = f"""■ JCROSS_NODE_longmem_{node_id}

【空間座相】
{tags}

【次元概念】
{concept}

【領域】
{domain}

【時間刻印】
2026-04-12T00:00:00+00:00

【連帯】

【抽象度】
<0.5>

---
[本質記憶]
{text.strip()}
===
"""
    return f"longmem_{node_id}", template

def convert():
    if not os.path.exists(JCROSS_DIR):
        os.makedirs(JCROSS_DIR)
    else:
        # Clear old v4 nodes
        for f in os.listdir(JCROSS_DIR):
            if f.endswith(".jcross"):
                os.remove(os.path.join(JCROSS_DIR, f))

    with open(CHALLENGE_FILE, 'r') as f:
        challenge = json.load(f)

    all_history = set()
    for item in challenge:
        if 'haystack_sessions' in item:
            for session in item['haystack_sessions']:
                session_strs = []
                for msg in session:
                    if 'role' in msg and 'content' in msg:
                        session_strs.append(f"{msg['role'].capitalize()}: {msg['content']}")
                if session_strs:
                    s_str = "\n".join(session_strs)
                    all_history.add(s_str.strip())
        elif 'history' in item:
            sessions = item['history'].split('--- Session')
            for s in sessions:
                s = s.strip()
                if s:
                    cleaned = s.split(' ---\n', 1)[-1] if ' ---' in s else s
                    all_history.add(cleaned.strip())

    count = 0
    for idx, session_text in enumerate(all_history):
        node_id, content = make_jcross_v5(session_text, idx)
        file_path = os.path.join(JCROSS_DIR, f"{node_id}.jcross")
        with open(file_path, 'w') as f:
            f.write(content)
        count += 1
        
    print(f"Converted {count} sessions to JCross v5 format in {JCROSS_DIR}")

if __name__ == "__main__":
    convert()
