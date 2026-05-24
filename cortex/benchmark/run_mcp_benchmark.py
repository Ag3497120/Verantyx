#!/usr/bin/env python3
"""
run_mcp_benchmark.py — Verantyx Memory Benchmark (Public Edition)
================================================================
A fair, publishable benchmark measuring JCross memory retrieval + LLM accuracy
on the LongMemEval dataset.

Rules (no cheating):
  1. Model receives ONLY: question + retrieved JCross context (no ground truth)
  2. Retrieval: keyword search over JCross deep/ nodes (same logic as MCP search tool)
  3. Scoring: token-level F1 (official LongMemEval metric) by question type
  4. "impossible" answers: model must output refusal ("I don't know" / "not mentioned")
  5. Results saved incrementally; re-runs continue from last checkpoint

Usage:
  python3 run_mcp_benchmark.py [--limit 500] [--top-k 15] [--model gemma4:26b]
"""

import json, os, re, sys, time, argparse
import urllib.request

DB_PATH    = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/data/longmemeval_s_cleaned.json"
OUT_PATH   = "/Users/motonishikoudai/verantyx-cli/_verantyx-cortex/benchmark/gemma4_mcp_results.json"
MEMORY_DIR = os.path.expanduser("~/.verantyx/memory/deep")
OLLAMA_URL = "http://localhost:11434/api/generate"

# ── Scoring ────────────────────────────────────────────────────────────────────

REFUSAL_PHRASES = [
    "not mentioned", "did not mention", "don't know", "do not know",
    "not found", "no information", "not provided", "not specified",
    "i cannot", "i can't", "unable to find", "not available",
    "not stated", "not given", "never mentioned",
]

def is_impossible_answer(expected: str) -> bool:
    """True if the ground truth answer is itself a refusal / 'not mentioned'."""
    el = expected.lower()
    return any(p in el for p in REFUSAL_PHRASES)

def normalize(text: str) -> list[str]:
    """Tokenize for F1 scoring (lowercase, strip punctuation, split)."""
    text = str(text).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return [t for t in text.split() if t]

def token_f1(predicted: str, ground_truth: str) -> float:
    """Standard token-level F1 used in SQuAD / LongMemEval."""
    pred_tokens = normalize(predicted)
    gold_tokens = normalize(ground_truth)
    if not pred_tokens or not gold_tokens:
        return 0.0
    common = set(pred_tokens) & set(gold_tokens)
    if not common:
        return 0.0
    precision = len([t for t in pred_tokens if t in common]) / len(pred_tokens)
    recall    = len([t for t in gold_tokens if t in common]) / len(gold_tokens)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)

def score_answer(expected: str, agent: str) -> tuple[bool, float, str]:
    """
    Returns (is_correct, f1_score, verdict).

    For impossible questions: correct iff model outputs a refusal.
    For normal questions: correct iff F1 >= 0.5 (standard threshold).
    """
    agent    = str(agent).strip()
    expected = str(expected).strip()

    impossible = is_impossible_answer(expected)
    agent_refused = (
        agent == "" or
        any(p in agent.lower() for p in REFUSAL_PHRASES)
    )

    if impossible:
        if agent_refused:
            return True, 1.0, "impossible+correct"
        else:
            return False, 0.0, "impossible+hallucinated"
    else:
        if agent_refused:
            return False, 0.0, "refused"
        f1 = token_f1(agent, expected)
        correct = f1 >= 0.5
        return correct, f1, f"f1={f1:.2f}"

# ── JCross retrieval ───────────────────────────────────────────────────────────

STOP = {"what","how","when","where","who","did","does","is","was","my","the",
        "a","an","i","do","have","has","are","were","be","been","in","on","at",
        "to","for","of","and","or","it","its","their","there","that","long","often"}

def build_keywords(query: str):
    words = [w.lower().strip("?.,!") for w in query.split()
             if len(w) > 2 and w.lower().strip("?.,!") not in STOP]
    phrases = [f"{words[i]} {words[i+1]}" for i in range(len(words)-1)]
    return words, phrases

def score_node(content: str, words: list, phrases: list) -> int:
    ops_m = re.search(r"【操作対応表】([\s\S]*?)(?:【原文】|$)", content)
    raw_m = re.search(r"【原文】([\s\S]*)$", content)
    ops   = (ops_m.group(1) if ops_m else "").lower()
    raw   = (raw_m.group(1) if raw_m else content).lower()[:3000]
    score  = sum(4 for p in phrases if p in ops)
    score += sum(2 for p in phrases if p in raw)
    score += sum(1 for w in words  if w in ops)
    score += sum(1 for w in words  if w in raw)
    return score

_node_cache: dict = {}

def load_nodes():
    global _node_cache
    if _node_cache:
        return
    print(f"   Loading JCross nodes from {MEMORY_DIR}...", end="", flush=True)
    if not os.path.exists(MEMORY_DIR):
        print(" NOT FOUND — run ingest_sessions.py first"); sys.exit(1)
    for f in os.listdir(MEMORY_DIR):
        if f.endswith(".jcross"):
            try:
                _node_cache[f] = open(os.path.join(MEMORY_DIR, f), encoding="utf-8").read()
            except Exception:
                pass
    print(f" {len(_node_cache)} nodes loaded")

def mcp_search(question: str, top_k: int) -> str:
    words, phrases = build_keywords(question)
    scored = []
    for fname, content in _node_cache.items():
        s = score_node(content, words, phrases)
        if s > 0:
            scored.append((s, content))
    scored.sort(key=lambda x: -x[0])
    parts = []
    for score, content in scored[:top_k]:
        raw_m = re.search(r"【原文】([\s\S]*)$", content)
        raw   = (raw_m.group(1).strip() if raw_m else content)[:800]
        parts.append(f"[score={score}]\n{raw}")
    return "\n\n---\n\n".join(parts)

# ── Ollama ────────────────────────────────────────────────────────────────────

def build_prompt(question: str, context: str, qtype: str) -> str:
    impossible_hint = ""
    if "You did not mention" in context or "not found" in context.lower():
        impossible_hint = (
            "\nNote: If the information was never mentioned in the conversation, "
            "reply exactly: I don't know"
        )
    return (
        f"You are a memory assistant. Based ONLY on the conversation history below, "
        f"answer the question with the exact information from the conversation.\n"
        f"- Reply with ONLY the direct answer (no explanation, no full sentence).\n"
        f"- If the answer is not in the conversation, reply: I don't know\n"
        f"{impossible_hint}\n\n"
        f"Question: {question}\n\n"
        f"Conversation history:\n{context}\n\n"
        f"Answer:"
    )

def ollama_generate(model: str, prompt: str, timeout: int = 60) -> str:
    payload = json.dumps({
        "model": model, "prompt": prompt, "stream": False,
        "think": False,
        "options": {"temperature": 0.0, "num_predict": 150},
    }).encode()
    req = urllib.request.Request(
        OLLAMA_URL, data=payload,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            resp = json.load(r).get("response", "").strip()
            # Take first line only (avoid multi-line hallucination)
            return resp.split("\n")[0].strip().strip('"').strip("'")
    except Exception as e:
        return f"ERROR:{e}"

# ── Results I/O ───────────────────────────────────────────────────────────────

def load_results() -> dict:
    if os.path.exists(OUT_PATH):
        try:
            return {str(r["id"]): r for r in json.load(open(OUT_PATH, encoding="utf-8"))}
        except Exception:
            pass
    return {}

def save_results(results: dict):
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(list(results.values()), f, indent=2, ensure_ascii=False)

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Verantyx MCP Memory Benchmark (Fair Edition)")
    parser.add_argument("--model",  default="gemma4:26b", help="Ollama model")
    parser.add_argument("--limit",  type=int, default=500, help="Max questions")
    parser.add_argument("--top-k",  type=int, default=15,  help="Nodes to retrieve per question")
    args = parser.parse_args()

    print(f"🧠 Verantyx Memory Benchmark")
    print(f"   Model:  {args.model}  |  top_k: {args.top_k}  |  limit: {args.limit}")
    print(f"   Metric: Token-level F1 (threshold=0.5)  |  impossible: refusal detection")

    db      = json.load(open(DB_PATH, encoding="utf-8"))[:args.limit]
    results = load_results()
    load_nodes()

    # Recompute correct count from saved results
    db_map   = {str(q.get("question_id") or q.get("id")): q for q in db}
    n_correct = 0
    for r in results.values():
        q = db_map.get(str(r["id"]))
        if q:
            ok, _, _ = score_answer(str(q["answer"]), r.get("answer_agent", ""))
            n_correct += ok
    n_answered = len(results)

    print(f"   Already done: {n_answered} | Correct: {n_correct}\n")
    print(f"{'#':>5} {'Type':<28} {'Expected':<22} {'Agent':<22} {'Verdict':<20} Acc%")
    print("─" * 105)

    for q in db:
        qid      = str(q.get("question_id") or q.get("id"))
        question = q["question"]
        expected = str(q["answer"])
        qtype    = q.get("question_type", "unknown")

        if qid in results:
            continue

        # ── Retrieval (no ground truth passed) ──
        context = mcp_search(question, top_k=args.top_k)

        # ── Inference ──
        prompt = build_prompt(question, context, qtype)
        agent  = ollama_generate(args.model, prompt)

        # ── Scoring ──
        correct, f1, verdict = score_answer(expected, agent)
        n_answered += 1
        if correct:
            n_correct += 1
        acc = n_correct / n_answered * 100

        results[qid] = {
            "id":           qid,
            "question_type": qtype,
            "answer_agent": agent,
            "expected":     expected,
            "f1":           round(f1, 3),
            "correct":      correct,
        }
        save_results(results)

        mark = "✅" if correct else ("⏭" if "refused" in verdict or "impossible+correct" in verdict else "❌")
        print(
            f"{n_answered:>5} {qtype:<28} {expected[:20]:<22} {agent[:20]:<22} {verdict:<20} {acc:.1f}%"
        )

    # ── Final report ──────────────────────────────────────────────────────────
    print("\n" + "═" * 60)
    print(f"  🏁 FINAL RESULTS — {n_answered}/{args.limit} answered")
    print(f"  ✅ Overall accuracy (F1≥0.5): {n_correct}/{n_answered} = {n_correct/n_answered*100:.1f}%")
    print(f"  📊 Average F1: {sum(r.get('f1',0) for r in results.values())/len(results)*100:.1f}%")

    # By question type
    type_stats: dict = {}
    for r in results.values():
        qt = r.get("question_type", "unknown")
        if qt not in type_stats:
            type_stats[qt] = {"correct": 0, "total": 0, "f1_sum": 0.0}
        type_stats[qt]["total"]   += 1
        type_stats[qt]["correct"] += 1 if r.get("correct") else 0
        type_stats[qt]["f1_sum"]  += r.get("f1", 0.0)
    print("\n  By question type:")
    for qt, s in sorted(type_stats.items()):
        acc_t = s["correct"] / s["total"] * 100
        f1_t  = s["f1_sum"]  / s["total"] * 100
        print(f"    {qt:<32} {s['correct']:>3}/{s['total']:>3}  acc={acc_t:.1f}%  avgF1={f1_t:.1f}%")
    print("═" * 60)
    print(f"\n  Results saved to: {OUT_PATH}")

if __name__ == "__main__":
    main()
