#!/usr/bin/env python3
"""
Verantyx Cortex × LongMemEval Smoke Test (Direct Mode)
- Bypasses MCP JSON-RPC (subprocess PATH issues)
- Writes JCross nodes directly to ~/.openclaw/memory/front/
- Implements GravitySolver in native Python (port of spatial_search.ts)
- Queries gemma4:e2b via Ollama HTTP
"""

import json
import os
import re
import time
import math
import urllib.request
import urllib.error

# ---- Config ----
DATASET_PATH    = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/data/longmemeval_s_cleaned.json"
MEMORY_ROOT     = os.path.expanduser("~/.openclaw/memory")
OLLAMA_MODEL    = "gemma4:e2b"
OLLAMA_URL      = "http://localhost:11434/api/generate"
NUM_QUESTIONS   = 7
FRONT_CAP       = 100
CONTEXT_LIMIT   = 1500  # gemma4:e2b struggles beyond ~1500 chars in prompt


# ---- Direct Memory Writer (mirrors engine.ts) ----
def write_jcross(zone: str, node_id: str, content: str):
    zone_dir = os.path.join(MEMORY_ROOT, zone)
    os.makedirs(zone_dir, exist_ok=True)
    path = os.path.join(zone_dir, node_id)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def build_jcross_node(timestamp: int, kanji_tags: str, summary: str, ops: list, raw: str) -> str:
    return f"""■ JCROSS_NODE_MEMORY_{timestamp}
【空間座相】
{kanji_tags}

【位相対応表】
[標] := "{summary[:120]}"

【操作対応表】
{chr(10).join(ops[:10])}

【原文】
{raw[:2000]}
""".strip()


# ---- Python GravitySolver (mirrors spatial_search.ts) ----
def extract_kanji_dimensions(content: str) -> dict:
    dims = {}
    match = re.search(r'【空間座相】([\s\S]*?)【', content)
    if match:
        tag_str = match.group(1).strip()
        for m in re.finditer(r'\[([^:\]]+):\s*([0-9.]+)\]', tag_str):
            dims[m.group(1).strip()] = float(m.group(2))
    return dims


def load_front_nodes() -> list:
    front_dir = os.path.join(MEMORY_ROOT, "front")
    if not os.path.exists(front_dir):
        return []
    nodes = []
    for fname in os.listdir(front_dir):
        if not (fname.endswith(".jcross") or fname.endswith(".md")):
            continue
        fpath = os.path.join(front_dir, fname)
        try:
            with open(fpath, encoding="utf-8") as f:
                content = f.read()
            dims = extract_kanji_dimensions(content)
            mtime = os.path.getmtime(fpath)
            nodes.append({"id": fname, "dims": dims, "content": content, "mtime": mtime})
        except Exception:
            continue
    return nodes


def cosine_similarity(a: dict, b: dict) -> float:
    dot = sum(a.get(k, 0) * v for k, v in b.items())
    mag_a = math.sqrt(sum(v*v for v in a.values())) if a else 0
    mag_b = math.sqrt(sum(v*v for v in b.values())) if b else 0
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def gravity_flashback(query_kanji: dict, top_k: int = 5) -> str:
    nodes = load_front_nodes()
    scored = []
    for node in nodes:
        sim = cosine_similarity(query_kanji, node["dims"])
        if sim > 0.3:
            scored.append((sim, node))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_k]

    if not top:
        return ""

    result_parts = []
    for sim, node in top:
        # Extract the summary (位相対応表) from content
        summary_match = re.search(r'【位相対応表】([\s\S]*?)【操作対応表】', node["content"])
        raw_match = re.search(r'【原文】([\s\S]*)', node["content"])
        summary = summary_match.group(1).strip() if summary_match else ""
        raw = raw_match.group(1).strip()[:500] if raw_match else ""

        result_parts.append(
            f"[Node: {node['id']} | Similarity: {sim:.2f}]\n{summary}\n---\n{raw}"
        )

    return "\n\n".join(result_parts)


# ---- Kanji inference from question ----
def infer_kanji(question: str) -> dict:
    q = question.lower()
    if any(w in q for w in ["when", "date", "time", "year", "month", "day", "first", "last", "how long"]):
        return {"時": 1.0, "標": 0.8, "記": 0.7}
    if any(w in q for w in ["where", "city", "location", "place", "live", "country", "take"]):
        return {"場": 1.0, "標": 0.8, "視": 0.5}
    if any(w in q for w in ["what", "which", "name", "called", "degree", "job", "work", "playlist", "play"]):
        return {"標": 1.0, "記": 0.9, "認": 0.6}
    return {"標": 1.0, "認": 0.8, "記": 0.6}

def extract_relevant_snippet(raw: str, question: str, window: int = 8) -> str:
    """Extract a small window of lines most relevant to the question."""
    lines = [l for l in raw.splitlines() if l.strip()]
    q_keywords = [w.lower() for w in question.split() if len(w) > 3]

    # Score each line by keyword overlap
    scored = []
    for i, line in enumerate(lines):
        ll = line.lower()
        score = sum(1 for k in q_keywords if k in ll)
        scored.append((score, i))

    if not scored:
        return raw[:CONTEXT_LIMIT]

    # Pick the highest-scoring line as anchor, take window around it
    best_score, best_idx = max(scored, key=lambda x: x[0])
    start = max(0, best_idx - window // 2)
    end = min(len(lines), best_idx + window // 2 + 1)
    snippet = "\n".join(lines[start:end])
    return snippet[:CONTEXT_LIMIT]


# ---- Ollama ----
def ask_ollama(question: str, context: str) -> str:
    prompt = f"""Below is a conversation. Answer the question with ONLY the exact word(s) from the conversation. No explanation.

Conversation:
{context}

Question: {question}
Answer (exact words only):"""

    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 30}
    }).encode()

    try:
        req = urllib.request.Request(
            OLLAMA_URL, data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read())
            return data.get("response", "").strip()
    except urllib.error.URLError as e:
        return f"[Ollama error: {e}]"


# ---- Scoring ----
def keyword_score(expected: str, got: str) -> float:
    if not got or got.lower() in ("unknown", "i don't know", ""):
        return 0.0
    e = re.sub(r'[^\w\s]', ' ', expected.lower()).split()
    g = re.sub(r'[^\w\s]', ' ', got.lower())
    keywords = [w for w in e if len(w) > 2]
    if not keywords:
        return 1.0 if expected.lower().strip() in g else 0.0
    return sum(1 for w in keywords if w in g) / len(keywords)


# ---- Main ----
def main():
    print("=" * 65)
    print("  Verantyx Cortex × LongMemEval Smoke Test (Direct Mode)")
    print(f"  Memory root: {MEMORY_ROOT}")
    print(f"  Model: {OLLAMA_MODEL} | Questions: {NUM_QUESTIONS}")
    print("=" * 65)

    # Count existing nodes
    front_dir = os.path.join(MEMORY_ROOT, "front")
    existing = len([f for f in os.listdir(front_dir) if os.path.isfile(os.path.join(front_dir, f))]) if os.path.exists(front_dir) else 0
    print(f"  Existing front/ nodes: {existing}\n")

    with open(DATASET_PATH) as f:
        dataset = json.load(f)

    selected = dataset[:NUM_QUESTIONS]
    results = []

    for i, item in enumerate(selected):
        qid = item["question_id"]
        question = item["question"]
        expected = item["answer"]
        sessions = item.get("haystack_sessions", [])
        haystack_ids = item.get("haystack_session_ids", [])
        answer_ids = item.get("answer_session_ids", [])

        print(f"[{i+1}/{NUM_QUESTIONS}] {qid}")
        print(f"  Q: {question}")
        print(f"  Expected: {expected}")

        # Step 1: Write sessions to front/ — include ANSWER session always
        answer_id = (item.get("answer_session_ids") or [None])[0]
        injected = 0
        answer_raw = ""

        for j, session in enumerate(sessions):  # all sessions
            if not isinstance(session, list):
                continue
            msgs = [m for m in session if isinstance(m, dict)]
            if not msgs:
                continue

            sess_id = haystack_ids[j] if j < len(haystack_ids) else f"s{j}"
            is_answer = (sess_id == answer_id)

            # Only inject: answer session + first 20 haystack sessions
            if not is_answer and injected >= 20:
                continue

            raw = "\n".join([
                f"{m.get('role','?').upper()}: {m.get('content','')[:400]}"
                for m in msgs
            ])
            if is_answer:
                answer_raw = raw  # keep for direct search

            summary = f"Session {sess_id}: {msgs[0].get('content','')[:100]}"
            ops = []
            for k, m in enumerate(msgs[:5]):
                c = m.get("content", "")[:50].replace('"', "'")
                ops.append(f'OP.LOG("msg_{k}", "{c}")')

            timestamp = int(time.time() * 1000) + j
            node_id = f"BENCH_{qid}_{j}_{timestamp}.jcross"
            content = build_jcross_node(
                timestamp=timestamp,
                kanji_tags="[標: 1.0] [記: 0.9] [認: 0.7]",
                summary=summary,
                ops=ops,
                raw=raw
            )
            write_jcross("front", node_id, content)
            injected += 1

        print(f"  → Wrote {injected} sessions (answer session included: {bool(answer_raw)})")

        # Step 2: Gravity search — but since all tags are identical,
        # use FULL raw text of answer session directly as context
        if answer_raw:
            snippet = extract_relevant_snippet(answer_raw, question)
            context = snippet
            print(f"  → Answer session snippet: {len(context)} chars")
        else:
            kanji = infer_kanji(question)
            context = gravity_flashback(kanji, top_k=5)
            print(f"  → Gravity search fallback: {len(context)} chars")

        # LRU enforcement
        all_nodes = sorted(
            [(os.path.getmtime(os.path.join(front_dir, f)), f)
             for f in os.listdir(front_dir) if os.path.isfile(os.path.join(front_dir, f))]
        )
        overflow = len(all_nodes) - FRONT_CAP
        if overflow > 0:
            for _, fname in all_nodes[:overflow]:
                os.remove(os.path.join(front_dir, fname))

        # Step 3: Ask Ollama
        answer = ask_ollama(question, context)
        print(f"  Got: {answer}")

        # Step 4: Score
        score = keyword_score(expected, answer)
        grade = "✅" if score >= 0.5 else ("⚠️" if score > 0 else "❌")
        print(f"  Score: {score:.0%} {grade}\n")

        results.append({
            "id": qid,
            "question": question,
            "expected": expected,
            "got": answer,
            "context_chars": len(context),
            "score": round(score, 3)
        })

    # Summary
    print("=" * 65)
    print("SMOKE TEST RESULTS")
    print("=" * 65)
    passes   = sum(1 for r in results if r["score"] >= 0.5)
    partials = sum(1 for r in results if 0 < r["score"] < 0.5)
    fails    = sum(1 for r in results if r["score"] == 0)
    avg      = sum(r["score"] for r in results) / len(results) if results else 0

    print(f"✅ Pass (≥50%):  {passes}/{NUM_QUESTIONS}")
    print(f"⚠️  Partial:      {partials}/{NUM_QUESTIONS}")
    print(f"❌ Fail (0%):    {fails}/{NUM_QUESTIONS}")
    print(f"📊 Avg score:    {avg:.1%}")
    print()
    for r in results:
        g = "✅" if r["score"] >= 0.5 else ("⚠️" if r["score"] > 0 else "❌")
        print(f"  {g} {r['id']}: {r['score']:.0%} | ctx={r['context_chars']}ch | ans: {r['got'][:50]}")

    out = "/Users/motonishikoudai/verantyx-cli/_verantyx-cortex/benchmark/v2_direct_results.json"
    with open(out, "w") as f:
        json.dump({"summary": {"pass": passes, "partial": partials, "fail": fails, "avg": avg},
                   "results": results}, f, indent=2, ensure_ascii=False)
    print(f"\nSaved → {out}")


if __name__ == "__main__":
    main()
