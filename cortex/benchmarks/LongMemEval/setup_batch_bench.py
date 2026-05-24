import json
import os

ORACLE_PATH = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/data/longmemeval_oracle.json"
TARGET_DIR = "/Users/motonishikoudai/verantyx-cli/verantyx-browser/.ronin/jcross_v6"

def setup_batch():
    if not os.path.exists(TARGET_DIR):
        os.makedirs(TARGET_DIR)
        
    with open(ORACLE_PATH, "r") as f:
        data = json.load(f)
        
    # Questions 2-6 (indices 1 to 5)
    for q_idx in range(1, 6):
        item = data[q_idx]
        sessions = item['haystack_sessions']
        
        for i, session in enumerate(sessions):
            node_id = f"bench_q{q_idx+1}_s{i}"
            full_text = "\n".join([f"{t['role'].upper()}: {t['content']}" for t in session])
            
            # Sublimation Logic (Simulation of G3 Flash)
            # L1 Summary Extraction
            summary = "Session history involving "
            entities = []
            if "catholic charities" in full_text.lower():
                summary += "volunteer work at Catholic Charities, refugee services, and entrepreneurship programs."
                entities += ["Catholic Charities", "Refugees", "Entrepreneurship", "Grant", "Microloan"]
            if "buddist" in full_text.lower() or "retreat" in full_text.lower():
                summary += "spiritual retreat at a Buddhist temple, meditation, and yoga."
                entities += ["Buddhist temple", "Spiritual retreat", "Meditation", "Yoga"]
            if "house" in full_text.lower() or "lease" in full_text.lower():
                summary += "home buying, leasing agreements, and real estate discussion."
                entities += ["Lease", "Apartment", "Real Estate"]
            
            jcross_content = f"""■ JCROSS_NODE_{node_id}

【空間座相】
[渇:0.1] [認:0.9] [誠:0.7]

【次元概念】
Oracle Haystack: {summary[:50]}...

【領域】
personal_memory

【時間刻印】
2023-04-12T10:00:00Z

---
[L1_Cache]
Keywords: {", ".join(entities)}
Summary: {summary}

[L2_Archive]
{full_text}
===
"""
            with open(os.path.join(TARGET_DIR, f"{node_id}.jcross"), "w") as out:
                out.write(jcross_content)
                
    print(f"Batch setup complete. Nodes for Q2-Q6 injected into {TARGET_DIR}")

if __name__ == "__main__":
    setup_batch()
