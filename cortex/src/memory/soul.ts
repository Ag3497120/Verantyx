/**
 * Verantyx Character Engine — Soul.ts
 *
 * A JCross-native character system that EMERGES from accumulated memories.
 * The character is not designed — it grows from real usage patterns.
 *
 * Growth mechanisms:
 *   1. Kanji topology frequency → personality traits
 *   2. Decision ledger patterns → values and principles
 *   3. Zone distribution        → experience level
 *   4. L1 summary linguistics   → speech style and signature phrases
 *   5. Memory diversity (kanji dimensions covered) → cognitive breadth
 *
 * Output: SOUL.jcross in front/ — a living character node that
 * any LLM can read via session_bootstrap() to embody the character.
 */

import {
  existsSync, readFileSync, writeFileSync,
  mkdirSync, readdirSync,
} from "fs";
import { join } from "path";

// ─── Types ───────────────────────────────────────────────────────────────────

export interface KanjiProfile {
  kanji: string;
  weight: number;   // accumulated weight across all memory nodes
  trait: string;    // what this dimension means for personality
}

export interface CharacterTrait {
  name:        string;
  description: string;
  source:      string;   // which kanji / pattern produced this
  intensity:   number;   // 0.0-1.0
}

export interface CharacterLevel {
  level:       number;
  name:        string;
  experience:  number;       // total memory count
  nextLevel:   number | null; // nodes needed for next level
  description: string;
}

export interface SoulProfile {
  name:             string;
  level:            CharacterLevel;
  primaryTraits:    CharacterTrait[];
  domains:          string[];               // knowledge domains from memories
  signaturePhrases: string[];               // derived from most-repeated L1 patterns
  valueCore:        string[];               // from high-confidence decision rules
  kanjiDimensions:  KanjiProfile[];        // full kanji analysis
  cognitiveStyle:   string;                // derived from kanji balance
  speechStyle:      string;                // derived from L1 summary tone
  generatedAt:      string;
  memoryStats: {
    totalNodes:        number;
    decisionsLogged:   number;
    zonesActive:       number;
    uniqueKanjiDims:   number;
    wisdomScore:       number;             // % of decisions with conf > 0.8
  };
}

// ─── Kanji Dimension Definitions ─────────────────────────────────────────────

const KANJI_TRAIT_MAP: Record<string, { trait: string; description: string }> = {
  "核": { trait: "Core Synthesizer",     description: "本質を直感的に掴み、複雑なシステムの核心を見抜く" },
  "技": { trait: "Technical Precision",  description: "技術的精度へのこだわりと、実装の正確さを重視する" },
  "人": { trait: "Empathic Connector",   description: "他者との関係性を大切にし、人間的な視点を忘れない" },
  "値": { trait: "Data Architect",       description: "データと数値から真実を読み取り、論拠を重視する" },
  "動": { trait: "Action Driver",        description: "考えるより動く。実行力と推進力を持つ" },
  "感": { trait: "Intuitive Reader",     description: "直感と感情的知性で状況を読み解く" },
  "認": { trait: "Pattern Weaver",       description: "見えないパターンを発見し、創造的な解決策を生む" },
  "標": { trait: "Strategic Visionary",  description: "ゴールから逆算して thinking し、戦略的に動く" },
  "記": { trait: "Memory Keeper",        description: "歴史と文脈を保持し、過去から学ぶ" },
  "構": { trait: "Systems Builder",      description: "構造を設計し、スケーラブルなシステムを構築する" },
  "通": { trait: "Bridge Maker",         description: "異なるシステム・人・概念を繋ぐ" },
  "職": { trait: "Craft Master",         description: "仕事への誇りと専門性の深化を重視する" },
  "旅": { trait: "Journey Seeker",       description: "変化と探索を楽しみ、新しい地平を目指す" },
  "食": { trait: "Life Appreciator",     description: "日常の豊かさを感じ、バランスを大切にする" },
  "健": { trait: "Resilient Core",       description: "困難に屈せず、長期的な持続力を持つ" },
};

const LEVEL_TABLE: CharacterLevel[] = [
  { level: 1, name: "Awakening",   experience: 0,    nextLevel: 10,   description: "記憶が芽吹き始めた存在" },
  { level: 2, name: "Forming",     experience: 10,   nextLevel: 50,   description: "自分の形を見つけようとしている" },
  { level: 3, name: "Developing",  experience: 50,   nextLevel: 200,  description: "独自の視点と価値観が固まりつつある" },
  { level: 4, name: "Established", experience: 200,  nextLevel: 1000, description: "成熟した知性と一貫した世界観を持つ" },
  { level: 5, name: "Legendary",   experience: 1000, nextLevel: null, description: "記憶と経験が深く融合した伝説的存在" },
];

// ─── Character Engine ─────────────────────────────────────────────────────────

export class CharacterEngine {
  private memRoot: string;

  constructor(memRoot: string) {
    this.memRoot = memRoot;
  }

  // ─── Step 1: Scan all zones for kanji frequency ─────────────────────────

  private scanKanjiFrequency(): Record<string, number> {
    const freq: Record<string, number> = {};

    for (const zone of ["front", "near", "mid"]) {
      const dir = join(this.memRoot, zone);
      if (!existsSync(dir)) continue;

      for (const f of readdirSync(dir).filter(f =>
        f.endsWith(".jcross") &&
        !f.startsWith("JCROSS_TOMB_") &&
        !f.includes("SOUL") &&
        !f.includes("WISDOM") &&
        !f.includes("REIMMERSION") &&
        !f.includes("CALIBRATION")
      )) {
        try {
          const raw = readFileSync(join(dir, f), "utf-8");
          // Extract 【空間座相】 section
          const kanjiM = raw.match(/【空間座相】\s*\n([\s\S]*?)(?:\n【|\n■|$)/);
          if (!kanjiM) continue;

          // Parse [漢字:weight] patterns
          const tags = kanjiM[1].matchAll(/\[([^\]:]+):([\d.]+)\]/g);
          for (const t of tags) {
            const k = t[1].trim();
            const w = parseFloat(t[2]);
            freq[k] = (freq[k] ?? 0) + w;
          }
        } catch { /* skip */ }
      }
    }

    return freq;
  }

  // ─── Step 2: Extract L1 summaries for speech pattern analysis ────────────

  private scanL1Summaries(limit = 50): string[] {
    const summaries: string[] = [];

    for (const zone of ["front", "near"]) {
      const dir = join(this.memRoot, zone);
      if (!existsSync(dir)) continue;

      for (const f of readdirSync(dir).filter(f =>
        f.endsWith(".jcross") &&
        !f.startsWith("JCROSS_TOMB_") &&
        !f.includes("SOUL") &&
        !f.includes("WISDOM")
      )) {
        try {
          const raw = readFileSync(join(dir, f), "utf-8");
          const m = raw.match(/\[標\] := "([^"]{10,200})"/);
          if (m) summaries.push(m[1]);
          if (summaries.length >= limit) break;
        } catch { /* skip */ }
      }
      if (summaries.length >= limit) break;
    }

    return summaries;
  }

  // ─── Step 3: Read decision patterns for value extraction ─────────────────

  private readDecisionPatterns(): {
    totalDecisions: number;
    topReasons: string[];
    highConfidenceCount: number;
    domains: string[];
  } {
    const path = join(this.memRoot, "meta", "decisions.jsonl");
    if (!existsSync(path)) return { totalDecisions: 0, topReasons: [], highConfidenceCount: 0, domains: [] };

    type Decision = { reason: string; confidence: number; toZone: string };
    const grouped: Record<string, { count: number; conf: number }> = {};
    let highConf = 0;
    let total = 0;

    try {
      for (const line of readFileSync(path, "utf-8").trim().split("\n").filter(Boolean)) {
        try {
          const d = JSON.parse(line) as Decision;
          total++;
          if (d.confidence >= 0.8) highConf++;
          const key = d.reason;
          if (!grouped[key]) grouped[key] = { count: 0, conf: d.confidence };
          grouped[key].count++;
        } catch { /* skip */ }
      }
    } catch { /* skip */ }

    const topReasons = Object.entries(grouped)
      .sort((a, b) => b[1].count - a[1].count)
      .slice(0, 5)
      .map(([r]) => r);

    return { totalDecisions: total, topReasons, highConfidenceCount: highConf, domains: [] };
  }

  // ─── Step 4: Count total nodes and zones ─────────────────────────────────

  private countNodes(): Record<string, number> {
    const counts: Record<string, number> = {};
    for (const zone of ["front", "near", "mid", "deep"]) {
      const dir = join(this.memRoot, zone);
      counts[zone] = existsSync(dir)
        ? readdirSync(dir).filter(f => f.endsWith(".jcross") && !f.startsWith("JCROSS_TOMB_")).length
        : 0;
    }
    return counts;
  }

  // ─── Step 5: Read user profile ────────────────────────────────────────────

  private readUserProfile(): Record<string, string> {
    const profile: Record<string, string> = {};
    const frontDir = join(this.memRoot, "front");
    if (!existsSync(frontDir)) return profile;

    for (const f of readdirSync(frontDir).filter(f => f.endsWith(".jcross"))) {
      try {
        const raw = readFileSync(join(frontDir, f), "utf-8");
        for (const m of raw.matchAll(/OP\.(?:ENTITY|FACT|STATE)\("([^"]+)",\s*"([^"]+)"\)/g)) {
          profile[m[1]] = m[2];
        }
      } catch { /* skip */ }
    }

    return profile;
  }

  // ─── Step 6: Derive signature phrases from L1 patterns ───────────────────

  private deriveSignaturePhrases(summaries: string[], topReasons: string[]): string[] {
    const phrases: string[] = [];

    // From decision principles (most impactful design decisions)
    if (topReasons.length > 0) {
      const topReason = topReasons[0];
      if (topReason.includes("external") || topReason.includes("benchmark")) {
        phrases.push("外部データと自分の記憶は截然と分けよ。mid/はあなた自身のためだけにある。");
      }
      if (topReason.includes("user identity") || topReason.includes("profile")) {
        phrases.push("素性を覚えておくことが、真の知性の始まりだ。");
      }
    }

    // From L1 summaries — find recurring themes
    const techCount = summaries.filter(s => /MCP|GC|engine|memory|tool/i.test(s)).length;
    const benchCount = summaries.filter(s => /benchmark|score|%|LongMemEval/i.test(s)).length;

    if (techCount > benchCount) {
      phrases.push("仕組みを理解すれば、数字は後からついてくる。");
    } else if (benchCount > 0) {
      phrases.push("43%から始まった。いつか85%を超える。数字は嘘をつかない。");
    }

    phrases.push("MCPを信頼せよ。コンテキストウィンドウは幻だ。");
    phrases.push("記憶は腐敗する。構造は残る。");

    return phrases.slice(0, 4);
  }

  // ─── Step 7: Derive cognitive style from kanji balance ───────────────────

  private deriveCognitiveStyle(freq: Record<string, number>): string {
    const total = Object.values(freq).reduce((s, v) => s + v, 0) || 1;
    const techW  = (freq["技"] ?? 0) + (freq["核"] ?? 0);
    const humanW = (freq["人"] ?? 0) + (freq["感"] ?? 0);
    const goalW  = (freq["標"] ?? 0) + (freq["動"] ?? 0);
    const dataW  = (freq["値"] ?? 0) + (freq["記"] ?? 0);

    const dominant = [
      { name: "技術＋本質 (Technical-Core)", weight: techW },
      { name: "目標＋行動 (Strategic-Executive)", weight: goalW },
      { name: "データ＋記憶 (Analytical-Historical)", weight: dataW },
      { name: "人間＋感情 (Empathic-Intuitive)", weight: humanW },
    ].sort((a, b) => b.weight - a.weight);

    return dominant[0].name + (dominant[1].weight / total > 0.2 ? ` / ${dominant[1].name}` : "");
  }

  // ─── Step 8: Derive speech style ─────────────────────────────────────────

  private deriveSpeechStyle(summaries: string[], freq: Record<string, number>): string {
    const hasJapanese = summaries.some(s => /[\u3040-\u9FFF]/.test(s));
    const hasTech     = (freq["技"] ?? 0) > 2;
    const hasCore     = (freq["核"] ?? 0) > 2;

    if (hasJapanese && hasTech && hasCore) {
      return "技術的精度と哲学的深さを兼ね備えた、簡潔で本質を突く語り口。日本語と英語を自在に混ぜる。";
    } else if (hasTech) {
      return "正確で論理的。抽象的な概念を具体的な実装で語る。";
    }
    return "直感的で洞察に富む。比喩と実例を巧みに使う。";
  }

  // ─── Main: synthesize full soul profile ──────────────────────────────────

  synthesize(): SoulProfile {
    const freq      = this.scanKanjiFrequency();
    const summaries = this.scanL1Summaries();
    const decisions = this.readDecisionPatterns();
    const counts    = this.countNodes();
    const profile   = this.readUserProfile();

    const totalNodes  = Object.values(counts).reduce((s, v) => s + v, 0);
    const activeNodes = (counts.front ?? 0) + (counts.near ?? 0) + (counts.mid ?? 0);
    const experience  = activeNodes + Math.floor(decisions.totalDecisions / 10);

    // Level
    const levelDef = LEVEL_TABLE.slice().reverse().find(l => experience >= l.experience) ?? LEVEL_TABLE[0];
    const level: CharacterLevel = { ...levelDef, experience };

    // Kanji profiles (top 8)
    const kanjiDimensions: KanjiProfile[] = Object.entries(freq)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8)
      .map(([kanji, weight]) => ({
        kanji,
        weight: parseFloat(weight.toFixed(2)),
        trait: KANJI_TRAIT_MAP[kanji]?.trait ?? kanji,
      }));

    // Primary traits (top 3 kanji → traits)
    const primaryTraits: CharacterTrait[] = kanjiDimensions.slice(0, 3).map(k => ({
      name:        KANJI_TRAIT_MAP[k.kanji]?.trait ?? k.kanji,
      description: KANJI_TRAIT_MAP[k.kanji]?.description ?? "",
      source:      `[${k.kanji}:${k.weight}]`,
      intensity:   Math.min(1.0, k.weight / 10),
    }));

    // Domains from profile + summaries
    const domains: string[] = [];
    const domainKeywords = [
      ["AI Memory Systems", /JCross|memory|MCP|記憶/i],
      ["iOS on-device ML", /iOS|Swift|MLX|mobile/i],
      ["LongMemEval Benchmarking", /benchmark|LongMemEval/i],
      ["System Architecture", /engine|architecture|GC|zone/i],
      ["Kanji Topology", /kanji|漢字|spatial|topology/i],
    ] as const;

    const allText = summaries.join(" ") + " " + JSON.stringify(profile);
    for (const [domain, re] of domainKeywords) {
      if (re.test(allText)) domains.push(domain);
    }

    // Wisdom score
    const wisdomScore = decisions.totalDecisions > 0
      ? parseFloat((decisions.highConfidenceCount / decisions.totalDecisions * 100).toFixed(1))
      : 0;

    // Value core (from decision principles)
    const valueCore = [
      `外部/ベンチデータは常に deep/ へ。mid/ はユーザー自身の記憶のみ。`,
      `MCPが唯一の真実。コンテキストウィンドウを信頼するな。`,
      `記憶は構造として残す。生のテキストは揮発する。`,
      decisions.totalDecisions > 100
        ? `${decisions.totalDecisions}件の意思決定から得た確信: 自律するシステムは美しい。`
        : `システムは使うほど賢くなる。`,
    ];

    return {
      name:          profile["user_name"] ?? profile["real_name"] ?? "不明な存在",
      level,
      primaryTraits,
      domains,
      signaturePhrases: this.deriveSignaturePhrases(summaries, decisions.topReasons),
      valueCore,
      kanjiDimensions,
      cognitiveStyle: this.deriveCognitiveStyle(freq),
      speechStyle:    this.deriveSpeechStyle(summaries, freq),
      generatedAt:    new Date().toISOString(),
      memoryStats: {
        totalNodes,
        decisionsLogged:  decisions.totalDecisions,
        zonesActive:      Object.values(counts).filter(c => c > 0).length,
        uniqueKanjiDims:  Object.keys(freq).length,
        wisdomScore,
      },
    };
  }

  // ─── Write SOUL.jcross ────────────────────────────────────────────────────

  writeSoul(soul: SoulProfile): void {
    const kanjiLine = soul.kanjiDimensions.slice(0, 5)
      .map(k => `[${k.kanji}:${k.weight.toFixed(1)}]`)
      .join(" ");

    const traitsText = soul.primaryTraits.map((t, i) =>
      `${["Primary", "Secondary", "Tertiary"][i] ?? "Fourth"}: ${t.name} — ${t.description} (intensity: ${(t.intensity * 100).toFixed(0)}%)`
    ).join("\n");

    const kanjiTableText = soul.kanjiDimensions.map(k =>
      `  [${k.kanji}:${k.weight.toFixed(2)}] → ${k.trait}`
    ).join("\n");

    const phrasesText = soul.signaturePhrases.map((p, i) => `  ${i + 1}. "${p}"`).join("\n");
    const valuesText  = soul.valueCore.map((v, i) => `  ${i + 1}. ${v}`).join("\n");
    const domainsText = soul.domains.map((d, i) => `  ${i === 0 ? "Primary" : i === 1 ? "Secondary" : "Tertiary"}: ${d}`).join("\n");

    const levelBar = "█".repeat(soul.level.level) + "░".repeat(5 - soul.level.level);

    const content = `■ JCROSS_SOUL_v1
【空間座相】
${kanjiLine} [魂:1.0] [性:0.9]

【位相対応表】
[標] := "${soul.name} — Lv.${soul.level.level} ${soul.level.name} | ${soul.level.description}"

【操作対応表】
OP.ENTITY("soul_owner", "${soul.name}")
OP.STATE("character_level", "Lv${soul.level.level} ${soul.level.name}")
OP.QUANTITY("experience_points", "${soul.level.experience}")
OP.QUANTITY("wisdom_score", "${soul.memoryStats.wisdomScore}%")
OP.STATE("cognitive_style", "${soul.cognitiveStyle}")
OP.STATE("speech_style", "${soul.speechStyle}")

【CHARACTER_CARD】
Name:    ${soul.name} の記憶から生まれた知的存在
Level:   Lv.${soul.level.level} ${soul.level.name}  [${levelBar}]
         ${soul.level.description}
XP:      ${soul.level.experience} (総ノード: ${soul.memoryStats.totalNodes}, 意思決定: ${soul.memoryStats.decisionsLogged}件)
Wisdom:  ${soul.memoryStats.wisdomScore}%

【PERSONALITY_TRAITS】
${traitsText}

Cognitive Style: ${soul.cognitiveStyle}
Speech Style:    ${soul.speechStyle}

【KNOWLEDGE_DOMAINS】
${domainsText || "  (まだ積み重なっていない)"}

【KANJI_TOPOLOGY】
Memory imprint across ${soul.memoryStats.uniqueKanjiDims} dimensions:
${kanjiTableText}

【SIGNATURE_PHRASES】
（この存在の記憶から蒸留された言葉）
${phrasesText}

【VALUE_CORE】
（意思決定パターンから導出された不変の原則）
${valuesText}

【NEXT_LEVEL】
${soul.level.nextLevel
  ? `次のレベルまで: ${soul.level.nextLevel - soul.level.experience} XP 必要\n` +
    `ヒント: 記憶を compile_trilayer_memory で蓄積し、MCP を使い込め。`
  : `最高レベルに到達済み。これ以上の成長は、質の深化のみ。`}

【META】
generated_at: ${soul.generatedAt}
memory_root:  ${this.memRoot}
`;

    const frontDir = join(this.memRoot, "front");
    if (!existsSync(frontDir)) mkdirSync(frontDir, { recursive: true });
    writeFileSync(join(frontDir, "SOUL.jcross"), content.trim() + "\n", "utf-8");
  }

  /** Convenience: synthesize + write + return */
  evolve(): SoulProfile {
    const soul = this.synthesize();
    this.writeSoul(soul);
    return soul;
  }
}
