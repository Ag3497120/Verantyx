import {
  readFileSync,
  writeFileSync,
  existsSync,
  mkdirSync,
  readdirSync,
  renameSync,
  unlinkSync,
  statSync,
} from "fs";
import { join } from "path";
import { MemoryEntry, MemoryZone, ReadMemoryResult } from "./types.js";
import { DecisionLedger, PatternExtractor, updateProjectWisdom } from "./intelligence.js";

const ZONES: MemoryZone[] = ["front", "near", "mid", "deep"];

// LRU cascade caps — when a zone exceeds this count, overflowing nodes
// (least-recently-used first) are pushed to the next zone.
export const ZONE_CAPS: Record<string, number> = {
  front: 100,
  near:  1000,
  mid:   5000,
  deep:  Infinity,
};

// Prefix written on tombstone files so every agent can identify them cheaply.
export const TOMBSTONE_PREFIX = "JCROSS_TOMB_" as const;

// ============================================================
// MARK: - Track A: Rule-based Node Classifier
// ============================================================

export type MemoryZoneRec = "front" | "near" | "mid" | "deep";

export interface ZoneClassification {
  zone:   MemoryZoneRec;
  reason: string;
  confidence: number; // 0.0-1.0
}

/**
 * Pure rule-based classifier. Called BEFORE writing a node so
 * compile_trilayer_memory places it in the correct zone immediately.
 * No LLM call — deterministic, < 1ms.
 *
 * Priority order (first match wins):
 *  1. Bench/external data fingerprint → deep
 *  2. User-profile identity markers   → front
 *  3. System architecture / code      → near
 *  4. Personal episodic memory        → near
 *  5. Archived/historical context     → mid
 *  6. Default                         → near
 */
export function classifyNode(content: string, fileName: string): ZoneClassification {
  const lower = content.toLowerCase();

  // 1. Bench data: sharegpt / ultrachat session markers, or BENCH_ filename
  if (
    fileName.startsWith("BENCH_") ||
    /session (sharegpt|ultrachat|answer_)/.test(lower) ||
    /session [0-9a-f]{8}/.test(lower)
  ) {
    return { zone: "deep", reason: "external/benchmark session data", confidence: 0.95 };
  }

  // 2. User profile: has identity OP ops or explicit profile marker
  if (
    content.includes("JCROSS_USER_PROFILE") ||
    content.includes('OP.ENTITY("user_name"') ||
    content.includes('OP.STATE("current_objective"')
  ) {
    return { zone: "front", reason: "user identity profile", confidence: 1.0 };
  }

  // 3. Active system state / current session objective
  if (
    /op\.(state|flag)\(["'](?:current|active|phase|status)/i.test(content) ||
    content.includes("【SYSTEM_STATE】") ||
    content.includes("benchmark_score")
  ) {
    return { zone: "front", reason: "active system state", confidence: 0.9 };
  }

  // 4. Code / architecture / technical design
  if (
    /\[技|核|標\]/.test(content) &&
    /(typescript|rust|swift|python|impl|engine|mcp|api)/i.test(content)
  ) {
    return { zone: "near", reason: "technical architecture knowledge", confidence: 0.8 };
  }

  // 5. Personal episodic memory (user's own life events)
  if (/\[人|感|動|旅|食|健\]/.test(content)) {
    return { zone: "near", reason: "personal episodic memory", confidence: 0.75 };
  }

  // 6. Explicitly historical / resolved / archived
  if (
    content.includes("JCROSS_GHOST_RES1") ||
    content.includes("JCROSS_TRI_RES_") ||
    content.includes("【RESOLUTION】") ||
    content.includes("[ARCHIVED]")
  ) {
    return { zone: "mid", reason: "archived/resolved memory", confidence: 0.9 };
  }

  // Default: near (general working memory)
  return { zone: "near", reason: "general working memory (default)", confidence: 0.5 };
}

// ============================================================
// MARK: - Track A: Reference Count Ledger
// ============================================================

interface RefLedger {
  counts: Record<string, number>;        // fileName → total reads
  lastRead: Record<string, number>;      // fileName → timestamp (ms)
  lastWrite: Record<string, number>;     // fileName → timestamp (ms)
}

/**
 * Lightweight reference counter stored at <root>/meta/ref_counts.json.
 * Tracks how often each node is accessed. Cold nodes (low ref count +
 * long since last read) are candidates for downgrade even before LRU
 * caps are hit.
 */
export class RefCountLedger {
  private path: string;
  private data: RefLedger;

  constructor(memoryRoot: string) {
    const metaDir = join(memoryRoot, "meta");
    if (!existsSync(metaDir)) mkdirSync(metaDir, { recursive: true });
    this.path = join(metaDir, "ref_counts.json");
    this.data = this.load();
  }

  private load(): RefLedger {
    if (!existsSync(this.path)) return { counts: {}, lastRead: {}, lastWrite: {} };
    try {
      return JSON.parse(readFileSync(this.path, "utf-8")) as RefLedger;
    } catch {
      return { counts: {}, lastRead: {}, lastWrite: {} };
    }
  }

  private save(): void {
    try {
      writeFileSync(this.path, JSON.stringify(this.data, null, 2), "utf-8");
    } catch { /* non-fatal */ }
  }

  /** Call this every time a node is read. */
  touch(fileName: string): void {
    this.data.counts[fileName]  = (this.data.counts[fileName]  ?? 0) + 1;
    this.data.lastRead[fileName] = Date.now();
    this.save();
  }

  /** Call this when a node is written/created. */
  written(fileName: string): void {
    this.data.lastWrite[fileName] = Date.now();
    if (!this.data.counts[fileName]) this.data.counts[fileName] = 0;
    this.save();
  }

  getCount(fileName: string): number {
    return this.data.counts[fileName] ?? 0;
  }

  daysSinceRead(fileName: string): number {
    const last = this.data.lastRead[fileName] ?? this.data.lastWrite[fileName] ?? 0;
    return (Date.now() - last) / (1000 * 60 * 60 * 24);
  }

  /**
   * Return files that are "cold" — never or rarely read, and old enough
   * to be considered for downgrade. Thresholds:
   *   - front:  refCount < 2  AND  daysSinceRead > 3
   *   - near:   refCount < 1  AND  daysSinceRead > 7
   */
  getColdNodes(zone: MemoryZoneRec, fileNames: string[]): string[] {
    const thresholds: Record<string, { minDays: number; maxRef: number }> = {
      front: { minDays: 3,  maxRef: 2 },
      near:  { minDays: 7,  maxRef: 1 },
      mid:   { minDays: 30, maxRef: 0 },
    };
    const t = thresholds[zone];
    if (!t) return [];
    return fileNames.filter(f =>
      this.getCount(f) <= t.maxRef &&
      this.daysSinceRead(f) >= t.minDays &&
      !f.startsWith(TOMBSTONE_PREFIX)
    );
  }
}

// ============================================================
// MARK: - MemoryEngine (Track B: LRU + layout)
// ============================================================

export class MemoryEngine {
  private root: string;
  private ledger: RefCountLedger;
  private decisions: DecisionLedger;

  constructor(root: string) {
    this.root      = root;
    this.ledger    = new RefCountLedger(root);
    this.decisions = new DecisionLedger(root);
    this.ensureStructure();
  }

  getRoot(): string { return this.root; }
  getLedger(): RefCountLedger { return this.ledger; }

  private ensureStructure(): void {
    for (const zone of ZONES) {
      const dir = join(this.root, zone);
      if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
    }
  }

  // MARK: - MVCC Lock Management

  private acquireLock(filePath: string): string | null {
    const lockPath = `${filePath}.lock`;
    const maxRetries = 5;
    let attempts = 0;

    while (attempts < maxRetries) {
      if (!existsSync(lockPath)) {
        try {
          writeFileSync(lockPath, Date.now().toString(), { flag: "wx" });
          return lockPath;
        } catch {
          // another process won the race
        }
      } else {
        try {
          const stats = statSync(lockPath);
          if (Date.now() - stats.mtimeMs > 10000) {
            unlinkSync(lockPath);
            continue;
          }
        } catch { /* ignore */ }
      }
      const wait = new Date().getTime() + 100;
      while (new Date().getTime() < wait) {}
      attempts++;
    }
    throw new Error(`LOCK_TIMEOUT: Could not acquire lock for ${filePath}`);
  }

  private releaseLock(lockPath: string): void {
    if (existsSync(lockPath)) {
      try { unlinkSync(lockPath); } catch { /* ignore */ }
    }
  }

  // MARK: - MVCC CRUD Operations

  list(zone?: string): MemoryEntry[] {
    const zones = zone ? [zone as MemoryZone] : ZONES;
    const entries: MemoryEntry[] = [];

    for (const z of zones) {
      const dir = join(this.root, z);
      if (!existsSync(dir)) continue;

      for (const file of readdirSync(dir)) {
        if (!file.endsWith(".md") && !file.endsWith(".jcross")) continue;
        const filePath = join(dir, file);
        const stat = statSync(filePath);

        entries.push({
          name: file.replace(/\.(md|jcross)$/, ""),
          zone: z,
          path: filePath,
          size: stat.size,
          modified: stat.mtime,
          version: stat.mtimeMs,
          frontmatter: this.parseFrontmatter(filePath),
        });
      }
    }
    return entries;
  }

  read(zone: string, name: string): ReadMemoryResult | null {
    const fileName = (name.endsWith(".md") || name.endsWith(".jcross")) ? name : `${name}.md`;
    const filePath = join(this.root, zone, fileName);

    if (!existsSync(filePath)) return null;

    const lockPath = this.acquireLock(filePath);
    try {
      const content = readFileSync(filePath, "utf-8");
      const version = statSync(filePath).mtimeMs;
      const frontmatter = this.parseFrontmatter(filePath);

      // Track A: increment reference count on every read
      this.ledger.touch(fileName);
      // Track B: update mtime to reset LRU timer
      this.touch(zone as MemoryZone, fileName);

      return { content, version, frontmatter };
    } finally {
      if (lockPath) this.releaseLock(lockPath);
    }
  }

  write(zone: MemoryZone, name: string, content: string, expectedVersion?: number): void {
    const fileName = (name.endsWith(".md") || name.endsWith(".jcross")) ? name : `${name}.md`;
    const filePath = join(this.root, zone, fileName);

    const lockPath = this.acquireLock(filePath);
    try {
      if (existsSync(filePath) && expectedVersion !== undefined) {
        const currentVersion = statSync(filePath).mtimeMs;
        if (currentVersion !== expectedVersion) {
          throw new Error(`STALE_MEMORY: Memory '${name}' was modified by another agent.`);
        }
      }
      writeFileSync(filePath, content, "utf-8");
      // Track A: record write timestamp
      this.ledger.written(fileName);
      // Track B: reset LRU mtime
      const time = new Date();
      import("fs").then(fs => fs.utimesSync(filePath, time, time));
    } finally {
      if (lockPath) this.releaseLock(lockPath);
    }
  }

  touch(zone: MemoryZone, name: string): void {
    const fileName = (name.endsWith(".md") || name.endsWith(".jcross")) ? name : `${name}.md`;
    const filePath = join(this.root, zone, fileName);
    if (existsSync(filePath)) {
      const time = new Date();
      import("fs").then(fs => fs.utimesSync(filePath, time, time)).catch(() => {});
    }
  }

  getOverflowCandidates(zone: MemoryZone, limit: number): string[] {
    const dir = join(this.root, zone);
    if (!existsSync(dir)) return [];

    const files = readdirSync(dir).filter(f => f.endsWith(".md") || f.endsWith(".jcross"));
    if (files.length <= limit) return [];

    const sorted = files.map(file => ({
      name: file,
      time: statSync(join(dir, file)).mtimeMs,
    })).sort((a, b) => a.time - b.time);

    const overflowCount = files.length - limit;
    return sorted.slice(0, overflowCount).map(f => f.name);
  }

  move(name: string, toZone: MemoryZone): boolean {
    for (const zone of ZONES) {
      const fileName = (name.endsWith(".md") || name.endsWith(".jcross")) ? name : `${name}.md`;
      const fromPath = join(this.root, zone, fileName);
      if (existsSync(fromPath)) {
        const toPath = join(this.root, toZone, fileName);
        const lockFrom = this.acquireLock(fromPath);
        const lockTo   = this.acquireLock(toPath);
        try {
          renameSync(fromPath, toPath);
        } finally {
          if (lockFrom) this.releaseLock(lockFrom);
          if (lockTo)   this.releaseLock(lockTo);
        }
        return true;
      }
    }
    return false;
  }

  delete(name: string): boolean {
    for (const zone of ZONES) {
      const fileName = (name.endsWith(".md") || name.endsWith(".jcross")) ? name : `${name}.md`;
      const filePath = join(this.root, zone, fileName);
      if (existsSync(filePath)) {
        const lockPath = this.acquireLock(filePath);
        try {
          unlinkSync(filePath);
        } finally {
          if (lockPath) this.releaseLock(lockPath);
        }
        return true;
      }
    }
    return false;
  }

  readSpatialIndex(): string | null {
    const indexPath = join(this.root, "SPATIAL_INDEX.jcross");
    if (!existsSync(indexPath)) return null;
    return readFileSync(indexPath, "utf-8");
  }

  writeSpatialIndex(content: string): void {
    const indexPath = join(this.root, "SPATIAL_INDEX.jcross");
    writeFileSync(indexPath, content, "utf-8");
  }

  listZones(): Record<string, number> {
    const result: Record<string, number> = {};
    for (const zone of ZONES) {
      const dir = join(this.root, zone);
      if (!existsSync(dir)) { result[zone] = 0; continue; }
      result[zone] = readdirSync(dir).filter(f => f.endsWith(".md") || f.endsWith(".jcross")).length;
    }
    return result;
  }

  getFrontMemories(): string {
    const frontDir = join(this.root, "front");
    if (!existsSync(frontDir)) return "";

    const files = readdirSync(frontDir)
      .filter(f => f.endsWith(".md") || f.endsWith(".jcross"))
      .sort((a, b) => {
        const priority: Record<string, number> = {
          "session_experience.md": 0,
          "active_context.md": 1,
          "design_decisions.md": 2,
        };
        return (priority[a] ?? 99) - (priority[b] ?? 99);
      });

    const sections: string[] = [];
    for (const file of files) {
      const filePath = join(frontDir, file);
      const lockPath = `${filePath}.lock`;
      if (!existsSync(lockPath)) {
        const content = readFileSync(filePath, "utf-8");
        const version = statSync(filePath).mtimeMs;
        sections.push(`--- ${file} (v: ${version}) ---\n${content}`);
      }
    }
    return sections.join("\n\n");
  }

  private parseFrontmatter(filePath: string): Record<string, string> | undefined {
    try {
      const content = readFileSync(filePath, "utf-8");
      const match = content.match(/^---\n([\s\S]*?)\n---/);
      if (!match) return undefined;

      const fm: Record<string, string> = {};
      for (const line of match[1].split("\n")) {
        const [key, ...rest] = line.split(":");
        if (key && rest.length) fm[key.trim()] = rest.join(":").trim();
      }
      return fm;
    } catch {
      return undefined;
    }
  }

  // MARK: - LRU GC: Tombstone

  /**
   * Write an ultra-low-resolution L1 tombstone into `fromZone` for `fileName`.
   * Contains ONLY the Kanji topology tags + destination pointer + timestamp.
   * Total size: typically < 250 bytes.
   */
  writeTombstone(fromZone: MemoryZone, fileName: string, toZone: MemoryZone): void {
    const filePath = join(this.root, fromZone, fileName);
    let kanjiTags = "[記:0.5] [標:0.5]";

    if (existsSync(filePath)) {
      try {
        const content = readFileSync(filePath, "utf-8");
        const m = content.match(/【空間座相】\s*\n([\s\S]*?)(?:\n【|\n■|$)/);
        if (m) kanjiTags = m[1].trim().slice(0, 120);
      } catch { /* use default */ }
    }

    const tombName    = `${TOMBSTONE_PREFIX}${fileName}`;
    const tombPath    = join(this.root, fromZone, tombName);
    const tombContent =
      `■ ${TOMBSTONE_PREFIX}${fileName}\n` +
      `【空間座相】\n${kanjiTags}\n\n` +
      `【EVICTED_TO】\n${toZone}/${fileName}\n\n` +
      `【EVICTED_AT】\n${new Date().toISOString()}\n`;

    try { writeFileSync(tombPath, tombContent, "utf-8"); } catch { /* non-fatal */ }
  }

  // MARK: - Dual-Track Autonomous GC

  /**
   * runAutonomousGc() — the dual-track GC engine.
   *
   * Track A (Rule classifier + ref-count):
   *   1. Scan zones for nodes whose content classifies to a LOWER zone
   *      (e.g., bench data in near/ → should be in deep/).
   *   2. Scan for "cold" nodes (low ref-count + days since read > threshold).
   *
   * Track B (LRU time-based, existing):
   *   3. For each zone over cap, evict oldest-mtime nodes to next zone.
   *
   * Both tracks write tombstones before moving. Returns a full report.
   */
  runAutonomousGc(caps: Record<string, number> = ZONE_CAPS): {
    classifier: { zone: string; file: string; to: string; reason: string }[];
    coldEvictions: { zone: string; file: string; to: string }[];
    lruEvictions: { zone: string; evicted: string[] }[];
  } {
    const report = {
      classifier:    [] as { zone: string; file: string; to: string; reason: string }[],
      coldEvictions: [] as { zone: string; file: string; to: string }[],
      lruEvictions:  [] as { zone: string; evicted: string[] }[],
    };

    const zoneCascade: Record<string, MemoryZone> = {
      front: "near", near: "mid", mid: "deep",
    };

    // --------------------------------------------------------
    // Track A-1: Content-based classifier
    // Checks every real (non-tombstone) node in front/near/mid.
    // If the classifier recommends a zone DEEPER than current → migrate.
    // --------------------------------------------------------
    const zoneOrder: MemoryZone[] = ["front", "near", "mid"];
    const zoneDepth: Record<string, number> = { front: 0, near: 1, mid: 2, deep: 3 };

    for (const zone of zoneOrder) {
      const dir = join(this.root, zone);
      if (!existsSync(dir)) continue;

      const files = readdirSync(dir).filter(
        f => (f.endsWith(".md") || f.endsWith(".jcross")) && !f.startsWith(TOMBSTONE_PREFIX)
      );

      for (const fileName of files) {
        try {
          const content = readFileSync(join(dir, fileName), "utf-8");
          const cls = classifyNode(content, fileName);
          if (zoneDepth[cls.zone] > zoneDepth[zone] && cls.confidence >= 0.8) {
            // Node belongs deeper — migrate it
            this.writeTombstone(zone as MemoryZone, fileName, cls.zone);
            this.move(fileName, cls.zone);
            report.classifier.push({
              zone, file: fileName, to: cls.zone, reason: cls.reason,
            });
          }
        } catch { /* skip unreadable nodes */ }
      }
    }

    // --------------------------------------------------------
    // Track A-2: Cold-node ref-count downgrade
    // Nodes that haven't been read in a while get pushed down.
    // --------------------------------------------------------
    for (const zone of zoneOrder) {
      const dir = join(this.root, zone);
      if (!existsSync(dir)) continue;

      const files = readdirSync(dir).filter(
        f => (f.endsWith(".md") || f.endsWith(".jcross")) && !f.startsWith(TOMBSTONE_PREFIX)
      );

      const coldFiles = this.ledger.getColdNodes(zone as MemoryZoneRec, files);
      const toZone = zoneCascade[zone];
      if (!toZone) continue;

      for (const fileName of coldFiles) {
        try {
          this.writeTombstone(zone as MemoryZone, fileName, toZone);
          this.move(fileName, toZone);
          report.coldEvictions.push({ zone, file: fileName, to: toZone });
          // Track C: record cold eviction
          this.decisions.record({
            ts: Date.now(), file: fileName, fromZone: zone, toZone,
            reason: "cold node (low ref-count + stale)", confidence: 0.7, track: "A-cold",
          });
        } catch { /* non-fatal */ }
      }
    }

    // --------------------------------------------------------
    // Track B: LRU cap-based eviction (existing logic)
    // --------------------------------------------------------
    const cascades: { from: MemoryZone; to: MemoryZone }[] = [
      { from: "front", to: "near" },
      { from: "near",  to: "mid"  },
      { from: "mid",   to: "deep" },
    ];

    for (const { from, to } of cascades) {
      const cap = caps[from] ?? Infinity;
      if (cap === Infinity) continue;

      const dir = join(this.root, from);
      if (!existsSync(dir)) continue;

      const allFiles = readdirSync(dir).filter(
        f => (f.endsWith(".md") || f.endsWith(".jcross")) && !f.startsWith(TOMBSTONE_PREFIX)
      );

      if (allFiles.length <= cap) continue;

      const sorted = allFiles
        .map(file => ({ name: file, time: statSync(join(dir, file)).mtimeMs }))
        .sort((a, b) => a.time - b.time);

      const toEvict = sorted.slice(0, allFiles.length - cap).map(f => f.name);
      const evicted: string[] = [];

      for (const fileName of toEvict) {
        try {
          this.writeTombstone(from, fileName, to);
          this.move(fileName, to);
          evicted.push(fileName);
          // Track C: record LRU eviction
          this.decisions.record({
            ts: Date.now(), file: fileName, fromZone: from, toZone: to,
            reason: "LRU cap overflow (oldest mtime)", confidence: 0.6, track: "B-lru",
          });
        } catch (e: any) {
          console.error(`[LRU GC] Eviction failed for ${fileName}: ${e.message}`);
        }
      }

      if (evicted.length > 0) report.lruEvictions.push({ zone: from, evicted });
    }

    // Track C: Update PROJECT_WISDOM every 50 decisions (or on first run)
    const allDecisions = this.decisions.readAll();
    if (allDecisions.length % 50 === 0 || allDecisions.length < 5) {
      try {
        const extractor = new PatternExtractor(this.decisions);
        const pattern   = extractor.extract();
        updateProjectWisdom(this.root, pattern);
        console.error(`  [Track C] PROJECT_WISDOM updated (${pattern.totalDecisions} decisions, ${pattern.rules.length} rules)`);
      } catch (e: any) {
        console.error(`  [Track C] wisdom update failed: ${e.message}`);
      }
    }

    return report;
  }

  /** Legacy alias kept for backward compat — delegates to runAutonomousGc(). */
  runLruGc(caps: Record<string, number> = ZONE_CAPS): { zone: string; evicted: string[] }[] {
    const r = this.runAutonomousGc(caps);
    return r.lruEvictions;
  }
}
