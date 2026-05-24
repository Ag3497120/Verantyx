import json
import os
import requests
from tqdm import tqdm

ORACLE_FILE = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/data/longmemeval_oracle.json"
TARGET_DIR = "/Users/motonishikoudai/verantyx-cli/verantyx-browser/.ronin/jcross_v6_bench_local"
MODEL = "gemma4:26b"
OLLAMA_URL = "http://localhost:11434/api/generate"

INGEST_PROMPT = """You are a High-Density Memory Compressor for the JCross Cortex.
Extract a searchable L1 Cache summary from the following raw memory.
Follow this format strictly:
Keywords: [list key concepts]
Summary: [one-sentence essence]

Memory:
{raw_memory}
"""

def main():
    if not os.path.exists(TARGET_DIR):
        os.makedirs(TARGET_DIR)
        
    with open(ORACLE_FILE, 'r') as f:
        data = json.load(f)
        
    print(f"Locally Ingesting {len(data)} sessions into JCross V6 (using {MODEL})...")
    
    for i, item in enumerate(tqdm(data)):
        session_id = f"bench_q{i}"
        target_path = os.path.join(TARGET_DIR, f"{session_id}.jcross")
        
        if os.path.exists(target_path): continue

        history = ""
        for s in item.get('sessions', []):
            for m in s:
                role = m.get('role', 'user').upper()
                content = m.get('content', '')
                history += f"{role}: {content}\n"
        
        # Call Local Ollama for L1 Extraction
        try:
            payload = {
                "model": MODEL,
                "prompt": INGEST_PROMPT.format(raw_memory=history[:4000]), # Context limit safe
                "stream": False
            }
            response = requests.post(OLLAMA_URL, json=payload, timeout=30)
            distillation = response.json().get('response', 'Keywords: unknown\nSummary: no data').strip()
        except Exception:
            distillation = f"Keywords: {session_id}\nSummary: Processing error."

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
{distillation}

[L2_Archive]
{history}
===
"""
        with open(target_path, "w") as f:
            f.write(node_content)

    print(f"Successfully local-hydrated {len(data)} nodes to {TARGET_DIR}")

if __name__ == "__main__":
    main()
