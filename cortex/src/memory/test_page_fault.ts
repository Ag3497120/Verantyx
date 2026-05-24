import fs from "fs";
import path from "path";
import { MemoryEngine } from "./engine.js";

const ENGINE_ROOT = path.resolve(process.env.HOME || "~", ".verantyx/memory");
const eng = new MemoryEngine(ENGINE_ROOT);

// 1. Create a "forgotten" memory in deep/
const forgottenFile = "TURN_FORGOTTEN_123.jcross";
const forgottenPath = path.join(ENGINE_ROOT, "deep", forgottenFile);
const jcrossContent = `■ JCROSS_FORGOTTEN_DATA
【空間座相】
[鍵:0.9] [庫:0.8] [認:1.0]

【位相対応表】
[標] := "Legacy Auth Database Connection"

【操作対応表】
OP.FACT("legacy_db_url", "postgres://old_auth_db:5432/users")
OP.FACT("admin_secret", "verantyx_legacy_xyz99")

【原文】
This is the old legacy authentication database connection. We might need this if the new Gatekeeper migration fails and we have to rollback.

【META】
timestamp: 1600000000
`;

if (!fs.existsSync(path.join(ENGINE_ROOT, "deep"))) {
    fs.mkdirSync(path.join(ENGINE_ROOT, "deep"), { recursive: true });
}
fs.writeFileSync(forgottenPath, jcrossContent, "utf-8");

console.log("⏬ Planted forgotten knowledge in deep memory zone:");
console.log(`   File: ${forgottenPath}`);

// 2. Simulate AI hitting a Tension (Page Fault)
const tension_signal = "認証データベースの鍵情報が欠落している (legacy_db_url)";
console.log(`\n⚠️ AI encountered TENSION: "${tension_signal}"`);

// 3. Resolve Tension (Page Fault resolution logic)
const queryKanji: Record<string, number> = {};
const chars = tension_signal.replace(/[^\u4E00-\u9FFF]/g, "");
for (const c of chars) queryKanji[c] = 0.8;
if (Object.keys(queryKanji).length === 0) queryKanji["欠"] = 1.0;

const results: { file: string; zone: string; score: number; raw: string }[] = [];
for (const z of ["near", "mid", "deep"]) {
    const dir = path.join(ENGINE_ROOT, z);
    if (!fs.existsSync(dir)) continue;
    for (const f of fs.readdirSync(dir).filter(f => f.endsWith(".jcross"))) {
        const content = fs.readFileSync(path.join(dir, f), "utf-8");
        const kanjiM = content.match(/【空間座相】\s*\n([^\n【]+)/);
        if (!kanjiM) continue;
        let score = 0;
        for (const [k, w] of Object.entries(queryKanji)) {
            const m = kanjiM[1].match(new RegExp(`\\[${k}:(\\d+\\.?\\d*)\\]`));
            if (m) score += parseFloat(m[1]) * w;
        }
        const opsM  = content.match(/【操作対応表】([\s\S]*?)(?:【原文】|$)/);
        const ops   = (opsM?.[1]??"").toLowerCase();
        if (ops.includes("legacy_db_url")) score += 2.0; // Semantic hit

        if (score > 0) results.push({ file: f, zone: z, score, raw: content });
    }
}
results.sort((a, b) => b.score - a.score);

if (results.length === 0) {
    console.log("❌ [TENSION unresolved] No nodes found.");
} else {
    console.log(`\n🔍 Found ${results.length} matching nodes in deep/mid/near.`);
    
    const promoted: string[] = [];
    for (const r of results.slice(0, 1)) {
        eng.move(r.file, "front");
        promoted.push(r.file);
        
        const l2M = r.raw.match(/【操作対応表】([\s\S]*?)(?:【原文】|$)/);
        console.log(`\n✅ [PAGE FAULT RESOLVED] Promoted ${r.file} to front/!`);
        console.log(`   Injected Context (L2 Ops):\n${l2M ? l2M[1].trim() : ""}`);
    }
}
