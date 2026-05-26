<div align="center">
  <h1>🛡️ Verantyx IDE & Cortex Engine</h1>
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

## 📖 About Verantyx

For this project, when I was previously trying to create a rule-based symbolic AI, I realized that it would be impossible to create it by myself, so I decided to control it by creating the parts that are controlled by myself, such as the harness part of the currently mainstream AI. (At that time, openclaw was attracting attention)
From there, I started developing this project because I thought it would be possible to prevent information leaks by obfuscating the source code and user requests in a puzzle-like state before passing them on to high-performance AI in the cloud.

The reason why this project has 0 stars is because it contained a secure folder and I suddenly made it a private repository, so the 9 stars disappeared. Thank you for your continued support as I have completely recovered. I have sorted out parts that seem to overlap with other repositories. I was mainly pushing releases in this repository, but I found that the source code update was delayed and updated it.

From now on, I'm thinking of focusing on Japanese, my native language, and translating English using a regular translation tool and posting it just in case.

## 🔐 Obfuscation and 6-axis 3D cross structure

The idea behind obfuscating this project is to use a data management method based on the three-dimensional cross structure found in Axis, the predecessor of verantyx, which was created in the early days as an image of how to pass data.

### 🧩 Definition of 6 dimensions (Axis)

| Axis | Name | Role / Extracted elements |
| :--- | :--- | :--- |
| **X-axis** | **Control Flow** | Time and order axis. `if` branches, `for` loops, exception handling, etc. |
| **Y-axis** | **Data Flow** | Dependency axis. Variable assignment, argument passing, etc. |
| **Z-axis** | **Type Constraints** | Boundary axis. Class definitions, type annotations, generics, etc. |
| **W axis** | **Memory Lifecycle** | Axis of life. Scope lifetime, memory allocation/release. |
| **V axis** | **Scope Hierarchy** | Axis of inclusion. Module, class nesting structure. |
| **U axis** | **Semantics & Meaning** | **★Most important★ Axis of business intention. Concrete variable names, function names, raw strings, and numbers. ** |

The conversion process is instantly performed locally on your MacBook by Verantyx's **Gatekeeper Engine**.

---

### 🔄 Raw code to Opaque Topology conversion mechanism

#### Step 1: Parsing and decomposition into AST (Abstract Syntax Tree)
First, the Gatekeeper engine (rule-based recommended) parses the target source code and converts the program structure into tree-structured data called AST (Abstract Syntax Tree).
At this point, all information is still included, such as ``which function is calling what,'' ``what are the variable names, and what is defined as a string?''

#### Step 2: "Physical separation and isolation" of semantics (U axis)
This is where Verantyx shines. Physically strip away all **information indicating the meaning (intention) of the business = U-axis** from the AST.

* **Things that are stripped away (U axis)**: Variable names, function names, strings, fixed numbers, etc.
* **What remains (X, Y, Z, W, V axes)**: The logical framework of ``assigning a variable,'' ``calling a function,'' ``branching with an if statement,'' and ``looping with a for statement.''

The stripped specific name and string data is securely stored locally in your Mac's **`JCrossIRVault` (vault)** and is never sent outside.

#### Step 3: Fully encrypted to Opaque Node
The remaining “bones”, stripped of meaning, are transformed into a fully opaque representation for sending to cloud LLM.

* **`NODE[0x...]` (Node ID)**: All variables and syntax elements are replaced with identifiers, such as random memory addresses.
* **`ARITY` (arity/number of terms)**:
    * `class.nullary`: An element with no arguments or content (just a value or a terminal node).
    * `class.standard`: Standard unary and binary operations (A + B, assignment, etc.).
    * `class.multiway`: Complex structures with multiple elements (for loops, if-else branches, function definitions, etc.).
* **`HASH` (Structural Hash)**: A checksum that shows where the node is in the graph and how it is connected to its surroundings. This allows you to locally verify that the structure is not broken when LLM solves the puzzle and returns it.

Even the original code statement disappears and becomes a pure mathematical graph: `class.multiway` nodes iterate over their child nodes.''

#### Step 4: Injecting “decoys” to prevent statistical inference
If you send your code in a graph structure to an external party, there is a risk that advanced AI or malicious attackers will statistically infer (reverse engineer) that the shape of this graph is the shape of a common script.

To prevent this, we randomly inject **fake nodes (decoys)** into the gaps in the graph.
```text
// _TOKEN_匶:0.2___jcross_BM_505__ [decoy-metadata]
````
By mixing in these meaningless Kanji tokens and dummy connections, the very shape of the graph is distorted, making it mathematically impossible for external AI to deduce the true identity of the original source code.

---

### 🧩 How does LLM “fix” this? (Restoration process)

1. **Solve as a puzzle**:
   Without knowing the original code, LLM infers the value of the target change from the indicated context and the shape of the graph (ARITY and HASH connections).
2. **Returning the structural patch**:
   LLM only returns structural patches (GraphPatch) in JSON format that rewrite the content.
3. **Local Reverse Transpilation**:
   Mac's Gatekeeper engine receives the patch and re-injects the real variable name and string (U-axis) that were hidden in `JCrossIRVault` earlier into the patch.

As a result, a magical development experience with no information leakage is achieved, where ``Even though the external AI has not seen or understood a single line of the original code, when it returns to the local code, the code has been rewritten correctly.''** *There may be information leaks that I have overlooked, so if you notice any, please let us know via issue.

---

## ⚠️ Tasks that I am currently unable to handle (I am not good at)

Currently, this structure cannot handle tasks such as **Rewriting from Swift to Rust**, which is typically the weakest task. Also, tasks 1 to 4 below are difficult for me.

### 1. Refactorings and bug fixes that depend on “semantics (domain knowledge)”
Since the external LLM only sees the skeleton of `NODE[0x...]`, it cannot deal with ``problems that cannot be solved without understanding the meaning of the code''.
* **❌ Example of a weak instruction**: "Add the prefix `auth_` to the names of all variables related to authentication."
* **Reason**: LLM has no visibility into "which authentication process".

### 2. Addition of new functions that strongly depend on external libraries (API)
All `import` statements and library calls in the source code are also encrypted as `NODE`, making tasks that require knowledge of specific libraries difficult.
* **❌ Example of weak instructions**: "Add the ability to upload files to AWS S3"
* **Reason**: LLM does not know which external libraries the current code is using.

### 3. Writing “an entire new feature from scratch”
Gatekeeper is extremely powerful at ``patch and modify existing structures (AST),'' but it is weak at ``creating huge new features that have both meaning (U-axis) and structure from a blank slate.''

### 4. Deterioration of inference due to ineffectiveness of “prior learned knowledge” of LLM itself
LLMs like Gemma and Claude have gotten smarter by studying source code from all over the world, but the format Verantyx sends is ``a graph of pure symbols and hashes unlike any other language in the world.''
* **Reason**: Because LLM's specialty, ``pattern recognition from the code context,'' is blocked, it becomes a difficult mathematical graph puzzle that you have never seen before, causing an increase in calculation costs.

### 💡 How are you overcoming it? (Future outlook)
Currently, Verantyx is implementing a combination of ``Tri-Layer JCross Memory'' and **Visual Anchors to overcome these weaknesses. We take an approach where only secure metadata that does not contain sensitive information is partially presented to LLM as visual anchors, giving hints while maintaining security.

---

## 📽️ Demo video and code conversion in action

<p align="center">
  <img src="demo.gif" alt="Verantyx Gatekeeper Demo" width="49%" style="border-radius: 8px;">
  <video src="https://github.com/verantyx/verantyx/releases/download/v1.2.5/demo_skill_generation.mov" controls="controls" muted="muted" width="49%" style="border-radius: 8px;"></video>
</p>

### Before & After: Obfuscation in action

**[Before] Raw Source Code (Local Environment)**
```python
import json
import os
import shutil
import requests
import subprocess
import re
from tqdm import tqdm
import sys

# Import our new parser
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
from verantyx.cross_engine.jcross_extraction_parser import JCrossExtractionParser

ORACLE_FILE = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/data/longmemeval_m_cleaned.json"
TARGET_DIR = "/Users/motonishikoudai/verantyx-cli/verantyx-browser/.ronin/jcross_v7"
QUERY_BIN = "/Users/motonishikoudai/verantyx-cli/verantyx-browser/target/release/examples/query_jcross"
MODEL = "gemma4:e2b"
OLLAMA_URL = "http://localhost:11434/api/generate"

FINAL_REPORT = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/official_v7_1_accuracy_report.json"
````

**[After] Gatekeeper JCross Opaque Topology (Sent to Cloud LLM)**
```lisp
;;; 🛡️ GATEKEEPER MODE — JCross IR View
;;; Real identifiers have been replaced with node IDs.
;;; Schema: D59144D1-BE1
;;; Nodes: 124 | Secrets redacted: 3442
;;; Source: cortex/bench_v7_1_puzzle_runner.py
;;;
// JCROSS_6AXIS_BEGIN
// lang:swift doc:0xD5E025

// ── TOP-LEVEL NODES
  NODE[0x7995] kind:opaque TYPE:opaque MEM:opaque HASH:0xb4af0a52 ARITY:class.multiway
  NODE[0x9DB8] kind:opaque TYPE:opaque MEM:opaque HASH:0x504933fd ARITY:class.standard
  NODE[0x627F] kind:opaque TYPE:opaque MEM:opaque HASH:0x97b540cb ARITY:class.multiway
  NODE[0x7F4C] kind:opaque TYPE:opaque MEM:opaque HASH:0x86742e8c ARITY:class.standard
  NODE[0xC79E] kind:opaque TYPE:opaque MEM:opaque HASH:0xd42206c4 ARITY:class.standard
  NODE[0x510B] kind:opaque TYPE:opaque MEM:opaque HASH:0x14b9be4e ARITY:class.nullary
  NODE[0xB5C0] kind:opaque TYPE:opaque MEM:opaque HASH:0xcacb18a2 ARITY:class.standard
// _TOKEN_匶:0.2___jcross_BM_505__ [decoy-metadata]
  NODE[0xE3CF] kind:opaque TYPE:opaque MEM:opaque HASH:0x375a5480
````

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

## 🔧 About repository settings and history

**Notice regarding Git settings:**
Early commits to this repository were made under the local Git name `kofdai`, derived from the developer's macOS username. This issue was fixed as of May 24, 2026, and all commits are now correctly attributed to `@Ag3497120`. This is a common issue in setting up your development environment and is not caused by a bot or automated tool. All future contributions will be recorded with the correct author name.

---

## 💡 Q&A and Appeal (Experimental Features)

Currently, you can start the **Verantyx Agent** by pressing the `Control` key three times.

<p align="center">
  <img src="assets/verantyx_agent_v2.png" alt="Verantyx Agent Interface" width="600" style="border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
</p>

This mode was created as a testing ground for the various IDE modes found in previous applications. In order to review the entire project and focus on the "gatekeeper mode" that is really needed, we have consolidated the experimental features for agent behavior that we have created so far into **Verantyx Agent**.

The main agent features included in previous releases are:

* **Dual Twin audit system**: In order to prevent the problem of AI calling tools and being negligent, we have introduced a mechanism where TwinB audits the validity of TwinA's tool calls by injecting JCross internally.
* **Introduction of Visual Anchor**: We changed from controlling skills and instructions only with prompts to a hybrid method of image injection and prompts using Visual Anchor.
* **Construction of L3.5 OS Asset Map**: In the agent started with Control×3, the internal computer map called "L3.5" is maintained only locally. We instilled in agents the awareness that the assets on their computers are connected to their own intelligence.
* **High-precision GUI operation using AX API**: We have moved from the existing GUI operation using screen recording to reliable and high-precision operation using the OS API tree (accessibility API).
* **Kanji topology compression**: When injecting an L3.5 map into a context, generate an image and use it as a prompt to prevent the context from becoming bloated. By associating a unique compression format called "Kanji Topology" with actual data, we ensured that only the necessary data is injected as appropriate.
* **Agent mode expansion**: Added two types: "Automatic mode" and "Advanced mode".
* **Internal knowledge priority mode**: For power users who use restriction-removal models, we have implemented a mode that allows them to fully utilize local AI not only as an orchestrator but also as the main thinking model and knowledge source.
* **L3.5 dedicated memory line**: To prevent L3.5 map memory from becoming complex and large, we have created a memory line that is completely separate from normal conversation memory.
* **Application to fine-tuning**: We have implemented a function that can be used as a foothold to extract user identity data from memories from L1 to L3.5 and perform fine-tuning on any model (achieving optimization that is not possible with a memory system alone).
* **Adoption of FAR zone structure**: Based on the philosophy of ``organizing memories without deleting them,'' we have adopted a structure that records the transition process such as the task package and title when a task is completed, and drops it into a new layer called the ``FAR zone.'' This ensures that important memories, such as the work process, are retained even after the task is finished.

These are just a few of the features currently being added.
A recent update introduced orchestration (Blind Commander Architecture) using a partially quantized version of `talkie-1930:13b` posted on HuggingFace. Taking advantage of the limitation of ``having only knowledge from 1930'', we use a rule-based intermediary to execute commands, and have the role of converting the user's message into figurative expressions of the time. Additional features are being added that embody the project's "experimental" philosophy.

### 🔄 Future roadmap and oversized challenges

This agent and gatekeeper mode are currently connected in the same storage area, but in the future we plan to implement a function that will allow them to be separated and fine-tuned.

Currently, this agent development has reached a temporary milestone. As I am a student myself, once this agent is able to fully handle the tasks given in Teams etc. (tasks such as ``Create and submit the most recent 〇〇 assignments''), I would like to begin full-scale development of ``Gatekeeper Mode,'' which I am currently working on as an improvement plan. Thank you to everyone who has given a star. Please wait for a while.

Finally, I would like to talk about the extra-large challenge that we have prepared as the culmination of this project.

1. **Porting to Windows version (Rust-based)**: This task is to rewrite the implementation currently written in the Swift language for macOS to Rust-based, so that Windows users can also experience the same gatekeeper function.
2. **Completely break away from cloud dependence**: To grow into an agent that can continue development autonomously using only local LLM without paying expensive API fees. We would like to utilize a 20B class model that runs on a MacBook (such as the recent `qwen3.6:27b`, which is said to be comparable to the highest-end model under certain conditions), operate a coding agent close to the cloud level, and proceed with the project by autonomously making improvements.