#!/usr/bin/env python3
"""
Verantyx Cortex × LongMemEval Smoke Test
- Runs 5-10 questions from LongMemEval
- Injects conversation history into JCross via MCP subprocess
- Retrieves context via spatial_cross_search
- Answers with local gemma4:e2b via Ollama
"""

import json
import subprocess
import sys
import urllib.request
import urllib.error

# ---- Config ----
OLLAMA_MODEL = "gemma4:e2b"
OLLAMA_URL = "http://localhost:11434/api/generate"
MCP_SERVER_PATH = "/Users/motonishikoudai/verantyx-cli/_verantyx-cortex/dist/mcp/server.js"
NUM_QUESTIONS = 7  # 5-10 range

# ---- MCP Tool Caller (via JSON-RPC over subprocess) ----
class MCPClient:
    def __init__(self, server_path: str):
        self.server_path = server_path
        self._proc = None

    def _send(self, method: str, params: dict) -> dict:
        payload = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params
        }) + "\n"

        proc = subprocess.Popen(
            ["node", self.server_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )
        stdout, _ = proc.communicate(input=payload.encode(), timeout=30)

        for line in stdout.decode().splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        return {}

    def compile_memory(self, kanji_tags: str, summary: str, ops: list, raw: str) -> bool:
        result = self._send("tools/call", {
            "name": "compile_trilayer_memory",
            "arguments": {
                "kanjiTags": kanji_tags,
                "l1Summary": summary,
                "midResOperations": ops,
                "rawText": raw
            }
        })
        return "result" in result

    def spatial_search(self, query_kanji: dict) -> str:
        result = self._send("tools/call", {
            "name": "spatial_cross_search",
            "arguments": {"queryKanji": query_kanji}
        })
        try:
            content = result["result"]["content"]
            if isinstance(content, list):
                return content[0].get("text", "")
            return str(content)
        except (KeyError, IndexError, TypeError):
            return ""


# ---- Ollama caller ----
def ask_ollama(prompt: str, context: str, model: str = OLLAMA_MODEL) -> str:
    full_prompt = f"""You are answering a question based only on the retrieved memory context below.
If the context doesn't contain the answer, say "I don't know."

[Memory Context]
{context if context.strip() else "(no relevant context retrieved)"}

[Question]
{prompt}

Answer concisely:"""

    payload = json.dumps({
        "model": model,
        "prompt": full_prompt,
        "stream": False
    }).encode()

    try:
        req = urllib.request.Request(
            OLLAMA_URL,
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            return data.get("response", "").strip()
    except urllib.error.URLError as e:
        return f"[Ollama Error: {e}]"


# ---- Fake LongMemEval samples (no HuggingFace required) ----
# Real structure mirrors the actual dataset format
SAMPLE_QUESTIONS = [
    {
        "id": "lme_001",
        "history": [
            {"role": "user", "content": "My dog's name is Biscuit and he's a golden retriever."},
            {"role": "assistant", "content": "That's a lovely name! Golden retrievers are wonderful dogs."},
            {"role": "user", "content": "Biscuit's birthday is March 15th. I want to plan a party for him."},
            {"role": "assistant", "content": "How fun! What kind of party are you thinking?"},
        ],
        "question": "What is the name of the user's dog and when is his birthday?",
        "answer": "The dog's name is Biscuit and his birthday is March 15th."
    },
    {
        "id": "lme_002",
        "history": [
            {"role": "user", "content": "I'm building a REST API in Go. The service name is 'beacon-api'."},
            {"role": "assistant", "content": "Great choice! What will beacon-api be responsible for?"},
            {"role": "user", "content": "It will handle authentication and user sessions. We're using PostgreSQL with schema name 'beacon_prod'."},
            {"role": "assistant", "content": "Good design. Will you be using any ORM?"},
            {"role": "user", "content": "No ORM, raw sqlx with connection pooling."},
        ],
        "question": "What database and schema are being used in beacon-api?",
        "answer": "PostgreSQL with schema name beacon_prod."
    },
    {
        "id": "lme_003",
        "history": [
            {"role": "user", "content": "My favorite coffee shop is called 'The Grind' on 5th Avenue."},
            {"role": "assistant", "content": "Sounds like a great spot!"},
            {"role": "user", "content": "I go there every Tuesday and Friday morning at 7:30am."},
            {"role": "assistant", "content": "That's a nice routine to have."},
            {"role": "user", "content": "They make the best oat milk cortado in the city."},
        ],
        "question": "What does the user order at their favorite coffee shop?",
        "answer": "An oat milk cortado."
    },
    {
        "id": "lme_004",
        "history": [
            {"role": "user", "content": "I've been learning Japanese for 2 years now."},
            {"role": "assistant", "content": "That's impressive! What level are you at?"},
            {"role": "user", "content": "I just passed JLPT N3. My goal is N2 by December."},
            {"role": "assistant", "content": "That's an ambitious but achievable goal with consistent study."},
        ],
        "question": "What Japanese proficiency level has the user achieved, and what is their goal?",
        "answer": "They passed JLPT N3 and their goal is N2 by December."
    },
    {
        "id": "lme_005",
        "history": [
            {"role": "user", "content": "Our startup is called Luminos. We're building a B2B SaaS for legal teams."},
            {"role": "assistant", "content": "Interesting space! What's the core problem you're solving?"},
            {"role": "user", "content": "Contract review automation. Our main competitor is LexCheck."},
            {"role": "assistant", "content": "The legal tech space is growing. Who are your target customers?"},
            {"role": "user", "content": "Mid-market companies with 50-500 employees, primarily in the US."},
        ],
        "question": "What is the startup name, what do they build, and who is their main competitor?",
        "answer": "The startup is Luminos, they build contract review automation for legal teams, and their main competitor is LexCheck."
    },
    {
        "id": "lme_006",
        "history": [
            {"role": "user", "content": "I moved to Tokyo in 2021 from Melbourne, Australia."},
            {"role": "assistant", "content": "That's a big move! How are you finding Tokyo?"},
            {"role": "user", "content": "I love it. I live in Shimokitazawa neighborhood. Very artsy area."},
            {"role": "assistant", "content": "Shimokitazawa is fantastic for the arts and music scene."},
        ],
        "question": "Where did the user move from, and what neighborhood do they live in now?",
        "answer": "They moved from Melbourne, Australia and now live in Shimokitazawa, Tokyo."
    },
    {
        "id": "lme_007",
        "history": [
            {"role": "user", "content": "I'm training for my first marathon. It's on October 12th in Chicago."},
            {"role": "assistant", "content": "Exciting! How's your training going?"},
            {"role": "user", "content": "My current long run PB is 28km at a 5:45/km pace."},
            {"role": "assistant", "content": "That's a solid base. You'll want to hit 32km in training before the race."},
            {"role": "user", "content": "My goal time is sub-4 hours."},
        ],
        "question": "What is the user's marathon goal time and when is the marathon?",
        "answer": "Their goal is sub-4 hours and the marathon is on October 12th in Chicago."
    }
]


# ---- Kanji extractor (simple heuristic) ----
DOMAIN_TO_KANJI = {
    "personal": {"個": 0.9, "記": 0.8, "標": 0.7},
    "technical": {"核": 1.0, "構": 0.8, "標": 0.6},
    "location": {"場": 1.0, "標": 0.8, "視": 0.6},
    "time": {"時": 1.0, "標": 0.8, "記": 0.5},
}

def infer_kanji(question: str) -> dict:
    q = question.lower()
    if any(w in q for w in ["when", "date", "birthday", "marathon", "time"]):
        return DOMAIN_TO_KANJI["time"]
    if any(w in q for w in ["where", "live", "location", "neighborhood", "city"]):
        return DOMAIN_TO_KANJI["location"]
    if any(w in q for w in ["database", "schema", "api", "code", "tech", "build"]):
        return DOMAIN_TO_KANJI["technical"]
    return DOMAIN_TO_KANJI["personal"]


# ---- Main smoke test runner ----
def main():
    print("=" * 60)
    print("Verantyx Cortex × LongMemEval Smoke Test")
    print(f"Model: {OLLAMA_MODEL} | Questions: {NUM_QUESTIONS}")
    print("=" * 60)

    mcp = MCPClient(MCP_SERVER_PATH)
    results = []

    for i, item in enumerate(SAMPLE_QUESTIONS[:NUM_QUESTIONS]):
        q_id = item["id"]
        history = item["history"]
        question = item["question"]
        expected = item["answer"]

        print(f"\n[{i+1}/{NUM_QUESTIONS}] ID: {q_id}")
        print(f"  Q: {question}")

        # Step 1: Inject conversation history into JCross
        raw_text = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in history])
        summary = f"Conversation about: {history[0]['content'][:80]}"
        ops = [f'OP.LOG("turn_{j}", "{m["content"][:60]}")' for j, m in enumerate(history)]

        print(f"  → Injecting {len(history)} turns into JCross memory...")
        ok = mcp.compile_memory(
            kanji_tags="[標: 1.0] [記: 0.8] [個: 0.6]",
            summary=summary,
            ops=ops,
            raw=raw_text
        )
        status = "✓" if ok else "✗ (MCP may be unavailable, using empty context)"

        # Step 2: Retrieve via spatial_cross_search
        kanji_query = infer_kanji(question)
        print(f"  → Gravity search with {kanji_query}...")
        context = mcp.spatial_search(kanji_query)
        context_preview = context[:200].replace("\n", " ") if context else "(empty)"
        print(f"  → Retrieved context: {context_preview}...")

        # Step 3: Ask gemma4:e2b
        print(f"  → Querying {OLLAMA_MODEL}...")
        answer = ask_ollama(question, context)

        print(f"  Expected : {expected}")
        print(f"  Got      : {answer}")

        # Simple exact-ish match check
        key_words = [w.lower() for w in expected.split() if len(w) > 3]
        match_count = sum(1 for w in key_words if w in answer.lower())
        score = match_count / max(len(key_words), 1)
        grade = "✅ PASS" if score >= 0.5 else "❌ FAIL"
        print(f"  Score    : {score:.0%} → {grade}")

        results.append({
            "id": q_id,
            "question": question,
            "expected": expected,
            "got": answer,
            "keyword_score": score,
            "mcp_inject_ok": ok
        })

    # Summary
    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    pass_count = sum(1 for r in results if r["keyword_score"] >= 0.5)
    avg_score = sum(r["keyword_score"] for r in results) / len(results)
    print(f"Pass: {pass_count}/{len(results)}")
    print(f"Avg keyword match score: {avg_score:.0%}")

    # Save results
    out_path = "/Users/motonishikoudai/verantyx-cli/_verantyx-cortex/benchmark/results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to: {out_path}")


if __name__ == "__main__":
    main()
