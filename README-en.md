<div align="center">
  <h1>🛡️ Verantyx (Verifiable & Auditable AI Engine)</h1>
  <p><b>The Zero-Leakage, Neuro-Symbolic AI Coding Gateway & Native macOS IDE</b></p>

<p>
    <a href="https://github.com/verantyx/verantyx/releases/latest"><img src="https://img.shields.io/badge/version-1.4.0-blue?style=flat-square" alt="Version 1.4.0"></a>
    <img src="https://img.shields.io/badge/platform-macOS%2014%2B-lightgrey?style=flat-square">
    <img src="https://img.shields.io/badge/Apple%20Silicon-optimized-orange?style=flat-square">
    <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square">
  </p>
  <p>
    <a href="README-en.md">English</a> · <a href="README-es.md">Español</a> · <a href="README-pt-BR.md">Português (Brasil)</a> · <a href="README-de.md">Deutsch</a> · <a href="README-fr.md">Français</a> · <a href="README-zh-CN.md">Simplified Chinese</a> · <a href="README-zh-TW.md">Traditional Chinese</a> · <a href="README-ko.md">한국어</a> · <a href="README.md">Japanese</a> · <a href="README-ar.md">العربية</a> · <a href="README-ru.md">Русский</a> · <a href="README-uk.md">Українська</a> · <a href="README-tr.md">Türkçe</a>
  </p>
</div>

---

Verantyx is a next-generation Neuro-Symbolic logic engine that makes AI-powered software development fully controllable and secure.
We offer two different front ends on top of one powerful core engine (JCross/L3.5 Memory). Please choose according to your purpose.

---

## 1. 🖥️ Verantyx Gatekeeper (IDE Mode)
**"I want to have the cloud LLM read my company's confidential code safely"**

Gatekeeper mode is the ultimate secure IDE that obfuscates your source code into meaningless mathematical puzzles (Opaque Topology) before passing it to the AI.
👉 [Click here for details of Gatekeeper mode and obfuscation mechanism (README-Gatekeeper.md)](./docs/README-Gatekeeper.md)

## 2. ⚡ Verantyx Agent (Spotlight Mode)
**“I want to fully utilize the most powerful local AI as an extension of my brain”**

It is a hyper-autonomous agent that can be activated by simply pressing the `Control` key three times. It is equipped with internal auditing using Dual Twin, physical blocking of hallucinations using the 1930 metaphor, and a next-generation thinking engine that recognizes PC assets as "your own memories (L3.5)."
👉 [Click here for details and architecture of Agent mode (README-Agent.md)](./docs/README-Agent.md)

---

## 💻 Installation method (build from source)

**Requirements:**
- macOS 14.0 or later (Apple Silicon highly recommended)
- Xcode 15.0 or later

```bash
git clone https://github.com/Ag3497120/Verantyx.git
cd Verantyx/cli/VerantyxIDE
open Verantyx.xcodeproj
# Select Verantyx scheme and press Cmd+R to build and run
````

*Note: Windows/Linux ports (Rust core + llama.cpp) are on the long-term roadmap, but we are currently extremely focused on completing the native macOS/MLX architecture. *

---

## 📖 About Verantyx

For this project, when I was previously trying to create a rule-based symbolic AI, I realized that it would be impossible to create it by myself, so I decided to control it by creating the parts that are controlled by myself, such as the harness part of the currently mainstream AI. (At that time, openclaw was attracting attention)
From there, I started developing this project because I thought it would be possible to prevent information leaks by obfuscating the source code and user requests in a puzzle-like state before passing them to high-performance AI in the cloud.

The reason why this project has 0 stars is because it contained a secure folder and I suddenly made it a private repository, so the 9 stars disappeared. Thank you for your continued support as I have completely recovered. I have sorted out parts that seem to overlap with other repositories. I was mainly pushing releases in this repository, but I found that the source code update was delayed and updated it.

From now on, I'm thinking of focusing on Japanese, my native language, and translating English using a regular translation tool and posting it just in case.

---

## 🔧 About repository settings and history

**Notice regarding Git settings:**
Early commits to this repository were made under the local Git name `kofdai`, derived from the developer's macOS username. This issue was fixed as of May 24, 2026, and all commits are now correctly attributed to `@Ag3497120`. This is a common issue in setting up your development environment and is not caused by a bot or automated tool. All future contributions will be recorded with the correct author name.