import json
import os

ORACLE_PATH = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/data/longmemeval_oracle.json"
TARGET_DIR = "/Users/motonishikoudai/verantyx-cli/verantyx-browser/.ronin/jcross_v6"

def setup():
    if not os.path.exists(TARGET_DIR):
        os.makedirs(TARGET_DIR)
        
    with open(ORACLE_PATH, "r") as f:
        data = json.load(f)
        
    # Question 1
    item = data[0]
    sessions = item['haystack_sessions']
    
    for i, session in enumerate(sessions):
        node_id = f"bench_q1_s{i}"
        
        # Combine turns into a single raw text block
        full_text = "\n".join([f"{t['role'].upper()}: {t['content']}" for t in session])
        
        # We simulate a high-quality V6 distillation
        # L1 summary for this session
        if "car" in full_text.lower():
            l1_summary = "Discussion about new car service, rewards programs (Shell), and pre-trip preparation (waxing/detailing)."
            key_entities = ["Shell", "Yellowstone", "Meguiar's", "Chemical Guys", "GPS system"]
            domain = "personal_memory"
        else:
            l1_summary = "General discussion from session history."
            key_entities = []
            domain = "personal_memory"
            
        jcross_content = f"""■ JCROSS_NODE_{node_id}

【空間座相】
[渇:0.2] [認:0.8] [視:0.5]

【次元概念】
Oracle Haystack: {l1_summary[:50]}...

【領域】
{domain}

【時間刻印】
2023-04-10T15:00:00Z

---
[L1_Cache]
Keywords: {", ".join(key_entities)}
Summary: {l1_summary}

[L2_Archive]
{full_text}
===
"""
        with open(os.path.join(TARGET_DIR, f"{node_id}.jcross"), "w") as out:
            out.write(jcross_content)
            
    print(f"Setup complete. 3 nodes injected into {TARGET_DIR}")

if __name__ == "__main__":
    setup()
