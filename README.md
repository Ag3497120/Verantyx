# 🔒 Verantyx: Enterprise Gatekeeper IDE

> **We're back!** This repository previously had 8 stars before maintenance (went private for security audits).
> GitHub doesn't preserve stars on private/public transitions. If you starred us before, please star again! ⭐
> **A macOS-exclusive Zero-Knowledge Proxy IDE. Let Frontier LLMs fully refactor your code without ever leaking your proprietary secrets to the cloud.**

<p align="center">
  <img src="demo.gif" alt="Verantyx Gatekeeper Demo" style="max-height:640px; width:100%; max-width: 800px;">
</p>

## 🚀 Quick Start
Launch the Gatekeeper daemon instantly with just 3 lines of code:

```bash
git clone https://github.com/Ag3497120/Verantyx.git
cd Verantyx/cli/VerantyxIDE
bash package_dmg.sh 2.4.0
```

---

> [!CAUTION]
> ## 🛑 Break It If You Can
> **To all Security Engineers, Red Teamers, and Cryptographers:**
> Verantyx claims to achieve a "Zero-Trust AI Coding Protocol" via Semantic Air-Gapping. We transform raw business logic into a mathematically stripped topological skeleton (JCross IR) that is safely sent to external LLMs. 
> 
> **The Challenge:** We challenge you to reverse-engineer proprietary business logic, original variable names, or core algorithms *solely* from our JCross IR outputs. If you can break our anonymity layer or find a side-channel statistical vulnerability, show us. 
> 
> **Are you ready to audit the future of Enterprise AI?** 👉 [Audit the Gatekeeper Architecture](#-the-gatekeeper-architecture)

## Overview

**Verantyx** is an enterprise-grade AI IDE designed to solve the critical security dilemma of modern software development: **How can organizations leverage powerful cloud LLMs (like Claude 3.7 or GPT-4o) without exposing their proprietary, confidential source code?**

Verantyx introduces a paradigm shift through its exclusive **Gatekeeper Mode architecture**. Instead of operating as a traditional AI coding assistant that transmits your raw IP to third-party servers, Verantyx utilizes a secure, neuro-symbolic pipeline orchestrated entirely on your local machine.

## 🛡️ The Gatekeeper Architecture

Enterprise codebases contain trade secrets, proprietary algorithms, and sensitive infrastructure logic. Sending this data to cloud APIs is often a severe compliance and security violation.

Verantyx solves this via a dual-model approach:
1. **The Local Orchestrator (SLM):** A local edge model (e.g., Qwen 2.5/3, Llama 3) runs securely on your local GPU/Apple Silicon. It parses your raw source code and abstracts it into an anonymized, topological Intermediate Representation (IR) known as the **JCross L2.5 Map**.
2. **The Cloud Worker (LLM):** The external cloud LLM receives *only* the obfuscated JCross IR (Kanji topology, structural outlines, and type definitions). It generates logic updates based purely on structural intent, completely blind to your actual business logic and variable values.
3. **The Integration Phase:** The local orchestrator receives the generated structural patches and safely weaves them back into the raw source code locally.

Your actual code never leaves your machine. Only the skeleton does.



## ✨ Key Enterprise Features

- **Zero-Trust AI Coding:** Total IP protection. Source code is decoupled into Abstract Syntax Trees and JCross representations before any network request is made.
- **Transpilation Pipeline:** Seamlessly migrate massive legacy codebases (e.g., Swift to Rust) autonomously. The built-in pipeline divides the project into thousands of JCross L2.5 TODOs, feeding them sequentially to the local agent loop without context overflow.
- **JCross Tri-Layer Spatial Memory:** Prevent infinite-loop hallucinations and context degradation. Verantyx compresses decisions and structural knowledge into local `.jcross` files (L1 Kanji, L2 Logic, L3 Context), retrieving them only when the local SLM needs them.
- **Native macOS SwiftUI IDE:** A high-performance, native UI that gives human operators complete visibility into the AI's internal `<think>` processes, memory retrievals, and Gatekeeper translations.

## 📂 Project Structure

```text
.
├── cli/                 # The macOS Swift IDE and Desktop application
│   ├── VerantyxIDE/     # Main SwiftUI IDE (Enterprise Gatekeeper UI)
│   └── verantyx-browser/# Rust-based stealth browser automation for secure research
├── cortex/              # The Agentic Brain & Memory Engine
│   ├── src/verantyx/    # Core TypeScript Gatekeeper routing and memory engines
│   └── jcross-memory/   # High-speed Rust parsers for JCross IR
└── README.md            # This file
```

## 🚀 Deployment & Build

Verantyx is designed for internal enterprise deployments.

### Building from Source (macOS)
Requires Xcode 15+ and macOS 14.0+. Apple Silicon (M1/M2/M3/M4) is highly recommended for running the local SLM Gatekeeper.

```bash
cd cli/VerantyxIDE
bash package_dmg.sh 2.0.0
```

### Local Model Requirements
The Gatekeeper Mode requires a local Ollama or MLX instance running a multimodal-capable edge model (e.g., Qwen3-VL, Llama-3-Vision) to process Visual Task Anchors.

## 📦 How We Release

### For Users (Binary)
```bash
# Download the latest DMG from Releases
# Open VerantyxIDE-2.4.7.dmg
# Drag to Applications folder
```

### For Developers (Source)
```bash
git clone https://github.com/Ag3497120/Verantyx.git
cd Verantyx
git checkout v2.4.7  # ← Important: check out the tag, not main!
bash cli/package_dmg.sh 2.4.7
```

### Release Process
1. Feature development on `main` branch.
2. Maintain sync between Source Code and Binary releases by always cutting DMG from explicit tags (`git tag vX.Y.Z`).

## 🚀 What's New in v2.3

Verantyx v2.3 introduces massive performance optimizations and hardens the Gatekeeper security architecture based on expert LLM reverse-engineering analysis.

### 1. ⚡ Transpilation Concurrency (32x Scalability)
- **Asynchronous TaskGroups:** The JCross transpilation pipeline (`JCrossVault._convertBatch`) has been completely rewritten using Swift's asynchronous `TaskGroup` architecture.
- **Hardware-Aware Scaling:** It now processes with a 32-parallel concurrency limit, fully utilizing enterprise workstations (e.g., 32+ cores). What used to take 5+ minutes for 14,000 files now finishes in under 2 minutes.

### 2. 🧹 Aggressive Exclusion Routing & Stability
- Implemented deep directory-level exclusion filters targeting non-essential structural files (e.g., `benchmarks/`, `envs/`, `test_data/`).
- The pipeline now precisely targets only core logic files, reducing the filesystem indexing overhead by over 50%.
- **Deep Path Resolution Fixes:** Resolved legacy "folder doesn't exist" errors by leveraging recursive `FileManager` directory creation, bypassing brittle string sanitization.

### 3. 🛡️ Semantic Air-Gapped Intermediate Representation
- Addressed advanced security feedback highlighting structural leakage (e.g., function size distributions and entity traceability).
- JCross IR now functions as a true "Semantic Air-Gap", entirely isolating semantic intent from raw obfuscation. External LLMs no longer see localized "obfuscated code", but rather an opaque topology graph.

## 🔐 JCross IR Anonymization Example

Verantyx converts proprietary business logic into an opaque **JCross Intermediate Representation** before it is ever sent to an external cloud LLM. This guarantees zero semantic leakage.

### Before (Raw Source Code)
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

EXTRACTOR_PROMPT = """[System Directive]
You are a pure Information Retrieval (IR) Semantic Extractor. 
Your ONLY job is to extract factual pieces (RDF Triples) from the raw chunks that are relevant to answering the Question.
DO NOT ANSWER THE QUESTION. DO NOT WRITE ANY NATURAL LANGUAGE.
You MUST output EXACTLY in the JCross Fragment format below.

[JCross Extraction Constraint]
If the subject or object of a relevant action is missing, ambiguous, or refers to a pronoun/vague entity (e.g. "that restaurant", "he", "she", "the book"), you MUST set 【状態】 to "欠落" and emit the 【軌道】 command tracing back to the source chunk so the engine can deep-read.
Otherwise, set 【状態】 to "確定".

[Format]
■ JCROSS_FRAG_{{chunk_id}}_{{index}}
【源泉】 {{chunk_id}}
【主体】 {{subject}}
【関係】 {{predicate}}
【客体】 {{object}}
【文脈】 {{context}}
【状態】 確定 | 欠落
【軌道】 [遡: {{chunk_id}}]

Example output if ambiguous:
■ JCROSS_FRAG_1372_1
【源泉】 idx_1372
【主体】 Unknown_Person
【関係】 Will_Work
【客体】 Sunday
【文脈】 Shift_Schedule
【状態】 欠落
【軌道】 [遡: idx_1372]

[Inputs]
Question:
{question}

Raw Chunks:
{evidence}
"""

EXECUTOR_PROMPT = """[System Directive]
You are Verantyx Puzzle Cortex.
Answer the following Question based ONLY on the structured Facts provided.
If the facts do not contain enough information to answer, say "I don't know". 
Keep your answer concise.

[Output Format]
<response>
(Your concise final answer here)
</response>

[Inputs]
Question:
{question}

Structured Facts (Resolved Memory Pieces):
{facts}
"""

def chunk_and_write_haystack(haystack_text, chunk_size=2000):
    if os.path.exists(TARGET_DIR):
        shutil.rmtree(TARGET_DIR)
    os.makedirs(TARGET_DIR)

    chunks = [haystack_text[i:i+chunk_size] for i in range(0, len(haystack_text), chunk_size)]
    for idx, c in enumerate(chunks):
        filepath = os.path.join(TARGET_DIR, f"tm_idx_{idx}.jcross")
        with open(filepath, "w") as f:
            f.write(f"■ JCROSS_NODE_idx_{idx}\\n")
            f.write("【空間座相】 [Z:0]\\n")
            f.write(f"[本質記憶]\\n{c}\\n===\\n")
    return chunks

def query_jcross(q_text, limit=5):
    query_input = {"queries": [q_text], "limit": limit}
    try:
        res = subprocess.run([QUERY_BIN, json.dumps(query_input)], capture_output=True, text=True, env={**os.environ, "JCROSS_TARGET_DIR": TARGET_DIR})
        if res.returncode == 0:
            out_lines = res.stdout.strip().split('\\n')
            for line in reversed(out_lines):
                if line.strip().startswith('{'):
                    try:
                        return json.loads(line).get("results", [])
                    except json.JSONDecodeError:
                        continue
            return []
    except Exception as e:
        print(f"[Rust Error]: {e}")
    return []

def extract_fragments_from_llm(question: str, evidence_text: str) -> str:
    payload = {
        "model": MODEL,
        "prompt": EXTRACTOR_PROMPT.format(question=question, evidence=evidence_text),
        "stream": False,
        "options": {"temperature": 0.0}
    }
    res = requests.post(OLLAMA_URL, json=payload, timeout=90)
    return res.json().get('response', '').strip()

def execute_final_answer_from_llm(question: str, fragments: list) -> str:
    fact_lines = []
    for f in fragments:
        if f.get("state") == "確定":
            fact_lines.append(f"- ({f.get('subject')} -> {f.get('predicate')} -> {f.get('object')} | Context: {f.get('context')})")
            
    facts_str = "\\n".join(fact_lines) if fact_lines else "No solid facts found."
    
    payload = {
        "model": MODEL,
        "prompt": EXECUTOR_PROMPT.format(question=question, facts=facts_str),
        "stream": False,
        "options": {"temperature": 0.2}
    }
    try:
        res = requests.post(OLLAMA_URL, json=payload, timeout=300)
        raw_answer = res.json().get('response', '').strip()
        resp_match = re.search(r"<response>(.*?)</response>", raw_answer, re.DOTALL)
        return resp_match.group(1).strip() if resp_match else raw_answer
    except Exception:
        return "ERROR"

def main():
    print("Loading Oracle...")
    with open(ORACLE_FILE, 'r') as f:
        data = json.load(f)
        
    checkpoint_file = FINAL_REPORT + ".jsonl"
    processed_ids = set()
    hits = 0
    
    if os.path.exists(checkpoint_file):
        with open(checkpoint_file, "r") as f:
            for line in f:
                if line.strip():
                    try:
                        item = json.loads(line)
                        processed_ids.add(item["id"])
                        if item["success"]: hits += 1
                    except json.JSONDecodeError:
                        continue
    
    total = len(data)
    print(f"Executing V7.1 Puzzle Cortex Benchmark: {total} questions against {MODEL}...")
    print(f"Found {len(processed_ids)} existing results. Resuming...")

    for i in tqdm(range(total)):
        if i in processed_ids: continue
        
        item = data[i]
        question = item['question']
        ground_truth = item.get('answer', '')
        haystack = item.get('haystack_sessions', '')
        
        if isinstance(haystack, list):
            haystack_text = "\\n".join([str(h) for h in haystack])
        else:
            haystack_text = str(haystack)
            
        all_chunks = chunk_and_write_haystack(haystack_text, 2000)
        
        # 1. BM25 Retrieval
        evidence_nodes = query_jcross(question, limit=5)
        
        # Keep track of investigated chunk ids so we don't loop infinitely
        investigated_chunks = set([n['key'] for n in evidence_nodes])
        
        final_fragments = []
        deep_read_count = 0
        MAX_DEEP_READS = 2
        
        while deep_read_count <= MAX_DEEP_READS:
            evidence_text = "\\n\\n".join([f"--- Chunk [{n['key']}] ---\\n{n['content']}" for n in evidence_nodes])
            if not evidence_text:
                break
                
            # 2. Puzzle IR Builder
            try:
                llm_output = extract_fragments_from_llm(question, evidence_text)
                print(f"RAW LLM OUTPUT:\\n{llm_output}")
                fragments = JCrossExtractionParser.parse(llm_output)
            except Exception as e:
                import traceback; traceback.print_exc()
                fragments = []
                
            final_fragments.extend(fragments)
            
            # 3. Micro Solver: Constraint & Deep Read Check
            needs_deep_read = False
            next_evidence_nodes = []
            
            for frag in fragments:
                if frag.get("state") == "欠落" and frag.get("trace"):
                    trace_target = frag.get("trace") # expected to be something like "idx_1372"
                    
                    # Extract the numeric index
                    match = re.search(r"idx_(\d+)", trace_target)
                    if match:
                        idx = int(match.group(1))
                        # Grab adjacent chunks
                        for adj in [idx - 1, idx + 1]:
                            adj_key = f"idx_{adj}"
                            if 0 <= adj < len(all_chunks) and adj_key not in investigated_chunks:
                                investigated_chunks.add(adj_key)
                                next_evidence_nodes.append({
                                    "key": adj_key,
                                    "content": all_chunks[adj]
                                })
                                needs_deep_read = True
            
            if needs_deep_read and deep_read_count < MAX_DEEP_READS:
                deep_read_count += 1
                evidence_nodes = next_evidence_nodes
            else:
                break

        # 4. LLM Executor (Final Generation)
        answer = execute_final_answer_from_llm(question, final_fragments)

        success = str(ground_truth).lower() in str(answer).lower() if ground_truth is not None else False
        if success: hits += 1
        
        result = {
            "id": i,
            "question": question,
            "ground_truth": ground_truth,
            "answer": answer,
            "success": success,
            "deep_reads": deep_read_count
        }
        
        with open(checkpoint_file, "a") as f:
            f.write(json.dumps(result) + "\\n")
            
        if i < 3:
            print(f"\\n--- [V7.1 Puzzle Cortex Log: Q{i}] ---")
            print(f"Q: {question}\\nTrue: {ground_truth}\\nPred: {answer}")
            print(f"Deep Reads performed: {deep_read_count}")
            print(f"Fragments Extracted:")
            for f in final_fragments:
                print(f"  - {f}")

    all_results = []
    final_hits = 0
    if os.path.exists(checkpoint_file):
        with open(checkpoint_file, "r") as f:
            for line in f:
                res = json.loads(line)
                all_results.append(res)
                if res["success"]: final_hits += 1

    score = (final_hits / total) * 100
    print(f"\\nV7.1 Puzzle Cortex Score: {score:.2f}% ({final_hits}/{total})")
    
    with open(FINAL_REPORT, "w") as f:
        json.dump({"score": score, "details": all_results}, f, indent=2)

if __name__ == "__main__":
    main()
```

### After (Gatekeeper JCross Opaque Topology)
```text
;;; 🛡️ GATEKEEPER MODE — JCross IR View
;;; Real identifiers have been replaced with node IDs.
;;; Schema: D59144D1-BE1
;;; Nodes: 124 | Secrets redacted: 3442
;;; Source: cortex/bench_v7_1_puzzle_runner.py
;;; 
;;; (To view raw code, toggle "Source File" above)
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
  NODE[0x1C84] kind:opaque TYPE:opaque MEM:opaque HASH:0x5bd486d9 ARITY:class.nullary
  NODE[0x228C] kind:opaque TYPE:opaque MEM:opaque HASH:0xd49cd8d1 ARITY:class.nullary
  NODE[0xEC69] kind:opaque TYPE:opaque MEM:opaque HASH:0x139f33a6 ARITY:class.nullary
  NODE[0x82C3] kind:opaque TYPE:opaque MEM:opaque HASH:0x77e4532a ARITY:class.multiway
  NODE[0xD000] kind:opaque TYPE:opaque MEM:opaque HASH:0x53b71162 ARITY:class.standard
  NODE[0x42EE] kind:opaque TYPE:opaque MEM:opaque HASH:0x980241df
  NODE[0x07B8] kind:opaque TYPE:opaque MEM:opaque HASH:0x442b6020 ARITY:class.nullary
  NODE[0x28FE] kind:opaque TYPE:opaque MEM:opaque HASH:0x00c86ec9 ARITY:class.reduced
  NODE[0xF764] kind:opaque TYPE:opaque MEM:opaque HASH:0x19b8ecb8 ARITY:class.nullary
  NODE[0x8EA0] kind:opaque TYPE:opaque MEM:opaque HASH:0x02a2dab0 ARITY:class.multiway
  NODE[0xB5C0] kind:opaque TYPE:opaque MEM:opaque HASH:0x12a0ca7d ARITY:class.nullary
  NODE[0xC79E] kind:opaque TYPE:opaque MEM:opaque HASH:0x0ccf4889 ARITY:class.reduced
  NODE[0x4873] kind:opaque TYPE:opaque MEM:opaque HASH:0x8e89501b
  NODE[0x25B9] kind:opaque TYPE:opaque MEM:opaque HASH:0xfe0f9697 ARITY:class.multiway
// _TOKEN_匶:0.2___jcross_BM_505__ [decoy-metadata]
  NODE[0xE3CF] kind:opaque TYPE:opaque MEM:opaque HASH:0x375a5480
  NODE[0x93A7] kind:opaque TYPE:opaque MEM:opaque HASH:0x73a6ad24 ARITY:class.multiway
  NODE[0x7995] kind:opaque TYPE:opaque MEM:opaque HASH:0xacd08998 ARITY:class.reduced
  NODE[0x1B54] kind:opaque TYPE:opaque MEM:opaque HASH:0x064e02db ARITY:class.nullary
  NODE[0xEA23] kind:opaque TYPE:opaque MEM:opaque HASH:0xbf738fe7 ARITY:class.nullary
  NODE[0x56E7] kind:opaque TYPE:opaque MEM:opaque HASH:0x930c188b ARITY:class.reduced
  NODE[0x2C34] kind:opaque TYPE:opaque MEM:opaque HASH:0xe17fd472
  NODE[0x1F7E] kind:opaque TYPE:opaque MEM:opaque HASH:0xc5a529f8
  NODE[0x3B8E] kind:opaque TYPE:opaque MEM:opaque HASH:0x8688c6c0 ARITY:class.reduced
  NODE[0xE386] kind:opaque TYPE:opaque MEM:opaque HASH:0x6ad54bb9 ARITY:class.multiway
  NODE[0x4417] kind:opaque TYPE:opaque MEM:opaque HASH:0x734fb097 ARITY:class.multiway
  NODE[0x93A7] kind:opaque TYPE:opaque MEM:opaque HASH:0xb9c5f7da ARITY:class.standard
  NODE[0x8472] kind:opaque TYPE:opaque MEM:opaque HASH:0x889c1e9b ARITY:class.nullary
  NODE[0xB217] kind:opaque TYPE:opaque MEM:opaque HASH:0x7cda6a5c ARITY:class.standard
  NODE[0x2C34] kind:opaque TYPE:opaque MEM:opaque HASH:0xe4378520 ARITY:class.reduced
  NODE[0xC368] kind:opaque TYPE:opaque MEM:opaque HASH:0xd62929ec ARITY:class.reduced
  NODE[0x3B8E] kind:opaque TYPE:opaque MEM:opaque HASH:0xd0bdac57
  NODE[0x45EB] kind:opaque TYPE:opaque MEM:opaque HASH:0xc8237df4 ARITY:class.standard
  NODE[0x4417] kind:opaque TYPE:opaque MEM:opaque HASH:0x0a5b0565 ARITY:class.nullary
  NODE[0x93A7] kind:opaque TYPE:opaque MEM:opaque HASH:0x93770a94 ARITY:class.standard
  NODE[0xDC13] kind:opaque TYPE:opaque MEM:opaque HASH:0x9f2dcb50 ARITY:class.nullary
  NODE[0x62F5] kind:opaque TYPE:opaque MEM:opaque HASH:0x3a79c088 ARITY:class.multiway
  NODE[0x79AC] kind:opaque TYPE:opaque MEM:opaque HASH:0x33fa4a7e
  NODE[0xF850] kind:opaque TYPE:opaque MEM:opaque HASH:0xb92dde80 ARITY:class.nullary
  NODE[0x2C34] kind:opaque TYPE:opaque MEM:opaque HASH:0x45d70e34 ARITY:class.nullary
  NODE[0xC368] kind:opaque TYPE:opaque MEM:opaque HASH:0x6116901c ARITY:class.standard
  NODE[0x3B8E] kind:opaque TYPE:opaque MEM:opaque HASH:0x4d9029db
  NODE[0x4417] kind:opaque TYPE:opaque MEM:opaque HASH:0xbb932004 ARITY:class.reduced
  NODE[0x43B2] kind:opaque TYPE:opaque MEM:opaque HASH:0x48eee8dc ARITY:class.nullary
  NODE[0x93A7] kind:opaque TYPE:opaque MEM:opaque HASH:0x643260b2 ARITY:class.nullary
  NODE[0x4DAC] kind:opaque TYPE:opaque MEM:opaque HASH:0xde26b82a
  NODE[0x4C8C] kind:opaque TYPE:opaque MEM:opaque HASH:0xd2baeb26 ARITY:class.standard
  NODE[0x12BC] kind:opaque TYPE:opaque MEM:opaque HASH:0x5323b175 ARITY:class.nullary
  NODE[0x40AA] kind:opaque TYPE:opaque MEM:opaque HASH:0x9ef63267 ARITY:class.standard
  NODE[0x63AB] kind:opaque TYPE:opaque MEM:opaque HASH:0x7400b79a
  NODE[0xF6EE] kind:opaque TYPE:opaque MEM:opaque HASH:0x1291e2f0 ARITY:class.reduced
  NODE[0xD65F] kind:opaque TYPE:opaque MEM:opaque HASH:0xde6f9079 ARITY:class.standard
  NODE[0x3DD7] kind:opaque TYPE:opaque MEM:opaque HASH:0xb89b91db ARITY:class.multiway
  NODE[0x7995] kind:opaque TYPE:opaque MEM:opaque HASH:0xb5a02e62 ARITY:class.reduced
  NODE[0xAFC2] kind:opaque TYPE:opaque MEM:opaque HASH:0x8fa74143
  NODE[0x1FBF] kind:opaque TYPE:opaque MEM:opaque HASH:0x479cecff ARITY:class.reduced
  NODE[0x1B54] kind:opaque TYPE:opaque MEM:opaque HASH:0xde3ff865 ARITY:class.multiway
  NODE[0xEA23] kind:opaque TYPE:opaque MEM:opaque HASH:0x8ce36b80 ARITY:class.reduced
  NODE[0x2C34] kind:opaque TYPE:opaque MEM:opaque HASH:0xe59adc2d ARITY:class.reduced
  NODE[0x3B8E] kind:opaque TYPE:opaque MEM:opaque HASH:0x055f9c2e ARITY:class.standard
  NODE[0x4417] kind:opaque TYPE:opaque MEM:opaque HASH:0xa31868d6 ARITY:class.standard
  NODE[0x93A7] kind:opaque TYPE:opaque MEM:opaque HASH:0xcfc16ddb ARITY:class.nullary
  NODE[0x6034] kind:opaque TYPE:opaque MEM:opaque HASH:0xc839c3f9 ARITY:class.nullary
  NODE[0x912C] kind:opaque TYPE:opaque MEM:opaque HASH:0x9738e696 ARITY:class.multiway
  NODE[0xE0FC] kind:opaque TYPE:opaque MEM:opaque HASH:0xb82266ec
  NODE[0x674F] kind:opaque TYPE:opaque MEM:opaque HASH:0xf86a22a1
  NODE[0x0C61] kind:opaque TYPE:opaque MEM:opaque HASH:0xfd72e14c ARITY:class.reduced
  NODE[0x1A65] kind:opaque TYPE:opaque MEM:opaque HASH:0x6d1b7193
  NODE[0x034C] kind:opaque TYPE:opaque MEM:opaque HASH:0x61ed7421
  NODE[0x5860] kind:opaque TYPE:opaque MEM:opaque HASH:0xbd89069e ARITY:class.reduced
  NODE[0x9427] kind:opaque TYPE:opaque MEM:opaque HASH:0x2a359749 ARITY:class.reduced
  NODE[0xDDD6] kind:opaque TYPE:opaque MEM:opaque HASH:0xd884efaa ARITY:class.nullary
  NODE[0xEF71] kind:opaque TYPE:opaque MEM:opaque HASH:0xfbb6c939
  NODE[0x5FBA] kind:opaque TYPE:opaque MEM:opaque HASH:0xe7695091 ARITY:class.reduced
  NODE[0xA54F] kind:opaque TYPE:opaque MEM:opaque HASH:0x3fe92299 ARITY:class.reduced
  NODE[0x016B] kind:opaque TYPE:opaque MEM:opaque HASH:0xa6d99976 ARITY:class.multiway
  NODE[0xC79E] kind:opaque TYPE:opaque MEM:opaque HASH:0x8acfe59b
  NODE[0x9F4E] kind:opaque TYPE:opaque MEM:opaque HASH:0x6026a846 ARITY:class.multiway
  NODE[0xC4A4] kind:opaque TYPE:opaque MEM:opaque HASH:0x48f5b0fb ARITY:class.standard
  NODE[0xF538] kind:opaque TYPE:opaque MEM:opaque HASH:0x9b340a56 ARITY:class.nullary
  NODE[0x88E8] kind:opaque TYPE:opaque MEM:opaque HASH:0x6893ef52 ARITY:class.reduced
// _TOKEN_曠:0.6___jcross_XD_665__ [decoy-metadata]
  NODE[0xFF22] kind:opaque TYPE:opaque MEM:opaque HASH:0x9525845c ARITY:class.multiway
  NODE[0xC363] kind:opaque TYPE:opaque MEM:opaque HASH:0xd7e1a85e
  NODE[0x1A65] kind:opaque TYPE:opaque MEM:opaque HASH:0x5f7058de ARITY:class.reduced
  NODE[0x932A] kind:opaque TYPE:opaque MEM:opaque HASH:0x6d3c836d ARITY:class.nullary
  NODE[0x3AA0] kind:opaque TYPE:opaque MEM:opaque HASH:0x1cd4903b ARITY:class.nullary
  NODE[0xAD3F] kind:opaque TYPE:opaque MEM:opaque HASH:0x93e9e6bb
  NODE[0xE230] kind:opaque TYPE:opaque MEM:opaque HASH:0xd469e5ed ARITY:class.reduced
  NODE[0x6EA9] kind:opaque TYPE:opaque MEM:opaque HASH:0x431fe962 ARITY:class.nullary
  NODE[0xE06B] kind:opaque TYPE:opaque MEM:opaque HASH:0xc164ba6c ARITY:class.multiway
  NODE[0x1DF5] kind:opaque TYPE:opaque MEM:opaque HASH:0xbf143921 ARITY:class.reduced
  NODE[0x0A1B] kind:opaque TYPE:opaque MEM:opaque HASH:0xed0cb07c
  NODE[0x065C] kind:opaque TYPE:opaque MEM:opaque HASH:0xf6546a75 ARITY:class.nullary
  NODE[0xBC07] kind:opaque TYPE:opaque MEM:opaque HASH:0x122995f1
// _TOKEN_緋:0.6___jcross_YD_571__ [decoy-metadata]
  NODE[0x6F6E] kind:opaque TYPE:opaque MEM:opaque HASH:0x6d83ae37
  NODE[0xA526] kind:opaque TYPE:opaque MEM:opaque HASH:0x563e5ad5 ARITY:class.nullary
  NODE[0x629B] kind:opaque TYPE:opaque MEM:opaque HASH:0xe2ca197f ARITY:class.standard
  NODE[0xF46F] kind:opaque TYPE:opaque MEM:opaque HASH:0x83f5664c ARITY:class.reduced
  NODE[0xFDEC] kind:opaque TYPE:opaque MEM:opaque HASH:0xb4101b38 ARITY:class.reduced
  NODE[0xFF28] kind:opaque TYPE:opaque MEM:opaque HASH:0x63dc9782
  NODE[0xF4E4] kind:opaque TYPE:opaque MEM:opaque HASH:0xf043e36e
  NODE[0xA4A1] kind:opaque TYPE:opaque MEM:opaque HASH:0xb0da5165 ARITY:class.reduced
  NODE[0x9A35] kind:opaque TYPE:opaque MEM:opaque HASH:0x04c27e6a
  NODE[0xAD3F] kind:opaque TYPE:opaque MEM:opaque HASH:0x3990bf31 ARITY:class.nullary
  NODE[0x54D9] kind:opaque TYPE:opaque MEM:opaque HASH:0x4a3f6afb
  NODE[0xDDD6] kind:opaque TYPE:opaque MEM:opaque HASH:0xd02ae4de ARITY:class.nullary
  NODE[0xAD0A] kind:opaque TYPE:opaque MEM:opaque HASH:0x133b41d5 ARITY:class.standard
  NODE[0xF4E4] kind:opaque TYPE:opaque MEM:opaque HASH:0xdfa91935 ARITY:class.multiway
  NODE[0x49D6] kind:opaque TYPE:opaque MEM:opaque HASH:0x6757701f
  NODE[0xA706] kind:opaque TYPE:opaque MEM:opaque HASH:0x9f1621b7 ARITY:class.reduced
  NODE[0xEDE0] kind:opaque TYPE:opaque MEM:opaque HASH:0xef443244
  NODE[0xEF71] kind:opaque TYPE:opaque MEM:opaque HASH:0x69dc6f5c
  NODE[0xB4CE] kind:opaque TYPE:opaque MEM:opaque HASH:0xef2ea6fd ARITY:class.reduced
  NODE[0xABB1] kind:opaque TYPE:opaque MEM:opaque HASH:0xaf672fb5
  NODE[0x0FA0] kind:opaque TYPE:opaque MEM:opaque HASH:0x8e5878ce
  NODE[0x71D9] kind:opaque TYPE:opaque MEM:opaque HASH:0x16fa401e ARITY:class.reduced
  NODE[0x16E7] kind:opaque TYPE:opaque MEM:opaque HASH:0x1f8c9f2e ARITY:class.reduced
  NODE[0xC4FE] kind:opaque TYPE:opaque MEM:opaque HASH:0x371958f5 ARITY:class.multiway
  NODE[0xF40D] kind:opaque TYPE:opaque MEM:opaque HASH:0xc547a5f7 ARITY:class.nullary
  NODE[0x1932] kind:opaque TYPE:opaque MEM:opaque HASH:0x44a84f61
  NODE[0xEBF2] kind:opaque TYPE:opaque MEM:opaque HASH:0xd564df92 ARITY:class.standard
  NODE[0x9A35] kind:opaque TYPE:opaque MEM:opaque HASH:0x5382b603 ARITY:class.standard
  NODE[0x06E1] kind:opaque TYPE:opaque MEM:opaque HASH:0x2a4d8a3b
  NODE[0x4345] kind:opaque TYPE:opaque MEM:opaque HASH:0xd78b6de7
  NODE[0x8155] kind:opaque TYPE:opaque MEM:opaque HASH:0x0c46a531
  NODE[0xCC24] kind:opaque TYPE:opaque MEM:opaque HASH:0x7ccce26d ARITY:class.multiway
  NODE[0xFFFD] kind:opaque TYPE:opaque MEM:opaque HASH:0x19c7012a ARITY:class.reduced
  NODE[0x6D4B] kind:opaque TYPE:opaque MEM:opaque HASH:0x37bfd8bd ARITY:class.standard
  NODE[0xAD3F] kind:opaque TYPE:opaque MEM:opaque HASH:0x1cf7d35c ARITY:class.reduced
  NODE[0x3182] kind:opaque TYPE:opaque MEM:opaque HASH:0xc38310c7 ARITY:class.nullary
  NODE[0xB5DF] kind:opaque TYPE:opaque MEM:opaque HASH:0x4e9bd206 ARITY:class.nullary
  NODE[0x8B6A] kind:opaque TYPE:opaque MEM:opaque HASH:0x53defc70 ARITY:class.multiway
  NODE[0x34FC] kind:opaque TYPE:opaque MEM:opaque HASH:0xac520ffb ARITY:class.nullary
  NODE[0x6EA9] kind:opaque TYPE:opaque MEM:opaque HASH:0x01ba504f ARITY:class.reduced
  NODE[0x2304] kind:opaque TYPE:opaque MEM:opaque HASH:0xabb9f2dc
  NODE[0xD777] kind:opaque TYPE:opaque MEM:opaque HASH:0x1b8ba299 ARITY:class.reduced
  NODE[0x8D73] kind:opaque TYPE:opaque MEM:opaque HASH:0x1b99ff17 ARITY:class.multiway
  NODE[0x5F54] kind:opaque TYPE:opaque MEM:opaque HASH:0xda49d5f1
  NODE[0xEDE0] kind:opaque TYPE:opaque MEM:opaque HASH:0x53afb02d ARITY:class.standard
  NODE[0xAA05] kind:opaque TYPE:opaque MEM:opaque HASH:0x66b69af9 ARITY:class.multiway
  NODE[0xCF3E] kind:opaque TYPE:opaque MEM:opaque HASH:0x93e4a17a ARITY:class.nullary
  NODE[0xFF63] kind:opaque TYPE:opaque MEM:opaque HASH:0x7e3b514e ARITY:class.reduced
  NODE[0xB767] kind:opaque TYPE:opaque MEM:opaque HASH:0xa73fbf1d ARITY:class.reduced
  NODE[0x0A7E] kind:opaque TYPE:opaque MEM:opaque HASH:0xcdfa84a2 ARITY:class.nullary
  NODE[0xFF63] kind:opaque TYPE:opaque MEM:opaque HASH:0xd1243109
  NODE[0xEBF2] kind:opaque TYPE:opaque MEM:opaque HASH:0xdde90399 ARITY:class.multiway
  NODE[0x4270] kind:opaque TYPE:opaque MEM:opaque HASH:0x9c5a78dc
  NODE[0x06E1] kind:opaque TYPE:opaque MEM:opaque HASH:0xfaceb589
  NODE[0x3046] kind:opaque TYPE:opaque MEM:opaque HASH:0x3882a5be
  NODE[0xFF63] kind:opaque TYPE:opaque MEM:opaque HASH:0xf2d7c429 ARITY:class.multiway
  NODE[0x8803] kind:opaque TYPE:opaque MEM:opaque HASH:0xf8466cbe ARITY:class.nullary
  NODE[0xF40D] kind:opaque TYPE:opaque MEM:opaque HASH:0x38bf2a29 ARITY:class.nullary
  NODE[0xFF28] kind:opaque TYPE:opaque MEM:opaque HASH:0xbac8733f ARITY:class.nullary
  NODE[0x33C7] kind:opaque TYPE:opaque MEM:opaque HASH:0xe0e9e7cd ARITY:class.multiway
  NODE[0x0A7E] kind:opaque TYPE:opaque MEM:opaque HASH:0x96fd359f ARITY:class.reduced
  NODE[0xCCD9] kind:opaque TYPE:opaque MEM:opaque HASH:0x584ad8c6 ARITY:class.nullary
  NODE[0xD4D4] kind:opaque TYPE:opaque MEM:opaque HASH:0xe946ec20 ARITY:class.nullary
  NODE[0xD795] kind:opaque TYPE:opaque MEM:opaque HASH:0xbcc74faa ARITY:class.standard
  NODE[0xDB8C] kind:opaque TYPE:opaque MEM:opaque HASH:0x6e1d12c1 ARITY:class.nullary
  NODE[0xE013] kind:opaque TYPE:opaque MEM:opaque HASH:0xbd0b54a6
  NODE[0x7696] kind:opaque TYPE:opaque MEM:opaque HASH:0x3dd3a1f1 ARITY:class.reduced
  NODE[0xCCD9] kind:opaque TYPE:opaque MEM:opaque HASH:0x26801a7c
  NODE[0xD4D4] kind:opaque TYPE:opaque MEM:opaque HASH:0x1f01ea0f ARITY:class.reduced
  NODE[0x0F66] kind:opaque TYPE:opaque MEM:opaque HASH:0x66ee4fce ARITY:class.standard
  NODE[0xC4A4] kind:opaque TYPE:opaque MEM:opaque HASH:0x20112858
  NODE[0x272B] kind:opaque TYPE:opaque MEM:opaque HASH:0x465f756d ARITY:class.nullary
  NODE[0xF056] kind:opaque TYPE:opaque MEM:opaque HASH:0xb98b5a9a ARITY:class.nullary
  NODE[0x339C] kind:opaque TYPE:opaque MEM:opaque HASH:0x9a8078b7 ARITY:class.multiway
  NODE[0x5755] kind:opaque TYPE:opaque MEM:opaque HASH:0x1670a686 ARITY:class.multiway
  NODE[0x912C] kind:opaque TYPE:opaque MEM:opaque HASH:0x8a31c304
  NODE[0xE0FC] kind:opaque TYPE:opaque MEM:opaque HASH:0x8e543fef ARITY:class.multiway
  NODE[0x38E5] kind:opaque TYPE:opaque MEM:opaque HASH:0x770219e2 ARITY:class.standard
  NODE[0xDE84] kind:opaque TYPE:opaque MEM:opaque HASH:0xdf41019a
  NODE[0xFDB7] kind:opaque TYPE:opaque MEM:opaque HASH:0x8d953bfa ARITY:class.reduced
  NODE[0x1A65] kind:opaque TYPE:opaque MEM:opaque HASH:0x6367c98c ARITY:class.nullary
  NODE[0x3573] kind:opaque TYPE:opaque MEM:opaque HASH:0xc01af62e
  NODE[0xDDD6] kind:opaque TYPE:opaque MEM:opaque HASH:0xa6a39255 ARITY:class.standard
  NODE[0xC833] kind:opaque TYPE:opaque MEM:opaque HASH:0x20642ca8 ARITY:class.standard
  NODE[0xE31B] kind:opaque TYPE:opaque MEM:opaque HASH:0x56aa4050 ARITY:class.multiway
  NODE[0xC4A4] kind:opaque TYPE:opaque MEM:opaque HASH:0x88053904 ARITY:class.nullary
  NODE[0xFF22] kind:opaque TYPE:opaque MEM:opaque HASH:0xff8c388f ARITY:class.standard
  NODE[0xAE15] kind:opaque TYPE:opaque MEM:opaque HASH:0xb5fa5cdd ARITY:class.multiway
  NODE[0xAD3F] kind:opaque TYPE:opaque MEM:opaque HASH:0x38d88af5 ARITY:class.standard
  NODE[0x7670] kind:opaque TYPE:opaque MEM:opaque HASH:0xc8151da2 ARITY:class.standard
  NODE[0xB5C2] kind:opaque TYPE:opaque MEM:opaque HASH:0x6de137fc
  NODE[0xE514] kind:opaque TYPE:opaque MEM:opaque HASH:0x2e87a56c ARITY:class.standard
  NODE[0x1508] kind:opaque TYPE:opaque MEM:opaque HASH:0xf207e9eb ARITY:class.reduced
  NODE[0xC5CF] kind:opaque TYPE:opaque MEM:opaque HASH:0x4d7cf53c ARITY:class.nullary
  NODE[0x611B] kind:opaque TYPE:opaque MEM:opaque HASH:0x28df8e2d ARITY:class.reduced
  NODE[0x9A37] kind:opaque TYPE:opaque MEM:opaque HASH:0x9c9bf1eb ARITY:class.nullary
  NODE[0x6261] kind:opaque TYPE:opaque MEM:opaque HASH:0x896ac9ac ARITY:class.multiway
  NODE[0xE0D9] kind:opaque TYPE:opaque MEM:opaque HASH:0xa9f2f942 ARITY:class.standard
  NODE[0xAD3F] kind:opaque TYPE:opaque MEM:opaque HASH:0xc6399fed ARITY:class.multiway
  NODE[0xCB32] kind:opaque TYPE:opaque MEM:opaque HASH:0x04f29f76 ARITY:class.reduced
  NODE[0x4374] kind:opaque TYPE:opaque MEM:opaque HASH:0x78009cf6 ARITY:class.nullary
  NODE[0xDFFC] kind:opaque TYPE:opaque MEM:opaque HASH:0x8ea03db2 ARITY:class.standard
  NODE[0x43B2] kind:opaque TYPE:opaque MEM:opaque HASH:0x29d7bb5c ARITY:class.multiway
  NODE[0x42C2] kind:opaque TYPE:opaque MEM:opaque HASH:0x0a914d8a ARITY:class.standard
  NODE[0xD7FA] kind:opaque TYPE:opaque MEM:opaque HASH:0x5ec46c2a ARITY:class.nullary
  NODE[0x6261] kind:opaque TYPE:opaque MEM:opaque HASH:0x7c9c0729 ARITY:class.nullary
  NODE[0xCF3E] kind:opaque TYPE:opaque MEM:opaque HASH:0x47bbe025 ARITY:class.standard
  NODE[0x04F2] kind:opaque TYPE:opaque MEM:opaque HASH:0x14af340f ARITY:class.standard
  NODE[0xB13B] kind:opaque TYPE:opaque MEM:opaque HASH:0xa25cf45b ARITY:class.reduced
  NODE[0x42C2] kind:opaque TYPE:opaque MEM:opaque HASH:0x5baad93f
// _TOKEN_緋:0.8___jcross_ZY_509__ [decoy-metadata]
  NODE[0x9F4E] kind:opaque TYPE:opaque MEM:opaque HASH:0x5ce76867 ARITY:class.multiway
  NODE[0x5FAE] kind:opaque TYPE:opaque MEM:opaque HASH:0x58e863d2 ARITY:class.standard
  NODE[0x6261] kind:opaque TYPE:opaque MEM:opaque HASH:0xe81f9057 ARITY:class.multiway
  NODE[0xB13B] kind:opaque TYPE:opaque MEM:opaque HASH:0x6a091b3a ARITY:class.multiway
  NODE[0x0F66] kind:opaque TYPE:opaque MEM:opaque HASH:0x4e9e40d5 ARITY:class.reduced
  NODE[0xC4A4] kind:opaque TYPE:opaque MEM:opaque HASH:0xcfc79888
  NODE[0x272B] kind:opaque TYPE:opaque MEM:opaque HASH:0x9030734e ARITY:class.nullary
  NODE[0xC833] kind:opaque TYPE:opaque MEM:opaque HASH:0x3b4f5fb9 ARITY:class.reduced
  NODE[0xB8A1] kind:opaque TYPE:opaque MEM:opaque HASH:0xc100e0a7 ARITY:class.multiway
  NODE[0x6B34] kind:opaque TYPE:opaque MEM:opaque HASH:0xadb72acc ARITY:class.reduced
  NODE[0xE370] kind:opaque TYPE:opaque MEM:opaque HASH:0x63b5585b
  NODE[0x7E44] kind:opaque TYPE:opaque MEM:opaque HASH:0xc23a51d4 ARITY:class.reduced
  NODE[0xC5CF] kind:opaque TYPE:opaque MEM:opaque HASH:0xb4cc4dc1 ARITY:class.nullary
  NODE[0x0227] kind:opaque TYPE:opaque MEM:opaque HASH:0x50ced6a6 ARITY:class.nullary
  NODE[0x9095] kind:opaque TYPE:opaque MEM:opaque HASH:0x3a55aafe ARITY:class.reduced
  NODE[0x0BE6] kind:opaque TYPE:opaque MEM:opaque HASH:0x4e57e393
  NODE[0x75AA] kind:opaque TYPE:opaque MEM:opaque HASH:0x303b52c9 ARITY:class.multiway
  NODE[0x8EA0] kind:opaque TYPE:opaque MEM:opaque HASH:0xe9bff388 ARITY:class.reduced
  NODE[0x8472] kind:opaque TYPE:opaque MEM:opaque HASH:0xd6302344 ARITY:class.multiway
  NODE[0x37ED] kind:opaque TYPE:opaque MEM:opaque HASH:0x8255e86e
  NODE[0x5348] kind:opaque TYPE:opaque MEM:opaque HASH:0xfb339da7 ARITY:class.reduced
  NODE[0x9DB8] kind:opaque TYPE:opaque MEM:opaque HASH:0x5a9a98bc ARITY:class.nullary
  NODE[0x8472] kind:opaque TYPE:opaque MEM:opaque HASH:0x43de3d83 ARITY:class.standard
  NODE[0x8472] kind:opaque TYPE:opaque MEM:opaque HASH:0x2479db0d ARITY:class.standard
  NODE[0xFA0D] kind:opaque TYPE:opaque MEM:opaque HASH:0xbc7af377
  NODE[0x40B4] kind:opaque TYPE:opaque MEM:opaque HASH:0xc9270b50
  NODE[0x0227] kind:opaque TYPE:opaque MEM:opaque HASH:0x6ed51203 ARITY:class.multiway
  NODE[0xA54F] kind:opaque TYPE:opaque MEM:opaque HASH:0xbc1a0a67 ARITY:class.multiway
  NODE[0x75AA] kind:opaque TYPE:opaque MEM:opaque HASH:0xbf787cfc
  NODE[0xF694] kind:opaque TYPE:opaque MEM:opaque HASH:0x33d535d7 ARITY:class.nullary
  NODE[0xA54F] kind:opaque TYPE:opaque MEM:opaque HASH:0x73cb7938 ARITY:class.reduced
  NODE[0x1B41] kind:opaque TYPE:opaque MEM:opaque HASH:0x04812e34
  NODE[0x1002] kind:opaque TYPE:opaque MEM:opaque HASH:0x79b8548d ARITY:class.multiway
  NODE[0xBA19] kind:opaque TYPE:opaque MEM:opaque HASH:0xe537661c ARITY:class.standard
  NODE[0xCCD9] kind:opaque TYPE:opaque MEM:opaque HASH:0x18d8d517
  NODE[0x28FE] kind:opaque TYPE:opaque MEM:opaque HASH:0x90241143 ARITY:class.nullary
  NODE[0x8EA0] kind:opaque TYPE:opaque MEM:opaque HASH:0xa30747da ARITY:class.nullary
// _TOKEN_匶:0.6___jcross_KH_606__ [decoy-metadata]
  NODE[0x8472] kind:opaque TYPE:opaque MEM:opaque HASH:0xad9281e3 ARITY:class.reduced
  NODE[0x5F4E] kind:opaque TYPE:opaque MEM:opaque HASH:0x27b835b5 ARITY:class.multiway
  NODE[0x912A] kind:opaque TYPE:opaque MEM:opaque HASH:0xb5ef8ec3
  NODE[0x1002] kind:opaque TYPE:opaque MEM:opaque HASH:0xe9388580
  NODE[0x912A] kind:opaque TYPE:opaque MEM:opaque HASH:0xef32a12b ARITY:class.multiway
  NODE[0x81F8] kind:opaque TYPE:opaque MEM:opaque HASH:0x8f7d77a9
  NODE[0x9448] kind:opaque TYPE:opaque MEM:opaque HASH:0xab561010
  NODE[0xCCD9] kind:opaque TYPE:opaque MEM:opaque HASH:0x41c1c2d1 ARITY:class.reduced
  NODE[0x1002] kind:opaque TYPE:opaque MEM:opaque HASH:0xbd8a8940 ARITY:class.nullary
  NODE[0x832B] kind:opaque TYPE:opaque MEM:opaque HASH:0x7ab082bc ARITY:class.nullary
  NODE[0x832B] kind:opaque TYPE:opaque MEM:opaque HASH:0x105df905 ARITY:class.multiway
  NODE[0x832B] kind:opaque TYPE:opaque MEM:opaque HASH:0xc5671008 ARITY:class.reduced
  NODE[0xA54F] kind:opaque TYPE:opaque MEM:opaque HASH:0xe0f0d4ba ARITY:class.reduced
  NODE[0xDC13] kind:opaque TYPE:opaque MEM:opaque HASH:0xcc704207 ARITY:class.nullary
  NODE[0x0BE6] kind:opaque TYPE:opaque MEM:opaque HASH:0x1331f358 ARITY:class.standard
  NODE[0x2910] kind:opaque TYPE:opaque MEM:opaque HASH:0x2431690d ARITY:class.reduced
  NODE[0xAFA0] kind:opaque TYPE:opaque MEM:opaque HASH:0x71c56a5a ARITY:class.nullary
  NODE[0x5B1C] kind:opaque TYPE:opaque MEM:opaque HASH:0x9b146690 ARITY:class.standard
  NODE[0x1A11] kind:opaque TYPE:opaque MEM:opaque HASH:0x555cf446 ARITY:class.standard
  NODE[0x2910] kind:opaque TYPE:opaque MEM:opaque HASH:0x535201c3 ARITY:class.nullary
  NODE[0xAFA0] kind:opaque TYPE:opaque MEM:opaque HASH:0xa6bf79ff ARITY:class.reduced
  NODE[0xE77F] kind:opaque TYPE:opaque MEM:opaque HASH:0x5b23fdf2 ARITY:class.standard
  NODE[0x1020] kind:opaque TYPE:opaque MEM:opaque HASH:0x0eb95dd9 ARITY:class.standard
  NODE[0x0EA9] kind:opaque TYPE:opaque MEM:opaque HASH:0x8a7925b6 ARITY:class.reduced
  NODE[0xEEFF] kind:opaque TYPE:opaque MEM:opaque HASH:0x0d47ea1a ARITY:class.nullary
  NODE[0x7995] kind:opaque TYPE:opaque MEM:opaque HASH:0x4939f0a0 ARITY:class.reduced
  NODE[0x8791] kind:opaque TYPE:opaque MEM:opaque HASH:0xd0d7f21e
  NODE[0x7F4C] kind:opaque TYPE:opaque MEM:opaque HASH:0x9693dff0 ARITY:class.standard
  NODE[0xE47A] kind:opaque TYPE:opaque MEM:opaque HASH:0x1dd0776c ARITY:class.standard
  NODE[0x7A75] kind:opaque TYPE:opaque MEM:opaque HASH:0xafb10a2e ARITY:class.nullary
  NODE[0x5B4A] kind:opaque TYPE:opaque MEM:opaque HASH:0x7f528584 ARITY:class.multiway
  NODE[0x931C] kind:opaque TYPE:opaque MEM:opaque HASH:0xc3a52a30 ARITY:class.reduced
  NODE[0x8472] kind:opaque TYPE:opaque MEM:opaque HASH:0xcf447f20 ARITY:class.multiway
  NODE[0x1A11] kind:opaque TYPE:opaque MEM:opaque HASH:0x2a12f178 ARITY:class.standard
  NODE[0x43B2] kind:opaque TYPE:opaque MEM:opaque HASH:0xa210737f ARITY:class.reduced
  NODE[0x0EA9] kind:opaque TYPE:opaque MEM:opaque HASH:0x2286a17d
  NODE[0xA46A] kind:opaque TYPE:opaque MEM:opaque HASH:0xf7e82619
  NODE[0xCA83] kind:opaque TYPE:opaque MEM:opaque HASH:0x54a96d6a ARITY:class.multiway
  NODE[0xCA2D] kind:opaque TYPE:opaque MEM:opaque HASH:0xb88b42f3 ARITY:class.multiway
  NODE[0x0EA9] kind:opaque TYPE:opaque MEM:opaque HASH:0x90bf8ead
  NODE[0x9E10] kind:opaque TYPE:opaque MEM:opaque HASH:0xab558c7a ARITY:class.standard
  NODE[0xA5BB] kind:opaque TYPE:opaque MEM:opaque HASH:0x7b117487
  NODE[0x511C] kind:opaque TYPE:opaque MEM:opaque HASH:0x42b86ec0 ARITY:class.reduced
  NODE[0xA5BB] kind:opaque TYPE:opaque MEM:opaque HASH:0xee78fca8
  NODE[0xDCFF] kind:opaque TYPE:opaque MEM:opaque HASH:0x41276de8 ARITY:class.multiway
  NODE[0x9E10] kind:opaque TYPE:opaque MEM:opaque HASH:0xd593c69f ARITY:class.multiway
  NODE[0xDCFF] kind:opaque TYPE:opaque MEM:opaque HASH:0xe527dd34 ARITY:class.nullary
  NODE[0x0B4F] kind:opaque TYPE:opaque MEM:opaque HASH:0xe41a0bf0 ARITY:class.reduced
  NODE[0x7931] kind:opaque TYPE:opaque MEM:opaque HASH:0xb2fdf3ce ARITY:class.reduced
  NODE[0x7995] kind:opaque TYPE:opaque MEM:opaque HASH:0xfe80d7d6 ARITY:class.nullary
  NODE[0xC34D] kind:opaque TYPE:opaque MEM:opaque HASH:0x872e6c7d ARITY:class.multiway
  NODE[0xDCFF] kind:opaque TYPE:opaque MEM:opaque HASH:0x1803eca4 ARITY:class.multiway
  NODE[0xF5C3] kind:opaque TYPE:opaque MEM:opaque HASH:0x9bbba775 ARITY:class.multiway
  NODE[0x7995] kind:opaque TYPE:opaque MEM:opaque HASH:0xe0503290
  NODE[0xED13] kind:opaque TYPE:opaque MEM:opaque HASH:0x900cd7cb ARITY:class.multiway
  NODE[0x445B] kind:opaque TYPE:opaque MEM:opaque HASH:0x62c9ee42 ARITY:class.nullary
  NODE[0x7056] kind:opaque TYPE:opaque MEM:opaque HASH:0x96334a40
  NODE[0x445B] kind:opaque TYPE:opaque MEM:opaque HASH:0x358e17ce ARITY:class.reduced
  NODE[0x06A5] kind:opaque TYPE:opaque MEM:opaque HASH:0x48668746 ARITY:class.multiway
  NODE[0xAB2E] kind:opaque TYPE:opaque MEM:opaque HASH:0x60b7b913
  NODE[0x89DE] kind:opaque TYPE:opaque MEM:opaque HASH:0x7bd9cbf7 ARITY:class.nullary
  NODE[0x272B] kind:opaque TYPE:opaque MEM:opaque HASH:0xabab6329 ARITY:class.nullary
  NODE[0x806B] kind:opaque TYPE:opaque MEM:opaque HASH:0x2c91195b ARITY:class.multiway
  NODE[0xFAE6] kind:opaque TYPE:opaque MEM:opaque HASH:0x6dc79d0c ARITY:class.standard
  NODE[0x0BE6] kind:opaque TYPE:opaque MEM:opaque HASH:0xf441cb7d ARITY:class.multiway
  NODE[0x3237] kind:opaque TYPE:opaque MEM:opaque HASH:0xa22ca5d1 ARITY:class.reduced
  NODE[0x7605] kind:opaque TYPE:opaque MEM:opaque HASH:0xbad1df65 ARITY:class.multiway
  NODE[0x12BC] kind:opaque TYPE:opaque MEM:opaque HASH:0x4a510983 ARITY:class.standard
  NODE[0xDC99] kind:opaque TYPE:opaque MEM:opaque HASH:0x96d49424 ARITY:class.nullary
  NODE[0x272B] kind:opaque TYPE:opaque MEM:opaque HASH:0x26fb77b3 ARITY:class.multiway
  NODE[0x01DF] kind:opaque TYPE:opaque MEM:opaque HASH:0x8a8cd0a7 ARITY:class.standard
  NODE[0x5755] kind:opaque TYPE:opaque MEM:opaque HASH:0xce1bbe47
  NODE[0xFAE6] kind:opaque TYPE:opaque MEM:opaque HASH:0x7593acf7 ARITY:class.reduced
  NODE[0x6034] kind:opaque TYPE:opaque MEM:opaque HASH:0x4b0f2b27
  NODE[0xA4A1] kind:opaque TYPE:opaque MEM:opaque HASH:0x9353f9ca
  NODE[0xB8BD] kind:opaque TYPE:opaque MEM:opaque HASH:0xe43dc75d ARITY:class.standard
  NODE[0x8726] kind:opaque TYPE:opaque MEM:opaque HASH:0x679c9ed8 ARITY:class.nullary
  NODE[0x85FC] kind:opaque TYPE:opaque MEM:opaque HASH:0x2f352826 ARITY:class.reduced
  NODE[0x61BA] kind:opaque TYPE:opaque MEM:opaque HASH:0xc3c6d53a
  NODE[0xE0D4] kind:opaque TYPE:opaque MEM:opaque HASH:0xe5b36219 ARITY:class.reduced
  NODE[0x0EA9] kind:opaque TYPE:opaque MEM:opaque HASH:0x0475689a ARITY:class.nullary
  NODE[0x7995] kind:opaque TYPE:opaque MEM:opaque HASH:0xaf379f31
  NODE[0x63AB] kind:opaque TYPE:opaque MEM:opaque HASH:0x370c26d7 ARITY:class.reduced
  NODE[0x7605] kind:opaque TYPE:opaque MEM:opaque HASH:0x69a7b13d ARITY:class.multiway
  NODE[0x627F] kind:opaque TYPE:opaque MEM:opaque HASH:0xaedece84 ARITY:class.reduced
  NODE[0x931F] kind:opaque TYPE:opaque MEM:opaque HASH:0x56938300 ARITY:class.multiway
  NODE[0x7931] kind:opaque TYPE:opaque MEM:opaque HASH:0x43dd56eb
  NODE[0x0EA9] kind:opaque TYPE:opaque MEM:opaque HASH:0xbb5525ce ARITY:class.reduced
  NODE[0x7995] kind:opaque TYPE:opaque MEM:opaque HASH:0x98fed7a2 ARITY:class.multiway
  NODE[0xB13B] kind:opaque TYPE:opaque MEM:opaque HASH:0xb1f449a3 ARITY:class.nullary
  NODE[0x9E10] kind:opaque TYPE:opaque MEM:opaque HASH:0x233ffa9e
  NODE[0x272B] kind:opaque TYPE:opaque MEM:opaque HASH:0x54b941b1 ARITY:class.nullary
  NODE[0xE8E9] kind:opaque TYPE:opaque MEM:opaque HASH:0x9aeeb2d4 ARITY:class.reduced
  NODE[0x0BE6] kind:opaque TYPE:opaque MEM:opaque HASH:0xac44ecbe ARITY:class.standard
  NODE[0x3237] kind:opaque TYPE:opaque MEM:opaque HASH:0x5b6ed1db ARITY:class.reduced
  NODE[0x19EE] kind:opaque TYPE:opaque MEM:opaque HASH:0x2932ec86 ARITY:class.reduced
  NODE[0x74E0] kind:opaque TYPE:opaque MEM:opaque HASH:0xb1c1ebfd ARITY:class.multiway
  NODE[0xDEAB] kind:opaque TYPE:opaque MEM:opaque HASH:0xa2dd7df0 ARITY:class.multiway
  NODE[0x19EE] kind:opaque TYPE:opaque MEM:opaque HASH:0xb69f6a67 ARITY:class.multiway
  NODE[0x7931] kind:opaque TYPE:opaque MEM:opaque HASH:0xb481f396 ARITY:class.multiway
  NODE[0xB8CF] kind:opaque TYPE:opaque MEM:opaque HASH:0xcc992a85 ARITY:class.multiway
  NODE[0x7931] kind:opaque TYPE:opaque MEM:opaque HASH:0x0d827dea ARITY:class.standard
  NODE[0xEBF2] kind:opaque TYPE:opaque MEM:opaque HASH:0x9474f5ca ARITY:class.reduced
  NODE[0xF764] kind:opaque TYPE:opaque MEM:opaque HASH:0xb36deb45 ARITY:class.standard
  NODE[0xBCF4] kind:opaque TYPE:opaque MEM:opaque HASH:0x42d5de43 ARITY:class.multiway
  NODE[0x06E1] kind:opaque TYPE:opaque MEM:opaque HASH:0x3138a07d
  NODE[0x3046] kind:opaque TYPE:opaque MEM:opaque HASH:0x3c8b1310 ARITY:class.nullary
  NODE[0x4270] kind:opaque TYPE:opaque MEM:opaque HASH:0xabd23767 ARITY:class.multiway
  NODE[0xDEAB] kind:opaque TYPE:opaque MEM:opaque HASH:0x5187cf43 ARITY:class.nullary
  NODE[0xC5CF] kind:opaque TYPE:opaque MEM:opaque HASH:0x0431913c
  NODE[0x49E8] kind:opaque TYPE:opaque MEM:opaque HASH:0xf6249cf4
  NODE[0x28FE] kind:opaque TYPE:opaque MEM:opaque HASH:0xc1d28b75 ARITY:class.standard
  NODE[0x46F5] kind:opaque TYPE:opaque MEM:opaque HASH:0x012c2ab9 ARITY:class.multiway
  NODE[0xDEAB] kind:opaque TYPE:opaque MEM:opaque HASH:0xb01587af ARITY:class.standard
  NODE[0xDEA6] kind:opaque TYPE:opaque MEM:opaque HASH:0x8930f726
  NODE[0x7605] kind:opaque TYPE:opaque MEM:opaque HASH:0x0ef610d4 ARITY:class.reduced
  NODE[0x12BC] kind:opaque TYPE:opaque MEM:opaque HASH:0xb41e4161 ARITY:class.standard
  NODE[0xDC99] kind:opaque TYPE:opaque MEM:opaque HASH:0x98beb6f2 ARITY:class.nullary
  NODE[0x272B] kind:opaque TYPE:opaque MEM:opaque HASH:0xd61d024e ARITY:class.standard
  NODE[0x01DF] kind:opaque TYPE:opaque MEM:opaque HASH:0xae5c04ef
  NODE[0xC5CF] kind:opaque TYPE:opaque MEM:opaque HASH:0xe3576afb ARITY:class.standard
  NODE[0xA4A1] kind:opaque TYPE:opaque MEM:opaque HASH:0xd6291fb4 ARITY:class.reduced
  NODE[0x46F5] kind:opaque TYPE:opaque MEM:opaque HASH:0x2696019c ARITY:class.nullary
  NODE[0x38E5] kind:opaque TYPE:opaque MEM:opaque HASH:0x77e4d8d3 ARITY:class.reduced
  NODE[0xB8BD] kind:opaque TYPE:opaque MEM:opaque HASH:0xb2f7c53a ARITY:class.reduced
  NODE[0x8726] kind:opaque TYPE:opaque MEM:opaque HASH:0x02049c6e
  NODE[0x85FC] kind:opaque TYPE:opaque MEM:opaque HASH:0x921f1268 ARITY:class.multiway
  NODE[0x61BA] kind:opaque TYPE:opaque MEM:opaque HASH:0x7809b512 ARITY:class.reduced
  NODE[0xE0D4] kind:opaque TYPE:opaque MEM:opaque HASH:0x4b7b87ce
  NODE[0x0EA9] kind:opaque TYPE:opaque MEM:opaque HASH:0x79bf373a ARITY:class.nullary
  NODE[0x7995] kind:opaque TYPE:opaque MEM:opaque HASH:0xee449b6c
  NODE[0x63AB] kind:opaque TYPE:opaque MEM:opaque HASH:0xe822081a ARITY:class.nullary
  NODE[0x7605] kind:opaque TYPE:opaque MEM:opaque HASH:0xdc18845a ARITY:class.nullary
  NODE[0x627F] kind:opaque TYPE:opaque MEM:opaque HASH:0xff32edf9 ARITY:class.standard
  NODE[0x931F] kind:opaque TYPE:opaque MEM:opaque HASH:0x54a38f35 ARITY:class.nullary
  NODE[0x7931] kind:opaque TYPE:opaque MEM:opaque HASH:0xbd1baed0
// _TOKEN_靄:0.8___jcross_HK_876__ [decoy-metadata]
  NODE[0x0EA9] kind:opaque TYPE:opaque MEM:opaque HASH:0x660acf36 ARITY:class.standard
  NODE[0x7995] kind:opaque TYPE:opaque MEM:opaque HASH:0x6d5e3fec ARITY:class.nullary
  NODE[0xB13B] kind:opaque TYPE:opaque MEM:opaque HASH:0xfd6fdfb6 ARITY:class.standard
  NODE[0x9E10] kind:opaque TYPE:opaque MEM:opaque HASH:0x4b9bd111 ARITY:class.standard
  NODE[0x2D24] kind:opaque TYPE:opaque MEM:opaque HASH:0xe195bbfb ARITY:class.standard
  NODE[0x196E] kind:opaque TYPE:opaque MEM:opaque HASH:0x0bc2c3e3 ARITY:class.multiway
  NODE[0x4CE1] kind:opaque TYPE:opaque MEM:opaque HASH:0x30b2f2c6
  NODE[0xB13B] kind:opaque TYPE:opaque MEM:opaque HASH:0x9b5bf236 ARITY:class.nullary
  NODE[0x2D24] kind:opaque TYPE:opaque MEM:opaque HASH:0xf3325e85 ARITY:class.multiway
  NODE[0xAF81] kind:opaque TYPE:opaque MEM:opaque HASH:0xea168c1c
  NODE[0x9E10] kind:opaque TYPE:opaque MEM:opaque HASH:0xeeeeb30c ARITY:class.nullary
  NODE[0x2D24] kind:opaque TYPE:opaque MEM:opaque HASH:0xd4b2521b ARITY:class.nullary
  NODE[0x770E] kind:opaque TYPE:opaque MEM:opaque HASH:0xd088754b ARITY:class.multiway
  NODE[0xAF81] kind:opaque TYPE:opaque MEM:opaque HASH:0x599a1300 ARITY:class.multiway
  NODE[0x7056] kind:opaque TYPE:opaque MEM:opaque HASH:0x41966b48 ARITY:class.reduced
  NODE[0x445B] kind:opaque TYPE:opaque MEM:opaque HASH:0xb90b31ea ARITY:class.standard
  NODE[0x15EB] kind:opaque TYPE:opaque MEM:opaque HASH:0x36ab3343
  NODE[0xCDDC] kind:opaque TYPE:opaque MEM:opaque HASH:0xa2a5b5c7 ARITY:class.nullary
  NODE[0x0BE6] kind:opaque TYPE:opaque MEM:opaque HASH:0x6e3d6ed3 ARITY:class.nullary
  NODE[0xAB2E] kind:opaque TYPE:opaque MEM:opaque HASH:0x47046283 ARITY:class.reduced
  NODE[0x9834] kind:opaque TYPE:opaque MEM:opaque HASH:0xdd88962b ARITY:class.reduced
  NODE[0x7FB0] kind:opaque TYPE:opaque MEM:opaque HASH:0x46843f7c ARITY:class.standard
  NODE[0x56E7] kind:opaque TYPE:opaque MEM:opaque HASH:0x87b0a850 ARITY:class.reduced
  NODE[0x81F8] kind:opaque TYPE:opaque MEM:opaque HASH:0xab66e6d6 ARITY:class.nullary
  NODE[0x2A89] kind:opaque TYPE:opaque MEM:opaque HASH:0x6c1cbbdd ARITY:class.nullary
  NODE[0x7995] kind:opaque TYPE:opaque MEM:opaque HASH:0x680aa383 ARITY:class.reduced
  NODE[0x1F7E] kind:opaque TYPE:opaque MEM:opaque HASH:0x8a98ed1e ARITY:class.standard
  NODE[0x18F1] kind:opaque TYPE:opaque MEM:opaque HASH:0x25c76a8d ARITY:class.nullary
  NODE[0xAFC2] kind:opaque TYPE:opaque MEM:opaque HASH:0x0697af1d ARITY:class.multiway
  NODE[0xC47D] kind:opaque TYPE:opaque MEM:opaque HASH:0x0012db76
  NODE[0xEDE0] kind:opaque TYPE:opaque MEM:opaque HASH:0x7fd02ee7 ARITY:class.multiway
  NODE[0x8CE1] kind:opaque TYPE:opaque MEM:opaque HASH:0x4bd437ab
  NODE[0xE3B0] kind:opaque TYPE:opaque MEM:opaque HASH:0xe2dec152 ARITY:class.nullary
  NODE[0x8EA0] kind:opaque TYPE:opaque MEM:opaque HASH:0x0e3467a5 ARITY:class.standard
  NODE[0x37ED] kind:opaque TYPE:opaque MEM:opaque HASH:0x9e102696 ARITY:class.multiway
  NODE[0xC47D] kind:opaque TYPE:opaque MEM:opaque HASH:0xfa350b06
  NODE[0xC47D] kind:opaque TYPE:opaque MEM:opaque HASH:0xc403b52a ARITY:class.standard
  NODE[0x81F8] kind:opaque TYPE:opaque MEM:opaque HASH:0x6f1e15b7 ARITY:class.multiway
  NODE[0xDCFF] kind:opaque TYPE:opaque MEM:opaque HASH:0xdf68e75d
  NODE[0x9E10] kind:opaque TYPE:opaque MEM:opaque HASH:0xbc93f0bb ARITY:class.nullary
  NODE[0xDCFF] kind:opaque TYPE:opaque MEM:opaque HASH:0xdbb3bae0
  NODE[0x7995] kind:opaque TYPE:opaque MEM:opaque HASH:0xe5ed05d5 ARITY:class.multiway
  NODE[0xDCFF] kind:opaque TYPE:opaque MEM:opaque HASH:0xe8e5caf3 ARITY:class.nullary
  NODE[0xD578] kind:opaque TYPE:opaque MEM:opaque HASH:0xd1227400 ARITY:class.nullary
  NODE[0xF5C3] kind:opaque TYPE:opaque MEM:opaque HASH:0x71c388a8 ARITY:class.reduced
  NODE[0x44F7] kind:opaque TYPE:opaque MEM:opaque HASH:0x2df13164
  NODE[0x8CE1] kind:opaque TYPE:opaque MEM:opaque HASH:0x335cec1a ARITY:class.multiway
  NODE[0xD578] kind:opaque TYPE:opaque MEM:opaque HASH:0x34057a7b ARITY:class.reduced
  NODE[0xE3B0] kind:opaque TYPE:opaque MEM:opaque HASH:0xf835d6f6 ARITY:class.standard
  NODE[0x006E] kind:opaque TYPE:opaque MEM:opaque HASH:0xcf02eafc ARITY:class.reduced
  NODE[0xD578] kind:opaque TYPE:opaque MEM:opaque HASH:0xd4135ab5 ARITY:class.multiway
  NODE[0x7995] kind:opaque TYPE:opaque MEM:opaque HASH:0xfb1ff5d9 ARITY:class.multiway
  NODE[0xED13] kind:opaque TYPE:opaque MEM:opaque HASH:0x3decd644 ARITY:class.standard
  NODE[0x445B] kind:opaque TYPE:opaque MEM:opaque HASH:0xe8256c8f ARITY:class.nullary
  NODE[0x40B4] kind:opaque TYPE:opaque MEM:opaque HASH:0xd5450524 ARITY:class.multiway
  NODE[0xECD8] kind:opaque TYPE:opaque MEM:opaque HASH:0x149b6794
  NODE[0x1F7E] kind:opaque TYPE:opaque MEM:opaque HASH:0x337340eb
  NODE[0xDE84] kind:opaque TYPE:opaque MEM:opaque HASH:0x9ee12abc ARITY:class.reduced
  NODE[0x9B68] kind:opaque TYPE:opaque MEM:opaque HASH:0xc21efcc4 ARITY:class.standard
  NODE[0xFDB7] kind:opaque TYPE:opaque MEM:opaque HASH:0xa14d2c81 ARITY:class.nullary
  NODE[0x8D4C] kind:opaque TYPE:opaque MEM:opaque HASH:0x859e51fd ARITY:class.multiway
  NODE[0xF09E] kind:opaque TYPE:opaque MEM:opaque HASH:0xee38a3ae ARITY:class.reduced
  NODE[0xECD8] kind:opaque TYPE:opaque MEM:opaque HASH:0xbc22da39
  NODE[0xDC14] kind:opaque TYPE:opaque MEM:opaque HASH:0x8f45fd47 ARITY:class.standard
  NODE[0x12BC] kind:opaque TYPE:opaque MEM:opaque HASH:0x14150ef8 ARITY:class.multiway
  NODE[0xAB2E] kind:opaque TYPE:opaque MEM:opaque HASH:0x4376afbf ARITY:class.standard
  NODE[0x4B46] kind:opaque TYPE:opaque MEM:opaque HASH:0xbe1713a9 ARITY:class.reduced
  NODE[0x40B4] kind:opaque TYPE:opaque MEM:opaque HASH:0x5f0f4f2e ARITY:class.nullary
  NODE[0x2FC4] kind:opaque TYPE:opaque MEM:opaque HASH:0xc11956c7 ARITY:class.nullary
  NODE[0xC34D] kind:opaque TYPE:opaque MEM:opaque HASH:0xebc6f6ad ARITY:class.standard
  NODE[0x8CE1] kind:opaque TYPE:opaque MEM:opaque HASH:0x84734ba5 ARITY:class.multiway
  NODE[0xAB2E] kind:opaque TYPE:opaque MEM:opaque HASH:0xdf5db41a ARITY:class.standard
  NODE[0xB005] kind:opaque TYPE:opaque MEM:opaque HASH:0x2f5e3971 ARITY:class.multiway
  NODE[0xECD8] kind:opaque TYPE:opaque MEM:opaque HASH:0x646ef65c ARITY:class.standard
  NODE[0xF694] kind:opaque TYPE:opaque MEM:opaque HASH:0xcef2836f ARITY:class.multiway
  NODE[0x510B] kind:opaque TYPE:opaque MEM:opaque HASH:0x7d33ca73
  NODE[0x8CE1] kind:opaque TYPE:opaque MEM:opaque HASH:0xe81f96a8 ARITY:class.standard
  NODE[0x1F7E] kind:opaque TYPE:opaque MEM:opaque HASH:0x2bb01ecc ARITY:class.multiway
  NODE[0xD578] kind:opaque TYPE:opaque MEM:opaque HASH:0x4700bb65
  NODE[0x272B] kind:opaque TYPE:opaque MEM:opaque HASH:0xa61a7af7 ARITY:class.reduced
  NODE[0xD578] kind:opaque TYPE:opaque MEM:opaque HASH:0xd97bb691 ARITY:class.nullary
  NODE[0x7931] kind:opaque TYPE:opaque MEM:opaque HASH:0xa97bd67a ARITY:class.standard
  NODE[0x6261] kind:opaque TYPE:opaque MEM:opaque HASH:0x10a1f439 ARITY:class.nullary
  NODE[0xD578] kind:opaque TYPE:opaque MEM:opaque HASH:0x423cef5a
  NODE[0xB1C7] kind:opaque TYPE:opaque MEM:opaque HASH:0x84106d84 ARITY:class.multiway
  NODE[0x7931] kind:opaque TYPE:opaque MEM:opaque HASH:0x1ad3a8a9
  NODE[0xF6CC] kind:opaque TYPE:opaque MEM:opaque HASH:0x587010c7 ARITY:class.multiway
  NODE[0xAEDC] kind:opaque TYPE:opaque MEM:opaque HASH:0x569aa5f4 ARITY:class.standard
  NODE[0xD578] kind:opaque TYPE:opaque MEM:opaque HASH:0xcf4dcfa9 ARITY:class.multiway
  NODE[0xE8E9] kind:opaque TYPE:opaque MEM:opaque HASH:0xd9e06848
  NODE[0xF6CC] kind:opaque TYPE:opaque MEM:opaque HASH:0xde8947d6 ARITY:class.reduced
  NODE[0xDD60] kind:opaque TYPE:opaque MEM:opaque HASH:0x962f9e77 ARITY:class.standard
  NODE[0x0227] kind:opaque TYPE:opaque MEM:opaque HASH:0x9d0fd36a ARITY:class.nullary
  NODE[0xF6CC] kind:opaque TYPE:opaque MEM:opaque HASH:0x657dcf0c
  NODE[0x28FE] kind:opaque TYPE:opaque MEM:opaque HASH:0x2cce9d4c ARITY:class.reduced
  NODE[0x3237] kind:opaque TYPE:opaque MEM:opaque HASH:0x4e3407d9 ARITY:class.multiway
  NODE[0x0227] kind:opaque TYPE:opaque MEM:opaque HASH:0xd3a131a0 ARITY:class.standard
  NODE[0xF6CC] kind:opaque TYPE:opaque MEM:opaque HASH:0x19014034 ARITY:class.multiway
  NODE[0x3237] kind:opaque TYPE:opaque MEM:opaque HASH:0xff1988c8 ARITY:class.reduced
  NODE[0x0227] kind:opaque TYPE:opaque MEM:opaque HASH:0xad946faa ARITY:class.reduced
  NODE[0x9095] kind:opaque TYPE:opaque MEM:opaque HASH:0x75dfc52c
  NODE[0x601C] kind:opaque TYPE:opaque MEM:opaque HASH:0x648a57b5
  NODE[0xCD2D] kind:opaque TYPE:opaque MEM:opaque HASH:0xe794bc6b ARITY:class.standard
  NODE[0x9427] kind:opaque TYPE:opaque MEM:opaque HASH:0x7def0052 ARITY:class.reduced
  NODE[0xDC13] kind:opaque TYPE:opaque MEM:opaque HASH:0xe47cf69b ARITY:class.reduced
  NODE[0x272B] kind:opaque TYPE:opaque MEM:opaque HASH:0xf987c665 ARITY:class.standard
  NODE[0xB7DD] kind:opaque TYPE:opaque MEM:opaque HASH:0x90c43438
  NODE[0x2910] kind:opaque TYPE:opaque MEM:opaque HASH:0xb2776de0 ARITY:class.reduced
  NODE[0xA706] kind:opaque TYPE:opaque MEM:opaque HASH:0x33914cb2 ARITY:class.standard
  NODE[0x984F] kind:opaque TYPE:opaque MEM:opaque HASH:0x759223e6
  NODE[0x59AF] kind:opaque TYPE:opaque MEM:opaque HASH:0x2ea495f5 ARITY:class.standard
  NODE[0xD7FA] kind:opaque TYPE:opaque MEM:opaque HASH:0xe774dfef ARITY:class.standard
  NODE[0x9CAE] kind:opaque TYPE:opaque MEM:opaque HASH:0xd31cc986 ARITY:class.nullary
  NODE[0x37FA] kind:opaque TYPE:opaque MEM:opaque HASH:0x70c7e17f ARITY:class.nullary
  NODE[0x186F] kind:opaque TYPE:opaque MEM:opaque HASH:0x2fb2d9a4 ARITY:class.nullary
  NODE[0xDFFC] kind:opaque TYPE:opaque MEM:opaque HASH:0xc7a63ba9 ARITY:class.reduced
  NODE[0xEDE0] kind:opaque TYPE:opaque MEM:opaque HASH:0x64bda90e ARITY:class.reduced
  NODE[0x2146] kind:opaque TYPE:opaque MEM:opaque HASH:0x4270a7eb ARITY:class.nullary
  NODE[0x96F0] kind:opaque TYPE:opaque MEM:opaque HASH:0xb0173b9a ARITY:class.multiway
  NODE[0xB7DD] kind:opaque TYPE:opaque MEM:opaque HASH:0x3eb152eb ARITY:class.standard
  NODE[0xA13B] kind:opaque TYPE:opaque MEM:opaque HASH:0x0513049b ARITY:class.reduced
  NODE[0xB7D5] kind:opaque TYPE:opaque MEM:opaque HASH:0x1af858aa
  NODE[0xAB9C] kind:opaque TYPE:opaque MEM:opaque HASH:0xb480dceb ARITY:class.standard
  NODE[0xB7D5] kind:opaque TYPE:opaque MEM:opaque HASH:0x0f71c1f4 ARITY:class.reduced
  NODE[0xAB9C] kind:opaque TYPE:opaque MEM:opaque HASH:0x7d65a1c2 ARITY:class.standard
  NODE[0x2146] kind:opaque TYPE:opaque MEM:opaque HASH:0xa2acf61f ARITY:class.multiway
  NODE[0xAD59] kind:opaque TYPE:opaque MEM:opaque HASH:0xfacb2100
  NODE[0xFAE6] kind:opaque TYPE:opaque MEM:opaque HASH:0x71fe9ae9 ARITY:class.reduced
  NODE[0x989F] kind:opaque TYPE:opaque MEM:opaque HASH:0x6c78cddc ARITY:class.reduced
  NODE[0x28FE] kind:opaque TYPE:opaque MEM:opaque HASH:0x090d4f12
  NODE[0xB7DD] kind:opaque TYPE:opaque MEM:opaque HASH:0x08259b86 ARITY:class.multiway
  NODE[0xFAE6] kind:opaque TYPE:opaque MEM:opaque HASH:0xc1a8c885 ARITY:class.multiway
  NODE[0x9A37] kind:opaque TYPE:opaque MEM:opaque HASH:0xa053d144 ARITY:class.multiway
  NODE[0xDE84] kind:opaque TYPE:opaque MEM:opaque HASH:0x2794bf2a ARITY:class.reduced
  NODE[0x1AD4] kind:opaque TYPE:opaque MEM:opaque HASH:0xc53e6083 ARITY:class.multiway
  NODE[0x272B] kind:opaque TYPE:opaque MEM:opaque HASH:0xe1609da9 ARITY:class.multiway
  NODE[0x806B] kind:opaque TYPE:opaque MEM:opaque HASH:0x4f90a1dd ARITY:class.standard
  NODE[0xFAE6] kind:opaque TYPE:opaque MEM:opaque HASH:0xfb8308ab ARITY:class.nullary
  NODE[0xA8FA] kind:opaque TYPE:opaque MEM:opaque HASH:0x58e2fdf6 ARITY:class.reduced
  NODE[0x1717] kind:opaque TYPE:opaque MEM:opaque HASH:0x766a78b1 ARITY:class.standard
  NODE[0xDB51] kind:opaque TYPE:opaque MEM:opaque HASH:0xfbe6ba21 ARITY:class.multiway
  NODE[0x3CFF] kind:opaque TYPE:opaque MEM:opaque HASH:0xa2741486 ARITY:class.multiway
  NODE[0xA8FA] kind:opaque TYPE:opaque MEM:opaque HASH:0x07d88e58 ARITY:class.multiway
  NODE[0xAB2E] kind:opaque TYPE:opaque MEM:opaque HASH:0xddb7ea27 ARITY:class.multiway
  NODE[0xA8FA] kind:opaque TYPE:opaque MEM:opaque HASH:0x434c75d4 ARITY:class.nullary
  NODE[0xED25] kind:opaque TYPE:opaque MEM:opaque HASH:0xdf6a7a8b ARITY:class.nullary
  NODE[0x19EE] kind:opaque TYPE:opaque MEM:opaque HASH:0xa0b7638c
  NODE[0xE3CF] kind:opaque TYPE:opaque MEM:opaque HASH:0xa23f42c9 ARITY:class.nullary
  NODE[0x7056] kind:opaque TYPE:opaque MEM:opaque HASH:0x92007b43 ARITY:class.standard
  NODE[0x445B] kind:opaque TYPE:opaque MEM:opaque HASH:0x44075809 ARITY:class.reduced
  NODE[0x0520] kind:opaque TYPE:opaque MEM:opaque HASH:0xceb48c4f ARITY:class.standard
  NODE[0x5407] kind:opaque TYPE:opaque MEM:opaque HASH:0x0bd32825
  NODE[0x19EE] kind:opaque TYPE:opaque MEM:opaque HASH:0xb91318e0 ARITY:class.nullary
  NODE[0xA13B] kind:opaque TYPE:opaque MEM:opaque HASH:0xf4a00fd9
  NODE[0x6414] kind:opaque TYPE:opaque MEM:opaque HASH:0x2d0aade2 ARITY:class.standard
  NODE[0x19EE] kind:opaque TYPE:opaque MEM:opaque HASH:0x9f72cd0b
  NODE[0x9767] kind:opaque TYPE:opaque MEM:opaque HASH:0x35fa8362 ARITY:class.standard
  NODE[0x86B5] kind:opaque TYPE:opaque MEM:opaque HASH:0xc6624ad3 ARITY:class.multiway
  NODE[0x794F] kind:opaque TYPE:opaque MEM:opaque HASH:0x2b86bd81 ARITY:class.nullary
  NODE[0xAD0A] kind:opaque TYPE:opaque MEM:opaque HASH:0xbdcb7f9e ARITY:class.multiway
  NODE[0xD1B1] kind:opaque TYPE:opaque MEM:opaque HASH:0xa1965c21 ARITY:class.reduced
  NODE[0xC811] kind:opaque TYPE:opaque MEM:opaque HASH:0xfb2b0d6a ARITY:class.standard
  NODE[0xB8BD] kind:opaque TYPE:opaque MEM:opaque HASH:0x6341aeed ARITY:class.nullary
  NODE[0xD484] kind:opaque TYPE:opaque MEM:opaque HASH:0xef5c227e ARITY:class.reduced
  NODE[0x76C8] kind:opaque TYPE:opaque MEM:opaque HASH:0xd2b11245 ARITY:class.multiway
  NODE[0xB7DD] kind:opaque TYPE:opaque MEM:opaque HASH:0x8b9a2a22 ARITY:class.nullary
  NODE[0xEAA8] kind:opaque TYPE:opaque MEM:opaque HASH:0x4ed4ea7a ARITY:class.standard
  NODE[0x19EE] kind:opaque TYPE:opaque MEM:opaque HASH:0xade41c74
  NODE[0x7931] kind:opaque TYPE:opaque MEM:opaque HASH:0xadf4a786 ARITY:class.multiway
  NODE[0xEAA8] kind:opaque TYPE:opaque MEM:opaque HASH:0xf4caffca ARITY:class.nullary
  NODE[0xD6AA] kind:opaque TYPE:opaque MEM:opaque HASH:0x6141d542 ARITY:class.reduced
  NODE[0x2304] kind:opaque TYPE:opaque MEM:opaque HASH:0xed69b52a ARITY:class.standard
  NODE[0xB8CF] kind:opaque TYPE:opaque MEM:opaque HASH:0x6ee71793 ARITY:class.nullary
  NODE[0x7931] kind:opaque TYPE:opaque MEM:opaque HASH:0xb37f3da0 ARITY:class.nullary
  NODE[0xEAA8] kind:opaque TYPE:opaque MEM:opaque HASH:0x5e1db819 ARITY:class.multiway
  NODE[0x58FA] kind:opaque TYPE:opaque MEM:opaque HASH:0x510fd4f9 ARITY:class.multiway
  NODE[0xCCD9] kind:opaque TYPE:opaque MEM:opaque HASH:0x592d0d5e ARITY:class.standard
  NODE[0x3F66] kind:opaque TYPE:opaque MEM:opaque HASH:0xce172d4f ARITY:class.reduced
  NODE[0xD6AA] kind:opaque TYPE:opaque MEM:opaque HASH:0x402ddbee ARITY:class.standard
  NODE[0x3185] kind:opaque TYPE:opaque MEM:opaque HASH:0xa00d44a8
  NODE[0xD4D4] kind:opaque TYPE:opaque MEM:opaque HASH:0x0cd529b8 ARITY:class.reduced
  NODE[0x9CEC] kind:opaque TYPE:opaque MEM:opaque HASH:0xede28bf0 ARITY:class.standard
  NODE[0xCBF1] kind:opaque TYPE:opaque MEM:opaque HASH:0x0d319be0 ARITY:class.multiway
  NODE[0xAD3F] kind:opaque TYPE:opaque MEM:opaque HASH:0x518d570f ARITY:class.multiway
  NODE[0xB767] kind:opaque TYPE:opaque MEM:opaque HASH:0xb33d0466 ARITY:class.multiway
  NODE[0x801F] kind:opaque TYPE:opaque MEM:opaque HASH:0xa872f94b ARITY:class.multiway
  NODE[0x60FC] kind:opaque TYPE:opaque MEM:opaque HASH:0x5eb0c7c2
  NODE[0x196E] kind:opaque TYPE:opaque MEM:opaque HASH:0x5ad30174 ARITY:class.multiway
  NODE[0x58FA] kind:opaque TYPE:opaque MEM:opaque HASH:0x892a6051 ARITY:class.multiway
  NODE[0xCCD9] kind:opaque TYPE:opaque MEM:opaque HASH:0x532c08c8 ARITY:class.standard
  NODE[0x60FC] kind:opaque TYPE:opaque MEM:opaque HASH:0xbe9562a1
  NODE[0x60FC] kind:opaque TYPE:opaque MEM:opaque HASH:0xa9c0a1cd ARITY:class.reduced
  NODE[0x8E19] kind:opaque TYPE:opaque MEM:opaque HASH:0xa5fd2e6d
  NODE[0x1002] kind:opaque TYPE:opaque MEM:opaque HASH:0x0f5ccbbe ARITY:class.standard
  NODE[0x770E] kind:opaque TYPE:opaque MEM:opaque HASH:0xe574a285 ARITY:class.nullary
  NODE[0x31E8] kind:opaque TYPE:opaque MEM:opaque HASH:0x4c53af41 ARITY:class.reduced
  NODE[0xA54F] kind:opaque TYPE:opaque MEM:opaque HASH:0x632f2eee ARITY:class.multiway
  NODE[0x43D4] kind:opaque TYPE:opaque MEM:opaque HASH:0x35a519b7 ARITY:class.reduced
  NODE[0xB58C] kind:opaque TYPE:opaque MEM:opaque HASH:0x466f12fe ARITY:class.reduced
  NODE[0x1002] kind:opaque TYPE:opaque MEM:opaque HASH:0x0ee5dfa3 ARITY:class.nullary
  NODE[0xA393] kind:opaque TYPE:opaque MEM:opaque HASH:0x5039ea0b ARITY:class.multiway
  NODE[0xB58C] kind:opaque TYPE:opaque MEM:opaque HASH:0xb3198acf ARITY:class.reduced
  NODE[0xCCD9] kind:opaque TYPE:opaque MEM:opaque HASH:0x120c9a2d ARITY:class.multiway
  NODE[0xA393] kind:opaque TYPE:opaque MEM:opaque HASH:0xb6e2e177 ARITY:class.reduced
  NODE[0x40B4] kind:opaque TYPE:opaque MEM:opaque HASH:0xbdb56419 ARITY:class.reduced
  NODE[0x96F0] kind:opaque TYPE:opaque MEM:opaque HASH:0x04840769 ARITY:class.reduced
  NODE[0xB58C] kind:opaque TYPE:opaque MEM:opaque HASH:0x29166cad ARITY:class.standard
  NODE[0x601C] kind:opaque TYPE:opaque MEM:opaque HASH:0xd2d3220b ARITY:class.reduced
  NODE[0x9A37] kind:opaque TYPE:opaque MEM:opaque HASH:0xd230949e ARITY:class.multiway
  NODE[0x2304] kind:opaque TYPE:opaque MEM:opaque HASH:0xed346153 ARITY:class.nullary
  NODE[0xA393] kind:opaque TYPE:opaque MEM:opaque HASH:0x93e4e1c5 ARITY:class.nullary
  NODE[0x96F0] kind:opaque TYPE:opaque MEM:opaque HASH:0x297ad1df ARITY:class.standard
  NODE[0x44F7] kind:opaque TYPE:opaque MEM:opaque HASH:0xf91a8094 ARITY:class.reduced
  NODE[0x76C8] kind:opaque TYPE:opaque MEM:opaque HASH:0xa06aff3c ARITY:class.multiway
  NODE[0xF764] kind:opaque TYPE:opaque MEM:opaque HASH:0x453a5e79 ARITY:class.standard
  NODE[0xB7DD] kind:opaque TYPE:opaque MEM:opaque HASH:0x8d900345
  NODE[0xA393] kind:opaque TYPE:opaque MEM:opaque HASH:0xe2dac60d ARITY:class.standard
  NODE[0x2146] kind:opaque TYPE:opaque MEM:opaque HASH:0x00c4eb1c ARITY:class.reduced
  NODE[0xB58C] kind:opaque TYPE:opaque MEM:opaque HASH:0x8e4c6a4c
  NODE[0xAD59] kind:opaque TYPE:opaque MEM:opaque HASH:0xcd4661f8 ARITY:class.reduced
  NODE[0x601C] kind:opaque TYPE:opaque MEM:opaque HASH:0xdf685d15
  NODE[0xEEFF] kind:opaque TYPE:opaque MEM:opaque HASH:0xf76ffbea
  NODE[0xD484] kind:opaque TYPE:opaque MEM:opaque HASH:0x811e9366 ARITY:class.standard
  NODE[0xB7D5] kind:opaque TYPE:opaque MEM:opaque HASH:0xe1704bf2 ARITY:class.reduced
  NODE[0xD484] kind:opaque TYPE:opaque MEM:opaque HASH:0x7882eb21 ARITY:class.reduced
  NODE[0xAB9C] kind:opaque TYPE:opaque MEM:opaque HASH:0x6102c0ef ARITY:class.nullary
  NODE[0x2304] kind:opaque TYPE:opaque MEM:opaque HASH:0x3947558a
  NODE[0xB7D5] kind:opaque TYPE:opaque MEM:opaque HASH:0x29aa2459 ARITY:class.reduced
  NODE[0x76C8] kind:opaque TYPE:opaque MEM:opaque HASH:0xbb86d9c1 ARITY:class.nullary
  NODE[0xB7DD] kind:opaque TYPE:opaque MEM:opaque HASH:0x986457e1 ARITY:class.standard
  NODE[0x1717] kind:opaque TYPE:opaque MEM:opaque HASH:0x1c2458c8
  NODE[0x624C] kind:opaque TYPE:opaque MEM:opaque HASH:0xd3aba185 ARITY:class.reduced
  NODE[0xAB04] kind:opaque TYPE:opaque MEM:opaque HASH:0x0c2d57cf
  NODE[0x6D17] kind:opaque TYPE:opaque MEM:opaque HASH:0xdd811ed1 ARITY:class.nullary
  NODE[0xA13B] kind:opaque TYPE:opaque MEM:opaque HASH:0x9285e88d ARITY:class.standard
  NODE[0x272B] kind:opaque TYPE:opaque MEM:opaque HASH:0x49036c7e ARITY:class.standard
  NODE[0x6261] kind:opaque TYPE:opaque MEM:opaque HASH:0x0c5f4569
  NODE[0x74E0] kind:opaque TYPE:opaque MEM:opaque HASH:0xe3d822f3 ARITY:class.multiway
  NODE[0xE8B5] kind:opaque TYPE:opaque MEM:opaque HASH:0xbae9e4d4 ARITY:class.reduced
  NODE[0x006E] kind:opaque TYPE:opaque MEM:opaque HASH:0xc9e7fb74
  NODE[0xB8BD] kind:opaque TYPE:opaque MEM:opaque HASH:0x33a45ee9 ARITY:class.multiway
  NODE[0x9A37] kind:opaque TYPE:opaque MEM:opaque HASH:0x2eb14572 ARITY:class.reduced
  NODE[0x3237] kind:opaque TYPE:opaque MEM:opaque HASH:0xb057e96c
  NODE[0x6261] kind:opaque TYPE:opaque MEM:opaque HASH:0x42755f5f ARITY:class.multiway
  NODE[0x1ADD] kind:opaque TYPE:opaque MEM:opaque HASH:0x90ab1e3c
  NODE[0xB1C7] kind:opaque TYPE:opaque MEM:opaque HASH:0xa3752ce1 ARITY:class.reduced
  NODE[0xE3B0] kind:opaque TYPE:opaque MEM:opaque HASH:0xbeba9f9b ARITY:class.multiway
  NODE[0x006E] kind:opaque TYPE:opaque MEM:opaque HASH:0x668e6027 ARITY:class.standard
  NODE[0x5C69] kind:opaque TYPE:opaque MEM:opaque HASH:0x4edf14d8
  NODE[0x272B] kind:opaque TYPE:opaque MEM:opaque HASH:0x067cd6a5 ARITY:class.multiway
  NODE[0xB1C7] kind:opaque TYPE:opaque MEM:opaque HASH:0x6cd22728
  NODE[0x6261] kind:opaque TYPE:opaque MEM:opaque HASH:0xf9de0bec ARITY:class.multiway
  NODE[0x006E] kind:opaque TYPE:opaque MEM:opaque HASH:0xf1017f4d ARITY:class.multiway
  NODE[0xB7D5] kind:opaque TYPE:opaque MEM:opaque HASH:0x2d5fbf56 ARITY:class.multiway
  NODE[0xF21A] kind:opaque TYPE:opaque MEM:opaque HASH:0x4edb931a ARITY:class.nullary
  NODE[0xC47D] kind:opaque TYPE:opaque MEM:opaque HASH:0xe676b98b ARITY:class.multiway
  NODE[0x81F8] kind:opaque TYPE:opaque MEM:opaque HASH:0xe46c1b2b ARITY:class.multiway
  NODE[0x7995] kind:opaque TYPE:opaque MEM:opaque HASH:0x4e7f14e5 ARITY:class.standard
  NODE[0x8791] kind:opaque TYPE:opaque MEM:opaque HASH:0x7b66c78c ARITY:class.reduced
  NODE[0x5C69] kind:opaque TYPE:opaque MEM:opaque HASH:0xdd8e04bd
  NODE[0x832B] kind:opaque TYPE:opaque MEM:opaque HASH:0xaa15fd33 ARITY:class.multiway
  NODE[0x157D] kind:opaque TYPE:opaque MEM:opaque HASH:0x7ea6489e
  NODE[0xDE84] kind:opaque TYPE:opaque MEM:opaque HASH:0x221c19aa ARITY:class.standard
  NODE[0xFDB7] kind:opaque TYPE:opaque MEM:opaque HASH:0x5a7d0e59 ARITY:class.multiway
  NODE[0xAB2E] kind:opaque TYPE:opaque MEM:opaque HASH:0x05bbda05
  NODE[0x272B] kind:opaque TYPE:opaque MEM:opaque HASH:0xd84a94d5 ARITY:class.multiway
  NODE[0xF62C] kind:opaque TYPE:opaque MEM:opaque HASH:0xf5dddadc ARITY:class.reduced
  NODE[0x6261] kind:opaque TYPE:opaque MEM:opaque HASH:0x6202e338 ARITY:class.multiway
  NODE[0xAB2E] kind:opaque TYPE:opaque MEM:opaque HASH:0x9ac7077f ARITY:class.nullary
  NODE[0x072E] kind:opaque TYPE:opaque MEM:opaque HASH:0x20517367 ARITY:class.multiway
  NODE[0xB1C7] kind:opaque TYPE:opaque MEM:opaque HASH:0xa5a0d987
  NODE[0xB7D5] kind:opaque TYPE:opaque MEM:opaque HASH:0x3905c7d8 ARITY:class.multiway
  NODE[0xC0DD] kind:opaque TYPE:opaque MEM:opaque HASH:0x8c458bc0 ARITY:class.multiway
  NODE[0xD1B1] kind:opaque TYPE:opaque MEM:opaque HASH:0x86082478 ARITY:class.multiway
  NODE[0xAB2E] kind:opaque TYPE:opaque MEM:opaque HASH:0x66121c72 ARITY:class.multiway
  NODE[0x9E55] kind:opaque TYPE:opaque MEM:opaque HASH:0xfbf9af16 ARITY:class.nullary
  NODE[0x5CDD] kind:opaque TYPE:opaque MEM:opaque HASH:0xfe676fa2 ARITY:class.standard
  NODE[0x4DDF] kind:opaque TYPE:opaque MEM:opaque HASH:0x06b9ebcc ARITY:class.reduced
  NODE[0xAB2E] kind:opaque TYPE:opaque MEM:opaque HASH:0x171bef5b
  NODE[0xA13B] kind:opaque TYPE:opaque MEM:opaque HASH:0x0f8af297 ARITY:class.standard
  NODE[0xAB2E] kind:opaque TYPE:opaque MEM:opaque HASH:0xce3d26a8 ARITY:class.standard
  NODE[0x3D97] kind:opaque TYPE:opaque MEM:opaque HASH:0x3ecbe2e5 ARITY:class.nullary
  NODE[0xF109] kind:opaque TYPE:opaque MEM:opaque HASH:0xcfee0260 ARITY:class.nullary
  NODE[0x8EA0] kind:opaque TYPE:opaque MEM:opaque HASH:0x034d72a4 ARITY:class.standard
  NODE[0x37ED] kind:opaque TYPE:opaque MEM:opaque HASH:0xb9e0a1e8 ARITY:class.standard
  NODE[0xC47D] kind:opaque TYPE:opaque MEM:opaque HASH:0x967faad8
  NODE[0xC47D] kind:opaque TYPE:opaque MEM:opaque HASH:0x6c33bece ARITY:class.multiway
  NODE[0x81F8] kind:opaque TYPE:opaque MEM:opaque HASH:0x6e7429c8 ARITY:class.reduced
  NODE[0xDCFF] kind:opaque TYPE:opaque MEM:opaque HASH:0x20e4f70b
  NODE[0x0EA9] kind:opaque TYPE:opaque MEM:opaque HASH:0x62160e29 ARITY:class.nullary
  NODE[0x7995] kind:opaque TYPE:opaque MEM:opaque HASH:0x313d4bed
  NODE[0xDCFF] kind:opaque TYPE:opaque MEM:opaque HASH:0x6c55761d ARITY:class.nullary
  NODE[0xF5C3] kind:opaque TYPE:opaque MEM:opaque HASH:0x55341884 ARITY:class.nullary
  NODE[0x0EA9] kind:opaque TYPE:opaque MEM:opaque HASH:0x31d61ef0 ARITY:class.nullary
  NODE[0xF764] kind:opaque TYPE:opaque MEM:opaque HASH:0x07fbfe37
  NODE[0x3D97] kind:opaque TYPE:opaque MEM:opaque HASH:0x492aa328 ARITY:class.reduced
  NODE[0x0EA9] kind:opaque TYPE:opaque MEM:opaque HASH:0x327adb8a ARITY:class.nullary
  NODE[0x006E] kind:opaque TYPE:opaque MEM:opaque HASH:0x31aa3e37 ARITY:class.nullary
  NODE[0xF109] kind:opaque TYPE:opaque MEM:opaque HASH:0xd3fff21a
  NODE[0x2311] kind:opaque TYPE:opaque MEM:opaque HASH:0x75c1a9db ARITY:class.standard
  NODE[0xECD8] kind:opaque TYPE:opaque MEM:opaque HASH:0x4a059198 ARITY:class.nullary
  NODE[0xF109] kind:opaque TYPE:opaque MEM:opaque HASH:0x27ffcded ARITY:class.standard
  NODE[0xDE84] kind:opaque TYPE:opaque MEM:opaque HASH:0x180e6786
  NODE[0xFDB7] kind:opaque TYPE:opaque MEM:opaque HASH:0x67dd3ad0 ARITY:class.standard
  NODE[0x9B1A] kind:opaque TYPE:opaque MEM:opaque HASH:0x81e632a2 ARITY:class.nullary
  NODE[0x2311] kind:opaque TYPE:opaque MEM:opaque HASH:0x8541561a ARITY:class.reduced
  NODE[0x0F0B] kind:opaque TYPE:opaque MEM:opaque HASH:0xb15c7039
  NODE[0xECD8] kind:opaque TYPE:opaque MEM:opaque HASH:0xa3081670 ARITY:class.multiway
  NODE[0xAB2E] kind:opaque TYPE:opaque MEM:opaque HASH:0xb41930f8 ARITY:class.multiway
  NODE[0xF109] kind:opaque TYPE:opaque MEM:opaque HASH:0x441e4222 ARITY:class.nullary
  NODE[0xAFC2] kind:opaque TYPE:opaque MEM:opaque HASH:0x99726d91 ARITY:class.nullary
  NODE[0x81F8] kind:opaque TYPE:opaque MEM:opaque HASH:0x0a6fc6ad ARITY:class.nullary
  NODE[0x6417] kind:opaque TYPE:opaque MEM:opaque HASH:0x019eb700 ARITY:class.reduced
  NODE[0x7995] kind:opaque TYPE:opaque MEM:opaque HASH:0xdab37783 ARITY:class.nullary
  NODE[0x7F9B] kind:opaque TYPE:opaque MEM:opaque HASH:0x64bafb0c ARITY:class.reduced
  NODE[0x2311] kind:opaque TYPE:opaque MEM:opaque HASH:0x4a53c57a ARITY:class.nullary
  NODE[0x3D97] kind:opaque TYPE:opaque MEM:opaque HASH:0x5d1f0dc7
  NODE[0x9B05] kind:opaque TYPE:opaque MEM:opaque HASH:0xdb02e27e ARITY:class.nullary
  NODE[0xAB0B] kind:opaque TYPE:opaque MEM:opaque HASH:0x38c85942 ARITY:class.standard
  NODE[0x5489] kind:opaque TYPE:opaque MEM:opaque HASH:0xbde33e1a ARITY:class.reduced
  NODE[0xCDDC] kind:opaque TYPE:opaque MEM:opaque HASH:0x3dd4933b ARITY:class.nullary
// JCROSS_6AXIS_END
```

## 🧠 Verantyx Cortex: OS-Level Agent

Verantyx isn't just an enterprise code editor—it functions as a fully integrated, OS-level AI assistant.

- **Instant Invocation:** Press `Control` 3 times from anywhere on your Mac to summon the Verantyx Cortex Spotlight UI.
- **Autonomous Resolution:** Ask it to fix errors, install missing dependencies, or control applications.
- **Deep Integration:** It can directly execute shell commands, operate local applications (like Parallels Desktop or Microsoft Teams), and navigate the web to solve complex environment issues autonomously.

[![Verantyx Cortex OS-Level Agent](assets/verantyx-cortex-demo.gif)](https://github.com/Ag3497120/Verantyx/blob/release_verantyx/assets/verantyx-cortex-demo.mp4)

---
*Verantyx: Secure your IP. Empower your architecture. Control the AI.*
