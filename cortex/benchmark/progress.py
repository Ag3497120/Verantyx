#!/usr/bin/env python3
"""
progress.py — LongMemEval benchmark progress & accuracy checker.
Usage: python3 progress.py
"""
import json, os, sys

DB_PATH  = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/data/longmemeval_s_cleaned.json"
OUT_PATH = "/Users/motonishikoudai/verantyx-cli/_verantyx-cortex/benchmark/gemma4_agent_results.json"

db = json.load(open(DB_PATH, encoding="utf-8"))[:500]
total = len(db)

if not os.path.exists(OUT_PATH):
    print(f"[0/{total}] 結果ファイルなし。まだ開始していません。")
    sys.exit(0)

results  = json.load(open(OUT_PATH, encoding="utf-8"))
done     = len(results)
pct_done = done / total * 100

db_map = {str(q.get("question_id") or q.get("id")): q for q in db}

correct   = 0
incorrect = []
not_found = 0

for r in results:
    rid    = str(r.get("id") or r.get("question_id"))
    agent  = str(r.get("answer_agent", "")).strip()
    q      = db_map.get(rid)
    if not q:
        continue
    expected = str(q["answer"]).strip()

    if agent == "NOT_FOUND":
        not_found += 1
        continue

    ok = (expected.lower() in agent.lower()) or (agent.lower() in expected.lower())
    if ok:
        correct += 1
    else:
        incorrect.append({
            "id":       rid,
            "expected": expected,
            "agent":    agent,
            "q":        q["question"]
        })

answered   = done - not_found
accuracy   = correct / answered * 100 if answered > 0 else 0
remaining  = total - done

print("=" * 55)
print(f"  📊 LongMemEval Progress — Gemma4:26b Agent")
print("=" * 55)
print(f"  完了:        {done:>4} / {total}  ({pct_done:.1f}%)")
print(f"  残り:        {remaining:>4} 問")
print(f"  正答:        {correct:>4} 問")
print(f"  誤答:        {len(incorrect):>4} 問")
print(f"  未発見:      {not_found:>4} 問 (NOT_FOUND)")
print(f"")
print(f"  ✅ 正答率:   {correct}/{answered} = {accuracy:.1f}%")
print("=" * 55)

# Show last 5 answers
print("\n  🔁 直近5件:")
for r in results[-5:]:
    rid   = str(r.get("id") or r.get("question_id"))
    agent = r.get("answer_agent", "")[:50]
    q     = db_map.get(rid)
    exp   = q["answer"] if q else "?"
    ok    = (exp.lower() in str(r.get("answer_agent","")).lower()) or (str(r.get("answer_agent","")).lower() in exp.lower())
    mark  = "✅" if ok else "❌"
    print(f"  {mark} {rid[:8]} | expected='{exp}' | agent='{agent}'")

# Show wrong answers
if incorrect:
    print(f"\n  ❌ 誤答一覧 ({len(incorrect)}件):")
    for x in incorrect[-10:]:
        print(f"     ID={x['id'][:8]} | Q: {x['q'][:50]}")
        print(f"             expected='{x['expected']}' | agent='{x['agent'][:50]}'")
