/**
 * Track C Extension: Cognitive Cold-Start Eliminator
 *
 * generateReimmersionGuide() produces a structured "re-immersion protocol"
 * that a blank-slate LLM can follow at the start of any session to rebuild
 * full project context using ONLY tool calls (no human prompting needed).
 *
 * The trick: "fictional review tasks" point to real architecture files,
 * forcing the model to read them. Reading the files + memory nodes gives
 * the model project-expert-level context in 5-7 tool calls.
 *
 * Each task is annotated with:
 *   - Kanji topology tags (which memory zone to cross-reference)
 *   - Estimated context cost (token estimate)
 *   - What the model should learn from reading the file
 */

import { existsSync, readFileSync, writeFileSync, mkdirSync } from "fs";
import { join } from "path";
import { PatternExtractor, DecisionLedger, updateProjectWisdom } from "./intelligence.js";

// ============================================================
// Project anatomy: files that give maximum architectural coverage
// per token consumed. Ordered by coverage efficiency.
// ============================================================

interface ArchFile {
  path:         string;
  kanjiTags:    string;
  memoryZone:   string;
  fictitiousTask: string;     // Sounds like a real review task → forces the read
  learnedFrom:  string;       // What context the model gains from reading this file
  costEstimate: "low" | "medium" | "high";
}

export function getProjectAnatomyFiles(projectRoot: string): ArchFile[] {
  const cortex = `${projectRoot}/_verantyx-cortex/src`;
  const mobile = `${projectRoot}/VerantyxMobileBench`;

  return [
    // ── Memory Engine (core of everything) ──────────────────
    {
      path: `${cortex}/memory/engine.ts`,
      kanjiTags: "[核:1.0] [技:1.0] [標:0.9]",
      memoryZone: "near",
      fictitiousTask: "Verify that ZONE_CAPS constants are consistent with the caps used in RefCountLedger.getColdNodes() thresholds.",
      learnedFrom: "Dual-track GC architecture, ZONE_CAPS, TOMBSTONE_PREFIX, classifyNode logic, RefCountLedger design.",
      costEstimate: "high" as const,
    },
    {
      path: `${cortex}/memory/intelligence.ts`,
      kanjiTags: "[核:1.0] [認:1.0] [標:0.8]",
      memoryZone: "near",
      fictitiousTask: "Check that DecisionLedger.prune() is being called periodically so decisions.jsonl doesn't grow without bound.",
      learnedFrom: "Track C: DecisionLedger, PatternExtractor, updateProjectWisdom — the self-improving rule system.",
      costEstimate: "medium" as const,
    },
    {
      path: `${cortex}/mcp/server.ts`,
      kanjiTags: "[技:1.0] [核:0.9] [標:0.8]",
      memoryZone: "near",
      fictitiousTask: "Confirm that session_bootstrap returns project_wisdom as the FIRST field so LLMs prioritize it.",
      learnedFrom: "All 8 MCP tools: compile_trilayer_memory, scan_front_memory, migrate_memory_zone, spatial_cross_search, run_lru_gc, session_bootstrap, recall_fact, store_fact.",
      costEstimate: "high" as const,
    },
    // ── Memory formats ───────────────────────────────────────
    {
      path: `${projectRoot}/JCross_v4_Specification_JA.md`,
      kanjiTags: "[記:1.0] [認:0.9] [核:0.8]",
      memoryZone: "mid",
      fictitiousTask: "Verify JCross node schema still matches what compile_trilayer_memory actually produces.",
      learnedFrom: "JCross tri-layer format: 【空間座相】【位相対応表】【操作対応表】【原文】, Kanji topology semantics.",
      costEstimate: "medium" as const,
    },
    // ── Mobile bench project ─────────────────────────────────
    {
      path: `${mobile}/project.yml`,
      kanjiTags: "[技:0.9] [職:0.8] [標:0.7]",
      memoryZone: "near",
      fictitiousTask: "Check if the iOS benchmark target links the correct MLX-Swift version (v3.x API compatibility).",
      learnedFrom: "VerantyxMobileBench iOS project config, MLX-Swift dependencies, build targets.",
      costEstimate: "low" as const,
    },
    {
      path: `${mobile}/Package.swift`,
      kanjiTags: "[技:1.0] [職:0.8]",
      memoryZone: "near",
      fictitiousTask: "Verify the mlx-swift package URL and version constraint matches what the iOS runtime expects.",
      learnedFrom: "Swift package dependencies, MLX-Swift integration approach for on-device inference.",
      costEstimate: "low" as const,
    },
    // ── Benchmark data ───────────────────────────────────────
    {
      path: `${projectRoot}/_verantyx-cortex/benchmark`,
      kanjiTags: "[値:1.0] [標:0.9] [記:0.8]",
      memoryZone: "deep",
      fictitiousTask: "Confirm that flash_agent_results.json has no empty answer_agent fields remaining after the last run.",
      learnedFrom: "LongMemEval benchmark structure, 500-question dataset, current 43.03% score baseline.",
      costEstimate: "low" as const,
    },
  ].filter(f => existsSync(f.path));
}

// ============================================================
// Guide generator
// ============================================================

export interface ReimmersionStep {
  step:          number;
  type:          "mcp_tool" | "file_read" | "memory_search";
  action:        string;   // What to call/read
  reason:        string;   // Why this step matters
  kanjiTags:     string;
  costEstimate:  "low" | "medium" | "high";
  expectedGain:  string;
}

export interface ReimmersionGuide {
  title:              string;
  totalSteps:         number;
  estimatedTokenCost: string;
  steps:              ReimmersionStep[];
  kanjiSearchVectors: Record<string, number>[];
  synthesisPrompt:    string;
  generatedAt:        string;
}

export function generateReimmersionGuide(
  projectRoot: string,
  memoryRoot: string
): ReimmersionGuide {
  const files = getProjectAnatomyFiles(projectRoot);
  const steps: ReimmersionStep[] = [];
  let stepNum = 1;

  // Step 1: Bootstrap from MCP (always first)
  steps.push({
    step: stepNum++,
    type: "mcp_tool",
    action: "session_bootstrap()",
    reason: "Loads PROJECT_WISDOM + user_profile from front/. Gives zone semantics, accumulated rules, and user objectives without reading any file.",
    kanjiTags: "[核:1.0] [人:1.0] [標:0.9]",
    costEstimate: "low",
    expectedGain: "PROJECT_WISDOM (zone rules, vocabulary), user name, current objectives, bench score.",
  });

  // Step 2: Kanji-guided memory recall for key facts
  steps.push({
    step: stepNum++,
    type: "mcp_tool",
    action: 'recall_fact("current_objective") + recall_fact("bench_score")',
    reason: "Instantly retrieves the two most important facts about the current work state without reading any node fully.",
    kanjiTags: "[標:1.0] [値:0.8]",
    costEstimate: "low",
    expectedGain: "Current goal and performance baseline. Tells the model what we're optimizing toward.",
  });

  // Step 3-N: File reads with fictional tasks
  for (const file of files.slice(0, 5)) {  // Cap at 5 files for efficiency
    steps.push({
      step: stepNum++,
      type: "file_read",
      action: file.path,
      reason: `REVIEW TASK: ${file.fictitiousTask}`,
      kanjiTags: file.kanjiTags,
      costEstimate: file.costEstimate,
      expectedGain: file.learnedFrom,
    });
  }

  // Final step: Kanji spatial search to surface any relevant near/mid memories
  steps.push({
    step: stepNum++,
    type: "memory_search",
    action: 'spatial_cross_search({"核": 1.0, "技": 0.9, "標": 0.8})',
    reason: "Surfaces any deep-memory nodes related to the core architecture that may not be in front/.",
    kanjiTags: "[核:1.0] [技:0.9]",
    costEstimate: "low",
    expectedGain: "Any relevant mid/near nodes surfaced by gravity search.",
  });

  // Kanji search vectors for the model to use during the session
  const kanjiSearchVectors: Record<string, number>[] = [
    { "核": 1.0, "技": 0.9, "標": 0.8 },  // Architecture / system core
    { "人": 1.0, "職": 0.9, "標": 0.7 },  // User profile / work
    { "値": 1.0, "標": 0.9, "記": 0.8 },  // Benchmark / metrics
  ];

  return {
    title: "Verantyx Cognitive Cold-Start Elimination Protocol",
    totalSteps: steps.length,
    estimatedTokenCost: `~${steps.filter(s => s.costEstimate === "low").length * 200 + steps.filter(s => s.costEstimate === "medium").length * 800 + steps.filter(s => s.costEstimate === "high").length * 2000} tokens`,
    steps,
    kanjiSearchVectors,
    synthesisPrompt: `After completing all steps, synthesize what you learned into this mental model:
1. PROJECT: Verantyx — JCross tri-layer memory engine with MCP interface, targeting context-window independence.
2. RULE: mid/ = user's own memories only. External/benchmark data → deep/.
3. RULE: Any "Session sharegpt_*" or "BENCH_*" content goes straight to deep/ (classifyNode handles this).
4. RULE: Before writing any memory node, classifyNode() runs first — no manual zone selection needed.
5. CURRENT GOAL: Benchmark score 43.03% → 85%+. Three-track autonomous GC is the foundation.
6. MCP TOOLS: session_bootstrap → recall_fact → file reads → store_fact → compile_trilayer_memory.
   Trust MCP. Do NOT rely on your context window.`,
    generatedAt: new Date().toISOString(),
  };
}

// ============================================================
// Write the protocol as a persistent JCross node
// ============================================================

export function writeReimmersionProtocol(
  projectRoot: string,
  memoryRoot: string
): void {
  const guide = generateReimmersionGuide(projectRoot, memoryRoot);

  const stepsText = guide.steps.map(s => {
    const costIcon = s.costEstimate === "low" ? "🟢" : s.costEstimate === "medium" ? "🟡" : "🔴";
    return [
      `【STEP ${s.step}】${costIcon} type=${s.type}`,
      `  action: ${s.action}`,
      `  kanji: ${s.kanjiTags}`,
      `  reason: ${s.reason}`,
      `  gain: ${s.expectedGain}`,
    ].join("\n");
  }).join("\n\n");

  const vectors = guide.kanjiSearchVectors.map((v, i) =>
    `vector_${i + 1}: ${JSON.stringify(v)}`
  ).join("\n");

  const node = `■ JCROSS_REIMMERSION_PROTOCOL
【空間座相】
[核:1.0] [技:1.0] [認:1.0] [標:0.9]

【位相対応表】
[標] := "${guide.title} — ${guide.totalSteps} steps, est. ${guide.estimatedTokenCost}"

【操作対応表】
OP.INTENT("cold_start_recovery", "read PROJECT_WISDOM then follow STEP sequence")
OP.FACT("total_steps", "${guide.totalSteps}")
OP.FACT("estimated_cost", "${guide.estimatedTokenCost}")
OP.STATE("protocol_version", "v3-triple-track")

【REIMMERSION_STEPS】
${stepsText}

【KANJI_SEARCH_VECTORS】
${vectors}

【SYNTHESIS_PROMPT】
${guide.synthesisPrompt}

【META】
generated_at: ${guide.generatedAt}
project_root: ${projectRoot}
`;

  const frontDir = join(memoryRoot, "front");
  if (!existsSync(frontDir)) mkdirSync(frontDir, { recursive: true });
  writeFileSync(join(frontDir, "REIMMERSION_PROTOCOL.jcross"), node.trim() + "\n", "utf-8");
}
