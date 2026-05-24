import os
import json
import time
import requests
import subprocess
from tqdm import tqdm

API_KEY = "AIzaSyCQK2KITz6WJmyyiVAk-N08xx0MK6kFN9I"
MODEL = "gemini-2.5-flash"
CHALLENGE_FILE = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/data/longmemeval_oracle.json"
OUTPUT_FILE = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/hypothesis_blind_test_v5.jsonl"
QUERY_BIN = "/Users/motonishikoudai/verantyx-cli/verantyx-browser/target/debug/examples/query_jcross"

def read_jcross_v5(queries, domain="personal_memory"):
    if isinstance(queries, str):
        queries = [queries]
    
    payload = {
        "queries": queries,
        "domain": domain,
        "limit": 10
    }
    
    try:
        res = subprocess.run([QUERY_BIN, json.dumps(payload)], capture_output=True, text=True)
        if res.returncode != 0:
            return f"Error querying JCross: {res.stderr}"
        
        data = json.loads(res.stdout)
        results = data.get('results', [])
        
        if not results:
            return f"No relevant information found for queries: {queries}"
            
        out = []
        for i, r in enumerate(results):
            tags = " ".join(r.get('kanji_tags', []))
            key = r['key']
            
            # Event Horizon Truncation: Strip system core bodies
            if "[核:1.0]" in tags:
                content = "[System Core File - Content Truncated to preserve focus]"
            else:
                content = r['content']
                
            out.append(f"[Result {i+1}] ノード名: {key}\n領域: {r.get('domain', 'unknown')}\nコンセプト: {r['concept']}\nタグ: {tags}\n本文:\n{content}")
            
        return "\n\n".join(out)
    except Exception as e:
        return f"Tool Error: {str(e)}"

def call_gemini(messages):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"
    payload = {
        "contents": [{"role": m["role"], "parts": [{"text": m["content"]}]} for m in messages],
        "generationConfig": {"temperature": 0.0}
    }
    
    for attempt in range(5):
        try:
            response = requests.post(url, json=payload, timeout=30)
            if response.status_code == 200:
                res_data = response.json()
                if 'candidates' in res_data and len(res_data['candidates']) > 0:
                    cand = res_data['candidates'][0]
                    if 'content' in cand and 'parts' in cand['content']:
                        return cand['content']['parts'][0]['text']
                    else:
                        print(f"Empty candidate or safety block: {cand.get('finishReason', 'unknown')}")
                        return "Error: Empty response due to safety or logic."
                else:
                    print(f"No candidates in response: {res_data}")
                    return "Error: No candidates found."
            elif response.status_code == 429:
                time.sleep(2 ** attempt)
            else:
                print(f"API Error: {response.status_code}")
                time.sleep(1)
        except Exception as e:
            print(f"Request Error: {e}")
            time.sleep(1)
    return "Error: Failed to get response from Gemini API"

def run_react_loop(question):
    system_prompt = """あなたはVerantyx-Cortexの推論インターフェース（V5）です。
過去の会話履歴を一切持っていません（コンテキスト窓は物理的に閉じられています）。
提供された直近の検索結果（Observation）のみを信頼し、質問に答えなさい。

## 戦略的注意（V5 プロトコル）
- **領域選択 (Domain)**: 基本的に 'personal_memory' 領域を検索してください。システム内部の情報のみが必要な場合を除き、ドメインを指定することでシステムノイズを遮断できます。
- **クエリ拡張 (Multi-Query)**: 一度に変更可能な複数の同義語を配列で指定できます。
    例: Action Input: {"queries": ["自転車", "サイクル", "メンテナンス"], "domain": "personal_memory"}
- **反省 (Reflection)**: 前回までの検索が失敗した理由を Thought 内で分析し、次のクエリに反映させてください。

## フォーマット
Thought: 私はこの事実を正確に知らない。外部脳（JCross）を検索する必要がある。前回のクエリ 'X' ではシステムのコードばかりがヒットしたため、ドメインを 'personal_memory' に絞り、キーワードを 'Y' に変更する。
Action: read_jcross_node
Action Input: {"queries": ["キーワード1", "キーワード2"], "domain": "personal_memory"}

(ツールの結果が返される)

Thought: 検索結果に基づき、質問に答える準備ができた。
Final Answer: 質問に対する具体的かつ正確な回答。"""
    
    past_attempts = [] # List of (queries, reflection)
    latest_observation = None
    
    for turn in range(5):
        user_content = f"Question: {question}\nAttempt: {turn+1}/5"
        
        full_prompt = system_prompt
        
        if past_attempts:
            user_content += "\n\n--- Work History (Breadcrumbs) ---"
            for i, (qs, ref) in enumerate(past_attempts):
                user_content += f"\nAttempt {i+1}: Queries={qs}\nReflection: {ref}"
        
        if latest_observation:
            user_content += f"\n\nLatest JCross Observation:\n{latest_observation}"
        else:
            user_content += "\n\n(No observation yet. Search required.)"
            
        current_messages = [
            {"role": "user", "content": f"{full_prompt}\n\n{user_content}"}
        ]
        
        response = call_gemini(current_messages)
        
        # Robust Extraction
        if "Final Answer:" in response:
            return response.split("Final Answer:")[-1].strip()
        
        # Parse Action
        try:
            # First look for JSON block
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                action_input_str = json_match.group(0)
                action_data = json.loads(action_input_str)
                queries = action_data.get("queries", [action_data.get("query", "error")])
                domain = action_data.get("domain", "personal_memory")
                
                # Extract Reflection from Thought
                thought = response.split("{")[0]
                if "Action:" in thought:
                    thought = thought.split("Action:")[0]
                thought = thought.replace("Thought:", "").strip()
                
                latest_observation = read_jcross_v5(queries, domain)
                past_attempts.append((queries, thought))
            elif "Action Input:" in response:
                action_input_str = response.split("Action Input:")[-1].strip()
                # ... same logic as before or just use the regex match ...
                latest_observation = "Format Error: Please provide Action Input as a JSON block { ... }"
            else:
                latest_observation = "No Action detected. Please use: Action: read_jcross_node\nAction Input: {\"queries\": [...], \"domain\": \"...\"}"
        except Exception as e:
            latest_observation = f"Parsing Error in Action Input: {str(e)}. Please use strict JSON."
            
    return "Error: Reach turn limit (5) without finding answer."

def main():
    if not os.path.exists(CHALLENGE_FILE):
        print("Challenge file not found.")
        return
        
    with open(CHALLENGE_FILE, 'r') as f:
        challenge = json.load(f)
        
    print(f"Starting V5 Benchmark with {MODEL} (Domain Isolation Active)")
    
    # We might want to clear output if restarting
    if os.path.exists(OUTPUT_FILE):
        os.remove(OUTPUT_FILE)
        
    results = []
    for item in tqdm(challenge):
        question = item['question']
        hypothesis = run_react_loop(question)
        
        results.append({
            "question_id": item['question_id'],
            "hypothesis": hypothesis,
            "ground_truth": item['answer']
        })
        
        with open(OUTPUT_FILE, 'a') as f:
            f.write(json.dumps(results[-1], ensure_ascii=False) + "\n")
            
    print(f"Benchmark V5 Complete. Output saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
