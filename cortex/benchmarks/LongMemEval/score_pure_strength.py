import os
import json
import time
import requests
from tqdm import tqdm

API_KEY = "AIzaSyCQK2KITz6WJmyyiVAk-N08xx0MK6kFN9I"
MODEL = "gemini-3-flash-preview"
HYP_FILE = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/hypothesis_blind_test_v4.jsonl"
REPORT_FILE = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/final_report_v4.json"

def eval_correctness(hyp, gt):
    if not hyp.strip() or "情報不足" in hyp or "I do not have enough information" in hyp:
        return False
        
    prompt = f"""You are a strict judge. Compare the AI's Hypothesis to the Ground Truth.
    
Ground Truth: {gt}
Hypothesis: {hyp}

Does the Hypothesis correctly state the key fact from the Ground Truth? 
Respond with ONLY 'CORRECT' or 'INCORRECT'."""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.0}}
    
    for attempt in range(3):
        try:
            res = requests.post(url, json=payload, timeout=20)
            if res.status_code == 200:
                text = res.json()['candidates'][0]['content']['parts'][0]['text'].strip().upper()
                return "CORRECT" in text and "INCORRECT" not in text
            time.sleep(1)
        except:
            time.sleep(1)
    return False

def main():
    if not os.path.exists(HYP_FILE):
        print("Hypothesis file not found.")
        return
        
    correct = 0
    total = 0
    
    with open(HYP_FILE, 'r') as f:
        lines = f.readlines()
        
    print(f"Scoring {len(lines)} questions via Gemini 3 Flash Judge...")
    for line in tqdm(lines):
        data = json.loads(line)
        total += 1
        if eval_correctness(data['hypothesis'], data['ground_truth']):
            correct += 1
            
    score = (correct / total) * 100 if total > 0 else 0
    report = {
        "total": total,
        "correct": correct,
        "accuracy": score
    }
    
    with open(REPORT_FILE, 'w') as f:
        json.dump(report, f, indent=2)
        
    print(f"\nFinal Accuracy: {score:.2f}% ({correct}/{total})")

if __name__ == "__main__":
    main()
