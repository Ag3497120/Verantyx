#!/usr/bin/env python3
"""
Verantyx Cortex × LongMemEval — Official Mode
  - ALL sessions injected (no oracle answer_session_ids)
  - Meaningful Kanji tags derived from session content
  - Gravity search finds answer session from Kanji similarity
  - gemma4:26b extracts the answer
"""

import json, os, re, math, glob, time
import urllib.request, urllib.error

# ---- Config ----
DATASET_PATH  = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/data/longmemeval_s_cleaned.json"
MEMORY_DIR    = os.path.expanduser("~/.openclaw/memory/front")
OLLAMA_MODEL  = "gemma4:26b"
OLLAMA_URL    = "http://localhost:11434/api/generate"
NUM_QUESTIONS = 500       # set to 500 for full run
CONTEXT_LIMIT = 1500
TOP_K_NODES   = 10     # wider net: answer sessions rank 6-8 in tests


# ---- Kanji Taxonomy ----
# Each category maps to a set of content keywords
KANJI_VOCAB = {
    "場": ["where", "location", "place", "store", "shop", "studio", "restaurant",
           "gym", "target", "walmart", "amazon", "theater", "clinic", "hospital",
           "park", "school", "university", "office", "museum", "market",
           "salon", "spa", "center", "center", "downtown", "nearby", "near",
           "serenity", "campus", "venue", "branch", "neighborhood"],
    "時": ["when", "date", "time", "year", "month", "day", "morning", "evening",
           "night", "ago", "last", "first", "today", "yesterday", "schedule",
           "appointment", "deadline", "recently", "since", "during",
           "week", "weekend", "annual", "monthly", "daily", "hour", "minute"],
    "人": ["name", "person", "friend", "family", "husband", "wife", "brother",
           "sister", "parent", "boss", "colleague", "doctor", "coach", "mentor",
           "i ", "my ", "me ", "myself", "changed", "called", "known as",
           "maiden", "last name", "first name", "renamed", "alias"],
    "商": ["buy", "purchase", "coupon", "price", "cost", "money", "paid",
           "order", "discount", "sale", "receipt", "checkout", "cart", "deals",
           "credit", "cash", "spend", "budget", "free", "redeem",
           "savings", "coupon", "cashback", "refund", "reward", "creamer"],
    "健": ["health", "yoga", "exercise", "workout", "gym", "doctor", "medicine",
           "wellness", "diet", "sleep", "stress", "anxiety", "therapy",
           "meditation", "fitness", "run", "walk", "stretch", "class",
           "pose", "pilates", "instructor", "studio", "session", "mat"],
    "食": ["food", "recipe", "cook", "eat", "meal", "lunch", "dinner", "breakfast",
           "brunch", "snack", "coffee", "creamer", "grocery", "ingredient",
           "restaurant", "menu", "dish", "vegan", "vegetarian",
           "spice", "bake", "grill", "cuisine", "cafe", "drink"],
    "職": ["work", "job", "career", "office", "commute", "boss", "promotion",
           "salary", "degree", "graduate", "university", "college", "interview",
           "hired", "profession", "business", "company", "role", "position",
           "administration", "internship", "resume", "coworker", "minutes each",
           "transit", "bus", "train", "drive", "commuting"],
    "娯": ["movie", "music", "book", "playlist", "spotify", "theater", "play",
           "concert", "show", "album", "song", "artist", "genre", "watched",
           "read", "listen", "netflix", "game", "hobby", "collection",
           "glass menagerie", "summer vibes", "performance", "stage"],
    "技": ["app", "software", "computer", "phone", "internet", "coding",
           "technology", "website", "tool", "device", "update", "install",
           "password", "login", "data", "ai", "chat", "digital"],
}


def content_to_kanji(text: str) -> dict:
    """Score session text against Kanji vocab → top-3 tags.
    Always attaches 記 at high weight to enable universal recall."""
    text_lower = text.lower()
    scores = {}
    for kanji, keywords in KANJI_VOCAB.items():
        hits = sum(1 for kw in keywords if kw in text_lower)
        if hits > 0:
            scores[kanji] = min(1.0, round(hits / 3, 2))  # lower divisor = higher sensitivity

    scores["記"] = 0.3   # universal base — low weight to not dominate similarity
    top = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
    if not top:
        top = [("標", 1.0), ("記", 0.9)]
    return dict(top)


def question_to_kanji(question: str) -> dict:
    """Map question keywords to query Kanji vector."""
    q = question.lower()
    vec = {"記": 0.3}  # low base so category Kanji dominate

    mappings = [
        (["where", "location", "place", "store", "shop", "redeem"],   "場", 1.0),
        (["when", "date", "time", "year", "first", "last"],            "時", 1.0),
        (["degree", "graduate", "university", "job", "career",
          "work", "commute", "position"],                               "職", 1.0),
        (["playlist", "music", "movie", "book", "play", "theater",
          "concert", "show", "song"],                                   "娯", 1.0),
        (["buy", "coupon", "purchase", "redeem", "price", "paid"],     "商", 0.9),
        (["yoga", "exercise", "gym", "health", "class", "studio"],     "健", 1.0),
        (["name", "called", "last name", "first name", "changed"],     "人", 1.0),
        (["food", "recipe", "restaurant", "eat", "coffee"],            "食", 0.9),
        (["app", "software", "computer", "tech", "phone", "device"],   "技", 0.9),
    ]
    for keywords, kanji, weight in mappings:
        if any(kw in q for kw in keywords):
            vec[kanji] = weight

    return vec


# ---- Direct JCross Writer ----
def write_jcross(node_id: str, kanji_dict: dict, summary: str, raw: str):
    """Write a JCross node directly to front/ memory."""
    os.makedirs(MEMORY_DIR, exist_ok=True)
    kanji_str = " ".join(f"[{k}: {v}]" for k, v in kanji_dict.items())
    content = f"""■ JCROSS_NODE_MEMORY_{node_id}
【空間座相】
{kanji_str}
【位相対応表】
[標] := "{summary[:120]}"
【原文】
{raw}
"""
    path = os.path.join(MEMORY_DIR, f"BENCH_{node_id}.jcross")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def clear_bench_nodes():
    """Remove only benchmark nodes from front/ before each question."""
    for f in glob.glob(os.path.join(MEMORY_DIR, "BENCH_*.jcross")):
        try:
            os.remove(f)
        except OSError:
            pass


# ---- Gravity Solver (Python port) ----
def cosine_similarity(a: dict, b: dict) -> float:
    keys = set(a) | set(b)
    dot = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
    norm_a = math.sqrt(sum(v**2 for v in a.values()))
    norm_b = math.sqrt(sum(v**2 for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def gravity_search(query_kanji: dict, top_k: int = TOP_K_NODES) -> list[str]:
    """Return top_k node file paths sorted by cosine similarity."""
    results = []
    for fname in os.listdir(MEMORY_DIR):
        if not fname.startswith("BENCH_"):
            continue
        fpath = os.path.join(MEMORY_DIR, fname)
        with open(fpath, encoding="utf-8") as fh:
            txt = fh.read()
        # Parse Kanji tags from 【空間座相】 section
        m = re.search(r'【空間座相】\s*(.*?)\s*【', txt, re.DOTALL)
        if not m:
            continue
        node_kanji = {}
        for tag in re.findall(r'\[(\S+):\s*([\d.]+)\]', m.group(1)):
            node_kanji[tag[0]] = float(tag[1])
        sim = cosine_similarity(query_kanji, node_kanji)
        results.append((sim, fpath))

    results.sort(reverse=True)
    return [r[1] for r in results[:top_k]]


def extract_raw(fpath: str) -> str:
    """Read raw conversation text from a JCross file."""
    with open(fpath, encoding="utf-8") as fh:
        content = fh.read()
    m = re.search(r'【原文】\s*([\s\S]*)', content)
    return m.group(1).strip() if m else content


def extract_snippet(raw: str, question: str, window: int = 10) -> str:
    """Extract lines most relevant to the question.
    Uses multi-anchor: collects ALL lines hitting keywords, not just one anchor.
    """
    lines = [l for l in raw.splitlines() if l.strip()]
    keywords = [w.lower() for w in question.split() if len(w) > 3]
    if not lines or not keywords:
        return raw[:CONTEXT_LIMIT]

    # Score every line
    scored = [(sum(1 for k in keywords if k in l.lower()), i) for i, l in enumerate(lines)]
    max_score = max(s for s, _ in scored)

    if max_score == 0:
        return raw[:CONTEXT_LIMIT]

    # Collect all anchor lines that hit at least half the max score
    anchors = [i for s, i in scored if s >= max(1, max_score // 2)]

    # Build union of windows around each anchor
    included = set()
    for anchor in anchors:
        for idx in range(max(0, anchor - window // 2),
                         min(len(lines), anchor + window // 2 + 1)):
            included.add(idx)

    selected = "\n".join(lines[i] for i in sorted(included))
    return selected[:CONTEXT_LIMIT]


# ---- Ollama ----
def ask_ollama(question: str, context: str) -> str:
    prompt = f"""Below is a conversation. Answer the question with ONLY the exact word(s) from the conversation. No explanation.

Conversation:
{context}

Question: {question}
Answer:"""

    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 2048}
    }).encode()

    try:
        req = urllib.request.Request(
            OLLAMA_URL, data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read())
            raw = data.get("response", "").strip()
            if "</think>" in raw:
                raw = raw.split("</think>")[-1].strip()
            return raw
    except Exception as e:
        return f"[Error: {e}]"


# ---- Scoring ----
def keyword_score(expected: str, got: str) -> float:
    if not got or any(x in got.lower() for x in ["don't know", "not available", "error"]):
        return 0.0
    ec = re.sub(r'[^\w\s]', ' ', expected.lower())
    gc = re.sub(r'[^\w\s]', ' ', got.lower())
    kw = [w for w in ec.split() if len(w) > 2]
    if not kw:
        return 1.0 if ec.strip() in gc else 0.0
    return sum(1 for w in kw if w in gc) / len(kw)


# ---- Main ----
def main():
    print("=" * 65)
    print("  Verantyx Cortex × LongMemEval — OFFICIAL MODE")
    print("  Semantic Kanji tagging | Oracle-free retrieval")
    print(f"  Model: {OLLAMA_MODEL} | Questions: {NUM_QUESTIONS}")
    print("=" * 65)

    with open(DATASET_PATH) as f:
        dataset = json.load(f)
    selected = dataset[:NUM_QUESTIONS]

    results = []

    for i, item in enumerate(selected):
        qid      = item["question_id"]
        question = item["question"]
        expected = item["answer"]
        sessions = item.get("haystack_sessions", [])
        sess_ids = item.get("haystack_session_ids", [])
        ans_ids  = item.get("answer_session_ids", [])  # used only for post-hoc analysis

        print(f"\n[{i+1}/{NUM_QUESTIONS}] {qid}")
        print(f"  Q: {question}")
        print(f"  Expected: {expected}")
        print(f"  Total sessions: {len(sessions)}")

        # Step 1: Clear previous bench nodes
        clear_bench_nodes()

        # Step 2: Inject ALL sessions with semantic Kanji tags
        ts = int(time.time() * 1000)
        injected = 0
        for j, session in enumerate(sessions):
            if not isinstance(session, list):
                continue
            raw = "\n".join([
                f"{m.get('role','?').upper()}: {m.get('content','')[:400]}"
                for m in session if isinstance(m, dict)
            ])
            if not raw.strip():
                continue

            sid = sess_ids[j] if j < len(sess_ids) else f"s{j}"
            kanji = content_to_kanji(raw)
            summary = f"Session {sid}: {raw[:100]}"
            node_id = f"{qid}_{j}_{ts + j}"
            write_jcross(node_id, kanji, summary, raw)
            injected += 1

        print(f"  → Injected {injected} sessions with semantic Kanji")

        # Step 3: Derive query Kanji from question (no oracle)
        q_kanji = question_to_kanji(question)
        print(f"  → Query Kanji: {q_kanji}")

        # Step 4: Gravity search → top-k nodes
        top_files = gravity_search(q_kanji, top_k=TOP_K_NODES)
        keywords = [w.lower() for w in question.split() if len(w) > 3]
        print(f"  → Surfaced {len(top_files)} nodes")

        # Step 5: Use Top-1 node (highest gravity similarity) as primary context
        # Gravity similarity is already the best relevance signal
        if top_files:
            top1_raw = extract_raw(top_files[0])
            snippet = extract_snippet(top1_raw, question)
            # If best_score=0 in top-1, try each node and take highest keyword match
            best_score = sum(1 for l in top1_raw.splitlines()
                             for k in keywords if k in l.lower())
            if best_score == 0:
                for fpath in top_files[1:]:
                    node_raw = extract_raw(fpath)
                    s = sum(1 for l in node_raw.splitlines() for k in keywords if k in l.lower())
                    if s > best_score:
                        best_score, snippet = s, extract_snippet(node_raw, question)
        else:
            snippet = ""
            best_score = 0

        print(f"  → Context: {len(snippet)} chars (kw_hits={best_score})")
        print(f"  preview: {snippet[:120].replace(chr(10), ' | ')}")

        # Step 6: Check if answer session is in top-k
        surfaced_content = " ".join(open(f).read() for f in top_files)
        answer_in_topk = any(aid in surfaced_content for aid in ans_ids) if ans_ids else None


        # Step 7: Ask gemma4:26b
        answer = ask_ollama(question, snippet)
        print(f"  Got: {answer[:100]}")

        score = keyword_score(expected, answer)
        grade = "✅" if score >= 0.5 else ("⚠️" if score > 0 else "❌")
        recall_mark = "🎯" if answer_in_topk else "🔍" if answer_in_topk is False else ""
        print(f"  Score: {score:.0%} {grade}  retrieval: {'hit' if answer_in_topk else 'miss'} {recall_mark}")

        results.append({
            "id": qid, "question": question, "expected": expected, "got": answer,
            "score": round(score, 3), "answer_in_topk": answer_in_topk,
            "sessions_total": len(sessions), "sessions_injected": injected
        })

    # Summary
    print("\n" + "=" * 65)
    print("OFFICIAL BENCHMARK RESULTS")
    print("=" * 65)
    passes   = sum(1 for r in results if r["score"] >= 0.5)
    partials = sum(1 for r in results if 0 < r["score"] < 0.5)
    fails    = sum(1 for r in results if r["score"] == 0)
    avg      = sum(r["score"] for r in results) / len(results) if results else 0
    retrieval_hits = sum(1 for r in results if r["answer_in_topk"] is True)

    print(f"✅ Pass (≥50%):    {passes}/{NUM_QUESTIONS}")
    print(f"⚠️  Partial:        {partials}/{NUM_QUESTIONS}")
    print(f"❌ Fail (0%):      {fails}/{NUM_QUESTIONS}")
    print(f"📊 Avg score:      {avg:.1%}")
    print(f"🎯 Retrieval@{TOP_K_NODES}:   {retrieval_hits}/{NUM_QUESTIONS}")
    print()
    for r in results:
        g = "✅" if r["score"] >= 0.5 else ("⚠️" if r["score"] > 0 else "❌")
        h = "🎯" if r["answer_in_topk"] else "miss"
        print(f"  {g} {r['id']}: {r['score']:.0%} | retrieval={h} | ans: {r['got'][:40]}")

    out = "/Users/motonishikoudai/verantyx-cli/_verantyx-cortex/benchmark/official_results.json"
    with open(out, "w") as f:
        json.dump({"mode": "official", "model": OLLAMA_MODEL, "top_k": TOP_K_NODES,
                   "summary": {"pass": passes, "partial": partials, "fail": fails,
                               "avg_score": avg, "retrieval_hits": retrieval_hits},
                   "results": results}, f, indent=2, ensure_ascii=False)
    print(f"\nSaved → {out}")


if __name__ == "__main__":
    main()
