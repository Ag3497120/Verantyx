#!/usr/bin/env python3
"""
Phase 1: ingest_sessions.py
Loads ALL unique haystack_sessions from LongMemEval into JCross deep/ zone.
Each session becomes one JCross node with OP commands extracted from USER turns.

Runtime: ~30-60 seconds (pure file I/O, no LLM required)
"""
import json, os, re, sys, time

DB_PATH    = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/data/longmemeval_s_cleaned.json"
MEMORY_DIR = os.path.expanduser("~/.verantyx/memory/deep")

KANJI_KEYWORDS = {
    "職": ["work","job","company","office","career","commute","boss","colleague","salary"],
    "健": ["health","doctor","hospital","exercise","gym","yoga","diet","sleep","weight"],
    "食": ["food","restaurant","eat","cook","meal","recipe","coffee","drink","lunch"],
    "娯": ["movie","film","book","music","game","hobby","travel","vacation","concert"],
    "技": ["code","software","app","computer","tech","programming","python","api"],
    "人": ["friend","family","partner","sister","brother","mother","father","husband","wife"],
    "場": ["home","house","apartment","city","neighborhood","store","gym","park"],
    "時": ["morning","evening","daily","weekly","schedule","routine","minutes","hours"],
    "商": ["buy","price","cost","money","budget","shop","purchase","rent","subscription"],
    "記": ["remember","forgot","past","history","used to","years ago","recently"],
}

def assign_kanji(text: str) -> str:
    text_lower = text.lower()
    scores = {}
    for kanji, kws in KANJI_KEYWORDS.items():
        score = sum(1 for kw in kws if kw in text_lower)
        if score > 0:
            scores[kanji] = min(score / 3, 1.0)
    if not scores:
        scores["記"] = 0.5
    tags = sorted(scores.items(), key=lambda x: -x[1])[:4]
    return " ".join(f"[{k}: {v:.1f}]" for k, v in tags)

def extract_ops(session: list, session_id: str) -> list:
    ops = [f'OP.SESSION_ID("{session_id}")']
    for turn in session:
        role    = turn.get("role", "")
        content = turn.get("content", "")
        has_ans = turn.get("has_answer", False)
        if role == "user" and content:
            # Extract short phrases as facts
            excerpt = content[:300].replace('"', "'")
            if has_ans:
                ops.append(f'OP.ANSWER_FACT("{excerpt}")')
            else:
                short = content[:120].replace('"', "'")
                ops.append(f'OP.MEMORY("{short}")')
    return ops

def extract_l1_summary(session: list, session_id: str) -> str:
    user_turns = [t["content"][:80] for t in session if t.get("role") == "user"]
    preview = " | ".join(user_turns[:2]) if user_turns else session_id
    return preview[:100].replace('"', "'")

def session_to_jcross(session_id: str, session: list, timestamp: int) -> str:
    full_text_parts = []
    for turn in session:
        role    = turn.get("role","").upper()
        content = turn.get("content","")[:400]
        has_ans = " [HAS_ANSWER]" if turn.get("has_answer") else ""
        full_text_parts.append(f"[{role}{has_ans}]: {content}")
    full_text = "\n\n".join(full_text_parts)[:3000]

    kanji    = assign_kanji(full_text)
    ops      = extract_ops(session, session_id)
    l1sum    = extract_l1_summary(session, session_id)

    # L1.5 index
    top_kanji = re.findall(r'\[(\S+?):', kanji)
    kanji_str = "".join(top_kanji[:3]) or "記"
    l15 = f'[{kanji_str}] | "{l1sum[:55]}"'

    return f"""■ JCROSS_SESSION_{timestamp}
【空間座相】
{kanji}

【L1.5索引】
{l15}

【位相対応表】
[標] := "{l1sum}"
[SESSION] := "{session_id}"

【操作対応表】
{chr(10).join(ops)}

【原文】
{full_text}
""".strip() + "\n"

def main():
    os.makedirs(MEMORY_DIR, exist_ok=True)

    print(f"📂 Loading dataset...")
    db = json.load(open(DB_PATH, encoding="utf-8"))[:500]

    # Collect unique sessions
    print(f"🔍 Deduplicating sessions...")
    unique = {}
    for q in db:
        for sid, session in zip(q["haystack_session_ids"], q["haystack_sessions"]):
            if sid not in unique:
                unique[sid] = session
    total = len(unique)
    print(f"   → {total} unique sessions to ingest")

    # Check already ingested
    existing = set()
    if os.path.exists(MEMORY_DIR):
        for f in os.listdir(MEMORY_DIR):
            if f.endswith(".jcross"):
                content = open(os.path.join(MEMORY_DIR, f)).read()
                m = re.search(r'OP\.SESSION_ID\("([^"]+)"\)', content)
                if m:
                    existing.add(m.group(1))
    print(f"   → Already ingested: {len(existing)} sessions")

    todo = {sid: sess for sid, sess in unique.items() if sid not in existing}
    print(f"   → To ingest: {len(todo)} sessions\n")

    if not todo:
        print("✅ All sessions already ingested!")
        return

    start  = time.time()
    count  = 0
    errors = 0

    for sid, session in todo.items():
        try:
            timestamp = int(time.time() * 1000) + count
            content   = session_to_jcross(sid, session, timestamp)
            # Sanitize filename
            fname = re.sub(r'[^a-zA-Z0-9_\-]', '_', sid) + ".jcross"
            path  = os.path.join(MEMORY_DIR, fname)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            count += 1
            if count % 1000 == 0:
                elapsed = time.time() - start
                rate    = count / elapsed
                eta     = (len(todo) - count) / rate
                print(f"  [{count}/{len(todo)}] {elapsed:.0f}s elapsed | ETA: {eta:.0f}s")
        except Exception as e:
            errors += 1

    elapsed = time.time() - start
    print(f"\n✅ Ingestion complete!")
    print(f"   Saved: {count} nodes → {MEMORY_DIR}")
    print(f"   Errors: {errors}")
    print(f"   Time: {elapsed:.1f}s")
    print(f"\n🚀 Next: run Phase 2:")
    print(f"   python3 run_mcp_benchmark.py")

if __name__ == "__main__":
    main()
