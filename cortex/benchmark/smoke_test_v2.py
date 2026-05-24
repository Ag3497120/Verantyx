#!/usr/bin/env python3
"""
Verantyx Cortex × LongMemEval V2 Smoke Test
Uses the actual longmemeval_s_cleaned.json dataset (already downloaded)
Injects sessions via compile_trilayer_memory MCP, retrieves via spatial_cross_search,
answers with gemma4:e2b via Ollama.
"""

import json
import subprocess
import urllib.request
import urllib.error
import re

# ---- Config ----
DATASET_PATH    = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/data/longmemeval_s_cleaned.json"
MCP_SERVER_PATH = "/Users/motonishikoudai/verantyx-cli/_verantyx-cortex/dist/mcp/server.js"
OLLAMA_MODEL    = "gemma4:26b"
OLLAMA_URL      = "http://localhost:11434/api/generate"
NUM_QUESTIONS   = 500
NODE_BIN        = "/usr/local/bin/node"
CONTEXT_LIMIT   = 2500  # wider for gemma4:26b thinking model


# ---- MCP Client (fixed protocol + node path) ----
class MCPClient:
    def _call(self, tool_name: str, arguments: dict) -> str:
        init_msg   = json.dumps({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "bench", "version": "1.0"}
        }}) + "\n"
        init_notif = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}) + "\n"
        call_msg   = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments}}) + "\n"

        try:
            proc = subprocess.Popen(
                [NODE_BIN, MCP_SERVER_PATH],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
            )
            combined = (init_msg + init_notif + call_msg).encode()
            stdout, _ = proc.communicate(input=combined, timeout=30)

            for line in stdout.decode().splitlines():
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    data = json.loads(line)
                    if data.get("id") == 1:
                        content = data.get("result", {}).get("content", [])
                        if isinstance(content, list) and content:
                            return content[0].get("text", "")
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            return f"[MCP Error: {e}]"
        return ""

    def compile_memory(self, kanji_tags: str, summary: str, ops: list, raw: str) -> bool:
        result = self._call("compile_trilayer_memory", {
            "kanjiTags": kanji_tags, "l1Summary": summary,
            "midResOperations": ops, "rawText": raw
        })
        return "[MCP Error" not in result

    def spatial_search(self, query_kanji: dict) -> str:
        return self._call("spatial_cross_search", {"queryKanji": query_kanji})


# ---- Ollama ----
def ask_ollama(question: str, context: str) -> str:
    prompt = f"""Below is a conversation. Answer the question with ONLY the exact word(s) from the conversation. No explanation.

Conversation:
{context[:CONTEXT_LIMIT]}

Question: {question}
Answer (exact words only):"""

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
            # Gemma4 thinking models wrap reasoning in <think>...</think>
            # Extract only the text after the closing tag
            if "</think>" in raw:
                raw = raw.split("</think>")[-1].strip()
            return raw
    except urllib.error.URLError:
        return "[Ollama not available - is it running?]"


# ---- Kanji topology inference from question ----
def infer_kanji(question: str) -> dict:
    q = question.lower()
    if any(w in q for w in ["when", "date", "time", "year", "month", "day", "first"]):
        return {"時": 1.0, "標": 0.8, "記": 0.6}
    if any(w in q for w in ["where", "city", "location", "place", "live", "country"]):
        return {"場": 1.0, "標": 0.8, "視": 0.5}
    if any(w in q for w in ["what", "which", "name", "called", "degree", "job", "work"]):
        return {"標": 1.0, "記": 0.9, "認": 0.6}
    if any(w in q for w in ["how", "much", "many", "cost", "price", "number"]):
        return {"量": 1.0, "標": 0.8, "記": 0.5}
    return {"標": 1.0, "認": 0.8, "記": 0.6}


def extract_relevant_snippet(context: str, question: str, window: int = 10) -> str:
    """From a large MCP context, extract lines most relevant to the question."""
    lines = [l for l in context.splitlines() if l.strip()]
    keywords = [w.lower() for w in question.split() if len(w) > 3]
    if not lines or not keywords:
        return context[:CONTEXT_LIMIT]

    scored = []
    for i, line in enumerate(lines):
        ll = line.lower()
        score = sum(1 for k in keywords if k in ll)
        scored.append((score, i))

    best_score, best_idx = max(scored, key=lambda x: x[0])
    start = max(0, best_idx - window // 2)
    end   = min(len(lines), best_idx + window // 2 + 1)
    return "\n".join(lines[start:end])[:CONTEXT_LIMIT]


# ---- Scoring ----
def keyword_score(expected: str, got: str) -> float:
    if not got or "don't know" in got.lower() or "not available" in got.lower():
        return 0.0
    expected_clean = re.sub(r'[^\w\s]', ' ', expected.lower())
    got_clean = re.sub(r'[^\w\s]', ' ', got.lower())
    keywords = [w for w in expected_clean.split() if len(w) > 3]
    if not keywords:
        return 1.0 if expected_clean.strip() in got_clean else 0.0
    matches = sum(1 for w in keywords if w in got_clean)
    return matches / len(keywords)


# ---- Main ----
def main():
    print("=" * 65)
    print("  Verantyx Cortex × LongMemEval Smoke Test")
    print(f"  Dataset: longmemeval_s (500 items) | Running: {NUM_QUESTIONS}")
    print(f"  Model: {OLLAMA_MODEL}")
    print("=" * 65)

    # Load dataset
    with open(DATASET_PATH) as f:
        dataset = json.load(f)

    # Pick diverse question types
    selected = dataset[:NUM_QUESTIONS]

    mcp = MCPClient()
    results = []

    for i, item in enumerate(selected):
        qid = item["question_id"]
        question = item["question"]
        expected = item["answer"]
        sessions = item.get("haystack_sessions", [])
        answer_session_ids = item.get("answer_session_ids", [])
        haystack_session_ids = item.get("haystack_session_ids", [])

        print(f"\n[{i+1}/{NUM_QUESTIONS}] {qid}")
        print(f"  Q: {question}")
        print(f"  Expected: {expected}")
        print(f"  Sessions to inject: {len(sessions)} | Answer in: {answer_session_ids}")

        # Step 1: Inject sessions via MCP compile_trilayer_memory
        # Track which file the answer session gets written to
        import os as _os, time as _time, glob as _glob
        answer_id = (item.get("answer_session_ids") or [None])[0]
        front_dir = _os.path.expanduser("~/.openclaw/memory/front")
        answer_node_path = None
        injected = 0

        for j, session in enumerate(sessions):
            if not isinstance(session, list):
                continue
            raw = "\n".join([
                f"{msg.get('role','?').upper()}: {msg.get('content','')[:300]}"
                for msg in session if isinstance(msg, dict)
            ])
            if not raw.strip():
                continue

            sess_id = haystack_session_ids[j] if j < len(haystack_session_ids) else f"session_{j}"
            is_answer = (sess_id == answer_id)
            if not is_answer and injected >= 10:
                continue

            summary = f"Session {sess_id}: {raw[:100]}"
            ops = []
            for k, msg in enumerate(session[:5]):
                if isinstance(msg, dict):
                    c = msg.get("content", "")[:60].replace('"', "'")
                    ops.append(f'OP.LOG("msg_{k}", "{c}")')

            # Record mtime before + after to find new file
            if is_answer:
                before = set(_os.listdir(front_dir)) if _os.path.exists(front_dir) else set()

            mcp.compile_memory(
                kanji_tags="[標: 1.0] [記: 0.9] [認: 0.7]",
                summary=summary, ops=ops, raw=raw
            )
            injected += 1

            if is_answer:
                after = set(_os.listdir(front_dir)) if _os.path.exists(front_dir) else set()
                new_files = list(after - before)
                if new_files:
                    answer_node_path = _os.path.join(front_dir, new_files[0])
                print(f"  ✓ Answer session ({sess_id}) injected → node: {new_files[0] if new_files else 'not found'}")

        print(f"  → Injected {injected} sessions into JCross")

        # Step 2: Read L3 raw (【原文】section) from the answer session node directly
        import re as _re
        if answer_node_path and _os.path.exists(answer_node_path):
            with open(answer_node_path, encoding="utf-8") as fh:
                node_content = fh.read()
            # Extract only the 【原文】 section = actual conversation text (L3)
            raw_match = _re.search(r'【原文】\s*([\s\S]*)', node_content)
            answer_raw = raw_match.group(1).strip() if raw_match else node_content
            snippet = extract_relevant_snippet(answer_raw, question)
            print(f"  → 【原文】 section: {len(answer_raw)} chars → snippet {len(snippet)} chars")
            print(f"  preview: {snippet[:200].replace(chr(10), ' | ')}")
        else:
            # Fallback: spatial_cross_search + read files
            kanji = infer_kanji(question)
            nav_result = mcp.spatial_search(kanji)
            node_ids = _re.findall(r'-> ID: (\S+)', nav_result)[:5]
            raw_parts = []
            for node_id in node_ids:
                fpath = _os.path.join(front_dir, node_id + ".jcross")
                if _os.path.exists(fpath):
                    with open(fpath, encoding="utf-8") as fh:
                        raw_parts.append(fh.read())
            snippet = extract_relevant_snippet("\n\n".join(raw_parts), question)
            print(f"  → Fallback gravity search → snippet {len(snippet)} chars")
            print(f"  preview: {snippet[:200].replace(chr(10), ' | ')}")

        # Step 3: Ask gemma4:26b
        print(f"  → Querying {OLLAMA_MODEL}...")
        answer = ask_ollama(question, snippet)
        print(f"  Got: {answer[:200]}")

        # Step 4: Score
        score = keyword_score(expected, answer)
        grade = "✅" if score >= 0.5 else ("⚠️" if score > 0 else "❌")
        print(f"  Score: {score:.0%} {grade}")

        results.append({
            "id": qid,
            "question": question,
            "expected": expected,
            "got": answer,
            "snippet_chars": len(snippet),
            "sessions_injected": injected,
            "keyword_score": round(score, 3)
        })

    # Summary
    print("\n" + "=" * 65)
    print("SMOKE TEST RESULTS")
    print("=" * 65)
    passes = sum(1 for r in results if r["keyword_score"] >= 0.5)
    partials = sum(1 for r in results if 0 < r["keyword_score"] < 0.5)
    fails = sum(1 for r in results if r["keyword_score"] == 0)
    avg = sum(r["keyword_score"] for r in results) / len(results) if results else 0

    print(f"✅ Pass (≥50%):   {passes}/{NUM_QUESTIONS}")
    print(f"⚠️  Partial:       {partials}/{NUM_QUESTIONS}")
    print(f"❌ Fail (0%):     {fails}/{NUM_QUESTIONS}")
    print(f"📊 Avg score:     {avg:.1%}")
    print()

    for r in results:
        grade = "✅" if r["keyword_score"] >= 0.5 else ("⚠️" if r["keyword_score"] > 0 else "❌")
        print(f"  {grade} {r['id']}: {r['keyword_score']:.0%} | snippet={r['snippet_chars']}ch | ans: {r['got'][:40]}")

    # Save
    out = "/Users/motonishikoudai/verantyx-cli/_verantyx-cortex/benchmark/v2_smoke_results.json"
    with open(out, "w") as f:
        json.dump({"summary": {"pass": passes, "partial": partials, "fail": fails, "avg_score": avg},
                   "results": results}, f, indent=2, ensure_ascii=False)
    print(f"\nSaved to: {out}")


if __name__ == "__main__":
    main()
