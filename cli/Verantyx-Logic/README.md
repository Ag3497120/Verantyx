---
title: Verantyx Logic Solver
emoji: 🧩
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
license: mit
language:
- en
- ja
tags:
- text-generation
- logic
- symbolic-reasoning
- verantyx
- math
---

# Verantyx (avh-math)

Verantyx (avh-math) is **not** a large language model (LLM).  
It is a **database-driven, deterministic reasoning engine** that returns **PROVED / DISPROVED (with counterexample) / UNKNOWN**.

This repository/package is the **math-focused** edition of Verantyx, designed as a **hybrid (“fusion”) of the earlier AXIS concept and the Verantyx architecture**, specialized for logic and mathematical verification.

---

## Key Points (TL;DR)

- This project was intentionally developed via **Vibe Coding** (conversational, LLM-assisted development) to demonstrate that **you do not need professional programming skills** to modify and evolve Verantyx—because the system is structured for it.
- The Hugging Face release can include **pseudo-weights** (a packaging technique that makes a Python+DB system look like a single “model weight” artifact).  
  These pseudo-weights are treated as **read-only snapshots**.
- Verantyx’s core feature remains: **the DB is editable and replaceable** (swap rules, swap domains, change behavior without retraining).
- **License: MIT** — you can do anything with it: modify, redistribute, commercialize. Modifications are welcome.
- **GPU is not required**. Verantyx is designed to run primarily on **CPU**.

---

## How Verantyx Differs From Rule-Based Systems and LLMs

| Aspect                | Typical Rule-Based System          | LLM                                         | Verantyx (avh-math)                                   |
| --------------------- | ---------------------------------- | ------------------------------------------- | ----------------------------------------------------- |
| Where knowledge lives | Rules scattered across code/config | Implicit in weights                         | **Explicit DB (JSONL)**                               |
| Reasoning             | Fixed if-then branching            | Probabilistic generation                    | **Deterministic verification + search**               |
| Counterexamples       | Rare / hard to model               | Can be generated but not guaranteed correct | **Constructs explicit counterexamples**               |
| Failure mode          | Missed exceptions, silent gaps     | Hallucination risk                          | **Returns UNKNOWN / NOT APPLICABLE**                  |
| Auditability          | Often difficult                    | Low                                         | **High (assumptions/DB/counterexamples are visible)** |
| Editability           | Maintenance becomes complex        | Weight edits are hard                       | **Swap DB to change behavior**                        |
| Best use              | Narrow business rules              | Language, ambiguity, creativity             | **Safety boundaries, verification, reproducibility**  |

Verantyx is not trying to “sound correct.”  
It tries to **prove, refute, or safely refuse**.

---

## What avh-math Can Do Today (Strengths)

- **Propositional logic**: truth-table evaluation, tautology checking, counterexample generation
- **Modal logic (Kripke semantics)**: model search, counterexample construction, handling frame conditions (reflexive / transitive, etc.)
- **Axiom matching (limited but practical)**: basic modal axiom schemas (K/T/S4/…), assumption detection and missing-assumption prompts

---

## About Pseudo-Weights (Important)

For Hugging Face distribution, Verantyx can be packaged as if it were “one model weight” by bundling:

- Python runtime files
- DB snapshots (JSONL/JSON)
  into a pseudo-weight artifact.

**Pseudo-weights are treated as read-only snapshots.**  
They exist for distribution convenience (including download counting), not as a live-edit format.

### Can I still edit/replace the DB?

Yes—DB editability is a core design principle. There are two typical workflows:

1. **Snapshot workflow (pseudo-weights distribution)**

   - Treat the packaged snapshot as read-only
   - Override behavior by **supplying an external DB** (replacement files)

2. **Source workflow (development mode)**
   - Edit the DB files directly in the repository
   - Changes take effect immediately

---

## License

**MIT License.**  
Commercial use, modification, redistribution are all allowed.  
Heavy modifications are welcome.

---

## Supported Platforms

### OS

- macOS (Intel / Apple Silicon)
- Linux
- Windows (works with a proper Python environment)

### Python

- Recommended: Python **3.10+** (3.11/3.12 also acceptable depending on dependencies)

### GPU

- **Not required.** Verantyx is primarily **CPU-first**.

---

## Installation

### 1) Install from source (recommended for DB editing)

```bash
git clone https://huggingface.co/kofdai/verantyx
cd verantyx

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -U pip
pip install -r requirements.txt
```

### 2) Use via Hugging Face-style loader (as a “model”)

Verantyx provides a loader interface (e.g., from_pretrained) so it can be used like a model, even though it is not an LLM.

```python
from verantyx_engine import VerantyxModel

engine = VerantyxModel.from_pretrained("kofdai/verantyx")
result = engine.solve('In arbitrary Kripke frames, is "p -> []p" always valid?')
print(result)
```

---

## Running (Web UI / CLI)

### Web UI (recommended)

```bash
python phase17_ui_server.py
```

Then open the UI in your browser and use SOLVE.

### CLI (optional)

```bash
python cli.py --help
```

---

## How It Works (High-Level)
1. Extract formulas (quoting is optional, but supported)
2. Detect domain (prop / modal / matrix, etc.)
3. Extract assumptions (e.g., reflexive/transitive) and detect missing assumptions
4. Route to solvers (KB match, truth-table, Kripke search)
5. Aggregate verdict (PROVED / DISPROVED / UNKNOWN)

---

## Structure Overview

**Two central files:**
- `phase17_ui_server.py`: Web UI server (API endpoints, interactive UI)
- `verantyx_engine.py`: Hugging Face compatible loader interface (from_pretrained)

**Core pipeline:**
- `avh_math/answer_engine.py`: global conductor
- `avh_math/report_builder.py`: orchestrator (Decomposer / Cross / Router / Verifier)
- `avh_math/input_pipeline.py`: text → structured Decomposed object
- `avh_math/recognizers/*`: semantic parsing + formula extraction
- `avh_math/cross/*`: ReasoningCross state + persistence
- `avh_math/puzzle/*`: cross assembly, solver routing, verification
- `avh_math/solvers/*`: propositional / modal solvers + axiom matching

**Data (knowledge is here):**
- `avh_math/db/foundation_kb.jsonl`: axioms, theorems, definitions, known patterns
- `avh_math/db/word_memory.json`: semantic roles for natural language parsing
- `avh_math/db/semantic_patterns.jsonl`: grammar/pattern DB for extracting structure

---

## Vibe Coding (Why It Matters)

This project intentionally adopted Vibe Coding:
- to prove Verantyx is simple enough to evolve via conversation
- to demonstrate non-programmers can still meaningfully modify behavior
- to make the development process transparent

### Gemini CLI Chat Logs

The Gemini CLI chat history used during development is stored as `.txt` files in the repository root.
These logs are **first-class artifacts** showing:
- how ideas evolved
- how problems were discovered
- why architectural decisions were made

---

## Addendum: Vibe Coding as a Statement — Verantyx Does Not Replace LLMs

One additional reason for adopting vibe coding is to clearly communicate Verantyx’s role:

**Verantyx is not designed to replace LLMs. It is designed to coexist with them.**

### Different roles

**LLMs excel at:**
- natural language understanding
- text generation
- ambiguous / creative / open-ended reasoning
- conversational interfaces

**Verantyx excels at:**
- explicit logical reasoning
- deterministic verification
- counterexample construction
- safety-critical decision boundaries
- auditability and reproducibility

These are complementary roles.

### A “post-hallucination” project

LLMs generate ideas.
Verantyx decides whether those ideas are allowed to stand.

---

## Roadmap (Excerpt)

A Verantyx-compatible GUI DB editor is planned to make DB editing accessible even for people who have never touched JSONL.
- CAD-like
- no-code
- safe-by-construction
- auditable + versioned
- immediate verification feedback

---

## FAQ

**Do I need config.json?**
If you publish on Hugging Face in a “model-like” format, providing a minimal config.json is typically a safe choice for compatibility. Verantyx is not an LLM, so only minimal metadata is required (exact needs depend on the chosen packaging approach).

**Do I need a GPU?**
No. Verantyx is designed to be CPU-first.

**Is a counterexample a bug?**
No. Counterexamples are a primary feature: they are explicit evidence that the formula/rule is invalid under given assumptions.

---

## Contributing

Issues and PRs are welcome.
Adding or improving DB entries (JSONL) can significantly expand the system’s capabilities.

---

## License

MIT License. See LICENSE.

---

## 日本語（Japanese）

# Verantyx (avh-math)

Verantyx (avh-math) は LLM（大規模言語モデル）ではありません。
DB（知識ベース）＋決定論的ソルバーによって「証明／反例／未知（UNKNOWN）」を返す **検証志向の推論エンジン**です。

本リポジトリ／配布物は、Verantyx の **数学（特に論理）特化版**であり、過去作 AXIS の概念と Verantyx アーキテクチャを融合したハイブリッド版として設計されています。

---

## 重要なポイント（要旨）
- 本プロジェクトは **Vibe Coding（対話的・LLM補助開発）**を意図的に採用し、Verantyx が「専門プログラマでなくても改変・進化できる」構造であることを示します。
- Hugging Face 公開のために、Python+DB集合を **疑似重み（pseudo-weights）**として “LLM重み風” にパッケージできます。
ただし疑似重みは **読み取り専用スナップショット（read-only）**として扱います。
- Verantyx の本質は DBが自由に編集・差し替え可能であることです（再学習不要）。
- **MIT License**：自由に改変・再配布・商用利用できます。「どんなにいじるのも大歓迎」です。
- **GPUは基本不要**（CPUで動く設計）。

---

## ルールベース／LLM と Verantyx の違い（比較表）

| 観点 | 典型的ルールベース | LLM | Verantyx (avh-math) |
| :--- | :--- | :--- | :--- |
| **知識の所在** | ルール/コードに散在しがち | 重み（暗黙） | **DB（JSONL）に明示** |
| **推論** | if-then中心（分岐固定） | 確率的生成 | **決定論的検証＋探索** |
| **反例** | 基本なし（例外設計が難しい） | 生成はできるが正しさ保証なし | **反例モデルを構成して否定** |
| **失敗の扱い** | 取りこぼし／例外漏れ | ハルシネーションの危険 | **UNKNOWN/NOT APPLICABLE を返す** |
| **監査性** | 追いにくい | 低い | **高い（仮定・DB・反例が可視）** |
| **改変のしやすさ** | ルール保守が難化しがち | 重み編集は困難 | **DB差し替えで挙動を変えられる** |
| **主用途** | 狭い業務ルール | 対話・文章・曖昧推論 | **安全境界が必要な検証** |

Verantyx は「それっぽい回答」より、
**証明できる／反例が作れる／不十分ならUNKNOWN**を重視します。

---

## avh-math が現状できること（強み）
- **命題論理**：真理値表、恒真式判定、反例生成
- **様相論理（Kripke意味論）**：モデル探索、反例構成、フレーム条件（反射性・推移性など）
- **公理照合（限定的）**：K/T/S4 など基本公理スキーマ、仮定不足の検出

---

## 疑似重み（pseudo-weights）について（重要）

Hugging Face 公開の都合で、Python＋DB集合を「一つのモデル重みのように見せる」パッケージングが可能です。
- ✅ 配布が簡単（ダウンロードカウント等にも有利）
- ❗ ただし 疑似重みは読み取り専用スナップショットとして扱います

### DBは自由にいじれるのか？

はい。DBの編集・差し替えは Verantyx の核です。
ただし運用は大きく2つです：
1. **スナップショット運用（疑似重み配布）**
   - 配布物は read-only とみなす
   - 外部DB差し替えで挙動を変更する（推奨）
2. **ソース運用（開発モード）**
   - リポジトリ内DBを直接編集
   - 変更が即反映される

---

## ライセンス

**MIT License**
- 商用利用OK
- 改変OK
- 再配布OK
- 組み込みOK

「どんなにいじるのも大歓迎」です。

---

## 対応環境（Supported Platforms）

### OS
- macOS（Intel / Apple Silicon）
- Linux
- Windows（Python環境が整っていれば可）

### Python
- 推奨：Python **3.10+**

### GPU
- **不要**（CPUファースト設計）

---

## インストール（Install）

### 1) ソースから（DB編集に推奨）

```bash
git clone https://huggingface.co/kofdai/verantyx
cd verantyx

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -U pip
pip install -r requirements.txt
```

### 2) Hugging Face ローダー（“モデル”として扱う）

```python
from verantyx_engine import VerantyxModel

engine = VerantyxModel.from_pretrained("kofdai/verantyx")
result = engine.solve('任意の Kripke frame において "p -> []p" は常に成り立つか？')
print(result)
```

---

## 実行（Web UI / CLI）

### Web UI（推奨）

```bash
python phase17_ui_server.py
```

CLI（任意）

```bash
python cli.py --help
```

---

## 動作の流れ（概要）
1. 式の抽出（ダブルクォートで囲ってもOK）
2. ドメイン判定
3. 仮定の抽出／不足仮定の提示
4. ソルバー選択（KB照合・真理値表・Kripke探索）
5. 結論統合（PROVED / DISPROVED / UNKNOWN）

---

## プロジェクト構造（概要）

**中心となる2ファイル：**
- `phase17_ui_server.py`：Web UIサーバー
- `verantyx_engine.py`：Hugging Face互換ローダー（from_pretrained）

**主要モジュール：**
- `avh_math/answer_engine.py`
- `avh_math/report_builder.py`
- `avh_math/input_pipeline.py`
- `avh_math/recognizers/*`
- `avh_math/cross/*`
- `avh_math/puzzle/*`
- `avh_math/solvers/*`

**DB（知識の実体）：**
- `avh_math/db/foundation_kb.jsonl`
- `avh_math/db/word_memory.json`
- `avh_math/db/semantic_patterns.jsonl`

---

## Vibe Coding について

本プロジェクトは あえて **Vibe Coding** を採用しています。
- 非エンジニアでも Verantyx を改変できることの証明
- 開発過程を透明化し、再現可能にするため

### Gemini CLI チャットログ

Gemini CLI とのチャット履歴を `.txt` でルートディレクトリに保存しています。
これは資料ではなく **プロジェクトの一部**です。

---

## 追記：Verantyx は LLM を置き換えない（共存する）

Vibe Coding を採用したもう一つの意図は、Verantyx の立ち位置を明確にすることです。

**Verantyx は LLM を置き換えるためのものではありません。共存するためのものです。**
- **LLM**：意図の言語化、案の生成、対話UI
- **Verantyx**：検証、反例、安全境界、監査可能性

LLMが案を出し、Verantyx が「通してよいか」を判断します。

---

## ロードマップ（抜粋）

DB未経験者でも安全に編集できる
Verantyx対応GUI DBエディタを将来リリース予定です。
- CAD風
- ノーコード
- 安全設計（safe-by-construction）
- 監査ログ／バージョン管理
- 即時検証フィードバック

---

## FAQ

**Q. config.json は必要？**
Hugging Face で“モデル風”に公開する場合、互換性のために最小限の config.json を置くのが一般に安全です。
Verantyx はLLMではないため、必要最小限のメタ情報で十分です（公開形態に依存）。

**Q. GPUは必要？**
不要です。CPUで動きます。

**Q. 反例が出るのは不具合？**
不具合ではありません。反例は「偽であることの証拠」です。Verantyxの主機能の一つです。

---

## Contributing

Issue / PR 歓迎です。
DB（JSONL）の改善だけでも大きく進化します。

---

## License

MIT License. See LICENSE.