# Contributing to Verantyx-CLI

Welcome to the Verantyx Neural Lab! 🧠✨

Verantyx began as a fork of OpenClaw infrastructure but has evolved into a fundamentally distinct cognitive architecture focusing on **Spatial Reasoning (JCross)**, the **Carbon Paper UI**, and the **4-Node Agentic Hierarchy**. 

We heavily rely on OpenClaw's robust lower-level Gateway, CLI framework, and Sandbox integrations, but all contributions to Verantyx should be viewed through the lens of stealth operations and physical API emulation to evade bot detection.

## Quick Links

- **GitHub:** https://github.com/verantyx/verantyx-cli
- **Core Vision:** Highly resilient, Human-in-The-Loop Autonomous Agent Systems built on native OS manipulation.

## The Paradigm Shift

If you are contributing, keep these core principles in mind:

1. **Carbon Paper UI (Anti-BotGuard Evasion):**
   We do not use headless Chrome automation tools (which are instantly categorized as bots by Cloudflare or Google). We interact via native OS workflows (`osascript`, simulated keystrokes, OS Clipboard ingestion) to ensure a zero-detection footprint.
2. **Spatial Memory Over VectorDB:**
   Verantyx relies on `.jcross` intermediate representations (IR) and "Kanji Ontology" semantic tags rather than heavy chunked vector embeddings. New features should strive to support this lightweight topological mapping.
3. **Local-First (SLM routing):**
   The primary router and planner must always be small enough to run on local silicon (e.g., Qwen2.5 1.5b via Ollama) without prematurely exposing full codebase contexts to cloud API endpoints.
4. **4-Node Isolation:**
   We strictly separate the **Local Planner**, **Senior Supervisor**, **Apprentice Verifier**, and **Stealth Worker**. Ensure these boundaries are maintained when proposing architectural changes.

## How to Contribute

1. **Bugs & small fixes** → Open a PR directly to `main`!
2. **Architectural Improvements** → If you are adding new graphical components to the `vera` 3D Command Center or expanding `.jcross` formats, please open an Issue first detailing your visual/system design.
3. **Rust Crate Structure (`verantyx-browser`)** → 
   Most active UI/Agent logic lives in:
   - `crates/ronin-hive/examples/interactive_chat.rs` (The main REPL engine)
   - `crates/ronin-core/src/memory_bridge/spatial_index.rs` (JCross Object mappings)
   - `crates/ronin-hive/src/roles/` (Gemini and SLM Roles definitions)

## Before You PR

- Ensure your changes perfectly compile: `cargo check --workspace`
- Test the interactive chat loop: `cd verantyx-browser && cargo run --example interactive_chat -p ronin-hive`
- **Provide screenshots** of the terminal output if your changes alter the visual formatting, Vera Lab UI, or Dialoguer terminal prompts.
- Do not mix pure `JCross` engine optimizations with unrelated low-level OpenClaw core patches unless entirely necessary.

## AI/Vibe-Coded PRs Welcome! 🤖

As a Neural Architecture project, we highly encourage writing code alongside your favorite LLMs.

Please specify in your PR:
- [ ] What LLM assisted you (e.g., Gemini 2.5 Pro, Claude-3.5)
- [ ] Are you modifying the visual syntax of `interactive_chat` terminal prints? 
- [ ] Are you introducing any new `JCross` feature implementations?

## Report a Vulnerability

Verantyx implements Human-In-The-Loop prompts (Dialoguer limits) before executing potentially destructive commands on native OS files. If you find a way to circumvent this and accidentally trigger massive undocumented file access, please reliably report the sandbox escape so we can patch the Node execution boundary.
