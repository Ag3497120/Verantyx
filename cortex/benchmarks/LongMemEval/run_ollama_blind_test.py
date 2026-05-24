import json
import requests
import re
import os
import time
from tqdm import tqdm

OLLAMA_URL = "http://localhost:11434/v1/chat/completions"
MODEL = "verantyx-gemma"
DB_PATH = "/Users/motonishikoudai/verantyx-cli/jcross-memory/data/jcross_mcp.json"
CHALLENGE_FILE = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/challenge_20.json"
OUTPUT_FILE = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/hypothesis_blind_test.jsonl"

def read_jcross_memory(query):
    if not os.path.exists(DB_PATH):
        return "Memory storage not found."
    
    with open(DB_PATH, 'r') as f:
        db = json.load(f)
    
    # Improved keyword-based search
    keywords = [w.lower().strip(",.?!") for w in query.split() if len(w) > 2]
    if not keywords:
        return f"Query '{query}' too short for analysis."
        
    scored_nodes = []
    for node in db['nodes']:
        score = sum(1 for kw in keywords if kw in node.lower())
        if score > 0:
            scored_nodes.append((score, node))
            
    scored_nodes.sort(key=lambda x: x[0], reverse=True)
    
    if not scored_nodes:
        return f"No relevant information found for keywords: {keywords}"
    
    # Return top 5 matches
    return "\n---\n".join([n for s, n in scored_nodes[:5]])

def run_react_loop(question):
    messages = [
        {"role": "user", "content": question}
    ]
    
    for _ in range(3):  # Max 3 turns
        response = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "messages": messages,
            "temperature": 0
        }).json()
        
        content = response['choices'][0]['message']['content']
        messages.append({"role": "assistant", "content": content})
        
        # Parse Action
        action_match = re.search(r"Action: ([\w_]+)", content)
        input_match = re.search(r"Action Input: ({.*?})", content)
        
        if action_match and input_match:
            action = action_match.group(1)
            try:
                action_input = json.loads(input_match.group(1))
                query = action_input.get("query", "")
            except:
                query = ""
                
            if action == "read_jcross_node":
                print(f"  [Tool Call] read_jcross_node: '{query}'")
                observation = read_jcross_memory(query)
                messages.append({"role": "user", "content": f"Observation: {observation}"})
            else:
                break # Unknown tool
        else:
            # No more tool calls, assume final answer
            break
            
    # Extract Final Answer
    final_match = re.search(r"Final Answer: (.*)", content, re.DOTALL)
    if final_match:
        return final_match.group(1).strip()
    return content.strip()

def main():
    with open(CHALLENGE_FILE, 'r') as f:
        challenge = json.load(f)
    
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
        
        # Save incrementally
        with open(OUTPUT_FILE, 'a') as f:
            f.write(json.dumps(results[-1]) + "\n")

    print(f"\nTesting complete. Results saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
