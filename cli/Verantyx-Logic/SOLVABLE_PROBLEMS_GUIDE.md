# Verantyx (avh-math) – Solvable Problems & Scope Guide

## English

---

### 1. Purpose of This Guide

This guide explains what kinds of problems the current Verantyx database can and cannot handle. Verantyx is not a general-purpose AI; its reasoning ability is strictly bounded by its database and solvers. This limitation is intentional.

---

### 2. High-Level Scope of the Current DB

The current avh-math database is designed to handle problems that are:

- **Symbolic** (logical structures, not numeric-heavy)
- **Rule-based** (deterministic, not statistical)
- **Explicitly stated** (closed-world assumption)
- **Verifiable by construction** (reducible to formal logic)

---

### 3. Supported Problem Domains (Current)

#### 3.1 Propositional Logic

The current DB and solvers fully support:

- Tautology checking
- Validity / invalidity of formulas
- Logical implication and contraposition
- Equivalence checking
- **Explicit counterexample construction**

**Example Questions:**

- _"Is (A ∧ B) -> A valid?"_
- _"Does (A -> B) -> (~B -> ~A) hold for all valuations?"_

#### 3.2 Modal Logic (Kripke Semantics)

Support for basic modal logic includes:

- **□ (Necessity)** and **◇ (Possibility)**
- Kripke frame semantics
- Frame conditions: **Reflexive, Transitive, Symmetric (partial)**
- **Explicit counterexample models** showing failing worlds and valuations.

**Example Questions:**

- _"Is p -> □p valid in arbitrary Kripke frames?"_ (Returns DISPROVED with countermodel)
- _"Is □p -> p valid in reflexive frames?"_ (Returns PROVED)

#### 3.3 Axiom-Based Reasoning (Limited)

The DB includes foundational axioms for:

- Classical propositional logic
- Modal systems (K, T, S4, partial S5)
- This allows matching formulas against known schemas and highlighting missing assumptions.

---

### 4. What Verantyx Explicitly Does NOT Handle (Yet)

The current DB does not support:

- Continuous mathematics (Calculus, Real Analysis)
- Probability theory and Statistics
- Empirical reasoning or "Common Sense" inference
- Open-ended word problems requiring guessing or approximation.

If a problem requires statistical inference or implicit background knowledge, Verantyx will return **UNKNOWN** or **NOT APPLICABLE**. This is a safety feature.

---

### 5. Input Rules (Mandatory)

To ensure the system correctly identifies the logical target, you must follow these rules:

- **Quote your formulas**: Always enclose the logical part of your query in double quotes (`"..."`).
- **Separation**: This allows Verantyx to separate the **instruction** (natural language) from the **problem** (logic).

| Type             | Example                              |
| :--------------- | :----------------------------------- |
| ✅ **Correct**   | _Is **"(A & B) -> A"** always true?_ |
| ❌ **Incorrect** | _Is (A & B) -> A always true?_       |

---

### 6. Best Query Patterns

The system works best when questions are clearly scoped and logically closed.

- **Good**: _"In modal logic, under transitivity, is the following formula valid: '[]p -> [][]p'?"_
- **Bad**: _"Is this generally true?"_ or _"Does this usually happen?"_

---

### 6. How the DB Is Used During Reasoning

1. **Immediate matching**: Checks against known axioms or known counterexamples.
2. **Constraint checking**: Enforces domain restrictions and frame conditions.
3. **Boundary detection**: Identifies where reasoning must stop and returns **UNKNOWN** instead of guessing.

---

### 7. Why This Limited Scope Is a Strength

- **Hallucination is structurally impossible.**
- Every answer is auditable and every failure is explicit.
- Verantyx prefers _"I cannot prove this with the current database"_ over _"This is probably true."_

---

### 8. How This Scope Can Expand

Solvable problems expand by adding new DB entries or new solvers, **not by retraining or scaling parameters.** Evolution is transparent and domain-driven.

---

### 9. Summary

Verantyx is suitable for **Formal Logic, Verification-oriented reasoning, and Safety-critical rule validation.** It is not a general intelligence that guesses answers; it is a deterministic engine that proves them.

---

---

## Japanese（日本語）

---

### 1. このガイドの目的

このガイドは、**現在の Verantyx (avh-math) の DB で「何ができて、何ができないか」**を明確に説明するためのものです。Verantyx は汎用 AI ではなく、その推論能力は DB とソルバーで厳密に制限されています。これは設計思想です。

---

### 2. 現在の DB の大枠の範囲

現在の avh-math DB が対応できる問題は、次をすべて満たすものです：

- **記号的である**（論理構造、数値計算中心ではない）
- **ルールベースである**（決定論的、統計的ではない）
- **明示的に書かれている**（閉じた世界の前提）
- **構造的に検証できる**（形式論理に還元可能）

---

### 3. 対応している問題分野

#### 3.1 命題論理

現在の DB とソルバーは以下を完全にサポートします：

- 恒真式判定
- 妥当性・非妥当性の判定
- 含意関係、対偶の評価
- 同値性チェック
- **明示的な反例（真理値割当）の生成**

**対応例：**

- _(A ∧ B) -> A は正しいか？_
- _(A -> B) -> (~B -> ~A) は常に成り立つか？_

#### 3.2 様相論理（Kripke 意味論）

以下の様相論理推論をサポートしています：

- **□（必要性）** および **◇（可能性）**
- Kripke フレーム意味論
- 到達関係の条件：**反射性、推移性、対称性（一部）**
- **具体的反例モデルの構成**（失敗した世界と真理値の表示）

**対応例：**

- _任意のフレームにおいて p -> □p は妥当か？_（反例を返します）
- _反射的なフレームにおいて □p -> p は妥当か？_（証明を返します）

#### 3.3 公理ベース推論（限定的）

以下の基礎公理を DB に含んでいます：

- 古典命題論理の公理
- 様相論理体系（K, T, S4, S5 の一部）
- これにより、既知の公理スキーマとの照合や、不足している仮定の指摘が可能です。

---

### 4. 明確に「できない」こと

現在の DB では以下は扱いません：

- 連続的な数学（解析学、微分積分など）
- 確率論、統計学
- 経験則や「常識」に基づく推論
- 推測や近似を必要とするオープンエンドな文章題

統計的推論や暗黙の背景知識が必要な場合、Verantyx は **UNKNOWN**（不明）または **NOT APPLICABLE**（非該当）を返します。これは**安全設計**です。

---

### 5. 入力のルール（必須）

システムが論理的な対象を正確に識別するために、以下のルールを必ず守ってください。

- **式を引用符で囲む**: クエリの論理式の部分は、必ずダブルクォーテーション（`"..."`）で囲んでください。
- **役割の分離**: これにより、Verantyx は**指示**（自然言語）と**対象**（論理）を明確に分離して処理できます。

| 形式            | 例                                     |
| :-------------- | :------------------------------------- |
| ✅ **正しい例** | _「**(A & B) -> A**」は常に正しいか？_ |
| ❌ **誤った例** | _(A & B) -> A は常に正しいか？_        |

---

### 6. 向いている質問の形

質問が明確に定義され、論理的に閉じている場合に最高の性能を発揮します。

- **良い例**: _「様相論理において、推移性を仮定した場合、式 '[]p -> [][]p' は妥当か？」_
- **悪い例**: _「これは普通正しい？」「だいたいどうなる？」_

---

### 6. DB の使われ方

1. **既知ルールとの照合**: 公理や既知の反例との即時マッチング。
2. **制約・仮定チェック**: ドメイン制限やフレーム条件の適用。
3. **推論限界の検出**: 推論が不可能な場所を特定し、推測せずに **UNKNOWN** を返します。

---

### 7. 制限が強みになる理由

- **ハルシネーション（捏造）が構造的に不可能です。**
- すべての回答が監査可能であり、失敗は明示されます。
- Verantyx は「おそらく正しい」と言うよりも、*「現在のデータベースでは証明できません」*と答えることを優先します。

---

### 8. 今後の拡張方法

対応できる問題の範囲は、DB エントリやソルバーの追加によってのみ拡張されます。**再学習やパラメータの増大による拡張ではありません。** 進化は透明で制御可能です。

---

### 9. まとめ

Verantyx は**形式論理、検証重視の推論、安全性が最優先されるルール確認**に適しています。答えを推測する汎用知能ではなく、数学的な厳密さで答えを証明・反証する決定論的エンジンです。
