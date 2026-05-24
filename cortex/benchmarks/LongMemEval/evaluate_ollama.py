import json
import requests
from tqdm import tqdm

OLLAMA_URL = "http://localhost:11434/v1/chat/completions"
MODEL = "verantyx-gemma"
OUTPUT_FILE = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/hypothesis_blind_test_v4.jsonl"

def eval_with_ollama(hyp, gt):
    if not hyp.strip() or "I do not have enough information" in hyp:
        return False
        
    prompt = f"Ground Truth: {gt}\nHypothesis: {hyp}\nIs the Hypothesis essentially the same answer as the Ground Truth? Answer with ONLY YES or NO."

    try:
        res = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": 10
        }, timeout=30)
        
        if res.status_code == 200:
            text = res.json()['choices'][0]['message']['content'].strip()
            print(f"GT: {gt} | HYP: {hyp[:30]} | ANS: {text}")
            return 'YES' in text.upper()
        else:
            return False
    except Exception as e:
        return False

with open(OUTPUT_FILE, 'r') as f:
    lines = f.readlines()[:5]

for line in lines:
    item = json.loads(line)
    eval_with_ollama(item['hypothesis'], item['ground_truth'])
