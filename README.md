<div align="center">
  <h1>🛡️ Verantyx (Verifiable & Auditable AI Engine)</h1>
  <p><b>An experimental substrate for evolving Vera, a persistent neuro-symbolic intelligence</b></p>

  <p>
    <a href="https://github.com/Ag3497120/Verantyx/releases/latest"><img src="https://img.shields.io/badge/version-2.4.6-blue?style=flat-square" alt="Version 2.4.6"></a>
    <img src="https://img.shields.io/badge/platform-macOS%2014%2B-lightgrey?style=flat-square">
    <img src="https://img.shields.io/badge/Apple%20Silicon-optimized-orange?style=flat-square">
    <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square"></a>
  </p>
  <p>
    <a href="README.md">English</a> · <a href="README-es.md">Español</a> · <a href="README-pt-BR.md">Português (Brasil)</a> · <a href="README-de.md">Deutsch</a> · <a href="README-fr.md">Français</a> · <a href="README-zh-CN.md">简体中文</a> · <a href="README-zh-TW.md">繁體中文</a> · <a href="README-ko.md">한국어</a> · <a href="README-ja.md">日本語</a> · <a href="README-ar.md">العربية</a> · <a href="README-ru.md">Русский</a> · <a href="README-uk.md">Українська</a> · <a href="README-tr.md">Türkçe</a>
  </p>
</div>

---

## What is this, really?

> Verantyx is an experimental substrate for evolving Vera, a persistent
> neuro-symbolic intelligence that learns from verified interaction with
> code, tools, interfaces, and the external world.

Put more plainly: **Verantyx is not an IDE that generates answers for you.**
It's a research environment where Vera discovers what it doesn't know, acts
on the outside world to find out, verifies what comes back, and turns the
experience into a reusable structure — so next time it doesn't need to ask
an LLM at all.

```text
Verantyx
└── unified experiment substrate
    ├── Vera            — persistent structure, gaps, verification, reasoning, memory
    ├── JGEN             — hypothesis generation, verbalization, hidden-state intervention
    ├── Computer Use     — screen perception, mouse/keyboard, acting on the outside world
    ├── Agent Runtime    — ReAct loop, tool execution, approval, retry
    ├── Learning Infra   — trajectory storage, structural similarity, skill formation
    └── IDE / CLI        — the interface a human observes and steers the experiment through
```

In this framing, Computer Use inside the IDE isn't a convenience feature —
it's Vera's **sense organs and effectors**: how it observes the outside
world, acts on it, and updates its own structure from what it learns.

### Five layers

1. **Perception** — turn text, code, files, screens, UI state, and tool
   results into structures Vera can actually reason over.
2. **Reasoning** — track missing pieces, contradictions, structural
   similarity, hypotheses, evidence, and typed `UNKNOWN` states.
3. **Acting on the world** — edit files, run commands, search the web,
   drive a browser, operate a GUI, control an application.
4. **Learning** — persist `observe → act → state change → outcome →
   reusable structure` from every real execution.
5. **Evolution verification** — when a new capability is added to Vera,
   measure whether it actually helped: fewer LLM calls, transfer to unseen
   tasks, no growth in bad memories, safety boundaries still held.

The actual product here isn't the UI — it's this closed cognitive loop:

```text
perceive → structure → detect a gap → hypothesize → act
    → world changes → verify → remember → do better next time
```

### Why "low-cost" matters here

Not just API-bill savings — four distinct kinds of cost this architecture
is built to cut:

- **Inference cost** — reuse an action that already worked instead of
  asking an LLM to re-derive it every time.
- **Development cost** — text, code, GUI, and ARC-style tasks all run
  through one shared Vera loop instead of being built as separate,
  one-off agents.
- **Learning cost** — instead of retraining a whole model, update
  structural memory, vector interventions, skills, and reflexes from the
  outside.
- **Experiment cost** — compare model swaps, Vera on/off, intervention
  on/off, memory on/off, and structural-similarity on/off, all inside the
  same IDE.

In that sense Verantyx is closer to an **experiment OS for neuro-symbolic
cognitive architectures** than a general-purpose AI IDE.

### CLI and IDE are two interfaces to one core

```text
Verantyx Core
├── Vera runtime
├── gap graph
├── structural similarity
├── intervention
├── tool protocol
└── experiment logging

Interfaces
├── Verantyx CLI
└── Verantyx IDE
```

The CLI is a reproducible research interface: easy to review, easy to keep
safety boundaries explicit, easy to script and automate, easy to compare
results across runs. The IDE is a high-degrees-of-freedom experiment
device: screen perception, GUI operation, visual-vector intervention,
long-running agents working alongside a human. Neither is a "lite" version
of the other — they're different interfaces onto the same core.

### On BotGuard-style refusals

Because of this framing, "defeat every obstacle in the outside world at any
cost" isn't actually the goal. What matters for a research substrate is the
capability to recognize the boundary of what it's allowed to do, run the
experiment inside that boundary, stop cleanly at the edge, hand off to a
human, and resume later without losing state. Turning a raw `CLICK_FAILED`
into a structured `EXTERNAL_POLICY_BOUNDARY` / `HUMAN_VERIFICATION_REQUIRED`
state — Vera understanding a real-world refusal as a *permission boundary*
rather than an *operation failure* — is itself the more interesting
neuro-symbolic research question, independent of whether any particular
site's automated-traffic detection gets bypassed.

---

## 30-second example

```text
$ verantyx gatekeeper ./my_secret_repo
→ source is rewritten into an Opaque Topology puzzle
→ the puzzle (not your code) is sent to the cloud LLM
→ the LLM's suggestion is de-obfuscated and shown as a diff
→ you approve or reject the patch before anything touches disk
```

## What actually works today

- **Gatekeeper mode**: obfuscate → cloud LLM → de-obfuscate → diff review,
  end to end.
- **Agent mode**: an autonomous loop over local models (Ollama/MLX/BitNet/
  JGEN), triple-key activation, tool calling, file read/write/patch.
- **Vera-harness chat**: Vera-alpha drives `Agent.run()`'s whole ReAct loop
  and streams progress to the IDE over HTTP+SSE. Toggle it from the chat
  input, switch cognition mode (Normal/Experiment/Sleep).
- **Persistent cognitive gap tracking**: anything Vera couldn't answer is
  recorded as a typed `GapNode` and kept, not discarded — you can search
  across structurally similar past gaps.
- **Approval queue for mutating tools**: any tool call with a side effect
  (writing a file, etc.) waits for explicit human approval before it runs.
  The IDE has a dedicated pending-approvals screen.
- **Direct intervention on JGEN's hidden states (experimental)**: structural
  inconsistencies Vera detects get injected into JGEN's hidden layers as
  text labels, and the reaction is observed in a closed loop. Still in the
  tuning stage — see [Wiki: Hidden-State-Reflection](https://github.com/Ag3497120/Verantyx/wiki/Hidden-State-Reflection).
- **Vera-α memory bridge**: a hallucination-free, verified fact store used
  alongside the LLM's own working memory. Facts, procedures, and domain
  modules only become trusted after passing through a human-approval
  quarantine queue.
- **Stereo-cross 3D graph view**: a live SceneKit visualization of what's
  actually stored in memory.

Still rough / in progress: a Windows/Linux port, full VR-bridge immersive
mode, unresolved hang cases with some large local models. Known issues
found through real usage are tracked in [Issues](https://github.com/Ag3497120/Verantyx/issues).
Design background lives in the [Wiki](https://github.com/Ag3497120/Verantyx/wiki);
open design discussion happens in [Discussions](https://github.com/Ag3497120/Verantyx/discussions).

## One thing I actually need help with

**Try the 30-second demo above on a clean macOS machine and tell me whether
it worked.** That's it — not a code review, not a co-maintainer commitment.
See below for how much time each way of helping actually takes.

---

## 🙋 Ways to help (pick your time budget)

### 10 minutes
- Read this README and tell me, in one sentence, what product you think
  this is.
- Report anything unclear in the install steps.
- Clone it, open it in Xcode, and tell me whether it builds on your
  machine (macOS version, Apple Silicon or Intel).

### 30 minutes
- Run the Gatekeeper-mode example above on one small repo of your own.
- Try the Agent-mode triple-key activation and describe what happened.
- Hand it one file with a known bug and see if it localizes the right
  spot.

### Help with translation
- Every non-English README ([日本語](./README-ja.md), and the others linked
  above) is currently a machine-translation draft. If you're a native
  speaker of any of those languages, a PR that rewrites even one paragraph
  into natural phrasing is genuinely useful — you don't need to redo the
  whole file at once.

### Technical contribution
- [Issues](https://github.com/Ag3497120/Verantyx/issues) lists real,
  usage-verified problems (startup errors, hangs waiting on repro, unbuilt
  design items). Look for `good first issue` / `help wanted`.
- Open-ended design questions or ideas go in
  [Discussions](https://github.com/Ag3497120/Verantyx/discussions).
- Read [CONTRIBUTING.md](./CONTRIBUTING.md) for how to send a PR/Issue,
  and the [Wiki](https://github.com/Ag3497120/Verantyx/wiki) for
  architecture background first.

If you've starred this repo and have five minutes, a one-sentence reply
about what you think this project is would genuinely help more than the
star itself.

---

Verantyx is a next-generation neuro-symbolic logic engine aimed at making
AI-driven software development fully controllable and safe. On top of one
core engine (JCross / L3.5 Memory) it offers **two different frontends** —
pick whichever matches what you're trying to do.

---

## 1. 🖥️ Verantyx Gatekeeper (IDE Mode)
**"I want the cloud LLM to safely read my company's confidential code."**

Gatekeeper mode is the secure IDE that obfuscates your source code into
meaningless mathematical puzzles (Opaque Topology) before it ever reaches
the AI.
👉 [Details on Gatekeeper mode and the obfuscation mechanism (README-Gatekeeper.md)](./docs/README-Gatekeeper.md)

## 2. ⚡ Verantyx Agent (Spotlight Mode)
**"I want to use the strongest local AI as a genuine extension of my brain."**

A hyper-autonomous agent activated by pressing `Control` three times. It
carries internal auditing via Dual Twin, hallucination blocking via the
1930 metaphor, and a thinking engine that treats your machine's own assets
as "its own memory (L3.5)."
👉 [Details and architecture of Agent mode (README-Agent.md)](./docs/README-Agent.md)

## 3. 🥽 Verantyx VR Bridge (PCVR Streaming)
**"Run Half-Life: Alyx on a Mac, play it on Vision Pro."**

A new sub-project: an ultra-low-latency VR bridge that streams SteamVR
games running on a Mac (via D3DMetal/GPTK) directly to Apple Vision Pro.
- **Mac side (HardwareEncoder)**: a custom OpenVR emulator
  (`openvr_emulator.cpp`) intercepts DirectX 11 textures from the game
  engine (Source 2) and hardware-encodes them to HEVC (H.265) via macOS
  VideoToolbox, streamed straight to Vision Pro over UDP.
- **Input mapping**: gamepad input (e.g. Joy-Con) is converted to a
  virtual VR controller via a Python script (`joycon_mapper.py`) and fed
  back into the game.
- **Status**: 2D window rendering on Vision Pro works today; full
  immersive VR via CompositorServices (Metal) is the next target, not yet
  done.

---

## 💻 Installation (build from source)

**Requirements:**
- macOS 14.0 or later (Apple Silicon strongly recommended)
- Xcode 15.0 or later

```bash
git clone https://github.com/Ag3497120/Verantyx.git
cd Verantyx/cli/VerantyxIDE
open Verantyx.xcodeproj
# Select the Verantyx scheme and press Cmd+R to build and run
```

*Note: a Windows/Linux port (Rust core + llama.cpp) is on the long-term
roadmap, but current effort is focused entirely on the native macOS/MLX
architecture.*

---

## 📖 About Verantyx

This project started from an earlier, failed attempt to build a
rule-based symbolic AI by hand — building the whole thing solo turned out
to be unrealistic, so I decided to instead build and control the harness
layer around today's mainstream AI myself (around the time openclaw was
getting attention). The first concrete goal that came out of that was
defensive: obfuscate source code and user requests into a puzzle-like
state before handing them to a high-performance cloud AI, so nothing
leaks.

That harness kept growing, and at some point it stopped being just "a
safe way to call an LLM" and became something else: Vera, a persistent
structure that remembers what it doesn't know, tracks it as a typed gap
instead of forgetting it, and slowly turns verified experience into
reusable knowledge instead of re-deriving everything from a prompt every
time. Verantyx, as it exists today, is the experimental substrate built
around growing that structure — the neuro-symbolic framing at the top of
this README isn't marketing language layered on afterward; it's the
actual reason most of the current architecture (GapNode tracking, the
tool-call approval queue, hidden-state intervention, structural-similarity
transfer) exists.

The reason this repo sat at zero stars for a while: it briefly went
private because it contained a folder with sensitive material, which reset
its star count from 9 to 0. It's since been fully restored, and I've
cleaned up parts that overlapped with my other repos. I'd been mostly
pushing releases here while source updates lagged behind; that's now
fixed.

I write and think primarily in Japanese day to day, so [README-ja.md](./README-ja.md)
is the version I maintain most directly; this English README is the one I
keep current for the project's public face. The other language versions
are still machine-translation drafts — see "Help with translation" above
if you'd like to fix that for your own language.

---

## 🔧 Repository settings and history

**Note on Git settings:** early commits in this repository were made under
the local Git username `kofdai`, derived from the developer's macOS
account name. This was fixed as of May 24, 2026, and all commits are now
correctly attributed to `@Ag3497120`. This is a common local
dev-environment setup issue, not a bot or automation artifact. All future
contributions will be recorded under the correct author name.

---

## 📚 Docs & community

- **[Wiki](https://github.com/Ag3497120/Verantyx/wiki)** — architecture and
  design background (Vera-as-harness, GapNode, hidden-state intervention
  experiment results, and more)
- **[Issues](https://github.com/Ag3497120/Verantyx/issues)** — known
  issues found through real usage
- **[Discussions](https://github.com/Ag3497120/Verantyx/discussions)** —
  open design discussion
- **[CONTRIBUTING.md](./CONTRIBUTING.md)** — how to contribute
- **[SECURITY.md](./SECURITY.md)** — how to report a vulnerability
- **[CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md)** — code of conduct
