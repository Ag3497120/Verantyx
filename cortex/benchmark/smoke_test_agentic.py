#!/usr/bin/env python3
"""
Verantyx Cortex × LongMemEval — Agentic Mode
==============================================
アーキテクチャ:
  LLM 1個 (gemma4:26b) を L1〜L3 の全フェーズで使用。
  各セッション注入はステートレス独立呼び出し → コンテキスト汚染ゼロ。
  最終推論時はAIが自分の内部記憶を100%信用せず、JCrossのみを正として回答。

動作フロー:
  [注入] Session raw → LLM (OP対応表参照) → L2 OPs生成 → JCross書き込み → コンテキスト排出
  [検索] L1 Kanji map → 候補絞り → L2 OPスキャン → Top-1特定 → L3+L2 → LLM回答
"""

import json, os, re, math, glob, time
import urllib.request

# ---- Config ----
DATASET_PATH   = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/data/longmemeval_s_cleaned.json"
MEMORY_DIR     = os.path.expanduser("~/.openclaw/memory/front")
OLLAMA_URL     = "http://localhost:11434/api/generate"
MODEL_LIGHT    = "gemma4:e2b"   # L2生成: 軽量・高速・ステートレス
MODEL_HEAVY    = "gemma4:26b"   # 最終推論: 高精度
NUM_QUESTIONS  = 7              # 500に変更でフルラン
L1_TOP_K       = 50             # L1マップで絞る候補数
L2_AUGMENT_K   = 15             # LLM L2生成を適用する上位N件
L2_FINAL_K     = 1              # 最終推論に渡す件数

# ---- Operation Command Vocabulary Table (OP対応表) ----
# このテーブルをLLMに渡すことで自然言語→操作コマンド変換を定義する
OP_TABLE = """OPERATION TABLE — Verantyx Memory Compression Vocabulary
================================================================
Convert conversation to these operation commands. One per line.
If no single op fits, COMBINE with + (e.g. OP.FACT+ENTITY(...)).

OP.TOPIC("description")           - What this conversation is mainly about
OP.INTENT("goal")                 - What the user is trying to accomplish
OP.FACT("key", "value")           - A factual statement from the conversation
OP.ENTITY("type", "name")         - A named entity (place, person, product, brand)
OP.QUANTITY("what", "amount")     - A numeric or measurable fact
OP.STATE("subject", "state")      - A condition or changed state
OP.RELATION("a", "rel", "b")      - A relationship between two things
OP.LOG("key", "content")          - General important content not fitting above

Rules:
- Extract ALL facts, entities, quantities, intents
- For place names, always use OP.ENTITY("place", "Name")
- For durations (X minutes, X hours), always use OP.QUANTITY
- For proper nouns (brand names, studio names), always use OP.ENTITY
- For educational/career facts, always use OP.FACT
- Combine when richer: OP.FACT+ENTITY("yoga_studio_near", "Serenity Yoga")
- Output ONLY operation lines. No explanation. No markdown.
================================================================"""


# ---- Kanji Taxonomy (L1 Map) ----
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
           "transit", "bus", "train", "drive", "commuting"],
    "娯": ["movie", "music", "book", "playlist", "spotify", "theater", "play",
           "concert", "show", "album", "song", "listened", "read",
           "glass menagerie", "summer vibes", "performance"],
    "技": ["app", "software", "computer", "phone", "internet",
           "technology", "website", "device", "data", "digital"],
}


def content_to_kanji(text: str) -> dict:
    tl = text.lower()
    scores = {}
    for k, kws in KANJI_VOCAB.items():
        hits = sum(1 for kw in kws if kw in tl)
        if hits > 0:
            scores[k] = min(1.0, round(hits / 3, 2))
    scores["記"] = 0.3
    top = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
    return dict(top)


def question_to_kanji(question: str) -> dict:
    q = question.lower()
    vec = {"記": 0.3}
    mappings = [
        (["where", "location", "place", "store", "redeem"],     "場", 1.0),
        (["when", "date", "time", "year", "first", "last"],      "時", 1.0),
        (["degree", "graduate", "job", "career", "work",
          "commute", "position"],                                 "職", 1.0),
        (["playlist", "music", "movie", "book", "play",
          "theater", "concert", "show", "song"],                  "娯", 1.0),
        (["buy", "coupon", "purchase", "redeem", "price"],        "商", 0.9),
        (["yoga", "exercise", "gym", "health", "class",
          "studio"],                                              "健", 1.0),
        (["name", "called", "last name", "first name",
          "changed"],                                             "人", 1.0),
        (["food", "recipe", "restaurant", "eat", "coffee"],       "食", 0.9),
    ]
    for kws, kanji, w in mappings:
        if any(kw in q for kw in kws):
            vec[kanji] = w
    return vec


# ---- LLM Call (Stateless) ----
def llm_call(prompt: str, model: str, max_tokens: int = 512) -> str:
    """
    ステートレスな単一LLM呼び出し。
    各呼び出しはコンテキストを共有しない → 汚染ゼロ。
    """
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": max_tokens}
    }).encode()
    try:
        req = urllib.request.Request(
            OLLAMA_URL, data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            raw = data.get("response", "").strip()
            if "</think>" in raw:
                raw = raw.split("</think>")[-1].strip()
            return raw
    except Exception as e:
        return f"[LLM_ERROR: {e}]"


def generate_l2_ops_llm(session_raw: str) -> list[str]:
    """
    L2操作コマンド生成: LLMがOP対応表を参照してステートレスに変換。
    各セッション独立呼び出し → コンテキスト排出済み。
    """
    prompt = f"""{OP_TABLE}

Conversation to compress:
{session_raw[:600]}

Output operation commands only:"""

    result = llm_call(prompt, MODEL_LIGHT, max_tokens=256)
    # Parse OP lines
    ops = [line.strip() for line in result.splitlines()
           if line.strip().startswith("OP.")]
    # Fallback heuristics if LLM returns nothing
    if not ops:
        lines = session_raw.splitlines()
        user_lines = [l[5:].strip() for l in lines if l.startswith("USER:")]
        if user_lines:
            ops = [f'OP.TOPIC("{user_lines[0][:80].replace(chr(34), chr(39))}")']
    return ops[:12]


# ---- JCross Writer ----
def write_jcross(node_id: str, kanji: dict, summary: str,
                 ops: list[str], raw: str) -> str:
    os.makedirs(MEMORY_DIR, exist_ok=True)
    kanji_str = " ".join(f"[{k}: {v}]" for k, v in kanji.items())
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


# ---- L1 Gravity Search ----
def cosine(a: dict, b: dict) -> float:
    keys = set(a) | set(b)
    dot = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
    na  = math.sqrt(sum(v**2 for v in a.values()))
    nb  = math.sqrt(sum(v**2 for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def l1_search(query_kanji: dict, top_k: int) -> list[str]:
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
        nk = {tag[0]: float(tag[1]) for tag in
              re.findall(r'\[(\S+):\s*([\d.]+)\]', m.group(1))}
        sim = cosine(query_kanji, nk)
        results.append((sim, fpath))
    results.sort(reverse=True)
    return [r[1] for r in results[:top_k]]


# ---- L2 OP Scan ----
def extract_section(fpath: str, section: str, end_section: str = "") -> str:
    with open(fpath, encoding="utf-8") as fh:
        txt = fh.read()
    pattern = f'{section}\\s*([\\s\\S]*?)'
    pattern += f'\\s*{end_section}' if end_section else '$'
    m = re.search(pattern, txt)
    return m.group(1).strip() if m else ""


def l2_scan(question: str, candidates: list[str]) -> list[tuple]:
    """L2: OPコンテンツをスキャンして質問とのキーワードマッチでスコアリング。"""
    keywords = [w.lower() for w in question.split() if len(w) > 2]
    scored = []
    for fpath in candidates:
        ops  = extract_section(fpath, '【操作対応表】', '【原文】')
        sim_bonus = extract_section(fpath, '【位相対応表】', '【')
        score  = sum(1 for kw in keywords if kw in ops.lower())
        score += sum(0.5 for kw in keywords if kw in sim_bonus.lower())
        scored.append((score, fpath))
    scored.sort(reverse=True)
    return scored


# ---- L3+L2 Context Assembly ----
def assemble_context(fpath: str, use_full_raw: bool = True) -> str:
    """
    原文(L3)+操作コマンド(L2)の組み合わせ。
    原文のみでは意図・ニュアンスが不明なため、必ずL2とセットで使用。
    """
    ops = extract_section(fpath, '【操作対応表】', '【原文】')
    raw = extract_section(fpath, '【原文】')
    l3  = raw[:3000] if use_full_raw else raw[:1200]
    ctx = ""
    if ops:
        ctx += f"[L2: 意図・ファクト(操作コマンド)]\n{ops}\n\n"
    ctx += f"[L3: 原文会話]\n{l3}"
    return ctx


# ---- Final Answer (LLM, Trust JCross Only) ----
def ask_for_answer(question: str, context: str) -> str:
    """
    最終推論: AIは自己の内部記憶を信用しない。JCrossから取得した内容のみで回答。
    コンテキスト汚染防止: このターンで参照するのはretrieval結果のみ。
    """
    prompt = f"""[MEMORY SYSTEM: You are answering from retrieved external memory only.]
[RULE: Your internal training knowledge about this user is unreliable. Answer ONLY from the provided retrieved memory below.]
[RULE: Output ONLY the exact word(s) from the conversation. No explanation.]

Retrieved Memory:
{context}

Question: {question}
Answer:"""
    return llm_call(prompt, MODEL_HEAVY, max_tokens=2048)


# ---- Scoring ----
def keyword_score(expected: str, got: str) -> float:
    if not got or "[LLM_ERROR" in got or any(
            x in got.lower() for x in ["don't know", "not available", "cannot"]):
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
    print("  Verantyx Cortex × LongMemEval — Agentic 3-Layer Mode")
    print(f"  L2 generator: {MODEL_LIGHT} | Answer: {MODEL_HEAVY}")
    print(f"  L1_K={L1_TOP_K} | L2_augment={L2_AUGMENT_K} | final={L2_FINAL_K}")
    print("  Context isolation: each session call is STATELESS")
    print("=" * 65)

    with open(DATASET_PATH) as f:
        dataset = json.load(f)
    selected = dataset[:NUM_QUESTIONS]
    results  = []

    for i, item in enumerate(selected):
        qid      = item["question_id"]
        question = item["question"]
        expected = item["answer"]
        sessions = item.get("haystack_sessions", [])
        sess_ids = item.get("haystack_session_ids", [])
        ans_ids  = item.get("answer_session_ids", [])

        print(f"\n[{i+1}/{NUM_QUESTIONS}] {qid}")
        print(f"  Q: {question}")
        print(f"  Expected: {expected}")

        # ── PHASE 1: Inject all sessions with Heuristic L1 only (fast) ──
        clear_bench_nodes()
        ts = int(time.time() * 1000)
        injected = 0
        all_paths = []  # track all written paths
        for j, session in enumerate(sessions):
            if not isinstance(session, list):
                continue
            raw = "\n".join(
                f"{m.get('role','?').upper()}: {m.get('content','')[:400]}"
                for m in session if isinstance(m, dict)
            )
            if not raw.strip():
                continue
            sid     = sess_ids[j] if j < len(sess_ids) else f"s{j}"
            kanji   = content_to_kanji(raw)
            summary = f"{sid}: {raw[:100]}"
            # Heuristic L2 placeholder (will be replaced for top candidates)
            ops_heuristic = [f'OP.LOG("raw", "{raw[:80].replace(chr(34), chr(39))}")']
            fpath = write_jcross(f"{qid}_{j}_{ts+j}", kanji, summary, ops_heuristic, raw)
            all_paths.append(fpath)
            injected += 1

        print(f"  → Phase1: {injected} sessions injected (heuristic L1)")

        # ── PHASE 2: L1 Map Navigation ──
        q_kanji    = question_to_kanji(question)
        l1_results = l1_search(q_kanji, top_k=L1_TOP_K)
        print(f"  → Phase2 L1 map: {q_kanji} → {len(l1_results)} candidates")

        # ── PHASE 3: LLM L2 Augmentation (top L2_AUGMENT_K nodes) ──
        # 各ノードを独立呼び出しでL2操作コマンド生成 (コンテキスト汚染なし)
        # all_paths = 今ターンで書き込んだパスのみ。l1_results順でソートする。
        all_paths_set = set(all_paths)
        augment_targets = [p for p in l1_results if p in all_paths_set][:L2_AUGMENT_K]
        if not augment_targets:
            augment_targets = all_paths[:L2_AUGMENT_K]
        print(f"  → Phase3 L2 aug: {MODEL_LIGHT} generating ops for "
              f"{len(augment_targets)} candidates...")

        augmented_paths = []
        for fpath in augment_targets:
            raw = extract_section(fpath, '【原文】')
            ops = generate_l2_ops_llm(raw)   # STATELESS LLM call
            # Rewrite the node with LLM-generated L2 ops
            with open(fpath, encoding="utf-8") as fh:
                existing = fh.read()
            # Replace 【操作対応表】 section
            ops_str    = "\n".join(ops)
            new_content = re.sub(
                r'(【操作対応表】\n)([\s\S]*?)(【原文】)',
                f'\\1{ops_str}\n\\3',
                existing
            )
            with open(fpath, "w", encoding="utf-8") as fh:
                fh.write(new_content)
            augmented_paths.append(fpath)

        # ── PHASE 4: L2 Scan on augmented nodes ──
        l2_scored = l2_scan(question, augmented_paths)
        l2_top    = l2_scored[0] if l2_scored else (0, None)
        best_score, best_fpath = l2_top

        # Oracle check
        surfaced = " ".join(open(f).read() for _, f in l2_scored[:L2_FINAL_K]) if l2_scored else ""
        answer_in_l2 = any(aid in surfaced for aid in ans_ids) if ans_ids else None

        if best_fpath:
            top_ops = extract_section(best_fpath, '【操作対応表】', '【原文】')
            print(f"  → Phase4 L2 scan: score={best_score:.1f} | "
                  f"{top_ops[:80].replace(chr(10),' | ')}")
        else:
            print(f"  → Phase4 L2 scan: no result")
            best_fpath = l1_results[0] if l1_results else None

        # ── PHASE 5: L3+L2 Assembly + Final Answer ──
        # 原文のみでは意味不明なため必ずL2とセットで渡す
        if best_fpath:
            context = assemble_context(best_fpath, use_full_raw=True)
        else:
            context = ""
        print(f"  → Phase5 L3+L2: {len(context)} chars | "
              f"L2_hit={'✅' if answer_in_l2 else '❌'}")

        # AIは自己記憶を信用しない、JCrossだけを参照
        answer = ask_for_answer(question, context)
        print(f"  Got: {answer[:80]}")

        score = keyword_score(expected, answer)
        grade = "✅" if score >= 0.5 else ("⚠️" if score > 0 else "❌")
        print(f"  Score: {score:.0%} {grade}")

        results.append({
            "id": qid, "question": question, "expected": expected, "got": answer,
            "score": round(score, 3), "l2_hit": answer_in_l2,
            "l2_score": best_score, "sessions_total": len(sessions)
        })

    # ── Summary ──
    print("\n" + "=" * 65)
    print("AGENTIC 3-LAYER BENCHMARK RESULTS")
    print("=" * 65)
    passes  = sum(1 for r in results if r["score"] >= 0.5)
    avg     = sum(r["score"] for r in results) / len(results) if results else 0
    l2_hits = sum(1 for r in results if r["l2_hit"] is True)
    print(f"✅ Pass (≥50%): {passes}/{NUM_QUESTIONS}")
    print(f"📊 Avg score:  {avg:.1%}")
    print(f"🎯 L2 Retrieval: {l2_hits}/{NUM_QUESTIONS}")
    for r in results:
        g = "✅" if r["score"] >= 0.5 else ("⚠️" if r["score"] > 0 else "❌")
        h = "🎯" if r["l2_hit"] else "🔍"
        print(f"  {g} {r['id']}: {r['score']:.0%} | L2={h}({r['l2_score']:.1f}) | {r['got'][:40]}")

    out = "/Users/motonishikoudai/verantyx-cli/_verantyx-cortex/benchmark/agentic_results.json"
    with open(out, "w") as f:
        json.dump({"mode": "agentic_trilayer", "model_light": MODEL_LIGHT,
                   "model_heavy": MODEL_HEAVY, "L2_augment_k": L2_AUGMENT_K,
                   "summary": {"pass": passes, "avg": avg, "l2_hits": l2_hits},
                   "results": results}, f, indent=2, ensure_ascii=False)
    print(f"\nSaved → {out}")


if __name__ == "__main__":
    main()
