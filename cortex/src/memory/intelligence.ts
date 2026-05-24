/**
 * Track C: Contextual Intelligence Index
 *
 * Three components:
 *
 *  1. DecisionLedger      — records every classification/GC decision with full reasoning.
 *                           Stored at <root>/meta/decisions.jsonl (append-only).
 *
 *  2. PatternExtractor    — scans the ledger for recurring patterns and computes
 *                           confidence scores per rule.
 *
 *  3. updateProjectWisdom — writes/updates front/PROJECT_WISDOM.jcross so that
 *                           ANY new LLM session reading session_bootstrap() immediately
 *                           inherits the accumulated project knowledge and can make
 *                           the same zone-placement judgments as a veteran agent.
 */

import { existsSync, mkdirSync, appendFileSync, readFileSync, writeFileSync } from "fs";
import { join } from "path";

// ============================================================
// 1. Decision Ledger (append-only JSONL)
// ============================================================

export interface ClassificationDecision {
  ts:         number;        // Unix ms
  file:       string;
  fromZone:   string;
  toZone:     string;
  reason:     string;
  confidence: number;
  track:      "A-classifier" | "A-cold" | "B-lru" | "manual";
}

/**
 * Append-only log of every zone-placement decision made by the autonomous GC.
 * Used by PatternExtractor to derive project-specific rules.
 */
export class DecisionLedger {
  private path: string;

  constructor(memoryRoot: string) {
    const metaDir = join(memoryRoot, "meta");
    if (!existsSync(metaDir)) mkdirSync(metaDir, { recursive: true });
    this.path = join(metaDir, "decisions.jsonl");
  }

  record(decision: ClassificationDecision): void {
    try {
      appendFileSync(this.path, JSON.stringify(decision) + "\n", "utf-8");
    } catch { /* non-fatal */ }
  }

  readAll(): ClassificationDecision[] {
    if (!existsSync(this.path)) return [];
    try {
      return readFileSync(this.path, "utf-8")
        .trim()
        .split("\n")
        .filter(l => l.trim())
        .map(l => JSON.parse(l) as ClassificationDecision);
    } catch {
      return [];
    }
  }

  /** Keep only the last N entries to prevent unbounded growth. */
  prune(maxEntries = 10_000): void {
    const all = this.readAll();
    if (all.length <= maxEntries) return;
    const kept = all.slice(-maxEntries);
    try {
      writeFileSync(this.path, kept.map(e => JSON.stringify(e)).join("\n") + "\n", "utf-8");
    } catch { /* non-fatal */ }
  }
}

// ============================================================
// 2. Pattern Extractor
// ============================================================

export interface AccumulatedRule {
  id:          string;
  pattern:     string;           // human-readable description
  targetZone:  string;
  confidence:  number;           // 0.0–1.0
  sampleCount: number;
  examples:    string[];         // up to 3 example filenames
}

export interface ProjectPattern {
  rules:            AccumulatedRule[];
  totalDecisions:   number;
  zoneDistribution: Record<string, number>;
  vocabularyHints:  string[];    // inferred filename/content patterns → zone
  generatedAt:      string;
}

/**
 * Analyzes the decision ledger to discover:
 *  - Filename prefixes that consistently map to a single zone
 *  - Content keywords that predict zone placement
 *  - Confidence scores based on actual decision counts
 */
export class PatternExtractor {
  private ledger: DecisionLedger;

  constructor(ledger: DecisionLedger) {
    this.ledger = ledger;
  }

  extract(): ProjectPattern {
    const decisions = this.ledger.readAll();
    const totalDecisions = decisions.length;
    const zoneDistribution: Record<string, number> = {};

    // Tally destination zones
    for (const d of decisions) {
      zoneDistribution[d.toZone] = (zoneDistribution[d.toZone] ?? 0) + 1;
    }

    // Group by reason string → derive rules
    const reasonGroups: Record<string, ClassificationDecision[]> = {};
    for (const d of decisions) {
      const key = `${d.reason}→${d.toZone}`;
      if (!reasonGroups[key]) reasonGroups[key] = [];
      reasonGroups[key].push(d);
    }

    // Prefix patterns: group by filename prefix → zone
    const prefixGroups: Record<string, Record<string, number>> = {};
    for (const d of decisions) {
      const prefix = d.file.split("_")[0] + "_";
      if (!prefixGroups[prefix]) prefixGroups[prefix] = {};
      prefixGroups[prefix][d.toZone] = (prefixGroups[prefix][d.toZone] ?? 0) + 1;
    }

    const rules: AccumulatedRule[] = [];
    let ruleIdx = 1;

    // Rules from reason groups
    for (const [key, group] of Object.entries(reasonGroups)) {
      const [reason, zone] = key.split("→");
      const conf = Math.min(0.99, (group.length / (group.length + 1)) * (1 + group.length * 0.01));
      rules.push({
        id:          `rule_${String(ruleIdx++).padStart(3, "0")}`,
        pattern:     reason,
        targetZone:  zone,
        confidence:  parseFloat(conf.toFixed(3)),
        sampleCount: group.length,
        examples:    group.slice(0, 3).map(d => d.file),
      });
    }

    // Rules from prefix patterns
    for (const [prefix, zoneCounts] of Object.entries(prefixGroups)) {
      const sorted = Object.entries(zoneCounts).sort((a, b) => b[1] - a[1]);
      const [topZone, topCount] = sorted[0];
      const total = Object.values(zoneCounts).reduce((s, c) => s + c, 0);
      if (total >= 5 && topCount / total >= 0.9) {
        const existing = rules.find(r => r.pattern.includes(prefix));
        if (!existing) {
          rules.push({
            id:          `rule_${String(ruleIdx++).padStart(3, "0")}`,
            pattern:     `filename starts with "${prefix}"`,
            targetZone:  topZone,
            confidence:  parseFloat((topCount / total).toFixed(3)),
            sampleCount: total,
            examples:    decisions.filter(d => d.file.startsWith(prefix)).slice(0, 3).map(d => d.file),
          });
        }
      }
    }

    // Sort by confidence × sampleCount descending
    rules.sort((a, b) => (b.confidence * Math.log(b.sampleCount + 1)) - (a.confidence * Math.log(a.sampleCount + 1)));

    // Derive vocabulary hints
    const vocabHints: string[] = [];
    for (const rule of rules.slice(0, 10)) {
      vocabHints.push(`${rule.pattern} → ${rule.targetZone}/ (conf=${rule.confidence}, n=${rule.sampleCount})`);
    }

    return {
      rules,
      totalDecisions,
      zoneDistribution,
      vocabularyHints: vocabHints,
      generatedAt: new Date().toISOString(),
    };
  }
}

// ============================================================
// 3. PROJECT_WISDOM.jcross writer
// ============================================================

/**
 * Writes (or updates) `front/PROJECT_WISDOM.jcross`.
 *
 * This node is the THIRD PILLAR of the autonomous memory system.
 * It is what transforms a blank-slate LLM session into a session
 * that understands the project's memory topology, vocabulary, and
 * design principles — without any human prompt injection.
 *
 * When session_bootstrap() is called, this node is parsed and
 * returned as part of the user_profile, giving the LLM:
 *   - Zone semantics (what belongs where and why)
 *   - Accumulated rules (derived from N actual decisions)
 *   - Project vocabulary (known filename patterns → zones)
 *   - Design principles (immutable architectural truths)
 */
export function updateProjectWisdom(
  memoryRoot: string,
  pattern: ProjectPattern,
  extraPrinciples: string[] = []
): void {
  const topRules = pattern.rules.slice(0, 15);

  const rulesSection = topRules.map(r =>
    `${r.id}: ${r.pattern} → ${r.targetZone}/ (confidence=${r.confidence}, n=${r.sampleCount})\n` +
    `        examples: ${r.examples.join(", ")}`
  ).join("\n");

  const distSection = Object.entries(pattern.zoneDistribution)
    .map(([z, c]) => `${z}/: ${c} placements`)
    .join("\n");

  const wisdom = `■ JCROSS_PROJECT_WISDOM
【空間座相】
[核:1.0] [技:1.0] [標:0.9] [認:0.9]

【位相対応表】
[標] := "Verantyx JCross project wisdom — accumulated from ${pattern.totalDecisions} autonomous GC decisions. Read this to make correct zone-placement judgments."

【ZONE_SEMANTICS】
front/ — User profile, current session objectives, active system state.
         NOTHING from external datasets belongs here.
         Cap: 100 nodes.

near/  — User's OWN recent technical knowledge, personal episodic memory.
         Evicted from front/ by LRU but still warm.
         Cap: 1000 nodes.

mid/   — User's OWN compressed/archived memories after sublimation.
         NOT for external data. When a new LLM reads a node and asks
         "should this be compressed to mid/?", the answer is NO if the
         content is not the user's own experience.
         Cap: 5000 nodes.

deep/  — External / benchmark / archived data. Passive long-term storage.
         BENCH_* nodes, Session sharegpt_*, Session ultrachat_* ALL go here.
         No cap.

【PROJECT_VOCABULARY】
BENCH_*          → deep/  (LongMemEval benchmark sessions — external data)
Session sharegpt_* → deep/ (external ShareGPT chat data)
Session ultrachat_* → deep/ (external UltraChat data)
Session [8hex]_* → deep/  (external benchmark session format)
TURN_*           → classify by content (may be user's own memory)
OP.ENTITY("user_name") → front/ (user profile anchor)
OP.STATE("current_*")  → front/ (active system state)

【ACCUMULATED_RULES】
Total decisions analyzed: ${pattern.totalDecisions}
Zone distribution: ${distSection}

${rulesSection || "(No patterns yet — rules will appear after first GC run)"}

【DESIGN_PRINCIPLES】
1. mid/ is sacred space for the USER's own compressed memories.
   External/benchmark data must NEVER occupy it.

2. When classifyNode() sees "Session" + external-looking session IDs,
   send it straight to deep/ regardless of Kanji tags.

3. Kanji tags are assigned BY the LLM that writes the node.
   If they are all [標記認] (the default), treat this as a signal that
   the writing LLM did not have project context — re-evaluate by content.

4. front/ should feel like a "working desk" — only what is needed
   RIGHT NOW for the current user session.

5. The RefCountLedger is the most honest signal: a node that has never
   been read is cold and should cascade down automatically.

6. When uncertain about zone placement, ALWAYS check PROJECT_WISDOM first.
   If no rule applies, default to near/ and let the GC sort it out.

${extraPrinciples.length > 0 ? "【ADDITIONAL_PRINCIPLES】\n" + extraPrinciples.map((p, i) => `${i + 7}. ${p}`).join("\n") : ""}

【META】
updated_at: ${pattern.generatedAt}
decisions_analyzed: ${pattern.totalDecisions}
rules_count: ${topRules.length}
`;

  const frontDir = join(memoryRoot, "front");
  if (!existsSync(frontDir)) mkdirSync(frontDir, { recursive: true });
  writeFileSync(join(frontDir, "PROJECT_WISDOM.jcross"), wisdom.trim() + "\n", "utf-8");
}
