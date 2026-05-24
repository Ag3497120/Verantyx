import json
import os
import re
import time
import subprocess
import requests
from tqdm import tqdm

API_KEY = "AIzaSyCQK2KITz6WJmyyiVAk-N08xx0MK6kFN9I"
MODEL = "gemini-3-flash-preview"
CHALLENGE_FILE = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/data/longmemeval_oracle.json"
OUTPUT_FILE = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/hypothesis_blind_test_v4.jsonl"
QUERY_BIN = "/Users/motonishikoudai/verantyx-cli/verantyx-browser/target/debug/examples/query_jcross"

def read_jcross_v4(query):
    if not os.path.exists(QUERY_BIN):
        return "Rust Cargo target not found."
    try:
        res = subprocess.run([QUERY_BIN, query], capture_output=True, text=True)
        if res.returncode != 0:
            return f"Rust Engine Error: {res.stderr}"
            
        data = json.loads(res.stdout)
        results = data.get("results", [])
        
        if not results:
            return f"No relevant information found for query: '{query}'"
            
        out = []
        for i, r in enumerate(results[:10]): # Top 10
            tags = " ".join(r.get('kanji_tags', []))
            key = r['key']
            
            # Event Horizon Truncation: System Core Shield
            if "vibration_api" in key or "Cargo" in key:
                out.append(f"[Result {i+1}]\nノード名: {key}.jcross\n状態: システムコアファイル\n※重力が強すぎるため本文は省略。これはユーザーの対話履歴ではありません。\n---")
            else:
                content = r['content']
                if len(content) > 1000:
                    content = content[:1000] + "\n...[TRUNCATED BEYOND EVENT HORIZON]..."
                out.append(f"[Result {i+1}]\nノード名: {key}.jcross\nタグ: {tags}\n本文:\n{content}\n---")
                
        return "\n".join(out)
    except Exception as e:
        return f"Error executing JCross engine: {e}"

def generate_with_gemini(messages):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"
    contents = []
    
    # Merge system prompt into first user message
    system_prompt = ""
    for msg in messages:
        if msg["role"] == "system":
            system_prompt = msg["content"]
            continue
            
        role = "user" if msg["role"] in ["user", "system"] else "model"
        
        text = msg["content"]
        if system_prompt and role == "user" and len(contents) == 0:
            text = f"{system_prompt}\n\nTask:\n{text}"
            
        contents.append({"role": role, "parts": [{"text": text}]})
        
    for attempt in range(5):
        try:
            res = requests.post(url, json={"contents": contents, "generationConfig": {"temperature": 0.0}}, headers={"Content-Type": "application/json"})
            if res.status_code == 200:
                data = res.json()
                return data['candidates'][0]['content']['parts'][0]['text']
            elif res.status_code == 429:
                time.sleep(2 ** attempt)
            else:
                print(f"Gemini API Error: {res.status_code} {res.text}")
                return ""
        except Exception as e:
            time.sleep(1)
            
    return ""

def run_react_loop(question):
    system_prompt = """あなたはVerantyx-Cortexの推論インターフェースです。
過去の会話履歴を一切持っていません（コンテキスト窓は物理的に閉じられています）。
提供された直近の検索結果（Observation）のみを信頼し、質問に答えなさい。

## 戦略的注意
- **クエリの重複禁止**: 'Past Queries' にリストされている単語で再検索しても、同じ結果しか得られません。必ず別のキーワード、あるいはより具体的な表現（例: 特定の月、個別の固有名詞など）を試してください。
- **情報不足の判断**: 3回以上検索しても手がかりが得られない場合は、推測せず「情報不足」として回答してください。

## フォーマット
Thought: 私はこの事実を正確に知らない。外部脳（JCross）を検索する必要がある。
Action: read_jcross_node
Action Input: {"query": "検索したいキーワード"}

(ツールの結果が返される)

Thought: 検索結果に基づき、質問に答える準備ができた。
Final Answer: 質問に対する具体的かつ正確な回答。"""
    
    past_queries = []
    latest_observation = None
    
    for turn in range(5):
        # Construct FRESH context for each turn (Strictly Blind)
        current_messages = [{"role": "system", "content": system_prompt}]
        
        user_content = f"Question: {question}\nSearch Attempt: {turn+1}/5"
        if past_queries:
            user_content += f"\n\nPast Queries (Already tried): {', '.join(past_queries)}"
            user_content += "\n(CRITICAL: These queries did not yield the answer. TRY DIFFERENT KEYWORDS.)"
        
        if latest_observation:
            user_content += f"\n\nLatest JCross Observation:\n{latest_observation}"
        else:
            user_content += "\n\n(No observation yet. Search required.)"
            
        current_messages.append({"role": "user", "content": user_content})
        
        content = generate_with_gemini(current_messages)
        if not content: break
        
        # Parse Action/Final Answer
        action_match = re.search(r"Action:\s*[\"]?([\w_]+)[\"]?", content, re.IGNORECASE)
        input_match = re.search(r"Action Input:\s*({.*?})", content, re.DOTALL | re.IGNORECASE)
        final_match = re.search(r"Final Answer:\s*(.*)", content, re.DOTALL | re.IGNORECASE)
        
        if final_match: 
            return final_match.group(1).strip()
            
        if action_match and input_match:
            try:
                # Handle potential JSON escaped strings if model hallucinated format
                raw_input = input_match.group(1)
                # Quick fix if it outputted \"
                if '\\"' in raw_input:
                    try: raw_input = json.loads(f'"{raw_input}"')
                    except: pass
                
                action_input = json.loads(raw_input)
                query = action_input.get("query", "")
                
                # Prevent duplicate queries in the breadcrumbs if possible
                if query not in past_queries:
                    past_queries.append(query)
                
                print(f"  [Turn {turn+1}] 🔍 Query: {query}")
                latest_observation = read_jcross_v4(query)
            except Exception as e:
                latest_observation = f"Tool Input Error: {e}"
        else:
            # If it didn't provide an action or final answer, it failed the ReAct contract
            if "Thought:" in content:
                # Give it one more chance or just use the thought
                continue
            break
            
    return content.strip()

def main():
    if os.path.exists(OUTPUT_FILE):
        os.remove(OUTPUT_FILE)
        
    challenge = json.load(open(CHALLENGE_FILE))
    results = []
    
    print(f"Starting V4 Benchmark with {MODEL} (Event Horizon Truncation Active)")
    for item in tqdm(challenge):
        hypothesis = run_react_loop(item['question'])
        results.append({
            "question_id": item['question_id'],
            "hypothesis": hypothesis,
            "ground_truth": item.get('ground_truth', item.get('answer', ''))
        })
        with open(OUTPUT_FILE, 'a') as f: 
            f.write(json.dumps(results[-1]) + "\n")

if __name__ == "__main__": 
    main()
