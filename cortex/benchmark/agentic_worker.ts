#!/usr/bin/env node
/**
 * Verantyx Agentic Benchmark Worker
 * Runs the full LongMemEval benchmark with Ollama tool use (agentic loop).
 * Spawned as a background process by the solve_all MCP tool.
 * Saves results to gemma4_agentic_results.json incrementally.
 *
 * Usage: node --import tsx agentic_worker.ts [count] [model] [max_turns]
 *   count     = questions to process this run (default: 5)
 *   Re-run to process the next batch. Results accumulate in gemma4_agentic_results.json.
 */
import fs from "fs";
import path from "path";
import http from "http";
import os from "os";

const HOME       = os.homedir();
const OUT_PATH   = path.join(HOME, "verantyx-cli", "_verantyx-cortex", "benchmark", "gemma4_agentic_results.json");
const DB_PATH    = path.join(HOME, "verantyx-cli", "benchmarks", "LongMemEval", "data", "longmemeval_s_cleaned.json");
const DEEP_DIR   = path.join(HOME, ".verantyx", "memory", "deep");
const LOG_PATH   = path.join(HOME, "verantyx-cli", "_verantyx-cortex", "benchmark", "agentic_worker.log");
const LOCK_PATH  = path.join(HOME, "verantyx-cli", "_verantyx-cortex", "benchmark", "agentic_worker.lock");

const count     = parseInt(process.argv[2] ?? "5");   // questions to process this run
const model     = process.argv[3] ?? "gemma4:26b";
const maxTurns  = parseInt(process.argv[4] ?? "8");
const TOP_K     = 15;  // same as Python benchmark

function log(msg: string) {
    const line = `[${new Date().toISOString()}] ${msg}`;
    console.error(line);
    fs.appendFileSync(LOG_PATH, line + "\n");
}

// ── JCross search ──────────────────────────────────────────────────────────────
const STOP = new Set(["what","how","when","where","who","did","does","is","was",
    "my","the","a","an","i","do","have","has","are","were","in","on","at",
    "to","for","of","and","or","it","its","there","that","long","often"]);

function kwSearch(nodes: Map<string, string>, query: string, topK: number = TOP_K): string {
    const words = query.toLowerCase().replace(/[?.,!]/g, "").split(/\s+/)
        .filter((w) => w.length > 2 && !STOP.has(w));
    const phrases = words.slice(0, -1).map((w, i) => w + " " + words[i + 1]);
    const scored: [number, string][] = [];
    for (const [, content] of nodes) {
        const opsM = content.match(/【操作対応表】([\s\S]*?)(?:【原文】|$)/);
        const rawM = content.match(/【原文】([\s\S]*)$/);
        const ops  = (opsM?.[1] ?? "").toLowerCase();
        const raw  = (rawM?.[1] ?? content).toLowerCase().slice(0, 3000);
        let s = phrases.reduce((x, p) => x + (ops.includes(p) ? 4 : 0) + (raw.includes(p) ? 2 : 0), 0);
        s    += words.reduce((x, w) => x + (ops.includes(w) ? 1 : 0) + (raw.includes(w) ? 1 : 0), 0);
        if (s > 0) scored.push([s, content]);
    }
    scored.sort((a, b) => b[0] - a[0]);
    return scored.slice(0, topK).map(([sc, content]) => {
        const rawM = content.match(/【原文】([\s\S]*)$/);
        return `[score=${sc}]\n${(rawM?.[1] ?? content).slice(0, 600)}`;
    }).join("\n\n---\n\n") || "No results found.";
}

// ── Ollama /api/chat ───────────────────────────────────────────────────────────
const AGENT_TOOLS = [
    { type: "function", function: {
        name: "search",
        description: "Search JCross memory for relevant conversation sessions. Try different keywords if first search fails.",
        parameters: { type: "object", properties: {
            query: { type: "string", description: "Search keywords (2-4 words)" },
            top_k: { type: "number", description: "Number of results (default: 5)" },
        }, required: ["query"] },
    }},
    { type: "function", function: {
        name: "read_node",
        description: "Read the full content of a specific .jcross node by filename.",
        parameters: { type: "object", properties: {
            filename: { type: "string", description: "The .jcross filename from search results" },
        }, required: ["filename"] },
    }},
];

function agentChat(messages: any[]): Promise<any> {
    return new Promise((resolve) => {
        const payload = JSON.stringify({
            model, messages, tools: AGENT_TOOLS, stream: false, think: false,
            options: { temperature: 0.0, num_predict: 300 },
        });
        const req = http.request(
            { hostname: "localhost", port: 11434, path: "/api/chat", method: "POST",
              headers: { "Content-Type": "application/json" },
            },
            (res) => {
                let body = "";
                res.on("data", (c) => body += c);
                res.on("end", () => { try { resolve(JSON.parse(body)); } catch { resolve({}); } });
            }
        );
        req.on("error", () => resolve({}));
        req.write(payload);
        req.end();
    });
}

// ── Scoring ────────────────────────────────────────────────────────────────────
const REFUSALS = ["not mentioned","did not mention","don't know","do not know",
    "not found","i don't know","i cannot","i can't","unable to find"];

function isImpossible(exp: string) { return REFUSALS.some(r => exp.toLowerCase().includes(r)); }

function tokenF1(pred: string, gold: string): number {
    const tok = (s: string) => s.toLowerCase().replace(/[^a-z0-9\s]/g, " ").split(/\s+/).filter(Boolean);
    const p = tok(pred), g = tok(gold);
    if (!p.length || !g.length) return 0;
    const common = new Set(p.filter(t => g.includes(t)));
    const prec = [...p].filter(t => common.has(t)).length / p.length;
    const rec  = [...g].filter(t => common.has(t)).length / g.length;
    return prec + rec > 0 ? 2 * prec * rec / (prec + rec) : 0;
}

// ── Main ───────────────────────────────────────────────────────────────────────
async function main() {
    // Write lock file
    fs.mkdirSync(path.dirname(LOCK_PATH), { recursive: true });
    fs.writeFileSync(LOCK_PATH, String(process.pid));

    log(`Worker started: count=${count} model=${model} max_turns=${maxTurns}`);

    if (!fs.existsSync(DB_PATH)) { log("Dataset not found: " + DB_PATH); process.exit(1); }
    if (!fs.existsSync(DEEP_DIR)) { log("deep/ not found. Run ingest_sessions.py first."); process.exit(1); }

    const db500 = JSON.parse(fs.readFileSync(DB_PATH, "utf-8")) as any[];

    // Load JCross nodes
    log("Loading JCross nodes...");
    const nodes = new Map<string, string>();
    for (const f of fs.readdirSync(DEEP_DIR).filter(f => f.endsWith(".jcross"))) {
        try { nodes.set(f, fs.readFileSync(path.join(DEEP_DIR, f), "utf-8")); } catch { /* skip */ }
    }
    log(`Loaded ${nodes.size} JCross nodes`);

    // Load existing results
    let results: any[] = fs.existsSync(OUT_PATH)
        ? (JSON.parse(fs.readFileSync(OUT_PATH, "utf-8")) as any[])
        : [];
    const done = new Map(results.map(r => [String(r.id), r]));
    log(`Resuming from ${done.size} already answered questions`);

    // Pick next N unanswered questions from entire dataset
    const allPending = db500.filter(q => !done.has(String(q.question_id ?? q.id)));
    const pending    = allPending.slice(0, count);
    log(`Already done: ${done.size}/500 | Processing: ${pending.length} questions this run`);
    if (pending.length === 0) { log("All 500 questions answered!"); process.exit(0); }


    for (const q of pending) {
            const qid      = String(q.question_id ?? q.id);
            const question = q.question;
            const expected = String(q.answer);
            const qtype    = q.question_type ?? "unknown";

            // Fresh agent context per question
            const messages: any[] = [
                { role: "system", content:
                    "You are a memory retrieval assistant. You MUST use the search tool BEFORE answering.\n" +
                    "RULES:\n" +
                    "1. ALWAYS call search() first — never answer directly from memory.\n" +
                    "2. If the first search finds nothing useful, try a different keyword with search() again.\n" +
                    "3. You may call read_node() to read a specific file in detail.\n" +
                    "4. After searching, reply with ONLY the exact answer (no explanation, no full sentence).\n" +
                    "5. If the answer is genuinely not in the retrieved context after 2+ searches, reply: I don't know\n" +
                    "\nIMPORTANT: Do NOT skip the search step. Always search first." },
                { role: "user", content: question },
            ];

            let finalAnswer = "I don't know";
            let toolCalls   = 0;

            for (let turn = 0; turn < maxTurns; turn++) {
                const resp = await agentChat(messages);
                const msg  = resp?.message;
                if (!msg) break;
                messages.push(msg);

                if (msg.tool_calls?.length > 0) {
                    for (const tc of msg.tool_calls) {
                        const fn   = tc.function?.name;
                        const fa   = tc.function?.arguments ?? {};
                        toolCalls++;
                        let result = "";
                        if (fn === "search") {
                            result = kwSearch(nodes, String(fa.query ?? ""), Number(fa.top_k ?? TOP_K));
                        } else if (fn === "read_node") {
                            result = nodes.get(String(fa.filename ?? ""))?.slice(0, 1200) ?? "Not found";
                        } else {
                            result = "Unknown tool";
                        }
                        messages.push({ role: "tool", content: result });
                    }
                } else if (msg.content) {
                    finalAnswer = String(msg.content).split("\n")[0].trim().replace(/^"|"$/g, "");
                    break;
                } else {
                    break;
                }
            }

            // Score
            const refused  = !finalAnswer || REFUSALS.some(r => finalAnswer.toLowerCase().includes(r));
            const imp      = isImpossible(expected);
            const correct  = imp ? refused : (!refused && tokenF1(finalAnswer, expected) >= 0.5);
            const f1       = imp ? (correct ? 1 : 0) : (refused ? 0 : tokenF1(finalAnswer, expected));

            done.set(qid, {
                id: qid, question_type: qtype,
                answer_agent: finalAnswer, expected,
                f1: Math.round(f1 * 1000) / 1000,
                correct, tool_calls: toolCalls,
            });

            const mark = correct ? "✅" : (refused ? "⏭" : "❌");
            log(`${mark} [${qtype.slice(0,16)}] "${question.slice(0,40)}" → "${finalAnswer.slice(0,20)}" (f1=${f1.toFixed(2)}, tools=${toolCalls})`);
        results = Array.from(done.values());
        fs.mkdirSync(path.dirname(OUT_PATH), { recursive: true });
        fs.writeFileSync(OUT_PATH, JSON.stringify(results, null, 2));
        const correct = results.filter(r => r.correct).length;
        log(`  → saved (done.size=${done.size})`);
    }

    // Final save
    results = Array.from(done.values());
    // Clean up lock
    try { fs.unlinkSync(LOCK_PATH); } catch { /* ok */ }
    log(`Worker complete: ${done.size} questions answered`);
    process.exit(0);
}

main().catch(e => { log("Worker error: " + e.message); process.exit(1); });
