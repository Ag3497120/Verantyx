<div align="center">
  <h1>🛡️ Verantyx (Verifiable & Auditable AI Engine)</h1>
  <p><b>The Zero-Leakage, Neuro-Symbolic AI Coding Gateway & Native macOS IDE</b></p>

<p>
    <a href="https://github.com/verantyx/verantyx/releases/latest"><img src="https://img.shields.io/badge/version-1.4.0-blue?style=flat-square" alt="Version 1.4.0"></a>
    <img src="https://img.shields.io/badge/platform-macOS%2014%2B-lightgrey?style=flat-square">
    <img src="https://img.shields.io/badge/Apple%20Silicon-optimized-orange?style=flat-square">
    <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square"></a>
  </p>
  <p>
    <a href="README-en.md">English</a> · <a href="README-es.md">Español</a> · <a href="README-pt-BR.md">Português (Brasil)</a> · <a href="README-de.md">Deutsch</a> · <a href="README-fr.md">Français</a> · <a href="README-zh-CN.md">Simplified Chinese</a> · <a href="README-zh-TW.md">Traditional Chinese</a> · <a href="README-ko.md">한국어</a> · <a href="README.md">Japanese</a> · <a href="README-ar.md">العربية</a> · <a href="README-ru.md">Русский</a> · <a href="README-uk.md">Українська</a> · <a href="README-tr.md">Türkçe</a>
  </p>
</div>

---

## What is this?

Verantyx is a local-first, macOS-native coding agent that combines LLM
generation with a disagreement-aware structural reasoning engine (JCross).
It obfuscates your source code into meaningless mathematical puzzles before
sending it to a cloud LLM, so you get frontier-model help without leaking
your actual code.

## 30-second example

```text
$ verantyx gatekeeper ./my_secret_repo
→ source is rewritten into an Opaque Topology puzzle
→ the puzzle (not your code) is sent to the cloud LLM
→ the LLM's suggestion is de-obfuscated and shown as a diff
→ you approve or reject the patch before anything touches disk
```

## What actually works today

- **Gatekeeper mode**: obfuscate → cloud LLM → de-obfuscate → diff review, end to end.
- **Agent mode**: local-model autonomous loop (Ollama/MLX), triple-key activation, tool calling, file read/write/patch.
- **Vera-α memory bridge**: verified, hallucination-free fact store alongside the LLM's own working memory.
- **Stereo-cross 3D graph view**: a live SceneKit visualization of what's actually stored in memory.

Still rough / in progress: Windows/Linux port, full VR bridge immersive mode — see [About](#-about-verantyx) below for the honest version of what's unfinished.

## One thing I actually need help with

**I need a few people to just try the 30-second example above on a fresh macOS machine and tell me if it worked.** That's it — not a code review, not a co-maintainer commitment. See the entry points below for exactly how much time each option takes.

---

## 🙋 Ways to help (pick your time budget)

### 10 minutes
- Read this README and tell me, in one sentence, what product you think this is.
- Report anything unclear in the install steps.
- Clone + open in Xcode, tell me if it builds on your machine (macOS version, Apple Silicon or Intel).

### 30 minutes
- Run the Gatekeeper mode example above on one small repo of your own.
- Try the Agent mode triple-key activation and describe what happened.
- Try feeding it one file with a known bug and see if it localizes the right one.

### Technical contribution
- Check issues tagged `good first issue` / `help wanted` for a specific file, a completion condition, and the test command to verify it.
- If nothing's tagged yet, open an issue describing what you'd want to work on — I'll scope it down to one file / one condition.

If you starred this repo and have five minutes, even just replying with your one-sentence read of what this project is would genuinely help more than the star itself.

---

## 1. 🖥️ Verantyx Gatekeeper (IDE Mode)
**"I want to have the cloud LLM read my company's confidential code safely"**

Gatekeeper mode is the ultimate secure IDE that obfuscates your source code into meaningless mathematical puzzles (Opaque Topology) before passing it to the AI.
👉 [Click here for details of Gatekeeper mode and obfuscation mechanism (README-Gatekeeper.md)](./docs/README-Gatekeeper.md)

## 2. ⚡ Verantyx Agent (Spotlight Mode)
**“I want to fully utilize the most powerful local AI as an extension of my brain”**

It is a hyper-autonomous agent that can be activated by simply pressing the `Control` key three times. It is equipped with internal auditing using Dual Twin, physical blocking of hallucinations using the 1930 metaphor, and a next-generation thinking engine that recognizes PC assets as "your own memories (L3.5)."
👉 [Click here for details and architecture of Agent mode (README-Agent.md)](./docs/README-Agent.md)

## 3. 🥽 Verantyx VR Bridge (PCVR Streaming) — early prototype

A sub-project streaming SteamVR games running on Mac (via D3DMetal/GPTK) directly to Apple Vision Pro over an ultra-low-latency bridge.
- **Mac side (HardwareEncoder)**: a custom OpenVR emulator (`openvr_emulator.cpp`) intercepts DirectX 11 textures from the game engine (Source 2) and hardware-encodes them to HEVC (H.265) via macOS VideoToolbox, streaming to Vision Pro over UDP.
- **Input mapping**: gamepad input (e.g. Joy-Con) is converted to a virtual VR controller via a Python script (`joycon_mapper.py`) and fed back to the game.
- **Status**: 2D window rendering on Vision Pro works today; full immersive VR via CompositorServices (Metal) is the next milestone, not yet done.

---

## 💻 Installation (build from source)

**Requirements:**
- macOS 14.0 or later (Apple Silicon highly recommended)
- Xcode 15.0 or later

```bash
git clone https://github.com/Ag3497120/Verantyx.git
cd Verantyx/cli/VerantyxIDE
open Verantyx.xcodeproj
# Select the Verantyx scheme and press Cmd+R to build and run
```

*Note: a Windows/Linux port (Rust core + llama.cpp) is on the long-term roadmap, but current effort is focused entirely on the native macOS/MLX architecture.*

---

## 📖 About Verantyx

I was previously trying to build a rule-based symbolic AI and realized doing it entirely alone was unrealistic, so I decided to instead build and control the harness layer around today's mainstream AI models myself. (openclaw was getting attention around that time.) From there, the main goal of this project became: obfuscate source code and user requests into a puzzle-like state before handing them to a high-performance cloud AI, to prevent information leakage.

This repo briefly went private because it contained a folder with sensitive material, which reset its star count from 9 to 0 — it's since been fully restored and reorganized to remove overlap with other repos of mine. I'd been mostly pushing releases here while source updates lagged behind; that's now fixed.

Going forward, Japanese is the primary language I write in day to day; English content here is machine-translated and kept for reference.

---

## 🔧 Repository settings and history

**Note on Git settings:** early commits in this repository were made under the local Git username `kofdai`, derived from the developer's macOS account name. This was fixed as of May 24, 2026, and all commits are now correctly attributed to `@Ag3497120`. This is a common local dev-environment setup issue, not a bot or automation artifact. All future contributions will be recorded under the correct author name.
