#!/usr/bin/env python3
import json, os

DB_PATH = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/data/longmemeval_s_cleaned.json"
db = json.load(open(DB_PATH))[:500]
db_map = {str(q.get("question_id") or q.get("id")): q for q in db}

files = [
    ("agentic_results.json",      "旧: Antigravity JCross検索"),
    ("mcp_agent_results.json",    "旧: MCP Agent"),
    ("trilayer_results.json",     "旧: Trilayer抽出"),
    ("flash_agent_results.json",  "旧: Flash Agent"),
    ("official_results.json",     "旧: 公式スコア計測"),
    ("gemma4_agent_results.json", "新: gemma4 + get_context直接検索"),
    ("gemma4_mcp_results.json",   "新: gemma4 + JCross MCP検索"),
]

base = "/Users/motonishikoudai/verantyx-cli/_verantyx-cortex/benchmark/"
print(f"{'ラベル':<34} {'完了':>5} {'正答':>5} {'正答率':>7}")
print("-" * 57)
for fname, label in files:
    path = base + fname
    if not os.path.exists(path):
        continue
    try:
        results = json.load(open(path))
        correct = 0
        answered = 0
        for r in results:
            rid = str(r.get("id") or r.get("question_id") or "")
            ans = str(r.get("answer_agent") or r.get("answer") or "")
            if not ans or ans in ("NOT_FOUND", "?"):
                continue
            q = db_map.get(rid)
            if not q:
                continue
            exp = q["answer"]
            if exp.lower() in ans.lower() or ans.lower() in exp.lower():
                correct += 1
            answered += 1
        pct = correct / answered * 100 if answered > 0 else 0
        print(f"{label:<34} {answered:>5} {correct:>5} {pct:>6.1f}%")
    except Exception as e:
        print(f"{label:<34} ERROR: {e}")
