import json
import os
import subprocess
from tqdm import tqdm

CHALLENGE_FILE = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/data/longmemeval_oracle.json"
QUERY_BIN = "/Users/motonishikoudai/verantyx-cli/verantyx-browser/target/debug/examples/query_jcross"
COUNT = 146

def main():
    with open(CHALLENGE_FILE, 'r') as f:
        data = json.load(f)
    
    hits = 0
    results = []

    print(f"Calculating Interim Retrieval Score for first {COUNT} nodes...")
    
    for i in tqdm(range(COUNT)):
        item = data[i]
        question = item['question']
        target_ids = item['answer_session_ids']
        
        query_input = {"queries": [question], "limit": 10}
        
        try:
            res = subprocess.run([QUERY_BIN, json.dumps(query_input)], capture_output=True, text=True)
            if res.returncode == 0:
                out = json.loads(res.stdout)
                found_keys = [r['key'] for r in out.get('results', [])]
                
                success = False
                for tid in target_ids:
                    clean_tid = tid.replace('answer_', '')
                    for k in found_keys:
                        if clean_tid in k or k in clean_tid:
                            success = True
                            break
                    if success: break
                
                if success:
                    hits += 1
        except Exception:
            continue

    score = (hits / COUNT) * 100 if COUNT > 0 else 0
    print(f"\nInterim Retrieval Score: {score:.2f}% ({hits}/{COUNT})")

if __name__ == "__main__":
    main()
