import type { Command } from "commander";
import { AgentOrchestrator } from "../verantyx/agents/orchestrator.js";
import { MemoryEngine } from "../verantyx/memory/engine.js";
import { Gatekeeper } from "../verantyx/vfs/gatekeeper.js";
import { resolve, join } from "path";

function resolveMemoryRoot(): string {
  return process.env.RONIN_MEMORY_ROOT || join(process.env.HOME || "~", ".ronin", "memory");
}

function resolveVfsPath(): string {
  return process.env.RONIN_VFS_MAPPING || join(process.cwd(), ".ronin", "vfs_mapping.json");
}

export function registerRoninExecCli(program: Command) {
  program
    .command("exec <task>")
    .description("Execute a single ReAct loop task (supports stdin pipeline)")
    .option("-t, --tier <tier>", "Force capability tier", "Tier 1: Fully Autonomous")
    .action(async (task: string, opts: { tier: any }) => {
        let pipedTest = "";
        
        // Fabric: Unix Pipeline Injection
        if (!process.stdin.isTTY) {
            pipedTest = await new Promise<string>((res) => {
                let data = "";
                process.stdin.on("data", (chunk) => { data += chunk; });
                process.stdin.on("end", () => res(data));
            });
        }

        try {
            const mem = new MemoryEngine(resolveMemoryRoot());
            const gk = new Gatekeeper(resolveVfsPath());
            const orchestrator = new AgentOrchestrator(mem, gk);
            await orchestrator.initMcp(process.cwd());
            
            orchestrator.setLocallmTier(opts.tier);

            const fullMessage = pipedTest 
                ? `<sys_stdin>\n${pipedTest}\n</sys_stdin>\n\nTask: ${task}` 
                : task;
            
            console.log(`\n🚀 [Ronin Exec] Pipeline Initialized. Task: ${task}`);
            if (pipedTest) {
                 console.log(`  └─ [Fabric] 📎 Stdin captured (${pipedTest.length} bytes)`);
            }

            const result = await orchestrator.commanderChat(fullMessage, (chunk) => {
                process.stdout.write(chunk);
            });
            
            console.log("\n====== FINAL ENGINE OUTPUT ======\n");
            console.log(result);
            console.log("\n=================================\n");
            process.exit(0);
        } catch (e: any) {
            console.error(`[EXEC ERROR] ${e.message}`);
            process.exit(1);
        }
    });
}
