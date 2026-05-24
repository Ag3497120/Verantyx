# Verantyx Medical Knowledge Base Design Guide
**Explicit, Auditable, Non-Hallucinatory Medical Reasoning**

## English

### 1. Design Goal of a Medical DB in Verantyx

A medical database in Verantyx is not a corpus of facts. It is a:
- Structured knowledge base
- Logical constraint system
- Assumption-aware reasoning substrate

The goal is not coverage, but **safety and correctness**. If something cannot be represented explicitly, Verantyx should not reason about it.

---

### 2. Core Principles (Non-Negotiable)

#### 2.1 Explicitness Over Completeness
Every entry must explicitly state:
- What it applies to
- Under which conditions
- Where it does not apply
No implicit medical common sense is allowed.

#### 2.2 Failure Is a Valid Outcome
The DB must support returning:
- **UNKNOWN**
- **NOT APPLICABLE**
- **CONDITIONALLY TRUE**
Absence of knowledge must never be filled in.

#### 2.3 No Statistical Generalization
Do not encode: “Usually”, “Often”, “Most patients”. Verantyx is deterministic. Probabilistic medicine belongs outside the system.

---

### 3. Recommended DB Structure (JSONL)

Each line represents one reasoning unit.
```json
{
  "id": "med_guideline_hypertension_001",
  "domain": "medical",
  "category": "guideline",
  "title": "Hypertension diagnosis threshold (adult)",
  "statement": "Hypertension is diagnosed if systolic blood pressure >= 140 mmHg",
  "formal_constraints": [
    "age >= 18",
    "systolic_bp >= 140"
  ],
  "exclusions": [
    "pregnancy",
    "acute illness"
  ],
  "assumptions": [
    "standard measurement conditions",
    "resting state"
  ],
  "confidence_scope": "diagnostic_criteria",
  "source": "WHO guideline",
  "verifiable": true
}
```

---

### 4. Mandatory Fields Explained

- **`id`**: Stable identifier (required for auditability).
- **`domain`**: "medical" or "medical:cardiology" etc.
- **`statement`**: Human-readable, must be unambiguous.
- **`formal_constraints`**: Machine-checkable boolean predicates only.
- **`exclusions`**: Conditions where the rule must not apply (critical for safety).
- **`assumptions`**: Contextual requirements (must always be explicit).

---

### 5. Representing Diagnostic Logic

Do not encode diagnoses as conclusions.
- ❌ **Bad**: “The patient has disease X.”
- ✅ **Good**:
```json
{
  "category": "diagnostic_criteria",
  "statement": "Criteria for disease X are satisfied",
  "formal_constraints": ["test_A == positive", "symptom_B == present", "duration >= 6 months"]
}
```
Verantyx evaluates criteria. Humans make diagnoses.

---

### 6. Treatment & Protocol Entries

Treatments must always be conditional. Never encode: “Should be administered”, “Is recommended” without constraints.

---

### 7. Handling Uncertainty Correctly

If required data is missing → Verantyx must return **UNKNOWN**. No fallback assumptions. This is intentional safety behavior.

---

### 8. Counterexample-Friendly Design

Every rule must allow Verantyx to ask: **“Can I construct a case where this fails?”** If the answer is “no”, the rule is unsafe.

---

### 9. Versioning & Replaceability

Medical DBs are expected to change, be replaced, or differ by jurisdiction. Correct design means: Swapping DBs changes behavior; **no code modification is required.**

---

### 10. What This Enables

- Auditable medical reasoning
- Transparent assumption tracking
- No hallucination by design
- Medical-grade explainability

---

### 11. Planned GUI-Based Medical DB Editor (Verantyx-Compatible)

Verantyx is designed so that its knowledge bases are explicit, editable, and replaceable. However, editing JSONL directly is not suitable for all users. A Verantyx-compatible graphical DB editor is planned for future release.

**Planned characteristics:**
- Visual block-based rule construction
- Explicit condition / exclusion panels
- Real-time logical validation
- Full audit trail of edits
- Hot-swappable DB export for Verantyx

**Important:** This editor will not perform learning, prediction, or opaque automation. It is a structured authoring tool, not an AI assistant. Knowledge remains explicit. Reasoning remains deterministic. Responsibility remains human.

---
---

## 日本語（Japanese）

### 1. Verantyx における医療DBの目的

Verantyx の医療DBは、医学知識の集積ではありません。それは：
- 構造化知識ベース
- 論理制約集合
- 仮定付き推論基盤
です。目標は**網羅性ではなく、安全性と正当性**です。明示的に表現できないものについて、Verantyx は推論してはいけません。

---

### 2. 絶対に守る原則

#### 2.1 明示性は完全性より優先
すべてのルールに以下を明示します：
- 適用条件
- 非適用条件
- 仮定
暗黙の医学常識は禁止です。

#### 2.2 失敗は正常な結果
DB は以下を返せなければなりません：
- **UNKNOWN**
- **NOT APPLICABLE**
- **条件付き成立**
欠落知識を補完してはいけません。

#### 2.3 統計的表現は禁止
以下は禁止：「通常は」、「多くの場合」、「ほとんどの患者」。Verantyx は確率推論を行いません。

---

### 3. 推奨JSONL構造
（英語例と同様。1行＝1推論単位）

---

### 4. 診断ロジックの正しい表現

- ❌ 病名を断定する
- ✅ 診断基準を満たすかを評価する
診断は人間が行います。

---

### 5. 治療ルール設計
治療は必ず条件付き。「投与すべき」は書かない。

---

### 6. 不確実性の扱い
情報が足りない場合 → **UNKNOWN** を返す。これは欠陥ではなく**安全設計**です。

---

### 7. 反例可能性の確保
すべてのルールは「破れる状況」を想定できなければなりません。

---

### 8. DB差し替え前提設計
国別、ガイドライン別、年度別。DBを入れ替えるだけで挙動が変わるのが正解です。

---

### 9. この設計がもたらすもの

- 監査可能な医療推論
- 仮定の完全可視化
- ハルシネーション不可能
- 医療向け説明可能性

---

### 10. GUIベース医療DB編集ソフト（将来予定）

Verantyx は知識が明示的で、編集可能で、差し替え可能であることを前提に設計されています。JSONL直接編集が難しい利用者のために、Verantyx対応GUI編集ソフトを将来的にリリース予定です。

**想定機能：**
- ブロックベース編集
- 条件・除外の明示UI
- リアルタイム整合性チェック
- 編集履歴・監査ログ
- 即差し替え可能なDB出力

**重要：** 学習・推測・自動判断を行うAIではありません。これは**安全な知識記述環境**です。

---

### 11. 結論

Verantyx の医療DBは**医療AIのための「安全な思考空間」**です。答えを出すことより、間違えないことを優先します。
