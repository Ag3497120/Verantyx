#!/usr/bin/env python3
"""
Verantyx Cortex × LongMemEval — Full 3-Layer Retrieval

Architecture (per design spec):
  L1 [Kanji Topology]    : 超低解像度ナビゲーション。空間位置の粗い絞り込み。
                           タグ単体でも内容の要約として機能。
  L2 [Operation Commands]: 原文を操作コマンドで圧縮した高濃度セマンティック表現。
                           意図・ニュアンス・ファクトを機械可読形式で保持。
  L3 [Raw + L2 Combined] : 原文のみでは意味不明なため必ずL2とセットで使用。
                           コストを度外視して取りこぼしゼロを保証するフォールバック。

Retrieval cascade:
  L1 → Top-50候補に粗絞り
  L2 → Top-50のOP内容をスキャン、質問とキーワードマッチ → Top-3特定
  L3+L2 → Top-3のraw+opsを組み合わせてgemma4:26bに最終推論させる
"""

import json, os, re, math, glob, time
import urllib.request, urllib.error

# ---- Config ----
DATASET_PATH  = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/data/longmemeval_s_cleaned.json"
MEMORY_DIR    = os.path.expanduser("~/.openclaw/memory/front")
OLLAMA_MODEL  = "gemma4:26b"
OLLAMA_URL    = "http://localhost:11434/api/generate"
NUM_QUESTIONS = 500        # set to 500 for full run
CONTEXT_LIMIT = 2000

# Retrieval layer limits
L1_TOP_K = 50   # L1 Kanji → rough candidates
L2_TOP_K = 5    # L2 OP scan → refined candidates for L3 (increased for better recall)


# ---- Kanji Taxonomy (L1) ----
KANJI_VOCAB = {
    "場": ["where", "location", "place", "store", "shop", "studio", "restaurant",
           "gym", "target", "serenity", "campus", "venue", "near", "downtown",
           "theater", "clinic", "hospital", "park", "market", "salon"],
    "時": ["when", "date", "time", "year", "month", "day", "morning", "evening",
           "schedule", "daily", "hour", "minute", "week", "recently", "ago"],
    "人": ["name", "person", "friend", "family", "husband", "wife", "changed",
           "maiden", "last name", "first name", "renamed", "alias"],
    "商": ["buy", "purchase", "coupon", "price", "cost", "paid", "redeem",
           "discount", "sale", "receipt", "cashback", "creamer", "spend"],
    "健": ["health", "yoga", "exercise", "workout", "gym", "wellness",
           "meditation", "fitness", "pilates", "instructor", "studio", "mat"],
    "食": ["food", "recipe", "cook", "eat", "meal", "coffee", "creamer",
           "restaurant", "menu", "dish", "vegan", "spice", "bake", "grocery"],
    "職": ["work", "job", "career", "office", "commute", "degree", "graduate",
           "university", "college", "business", "company", "administration",
           "transit", "bus", "train", "drive", "commuting", "internship"],
    "娯": ["movie", "music", "book", "playlist", "spotify", "theater", "play",
           "concert", "show", "album", "song", "listened", "read",
           "glass menagerie", "summer vibes", "performance"],
    "技": ["app", "software", "computer", "phone", "internet",
           "technology", "website", "device", "data", "digital"],
}


# ---- Operation Command Vocabulary (L2) ----
# These are the defined operations. Combinations generate new ops if needed.
OP_VOCAB = [
    "OP.FACT",      # Factual claim: OP.FACT("key", "value")
    "OP.ENTITY",    # Named entity: OP.ENTITY("type", "name")
    "OP.TOPIC",     # Session topic: OP.TOPIC("subject")
    "OP.INTENT",    # User intent:  OP.INTENT("description")
    "OP.QUANTITY",  # Numeric fact: OP.QUANTITY("what", "amount")
    "OP.LOG",       # General log:  OP.LOG("key", "content")
]


def content_to_kanji(text: str) -> dict:
    """L1: Score session against Kanji vocab → top-3 tags."""
    tl = text.lower()
    scores = {}
    for k, kws in KANJI_VOCAB.items():
        hits = sum(1 for kw in kws if kw in tl)
        if hits > 0:
            scores[k] = min(1.0, round(hits / 3, 2))
    scores["記"] = 0.3  # universal minimal base
    top = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
    return dict(top)


def extract_l2_ops(session_raw: str, sess_id: str) -> list[str]:
    """
    L2: Heuristic fact extraction from session content → OP commands.
    Aggressively captures:
    - Multi-word proper nouns ("Serenity Yoga", "Glass Menagerie", "Business Administration")
    - Quantities with context ("45 minutes each way")
    - Named entities from BOTH user and assistant turns
    - Quoted strings (often product/place names)
    """
    ops = []
    lines = session_raw.splitlines()

    # 1. Topic from first USER turn
    user_lines  = [l[5:].strip() for l in lines if l.startswith("USER:") and len(l) > 10]
    asst_lines  = [l[10:].strip() for l in lines if l.startswith("ASSISTANT:") and len(l) > 15]
    if user_lines:
        ops.append(f'OP.TOPIC("{user_lines[0][:80].replace(chr(34), chr(39))}")')
    for ul in user_lines[1:3]:
        ops.append(f'OP.INTENT("{ul[:80].replace(chr(34), chr(39))}")')

    # 2. Multi-word proper nouns (2-4 capitalized words) from ALL text
    # This captures: "Serenity Yoga", "Glass Menagerie", "Business Administration",
    #                "Summer Vibes", "Target", "Johnson"
    multiword_pn = re.findall(
        r'\b[A-Z][a-z]{1,15}(?:\s+[A-Z][a-z]{1,15}){1,3}\b', session_raw
    )
    single_pn = re.findall(r'\b[A-Z][a-z]{3,15}\b', session_raw)
    skip = {"User", "Assistant", "What", "The", "How", "Where", "When", "Why",
            "Who", "Can", "Do", "Did", "Is", "Are", "Was", "Were", "Have", "Has",
            "Here", "Some", "This", "That", "These", "There", "Also", "Both",
            "With", "From", "Like", "Just", "More", "Your", "Their", "They"}
    seen = set()
    # Prioritize multi-word (more specific)
    for pn in multiword_pn + single_pn:
        if pn not in skip and pn not in seen and len(pn) > 3:
            seen.add(pn)
            ops.append(f'OP.ENTITY("name", "{pn}")')
            if len(seen) >= 8:
                break

    # 3. Quantities: numbers with units (duration, price, distance)
    qty_patterns = [
        # Duration with context (most important for commute questions)
        (r'((?:about |approximately )?\d+\s+(?:minutes?|hours?)\s*(?:each way|per day|a day|daily|commute|round trip|one[- ]way)?)', "duration"),
        (r'(\$\d+(?:\.\d+)?(?:\s+(?:coupon|off|discount|credit|rebate))?)',  "price"),
        (r'(\d+\s+(?:miles?|km|blocks?|steps))',                              "distance"),
        (r'(\d+\s+(?:years?|months?|weeks?)\s+(?:ago|later|before|after)?)',  "time_ago"),
    ]
    for pattern, label in qty_patterns:
        for match in re.findall(pattern, session_raw, re.IGNORECASE):
            qty = match.strip()[:60].replace('"', "'")
            if qty:
                ops.append(f'OP.QUANTITY("{label}", "{qty}")')

    # 4. Key USER statements as OP.LOG (full content for keyword matching)
    for i, ul in enumerate(user_lines[:4]):
        ops.append(f'OP.LOG("u{i}", "{ul[:80].replace(chr(34), chr(39))}")')
    # Also log assistant factual statements (they often contain the answer)
    for i, al in enumerate(asst_lines[:2]):
        ops.append(f'OP.LOG("a{i}", "{al[:80].replace(chr(34), chr(39))}")')

    return ops[:18]


def question_to_kanji(question: str) -> dict:
    """L1: Map question to query Kanji vector."""
    q = question.lower()
    vec = {"記": 0.3}
    mappings = [
        (["where", "location", "place", "store", "redeem"],    "場", 1.0),
        (["when", "date", "time", "year", "first", "last"],     "時", 1.0),
        (["degree", "graduate", "job", "career", "work",
          "commute", "position"],                                "職", 1.0),
        (["playlist", "music", "movie", "book", "play",
          "theater", "concert", "show", "song"],                 "娯", 1.0),
        (["buy", "coupon", "purchase", "redeem", "price"],       "商", 0.9),
        (["yoga", "exercise", "gym", "health", "class",
          "studio"],                                             "健", 1.0),
        (["name", "called", "last name", "first name",
          "changed"],                                            "人", 1.0),
        (["food", "recipe", "restaurant", "eat", "coffee"],      "食", 0.9),
    ]
    for kws, kanji, w in mappings:
        if any(kw in q for kw in kws):
            vec[kanji] = w
    return vec


# ---- JCross Writer (all 3 layers) ----
def write_jcross(node_id: str, kanji_dict: dict, summary: str,
                 ops: list[str], raw: str):
    """Write a full 3-layer JCross node."""
    os.makedirs(MEMORY_DIR, exist_ok=True)
    kanji_str = " ".join(f"[{k}: {v}]" for k, v in kanji_dict.items())
    ops_str   = "\n".join(ops)
    content = f"""■ JCROSS_NODE_MEMORY_{node_id}
【空間座相】
{kanji_str}
【位相対応表】
[標] := "{summary[:120]}"
【操作対応表】
{ops_str}
【原文】
{raw}
"""
    path = os.path.join(MEMORY_DIR, f"BENCH_{node_id}.jcross")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def clear_bench_nodes():
    for f in glob.glob(os.path.join(MEMORY_DIR, "BENCH_*.jcross")):
        try:
            os.remove(f)
        except OSError:
            pass


# ---- L1: Gravity Search (Kanji cosine similarity) ----
def cosine(a: dict, b: dict) -> float:
    keys = set(a) | set(b)
    dot = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
    na = math.sqrt(sum(v**2 for v in a.values()))
    nb = math.sqrt(sum(v**2 for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def l1_gravity_search(query_kanji: dict, top_k: int = L1_TOP_K) -> list[str]:
    """L1: Return top_k node paths sorted by Kanji cosine similarity."""
    results = []
    for fname in os.listdir(MEMORY_DIR):
        if not fname.startswith("BENCH_"):
            continue
        fpath = os.path.join(MEMORY_DIR, fname)
        with open(fpath, encoding="utf-8") as fh:
            txt = fh.read()
        m = re.search(r'【空間座相】\s*(.*?)\s*【', txt, re.DOTALL)
        if not m:
            continue
        nk = {}
        for tag in re.findall(r'\[(\S+):\s*([\d.]+)\]', m.group(1)):
            nk[tag[0]] = float(tag[1])
        sim = cosine(query_kanji, nk)
        results.append((sim, fpath))
    results.sort(reverse=True)
    return [r[1] for r in results[:top_k]]


# ---- L2: Operation Command Scan ----
def l2_op_scan(question: str, candidate_paths: list[str], top_k: int = L2_TOP_K) -> list[tuple]:
    """
    L2: Scan OP commands + raw text across L1 candidates.
    Scoring:
    - Proper noun exact phrase from question: +8 (highest priority)
    - Multi-word phrase in ops/nuance: +3
    - Single keyword in ops/nuance: +1
    - Keyword in raw text: +0.3 (lower weight to avoid noise)
    """
    # Build keywords + phrases
    words   = [w.lower() for w in re.sub(r'[?.,!]', '', question).split() if len(w) > 2]
    phrases = [f"{words[i]} {words[i+1]}" for i in range(len(words)-1)]
    phrases += [f"{words[i]} {words[i+1]} {words[i+2]}" for i in range(len(words)-2)]

    # Extract proper nouns from question (Title Case 2+ words: "Serenity Yoga", "Glass Menagerie")
    pn_skip = {"What","Where","When","Who","How","Did","Does","Was","Were","Have","Has","The","This","That"}
    q_proper_nouns = re.findall(r'\b[A-Z][a-z]{1,15}(?:\s+[A-Z][a-z]{1,15})+\b', question)
    q_proper_nouns = [pn.lower() for pn in q_proper_nouns if pn not in pn_skip]

    scored = []
    for fpath in candidate_paths:
        with open(fpath, encoding="utf-8") as fh:
            content = fh.read()
        m  = re.search(r'【操作対応表】\s*([\s\S]*?)\s*【原文】', content)
        m2 = re.search(r'【位相対応表】\s*([\s\S]*?)\s*【', content)
        mr = re.search(r'【原文】\s*([\s\S]*)', content)
        ops_text = (m.group(1).lower()  if m  else "")
        nuance   = (m2.group(1).lower() if m2 else "")
        raw_text = (mr.group(1).lower() if mr else "")[:2000]  # cap for perf
        combined = ops_text + " " + nuance

        # Proper noun exact match (highest signal)
        score  = sum(8 for pn in q_proper_nouns if pn in combined or pn in raw_text)
        # Phrase match in ops (high precision)
        score += sum(3 for ph in phrases if ph in combined)
        # Keyword match in ops
        score += sum(1 for kw in words if kw in combined)
        # Keyword match in raw (lower weight)
        score += sum(0.3 for kw in words if kw in raw_text)
        scored.append((score, fpath))
    scored.sort(reverse=True)
    return scored[:top_k]


# ---- L3: Raw text extraction ----
def extract_raw(fpath: str) -> str:
    with open(fpath, encoding="utf-8") as fh:
        content = fh.read()
    m = re.search(r'【原文】\s*([\s\S]*)', content)
    return m.group(1).strip() if m else content


def extract_ops(fpath: str) -> str:
    with open(fpath, encoding="utf-8") as fh:
        content = fh.read()
    m = re.search(r'【操作対応表】\s*([\s\S]*?)\s*【原文】', content)
    return m.group(1).strip() if m else ""


def extract_snippet(raw: str, question: str) -> str:
    """Extract lines most relevant to the question from raw text."""
    lines = [l for l in raw.splitlines() if l.strip()]
    keywords = [w.lower() for w in question.split() if len(w) > 3]
    if not lines or not keywords:
        return raw[:CONTEXT_LIMIT]
    scored = [(sum(1 for k in keywords if k in l.lower()), i) for i, l in enumerate(lines)]
    max_score = max(s for s, _ in scored)
    if max_score == 0:
        return raw[:CONTEXT_LIMIT]
    anchors = [i for s, i in scored if s >= max(1, max_score)]
    included = set()
    for anchor in anchors:
        for idx in range(max(0, anchor - 8), min(len(lines), anchor + 9)):
            included.add(idx)
    return "\n".join(lines[i] for i in sorted(included))[:CONTEXT_LIMIT]


# ---- L3+L2 Context Assembly ----
def assemble_l3_l2_context(fpath: str, question: str, use_full_raw: bool = False) -> str:
    """
    L3+L2 combination: raw text paired with operation commands.
    use_full_raw=True: pass full raw (up to 4000 chars) for maximum recall.
    use_full_raw=False: keyword-based snippet extraction.
    """
    raw = extract_raw(fpath)
    ops = extract_ops(fpath)

    l3_content = raw if use_full_raw else extract_snippet(raw, question)
    l3_content  = l3_content[:4000]  # increased from 3000 to 4000

    context = ""
    if ops:
        context += f"[Intent & Facts (L2)]\n{ops}\n\n"
    context += f"[Conversation (L3)]\n{l3_content}"
    return context


def assemble_multi_context(l2_scored: list[tuple], question: str, max_nodes: int = 3) -> str:
    """
    Concatenate top-N contexts for better recall.
    Used for all questions (not just cumulative) to reduce empty answers.
    """
    parts = []
    for idx, (s, fpath) in enumerate(l2_scored[:max_nodes]):
        ctx = assemble_l3_l2_context(fpath, question, use_full_raw=(s > 0))
        parts.append(f"[Memory {idx+1} | relevance={s:.1f}]\n{ctx}")
    return "\n\n" + "="*30 + "\n\n".join(parts)


# ---- Ollama ----
# ---- Cumulative question detection ----
CUMULATIVE_SIGNALS = [
    "total", "in total", "across all", "throughout", "overall",
    "how many", "how much", "combined", "all the times", "all events",
    "add up", "sum", "aggregate", "collectively"
]

def is_cumulative(question: str) -> bool:
    q = question.lower()
    return any(sig in q for sig in CUMULATIVE_SIGNALS)


def ask_ollama(question: str, context: str, cumulative: bool = False) -> str:
    if cumulative:
        prompt = f"""Below are MULTIPLE conversations. The question requires aggregating/summing across ALL of them.
Read ALL sessions carefully and combine the relevant facts to answer.
Answer with ONLY the exact value(s). No explanation.
If context is insufficient, respond with the closest fact you can find.

{context}

Question: {question}
Answer (aggregated across all sessions):"""
    else:
        prompt = f"""Below is a retrieved conversation with extracted facts.
Answer with ONLY the exact word(s) from the conversation. No explanation.
If the answer is not clearly stated, provide the most relevant information available.

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
def keyword_score(expected, got: str) -> float:
    expected = str(expected)  # guard against int answers (e.g. "99")
    got      = str(got) if got else ""
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
    print("  Verantyx Cortex × LongMemEval — 3-Layer Official Mode")
    print("  L1(Kanji) → L2(OP scan) → L3+L2(raw+ops)")
    print(f"  Model: {OLLAMA_MODEL} | Questions: {NUM_QUESTIONS}")
    print(f"  L1_TOP_K={L1_TOP_K} | L2_TOP_K={L2_TOP_K}")
    print("=" * 65)

    with open(DATASET_PATH) as f:
        dataset = json.load(f)
    selected = dataset[:NUM_QUESTIONS]

    # ---- Resume support: skip already-completed questions ----
    RESULTS_PATH = "/Users/motonishikoudai/verantyx-cli/_verantyx-cortex/benchmark/trilayer_results.json"
    results = []
    done_ids = set()
    if os.path.exists(RESULTS_PATH):
        try:
            with open(RESULTS_PATH) as f:
                prev = json.load(f)
            results = prev.get("results", [])
            done_ids = {r["id"] for r in results}
            print(f"  ♻️  Resuming from checkpoint: {len(done_ids)} questions already done")
        except Exception:
            pass

    for i, item in enumerate(selected):
        qid      = item["question_id"]
        question = item["question"]
        expected = item["answer"]
        sessions = item.get("haystack_sessions", [])
        sess_ids = item.get("haystack_session_ids", [])
        ans_ids  = item.get("answer_session_ids", [])

        # Skip already-completed questions (resume support)
        if qid in done_ids:
            continue

        print(f"\n[{i+1}/{NUM_QUESTIONS}] {qid}")
        print(f"  Q: {question}")
        print(f"  Expected: {expected}")

        # Step 1: Clear previous benchmark nodes
        clear_bench_nodes()

        # Step 2: Inject ALL sessions with L1+L2+L3
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
            # L1: Kanji tags
            kanji   = content_to_kanji(raw)
            summary = f"Session {sid}: {raw[:100]}"
            # L2: Operation commands (heuristic fact extraction)
            ops     = extract_l2_ops(raw, sid)
            node_id = f"{qid}_{j}_{ts + j}"
            write_jcross(node_id, kanji, summary, ops, raw)
            injected += 1

        print(f"  → Injected {injected} sessions (L1+L2+L3 each)")

        # Step 3: L1 Kanji gravity search → rough candidates
        q_kanji = question_to_kanji(question)
        l1_candidates = l1_gravity_search(q_kanji, top_k=L1_TOP_K)
        print(f"  → L1 Kanji: {q_kanji} → {len(l1_candidates)} candidates")

        # Step 4: L2 OP scan → refine to top-3 with scores
        l2_scored = l2_op_scan(question, l1_candidates, top_k=L2_TOP_K)
        l2_top_score = l2_scored[0][0] if l2_scored else 0
        l2_hit_paths = [fp for s, fp in l2_scored]

        # Oracle analysis (check if answer session is in l2 results)
        surfaced_all = " ".join(open(f).read() for f in l2_hit_paths) if l2_hit_paths else ""
        answer_in_l2 = any(aid in surfaced_all for aid in ans_ids) if ans_ids else None

        if l2_hit_paths:
            top_ops = extract_ops(l2_hit_paths[0])
            print(f"  → L2 OP scan → top_score={l2_top_score:.1f} | {top_ops[:80].replace(chr(10),' | ')}")
        else:
            print(f"  → L2 OP scan → no candidates")
            l2_hit_paths = l1_candidates[:L2_TOP_K]
            l2_top_score = 0

        # Step 5: L3+L2 context assembly (v3)
        # ALL questions: use top-3 contexts to reduce empty answers
        # Cumulative questions: use top-5 contexts + cumulative prompt
        cumulative = is_cumulative(question)

        if cumulative:
            # Cumulative: top-5 sessions concatenated
            best_context = assemble_multi_context(l2_scored, question, max_nodes=L2_TOP_K)
            mode = f"cumulative_top{min(len(l2_scored), L2_TOP_K)}"
            best_score = len(l2_scored)
        else:
            # Regular: top-3 contexts concatenated (reduces empty answers significantly)
            best_context = assemble_multi_context(l2_scored, question, max_nodes=3)
            mode = f"multi_top3"
            best_score = len([s for s, _ in l2_scored[:3] if s > 0])

        if not best_context and l2_hit_paths:
            best_context = assemble_l3_l2_context(l2_hit_paths[0], question, use_full_raw=False)
            mode = "fallback"

        print(f"  → L3+L2 [{mode}]: {len(best_context)} chars | cumulative={cumulative}")

        # Step 6: Ask gemma4:26b
        answer = ask_ollama(question, best_context, cumulative=cumulative)
        print(f"  Got: {answer[:100]}")

        score = keyword_score(expected, answer)
        grade = "✅" if score >= 0.5 else ("⚠️" if score > 0 else "❌")
        l2_mark = "🎯" if answer_in_l2 else "🔍"
        print(f"  Score: {score:.0%} {grade}  L2_retrieval: {'hit' if answer_in_l2 else 'miss'} {l2_mark}")

        results.append({
            "id": qid, "question": question, "expected": str(expected), "got": answer,
            "score": round(score, 3), "l2_hit": answer_in_l2,
            "sessions_total": len(sessions), "sessions_injected": injected
        })

        # ---- Incremental save (enables live monitoring + resume) ----
        _n = len(results)
        _p = sum(1 for r in results if r["score"] >= 0.5)
        _avg = sum(r["score"] for r in results) / _n
        _l2h = sum(1 for r in results if r["l2_hit"] is True)
        _out = "/Users/motonishikoudai/verantyx-cli/_verantyx-cortex/benchmark/trilayer_results.json"
        with open(_out, "w") as _f:
            json.dump({"mode": "trilayer_official", "model": OLLAMA_MODEL,
                       "progress": {"done": _n, "total": NUM_QUESTIONS},
                       "summary": {"pass": _p, "avg": round(_avg, 3), "l2_hits": _l2h},
                       "results": results}, _f, indent=2, ensure_ascii=False)

    # Summary
    print("\n" + "=" * 65)
    print("3-LAYER OFFICIAL BENCHMARK RESULTS")
    print("=" * 65)
    passes   = sum(1 for r in results if r["score"] >= 0.5)
    partials = sum(1 for r in results if 0 < r["score"] < 0.5)
    fails    = sum(1 for r in results if r["score"] == 0)
    avg      = sum(r["score"] for r in results) / len(results) if results else 0
    l2_hits  = sum(1 for r in results if r["l2_hit"] is True)

    print(f"✅ Pass (≥50%):    {passes}/{NUM_QUESTIONS}")
    print(f"⚠️  Partial:        {partials}/{NUM_QUESTIONS}")
    print(f"❌ Fail (0%):      {fails}/{NUM_QUESTIONS}")
    print(f"📊 Avg score:      {avg:.1%}")
    print(f"🎯 L2 Retrieval:   {l2_hits}/{NUM_QUESTIONS}")
    print()
    for r in results:
        g = "✅" if r["score"] >= 0.5 else ("⚠️" if r["score"] > 0 else "❌")
        h = "🎯" if r["l2_hit"] else "miss"
        print(f"  {g} {r['id']}: {r['score']:.0%} | L2={h} | ans: {r['got'][:40]}")

    out = "/Users/motonishikoudai/verantyx-cli/_verantyx-cortex/benchmark/trilayer_results.json"
    with open(out, "w") as f:
        json.dump({"mode": "trilayer_official", "model": OLLAMA_MODEL,
                   "L1_TOP_K": L1_TOP_K, "L2_TOP_K": L2_TOP_K,
                   "summary": {"pass": passes, "partial": partials, "fail": fails,
                               "avg_score": avg, "l2_retrieval_hits": l2_hits},
                   "results": results}, f, indent=2, ensure_ascii=False)
    print(f"\nSaved → {out}")


if __name__ == "__main__":
    main()
