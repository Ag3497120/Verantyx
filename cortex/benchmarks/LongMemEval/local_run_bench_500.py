import json
import os
import requests
import subprocess
from tqdm import tqdm

ORACLE_FILE = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/data/longmemeval_m_cleaned.json"
HYDRATED_DIR = "/Users/motonishikoudai/verantyx-cli/verantyx-browser/.ronin/jcross_v6_bench_local"
QUERY_BIN = "/Users/motonishikoudai/verantyx-cli/verantyx-browser/target/debug/examples/query_jcross"
MODEL = "gemma4:26b"
OLLAMA_URL = "http://localhost:11434/api/generate"

FINAL_REPORT = "official_v6_accuracy_report.json"

REASON_PROMPT = """You are the Verantyx Commander [Gemma 4 Edition].
Answer the following question based ONLY on the provided memory nodes.
If the answer is not in the memory, state "I don't know".

Question:
{question}

Supporting Evidence:
{evidence}

Answer:
"""

def query_jcross(q_text):
    query_input = {"queries": [q_text], "limit": 5}
    try:
        res = subprocess.run([QUERY_BIN, json.dumps(query_input)], capture_output=True, text=True)
        if res.returncode == 0:
            return json.loads(res.stdout).get("results", [])
    except Exception:
        return []
    return []

def main():
    if not os.path.exists(HYDRATED_DIR):
        print("Hydrated directory not found!")
        return
        
    with open(ORACLE_FILE, 'r') as f:
        data = json.load(f)
        
    # Checkpointing Logic
    checkpoint_file = FINAL_REPORT + ".jsonl"
    processed_ids = set()
    if os.path.exists(checkpoint_file):
        with open(checkpoint_file, "r") as f:
            for line in f:
                processed_ids.add(json.loads(line)["id"])
    
    hits = 0
    if os.path.exists(checkpoint_file):
        with open(checkpoint_file, "r") as f:
            for line in f:
                if json.loads(line)["success"]: hits += 1
    
    total = len(data)

    print(f"Executing Local Forge Benchmark: {total} questions against {MODEL}...")
    print(f"Found {len(processed_ids)} existing results. Resuming...")

    for i in tqdm(range(total)):
        if i in processed_ids: continue
        
        item = data[i]
        question = item['question']
        ground_truth = item.get('answer', '')
        
        # 1. Search JCross
        evidence_nodes = query_jcross(question)
        evidence_text = "\n".join([f"[{n['key']}]: {n['content']}" for n in evidence_nodes])
        
        # 2. Reason
        try:
            payload = {
                "model": MODEL,
                "prompt": REASON_PROMPT.format(question=question, evidence=evidence_text),
                "stream": False
            }
            response = requests.post(OLLAMA_URL, json=payload, timeout=60)
            answer = response.json().get('response', '').strip()
        except Exception:
            answer = "ERROR"

        # 3. Simple Audit (Heuristic containment)
        success = str(ground_truth).lower() in str(answer).lower() if ground_truth is not None else False
        if success: hits += 1
        
        result = {
            "id": i,
            "question": question,
            "ground_truth": ground_truth,
            "answer": answer,
            "success": success
        }
        
        # Append to checkpoint
        with open(checkpoint_file, "a") as f:
            f.write(json.dumps(result) + "\n")

    # Final wrap up
    # Read all from checkpoint to final JSON
    all_results = []
    final_hits = 0
    with open(checkpoint_file, "r") as f:
        for line in f:
            res = json.loads(line)
            all_results.append(res)
            if res["success"]: final_hits += 1

    score = (final_hits / total) * 100
    print(f"\nFinal Local Score: {score:.2f}% ({final_hits}/{total})")
    
    with open(FINAL_REPORT, "w") as f:
        json.dump({"score": score, "details": all_results}, f, indent=2)

if __name__ == "__main__":
    main()
