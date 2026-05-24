# Verantyx Cortex — Tri-Layer JCross Spatial Memory Engine

**Pure CPU, LLM-agnostic, persistent spatial memory for AI systems via Model Context Protocol (MCP).**

Verantyx Cortex resolves the fundamental constraint of LLM context windows. Instead of storing raw chat logs or relying on heavy embedding models, it compresses knowledge into a strict **3-Layer JCross format** and stores it permanently on disk. Any AI (Claude, Gemini, GPT, Cursor) can use it via MCP with zero configuration overhead.

The system's design goal: **a new LLM session started after a model switch should reach project-expert-level context within 5–7 tool calls, without any human prompting.**

---

## 🏗️ Architecture: Tri-Layer Spatial Memory

Each memory node (`.jcross` file) is structured in 3 resolutions, mirroring how human memory operates:

| Layer | Name | Description | Cost |
|-------|------|-------------|------|
| **L1** | Kanji Topology | Ultra-compressed spatial tags (`[標:1.0] [技:0.9]`) for instant O(1) scanning | Near-zero |
| **L1.5** | Index Line | 60-char compact summary: `[漢字] key entities` for bulk scan without loading L2/L3 | Near-zero |
| **L2** | Operational Logic | `OP.MAP` / `OP.FACT` / `OP.STATE` symbolic structures capturing intent and decisions | Low |
| **L3** | Raw Ground Truth | Verbatim original text. Only parsed for high-precision tasks | High (on-demand) |

This **variable-gear** design means:
- Routine tasks use only L1+L2 → zero context pollution, maximum speed
- Critical tasks fall back to L3 → full fidelity, no information loss

### Spatial Memory Zones

Memory nodes live in one of four physical directories, reflecting their current priority:

```
~/.openclaw/memory/
  front/   ← Active working memory (cap: 100 nodes)
  near/    ← User's own recent knowledge (cap: 1,000 nodes)
  mid/     ← User's own compressed/archived memories (cap: 5,000 nodes)
  deep/    ← External/benchmark data, cold storage (no cap)
  meta/
    decisions.jsonl   ← Decision ledger (Track C)
    ref_counts.json   ← Reference counter (Track A-2)

~/.openclaw/calibration/        ← ISOLATED — never pollutes main memory
  snapshot.json                 ← Non-destructive memory snapshot
  task_bank.jsonl               ← Accumulated meaningful calibration tasks
  sessions/cal_<timestamp>.md   ← Per-session calibration packets
  index.jcross                  ← Calibration session history
  config.json                   ← User's calibration command settings
```

> **Zone Semantics (non-negotiable):**  
> `mid/` is **only** for the user's own compressed memories — never external or benchmark data.  
> `BENCH_*` / `Session sharegpt_*` / `Session ultrachat_*` → always `deep/`, enforced automatically by `classifyNode()`.

---

## ⚙️ Triple-Track Autonomous GC

The memory system manages itself through three independent, parallel mechanisms:

### Track A-1: Content Classifier (`classifyNode`)
Runs **before every write**. Determines the correct zone from content fingerprints — no LLM call, < 1ms.

```
Priority (first match wins):
  1. BENCH_* / "Session sharegpt_*" → deep/   (conf: 0.95)
  2. OP.ENTITY("user_name") marker  → front/  (conf: 1.0)
  3. OP.STATE("current_*")          → front/  (conf: 0.9)
  4. [技|核] + code keywords         → near/   (conf: 0.8)
  5. [人|感|動] kanji                → near/   (conf: 0.75)
  6. JCROSS_GHOST / ARCHIVED        → mid/    (conf: 0.9)
  7. Default                         → near/
```

### Track A-2: Reference Count Ledger
Every `read()` increments a counter in `meta/ref_counts.json`.  
"Cold" nodes (low ref-count + stale mtime) cascade down autonomously:
- `front/`: 3 days, < 2 reads → demote to `near/`
- `near/`:  7 days, < 1 read  → demote to `mid/`

### Track B: LRU Time-Based Cap Eviction
When a zone exceeds its cap, the oldest-mtime nodes are pushed to the next zone.  
A **Tombstone** (`JCROSS_TOMB_<filename>`) is written in the source zone, preserving L1 Kanji topology so the node can be found instantly even after eviction.

### Track C: Contextual Intelligence Index (Decision Ledger)
Every GC decision (A-1, A-2, B) is appended to `meta/decisions.jsonl`.  
Every 50 decisions, `PatternExtractor` analyzes the ledger and updates `front/PROJECT_WISDOM.jcross`.

`PROJECT_WISDOM.jcross` is read by every new LLM session via `session_bootstrap()` — **making any blank-slate model perform like a project expert** without human prompting.

---

## 🔧 MCP Tools (v3.0 — 9 tools)

### Core Memory Operations

#### `compile_trilayer_memory`
Compiles a conversation or decision into a permanent JCross node.  
Now runs `classifyNode()` **before writing** — the node is placed in the correct zone immediately.

```json
{
  "kanjiTags": "[核:1.0] [技:0.9] [標:0.8]",
  "l1Summary": "Implemented triple-track autonomous GC.",
  "midResOperations": ["OP.FACT(\"current_phase\", \"Track C integration\")"],
  "rawText": "Full session context here..."
}
```

#### `scan_front_memory`
Returns all `front/` nodes as compact L1.5 index lines (≈ 60 chars each).

#### `memory_map`
Returns a global overview of all zones using L1.5 index. Minimal context cost.

#### `read_node`
Fetches a specific node by filename. Returns L2+L3 (or L1/L2/L3 selectively).  
Increments the reference counter automatically.

#### `semantic_op_search`
Searches L2 Operation Commands across all zones for named entities, facts, quantities.

#### `aggregate_memory_search`
Multi-node aggregation: retrieves and combines multiple nodes for cross-session analysis.

#### `migrate_memory_zone`
Manually moves a node between zones. Writes a tombstone in the source zone.

#### `spatial_cross_search`
L1 Kanji topology search using ARC-SGI Gravity Z-Depth algorithm.  
Input: `{"核": 1.0, "技": 0.9}` → returns nodes sorted by gravity score.

### Session Management Tools

#### `session_bootstrap`
**Call this first on every new session.**  
Returns: `project_wisdom` (zone rules + accumulated rules) + `user_profile` + `front_nodes` + zone counts.  
No file reads required — everything comes from MCP memory.

#### `recall_fact(key)`
Instant lookup of a specific profile key (e.g., `bench_score`, `current_objective`).

#### `store_fact(key, value)`
Persists a fact to `front/user_profile.jcross` immediately.

### GC & Calibration Tools

#### `run_lru_gc`
Triggers the full triple-track GC manually. Returns a detailed report:
- `classifier`: nodes reclassified by content fingerprint
- `coldEvictions`: nodes demoted by ref-count
- `lruEvictions`: nodes evicted by LRU cap

#### `generate_reimmersion_guide`
**The cognitive cold-start eliminator.**  
Generates a step-by-step protocol (7–9 steps) that brings a blank-slate LLM to project-expert state using only tool calls. Includes fictional review tasks pointing to real architecture files, Kanji search vectors, and a synthesis prompt.  
Saves `REIMMERSION_PROTOCOL.jcross` to `front/`.

---

## 🧰 Calibration CLI

The calibration system is **fully isolated** from the main memory (`~/.openclaw/calibration/` only).

### Setup (first time)

```bash
npm run setup
```

Interactive wizard:
1. Choose your **custom command name** (e.g., `cal`, `moto-cal`, `vera`)
2. Set project root
3. Register a **shell alias** in `~/.zshrc` / `~/.bashrc`
4. Run initial calibration

### Running Calibration

```bash
cal                  # Standard calibration packet (stdout)
cal --sync           # + update REIMMERSION_PROTOCOL.jcross
cal --output json    # JSON format
```

Or via npm:
```bash
npm run calibrate
npm run calibrate:sync
npm run calibrate:json
```

### What the Calibration Packet Contains

1. **First call**: `session_bootstrap()` — always
2. **User profile** from MCP memory
3. **Accumulated rules** from `decisions.jsonl` (e.g., `BENCH_* → deep/ conf=0.99, n=1166`)
4. **Memory-derived tasks** (Strategy A) — from real GC decisions and L1 summaries
5. **Git Diff reverse tasks** (Strategy B) — from past fix/bug commits, file paths auto-extracted
6. **L1.5 sampling tasks** (Strategy C) — daily-rotating node pairs for dependency exploration
7. **Architecture file tasks** — key files to read for code context
8. **Kanji search vectors** for `spatial_cross_search`
9. **Synthesis prompt** — what to internalize after completing the tasks

All tasks are **meaningful** because they draw from real session history, not generic file patterns.

---

## 📋 New Files (v3.0)

| File | Description |
|:-----|:------------|
| `src/memory/intelligence.ts` | Track C: `DecisionLedger`, `PatternExtractor`, `updateProjectWisdom()` |
| `src/memory/reimmersion.ts` | Cold-start eliminator: `generateReimmersionGuide()`, `writeReimmersionProtocol()` |
| `src/memory/calibration_store.ts` | Isolated calibration memory, three task-generation strategies |
| `src/cli/calibrate.ts` | Zero-cost calibration CLI with memory-aware task generation |
| `src/cli/setup.ts` | Interactive setup wizard — custom command name, shell alias registration |

### Modified Files (v3.0)

| File | Changes |
|:-----|:--------|
| `src/memory/engine.ts` | Full rewrite: `classifyNode()`, `RefCountLedger`, `runAutonomousGc()` (triple-track) |
| `src/memory/auto-selector.ts` | Wired `classifyNode()` pre-write + `runAutonomousGc()` post-write |
| `src/mcp/server.ts` | Added 5 new tools: `session_bootstrap`, `recall_fact`, `store_fact`, `run_lru_gc`, `generate_reimmersion_guide` |
| `package.json` | Added `setup`, `calibrate`, `calibrate:sync`, `calibrate:json` scripts |

---

## 🚀 Quick Start (New Session Protocol)

When starting a new session on an existing project:

```
1. session_bootstrap()              → PROJECT_WISDOM + user_profile
2. generate_reimmersion_guide()     → step-by-step re-immersion protocol
3. Follow the protocol steps:
   a. recall_fact("current_objective")
   b. recall_fact("bench_score")
   c. Read 4–5 architecture files (engine.ts, server.ts, intelligence.ts, ...)
   d. spatial_cross_search({"核": 1.0, "技": 0.9, "標": 0.8})
```

Or just run `cal` (after setup) from your terminal before switching to a new model.

---

## 📊 Performance History

| Version | Score | Method |
|---------|-------|--------|
| v1.0 (flash_agent) | 13.8% | Basic memory_map + retrieve |
| v3.0 (7-question test) | 85.7% | memory_map + read_node + semantic_op_search |
| Target | 85%+ | Full 500-question LongMemEval |

---

## 🗺️ Roadmap

- [ ] Full 500-question LongMemEval re-run with triple-track GC
- [ ] Kanji 18-dimension taxonomy documentation
- [ ] `mid/` sublimation: in-session LLM compression (no external API)
- [ ] Calibration feedback loop: task completion → DecisionLedger update
- [ ] iOS on-device inference integration (MLX-Swift / VerantyxMobileBench)
