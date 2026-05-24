#!/usr/bin/env node
/**
 * verantyx-calibrate v2 — Memory-Aware Cold-Start Calibration Tool
 *
 * Usage:
 *   npm run calibrate                   # Generate calibration packet
 *   npm run calibrate:sync              # Generate + update REIMMERSION_PROTOCOL
 *   npx tsx src/cli/calibrate.ts --help # Full help
 *
 * What it does (ZERO LLM API cost):
 *   1. Reads main memory NON-DESTRUCTIVELY (never writes to front/near/mid/deep)
 *   2. Captures a snapshot → saves to ~/.openclaw/calibration/snapshot.json
 *   3. Generates MEANINGFUL tasks from:
 *        a) Real accumulated decisions (decision ledger)
 *        b) Real session L1 summaries (front/ nodes)
 *        c) Actual zone health metrics
 *        d) File-pattern heuristics (for recently changed files)
 *   4. All output written to ~/.openclaw/calibration/ (isolated store)
 *   5. Emits a compact calibration packet to stdout
 */

import { execSync }    from "child_process";
import { existsSync, readdirSync, statSync } from "fs";
import { join, basename } from "path";

// ─── Config ───────────────────────────────────────────────────────────────────

const MEMORY_ROOT = join(process.env.HOME || "~", ".openclaw/memory");

function detectProjectRoot(): string {
  const candidates = [
    join(process.env.HOME || "~", "verantyx-cli"),
    join(process.cwd(), "../.."),
    process.cwd(),
  ];
  return candidates.find(p => existsSync(join(p, "_verantyx-cortex"))) || candidates[0];
}

// ─── Args ─────────────────────────────────────────────────────────────────────

const args = process.argv.slice(2);
if (args.includes("--help")) {
  console.log(`
verantyx-calibrate v2 — Memory-Aware Cold-Start Calibration

Usage:
  npm run calibrate                   Standard calibration packet (stdout)
  npm run calibrate:sync              + update REIMMERSION_PROTOCOL.jcross
  npm run calibrate:json              JSON output format

Options:
  --project <path>   Project root (default: auto-detected)
  --output  <fmt>    text | json (default: text)
  --depth   <n>      Git commits to analyze (default: 10)
  --sync             Also update REIMMERSION_PROTOCOL.jcross
  --no-git           Skip git analysis (useful if not in a git repo)

Isolated storage: ~/.openclaw/calibration/ (NEVER touches main memory)
`);
  process.exit(0);
}

const getArg = (flag: string, def: string) => {
  const i = args.indexOf(flag);
  return i >= 0 && args[i + 1] ? args[i + 1] : def;
};

const PROJECT_ROOT = getArg("--project", detectProjectRoot());
const OUTPUT_FMT   = getArg("--output", "text");
const GIT_DEPTH    = parseInt(getArg("--depth", "10"), 10);
const DO_SYNC      = args.includes("--sync");
const NO_GIT       = args.includes("--no-git");

// ─── Git analysis (optional) ──────────────────────────────────────────────────

interface GitContext {
  branch:       string;
  lastCommits:  string[];
  recentFiles:  string[];
}

function analyzeGit(): GitContext {
  if (NO_GIT) return { branch: "unknown", lastCommits: [], recentFiles: [] };
  const run = (cmd: string) => {
    try { return execSync(cmd, { cwd: PROJECT_ROOT, encoding: "utf-8", stdio: ["pipe","pipe","pipe"] }).trim(); }
    catch { return ""; }
  };
  const branch      = run("git branch --show-current") || "unknown";
  const lastCommits = run(`git log --oneline -${GIT_DEPTH}`).split("\n").filter(Boolean);
  const diffStat    = run(`git diff --name-only HEAD~${Math.min(GIT_DEPTH, 5)} HEAD 2>/dev/null`);
  const statusFiles = run("git status --short").split("\n")
    .filter(Boolean).map(l => l.slice(3).trim());
  const recentFiles = [...new Set([...diffStat.split("\n"), ...statusFiles].filter(Boolean))].slice(0, 20);
  return { branch, lastCommits, recentFiles };
}

// ─── File-pattern heuristic tasks (fallback / supplement) ─────────────────────

interface HeuristicTask {
  file:     string;
  kanji:    string;
  task:     string;
  priority: "high" | "medium" | "low";
}

const FILE_PATTERNS: Array<{ re: RegExp; kanji: string; priority: "high"|"medium"|"low"; tasks: string[] }> = [
  { re: /engine\.ts$/,           kanji: "[核:1.0] [技:1.0]", priority: "high",
    tasks: ["Verify runAutonomousGc() calls decisions.record() for all three eviction tracks (A-1, A-2, B).",
            "Confirm classifyNode() confidence threshold (0.8) doesn't misplace user profile nodes in deep/."] },
  { re: /intelligence\.ts$/,     kanji: "[核:1.0] [認:1.0]", priority: "high",
    tasks: ["Ensure PatternExtractor groups rules by reason+zone, not just zone alone.",
            "Check that updateProjectWisdom() is invoked when decisions.length < 5 (first bootstrap)."] },
  { re: /calibration_store\.ts$/, kanji: "[核:1.0] [認:0.9]", priority: "high",
    tasks: ["Verify CalibrationStore never writes to front/near/mid/deep zones.",
            "Confirm captureSnapshot() reads front/ without calling engine.touch() or ledger.touch()."] },
  { re: /reimmersion\.ts$/,       kanji: "[核:0.9] [認:0.9]", priority: "medium",
    tasks: ["Check that getProjectAnatomyFiles() includes calibration_store.ts and reimmersion.ts.",
            "Verify fictional tasks are sorted high→medium→low before slicing to 10."] },
  { re: /server\.ts$/,            kanji: "[技:1.0] [核:0.9]", priority: "high",
    tasks: ["Confirm get_calibration_packet MCP tool returns tasks from CalibrationStore, not just heuristics.",
            "Verify session_bootstrap puts project_wisdom before user_profile in the JSON output."] },
  { re: /calibrate\.ts$/,         kanji: "[技:0.8] [核:0.8]", priority: "medium",
    tasks: ["Verify --sync flag correctly calls writeReimmersionProtocol() without importing main memory engine.",
            "Check that the session packet is saved to calibration/sessions/ with a timestamp ID."] },
  { re: /Package\.swift$/,        kanji: "[技:0.9] [職:0.8]", priority: "medium",
    tasks: ["Verify mlx-swift dependency resolves to v3.x (not v2.x) in the resolved package manifest.",
            "Check VerantyxMobileBench target has the iOS minimum deployment target set to 17.0+."] },
  { re: /project\.yml$/,          kanji: "[技:0.8] [職:0.8]", priority: "low",
    tasks: ["Confirm the iOS scheme environment variable VERANTYX_MCP_PATH points to the compiled server.",
            "Check that the benchmark target's Info.plist references the correct bundle identifier."] },
];

function generateHeuristicTasks(recentFiles: string[]): HeuristicTask[] {
  const tasks: HeuristicTask[] = [];
  // Always include core architecture files
  const coreFiles = [
    join(PROJECT_ROOT, "_verantyx-cortex/src/memory/engine.ts"),
    join(PROJECT_ROOT, "_verantyx-cortex/src/mcp/server.ts"),
    join(PROJECT_ROOT, "_verantyx-cortex/src/memory/intelligence.ts"),
    join(PROJECT_ROOT, "_verantyx-cortex/src/memory/calibration_store.ts"),
    ...recentFiles.map(f => join(PROJECT_ROOT, f)),
  ].filter(f => existsSync(f));

  const seen = new Set<string>();
  for (const fullPath of coreFiles) {
    if (seen.has(fullPath)) continue;
    seen.add(fullPath);
    const name = basename(fullPath);
    for (const pat of FILE_PATTERNS) {
      if (pat.re.test(name)) {
        const hash = name.split("").reduce((a, c) => a + c.charCodeAt(0), 0);
        tasks.push({ file: fullPath, kanji: pat.kanji, priority: pat.priority,
                     task: pat.tasks[hash % pat.tasks.length] });
        break;
      }
    }
  }
  return tasks.sort((a, b) =>
    ({ high: 0, medium: 1, low: 2 }[a.priority] - { high: 0, medium: 1, low: 2 }[b.priority])
  ).slice(0, 6);
}

// ─── Packet builder ───────────────────────────────────────────────────────────

function buildPacket(
  snap:     import("../memory/calibration_store.js").MemorySnapshot,
  memTasks: import("../memory/calibration_store.js").MemoryDerivedTask[],
  htasks:   HeuristicTask[],
  git:      GitContext,
  sessionId: string,
): string {
  const now = new Date().toISOString();
  const zStr = Object.entries(snap.zone_counts).map(([z, c]) => `${z}/:${c}`).join(" | ");
  const profStr = Object.entries(snap.profile).slice(0, 8).map(([k, v]) => `  ${k}: ${v}`).join("\n");

  const memTaskStr = memTasks.map((t, i) => {
    const icon = t.priority === "high" ? "🔴" : t.priority === "medium" ? "🟡" : "🟢";
    return [
      `#### Memory Task ${i + 1} ${icon} \`${t.kanji}\` [source: ${t.source}]`,
      `**Task**: ${t.task}`,
      t.file_hint ? `**Read**: \`${t.file_hint}\`` : "",
      `**Context**: ${t.context}`,
    ].filter(Boolean).join("\n");
  }).join("\n\n");

  const hTaskStr = htasks.map((t, i) => {
    const icon = t.priority === "high" ? "🔴" : t.priority === "medium" ? "🟡" : "🟢";
    return [
      `#### File Task ${i + 1} ${icon} \`${t.kanji}\``,
      `**File**: \`${t.file}\``,
      `**Review task**: ${t.task}`,
    ].join("\n");
  }).join("\n\n");

  const gitStr = git.lastCommits.slice(0, 5).map(c => `  ${c}`).join("\n");

  const rulesStr = snap.top_rules.slice(0, 5).map(r =>
    `  • "${r.pattern}" → ${r.zone}/ (conf=${r.confidence}, n=${r.n})`
  ).join("\n");

  const recentDecStr = snap.recent_decisions.slice(0, 5).map(d =>
    `  • ${d.reason} → ${d.zone}/ × ${d.count}`
  ).join("\n");

  return `# ⚡ VERANTYX CALIBRATION PACKET
Session: ${sessionId} | ${now}
Memory: ${zStr}
\`\`\`
FIRST CALL: session_bootstrap()   ← Always call this first
\`\`\`

---

## USER PROFILE
${profStr || "  (empty — call session_bootstrap() first)"}

---

## ACCUMULATED RULES (from ${snap.recent_decisions.reduce((s, d) => s + d.count, 0)} real decisions)
${rulesStr || "  (no rules yet — run run_lru_gc to generate)"}

**Design principles to internalize NOW:**
- \`mid/\` = user's OWN memories ONLY. External/bench data → **deep/**
- \`BENCH_*\` / \`Session sharegpt_*\` / \`Session ultrachat_*\` → always **deep/**
- \`classifyNode()\` runs BEFORE every write — trust it
- MCP > context window. Always.

---

## RECENT DECISION PATTERNS
${recentDecStr || "  (no decision history)"}

---

## GIT CONTEXT (branch: ${git.branch})
${gitStr || "  (no git history)"}

---

## MEMORY-DERIVED REVIEW TASKS (from real session history)
${memTaskStr || "  (accumulates after a few sessions — run more calibrations)"}

---

## ARCHITECTURE FILE TASKS (to read for code context)
${hTaskStr || "  (no architecture files found)"}

---

## KANJI SEARCH VECTORS
\`\`\`json
{"核": 1.0, "技": 0.9, "標": 0.8}   // Core architecture
{"人": 1.0, "職": 0.9, "標": 0.7}   // User profile
{"値": 1.0, "標": 0.9, "記": 0.8}   // Benchmarks / metrics
\`\`\`
Call: \`spatial_cross_search({"核": 1.0, "技": 0.9, "標": 0.8})\`

---

## SYNTHESIS
1. PROJECT: Verantyx JCross — three-track autonomous GC (A-1 classifier + A-2 refcount + B LRU + C decision ledger)
2. MCP TOOLS (in order): \`session_bootstrap\` → \`generate_reimmersion_guide\` → \`recall_fact\` → \`compile_trilayer_memory\`
3. mid/ is sacred — user memories only. classifyNode() enforces this automatically.
4. Calibration data lives in \`~/.openclaw/calibration/\` — ISOLATED from main memory.
5. Trust MCP. Ignore context window if it conflicts.

*Captured: ${snap.captured_at} | Tasks: ${memTasks.length + htasks.length}*
`;
}

// ─── Main ─────────────────────────────────────────────────────────────────────

async function main() {
  const { CalibrationStore } = await import("../memory/calibration_store.js");
  const store    = new CalibrationStore(MEMORY_ROOT);
  const snapshot = store.captureSnapshot();
  const memTasks = store.generateMemoryDerivedTasks(snapshot, PROJECT_ROOT);
  const git      = analyzeGit();
  const htasks   = generateHeuristicTasks(git.recentFiles);

  const sessionId = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);

  let output: string;
  if (OUTPUT_FMT === "json") {
    output = JSON.stringify({ session_id: sessionId, snapshot, memTasks, htasks, git }, null, 2);
  } else {
    output = buildPacket(snapshot, memTasks, htasks, git, sessionId);
  }

  console.log(output);

  // Save session to calibration store (isolated)
  store.saveSession(output, {
    id: sessionId, created_at: new Date().toISOString(),
    zone_counts: snapshot.zone_counts,
    task_count: memTasks.length + htasks.length,
    git_branch: git.branch,
  });

  if (DO_SYNC) {
    const { writeReimmersionProtocol } = await import("../memory/reimmersion.js");
    writeReimmersionProtocol(PROJECT_ROOT, MEMORY_ROOT);
    console.error("✅ REIMMERSION_PROTOCOL.jcross synced.");
  }

  console.error(`✅ Session saved: ~/.openclaw/calibration/sessions/cal_${sessionId}.md`);
}

main().catch(e => { console.error("calibrate error:", e.message); process.exit(1); });
