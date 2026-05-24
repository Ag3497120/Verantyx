# Verantyx (avh-math) – Structural Guide & Reasoning Architecture

## (English)

---

### 1. What Verantyx Is (and Is Not)

Verantyx (avh-math) is not a large language model.
- ❌ No gradient training
- ❌ No token prediction
- ❌ No external data mining
- ❌ No probabilistic text generation

Instead, Verantyx is:
- ✅ A symbolic reasoning engine
- ✅ A database-driven logical system
- ✅ A deterministic solver over structured representations
- ✅ A system where knowledge is explicit and editable

The core philosophy is:
**Reasoning should be inspectable, reproducible, and replaceable.**

---

### 2. Core Design Philosophy

Traditional LLMs embed knowledge implicitly in weights. Verantyx does the opposite.

| Aspect | LLM | Verantyx |
| :--- | :--- | :--- |
| **Knowledge** | Implicit (weights) | Explicit (DB, axioms) |
| **Reasoning** | Probabilistic | Deterministic |
| **Editability** | Hard | Trivial (edit JSON) |
| **Failure mode**| Hallucination | Explicit "unknown / counterexample" |
| **Transparency**| Low | High |

Verantyx treats logic and mathematics as a solvable structure, not as text.

---

### 3. Entry Points (User Interfaces)

These are the official entry points into the system.

#### 3.1 `phase17_ui_server.py`
**Main web UI server**
- Initializes `AnswerEngine`
- Serves the interactive UI
- Handles `/api/solve`, `/api/ui_rules`, etc.
- This is the primary runtime during normal use.

#### 3.2 `verantyx_engine.py`
**Model loader interface (Hugging Face compatible)**
- Implements `from_pretrained`
- Loads the embedded DB snapshot
- Initializes a working reasoning environment
- This file exists so Verantyx can be treated as if it were an LLM model on Hugging Face — without actually being one.

#### 3.3 `cli.py` (optional)
**Command-line interface**
- For batch execution, debugging, and automation.

---

### 4. Main Pipeline & Orchestration Layer

This is the central nervous system.

#### 4.1 `avh_math/answer_engine.py`
**The global conductor**
- Entry point for all reasoning requests
- Calls `ReportBuilder`
- Returns structured results (status, proof, counterexample)

#### 4.2 `avh_math/report_builder.py`
**The reasoning orchestrator**
This file connects everything: Input parsing, Cross construction, Solver routing, Verification, and Result aggregation. Nothing reasons directly without passing through `ReportBuilder`.

#### 4.3 `avh_math/input_pipeline.py`
**Text → Structure**
- Converts raw user input into a structured `Decomposed` object.
- Uses recognizers to extract formulas, detect domains, and infer query types.
- This step is where natural language stops and formal reasoning begins.

---

### 5. Recognition & Parsing Layer

This layer answers: *“What is the user actually asking?”*

- **`recognizers/dispatcher.py`**: Routes input to the correct recognizer.
- **`recognizers/semantic_parser.py`**: Parses natural language structure using `word_memory.json`. Detects quantifiers like “for all”.
- **`recognizers/formula.py`**: Extracts symbolic formulas (operators, parentheses, modal symbols).
- **`recognizers/base.py`**: Base class for all recognizers.
- **`input_structured.py`**: Parses explicit headers (e.g., `Domain: modal_logic`).

---

### 6. Puzzle & Cross Structure (Reasoning State)

Verantyx does not reason in a linear chain. It reasons in a **Cross** (3D lattice-like structure).

- **`cross/cross_core.py`**: Defines `ReasoningCross` (holds assumptions, candidate formulas, results).
- **`cross/cross_db.py`**: Saves/loads Cross states for replay and inspection.
- **`puzzle/assemble_reasoning_cross.py`**: Builds the initial Cross from parsed input.
- **`puzzle/solver_router.py`**: Strategic decision point (decides which solver to use and in what order).
- **`puzzle/math_verifier.py`**: Executes solvers, integrates results, and determines the final verdict.

---

### 7. Solvers & Engines (Actual Reasoning)

These components do real logical work.

- **`solvers/prop_solver.py`**: Propositional logic, AST parsing, and exhaustive truth-table evaluation.
- **`solvers/modal_solver.py`**: Kripke frame construction, model checking, and counterexample generation.
- **`solvers/modal_axioms.py`**: Matches formulas against known modal principles (K, T, S4, S5).
- **`puzzle/kb_matcher.py`**: Fast path for known theorems and axioms.

---

### 8. Data & Knowledge Bases

This is where knowledge actually lives.

- **`foundation_kb.jsonl`**: Logical axioms, mathematical theorems, definitions, and counterexamples.
- **`word_memory.json`**: Semantic roles of words used by the parser.
- **`semantic_patterns.jsonl`**: Grammar patterns for extracting structure from text.

---

### 9. Dependency Flow (Simplified)

```text
User Input
  ↓
phase17_ui_server.py
  ↓
AnswerEngine
  ↓
ReportBuilder
  ├─ InputPipeline
  │    └─ Recognizers
  │
  ├─ AssembleReasoningCross
  │    └─ ReasoningCross
  │
  └─ SolverRouter
        └─ MathVerifier
              ├─ PropSolver
              ├─ ModalSolver
              └─ KBMatcher
```

---

### 10. Why This Matters

Because of this architecture:
- You can swap databases.
- You can add new domains.
- You can inspect every reasoning step.
- You can **prove or disprove** instead of guessing.

This is not an LLM that sounds correct. This is a system that can say:
*“Here is the counterexample. Therefore, the formula is false.”*

---
---

## (日本語)

---

### 1. Verantyxとは何か（そして何ではないか）

Verantyx (avh-math) は大規模言語モデルではありません。
- ❌ 勾配学習を行わない
- ❌ トークン予測を行わない
- ❌ 外部データの採掘を行わない
- ❌ 確率的な文章生成を行わない

代わりに Verantyx は：
- ✅ 記号的推論エンジン
- ✅ データベース駆動の論理システム
- ✅ 構造化表現に対する決定論的ソルバー
- ✅ 知識が明示的かつ編集可能なシステム

中核となる思想は次の一文です。
**「推論は、検査可能で、再現可能で、置き換え可能であるべきだ。」**

---

### 2. 中核となる設計思想

従来の LLM は、知識を重みの中に暗黙的に埋め込みます。Verantyx はそれを真逆に設計しています。

| 観点 | LLM | Verantyx |
| :--- | :--- | :--- |
| **知識** | 暗黙的（重み） | 明示的（DB・公理） |
| **推論** | 確率的 | 決定論的 |
| **編集性** | 困難 | 容易（JSON編集） |
| **失敗形態** | ハルシネーション | 明示的な「不明／反例」 |
| **透明性** | 低い | 高い |

Verantyx は 論理と数学を「文章」ではなく「解ける構造」として扱います。

---

### 3. エントリーポイント（UI）

#### 3.1 `phase17_ui_server.py`
**Web UI サーバー本体**
- `AnswerEngine` を初期化し、インタラクティブ UI を提供します。
- `/api/solve` などのリクエストを処理するメインランタイムです。

#### 3.2 `verantyx_engine.py`
**Hugging Face 互換のモデルローダー**
- `from_pretrained` を実装し、DB スナップショットをロードします。
- Hugging Face 上で LLM のように扱えるようにするためのインターフェースです。

#### 3.3 `cli.py`（任意）
**コマンドラインインターフェース**
- 一括実行やデバッグ、自動化のためのツールです。

---

### 4. メインパイプラインと統括層

Verantyx の **中枢神経系** です。

#### 4.1 `avh_math/answer_engine.py`
**推論の全体指揮官**
- すべての推論要求を受け取り、`ReportBuilder` を呼び出して結果をまとめます。

#### 4.2 `avh_math/report_builder.py`
**推論のオーケストレーター**
- 入力解析、Cross構築、Solver選択、検証、結果統合のすべてを繋ぎます。

#### 4.3 `avh_math/input_pipeline.py`
**テキスト → 構造**
- 生テキストを構造化された `Decomposed` オブジェクトへ変換します。
- ここが 自然言語が終わり、形式推論が始まる境界 です。

---

### 5. 認識・解析レイヤー

「ユーザーは何を問うているのか？」を決定します。

- **`recognizers/dispatcher.py`**: 入力を適切なパーサーに振り分けます。
- **`recognizers/semantic_parser.py`**: `word_memory.json` を使い、自然言語の構造（全称記号など）を解析します。
- **`recognizers/formula.py`**: 記号的な論理式を抽出します。
- **`recognizers/base.py`**: すべてのパーサーの基底クラスです。
- **`input_structured.py`**: `Domain: ...` などの明示的なヘッダをパースします。

---

### 6. Cross（立体十字）構造による推論状態

Verantyx は線形推論ではなく、3次元的な **Cross 構造** で推論を進めます。

- **`cross/cross_core.py`**: `ReasoningCross`（仮定、候補式、結果を保持）を定義します。
- **`cross/cross_db.py`**: 推論状態の保存と読み込みを行います。
- **`puzzle/assemble_reasoning_cross.py`**: 解析済み入力から初期の Cross を組み立てます。
- **`puzzle/solver_router.py`**: どのソルバーをどの順序で使うかの戦略を決定します。
- **`puzzle/math_verifier.py`**: ソルバーを実行し、最終的な判定（証明／反証）を下します。

---

### 7. ソルバー（実際の論理計算）

実際に論理的な演算を行うコンポーネントです。

- **`solvers/prop_solver.py`**: 命題論理の真理値表評価。
- **`solvers/modal_solver.py`**: 様相論理の Kripke モデル探索と反例生成。
- **`solvers/modal_axioms.py`**: 既知の公理系（K, T, S4, S5）との照合。
- **`puzzle/kb_matcher.py`**: 知識ベースからの高速な検索。

---

### 8. データベース（知識の実体）

知識は重みの中ではなく、ここにのみ存在します。

- **`foundation_kb.jsonl`**: 公理、定理、定義、反例のマスターDB。
- **`word_memory.json`**: 単語の意味役割（パーサーが使用）。
- **`semantic_patterns.jsonl`**: 構造抽出のための文法パターン。

---

### 9. 依存関係フロー

（英語版と同一のため省略）

---

### 10. なぜこれが重要か

この設計により：
- DB を差し替えるだけで能力を変えられます。
- すべての推論過程を人間が検査できます。
- 推測ではなく、**証明と具体的な反例** を出せます。

これは「それっぽい答え」を出す AI ではなく、
**「これが反例です。よってこの式は偽です。」** と断言できるシステムです。
