# Verantyx for Medical & Healthcare Reasoning
**Safety-Oriented, Non-Hallucinatory Decision Support**

## English

### 1. Important Disclaimer

Verantyx is not a medical diagnosis system and does not replace clinicians.

It is designed as a:
- Decision-support tool
- Logical consistency checker
- Assumption-aware reasoning engine

**All outputs must be reviewed by qualified medical professionals.**

---

### 2. Why Hallucination Is Unacceptable in Medicine

In medical contexts:
- A plausible-sounding error can cause harm.
- Silence is safer than misinformation.
- “Unknown” is a valid and necessary outcome.

Traditional LLMs are unsuitable for critical medical reasoning because:
- They must always generate an answer.
- They optimize for fluency, not correctness.
- They cannot structurally refuse to answer.

---

### 3. Verantyx’s Medical Safety Principle

Verantyx follows a strict principle:
> **No structure, no answer.**

Every medical-related output must be supported by:
- Explicit knowledge entries
- Logical derivations
- Or clearly stated assumptions

If the system cannot justify an answer:
- It returns **UNKNOWN**.
- Or requests additional constraints.

This makes unsafe speculation impossible.

---

### 4. Explicit Assumptions and Boundary Conditions

Medical reasoning often depends on assumptions:
- Patient age
- Comorbidities
- Test availability
- Diagnostic criteria

Verantyx:
- Makes all assumptions explicit.
- Separates facts from hypotheses.
- Shows which conclusions depend on which assumptions.

This prevents hidden inference chains — a major risk in medical AI.

---

### 5. Counterexample-Based Safety

Instead of asserting confidence, Verantyx asks:
> **“Under what conditions would this conclusion fail?”**

For example:
- If a guideline applies only under specific criteria.
- If a diagnosis fails when one assumption is violated.

Verantyx attempts to construct counterexamples. If a counterexample exists, the claim is rejected. This mirrors medical differential diagnosis logic.

---

### 6. Difference from Rule-Based Clinical Systems

Traditional clinical rule engines:
- Encode fixed decision trees.
- Break when inputs are incomplete.
- Cannot explain why a rule failed.

Verantyx:
- Dynamically constructs reasoning states.
- Evaluates multiple reasoning paths.
- Explains failure explicitly.
- Adapts when knowledge bases are updated.

Rules are not hard-coded behavior — they are reasoning objects.

---

### 7. Suitable Medical Use Cases

Verantyx is suitable for:
- Clinical guideline consistency checking.
- Diagnostic criteria verification.
- Treatment protocol validation.
- Risk condition logic checking.
- Medical education and training.
- Audit and compliance review.

It is **not suitable** for:
- Autonomous diagnosis.
- Real-time emergency decisions.
- Patient-facing medical advice.

---

### 8. Why This Architecture Fits Healthcare

Healthcare demands systems that:
- Can say “I don’t know”.
- Expose uncertainty.
- Are auditable and inspectable.
- Fail safely.

Verantyx was designed with these constraints from the ground up.

---

### 9. Summary

Verantyx supports medicine because:
- It never invents medical facts.
- It never hides uncertainty.
- It never answers without justification.
- It always exposes assumptions and limits.

**In medicine, correctness is not optional. Verantyx is built accordingly.**

---
---

## 日本語（Japanese）

### 1. 重要な注意事項

Verantyx は 医療診断システムではありません。また、医師や医療従事者の判断を代替するものではありません。

本システムは：
- 意思決定支援
- 論理整合性チェック
- 仮定を明示した推論

を目的としたツールです。
**すべての出力は、必ず専門家による確認が必要です。**

---

### 2. 医療においてハルシネーションが致命的な理由

医療分野では：
- 「それらしい誤答」は危険。
- 不確実なら沈黙すべき。
- **UNKNOWN** は正当な結論。

LLM が医療に不向きな理由：
- 常に回答を生成してしまう。
- 正しさより流暢さを最適化。
- 構造的に回答拒否ができない。

---

### 3. Verantyx の医療安全原則

Verantyx の原則は一つです：
> **構造がなければ答えない。**

すべての結論は：
- 明示的な知識
- 論理的導出
- 仮定の明示

のいずれかに基づきます。正当化できない場合：
- **UNKNOWN** を返す。
- 追加条件を要求する。

憶測は不可能です。

---

### 4. 仮定と境界条件の完全可視化

医療推論は多くの仮定に依存します：
- 年齢
- 併存疾患
- 検査条件
- 診断基準

Verantyx は：
- 仮定をすべて明示。
- 事実と仮説を分離。
- 結論がどの仮定に依存するかを表示。

これは医療 AI の最大のリスクである「隠れた推論」を防ぎます。

---

### 5. 反例による安全性検証

Verantyx は自信を主張しません。代わりに問います：
> **「この結論が成り立たない条件は何か？」**

反例が存在する場合、その主張は却下されます。これは鑑別診断の思考と同じ構造です。

---

### 6. ルールベース医療システムとの違い

従来の医療ルールエンジン：
- 固定分岐。
- 入力不足に弱い。
- なぜ失敗したか説明できない。

Verantyx は：
- 推論状態を動的に構築。
- 複数経路を評価。
- 失敗理由を明示。
- DB 更新に自然対応。

ルールは制御ではなく、**推論対象**です。

---

### 7. 想定される医療用途

適している用途：
- ガイドライン整合性検証。
- 診断基準チェック。
- 治療プロトコル検証。
- リスク条件ロジック確認。
- 医学教育。
- 監査・コンプライアンス。

適さない用途：
- 自動診断。
- 緊急医療判断。
- 患者向け直接助言。

---

### 8. 医療に適した理由（構造面）

医療では：
- 「分からない」と言える。
- 不確実性を出せる。
- 監査可能。
- 安全に失敗する。

ことが必須です。Verantyx はこの前提で設計されています。

---

### 9. まとめ

Verantyx が医療に向いている理由：
- 医学知識を捏造しない。
- 不確実性を隠さない。
- 正当化なしに答えない。
- 仮定と限界を常に明示する。

**医療では「正しさ」は必須条件です。Verantyx はその前提で作られています。**
