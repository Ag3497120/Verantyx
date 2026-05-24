import os
import json
import time
import requests
from tqdm import tqdm

API_KEY = "AIzaSyBxkFg8k95WLa2M3XrX0_b8pcbmLhg24Zo" 
OUTPUT_FILE = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/hypothesis_blind_test_v4.jsonl"

def eval_with_gemini(hyp, gt):
    prompt = f"You are a strict evaluator. Does the 'Hypothesis' correctly match or imply the 'Ground Truth'?\nGround Truth: {gt}\nHypothesis: {hyp}\nRespond YES or NO."
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent?key={API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        res = requests.post(url, json=payload)
        if res.status_code == 200:
            text = res.json()['candidates'][0]['content']['parts'][0]['text']
            return 'YES' in text.upper()
        else:
            print(f"Error {res.status_code}: {res.text}")
            return False
    except Exception as e:
        print(f"Exception: {e}")
        return False

# Evaluate 5 for testing
with open(OUTPUT_FILE, 'r') as f:
    lines = f.readlines()[:5]
for line in lines:
    item = json.loads(line)
    print(item['hypothesis'][:50], eval_with_gemini(item['hypothesis'], item['ground_truth']))

