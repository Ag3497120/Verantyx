# Verantyx Cortex — MCP Usage Guide

> Complete reference for all 19 MCP tools.  
> Every tool works directly from Claude Desktop, Cursor, and Antigravity — no terminal required.

---

## Table of Contents

1. [Core Concepts](#core-concepts)
2. [Session Protocol](#session-protocol)
3. [Tool Reference](#tool-reference)
   - [boot](#boot) — Start every session with this
   - [remember](#remember) — Save a memory
   - [recall](#recall) — Retrieve a fact instantly
   - [store](#store) — Write to user profile
   - [scan](#scan) — Scan active memory
   - [map](#map) — Overview of all zones
   - [read](#read) — Fetch a specific node
   - [search](#search) — Semantic keyword search
   - [aggregate](#aggregate) — Multi-node retrieval
   - [find](#find) — Kanji topology search
   - [move](#move) — Move a node between zones
   - [gc](#gc) — Run garbage collection
   - [guide](#guide) — Re-immersion protocol
   - [calibrate](#calibrate) — Calibration packet
   - [setup](#setup) — First-time setup
   - [evolve](#evolve) — Evolve character
   - [soul](#soul) — Show character profile
   - [rename_tool](#rename_tool) — Customize tool names
   - [list_aliases](#list_aliases) — Show all aliases
4. [Workflows](#workflows)
5. [Kanji Reference](#kanji-reference)
6. [Zone Rules](#zone-rules)
7. [Troubleshooting](#troubleshooting)

---

## Core Concepts

### Memory Zones

```
front/  ←  Active working memory      (cap: 100)
near/   ←  Your recent knowledge      (cap: 1,000)
mid/    ←  Your compressed memories   (cap: 5,000)
deep/   ←  External data, cold store  (no cap)
```

**Immutable rule:** `mid/` is yours only. Benchmark data, external datasets, and anything not directly authored by you always goes to `deep/`. The `classifyNode()` function enforces this automatically before every write.

### Tri-Layer JCross Format

Each node has three layers. You use whichever is appropriate:

```
L1    [核:1.0] [技:0.9] [標:0.8]      ← Kanji tags — O(1) scan
L1.5  "Implemented triple-track GC"   ← 60-char summary for bulk scan
L2    OP.FACT("key", "value")         ← Structured operations
L3    "Full verbatim text..."         ← Raw context, loaded on demand
```

### Tool Name Customization

All tools can be aliased to any name you prefer:

```
rename_tool({ from: "calibrate", to: "vera" })
```

See the [rename_tool](#rename_tool) section for full details.

---

## Session Protocol

### Standard — every new session or model switch

```
1.  boot()        ← Always first. Returns project state + user profile.
2.  guide()       ← Generates 7-9 step re-immersion protocol.
3.  calibrate()   ← Task packet with real context. Start working.
```

### Minimal — when you know the project well

```
1.  boot()
2.  recall("current_focus")
```

### Deep dive — when re-learning a specific subsystem

```
1.  boot()
2.  find({ 核: 1.0, 技: 0.9 })     ← Find architecture-related nodes
3.  read({ fileName: "TURN_xyz.jcross" })
4.  search({ queryText: "GC decision" })
```

---

## Tool Reference

---

### `boot`

**Call this first at the start of every session.** Returns your full project state — profile, project wisdom, active front nodes, zone counts, and active aliases.

**Parameters:** none

**Returns:**
- Zone counts across all four zones
- Character level (if evolved)
- User profile key-value pairs
- PROJECT_WISDOM accumulated rules (what the system has learned from past GC decisions)
- Active front nodes (L1.5 summaries)
- Current tool aliases

**Example:**

```
boot()
```

**Output:**

```
# Verantyx Boot
zone_counts: {"front":12,"near":847,"mid":2103,"deep":65}
character_level: Lv3 Developing

## User Profile
  user_name: motonishikoudai
  current_focus: triple-track GC testing
  main_project: verantyx-cortex

## Project Wisdom
  Rule: bench data → deep/ (confidence: 0.95, n=212)
  Rule: session turn → near/ (confidence: 0.88, n=341)

## Active Front Nodes
  SOUL.jcross: "[人:1.0] [技:1.0]..."
  PROJECT_WISDOM.jcross: "[核:1.0] [標:0.9]..."

## Tool Aliases
  vera → calibrate
  start → boot
```

---

### `remember`

Save a memory as a Tri-Layer JCross node. The `classifyNode()` function automatically determines the correct zone before writing.

**Parameters:**

| Parameter | Type | Required | Description |
|:---|:---|:---|:---|
| `kanjiTags` | string | ✅ | L1 Kanji topology. Example: `"[核:1.0] [技:0.9] [標:0.8]"` |
| `l1Summary` | string | ✅ | 1-2 sentence summary of the critical decision or state. |
| `midResOperations` | string[] | ✅ | L2 operation commands. Example: `["OP.FACT(\"key\", \"val\")"]` |
| `rawText` | string | ✅ | Complete verbatim L3 context to permanently store. |

**Kanji guidance:**

```
[核]  Core insight or fundamental design decision
[技]  Technical implementation detail
[標]  Goal, metric, or target
[人]  User-related, persona, or social context
[値]  Numerical data, benchmark results, measurements
[記]  Historical record, past event, previous decision
[構]  Architecture, structure, system design
[動]  Action taken, process executed, migration done
[認]  Pattern recognized, anomaly detected
```

**Example:**

```
remember({
  kanjiTags: "[核:1.0] [構:0.9] [技:0.8]",
  l1Summary: "Decided to implement three-zone GC with Tombstone tracking. Bench data excluded from mid/.",
  midResOperations: [
    "OP.STATE(\"gc_strategy\", \"triple-track-v3\")",
    "OP.FACT(\"tombstone_enabled\", \"true\")",
    "OP.ENTITY(\"affected_zones\", \"front,near,mid\")"
  ],
  rawText: "After testing, the correct architecture is: Track A-1 (classifier) runs before every write. Track A-2 (RefCountLedger) handles cold demotion. Track B (LRU) handles cap overflow with Tombstone residue. Benchmark data must never enter mid/ — classifyNode enforces this."
})
```

**Zone selection logic** (automatic, you don't control this):

```
Content suggests benchmarks/external → deep/
Content has profile markers          → front/
Content has [人|感|動] kanji          → near/
Default                              → near/
```

---

### `recall`

Instantly retrieve a single fact from `user_profile.jcross` by key. Much faster than semantic search for known keys.

**Parameters:**

| Parameter | Type | Required | Description |
|:---|:---|:---|:---|
| `key` | string | ✅ | The fact key to look up. |

**Common keys:**

| Key | Typical value |
|:---|:---|
| `user_name` | Your username |
| `current_focus` | What you're working on right now |
| `main_project` | Primary project name |
| `bench_score` | Latest benchmark score |
| `character_level` | Current character level |

**Example:**

```
recall({ key: "current_focus" })
→ "triple-track GC testing"

recall({ key: "bench_score" })
→ "85.7%"
```

---

### `store`

Write or update a single key-value fact in `user_profile.jcross`. Use this immediately when you learn something important that should survive the session.

**Parameters:**

| Parameter | Type | Required | Description |
|:---|:---|:---|:---|
| `key` | string | ✅ | Fact key (snake_case). |
| `value` | string | ✅ | Fact value. |

**Example:**

```
store({ key: "current_focus",  value: "LongMemEval 500-question run" })
store({ key: "bench_score",    value: "85.7%" })
store({ key: "main_project",   value: "verantyx-cortex" })
store({ key: "next_milestone", value: "full GC stress test" })
```

**When to call `store()`:**
- User mentions their current task or focus
- A benchmark result is achieved
- A key decision is made that should always be remembered
- Any fact that `boot()` should return next session

---

### `scan`

List all nodes in `front/` as compact L1.5 index lines. Use this to quickly see what's in active memory before deciding what to read.

**Parameters:** none

**Example:**

```
scan()
```

**Output:**

```
SOUL.jcross: [人:1.0][職:1.0][技:1.0] | "motonishikoudai — Lv3 Developing"
PROJECT_WISDOM.jcross: [核:1.0][標:0.9] | "Triple-track GC finalized v3.0"
REIMMERSION_PROTOCOL.jcross: [認:1.0][記:0.9] | "_verantyx-cortex project"
TURN_1744892040000.jcross: [技:0.9][構:0.8] | "Implemented classifyNode fingerprint"
user_profile.jcross: [人:1.0][記:0.9] | "User profile — motonishikoudai"
```

---

### `map`

Overview of one or more zones as L1.5 index lines. Use this when you need to survey a zone beyond `front/`.

**Parameters:**

| Parameter | Type | Required | Description |
|:---|:---|:---|:---|
| `zones` | string[] | ❌ | Zones to scan. Default: `["front"]`. |
| `maxNodes` | number | ❌ | Max nodes per zone. Default: 100. |
| `queryText` | string | ❌ | If provided, returns nodes sorted by relevance. |

**Example:**

```
map({ zones: ["front", "near"] })

map({ zones: ["near"], maxNodes: 20, queryText: "GC decision" })
```

---

### `read`

Fetch the full content of a specific JCross node by filename. The reference counter is incremented on each read (affects GC cold-demotion).

**Parameters:**

| Parameter | Type | Required | Description |
|:---|:---|:---|:---|
| `fileName` | string | ✅ | Exact filename (e.g., `"TURN_1744892040000.jcross"`). |
| `layer` | string | ❌ | Which layer to return. `"l1"`, `"l2"`, `"l3"`, or `"l2l3"` (default). |
| `zone` | string | ❌ | Zone hint to speed up lookup: `"front"`, `"near"`, `"mid"`, `"deep"`. |

**Example:**

```
read({ fileName: "SOUL.jcross", zone: "front" })

read({ fileName: "TURN_1744892040000.jcross", layer: "l2" })

read({ fileName: "PROJECT_WISDOM.jcross", layer: "l3" })
```

**Layer selection guide:**

| Layer | Use when | Cost |
|:---|:---|:---|
| `l1` | Only need kanji topology | Near zero |
| `l2` | Need structured facts/state | Low |
| `l3` | Need verbatim original context | High |
| `l2l3` | Deep reasoning required | High |

---

### `search`

Search L2 operation commands (`OP.FACT`, `OP.ENTITY`, `OP.STATE`) across all zones by keyword. Use this when you know what you're looking for conceptually.

**Parameters:**

| Parameter | Type | Required | Description |
|:---|:---|:---|:---|
| `queryText` | string | ✅ | Natural language keyword or phrase. |
| `topK` | number | ❌ | Max results. Default: 5. |
| `zonesHint` | string[] | ❌ | Limit search to specific zones. |

**Example:**

```
search({ queryText: "bench_score" })
search({ queryText: "user_name", zonesHint: ["front"] })
search({ queryText: "GC strategy", topK: 10 })
```

**When to use `search` vs `find`:**
- `search` → You have a keyword or fact key in mind
- `find` → You want nodes matching a conceptual topic via Kanji

---

### `aggregate`

Retrieve multiple nodes that match a query and return their combined content. Use for questions like "collect all GC-related decisions" or "show everything about the benchmark runs."

**Parameters:**

| Parameter | Type | Required | Description |
|:---|:---|:---|:---|
| `queryText` | string | ✅ | What to aggregate across. |
| `topK` | number | ❌ | Number of nodes to retrieve. Default: 5, max: 10. |
| `zonesHint` | string[] | ❌ | Narrow to specific zones. |

**Example:**

```
aggregate({ queryText: "benchmark results", topK: 5 })
aggregate({ queryText: "architecture decision", zonesHint: ["near", "mid"] })
```

---

### `find`

ARC-SGI Gravity Z-Depth Kanji topology search across all zones. Scores nodes by how closely their L1 kanji vector matches your query vector. Best for conceptual or topic-level retrieval.

**Parameters:**

| Parameter | Type | Required | Description |
|:---|:---|:---|:---|
| `queryKanji` | object | ✅ | Search vector as kanji → weight pairs. |

**Example:**

```
find({ queryKanji: { "核": 1.0, "技": 0.9 } })     // architecture + implementation
find({ queryKanji: { "標": 1.0, "値": 0.9 } })     // goals + metrics
find({ queryKanji: { "人": 1.0, "職": 0.8 } })     // user + craft
find({ queryKanji: { "記": 1.0, "構": 0.8 } })     // history + structure
```

**Output:**

```
[near/TURN_1744892040000.jcross] score=1.83
  "Implemented triple-track GC with classifyNode pre-write check"

[near/TURN_1744901234000.jcross] score=1.52
  "Refactored LRU eviction to write Tombstone residue on demotion"
```

**Common search vectors:**

| Topic | Vector |
|:---|:---|
| Core architecture | `{ 核: 1.0, 構: 0.9, 技: 0.8 }` |
| Project goals/metrics | `{ 標: 1.0, 値: 0.9 }` |
| User profile/persona | `{ 人: 1.0, 職: 0.8, 感: 0.7 }` |
| Benchmark/historical | `{ 値: 1.0, 記: 0.9 }` |
| Decisions made | `{ 核: 1.0, 動: 0.9 }` |
| Pattern recognition | `{ 認: 1.0, 核: 0.8 }` |

---

### `move`

Manually move a node from one zone to another. A Tombstone label is written in the source zone so the node remains discoverable via L1 scan even after it's gone.

**Parameters:**

| Parameter | Type | Required | Description |
|:---|:---|:---|:---|
| `fileName` | string | ✅ | Exact filename to move. |
| `targetZone` | string | ✅ | Destination: `"front"`, `"near"`, `"mid"`, or `"deep"`. |

**Example:**

```
move({ fileName: "BENCH_result_v7.jcross", targetZone: "deep" })
move({ fileName: "TURN_1234.jcross",       targetZone: "mid" })
move({ fileName: "PROJECT_SEED.jcross",    targetZone: "front" })
```

**When to call `move()` manually:**
- You see a benchmark file in `near/` or `mid/` — send it to `deep/`
- You have a node that should always be visible — promote it to `front/`
- `scan()` reveals clutter in `front/` that belongs further back

---

### `gc`

Manually trigger the full Triple-Track Autonomous GC pipeline. Normally runs in the background every 10 minutes — call this when you need an immediate pass.

**Parameters:**

| Parameter | Type | Required | Description |
|:---|:---|:---|:---|
| `front_cap` | number | ❌ | Override front/ cap. Default: 100. |
| `near_cap` | number | ❌ | Override near/ cap. Default: 1,000. |
| `mid_cap` | number | ❌ | Override mid/ cap. Default: 5,000. |

**Example:**

```
gc()

gc({ front_cap: 50 })    // aggressively clean front/
```

**What GC does:**

1. **Track A-1 (Classifier):** Scans all nodes and reclassifies any that are in the wrong zone.
2. **Track A-2 (RefCountLedger):** Demotes cold nodes (low reads + old mtime).
3. **Track B (LRU):** Evicts oldest nodes from any zone exceeding its cap, writing Tombstones.
4. **Track C (DecisionLedger):** Logs the decision. Every 50 decisions, updates `PROJECT_WISDOM.jcross`.

---

### `guide`

Generates a complete re-immersion protocol: a step-by-step sequence of MCP calls that rebuilds expert project context in under 10 tool calls. Writes `REIMMERSION_PROTOCOL.jcross` to `front/`.

**Parameters:**

| Parameter | Type | Required | Description |
|:---|:---|:---|:---|
| `project_root` | string | ❌ | Absolute path to project root. Auto-detected by default. |

**Example:**

```
guide()
guide({ project_root: "/Users/yourname/verantyx-cli" })
```

**Output structure:**

```
# Verantyx Re-Immersion Protocol
Total steps: 8 | Cost: medium

## Steps
### Step 1 🟢 [scan] [核][技]
Action: Call scan() to see the full active front/ index
Why: Establishes baseline of what's currently loaded
You gain: Full list of active nodes and their Kanji signatures

### Step 2 🟡 [find] [構][核]
Action: Call find({ 核: 1.0, 構: 0.9 })
Why: Retrieve architecture-related decisions from all zones
You gain: Core design decisions made in previous sessions
...

## Kanji Vectors
  vector_1: {"核": 1.0, "技": 0.9}
  vector_2: {"標": 1.0, "値": 0.8}

## Synthesis
Call recall("current_focus") → recall("main_project") → you now know
everything needed to continue as-if you never lost context.
```

---

### `calibrate`

Generates a full calibration packet using three strategies that are completely isolated from main memory. No writes. No pollution. Run this after `boot()` + `guide()` to get meaningful review tasks generated from real project data.

**Parameters:**

| Parameter | Type | Required | Description |
|:---|:---|:---|:---|
| `output_format` | string | ❌ | `"text"` (default) or `"json"`. |
| `project_root` | string | ❌ | Project root path. Auto-detected from `config.json`. |

**Example:**

```
calibrate()
calibrate({ output_format: "json" })
```

### Three task generation strategies

**Strategy A — Memory-derived tasks**  
Reads real accumulated decisions, L1 summaries, and zone health metrics. Produces tasks like:

```
### Task 1 🔴 [memory]
Task: review the GC classifier logic in engine.ts — a past decision 
      flagged a edge case for session data with [記] kanji.
Read: `/Users/.../src/memory/engine.ts`
Context: 3 recorded decisions pointed here with confidence 0.88
```

**Strategy B — Git Diff reverse engineering**  
Parses git history for `fix:` and `bug:` commits. Presents already-solved bugs as fictional review tasks. File paths extracted automatically — the model is forced to read real code.

```
### Task 2 🟡 [git-diff]
Task: check if the Tombstone write on zone eviction handles the edge case
      where the source file is locked by another process.
Read: `/Users/.../src/memory/engine.ts` (line ~471)
Context: fix commit bf3a219: "fix MVCC lock timeout on Tombstone write"
```

**Strategy C — L1.5 Random sampling**  
Daily-rotating sample of 2-3 real JCross nodes. Auto-generates dependency exploration tasks.

```
### Task 3 🟢 [l1.5-sample]
Task: investigate the relationship between TURN_1744892040000.jcross [核][構]
      and TURN_1744901234000.jcross [技][動] — how do their decisions interact?
Context: Sampled from near/ L1.5 index
```

---

### `setup`

First-time configuration. Writes `~/.verantyx/calibration/config.json`, updates `REIMMERSION_PROTOCOL.jcross`, and returns the one-line shell alias to add. **No terminal required.**

**Parameters:**

| Parameter | Type | Required | Description |
|:---|:---|:---|:---|
| `command_name` | string | ❌ | Shell alias name. Default: `"cal"` |
| `project_root` | string | ❌ | Project root path. Auto-detected. |
| `shell_rc` | string | ❌ | Shell config file. Auto-detected (`~/.zshrc` or `~/.bashrc`). |

**Example:**

```
setup({ command_name: "vera" })
setup({ command_name: "moto-cal", project_root: "/Users/yourname/verantyx-cli" })
```

**Output:**

```
# ✅ Setup Complete
command_name: vera
project_root: /Users/yourname/verantyx-cli
shell_rc:     /Users/yourname/.zshrc

## Add to shell RC (one-time)
```bash
# verantyx-calibrate: vera
alias vera='node --import tsx /path/to/calibrate.ts'
```

## From now on
  Terminal: `vera`
  MCP tool: `calibrate()` ← no terminal needed
```

---

### `evolve`

Synthesizes your character from accumulated memory patterns and saves it as `SOUL.jcross` in `front/`. Call this after accumulating significant new memories to see how your character has grown.

**Parameters:** none

**Character synthesis sources:**
- Kanji frequency across all zones (which dimensions dominate your thinking)
- Decision patterns from `decisions.jsonl` (what kind of choices you make)
- L1 summary linguistic patterns (how you describe things)
- Zone distribution (how organized your memory structure is)

**XP formula:**
```
XP = (front_count + near_count + mid_count) + (total_decisions / 10)
```

**Example:**

```
evolve()
```

**Output:**

```
# ⭐ Character Evolved
Level: Lv.3 Developing  [███░░]
XP: 120 | Wisdom: 100.0%

## Traits
  • Technical Precision — obsesses over correct implementation
  • Empathic Connector — never loses the human perspective
  • Strategic Visionary — thinks backwards from the goal

## Signature
  「外部データと自分の記憶は截然と分けよ。mid/はあなた自身のためだけにある。」
  「MCPを信頼せよ。コンテキストウィンドウは幻だ。」

Next level in 80 XP
✅ SOUL.jcross → front/
```

---

### `soul`

Read and display the current character profile from `SOUL.jcross`. Call `evolve()` first if no character exists.

**Parameters:** none

**Example:**
```
soul()
```

---

### `rename_tool`

Register a persistent alias for any tool. Aliases are saved to `~/.verantyx/calibration/tool_aliases.json` and survive model switches, restarts, and new sessions.

**Parameters:**

| Parameter | Type | Required | Description |
|:---|:---|:---|:---|
| `from` | string | ✅ | Original tool name or existing alias. |
| `to` | string | ✅ | New alias name. Alphanumeric, hyphens, underscores. |

**Example:**

```
rename_tool({ from: "calibrate", to: "vera" })
→ ✅ Alias: vera → calibrate

rename_tool({ from: "boot",     to: "start" })
rename_tool({ from: "remember", to: "mem"   })
rename_tool({ from: "find",     to: "seek"  })
```

**Chain resolution is supported:**

```
rename_tool({ from: "calibrate", to: "c" })
rename_tool({ from: "c",         to: "v" })
// v → c → calibrate  (all work)
```

**How to use from a chat interface:**

You can ask the LLM in plain language:

```
"Make 'boot' callable as 'start'"
"Rename calibrate to vera"
"Call remember 'mem' from now on"
"I want to type 'v' to run calibrate"
```

The LLM will call `rename_tool()` on your behalf.

**Aliases appear:**
- In `boot()` output (always visible at session start)
- In `calibrate()` output
- In `list_aliases()` output
- In the tool list itself (aliased tools show up as separate entries)

---

### `list_aliases`

Show all active tool aliases and the full list of core tool names.

**Parameters:** none

**Example:**

```
list_aliases()
```

**Output:**

```
# Tool Aliases
  vera → calibrate
  start → boot
  mem → remember

Core tools:
  remember  scan  map  read  search  aggregate  find
  move  boot  recall  store  gc  guide  evolve  soul
  setup  calibrate  rename_tool  list_aliases
```

---

## Workflows

### Workflow 1: New session after model switch

```
boot()
  → reads project_wisdom + user_profile + front nodes + aliases

guide()
  → generates 8-step re-immersion protocol
  → follow the steps sequentially

calibrate()
  → generates review tasks from real memory
  → read the flagged files
  → you now have full expert context
```

**Total cost: 3 tool calls, ~1 minute.**

---

### Workflow 2: Save important context mid-session

When something important happens that you never want to forget:

```
remember({
  kanjiTags: "[核:1.0] [動:0.9]",
  l1Summary: "Decided to move all benchmark JSON to deep/ after GC audit.",
  midResOperations: [
    "OP.STATE(\"bench_data_policy\", \"always-deep\")",
    "OP.FACT(\"gc_audit_date\", \"2026-04-19\")"
  ],
  rawText: "After scanning near/ we found 47 benchmark result files incorrectly classified. Moved them all to deep/ using move(). Added this as an invariant rule: bench data always goes to deep/, classifyNode now enforces this."
})

store({ key: "current_focus", value: "GC audit complete, starting LongMemEval run" })
```

---

### Workflow 3: Finding a specific past decision

```
// Option A: You know a keyword
search({ queryText: "classifyNode fingerprint" })

// Option B: You know the topic area
find({ queryKanji: { "核": 1.0, "構": 0.9 } })

// Option C: Broad survey
map({ zones: ["near"], queryText: "GC" })

// Then load the node
read({ fileName: "TURN_1744892040000.jcross", layer: "l2l3" })
```

---

### Workflow 4: Manual zone cleanup

```
// See what's in front/
scan()

// Check near/ for misclassified files
map({ zones: ["near"], maxNodes: 30 })

// Move any benchmark files to deep/
move({ fileName: "BENCH_session_result.jcross", targetZone: "deep" })

// Run GC to catch the rest
gc()
```

---

### Workflow 5: Customize your tool names (one-time)

```
// Give all your tools personal names
rename_tool({ from: "boot",      to: "start" })
rename_tool({ from: "calibrate", to: "vera"  })
rename_tool({ from: "remember",  to: "mem"   })
rename_tool({ from: "find",      to: "seek"  })
rename_tool({ from: "evolve",    to: "grow"  })

// Verify
list_aliases()

// From now on, just say:
start()
vera()
mem({ kanjiTags: "...", ... })
seek({ queryKanji: { 核: 1.0 } })
grow()
```

---

### Workflow 6: Character growth check

```
// See who you are right now
soul()

// After a productive session, grow
remember({ ... })  // session memories
evolve()           // synthesize new character from all memories

// Check what changed
soul()
```

---

## Kanji Reference

| Kanji | Dimension | Use this for |
|:---:|:---|:---|
| `核` | Core Synthesizer | Fundamental insights, core decisions |
| `技` | Technical Precision | Implementation details, code, APIs |
| `人` | Empathic Connector | User profile, social context, relationships |
| `値` | Data Architect | Metrics, numbers, benchmark results |
| `動` | Action Driver | Actions taken, migrations, changes made |
| `感` | Intuitive Reader | Intuitions, emotional context, gut feelings |
| `認` | Pattern Weaver | Patterns found, anomalies, recognitions |
| `標` | Strategic Visionary | Goals, targets, milestones, objectives |
| `記` | Memory Keeper | Historical records, past events |
| `構` | Systems Builder | System architecture, structural decisions |
| `通` | Bridge Maker | Integrations, connections between systems |
| `職` | Craft Master | Professional craft, expertise, quality |

### Kanji Weight Guidelines

```
1.0  ← Primary dimension — the main point of this memory
0.9  ← Strong secondary dimension
0.8  ← Clear supporting dimension
0.5  ← Mild relevance
```

**Examples:**

```
Bug fix:          [技:1.0] [動:0.9]
Architecture doc: [核:1.0] [構:0.9] [標:0.8]
Benchmark run:    [値:1.0] [標:0.9] [記:0.8]
User preference:  [人:1.0] [感:0.8]
GC decision:      [核:1.0] [動:0.9] [記:0.8]
Integration work: [通:1.0] [技:0.9] [構:0.8]
```

---

## Zone Rules

### When does a node go to each zone?

| Zone | Auto-assigned when |
|:---|:---|
| `front/` | User profile, current objectives, `OP.STATE("current_*")`, character (SOUL) |
| `near/` | General working memory, technical content, session turns (default) |
| `mid/` | Compressed user memories, older context |
| `deep/` | **Any** benchmark data, external datasets, session files with `sharegpt_` prefix |

### Tombstones

When a node is evicted from a zone (by LRU cap overflow), a Tombstone is written:

```
JCROSS_TOMB_TURN_1744892040000.jcross
```

The tombstone contains:
- The original L1 Kanji tags
- Where the node was moved to
- The timestamp of eviction

This means you can always `scan()` or `find()` to discover evicted nodes, then use `read()` with `zone: "deep"` (or wherever it was sent) to retrieve the full content.

---

## Troubleshooting

### `boot()` shows empty profile

```
store({ key: "user_name", value: "yourname" })
store({ key: "main_project", value: "verantyx-cortex" })
store({ key: "current_focus", value: "what you are working on" })
```

Then call `boot()` again.

---

### `read()` says file not found

The node may have been evicted. Try:

```
// Search for it
search({ queryText: "key phrase from that memory" })

// Or check tombstone residue
scan()    // Tombstones appear as JCROSS_TOMB_* files
map({ zones: ["near", "mid", "deep"] })
```

---

### Memory keeps filling after GC

If `scan()` shows `front/` always near 100 nodes:

```
// Force aggressive GC with lower cap
gc({ front_cap: 50 })

// Or manually move things out
move({ fileName: "OLD_BENCH_result.jcross", targetZone: "deep" })
```

---

### `calibrate()` returns no tasks

Tasks accumulate over sessions. After a few `remember()` calls and model switches, tasks will appear. Initially you'll only see the Kanji search vectors and synthesis rules.

---

### Tool alias not working

```
// Check the alias was registered
list_aliases()

// Re-register if missing
rename_tool({ from: "calibrate", to: "vera" })
```

If the alias file was deleted, re-register all aliases. They're stored at:
```
~/.verantyx/calibration/tool_aliases.json
```

---

### SOUL.jcross not found

```
// Generate character first
evolve()

// Then display
soul()
```

---

*Verantyx Cortex v3.1 — MCP Usage Guide*
