import json
import os
from tqdm import tqdm

ORACLE_FILE = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/data/longmemeval_oracle.json"
TARGET_DIR = "/Users/motonishikoudai/verantyx-cli/verantyx-browser/.ronin/jcross_v6_bench"

def main():
    if not os.path.exists(TARGET_DIR):
        os.makedirs(TARGET_DIR)
        
    with open(ORACLE_FILE, 'r') as f:
        data = json.load(f)
        
    print(f"Ingesting {len(data)} sessions into JCross V6 nodes...")
    
    for i, item in enumerate(tqdm(data)):
        session_id = f"bench_q{i}"
        
        # Flatten the session into a single text block
        # (LongMemEval haystacks are often provided in a 'sessions' list or similar)
        # Here we use the raw messages provided in the oracle sample
        history = ""
        for s in item.get('sessions', []):
            for m in s:
                role = m.get('role', 'user').upper()
                content = m.get('content', '')
                history += f"{role}: {content}\n"
        
        # Heuristic L1 Summary: First 300 chars + First role
        summary = history[:300].replace('\n', ' ')
        
        # Construct V6 JCross
        node_content = f"""■ JCROSS_NODE_{session_id}

【空間座相】
[渇:0.1] [認:0.9] [誠:0.7]

【次元概念】
Oracle Session {i}: {item['question'][:100]}

【領域】
personal_memory

【時間刻印】
2023-01-01T12:00:00Z

---
[L1_Cache]
Keywords: benchmark, oracle, {session_id}
Summary: {summary}

[L2_Archive]
{history}
===
"""
        with open(os.path.join(TARGET_DIR, f"{session_id}.jcross"), "w") as f:
            f.write(node_content)

    print(f"Successfully ingested {len(data)} nodes to {TARGET_DIR}")

if __name__ == "__main__":
    main()
