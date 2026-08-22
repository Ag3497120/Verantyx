<div align="center">
  <h1>🛡️ Verantyx IDE &amp; Cortex Engine</h1>
  <p><b>The Zero-Leakage, Neuro-Symbolic AI Coding Gateway &amp; Native macOS IDE</b></p>
  <p><i>We trade token cost for absolute security, deterministic patching, and forced structural reasoning.</i></p>

  <p>
    <img src="https://img.shields.io/badge/version-0.4.0-blue?style=flat-square" alt="Version 0.4.0">
    <img src="https://img.shields.io/badge/platform-macOS%2014%2B-lightgrey?style=flat-square">
    <img src="https://img.shields.io/badge/Apple%20Silicon-optimized-orange?style=flat-square">
    <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square">
  </p>

  <p>
    <a href="#-the-vision-why-verantyx-exists">Vision</a> •
    <a href="#-gatekeeper-mode-architecture">Gatekeeper Architecture</a> •
    <a href="#-whats-new-in-v030">What's New</a> •
    <a href="#-the-contributor-strategy-join-the-core-engineering-team"><b>Contribute!</b></a> •
    <a href="#-demos">Demos</a>
  </p>
</div>

---

## 📦 Download

**[→ Download Latest Release (v0.4.0)](https://github.com/Ag3497120/verantyx/releases/latest)**

1. Download **`VerantyxIDE-0.4.0.dmg`**
2. Open the DMG and drag **Verantyx.app** to your **Applications** folder
3. **First launch — bypass Gatekeeper (macOS security prompt):**
   - Right-click `Verantyx.app` in Finder → **"Open"**
   - Click **"Open"** in the unidentified developer dialog
   - _Or run in Terminal:_ `xattr -d com.apple.quarantine /Applications/Verantyx.app`

---

## 🌌 The Vision: Why Verantyx Exists

The AI coding revolution is broken for enterprise. **Semantic Leakage** prevents banks, healthcare systems, and defense contractors from uploading their proprietary code to APIs like OpenAI or Anthropic. Furthermore, even when code is uploaded, LLMs frequently hallucinate syntax errors, hallucinate non-existent variables, and break build pipelines.

Verantyx takes a radically different approach. We are building the **Enterprise Security Gateway for AI Coding**.

### 1. Zero-Leakage Gatekeeper Mode
We convert your source code into a synthetic, mathematically anonymized graph called **JCross IR**. External LLMs *never* see your business logic—they only see abstract structural shapes. We gladly sacrifice token efficiency (API costs) to guarantee 100% intellectual property protection and flawless, deterministic AST patching.

### 2. Forced Structural Reasoning
By stripping away English semantics and replacing them with Kanji dimensional weights (e.g., `[核:1.0][像:0.8]`), we force LLMs to stop guessing based on variable names and start reasoning about the pure logic graph. This unlocks massive-scale refactoring capabilities without syntax hallucination.

### 💡 The Verantyx Paradox: Burning Tokens vs. Infinite Local Memory

This architecture embraces what might seem like a direct contradiction.

**On one hand (The Cloud Gatekeeper):** We do *not* care about saving API tokens. When routing tasks to external LLMs (Claude/GPT), we intentionally inflate token consumption by 30-40% by obfuscating code into JCross IR. We proudly trade API efficiency for **mathematically guaranteed security (zero-leakage)** and deterministic patching for enterprise logic.

**On the other hand (The Local Cortex):** We are building the ultimate zero-cost, infinite-context local engine. By leveraging the same JCross IR format, we have implemented a **Tri-Layer Cognitive Memory System** that mimics human biological memory:
- **L1 (Kanji Topology)**: Semantic anchors used to instantly grasp structure.
- **L1.5 (Bridge Index)**: One-line summaries for massive O(1) scanning without context-window pollution.
- **L2 & L3 (Facts & Raw Text)**: The actual deep storage of code graphs and decisions.

Because our models only need to process *mathematical structure* rather than massive raw text payloads, we enable **ultra-small, 2B-class local models** (running entirely offline on Apple Silicon via MLX) to navigate and manage massive, enterprise-scale codebases *without ever suffering from context loss*.

We burn tokens in the cloud to buy perfect security. We compress structure locally to achieve infinite memory on edge devices. If you share this vision of the future, you belong here.

---

## 🔐 Gatekeeper Mode Architecture

### Role Split: Local Commander vs. Cloud Worker

Gatekeeper Mode separates concerns between two completely distinct roles:

```
User: "Convert this Swift code to Rust"
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│  🧠 LOCAL COMMANDER  (any 7B–26B Ollama/MLX/BitNet LLM) │
│  Role: Intent Classification & Memory Orchestration     │
│  • "Swift → Rust" → StructuralCommand                  │
│  • Decides which JCross transformation applies         │
│  • Selects target files from Vault index               │
│  • Generates IR query — NOT the actual code            │
│  • Validates Cloud LLM response, triggers retry        │
│  • Final security gate: ensures no real values leak    │
│  ⚡ Even a 7B model handles classification reliably    │
│  ⚡ Model size does NOT affect output code quality     │
└─────────────────────────────────────────────────────────┘
        │  JCross IR (meaning-zero structural puzzle)
        │  e.g. [迅:1.0][錆:0.9] TRANSFORM → ...
        ▼
┌─────────────────────────────────────────────────────────┐
│  CLOUD LLM WORKER  (Claude / DeepSeek / GPT-4)          │
│  Role: Structural puzzle solving (blind solver)         │
│  • Sees ONLY abstract JCross IR, never source code      │
│  • Generates GraphPatch (structural diff)               │
│  ★ This determines 70–80% of output code quality        │
└─────────────────────────────────────────────────────────┘
        │  GraphPatch (semantic-zero diff)
        ▼
┌─────────────────────────────────────────────────────────┐
│  VAULT PATCHER  (100% local, deterministic)             │
│  Role: Restore real identifiers from local Vault        │
│  • No AI, no LLM — pure deterministic mapping          │
│  • FUNC_001 → actualFunctionName()                     │
└─────────────────────────────────────────────────────────┘
        │
        ▼
   Final Code Output (real identifiers restored)
```

> **Key insight:** The Commander's model size (7B vs 26B) has **negligible impact on conversion quality**.
> The Commander only performs intent classification (a simple categorization task).
> **Conversion quality is entirely determined by the Cloud LLM (step ②).**
> You can replace the Commander with a smaller model to save RAM without any quality regression.

### ⚠️ Cloud LLM Performance & Model Selection

Because the Cloud LLM receives **meaning-zero JCross IR** instead of natural language source code, its behavior differs from direct prompting:

| Aspect | Impact |
|---|---|
| **General-purpose LLMs** (e.g., Claude Haiku, GPT-3.5) | Moderate degradation (~15-25%). Models rely on semantic cues absent in IR. |
| **Reasoning-specialized LLMs** (e.g., Claude Opus, DeepSeek-R1, o1-preview) | **Minimal to no degradation.** These models excel at structural logic puzzles regardless of naming. |
| **Code-specialized LLMs** (e.g., DeepSeek-Coder, Codestral) | **Recommended.** Pattern-matching on code structure is their strength. |
| **Small Cloud LLMs** (<7B hosted) | Significant degradation. Structural reasoning requires sufficient model capacity. |

> **Recommended configuration:**
> Claude Opus / DeepSeek-R1 / o1-preview as Cloud Worker + gemma4:26b or smaller as Local Commander.
> The Commander's size has negligible impact on output quality — it only classifies intent.

### Failure Recovery: Automatic Retry

When the Cloud LLM's patch fails to apply (compile error, type mismatch, etc.), Verantyx automatically sends the error back to the Cloud LLM as a JCross IR error report and requests a corrected patch. This retry count is configurable in **Settings → Privacy → Gatekeeper Mode → Retry Count**.

---

## ✨ What's New in v0.3.0

### 🚀 Massive IDE Stability Overhaul & Scroll Fixes

**v0.3.0 is a monumental stability release.** We have systemically eliminated the root causes of the most frustrating UI freezes, deadlocks, and scrolling bugs that plagued the IDE during heavy local AI inference.

#### 🔧 Scroll-Freezing & Layout Deadlocks Resolved
- **Trackpad Scroll Lock Fixed:** Fixed a major issue where rapid UI updates during LLM generation (via `processLog`) would force continuous `ScrollViewReader` jumps, completely locking user trackpad scrolling.
- **Hit-Test Boundaries Restored:** Re-applied `.clipped()` boundaries to all `ResizableSplit` panes, ensuring that invisible overflow views no longer intercept pointer events or block hover effects.
- **Gesture Conflict Resolved:** Reverted the `ResizableHSplit` divider gesture from `highPriorityGesture` back to a standard `.gesture` with `minimumDistance: 4`, completely resolving conflicts with macOS native scrolling gestures.

#### 🛡️ MainActor Deadlocks & SIGTERM Crashes Eliminated
- **Asynchronous Disk I/O:** Initializing `SessionStore` and running repository directory scans no longer freeze the main thread at launch. Heavy initialization logic has been moved to safely detached background tasks.
- **Safe Process Execution:** `JCrossVault` no longer runs synchronous `Process().waitUntilExit()` for Git Diff operations on the main thread. It now utilizes non-blocking `Task.detached` patterns that safely return values back to the UI.
- **Golden Threading Rule Enforced:** Eradicated all unsafe `Task.detached { [weak self] }` closures that were previously causing Swift runtime memory races when evaluating `ObservableObject` conformance.

### 🧩 Seamless MCP (Model Context Protocol) Integration
- **Unified Spotlight UI (`MCPQuickPanel`):** Press `⌘⇧M` from anywhere to summon a floating, fuzzy-searchable overlay to instantly invoke MCP tools, connect servers, and manage capabilities without leaving your code.
- **One-Click Templates:** Add full servers like GitHub, Brave Search, FileSystem, and PostgreSQL in seconds via the pre-configured template picker.

### 🧬 Self-Evolution & Continuous Integration
- **SelfEvolutionView Integration:** The IDE can now build itself, apply its own patches, and run a virtual CI pipeline. It even generates and submits GitHub PRs directly from the editor using a single unified interface.

### ⚡ BitNet b1.58 Integration Guard
- `BitNetCommanderEngine` now robustly verifies installation state before attempting to run local 1-bit inference, gracefully failing over to Ollama if the 800MB local model is unavailable, rather than silently hanging the orchestrator.

### 🕵️‍♂️ Biometric Stealth Browser (New in v0.4.0)
- **Hybrid Injection Pipeline**: The agent now physically drives a headless browser using OS-level macOS `CGEvent` simulation combined with DOM-level JavaScript synchronization.
- **BotGuard Evasion**: Captures the user's actual typing cadence (keyboard entropy) and mouse trajectories (mouse entropy) during chat interactions, and replays them perfectly during agent web searches to bypass Cloudflare and reCAPTCHA bot detection.
- **Zero-Steal Focus**: The agent injects physical keystrokes and DOM updates invisibly in the background without stealing the user's OS keyboard focus, allowing parallel multitasking while the agent scours the web.

---

## ✨ Features

| Feature | Status |
|---|---|
| 🤖 Ollama integration (gemma4:26b, etc.) | ✅ v0.1.0 |
| ⚡ MLX Apple Silicon inference (offline) | ✅ v0.1.0 |
| 🔑 Anthropic Claude integration | ✅ v0.1.0 |
| 💬 Natural language → file edits | ✅ v0.1.0 |
| 🔍 Diff review → one-click Apply | ✅ v0.1.0 |
| 📂 Open any folder as workspace | ✅ v0.1.0 |
| 🔒 Fully offline (no Wi-Fi required) | ✅ v0.1.0 |
| 🧠 JCross long-term memory (Cortex) | ✅ v0.1.0 |
| 🔒 Privacy Gateway: 3-phase PII masking | ✅ v0.1.0 |
| 🧬 Self-Evolution: live IDE self-patching | ✅ v0.1.0 |
| 📜 Session history with restore | ✅ v0.1.0 |
| 🛠️ MCP (Model Context Protocol) client | ✅ v0.1.0 |
| 🪟 Proportional window resize | ✅ v0.2.0 |
| 🏎️ Instant model picker (no blank freeze) | ✅ v0.2.0 |
| 🔧 Deadlock-free @MainActor threading | ✅ v0.3.0 |
| 🖱️ Trackpad UI scroll-freezing fixed | ✅ v0.3.0 |
| 🧠 Commander role visible in Pipeline UI | ✅ v0.3.0 |
| ⚡ BitNet 1.58b integration guard | ✅ v0.3.0 |
| 🧩 Spotlight-style MCP Quick Panel | ✅ v0.3.0 |
| 🕵️‍♂️ Biometric Stealth Browser (Hybrid JS/HID) | ✅ **v0.4.0** |
| 🛡️ BotGuard & Cloudflare bypass simulation | ✅ **v0.4.0** |

---

## 🧠 Verantyx Cortex (Recommended)

Cortex gives the AI persistent long-term memory across sessions using the JCross spatial memory system.

```bash
npx -y @verantyx/cortex setup
```

---

## 🤝 The Contributor Strategy: Join the Core Engineering Team

AST parsing, memory management, and neuro-symbolic transformations are notoriously complex system programming challenges. We know developers can't just "drop in and fix 5 lines of code."

To make contributing highly accessible and incredibly impactful, we have deliberately designed a decoupled architecture:

### 🧠 The Core vs. The Periphery
- **The Core Engine (Maintained by Verantyx):** The complex JCross Topology Matrix, memory classifiers, and Reverse-Transpilation engines.
- **The Periphery (Built by the Community):** The language-specific AST Extraction Parsers.

**We have already built the Python and Swift parsers. We desperately need the open-source community to build the bridges for the rest of the programming world.**

### 🎯 We Need Your Help
If you want to build a serious OSS portfolio in system programming and AI architecture, here is where you can make a massive impact today. Search our issues for these tags:

*   🏷️ **`help wanted` Go AST Parser:** Build the structural extractor that maps Golang `struct` and `interface` to JCross IR.
*   🏷️ **`help wanted` Java/Kotlin AST Parser:** Help bring Verantyx to the massive enterprise Java ecosystem.
*   🏷️ **`good first issue` Rust AST Parser (Partial):** We have the foundation, but need help mapping Rust's lifetime syntax to JCross edges.
*   🏷️ **`good first issue` UI Integrations:** Help us build toggle switches for the JCross/Raw view in the macOS Native Editor.

*We actively review, merge, and mentor contributors on these issues. Your code will directly power the future of secure AI development.*

---

## 🎥 Demos

### Gatekeeper Mode in Action
Protecting intellectual property by converting Swift code into abstracted JCross IR before sending to cloud LLMs.

<video src="https://github.com/Ag3497120/verantyx/releases/download/v1.1.0/gatekeeper_demo.mov" controls="controls" muted="muted" style="max-width: 100%;"></video>

### Local Nano LLM Memory & Kanji Topology
Demonstrating infinite context retention and language enforcement on local 2B models using `[和:1.0]` Kanji Topology memory nodes.

<video src="https://github.com/Ag3497120/verantyx/releases/download/v1.1.0/nano_memory_demo.mov" controls="controls" muted="muted" style="max-width: 100%;"></video>

---

## 🛠 Building from Source (macOS Only)

### Prerequisites
- macOS 14.0+ (Apple Silicon highly recommended)
- Xcode 15+

### Build & Run
1. Clone the repository.
2. Open `VerantyxIDE/Verantyx.xcodeproj` in Xcode.
3. Select the `Verantyx` scheme and hit Run (Cmd+R).

*Note: A Windows port (Rust core + llama.cpp) is on our long-term roadmap, but we are laser-focused on perfecting the macOS MLX architecture first. We will lean heavily on the community for beta testing when the time comes!*
