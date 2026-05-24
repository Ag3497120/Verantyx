#!/usr/bin/env python3
"""
Verantyx MCP Agent Benchmark — Gemini Flash × LongMemEval

通常のPythonヒューリスティック方式と異なり、
Gemini Flash に MCP ツールを function calling で渡し、
エージェントとして自律的に記憶を検索・回答させる。

Flow per question:
  Gemini Flash
    → memory_map()       でメモリ全体を俯瞰
    → semantic_op_search() or read_node() で精密取得
    → 回答を返す
"""

import json, os, re, time, glob
import urllib.request, urllib.error

# ---- Config ----
DATASET_PATH  = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/data/longmemeval_s_cleaned.json"
MEMORY_ROOT   = os.path.expanduser("~/.openclaw/memory")
GEMINI_API_KEY = "AIzaSyATPOY0fmk94_bOWvkj13tvXGIegyjsZKE"
GEMINI_MODEL   = "gemini-2.0-flash"   # 変更可: gemini-2.5-flash-preview-04-17
NUM_QUESTIONS  = 7                     # テスト用: 本番は 500
RESULTS_PATH   = "/Users/motonishikoudai/verantyx-cli/_verantyx-cortex/benchmark/mcp_agent_results.json"
ZONES          = ["front", "near", "mid", "deep"]
MAX_TOOL_TURNS = 5   # エージェントのツール呼び出し上限


# ============================================================
# MCP Tool 実装 (server.ts の Python 移植版)
# ============================================================

def mcp_memory_map(zones=None, max_nodes=100, query_text=None):
    """全ノードを L1.5 索引で俯瞰 (~60文字/行)"""
    if zones is None:
        zones = ["front"]
    output = "[MEMORY MAP]\n"

    for zone in zones:
        dirpath = os.path.join(MEMORY_ROOT, zone)
        if not os.path.isdir(dirpath):
            output += f"\n{zone}: (empty)\n"
            continue
        files = sorted([f for f in os.listdir(dirpath) if f.endswith(".jcross")])
        output += f"\n{zone}/ — {len(files)} nodes\n"

        if zone == "front" or len(files) <= 200:
            # relevanceソート
            if query_text:
                qwords = [w.lower() for w in query_text.split() if len(w) > 2]
                def score(f):
                    try:
                        c = open(os.path.join(dirpath, f), encoding="utf-8").read().lower()
                        return sum(1 for w in qwords if w in c)
                    except: return 0
                files = sorted(files, key=score, reverse=True)

            for fname in files[:max_nodes]:
                try:
                    content = open(os.path.join(dirpath, fname), encoding="utf-8").read()
                    # L1.5 優先
                    m = re.search(r'【L1\.5索引】\s*([^\n【]+)', content)
                    if m:
                        index_line = m.group(1).strip()
                    else:
                        # フォールバック
                        k = re.search(r'【空間座相】\s*([^\n【]+)', content)
                        op = re.search(r'OP\.[A-Z]+\("([^"]{2,30})"', content)
                        kanji_raw = re.sub(r':\s*[\d.]+', '', k.group(1) if k else '?')
                        kanji_raw = re.sub(r'[\[\]\s]', '', kanji_raw)[:6]
                        index_line = f'[{kanji_raw}] | "{op.group(1)[:40] if op else "no index"}"'
                    output += f"  {fname.replace('.jcross','')} {index_line}\n"
                except:
                    output += f"  {fname.replace('.jcross','')} [read error]\n"

            if len(files) > max_nodes:
                output += f"  ... and {len(files)-max_nodes} more\n"
        else:
            # 大量ゾーン: Kanji ヒストグラム
            kanji_freq = {}
            for fname in files:
                try:
                    content = open(os.path.join(dirpath, fname), encoding="utf-8").read()
                    for m in re.findall(r'\[([^\]:]+):\s*[\d.]+\]', content):
                        kanji_freq[m] = kanji_freq.get(m, 0) + 1
                except: pass
            hist = "  ".join(f"{k}×{v}" for k, v in sorted(kanji_freq.items(), key=lambda x: -x[1])[:15])
            output += f"  Topics: {hist}\n"
            output += f"  (Use query_text param or semantic_op_search for targeted retrieval)\n"

    return output.strip()


def mcp_read_node(file_name, zone=None, layer="l2l3"):
    """特定ノードの L1/L2/L3 を精密取得"""
    search_zones = [zone] if zone else ZONES
    content = None
    found_zone = ""

    for z in search_zones:
        fpath = os.path.join(MEMORY_ROOT, z, file_name)
        if os.path.exists(fpath):
            content = open(fpath, encoding="utf-8").read()
            found_zone = z
            break

    if not content:
        return f"Node '{file_name}' not found in zones: {search_zones}"

    result = f"[Node: {file_name} | Zone: {found_zone}]\n\n"

    if layer in ("l1", "l2l3"):
        l15 = re.search(r'【L1\.5索引】\s*([^\n【]+)', content)
        kanji = re.search(r'【空間座相】([\s\S]*?)【', content)
        result += f"=== L1 Kanji Topology ===\n{kanji.group(1).strip() if kanji else ''}\n"
        if l15:
            result += f"=== L1.5 Index ===\n{l15.group(1).strip()}\n"
        result += "\n"

    if layer in ("l2", "l2l3"):
        ops    = re.search(r'【操作対応表】([\s\S]*?)【原文】', content)
        nuance = re.search(r'【位相対応表】([\s\S]*?)【', content)
        result += "=== L2 Operations ===\n"
        if nuance: result += nuance.group(1).strip() + "\n"
        if ops:    result += ops.group(1).strip() + "\n"
        result += "\n"

    if layer in ("l3", "l2l3"):
        raw = re.search(r'【原文】([\s\S]*)', content)
        result += f"=== L3 Raw Context ===\n{raw.group(1).strip() if raw else 'no raw text'}"

    return result


def mcp_semantic_op_search(query_text, top_k=5, zones_hint=None):
    """L2 OP コマンドのセマンティック検索"""
    target_zones = zones_hint if zones_hint else ZONES
    qwords = [w.lower() for w in query_text.split() if len(w) > 2]
    scored = []

    for zone in target_zones:
        dirpath = os.path.join(MEMORY_ROOT, zone)
        if not os.path.isdir(dirpath): continue
        for fname in os.listdir(dirpath):
            if not fname.endswith(".jcross"): continue
            try:
                content = open(os.path.join(dirpath, fname), encoding="utf-8").read()
                ops_m = re.search(r'【操作対応表】([\s\S]*?)【原文】', content)
                ops_text = ops_m.group(1).lower() if ops_m else ""
                score = sum(1 for w in qwords if w in ops_text)
                if score > 0:
                    scored.append((score, zone, fname, ops_text[:200]))
            except: pass

    scored.sort(reverse=True)
    results = []
    for score, zone, fname, snippet in scored[:top_k]:
        results.append(f"[{zone}/{fname.replace('.jcross','')} | score={score}]\n{snippet}")
    return "\n\n".join(results) if results else "No matches found."


def mcp_aggregate_memory_search(query_text, top_k=5, zones_hint=None):
    """複数ノードの L2+L3 を集計 (累積質問用)"""
    target_zones = zones_hint if zones_hint else ZONES
    qwords = [w.lower() for w in query_text.split() if len(w) > 2]
    scored = []

    for zone in target_zones:
        dirpath = os.path.join(MEMORY_ROOT, zone)
        if not os.path.isdir(dirpath): continue
        for fname in os.listdir(dirpath):
            if not fname.endswith(".jcross"): continue
            try:
                content = open(os.path.join(dirpath, fname), encoding="utf-8").read()
                score = sum(1 for w in qwords if w in content.lower())
                if score > 0:
                    scored.append((score, zone, fname, content))
            except: pass

    scored.sort(reverse=True)
    parts = []
    for i, (score, zone, fname, content) in enumerate(scored[:top_k]):
        ops_m = re.search(r'【操作対応表】([\s\S]*?)【原文】', content)
        raw_m = re.search(r'【原文】([\s\S]*)', content)
        ops_text = ops_m.group(1).strip()[:300] if ops_m else ""
        raw_text = raw_m.group(1).strip()[:800] if raw_m else ""
        parts.append(f"[Memory {i+1} | {zone}/{fname.replace('.jcross','')} score={score}]\n{ops_text}\n{raw_text}")

    return "\n\n===\n\n".join(parts) if parts else "No relevant memories found."


# ============================================================
# Tool Definitions for Gemini Function Calling
# ============================================================

TOOL_DECLARATIONS = [
    {
        "name": "memory_map",
        "description": "Global memory overview. Returns one compact line per memory node (~60 chars). Use this FIRST to see what memories exist. Then use read_node for details.",
        "parameters": {
            "type": "object",
            "properties": {
                "zones":      {"type": "array", "items": {"type": "string"}, "description": "Zones to scan. Default: ['front']. Use ['front','near'] for broader search."},
                "max_nodes":  {"type": "integer", "description": "Max nodes to list per zone. Default: 100."},
                "query_text": {"type": "string", "description": "If provided, returns nodes sorted by relevance to this query."}
            },
            "required": []
        }
    },
    {
        "name": "read_node",
        "description": "Fetch a specific memory node's full content by filename. Zero context pollution — only the target node is loaded.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_name": {"type": "string", "description": "Exact filename (e.g., 'TURN_1776492446957.jcross'). Obtained from memory_map output."},
                "zone":      {"type": "string", "description": "Zone hint: 'front', 'near', 'mid', or 'deep'. Omit to search all zones."},
                "layer":     {"type": "string", "description": "Which layers: 'l1', 'l2', 'l3', 'l2l3' (default=full).", "enum": ["l1","l2","l3","l2l3"]}
            },
            "required": ["file_name"]
        }
    },
    {
        "name": "semantic_op_search",
        "description": "Search across L2 Operation Commands for facts, entities, quantities. Use for specific named entity lookups.",
        "parameters": {
            "type": "object",
            "properties": {
                "query_text":  {"type": "string", "description": "Natural language query. Example: 'yoga studio name' or 'graduation degree'"},
                "top_k":       {"type": "integer", "description": "Max results. Default: 5."},
                "zones_hint":  {"type": "array", "items": {"type": "string"}, "description": "Optional zone filter."}
            },
            "required": ["query_text"]
        }
    },
    {
        "name": "aggregate_memory_search",
        "description": "Multi-node aggregation search. Use for 'how many total', 'across all events', 'sum of' type questions.",
        "parameters": {
            "type": "object",
            "properties": {
                "query_text":  {"type": "string", "description": "Aggregation query."},
                "top_k":       {"type": "integer", "description": "Number of nodes to aggregate. Default: 5, max: 10."},
                "zones_hint":  {"type": "array", "items": {"type": "string"}, "description": "Optional zone filter."}
            },
            "required": ["query_text"]
        }
    }
]


def dispatch_tool(name, args):
    """ツール呼び出しディスパッチャ"""
    if name == "memory_map":
        return mcp_memory_map(
            zones=args.get("zones", ["front"]),
            max_nodes=args.get("max_nodes", 100),
            query_text=args.get("query_text")
        )
    elif name == "read_node":
        return mcp_read_node(
            file_name=args.get("file_name", ""),
            zone=args.get("zone"),
            layer=args.get("layer", "l2l3")
        )
    elif name == "semantic_op_search":
        return mcp_semantic_op_search(
            query_text=args["query_text"],
            top_k=args.get("top_k", 5),
            zones_hint=args.get("zones_hint")
        )
    elif name == "aggregate_memory_search":
        return mcp_aggregate_memory_search(
            query_text=args["query_text"],
            top_k=args.get("top_k", 5),
            zones_hint=args.get("zones_hint")
        )
    else:
        return f"Unknown tool: {name}"


# ============================================================
# Gemini Flash Agent Loop
# ============================================================

GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"


def call_gemini(contents, tools=None):
    """Gemini API 呼び出し"""
    body = {"contents": contents}
    if tools:
        body["tools"] = [{"function_declarations": tools}]
        body["tool_config"] = {"function_calling_config": {"mode": "AUTO"}}

    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        GEMINI_URL, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def extract_text(response):
    """レスポンスからテキストを抽出"""
    try:
        parts = response["candidates"][0]["content"]["parts"]
        texts = [p.get("text", "") for p in parts if "text" in p]
        return " ".join(texts).strip()
    except:
        return ""


def extract_tool_calls(response):
    """レスポンスからツール呼び出しを抽出"""
    try:
        parts = response["candidates"][0]["content"]["parts"]
        return [p["functionCall"] for p in parts if "functionCall" in p]
    except:
        return []


def agent_answer(question: str, session_ids: list) -> tuple[str, list]:
    """
    Gemini Flash エージェントが MCP ツールを自律的に使って質問に答える
    Returns: (answer, tool_call_log)
    """
    system_prompt = f"""You are a memory assistant with access to JCross spatial memory tools.

Your task: Answer the following question by searching through the memory store.

Strategy:
1. Call memory_map(query_text="<key keywords from question>", zones=["front","near"]) to see available memories
2. Identify the most relevant node(s) from the compact index
3. Call read_node(file_name="<exact filename>") to get full details
4. If the question requires totals/counts across sessions, use aggregate_memory_search
5. Answer with ONLY the specific value asked for. No explanation needed.

Question: {question}

IMPORTANT: Answer concisely with just the fact requested."""

    contents = [{"role": "user", "parts": [{"text": system_prompt}]}]
    tool_log = []

    for turn in range(MAX_TOOL_TURNS):
        try:
            response = call_gemini(contents, tools=TOOL_DECLARATIONS)
        except Exception as e:
            return f"[API Error: {e}]", tool_log

        finish_reason = response.get("candidates", [{}])[0].get("finishReason", "")
        tool_calls = extract_tool_calls(response)
        model_text = extract_text(response)

        # アシスタントの返答をコンテキストに追加
        assistant_parts = []
        if model_text:
            assistant_parts.append({"text": model_text})
        for tc in tool_calls:
            assistant_parts.append({"functionCall": tc})
        if assistant_parts:
            contents.append({"role": "model", "parts": assistant_parts})

        # ツール呼び出しがなければ終了
        if not tool_calls:
            return model_text, tool_log

        # ツールを実行して結果を返す
        tool_response_parts = []
        for tc in tool_calls:
            tool_name = tc["name"]
            tool_args = tc.get("args", {})
            result = dispatch_tool(tool_name, tool_args)
            tool_log.append(f"{tool_name}({json.dumps(tool_args, ensure_ascii=False)[:80]})")
            # 結果を切り捨て (Gemini のコンテキスト上限対策)
            if len(result) > 8000:
                result = result[:8000] + "\n[...truncated]"
            tool_response_parts.append({
                "functionResponse": {
                    "name": tool_name,
                    "response": {"result": result}
                }
            })

        contents.append({"role": "user", "parts": tool_response_parts})

    # MAX_TOOL_TURNS に達した場合、最後のテキストを返す
    return extract_text(response) if 'response' in dir() else "[max turns reached]", tool_log


# ============================================================
# Scoring
# ============================================================

def keyword_score(expected, got: str) -> float:
    expected = str(expected)
    got      = str(got) if got else ""
    if not got or any(x in got.lower() for x in ["don't know", "not available", "error", "api error"]):
        return 0.0
    # not-mentioned 型の正解
    if any(x in expected.lower() for x in ["not mentioned", "not stated", "never mentioned"]):
        if any(x in got.lower() for x in ["not mentioned", "not stated", "no information", "not found"]):
            return 1.0
        return 0.3
    ec = re.sub(r'[^\w\s]', ' ', expected.lower())
    gc = re.sub(r'[^\w\s]', ' ', got.lower())
    kw = [w for w in ec.split() if len(w) > 2]
    if not kw:
        return 1.0 if ec.strip() in gc else 0.0
    return sum(1 for w in kw if w in gc) / len(kw)


# ============================================================
# Main
# ============================================================

def main():
    print("=" * 70)
    print("  Verantyx MCP Agent Benchmark — Gemini Flash × LongMemEval")
    print(f"  Model: {GEMINI_MODEL} | Questions: {NUM_QUESTIONS}")
    print("  Mode: Agentic (memory_map → read_node / semantic_op_search)")
    print("=" * 70)

    with open(DATASET_PATH) as f:
        dataset = json.load(f)
    selected = dataset[:NUM_QUESTIONS]

    # Resume support
    results = []
    done_ids = set()
    if os.path.exists(RESULTS_PATH):
        try:
            existing = json.load(open(RESULTS_PATH))
            results = existing.get("results", [])
            done_ids = {r["id"] for r in results}
            print(f"\n  ♻️  Resuming from checkpoint: {len(done_ids)} questions already done\n")
        except:
            pass

    scores = [r["score"] for r in results]

    for i, item in enumerate(selected):
        qid        = item.get("id") or item.get("question_id", f"q{i}")
        question   = item.get("question", "")
        expected   = item.get("answer") or item.get("expected_answer", "")
        session_ids = item.get("answer_session_ids", [])

        if qid in done_ids:
            continue

        n = len(results) + 1
        print(f"\n[{n}/{NUM_QUESTIONS}] {qid}")
        print(f"  Q: {question[:80]}")
        print(f"  Expected: {str(expected)[:60]}")

        answer, tool_log = agent_answer(question, session_ids)

        print(f"  Tools used: {' → '.join(tool_log) if tool_log else '(none)'}")
        print(f"  Got: {answer[:100]}")

        score = keyword_score(expected, answer)
        grade = "✅" if score >= 0.5 else ("⚠️" if score > 0 else "❌")
        print(f"  Score: {score:.0%} {grade}")

        scores.append(score)
        results.append({
            "id": qid, "question": question,
            "expected": str(expected), "got": answer,
            "score": round(score, 3),
            "tools_used": tool_log
        })

        # インクリメンタル保存
        _n = len(results)
        _p = sum(1 for s in scores if s >= 0.5)
        _avg = sum(scores) / _n * 100
        with open(RESULTS_PATH, "w") as f:
            json.dump({
                "model": GEMINI_MODEL,
                "mode": "mcp_agent",
                "completed": _n,
                "pass_rate": round(_p/_n*100, 1),
                "avg_score": round(_avg, 1),
                "results": results
            }, f, indent=2, ensure_ascii=False)

        if _n % 5 == 0:
            print(f"\n  [{_n}/{NUM_QUESTIONS}] pass={_p}/{_n} ({_p/_n*100:.1f}%) avg={_avg:.1f}%")

        time.sleep(0.5)  # API レート制限対策

    # Final summary
    n  = len(results)
    p  = sum(1 for s in scores if s >= 0.5)
    pt = sum(1 for s in scores if 0 < s < 0.5)
    f  = sum(1 for s in scores if s == 0)
    avg = sum(scores) / n * 100

    print("\n" + "=" * 70)
    print("  MCP AGENT BENCHMARK RESULTS")
    print("=" * 70)
    print(f"  ✅ Pass (≥50%):  {p}/{n} = {p/n*100:.1f}%")
    print(f"  ⚠️  Partial:      {pt}/{n} = {pt/n*100:.1f}%")
    print(f"  ❌ Fail:         {f}/{n} = {f/n*100:.1f}%")
    print(f"  📊 Avg score:    {avg:.2f}%")
    print(f"\n  Saved → {RESULTS_PATH}")
    print("=" * 70)


if __name__ == "__main__":
    main()
