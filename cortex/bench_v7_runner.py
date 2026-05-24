import json
import os
import shutil
import requests
import subprocess
import re
from tqdm import tqdm

ORACLE_FILE = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/data/longmemeval_m_cleaned.json"
TARGET_DIR = "/Users/motonishikoudai/verantyx-cli/verantyx-browser/.ronin/jcross_v7"
QUERY_BIN = "/Users/motonishikoudai/verantyx-cli/verantyx-browser/target/release/examples/query_jcross"
MODEL = "gemma4:26b"
OLLAMA_URL = "http://localhost:11434/api/generate"

FINAL_REPORT = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/official_v7_accuracy_report.json"

SYSTEM_PROMPT = """[System Directive]
You are Verantyx Cortex (V7 Edition). 
Answer the following bench question based ONLY on the dynamically fetched memory chunks.
If the answer is completely missing, say "I don't know".

[Output Format]
<jcross_cognition>
■ JCROSS_NODE_current
【空間座相】 [Z:0]
【次元概念】 (Tag key entities inside the question and response)
[本質記憶]
//! {{question}}
//! {{response_summary}}
</jcross_cognition>

<response>
(Your specific concise final answer here)
</response>

Question:
{question}

Dynamically Fetched L2 Raw Chunks:
{evidence}
"""

def chunk_and_write_haystack(haystack_text, chunk_size=2000):
    if os.path.exists(TARGET_DIR):
        shutil.rmtree(TARGET_DIR)
    os.makedirs(TARGET_DIR)

    # Fast slicing
    chunks = [haystack_text[i:i+chunk_size] for i in range(0, len(haystack_text), chunk_size)]
    
    for idx, c in enumerate(chunks):
        filepath = os.path.join(TARGET_DIR, f"tm_idx_{idx}.jcross")
        with open(filepath, "w") as f:
            f.write(f"■ JCROSS_NODE_idx_{idx}\n")
            f.write("【空間座相】 [Z:0]\n")
            f.write(f"[本質記憶]\n{c}\n===\n")

def query_jcross(q_text, limit=5):
    query_input = {"queries": [q_text], "limit": limit}
    try:
        res = subprocess.run([QUERY_BIN, json.dumps(query_input)], capture_output=True, text=True, env={**os.environ, "JCROSS_TARGET_DIR": TARGET_DIR})
        if res.returncode == 0:
            out_lines = res.stdout.strip().split('\n')
            for line in reversed(out_lines):
                if line.strip().startswith('{'):
                    try:
                        return json.loads(line).get("results", [])
                    except json.JSONDecodeError:
                        continue
            return []
    except Exception as e:
        print(f"[Rust Error]: {e}")
    return []

def main():
    print("Loading Oracle...")
    with open(ORACLE_FILE, 'r') as f:
        data = json.load(f)
        
    checkpoint_file = FINAL_REPORT + ".jsonl"
    processed_ids = set()
    hits = 0
    
    jsonl_file = FINAL_REPORT + ".jsonl"
    if os.path.exists(jsonl_file):
        with open(jsonl_file, "r") as f:
            for line in f:
                if line.strip():
                    try:
                        item = json.loads(line)
                        processed_ids.add(item["id"])
                        if item["success"]: hits += 1
                    except json.JSONDecodeError:
                        continue
    
    total = len(data)
    print(f"Executing V7 Zero-Phase Benchmark: {total} questions against {MODEL}...")
    print(f"Found {len(processed_ids)} existing results. Resuming...")

    for i in tqdm(range(total)):
        if i in processed_ids: continue
        
        item = data[i]
        question = item['question']
        ground_truth = item.get('answer', '')
        haystack = item.get('haystack_sessions', '')
        
        # 1. Zero-Phase Fast Chunking (Rebuilding the physical context array instantly)
        if isinstance(haystack, list):
            haystack_text = "\\n".join([str(h) for h in haystack])
        else:
            haystack_text = str(haystack)
            
        chunk_and_write_haystack(haystack_text, 2000)
        
        # 2. Rust BM25 Deep Memory Search on raw chunks
        evidence_nodes = query_jcross(question, limit=5)
        evidence_text = "\\n\\n".join([f"--- Chunk [{n['key']}] ---\\n{n['content']}" for n in evidence_nodes])
        
        # 3. Gemma 4 Real-time Compression + Reasoning
        try:
            payload = {
                "model": MODEL,
                "prompt": SYSTEM_PROMPT.format(question=question, evidence=evidence_text),
                "stream": False,
                "options": {"temperature": 0.2}
            }
            res = requests.post(OLLAMA_URL, json=payload, timeout=90)
            raw_answer = res.json().get('response', '').strip()
            
            resp_match = re.search(r"<response>(.*?)</response>", raw_answer, re.DOTALL)
            answer = resp_match.group(1).strip() if resp_match else raw_answer
        except Exception as e:
            import traceback; traceback.print_exc()
            answer = "ERROR"

        # Simple verification
        success = str(ground_truth).lower() in str(answer).lower() if ground_truth is not None else False
        if success: hits += 1
        
        result = {
            "id": i,
            "question": question,
            "ground_truth": ground_truth,
            "answer": answer,
            "success": success
        }
        
        with open(checkpoint_file, "a") as f:
            f.write(json.dumps(result) + "\n")
            
        # Log first few thoughts to confirm it's working
        if i < 3:
            print(f"\\n--- [V7 Cortex Log: Q{i}] ---")
            print(f"Q: {question}\\nTrue: {ground_truth}\\nPred: {answer}")
            print(f"Hit 5 chunks. Example top chunk keys: {[n['key'] for n in evidence_nodes]}")

    all_results = []
    final_hits = 0
    if os.path.exists(checkpoint_file):
        with open(checkpoint_file, "r") as f:
            for line in f:
                res = json.loads(line)
                all_results.append(res)
                if res["success"]: final_hits += 1

    score = (final_hits / total) * 100
    print(f"\\nV7 Zero-Phase Cortex Score: {score:.2f}% ({final_hits}/{total})")
    
    with open(FINAL_REPORT, "w") as f:
        json.dump({"score": score, "details": all_results}, f, indent=2)

if __name__ == "__main__":
    main()
