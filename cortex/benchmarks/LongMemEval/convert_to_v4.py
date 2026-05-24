import json
import os
import hashlib
from datetime import datetime

CHALLENGE_FILE = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/data/longmemeval_oracle.json"
JCROSS_DIR = "/Users/motonishikoudai/verantyx-cli/jcross_v4"

def make_jcross_v4(text, index):
    # Hash the text to create a unique ID
    node_id = hashlib.md5(text.encode('utf-8')).hexdigest()[:12]
    
    # 簡易的にいくつかのキーワードをベースに漢字タグを付与
    tags = "[探:0.5] [新:0.8]"
    if "car" in text.lower() or "bike" in text.lower() or "service" in text.lower():
        tags += " [車:1.0] [機:0.8]"
    if "date" in text.lower() or "time" in text.lower() or "month" in text.lower():
        tags += " [時:1.0]"
        
    # Extract concept
    lines = text.strip().split('\n')
    concept = text.strip()[:2000].replace('\n', ' ')

    template = f"""■ JCROSS_NODE_longmem_{node_id}

【空間座相】
{tags}

【次元概念】
{concept}

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

    with open(CHALLENGE_FILE, 'r') as f:
        challenge = json.load(f)

    all_history = set()
    for item in challenge:
        if 'haystack_sessions' in item:
            for session in item['haystack_sessions']:
                # session is list of dicts with role and content
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
        node_id, content = make_jcross_v4(session_text, idx)
        file_path = os.path.join(JCROSS_DIR, f"{node_id}.jcross")
        with open(file_path, 'w') as f:
            f.write(content)
        count += 1
        
    print(f"Converted {count} sessions to JCross v4 format.")

if __name__ == "__main__":
    convert()
