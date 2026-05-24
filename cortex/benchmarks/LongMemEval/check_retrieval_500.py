import os
import json
import subprocess
from tqdm import tqdm

CHALLENGE_FILE = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/data/longmemeval_oracle.json"
QUERY_BIN = "/Users/motonishikoudai/verantyx-cli/verantyx-browser/target/debug/examples/query_jcross"

def main():
    with open(CHALLENGE_FILE, 'r') as f:
        data = json.load(f)
    
    hits = 0
    total = 500
    results = []

    print(f"Checking Retrieval Accuracy for {total} questions...")
    
    for i in tqdm(range(total)):
        item = data[i]
        question = item['question']
        target_ids = item['answer_session_ids']
        
        # Simple keyword extraction for the query
        # In a real ReAct loop, the LLM would do this.
        # Here we simulate the first turn search.
        query_input = {"queries": [question], "domain": "personal_memory", "limit": 10}
        
        try:
            res = subprocess.run([QUERY_BIN, json.dumps(query_input)], capture_output=True, text=True)
            if res.returncode == 0:
                out = json.loads(res.stdout)
                found_keys = [r['key'] for r in out.get('results', [])]
                
                # Check if any of the target IDs are in the search results
                # Note: Session IDs in oracle might map to JCross keys 
                # e.g. answer_cc021f81_3 -> tm_cc021f81...
                # We check for substring matches or exact matches.
                success = False
                for tid in target_ids:
                    # Clean the ID (remove 'answer_')
                    clean_tid = tid.replace('answer_', '')
                    for k in found_keys:
                        if clean_tid in k or k in clean_tid:
                            success = True
                            break
                    if success: break
                
                if success:
                    hits += 1
                
                results.append({
                    "id": i,
                    "success": success,
                    "found": found_keys[:3],
                    "target": target_ids
                })
        except Exception as e:
            continue

    score = (hits / total) * 100
    print(f"\nRetrieval Accuracy: {score:.2f}% ({hits}/{total})")
    
    with open("retrieval_report_500.json", "w") as f:
        json.dump({"score": score, "details": results}, f, indent=2)

if __name__ == "__main__":
    main()
