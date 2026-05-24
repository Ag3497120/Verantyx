import json
import requests
import re
import os
import time
from tqdm import tqdm
from src.verantyx.cross_engine.jcross_v4_parser import JCrossParser

OLLAMA_URL = "http://localhost:11434/v1/chat/completions"
MODEL = "verantyx-gemma"
DB_PATH = "/Users/motonishikoudai/verantyx-cli/jcross-memory/data/jcross_mcp.json"
CHALLENGE_FILE = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/challenge_20.json"
OUTPUT_FILE = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/hypothesis_blind_test_v4.jsonl"

def read_jcross_memory(query):
    if not os.path.exists(DB_PATH):
        return "Memory storage not found."
    
    with open(DB_PATH, 'r') as f:
        db = json.load(f)
    
    keywords = [w.lower().strip(",.?!") for w in query.split() if len(w) > 2]
    if not keywords: return f"Query '{query}' too short."
        
    scored_nodes = []
    for node in db['nodes']:
        score = sum(1 for kw in keywords if kw in node.lower())
        if score > 0: scored_nodes.append((score, node))
            
    scored_nodes.sort(key=lambda x: x[0], reverse=True)
    if not scored_nodes: return f"No info found for keywords: {keywords}"
    return "\n---\n".join([n for s, n in scored_nodes[:5]])

def run_react_loop(question):
    messages = [{"role": "user", "content": question}]
    for turn in range(5): 
        response = requests.post(OLLAMA_URL, json={
            "model": MODEL, "messages": messages, "temperature": 0
        }).json()
        content = response['choices'][0]['message']['content']
        messages.append({"role": "assistant", "content": content})
        
        action_match = re.search(r"Action: ([\w_]+)", content)
        input_match = re.search(r"Action Input: ({.*?})", content, re.DOTALL)
        
        if action_match and input_match:
            action = action_match.group(1)
            try:
                action_input = json.loads(input_match.group(1))
                query = action_input.get("query", "")
                print(f"  [Turn {turn+1}] 🔍 Searching: {query}")
                observation = read_jcross_memory(query)
                messages.append({"role": "user", "content": f"Observation: {observation}\n\n(If you have enough information, write 'Final Answer: [your answer]', otherwise search again)"})
            except Exception as e:
                messages.append({"role": "user", "content": f"Observation: Tool Input Error: {e}"})
        else:
            break
            
    final_match = re.search(r"Final Answer: (.*)", content, re.DOTALL)
    if final_match: return final_match.group(1).strip()
    return content.strip()

def main():
    challenge = json.load(open(CHALLENGE_FILE))
    results = []
    for item in tqdm(challenge):
        print(f"\nEvaluating: {item['question_id']}")
        hypothesis = run_react_loop(item['question'])
        print(f"  Result: {hypothesis}")
        results.append({
            "question_id": item['question_id'],
            "hypothesis": hypothesis,
            "ground_truth": item['ground_truth']
        })
        with open(OUTPUT_FILE, 'a') as f: f.write(json.dumps(results[-1]) + "\n")

if __name__ == "__main__": main()
