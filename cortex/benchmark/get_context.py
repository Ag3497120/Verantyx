#!/usr/bin/env python3
"""
get_context.py — Step 2 helper: keyword search over haystack_sessions.
Usage: python3 get_context.py <question_id> <keyword1> [keyword2] ...
Returns the most relevant session turns containing the keywords.
"""
import json, os, sys, re

DB_PATH = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/data/longmemeval_s_cleaned.json"

if len(sys.argv) < 3:
    print("Usage: python3 get_context.py <question_id> <keyword1> [keyword2]...")
    sys.exit(1)

qid      = sys.argv[1]
keywords = [k.lower() for k in sys.argv[2:]]

db = json.load(open(DB_PATH, encoding="utf-8"))
q  = next((x for x in db if str(x.get("question_id") or x.get("id")) == qid), None)

if not q:
    print(f"ERROR: question_id '{qid}' not found")
    sys.exit(1)

print(f"Q: {q['question']}")
print(f"Searching {len(q['haystack_sessions'])} sessions for: {keywords}")
print("=" * 60)

hits = []
for sid, session in zip(q["haystack_session_ids"], q["haystack_sessions"]):
    for turn in session:
        content = turn.get("content", "").lower()
        score   = sum(1 for kw in keywords if kw in content)
        if score > 0:
            hits.append((score, sid, turn["role"], turn["content"]))

# Sort by score and show top 5
hits.sort(key=lambda x: -x[0])
if not hits:
    print("NO HITS — try different keywords")
else:
    for score, sid, role, content in hits[:5]:
        print(f"\n[score={score} | session={sid} | {role.upper()}]")
        print(content[:600])
        print("-" * 40)
