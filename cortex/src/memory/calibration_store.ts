/**
 * CalibrationStore — Isolated calibration memory
 *
 * Reads FROM main memory (non-destructively) but writes ONLY to
 * ~/.openclaw/calibration/. Never touches front/near/mid/deep.
 *
 * Task generation strategies (all zero LLM cost):
 *   A) Memory-derived       — from real decisions, L1 summaries, zone health
 *   B) Git Diff reverse     — from past fix/bug commits, file paths auto-extracted
 *   C) L1.5 random sampling — from JCross node pairs, dependency-exploration tasks
 */

import {
  existsSync, readFileSync, writeFileSync,
  mkdirSync, readdirSync, appendFileSync,
} from "fs";
import { join, basename } from "path";
import { execSync } from "child_process";

export function getCalibrationRoot(memoryRoot: string): string {
  return join(memoryRoot, "..", "calibration");
}

export interface MemoryDerivedTask {
  id:          string;
  generated_at: string;
  source:      "memory_node" | "decision_ledger" | "pattern_rule" | "heuristic" | "git_diff" | "l15_sampling";
  sourceFile?: string;
  kanji:       string;
  task:        string;
  context:     string;
  file_hint?:  string;
  priority:    "high" | "medium" | "low";
}

export interface CalibrationSession {
  id:          string;
  created_at:  string;
  zone_counts: Record<string, number>;
  task_count:  number;
  git_branch?: string;
}

export interface MemorySnapshot {
  captured_at:  string;
  zone_counts:  Record<string, number>;
  front_nodes:  { file: string; kanji: string; l1: string }[];
  profile:      Record<string, string>;
  top_rules:    { pattern: string; zone: string; confidence: number; n: number }[];
  recent_decisions: { reason: string; zone: string; count: number }[];
}

// ─── Strategy B: Git Diff Reverse Engineering ─────────────────────────────────

interface GitCommit {
  hash:        string;
  subject:     string;
  files:       string[];
  isFixCommit: boolean;
}

export class GitDiffTaskGenerator {
  private projectRoot: string;

  constructor(projectRoot: string) {
    this.projectRoot = projectRoot;
  }

  private run(cmd: string): string {
    try {
      return execSync(cmd, {
        cwd: this.projectRoot, encoding: "utf-8", stdio: ["pipe", "pipe", "pipe"],
      }).trim();
    } catch { return ""; }
  }

  parseRecentFixCommits(depth = 20): GitCommit[] {
    const log = this.run(`git log --format="%H|||%s" --name-only -${depth} 2>/dev/null`);
    if (!log) return [];

    const commits: GitCommit[] = [];
    let current: GitCommit | null = null;

    for (const line of log.split("\n")) {
      if (line.includes("|||")) {
        if (current) commits.push(current);
        const [hash, ...rest] = line.split("|||");
        const subject = rest.join("|||").trim();
        const isFixCommit =
          /^(fix|bug|hotfix|patch|revert|repair|correct)[\s(:]/i.test(subject) ||
          /\b(fix|fixed|fixes|resolve|resolved|bug|regression|broken|crash)\b/i.test(subject);
        current = { hash: hash.trim(), subject, files: [], isFixCommit };
      } else if (line.trim() && current) {
        const f = line.trim();
        if (/\.(ts|swift|json|md|yml)$/.test(f)) current.files.push(f);
      }
    }
    if (current) commits.push(current);

    return commits.filter(c => c.isFixCommit && c.files.length > 0).slice(0, 6);
  }

  generateTasks(): MemoryDerivedTask[] {
    const fixCommits = this.parseRecentFixCommits();
    const tasks: MemoryDerivedTask[] = [];
    const now = new Date().toISOString();
    let id = Date.now() + 10000;

    for (const commit of fixCommits) {
      const primary = commit.files.find(f =>
        f.includes("engine") || f.includes("server") || f.includes("selector")
      ) || commit.files[0];
      const fullPath = join(this.projectRoot, primary);

      tasks.push({
        id:           `task_${id++}`,
        generated_at: now,
        source:       "git_diff",
        sourceFile:   `git:${commit.hash.slice(0, 8)}`,
        kanji:        "[核:0.9] [技:0.9] [標:0.8]",
        task: `Commit ${commit.hash.slice(0, 8)} "${commit.subject}" modified ${commit.files.length} file(s). ` +
              `Verify the fix in ${basename(primary)} is still correctly applied ` +
              `and hasn't been accidentally reverted by subsequent changes.`,
        context: `Real git history: this was an actual fix commit. ` +
                 `Changed: ${commit.files.slice(0, 3).join(", ")}`,
        file_hint: existsSync(fullPath) ? fullPath : undefined,
        priority: "medium",
      });
    }

    return tasks;
  }
}

// ─── Strategy C: L1.5 Index Random Sampling ──────────────────────────────────

interface L15Node {
  zone:  string;
  file:  string;
  kanji: string;
  l1:    string;
}

export class L15SamplingTaskGenerator {
  private memRoot: string;

  constructor(memRoot: string) {
    this.memRoot = memRoot;
  }

  sampleNodes(count = 3): L15Node[] {
    const allNodes: L15Node[] = [];

    for (const zone of ["front", "near", "mid"]) {
      const dir = join(this.memRoot, zone);
      if (!existsSync(dir)) continue;

      const files = readdirSync(dir).filter(f =>
        f.endsWith(".jcross") &&
        !f.startsWith("JCROSS_TOMB_") &&
        !f.includes("PROJECT_WISDOM") &&
        !f.includes("REIMMERSION") &&
        !f.includes("CALIBRATION")
      );

      for (const f of files) {
        try {
          const raw    = readFileSync(join(dir, f), "utf-8");
          const kanjiM = raw.match(/【空間座相】\s*\n([^\n【]+)/);
          const l1M    = raw.match(/\[標\] := "([^"]{10,200})"/);
          if (kanjiM && l1M) {
            allNodes.push({ zone, file: f, kanji: kanjiM[1].trim().slice(0, 60), l1: l1M[1].slice(0, 150) });
          }
        } catch { /* skip */ }
      }
    }

    if (allNodes.length === 0) return [];

    // Daily-rotating deterministic sample
    const seed = Math.floor(Date.now() / (1000 * 60 * 60 * 24));
    const sampled: L15Node[] = [];
    const seen = new Set<number>();
    let i = 0;
    while (sampled.length < Math.min(count, allNodes.length) && i < 200) {
      const idx = Math.abs((seed * (i + 1) * 2654435761) % allNodes.length);
      if (!seen.has(idx)) { seen.add(idx); sampled.push(allNodes[idx]); }
      i++;
    }
    return sampled;
  }

  generateTasks(): MemoryDerivedTask[] {
    const nodes = this.sampleNodes(3);
    if (nodes.length < 2) return [];

    const tasks: MemoryDerivedTask[] = [];
    const now = new Date().toISOString();
    let id = Date.now() + 20000;

    const [a, b] = nodes;
    tasks.push({
      id:           `task_${id++}`,
      generated_at: now,
      source:       "l15_sampling",
      sourceFile:   `${a.zone}/${a.file}`,
      kanji:        "[認:1.0] [核:0.9] [標:0.8]",
      task: `Investigate the structural dependency between:\n` +
            `  Node A [${a.zone}/${a.file}] ${a.kanji}\n    "${a.l1.slice(0, 80)}"\n` +
            `  Node B [${b.zone}/${b.file}] ${b.kanji}\n    "${b.l1.slice(0, 80)}"\n` +
            `Use spatial_cross_search to find connecting nodes. ` +
            `Do these represent functionally related aspects of the same system?`,
      context: `Daily-rotated L1.5 sample. Cross-node exploration surfaces forgotten context from deeper zones.`,
      priority: "low",
    });

    if (nodes.length >= 3) {
      const c = nodes[2];
      tasks.push({
        id:           `task_${id++}`,
        generated_at: now,
        source:       "l15_sampling",
        sourceFile:   `${c.zone}/${c.file}`,
        kanji:        "[認:1.0] [技:0.8] [標:0.7]",
        task: `Node [${c.zone}/${c.file}] "${c.l1.slice(0, 60)}..." has kanji ${c.kanji}. ` +
              `Determine if it's correctly placed in ${c.zone}/ given its content, ` +
              `or if classifyNode() would now send it elsewhere.`,
        context: `L1.5 sampling may surface misclassified nodes. This feeds back into Track C DecisionLedger.`,
        priority: "low",
      });
    }

    return tasks;
  }
}

// ─── CalibrationStore ─────────────────────────────────────────────────────────

export class CalibrationStore {
  private calRoot:     string;
  private sessionsDir: string;
  private bankPath:    string;
  private snapPath:    string;
  private indexPath:   string;
  private memRoot:     string;

  constructor(memoryRoot: string) {
    this.memRoot     = memoryRoot;
    this.calRoot     = getCalibrationRoot(memoryRoot);
    this.sessionsDir = join(this.calRoot, "sessions");
    this.bankPath    = join(this.calRoot, "task_bank.jsonl");
    this.snapPath    = join(this.calRoot, "snapshot.json");
    this.indexPath   = join(this.calRoot, "index.jcross");
    this.ensureDirs();
  }

  private ensureDirs(): void {
    for (const dir of [this.calRoot, this.sessionsDir]) {
      if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
    }
  }

  captureSnapshot(): MemorySnapshot {
    const snapshot: MemorySnapshot = {
      captured_at: new Date().toISOString(),
      zone_counts: {}, front_nodes: [], profile: {}, top_rules: [], recent_decisions: [],
    };

    for (const zone of ["front", "near", "mid", "deep"]) {
      const dir = join(this.memRoot, zone);
      snapshot.zone_counts[zone] = existsSync(dir)
        ? readdirSync(dir).filter(f => f.endsWith(".jcross")).length : 0;
    }

    const frontDir = join(this.memRoot, "front");
    if (existsSync(frontDir)) {
      for (const f of readdirSync(frontDir).filter(f => f.endsWith(".jcross"))) {
        try {
          const raw    = readFileSync(join(frontDir, f), "utf-8");
          const kanjiM = raw.match(/【空間座相】\s*\n([^\n【]+)/);
          const l1M    = raw.match(/\[標\] := "([^"]{1,200})"/);
          if (l1M) snapshot.front_nodes.push({ file: f, kanji: kanjiM?.[1]?.trim() ?? "", l1: l1M[1] });
          for (const m of raw.matchAll(/OP\.(?:ENTITY|FACT|STATE)\("([^"]+)",\s*"([^"]+)"\)/g))
            snapshot.profile[m[1]] = m[2];
        } catch { /* skip */ }
      }
    }

    const decisionsPath = join(this.memRoot, "meta", "decisions.jsonl");
    if (existsSync(decisionsPath)) {
      try {
        type Decision = { reason: string; toZone: string };
        const grouped: Record<string, { zone: string; count: number }> = {};
        for (const line of readFileSync(decisionsPath, "utf-8").trim().split("\n").filter(Boolean)) {
          try {
            const d = JSON.parse(line) as Decision;
            const k = `${d.reason}→${d.toZone}`;
            if (!grouped[k]) grouped[k] = { zone: d.toZone, count: 0 };
            grouped[k].count++;
          } catch { /* skip */ }
        }
        snapshot.recent_decisions = Object.entries(grouped)
          .sort((a, b) => b[1].count - a[1].count)
          .slice(0, 10)
          .map(([rz, v]) => ({ reason: rz.split("→")[0], zone: v.zone, count: v.count }));

        const wisdomPath = join(this.memRoot, "front", "PROJECT_WISDOM.jcross");
        if (existsSync(wisdomPath)) {
          const wisdom = readFileSync(wisdomPath, "utf-8");
          const rs = wisdom.match(/【ACCUMULATED_RULES】([\s\S]*?)【/);
          if (rs) {
            for (const line of rs[1].trim().split("\n").filter(l => /^rule_/.test(l)).slice(0, 8)) {
              const m = line.match(/rule_\d+: (.+?) → (\w+)\/ \(confidence=([\d.]+), n=(\d+)\)/);
              if (m) snapshot.top_rules.push({ pattern: m[1], zone: m[2], confidence: +m[3], n: +m[4] });
            }
          }
        }
      } catch { /* skip */ }
    }

    writeFileSync(this.snapPath, JSON.stringify(snapshot, null, 2), "utf-8");
    return snapshot;
  }

  generateMemoryDerivedTasks(snapshot: MemorySnapshot, projectRoot: string): MemoryDerivedTask[] {
    const tasks: MemoryDerivedTask[] = [];
    const now = new Date().toISOString();
    let id = Date.now();
    const CORTEX = join(projectRoot, "_verantyx-cortex/src");

    // Strategy A-1: Decision ledger
    for (const dec of snapshot.recent_decisions.slice(0, 3)) {
      if (dec.count >= 5) tasks.push({
        id: `task_${id++}`, generated_at: now, source: "decision_ledger",
        kanji: "[核:1.0] [記:0.9] [標:0.8]",
        task: `Verify ${dec.count} nodes classified as "${dec.reason}" landed in ${dec.zone}/ with correct tombstones.`,
        context: `${dec.count} real GC moves → ${dec.zone}/. Architectural pattern from decision ledger.`,
        file_hint: join(CORTEX, "memory/engine.ts"),
        priority: dec.count > 100 ? "high" : "medium",
      });
    }

    // Strategy A-2: Top rules
    for (const r of snapshot.top_rules.filter(r => r.confidence >= 0.9 && r.n >= 10).slice(0, 2)) {
      tasks.push({
        id: `task_${id++}`, generated_at: now, source: "pattern_rule",
        kanji: "[核:0.9] [技:0.8] [認:0.8]",
        task: `Rule "${r.pattern} → ${r.zone}/" (conf=${r.confidence}, n=${r.n}). Verify classifyNode() implements this.`,
        context: `Top rule from PROJECT_WISDOM. ${r.n} real decisions back this up.`,
        file_hint: join(CORTEX, "memory/engine.ts"),
        priority: "high",
      });
    }

    // Strategy A-3: front/ L1 nodes
    for (const node of snapshot.front_nodes
      .filter(n => !n.file.includes("WISDOM") && !n.file.includes("REIMMERSION"))
      .slice(0, 2)) {
      tasks.push({
        id: `task_${id++}`, generated_at: now, source: "memory_node", sourceFile: node.file,
        kanji: node.kanji || "[記:0.9] [標:0.8]",
        task: `[${node.file}]: "${node.l1.slice(0, 120)}" — verify this is consistent with current code.`,
        context: `Real memory node from front/. Connects memory context with actual code state.`,
        priority: "medium",
      });
    }

    // Strategy A-4: Zone health
    const z = snapshot.zone_counts;
    if (z.near > 800) tasks.push({
      id: `task_${id++}`, generated_at: now, source: "heuristic", kanji: "[核:1.0] [値:0.9]",
      task: `near/ at ${z.near}/1000. Verify RefCountLedger identifies cold nodes before cap breach.`,
      context: `Actual zone count. Real operational risk.`,
      file_hint: join(CORTEX, "memory/engine.ts"), priority: "high",
    });
    if (z.deep > 1000) tasks.push({
      id: `task_${id++}`, generated_at: now, source: "heuristic", kanji: "[記:0.8] [値:0.8]",
      task: `deep/ has ${z.deep} nodes. Verify tombstone EVICTED_TO fields are intact.`,
      context: `Large deep/ = significant cascade. Tombstone integrity matters.`,
      file_hint: join(CORTEX, "memory/engine.ts"), priority: "low",
    });

    // Strategy B: Git Diff
    try { tasks.push(...new GitDiffTaskGenerator(projectRoot).generateTasks()); } catch { /* skip */ }

    // Strategy C: L1.5 Sampling
    try { tasks.push(...new L15SamplingTaskGenerator(this.memRoot).generateTasks()); } catch { /* skip */ }

    // Benchmark task
    const score = snapshot.profile["bench_current_score"];
    if (score) tasks.push({
      id: `task_${id++}`, generated_at: now, source: "memory_node", kanji: "[値:1.0] [標:0.9]",
      task: `Benchmark at ${score}. Verify session_bootstrap surfaces project_wisdom as first field.`,
      context: `Real metric from user_profile. Goal: 85%+.`,
      file_hint: join(CORTEX, "mcp/server.ts"), priority: "high",
    });

    for (const task of tasks) {
      try { appendFileSync(this.bankPath, JSON.stringify(task) + "\n", "utf-8"); } catch { /* non-fatal */ }
    }
    return tasks;
  }

  readTaskBank(limit = 20): MemoryDerivedTask[] {
    if (!existsSync(this.bankPath)) return [];
    try {
      return readFileSync(this.bankPath, "utf-8").trim().split("\n")
        .filter(Boolean).slice(-limit).map(l => JSON.parse(l) as MemoryDerivedTask);
    } catch { return []; }
  }

  saveSession(packet: string, meta: CalibrationSession): void {
    writeFileSync(join(this.sessionsDir, `cal_${meta.id}.md`), packet, "utf-8");
    const idxLine = `[${meta.created_at}] ${meta.id} zone=${JSON.stringify(meta.zone_counts)} tasks=${meta.task_count}\n`;
    const idxContent =
      `■ JCROSS_CALIBRATION_INDEX\n【空間座相】\n[核:0.8] [記:0.8] [標:0.7]\n\n` +
      `【位相対応表】\n[標] := "Calibration session history — isolated from main memory"\n\n` +
      `【SESSIONS】\n` +
      (existsSync(this.indexPath) ? readFileSync(this.indexPath, "utf-8").split("【SESSIONS】\n")[1] || "" : "") +
      idxLine;
    writeFileSync(this.indexPath, idxContent, "utf-8");
  }

  getLastSnapshot(): MemorySnapshot | null {
    if (!existsSync(this.snapPath)) return null;
    try { return JSON.parse(readFileSync(this.snapPath, "utf-8")) as MemorySnapshot; } catch { return null; }
  }
}
