#!/usr/bin/env python3
"""
save_answer.py — Step 3 helper for gemma4 benchmark agent.
Usage: python3 save_answer.py <question_id> <answer>
"""
import json, os, sys

OUT_PATH = "/Users/motonishikoudai/verantyx-cli/_verantyx-cortex/benchmark/gemma4_agent_results.json"

if len(sys.argv) < 3:
    print("Usage: python3 save_answer.py <question_id> <answer>")
    sys.exit(1)

qid    = sys.argv[1]
answer = " ".join(sys.argv[2:])

existing = []
if os.path.exists(OUT_PATH):
    try:
        existing = json.load(open(OUT_PATH, encoding="utf-8"))
    except Exception:
        pass

# Avoid duplicates
existing = [x for x in existing if str(x.get("id") or x.get("question_id")) != str(qid)]
existing.append({"id": qid, "answer_agent": answer})

with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(existing, f, indent=2, ensure_ascii=False)

print(f"SAVED: {qid} -> {answer[:80]}")
print(f"TOTAL: {len(existing)}")
