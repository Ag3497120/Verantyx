#!/usr/bin/env python3
"""
next_question.py — Step 1 helper for gemma4 benchmark agent.
Prints the next unanswered question and exits.
Usage: python3 next_question.py
"""
import json, os, sys

DB_PATH  = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/data/longmemeval_s_cleaned.json"
OUT_PATH = "/Users/motonishikoudai/verantyx-cli/_verantyx-cortex/benchmark/gemma4_agent_results.json"

db = json.load(open(DB_PATH, encoding="utf-8"))

done = set()
if os.path.exists(OUT_PATH):
    try:
        for x in json.load(open(OUT_PATH, encoding="utf-8")):
            qid = x.get("id") or x.get("question_id")
            if qid:
                done.add(str(qid))
    except Exception:
        pass

pending = []
for q in db[:500]:
    qid = str(q.get("id") or q.get("question_id") or "")
    if qid not in done:
        pending.append(q)

if not pending:
    print("ALL_DONE")
    sys.exit(0)

q = pending[0]
qid = q.get("id") or q.get("question_id")
question = q.get("question", "")
expected = q.get("answer", q.get("expected_answer", "?"))

print(f"ID: {qid}")
print(f"Q: {question}")
print(f"REMAINING: {len(pending)}")
