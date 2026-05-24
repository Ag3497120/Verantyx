# Verantyx Reasoning & Language Understanding Guide

This guide explains the two core pillars of Verantyx: **Structural Language Understanding** and **Puzzle-Based Reasoning (Reasoning Cross)**.

---

## English

### 1. The Core Philosophy: "Reasoning is a Puzzle"

Verantyx does not "think" like a human or "predict" like an LLM. Instead, it treats every problem as a jigsaw puzzle.
If pieces are missing, it cannot complete the picture. If pieces don't fit, it reports a contradiction.

### 2. Structural Language Understanding

Verantyx does not use statistical NLP. It uses **Semantic Parsing** based on explicit memory.

#### A. Word Memory (`word_memory.json`)
The system "knows" the role of words before it reads a sentence.
- **Quantifiers**: `always`, `for all` → Triggers "Universal Validity Check"
- **Operators**: `implies`, `and`, `valid` → Triggers logic solvers
- **Context**: `transitive`, `reflexive` → Triggers "Assumption Extraction"

#### B. Structural Isolation (Auto-Quoting)
When you type a mixed sentence like:
> *Is []p -> p always true?*

Verantyx identifies that `[]p -> p` is a mathematical formula (unknown structure) and `Is`, `always`, `true` are known commands.
It internally converts this to:
> *Is **"[]p -> p"** always true?*

This protects the formula from being corrupted by language processing.

#### C. Intent Extraction
Once the structure is clear, the system extracts the **Intent**:
- **Action**: `VERIFY` (Proof) or `FIND_COUNTEREXAMPLE`
- **Domain**: `modal_logic` or `propositional_logic`
- **Constraints**: `assume:transitive`

### 3. Puzzle-Based Reasoning (Reasoning Cross)

Once the input is parsed, Verantyx builds a **Reasoning Cross**—a multi-dimensional data structure that holds the state of the problem.

#### The 6 Axes of the Cross
1.  **Core Formula**: The target proposition to be proved.
2.  **Assumptions**: The constraints (e.g., transitive frame).
3.  **Domain**: The mathematical field (e.g., Modal Logic).
4.  **Candidates**: Potential interpretations of the input.
5.  **Evidence**: Knowledge retrieved from the DB.
6.  **Counterexamples**: Concrete models that violate the formula.

#### The Solver Pipeline
1.  **Decomposer**: Breaks text into the Cross structure.
2.  **Router**: Decides which solver (Truth Table, Kripke Search) to use.
3.  **Verifier**: Runs the solver.
    - If a counterexample is found: `DISPROVED`
    - If all models hold: `PROVED`
4.  **ReportBuilder**: Translates the Cross state back into a human-readable report.

---
---

## 日本語

### 1. 核心となる哲学：「推論とはパズルである」

Verantyx は人間のように「思考」したり、LLMのように「予測」したりしません。代わりに、あらゆる問題をジグソーパズルのように扱います。
ピースが足りなければ絵は完成せず、ピースが合わなければ矛盾を報告します。

### 2. 構造的言語理解（Semantic Parsing）

Verantyx は統計的NLP（自然言語処理）を使用しません。明示的な記憶に基づく **意味解析（Semantic Parsing）** を使用します。

#### A. 単語記憶 (`word_memory.json`)
システムは、文章を読む前に単語の役割を「知って」います。
- **全称子**: `常に`, `すべての` → 「普遍的妥当性チェック」を起動
- **演算子**: `ならば`, `かつ` → 論理ソルバーを起動
- **文脈**: `推移的`, `反射的` → 「仮定抽出」を起動

#### B. 構造的分離（自動クォート）
次のような混在した文が入力された場合：
> *推移的なフレームで []p -> p は常に成り立ちますか？*

Verantyx は、`[]p -> p` が数式（未知の構造）であり、それ以外が既知のコマンドであることを特定します。
内部的に次のように変換されます：
> *推移的なフレームで **"[]p -> p"** は常に成り立ちますか？*

これにより、数式が言語処理によって破壊されるのを防ぎます。

#### C. 意図の抽出
構造が明確になると、システムは **意図（Intent）** を抽出します：
- **アクション**: `VERIFY`（証明）または `FIND_COUNTEREXAMPLE`（反例探索）
- **ドメイン**: `modal_logic`（様相論理）または `propositional_logic`（命題論理）
- **制約**: `assume:transitive`（推移性仮定）

### 3. パズル推論（Reasoning Cross）

入力が解析されると、Verantyx は **Reasoning Cross（推論クロス）** と呼ばれる、問題の状態を保持する多次元データ構造を構築します。

#### クロスの6つの軸
1.  **Core Formula（核となる式）**: 証明すべき対象。
2.  **Assumptions（仮定）**: 制約条件（例：推移的フレーム）。
3.  **Domain（ドメイン）**: 数学的分野。
4.  **Candidates（候補）**: 入力の解釈の可能性。
5.  **Evidence（証拠）**: DBから検索された知識。
6.  **Counterexamples（反例）**: 式を否定する具体的なモデル。

#### ソルバーパイプライン
1.  **Decomposer**: テキストを Cross 構造に分解します。
2.  **Router**: どのソルバー（真理値表、Kripke探索）を使うか決定します。
3.  **Verifier**: ソルバーを実行します。
    - 反例が見つかれば：`DISPROVED`
    - すべてのモデルで成立すれば：`PROVED`
4.  **ReportBuilder**: Cross の状態を人間が読めるレポートに再翻訳します。
