import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import { compileTriLayerJCross } from "../memory/auto-selector.js";
import path from "path";
import fs from "fs";

// The MCP Server definition
const server = new Server(
    {
        name: "verantyx-trilayer-memory",
        version: "1.0.0",
    },
    {
        capabilities: {
            tools: {}
        }
    }
);

const ENGINE_ROOT = path.resolve(process.env.HOME || "~", ".openclaw/memory");

server.setRequestHandler(ListToolsRequestSchema, async () => {
    return {
        tools: [
            {
                name: "compile_trilayer_memory",
                description: "Directly compile a 3-Layer JCross Memory node into the Front drive using Main LLM symbolic extraction (no local SLM).",
                inputSchema: {
                    type: "object",
                    properties: {
                        kanjiTags: {
                            type: "string",
                            description: "Layer 1 Topology: A string defining Spatial Kanji tags and weights. Example: '[標: 指示] [認: 1.0] [視: 0.8]'"
                        },
                        l1Summary: {
                            type: "string",
                            description: "Layer 1 Summary: A concise 1-2 sentence description of the critical decision or system state."
                        },
                        midResOperations: {
                            type: "array",
                            items: { type: "string" },
                            description: "Layer 2 Logic: A list of operation strings like 'OP.MAP_STATE(\"Agent Loop Phase\", \"[状態: 最終回答]\")' or 'OP.MAP(\"Concept\", \"[概念: X]\")'."
                        },
                        rawText: {
                            type: "string",
                            description: "Layer 3 Raw Text: A complete verbatim copy or deep description of the context/conversation to permanently store."
                        }
                    },
                    required: ["kanjiTags", "l1Summary", "midResOperations", "rawText"]
                }
            },
            {
                name: "scan_front_memory",
                description: "Quickly scan the metadata (Kanji Tags) of all JCross nodes in the front memory drive.",
                inputSchema: {
                    type: "object",
                    properties: {}
                }
            },
            {
                name: "evolve_character",
                description: "MCP使用の蓄積から知性キャラクターを育成・進化させます。漢字トポロジー頻度・意思決定パターン・L1サマリーから性格・価値観・口調を抽出し、SOUL.jcrossとしてfront/に保存します。使うほど成長します。",
                inputSchema: { type: "object", properties: {} }
            },
            {
                name: "get_character",
                description: "現在のキャラクタープロファイル（SOUL.jcross）を読み込んで表示します。evolve_characterを先に呼ぶ必要があります。",
                inputSchema: { type: "object", properties: {} }
            },
            {
                name: "migrate_memory_zone",
                description: "Safely and atomically move a memory node (e.g., tracking a completed task) from one spatial zone to another to establish active working memory Garbage Collection.",
                inputSchema: {
                    type: "object",
                    properties: {
                        fileName: {
                            type: "string",
                            description: "The name of the memory file to migrate (e.g., 'TURN_1234.jcross')."
                        },
                        targetZone: {
                            type: "string",
                            description: "The destination zone ('near', 'mid', or 'deep').",
                            enum: ["front", "near", "mid", "deep"]
                        }
                    },
                    required: ["fileName", "targetZone"]
                }
            },
            {
                name: "spatial_cross_search",
                description: "Utilizes the ARC-SGI Gravity Z-Depth algorithm to perform associative memory retrieval. Pulls dormant cross-spatial memory nodes representing similar architectural intent into the active context layer instantly.",
                inputSchema: {
                    type: "object",
                    properties: {
                        queryKanji: {
                            type: "object",
                            description: "A dictionary representing the search vector for Kanji Topology. Example: {'標': 1.0, '認': 0.8}",
                            additionalProperties: { type: "number" }
                        }
                    },
                    required: ["queryKanji"]
                }
            },
            {
                name: "run_lru_gc",
                description: "Manually trigger a full LRU cascade GC pass. Evicts least-recently-used nodes from each zone when it exceeds its cap, writing an ultra-low-resolution L1 Kanji tombstone label in the source zone so agents can still discover what was moved and where. Returns the eviction report.",
                inputSchema: {
                    type: "object",
                    properties: {
                        front_cap: { type: "number", description: "Override cap for front/ zone (default 100)." },
                        near_cap:  { type: "number", description: "Override cap for near/ zone (default 1000)." },
                        mid_cap:   { type: "number", description: "Override cap for mid/ zone (default 5000)." }
                    }
                }
            },
            {
                name: "session_bootstrap",
                description: "CALL THIS FIRST AT THE START OF EVERY SESSION. Reads all front/ nodes and returns a structured JSON summary of the user profile, current objectives, and recent context. This replaces the model's context window as the source of truth.",
                inputSchema: { type: "object", properties: {} }
            },
            {
                name: "recall_fact",
                description: "Instantly retrieve a specific fact from the user profile by key (e.g. 'user_name', 'current_focus', 'bench_score'). Returns the raw value string. Much faster than semantic search for known keys.",
                inputSchema: {
                    type: "object",
                    properties: {
                        key: { type: "string", description: "The fact key to look up (e.g. 'user_name', 'project_main', 'bench_score')." }
                    },
                    required: ["key"]
                }
            },
            {
                name: "generate_reimmersion_guide",
                description: "CALL THIS ON ANY NEW SESSION after session_bootstrap(). Returns a step-by-step protocol to rebuild full project context in 5-7 tool calls. Provides fictional review tasks pointing to real architecture files, Kanji search vectors, and a synthesis prompt. Following this guide makes a blank-slate model perform like a project expert within minutes — without any human prompting.",
                inputSchema: {
                    type: "object",
                    properties: {
                        project_root: { type: "string", description: "Absolute path to the verantyx-cli project root. Default: auto-detected." }
                    }
                }
            },
            {
                name: "store_fact",
                description: "Write or update a single key-value fact in the user profile (front/user_profile.jcross). Use this IMMEDIATELY when you learn something important about the user that should survive beyond this session.",
                inputSchema: {
                    type: "object",
                    properties: {
                        key:   { type: "string", description: "Fact key (snake_case, e.g. 'favorite_language')." },
                        value: { type: "string", description: "Fact value." }
                    },
                    required: ["key", "value"]
                }
            },
            {
                name: "setup_calibration",
                description: [
                    "【初回セットアップ】キャリブレーションシステムを設定します。",
                    "ターミナル不要 — Claude Desktop / Cursor / Antigravity から直接呼び出せます。",
                    "実行すると: (1) ~/.openclaw/calibration/config.json を書き込む",
                    "(2) ~/.zshrc に指定コマンド名のエイリアスを追加する指示を返す",
                    "(3) REIMMERSION_PROTOCOL.jcross を更新する",
                    "引数なしで呼ぶとデフォルト設定 (command_name='cal') で動作します。"
                ].join(" "),
                inputSchema: {
                    type: "object",
                    properties: {
                        command_name: {
                            type: "string",
                            description: "シェルに登録するコマンド名 (例: 'cal', 'vera', 'moto-cal')。デフォルト: 'cal'"
                        },
                        project_root: {
                            type: "string",
                            description: "プロジェクトルートの絶対パス。デフォルト: 自動検出"
                        },
                        shell_rc: {
                            type: "string",
                            description: "シェル設定ファイル (例: '~/.zshrc')。デフォルト: 自動検出"
                        }
                    }
                }
            },
            {
                name: "run_calibration",
                description: [
                    "【キャリブレーション実行】モデル切り替え時やセッション再開時に呼び出します。",
                    "ターミナル不要 — MCP ツールとして完結します。",
                    "三つの戦略でタスクを生成: (A) 記憶由来, (B) Git Diff逆算, (C) L1.5ランダムサンプリング。",
                    "出力をそのまま読むことで直前の会話コンテキストを数分で再構築できます。"
                ].join(" "),
                inputSchema: {
                    type: "object",
                    properties: {
                        output_format: {
                            type: "string",
                            enum: ["text", "json"],
                            description: "出力フォーマット。デフォルト: text"
                        },
                        project_root: {
                            type: "string",
                            description: "プロジェクトルートの絶対パス。省略時は自動検出。"
                        }
                    }
                }
            }
        ]
    };
});

server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const { name, arguments: args } = request.params;

    if (name === "compile_trilayer_memory") {
        const { kanjiTags, l1Summary, midResOperations, rawText } = args as any;
        
        try {
            await compileTriLayerJCross({ kanjiTags, l1Summary, midResOperations, rawText }, ENGINE_ROOT);
            return {
                content: [{ type: "text", text: "Successfully Compiled Pure CPU Symbolic Memory to JCross Drive." }]
            };
        } catch (e: any) {
            return {
                isError: true,
                content: [{ type: "text", text: `Failed to compile memory: ${e.message}` }]
            };
        }
    }
    
    if (name === "scan_front_memory") {
        try {
            const frontDir = path.join(ENGINE_ROOT, "front");
            if (!fs.existsSync(frontDir)) {
                return { content: [{ type: "text", text: "Front memory empty." }] };
            }
            
            const files = fs.readdirSync(frontDir).filter(f => f.endsWith(".jcross"));
            let summaries = [];
            for (const f of files) {
                const content = fs.readFileSync(path.join(frontDir, f), "utf-8");
                const phaseMatch = content.match(/【位相対応表】([\s\S]*?)【操作対応表】/);
                if (phaseMatch) {
                    summaries.push(`[File: ${f}]\n${phaseMatch[1].trim()}`);
                }
            }
            return {
                content: [{ type: "text", text: summaries.length > 0 ? summaries.join("\n\n") : "No Kanji topology found." }]
            };
        } catch (e: any) {
            return {
                 isError: true,
                 content: [{ type: "text", text: `Error reading memory: ${e.message}` }]
            };
        }
    }

    if (name === "migrate_memory_zone") {
        const { fileName, targetZone } = args as any;
        try {
            const { MemoryEngine } = await import("../memory/engine.js");
            const engine = new MemoryEngine(ENGINE_ROOT);
            const success = engine.move(fileName, targetZone);
            if (success) {
                return { content: [{ type: "text", text: `Successfully migrated ${fileName} to ${targetZone}/ zone.` }] };
            } else {
                return { isError: true, content: [{ type: "text", text: `Failed to find ${fileName} in any zone to migrate.` }] };
            }
        } catch (e: any) {
            return {
                isError: true,
                content: [{ type: "text", text: `Migration error: ${e.message}` }]
            };
        }
    }

    if (name === "spatial_cross_search") {
        const { queryKanji } = args as any;
        try {
            const { GravitySolver } = await import("../memory/spatial_search.js");
            const solver = new GravitySolver(ENGINE_ROOT);
            const surfaced = solver.triggerFlashback(queryKanji);
            const details = solver.getSurfacedNodeDetails(surfaced);
            
            return {
                content: [{ type: "text", text: details.trim() || "No correlating Kanji structures found in Deep Memory." }]
            };
        } catch (e: any) {
            return {
                isError: true,
                content: [{ type: "text", text: `Gravity Search error: ${e.message}` }]
            };
        }
    }

    if (name === "run_lru_gc") {
        const { front_cap, near_cap, mid_cap } = (args ?? {}) as any;
        try {
            const { MemoryEngine, ZONE_CAPS } = await import("../memory/engine.js");
            const engine = new MemoryEngine(ENGINE_ROOT);
            const caps = {
                ...ZONE_CAPS,
                ...(front_cap !== undefined ? { front: front_cap } : {}),
                ...(near_cap  !== undefined ? { near:  near_cap  } : {}),
                ...(mid_cap   !== undefined ? { mid:   mid_cap   } : {}),
            };
            // Track C: also update PROJECT_WISDOM after manual GC
            const { DecisionLedger, PatternExtractor, updateProjectWisdom } = await import("../memory/intelligence.js");
            const report = engine.runAutonomousGc();
            const totalC   = report.classifier.length;
            const totalCold= report.coldEvictions.length;
            const totalLru = report.lruEvictions.reduce((s: number, r: {evicted:string[]}) => s + r.evicted.length, 0);
            const total = totalC + totalCold + totalLru;
            const lines: string[] = [
                `✅ Autonomous GC complete. Total movements: ${total}`,
                totalC > 0    ? `  [Classifier] ${totalC} misplaced node(s) moved to correct zone:` : "",
                ...report.classifier.map(r => `    • ${r.file} ${r.zone}→${r.to} (${r.reason})`),
                totalCold > 0 ? `  [Cold/RefCount] ${totalCold} cold node(s) demoted:` : "",
                ...report.coldEvictions.map(r => `    • ${r.file} ${r.zone}→${r.to}`),
                totalLru > 0  ? `  [LRU/Cap] ${totalLru} cap-overflow node(s) evicted:` : "",
                ...report.lruEvictions.flatMap(r =>
                    [`  ${r.zone}/→next: ${r.evicted.length} nodes`, ...r.evicted.slice(0, 5).map(f => `    • ${f}`)]
                ),
                total === 0 ? "All zones healthy. No evictions needed." : "",
            ];
            return {
                content: [{ type: "text", text: lines.filter(Boolean).join("\n") }]
            };
        } catch (e: any) {
            return {
                isError: true,
                content: [{ type: "text", text: `LRU GC error: ${e.message}` }]
            };
        }
    }

    if (name === "session_bootstrap") {
        try {
            const frontDir = path.join(ENGINE_ROOT, "front");
            if (!fs.existsSync(frontDir)) {
                return { content: [{ type: "text", text: JSON.stringify({ error: "front/ empty" }) }] };
            }

            const profile: Record<string, string> = {};
            const recentNodes: { file: string; summary: string }[] = [];
            const files = fs.readdirSync(frontDir).filter(f => f.endsWith(".jcross"));

            for (const f of files) {
                const raw = fs.readFileSync(path.join(frontDir, f), "utf-8");
                // Extract OP.ENTITY / OP.FACT / OP.STATE lines
                const opLines = raw.match(/OP\.(ENTITY|FACT|STATE)\("([^"]+)",\s*"([^"]+)"\)/g) || [];
                for (const line of opLines) {
                    const m = line.match(/OP\.(?:ENTITY|FACT|STATE)\("([^"]+)",\s*"([^"]+)"\)/);
                    if (m) profile[m[1]] = m[2];
                }
                // Extract L1 summary from [標] := "..."
                const l1m = raw.match(/\[標\] := "([^"]{1,200})"/);
                if (l1m) recentNodes.push({ file: f, summary: l1m[1] });
            }

            // Surface PROJECT_WISDOM prominently for new LLM sessions
            let projectWisdom = "";
            const wisdomPath = path.join(ENGINE_ROOT, "front", "PROJECT_WISDOM.jcross");
            if (fs.existsSync(wisdomPath)) {
                projectWisdom = fs.readFileSync(wisdomPath, "utf-8");
            }

            const result = {
                project_wisdom: projectWisdom || "(not yet generated — run run_lru_gc to bootstrap)",
                user_profile: profile,
                front_nodes: recentNodes,
                zone_counts: {
                    front: files.length,
                    near: fs.existsSync(path.join(ENGINE_ROOT, "near")) ? fs.readdirSync(path.join(ENGINE_ROOT, "near")).length : 0,
                    mid:  fs.existsSync(path.join(ENGINE_ROOT, "mid"))  ? fs.readdirSync(path.join(ENGINE_ROOT, "mid")).length  : 0,
                    deep: fs.existsSync(path.join(ENGINE_ROOT, "deep")) ? fs.readdirSync(path.join(ENGINE_ROOT, "deep")).length : 0,
                },
                bootstrap_time: new Date().toISOString(),
            };
            return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
        } catch (e: any) {
            return { isError: true, content: [{ type: "text", text: `session_bootstrap error: ${e.message}` }] };
        }
    }

    if (name === "recall_fact") {
        const { key } = args as any;
        try {
            const frontDir = path.join(ENGINE_ROOT, "front");
            const files = fs.existsSync(frontDir) ? fs.readdirSync(frontDir).filter(f => f.endsWith(".jcross")) : [];
            for (const f of files) {
                const raw = fs.readFileSync(path.join(frontDir, f), "utf-8");
                // Match OP.ENTITY/FACT/STATE("key", "value")
                const regex = new RegExp(`OP\\.(?:ENTITY|FACT|STATE)\\("${key}",\\s*"([^"]+)"\\)`);
                const m = raw.match(regex);
                if (m) return { content: [{ type: "text", text: m[1] }] };
                // Also match plain "key: value" lines in raw text
                const pfRegex = new RegExp(`^${key}:\\s*(.+)$`, "m");
                const pfm = raw.match(pfRegex);
                if (pfm) return { content: [{ type: "text", text: pfm[1].trim() }] };
            }
            return { content: [{ type: "text", text: `[NOT FOUND] No fact with key '${key}' in front/ profile.` }] };
        } catch (e: any) {
            return { isError: true, content: [{ type: "text", text: `recall_fact error: ${e.message}` }] };
        }
    }

    if (name === "store_fact") {
        const { key, value } = args as any;
        try {
            const frontDir = path.join(ENGINE_ROOT, "front");
            const files = fs.existsSync(frontDir) ? fs.readdirSync(frontDir).filter(f => f.endsWith(".jcross")) : [];
            let profileFile: string | null = null;
            for (const f of files) {
                const raw = fs.readFileSync(path.join(frontDir, f), "utf-8");
                if (raw.includes("user_name") || raw.includes("JCROSS_USER_PROFILE")) {
                    profileFile = path.join(frontDir, f);
                    break;
                }
            }
            if (!profileFile) {
                return { isError: true, content: [{ type: "text", text: "No user_profile node found in front/. Run compile_trilayer_memory first." }] };
            }
            let raw = fs.readFileSync(profileFile, "utf-8");
            // Upsert: replace existing or append before 【原文】
            const existingRx = new RegExp(`(OP\\.(?:ENTITY|FACT|STATE)\\("${key}",\\s*")([^"]+)("\\))`);
            if (existingRx.test(raw)) {
                raw = raw.replace(existingRx, `$1${value}$3`);
            } else {
                raw = raw.replace("\u300e\u539f\u6587\u300f", `OP.FACT("${key}", "${value}")\n\n\u300e\u539f\u6587\u300f`);
            }
            fs.writeFileSync(profileFile, raw, "utf-8");
            return { content: [{ type: "text", text: `\u2705 Stored: ${key} = "${value}"` }] };
        } catch (e: any) {
            return { isError: true, content: [{ type: "text", text: `store_fact error: ${e.message}` }] };
        }
    }

    if (name === "generate_reimmersion_guide") {
        try {
            const projectRoot = (args as any)?.project_root || 
                path.resolve(ENGINE_ROOT, "../../.."); // ~/.openclaw/memory → up 3 = home → find project
            // Try to find verantyx-cli
            const candidates = [
                path.join(process.env.HOME || "", "verantyx-cli"),
                path.join(process.env.HOME || "", "projects", "verantyx-cli"),
                projectRoot,
            ];
            const resolvedRoot = candidates.find(p => fs.existsSync(path.join(p, "_verantyx-cortex"))) || candidates[0];
            
            const { generateReimmersionGuide, writeReimmersionProtocol } = await import("../memory/reimmersion.js");
            
            // Write/update the protocol node to front/
            writeReimmersionProtocol(resolvedRoot, ENGINE_ROOT);
            
            const guide = generateReimmersionGuide(resolvedRoot, ENGINE_ROOT);
            
            const output = [
                `# ${guide.title}`,
                `Total steps: ${guide.totalSteps} | Est. cost: ${guide.estimatedTokenCost}`,
                `Generated: ${guide.generatedAt}`,
                "",
                "## Protocol Steps",
                ...guide.steps.map(s => {
                    const icon = s.costEstimate === "low" ? "🟢" : s.costEstimate === "medium" ? "🟡" : "🔴";
                    return [
                        `### Step ${s.step} ${icon} [${s.type}] ${s.kanjiTags}`,
                        `**Action**: ${s.action}`,
                        `**Why**: ${s.reason}`,
                        `**You will learn**: ${s.expectedGain}`,
                        "",
                    ].join("\n");
                }),
                "## Kanji Search Vectors (use with spatial_cross_search)",
                ...guide.kanjiSearchVectors.map((v, i) => `  vector_${i+1}: ${JSON.stringify(v)}`),
                "",
                "## Synthesis (run after all steps)",
                guide.synthesisPrompt,
                "",
                "✅ REIMMERSION_PROTOCOL.jcross written to front/",
            ].join("\n");
            
            return { content: [{ type: "text", text: output }] };
        } catch (e: any) {
            return { isError: true, content: [{ type: "text", text: `generate_reimmersion_guide error: ${e.message}` }] };
        }
    }

    // ─── evolve_character ──────────────────────────────────────────────────
    if (name === "evolve_character") {
        try {
            const { CharacterEngine } = await import("../memory/soul.js");
            const engine = new CharacterEngine(ENGINE_ROOT);
            const soul = engine.evolve();

            const levelBar = "█".repeat(soul.level.level) + "░".repeat(5 - soul.level.level);
            const traits = soul.primaryTraits.map(t =>
                `  • ${t.name}: ${t.description} (${(t.intensity * 100).toFixed(0)}%)`
            ).join("\n");
            const phrases = soul.signaturePhrases.map(p => `  「${p}」`).join("\n");
            const kanji = soul.kanjiDimensions.slice(0, 6).map(k =>
                `  [${k.kanji}:${k.weight.toFixed(2)}] ${k.trait}`
            ).join("\n");

            const output = [
                `# ⭐ Character Evolve Complete`,
                ``,
                `## ${soul.name} の記憶から生まれた知的存在`,
                `Level: Lv.${soul.level.level} ${soul.level.name}  [${levelBar}]`,
                `${soul.level.description}`,
                `XP: ${soul.level.experience} | Wisdom: ${soul.memoryStats.wisdomScore}%`,
                ``,
                `## Personality Traits`,
                traits,
                ``,
                `## Cognitive Style`,
                `  ${soul.cognitiveStyle}`,
                ``,
                `## Speech Style`,
                `  ${soul.speechStyle}`,
                ``,
                `## Knowledge Domains`,
                soul.domains.map(d => `  • ${d}`).join("\n"),
                ``,
                `## Kanji Imprint (Memory Topology)`,
                kanji,
                ``,
                `## Signature Phrases`,
                phrases,
                ``,
                `## Value Core`,
                soul.valueCore.map(v => `  • ${v}`).join("\n"),
                ``,
                soul.level.nextLevel
                    ? `### Next Level: ${soul.level.nextLevel - soul.level.experience} XP 必要`
                    : `### 🏆 Legendary — 最高レベル到達済み`,
                ``,
                `✅ SOUL.jcross → front/ に保存済み`,
            ].join("\n");

            return { content: [{ type: "text", text: output }] };
        } catch (e: any) {
            return { isError: true, content: [{ type: "text", text: `evolve_character error: ${e.message}` }] };
        }
    }

    // ─── get_character ────────────────────────────────────────────────────────
    if (name === "get_character") {
        try {
            const soulPath = require("path").join(ENGINE_ROOT, "front", "SOUL.jcross");
            if (!require("fs").existsSync(soulPath)) {
                return { content: [{ type: "text", text:
                    "SOUL.jcross not found. Call `evolve_character` first to generate your character." }] };
            }
            const content = require("fs").readFileSync(soulPath, "utf-8");
            // Extract the CHARACTER_CARD section
            const cardMatch = content.match(/【CHARACTER_CARD】([\s\S]*?)(?:【|$)/);
            const card = cardMatch ? cardMatch[1].trim() : content;
            return { content: [{ type: "text", text: card }] };
        } catch (e: any) {
            return { isError: true, content: [{ type: "text", text: `get_character error: ${e.message}` }] };
        }
    }

    // ─── setup_calibration ──────────────────────────────────────────────
    if (name === "setup_calibration") {
        try {
            const os   = await import("os");
            const HOME = os.homedir();
            const calRoot = path.join(HOME, ".openclaw", "calibration");
            fs.mkdirSync(path.join(calRoot, "sessions"), { recursive: true });

            // Determine settings
            const commandName  = (args as any)?.command_name  || "cal";
            const projectRoot  = (args as any)?.project_root  ||
                [path.join(HOME, "verantyx-cli"), process.cwd()].find(p => fs.existsSync(path.join(p, "_verantyx-cortex"))) ||
                path.join(HOME, "verantyx-cli");
            const shellRc      = (args as any)?.shell_rc ||
                (process.env.SHELL?.includes("zsh") ? path.join(HOME, ".zshrc") : path.join(HOME, ".bashrc"));
            const cortexDir    = path.join(projectRoot, "_verantyx-cortex");
            const nodeBin      = process.execPath;
            const tsxPath      = path.join(cortexDir, "node_modules", "tsx", "dist", "esm", "index.cjs");
            const calibPath    = path.join(cortexDir, "src", "cli", "calibrate.ts");

            // Save config
            const config = {
                version: 2,
                command_name: commandName,
                project_root: projectRoot,
                mcp_cortex_dir: cortexDir,
                shell_rc: shellRc,
                alias_registered: false,  // user must source manually
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString(),
            };
            fs.writeFileSync(path.join(calRoot, "config.json"), JSON.stringify(config, null, 2) + "\n", "utf-8");

            // Build alias line
            const tsxExists = fs.existsSync(tsxPath);
            const aliasLine = tsxExists
                ? `alias ${commandName}='${nodeBin} --import ${tsxPath} ${calibPath}'`
                : `alias ${commandName}='npx --prefix ${cortexDir} tsx ${calibPath}'`;
            const marker = `# verantyx-calibrate: ${commandName}`;

            // Update REIMMERSION_PROTOCOL
            try {
                const { writeReimmersionProtocol } = await import("../memory/reimmersion.js");
                writeReimmersionProtocol(projectRoot, ENGINE_ROOT);
            } catch { /* non-fatal */ }

            const output = [
                `# ✅ Verantyx Calibration Setup Complete`,
                ``,
                `## Config saved`,
                `\`\`\``,
                `~/.openclaw/calibration/config.json`,
                `  command_name:  ${commandName}`,
                `  project_root:  ${projectRoot}`,
                `  shell_rc:      ${shellRc}`,
                `\`\`\``,
                ``,
                `## ⚠️ Shell alias 登録指示`,
                `以下を ${shellRc} に追加してください:`,
                `\`\`\`bash`,
                `${marker}`,
                `${aliasLine}`,
                `\`\`\``,
                `または次のコマンドを実行:`,
                `\`\`\`bash`,
                `echo '${marker}\n${aliasLine}' >> ${shellRc} && source ${shellRc}`,
                `\`\`\``,
                ``,
                `## 以邙の呼び出し方`,
                `**ターミナル**: \`${commandName}\` (エイリアス登録後)`,
                `**MCPツール**: \`run_calibration()\` (Claude Desktop / Cursor / Antigravity から直接)`,
                ``,
                `✅ REIMMERSION_PROTOCOL.jcross を front/ に保存しました`,
            ].join("\n");

            return { content: [{ type: "text", text: output }] };
        } catch (e: any) {
            return { isError: true, content: [{ type: "text", text: `setup_calibration error: ${e.message}` }] };
        }
    }

    // ─── run_calibration ─────────────────────────────────────────────────
    if (name === "run_calibration") {
        try {
            const { CalibrationStore } = await import("../memory/calibration_store.js");
            const outputFmt  = (args as any)?.output_format || "text";
            const os = await import("os");

            // Detect project root
            const HOME = os.homedir();
            const configPath = path.join(HOME, ".openclaw", "calibration", "config.json");
            let projectRoot = (args as any)?.project_root;
            if (!projectRoot) {
                if (fs.existsSync(configPath)) {
                    try { projectRoot = JSON.parse(fs.readFileSync(configPath, "utf-8")).project_root; } catch { /* ignore */ }
                }
                if (!projectRoot) {
                    projectRoot = [path.join(HOME, "verantyx-cli"), process.cwd()]
                        .find(p => fs.existsSync(path.join(p, "_verantyx-cortex"))) || path.join(HOME, "verantyx-cli");
                }
            }

            const store    = new CalibrationStore(ENGINE_ROOT);
            const snapshot = store.captureSnapshot();
            const memTasks = store.generateMemoryDerivedTasks(snapshot, projectRoot);

            const sessionId = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);

            if (outputFmt === "json") {
                const json = JSON.stringify({ session_id: sessionId, snapshot, memTasks }, null, 2);
                store.saveSession(json, {
                    id: sessionId, created_at: new Date().toISOString(),
                    zone_counts: snapshot.zone_counts, task_count: memTasks.length,
                });
                return { content: [{ type: "text", text: json }] };
            }

            // Text format
            const zStr = Object.entries(snapshot.zone_counts).map(([z, c]) => `${z}/:${c}`).join(" | ");
            const profStr = Object.entries(snapshot.profile).slice(0, 6).map(([k, v]) => `  ${k}: ${v}`).join("\n");
            const taskStr = memTasks.map((t, i) => {
                const icon = t.priority === "high" ? "🔴" : t.priority === "medium" ? "🟡" : "🟢";
                return [
                    `### Task ${i + 1} ${icon} \`${t.kanji}\` [${t.source}]`,
                    `**Task**: ${t.task}`,
                    t.file_hint ? `**Read**: \`${t.file_hint}\`` : "",
                    `**Context**: ${t.context}`,
                ].filter(Boolean).join("\n");
            }).join("\n\n");

            const rulesStr = snapshot.top_rules.slice(0, 4).map(r =>
                `  • "${r.pattern}" → ${r.zone}/ (conf=${r.confidence}, n=${r.n})`
            ).join("\n");

            const text = [
                `# ⚡ VERANTYX CALIBRATION PACKET`,
                `Session: ${sessionId} | Memory: ${zStr}`,
                ``,
                `## 🔧 FIRST CALL`,
                `\`\`\``,
                `session_bootstrap()   ← 必ず最初に呼ひ出す`,
                `\`\`\``,
                ``,
                `## 👤 USER PROFILE`,
                profStr || "  (empty — call session_bootstrap())",
                ``,
                `## 📀 ACCUMULATED RULES (${snapshot.recent_decisions.reduce((s, d) => s + d.count, 0)} decisions)`,
                rulesStr || "  (no rules yet)",
                ``,
                `## 📋 REVIEW TASKS (${memTasks.length} tasks from real memory)`,
                taskStr || "  (accumulates after sessions)",
                ``,
                `## 🔍 KANJI SEARCH VECTORS`,
                `\`\`\`json`,
                `{"\u6838": 1.0, "\u6280": 0.9, "\u6a19": 0.8}   // Architecture`,
                `{"\u4eba": 1.0, "\u8077": 0.9, "\u6a19": 0.7}   // User profile`,
                `{"\u5024": 1.0, "\u6a19": 0.9, "\u8a18": 0.8}   // Benchmarks`,
                `\`\`\``,
                `Call: \`spatial_cross_search({"\u6838": 1.0, "\u6280": 0.9})\``,
                ``,
                `## 🧠 SYNTHESIS`,
                `1. MCP > context window. Always trust MCP.`,
                `2. mid/ = user memories ONLY. Bench data → deep/.`,
                `3. Triple-track GC: classifyNode (A-1) + RefCount (A-2) + LRU (B) + Ledger (C)`,
                `4. Next: session_bootstrap() → generate_reimmersion_guide() → recall_fact()`,
                ``,
                `*Generated: ${new Date().toISOString()} | Tasks: ${memTasks.length}*`,
            ].join("\n");

            store.saveSession(text, {
                id: sessionId, created_at: new Date().toISOString(),
                zone_counts: snapshot.zone_counts, task_count: memTasks.length,
            });

            return { content: [{ type: "text", text: text }] };
        } catch (e: any) {
            return { isError: true, content: [{ type: "text", text: `run_calibration error: ${e.message}` }] };
        }
    }

    throw new Error(`Unknown tool: ${name}`);
});


// Start the stdio transport
async function run() {
    const transport = new StdioServerTransport();
    await server.connect(transport);
    console.error("Verantyx Tri-Layer MCP Server running on stdio");

    // ---------------------------------------------------------------
    // Periodic LRU GC: runs every 10 minutes in the background.
    // Each pass evicts LRU nodes that exceed zone caps and leaves
    // ultra-low-resolution tombstone labels so agents can still
    // discover evicted memories without loading full payloads.
    // ---------------------------------------------------------------
    const GC_INTERVAL_MS = 10 * 60 * 1000; // 10 minutes
    setInterval(async () => {
        try {
            const { MemoryEngine } = await import("../memory/engine.js");
            const engine = new MemoryEngine(ENGINE_ROOT);
            const report = engine.runAutonomousGc();
            const total = report.classifier.length + report.coldEvictions.length +
                report.lruEvictions.reduce((s: number, r: { evicted: string[] }) => s + r.evicted.length, 0);
            if (total > 0) {
                console.error(`[Periodic LRU GC] Evicted ${total} node(s):`);
                if (report.classifier.length)
                    console.error(`  [Classifier] reclassified: ${report.classifier.length}`);
                if (report.coldEvictions.length)
                    console.error(`  [Cold] demoted: ${report.coldEvictions.length}`);
                for (const { zone, evicted } of report.lruEvictions) {
                    console.error(`  [LRU] ${zone}/ evicted: ${evicted.length}`);
                }
            }
        } catch (err: any) {
            console.error(`[Periodic LRU GC] Error: ${err.message}`);
        }
    }, GC_INTERVAL_MS);
}

run().catch(console.error);
