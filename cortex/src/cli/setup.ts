#!/usr/bin/env node
/**
 * verantyx-setup — First-time setup wizard for the calibration system.
 *
 * Usage:
 *   npx tsx src/cli/setup.ts
 *
 * What it does:
 *   1. Interactive prompts (no external deps — pure readline)
 *   2. Saves config to ~/.openclaw/calibration/config.json
 *   3. Registers a custom shell alias (e.g., `cal`, `vera`, `moto-cal`)
 *   4. Runs the first calibration on completion
 */

import { createInterface } from "readline";
import { existsSync, readFileSync, writeFileSync, mkdirSync } from "fs";
import { join, resolve } from "path";
import { execSync } from "child_process";
import { homedir } from "os";

// ─── ANSI helpers ─────────────────────────────────────────────────────────────

const C = {
  reset:  "\x1b[0m",
  bold:   "\x1b[1m",
  dim:    "\x1b[2m",
  cyan:   "\x1b[36m",
  green:  "\x1b[32m",
  yellow: "\x1b[33m",
  red:    "\x1b[31m",
  magenta:"\x1b[35m",
  blue:   "\x1b[34m",
};
const c = (color: keyof typeof C, s: string) => `${C[color]}${s}${C.reset}`;

// ─── Config ───────────────────────────────────────────────────────────────────

const HOME         = homedir();
const CAL_ROOT     = join(HOME, ".openclaw", "calibration");
const CONFIG_PATH  = join(CAL_ROOT, "config.json");
const MEMORY_ROOT  = join(HOME, ".openclaw", "memory");

export interface CalibrationConfig {
  version:        number;
  command_name:   string;          // e.g., "cal", "moto-cal", "vera"
  project_root:   string;
  mcp_cortex_dir: string;          // path to _verantyx-cortex
  shell_rc:       string;          // ~/.zshrc or ~/.bashrc
  alias_registered: boolean;
  created_at:     string;
  updated_at:     string;
}

function loadConfig(): CalibrationConfig | null {
  if (!existsSync(CONFIG_PATH)) return null;
  try { return JSON.parse(readFileSync(CONFIG_PATH, "utf-8")) as CalibrationConfig; }
  catch { return null; }
}

function saveConfig(cfg: CalibrationConfig): void {
  mkdirSync(CAL_ROOT, { recursive: true });
  writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2) + "\n", "utf-8");
}

// ─── readline prompt helper ──────────────────────────────────────────────────

async function prompt(rl: ReturnType<typeof createInterface>, question: string, defaultVal = ""): Promise<string> {
  return new Promise(resolve => {
    const q = defaultVal
      ? `${question} ${c("dim", `[${defaultVal}]`)}: `
      : `${question}: `;
    rl.question(q, answer => {
      resolve(answer.trim() || defaultVal);
    });
  });
}

async function confirm(rl: ReturnType<typeof createInterface>, question: string, defaultVal = true): Promise<boolean> {
  const hint = defaultVal ? "Y/n" : "y/N";
  return new Promise(resolve => {
    rl.question(`${question} ${c("dim", `[${hint}]`)}: `, answer => {
      const a = answer.trim().toLowerCase();
      if (!a) resolve(defaultVal);
      else resolve(a === "y" || a === "yes");
    });
  });
}

// ─── Shell RC detection ───────────────────────────────────────────────────────

function detectShellRc(): string {
  const shell = process.env.SHELL || "";
  if (shell.includes("zsh")) return join(HOME, ".zshrc");
  if (shell.includes("bash")) return join(HOME, ".bashrc");
  return join(HOME, ".zshrc");  // default
}

function detectProjectRoot(): string {
  const candidates = [
    join(HOME, "verantyx-cli"),
    join(process.cwd(), "../.."),
    process.cwd(),
  ];
  return candidates.find(p => existsSync(join(p, "_verantyx-cortex"))) || join(HOME, "verantyx-cli");
}

// ─── Alias registration ───────────────────────────────────────────────────────

function buildAliasLine(cfg: CalibrationConfig): string {
  // The alias calls our calibrate script via node + tsx
  const cortex = cfg.mcp_cortex_dir;
  const nodeBin = process.execPath;  // absolute path to the node that's running this
  const tsxPath = join(cortex, "node_modules", "tsx", "dist", "esm", "index.cjs");
  const calibPath = join(cortex, "src", "cli", "calibrate.ts");

  // Prefer tsx from cortex, fall back to global
  const tsxPathFinal = existsSync(tsxPath) ? tsxPath : "tsx";
  if (existsSync(tsxPath)) {
    return `alias ${cfg.command_name}='${nodeBin} --import ${tsxPathFinal} ${calibPath}'`;
  }
  return `alias ${cfg.command_name}='npx --prefix ${cortex} tsx ${calibPath}'`;
}

function registerAlias(cfg: CalibrationConfig): boolean {
  const aliasLine = buildAliasLine(cfg);
  const marker    = `# verantyx-calibrate: ${cfg.command_name}`;
  const rc        = cfg.shell_rc;

  if (!existsSync(rc)) {
    writeFileSync(rc, `${marker}\n${aliasLine}\n`, "utf-8");
    return true;
  }

  let content = readFileSync(rc, "utf-8");

  // Remove old alias if it exists
  const oldMarkerRe = /# verantyx-calibrate: .*\nalias .*\n?/g;
  content = content.replace(oldMarkerRe, "");

  // Append new alias
  content = content.trimEnd() + `\n\n${marker}\n${aliasLine}\n`;
  writeFileSync(rc, content, "utf-8");
  return true;
}

// ─── First calibration run ────────────────────────────────────────────────────

async function runFirstCalibration(cfg: CalibrationConfig): Promise<void> {
  console.log("\n" + c("cyan", "Running initial calibration..."));
  const nodeBin = process.execPath;
  const tsxPath = join(cfg.mcp_cortex_dir, "node_modules", "tsx", "dist", "esm", "index.cjs");
  const calibPath = join(cfg.mcp_cortex_dir, "src", "cli", "calibrate.ts");

  try {
    const out = execSync(
      `${nodeBin} --import ${tsxPath} ${calibPath} --project ${cfg.project_root} --sync`,
      { encoding: "utf-8", stdio: ["pipe", "pipe", "pipe"] }
    );
    // Show just the first 30 lines
    const preview = out.split("\n").slice(0, 30).join("\n");
    console.log(c("dim", preview));
    console.log(c("dim", "... (full output saved to ~/.openclaw/calibration/sessions/)"));
  } catch (e: any) {
    console.log(c("yellow", "⚠️  Initial calibration had warnings (non-fatal). Run `" + cfg.command_name + "` manually to see details."));
  }
}

// ─── Setup banner ─────────────────────────────────────────────────────────────

function printBanner(): void {
  console.log(`
${c("magenta", "╔══════════════════════════════════════════════════════╗")}
${c("magenta", "║")}   ${c("bold", "VERANTYX  Calibration Setup Wizard")}                ${c("magenta", "║")}
${c("magenta", "║")}   ${c("dim", "Configure your cognitive cold-start eliminator")}     ${c("magenta", "║")}
${c("magenta", "╚══════════════════════════════════════════════════════╝")}
`);
}

function printSummary(cfg: CalibrationConfig): void {
  const aliasLine = buildAliasLine(cfg);
  console.log(`
${c("green", "╔══════════════════════════════════════════════════════╗")}
${c("green", "║")}  ${c("bold", "✅ Setup Complete")}                                    ${c("green", "║")}
${c("green", "╚══════════════════════════════════════════════════════╝")}

${c("bold", "Your calibration command:")}
  ${c("cyan", cfg.command_name)}               → Run calibration packet
  ${c("cyan", cfg.command_name)} --sync        → + update REIMMERSION_PROTOCOL
  ${c("cyan", cfg.command_name)} --output json → JSON output

${c("bold", "Config saved to:")}
  ${c("dim", CONFIG_PATH)}

${c("bold", "Calibration store (isolated from main memory):")}
  ${c("dim", CAL_ROOT + "/")}

${c("bold", "Shell alias added to:")}
  ${c("dim", cfg.shell_rc)}
  ${c("dim", aliasLine)}

${c("yellow", "→ Run:")} ${c("bold", `source ${cfg.shell_rc}`)} ${c("yellow", "to activate the alias now.")}

${c("bold", "When to run calibration:")}
  • After switching models
  • At the start of a new session on an existing project
  • After significant code changes

${c("bold", "Stored data:")}
  ~/.openclaw/calibration/snapshot.json    ← memory snapshot
  ~/.openclaw/calibration/task_bank.jsonl  ← accumulated tasks
  ~/.openclaw/calibration/sessions/        ← session history
`);
}

// ─── Main wizard ──────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  printBanner();

  const existingCfg = loadConfig();
  if (existingCfg) {
    console.log(c("yellow", `⚠️  Existing config found (command: "${existingCfg.command_name}")`));
    console.log(c("dim", `   Config: ${CONFIG_PATH}`));
    console.log();
  }

  const rl = createInterface({
    input:  process.stdin,
    output: process.stdout,
  });

  // ── Question 1: Command name ────────────────────────────────────────────────
  console.log(c("bold", "Step 1: Choose your calibration command name"));
  console.log(c("dim", "  This will be registered as a shell alias."));
  console.log(c("dim", "  Examples: cal, vera, moto-cal, v-cal, recal"));
  console.log();
  const commandName = await prompt(rl, c("cyan", "Command name"), existingCfg?.command_name || "cal");

  // Validate: no spaces, no special chars except -_
  if (!/^[a-zA-Z][a-zA-Z0-9_-]*$/.test(commandName)) {
    console.log(c("red", "❌ Invalid name. Must start with a letter and contain only letters, numbers, - or _."));
    rl.close();
    process.exit(1);
  }

  // ── Question 2: Project root ────────────────────────────────────────────────
  console.log();
  console.log(c("bold", "Step 2: Project root path"));
  const defaultRoot = detectProjectRoot();
  const projectRoot = resolve(await prompt(rl, c("cyan", "Project root"), defaultRoot));

  if (!existsSync(join(projectRoot, "_verantyx-cortex"))) {
    console.log(c("yellow", `⚠️  _verantyx-cortex/ not found in ${projectRoot}`));
    console.log(c("yellow", "   Continuing anyway — you can fix this later."));
  }

  const cortexDir = join(projectRoot, "_verantyx-cortex");

  // ── Question 3: Shell RC ────────────────────────────────────────────────────
  console.log();
  console.log(c("bold", "Step 3: Shell configuration file"));
  const defaultRc = detectShellRc();
  const shellRc   = resolve(await prompt(rl, c("cyan", "Shell RC file"), defaultRc));

  // ── Question 4: Register alias? ─────────────────────────────────────────────
  console.log();
  const doAlias = await confirm(rl, c("cyan", `Register "${commandName}" alias in ${shellRc}?`), true);

  // ── Question 5: Run first calibration? ─────────────────────────────────────
  console.log();
  const doFirstRun = await confirm(rl, c("cyan", "Run initial calibration now?"), true);

  rl.close();

  // ── Build config ────────────────────────────────────────────────────────────
  const cfg: CalibrationConfig = {
    version:          2,
    command_name:     commandName,
    project_root:     projectRoot,
    mcp_cortex_dir:   cortexDir,
    shell_rc:         shellRc,
    alias_registered: doAlias,
    created_at:       existingCfg?.created_at || new Date().toISOString(),
    updated_at:       new Date().toISOString(),
  };

  saveConfig(cfg);
  console.log(`\n${c("green", "✅")} Config saved.`);

  // ── Register alias ──────────────────────────────────────────────────────────
  if (doAlias) {
    const ok = registerAlias(cfg);
    if (ok) {
      console.log(`${c("green", "✅")} Alias "${commandName}" registered in ${shellRc}.`);
    }
  }

  // Also write a setup-agnostic script wrapper at cortex root
  const wrapperPath = join(cortexDir, `calibrate-${commandName}.sh`);
  const nodeBin  = process.execPath;
  const tsxPath  = join(cortexDir, "node_modules", "tsx", "dist", "esm", "index.cjs");
  const calibPath = join(cortexDir, "src", "cli", "calibrate.ts");
  const wrapperContent = `#!/bin/sh
# Verantyx calibration wrapper — command: ${commandName}
# Auto-generated by verantyx-setup. Do not edit manually.
exec ${nodeBin} --import ${tsxPath} ${calibPath} --project ${projectRoot} "$@"
`;
  writeFileSync(wrapperPath, wrapperContent, { mode: 0o755 });
  console.log(`${c("green", "✅")} Shell wrapper: ${wrapperPath}`);

  // ── First run ───────────────────────────────────────────────────────────────
  if (doFirstRun) {
    await runFirstCalibration(cfg);
  }

  printSummary(cfg);
}

main().catch(e => {
  console.error(c("red", `Setup error: ${e.message}`));
  process.exit(1);
});
