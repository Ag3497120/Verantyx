# Verantyx (avh-math) – Vibe Coding Guide
**Making Symbolic Reasoning Accessible to Everyone**

---

## English

### 1. Why We Chose Vibe Coding (Intentionally)

This project was intentionally developed using vibe coding. That choice was not a shortcut; it was a design decision. Verantyx aims to prove the following claim:
> **You do not need to be a professional programmer to build, modify, or evolve a reasoning system — if the system itself is structured correctly.**

Vibe coding aligns perfectly with this philosophy.

---

### 2. What “Vibe Coding” Means in This Project

In the context of Verantyx, vibe coding means:
- Conversational development
- Incremental, reasoning-driven changes
- Structural thinking over syntax mastery
- Letting intent drive architecture, not boilerplate

The core logic, pipeline, and database structures were developed through interactive dialogue, not traditional top-down coding alone.

---

### 3. Gemini CLI Chat Logs as First-Class Artifacts

To make this process transparent and reproducible, the full Gemini CLI chat history used during development is saved as .txt files.

**Where to find them:**
The chat logs are stored directly in the root directory of the repository. They are intentionally placed there:
- Not hidden
- Not compressed
- Not summarized

These files show:
- How ideas evolved
- How problems were discovered
- How architectural decisions were made
- How non-trivial logic emerged step by step

They are not supplementary material. They are part of the project.

---

### 4. Why This Matters

Most AI projects claim to be “open”. Verantyx shows how it was actually built. This allows:
- Non-programmers to follow the reasoning
- Domain experts (medical, legal, compliance) to understand the logic without reading code
- Contributors to learn how to think with the system, not just how to run it

---

### 5. Verantyx Is Designed to Be Easy to Modify

Verantyx is easy to work with because:
- Knowledge lives in editable JSONL databases
- Rules are explicit, not implicit
- There is no hidden training state
- Changing behavior does not require retraining
- Most changes do not require touching Python code at all

You can add rules, remove rules, replace entire domains, or swap medical DBs for legal or financial DBs — all without being a programmer.

---

### 6. Programming Skill Is Optional, Not Required

To interact meaningfully with Verantyx, you mainly need:
- Logical thinking
- Domain knowledge
- The ability to describe conditions and exclusions clearly

You do not need deep Python knowledge, an ML background, or training infrastructure. This is by design.

---

### 7. Planned GUI Editor for Non-Programmers

To further lower the barrier, a Verantyx-compatible GUI DB editor is planned. This editor will be CAD-like, visual, no-code, and safe-by-construction. The goal is to allow anyone — including clinicians, lawyers, and compliance officers — to edit reasoning rules without writing code.

---

### 8. The Core Message

Verantyx is not impressive because it is complex. It is impressive because:
> **It stays simple — even while doing rigorous reasoning.**

The use of vibe coding is proof of that simplicity.

---

### 9. Final Note

If you can explain a rule in words, you can make Verantyx reason about it. **That is the point.**

---

### 10. Vibe Coding as a Statement: Verantyx Does Not Replace LLMs

One additional and important reason for adopting vibe coding in this project is to make a clear statement about the role of Verantyx. Verantyx is not designed to replace large language models. It is designed to coexist with them.

#### 10.1 Verantyx and LLMs Have Different Roles
- **LLMs excel at**: Natural language understanding, text generation, and conversational interfaces.
- **Verantyx excels at**: Explicit logical reasoning, deterministic verification, and safety-critical decision boundaries.

These roles are complementary, not competitive.

#### 10.2 Why Vibe Coding Makes This Explicit
By developing Verantyx through conversational, LLM-assisted vibe coding:
- We demonstrate that LLMs are tools, not enemies.
- We show that Verantyx does not reject language models.
- We make it clear that Verantyx depends on clarity, not raw intelligence.

#### 10.3 Verantyx as a Structural Counterpart, Not a Successor
Verantyx exists to handle what LLMs should not be trusted to do alone: Medical decision criteria, legal constraints, and financial rule validation. In these domains, ambiguity is unacceptable. Vibe coding reinforces this boundary: LLMs help humans express intent, while Verantyx enforces structure and limits.

#### 10.4 A Clear Boundary by Design
The development process itself reflects the architecture:
- LLMs assist in designing rules.
- Humans validate and encode constraints.
- Verantyx executes reasoning deterministically.
No component pretends to be everything.

#### 10.5 The Intended Future Workflow
The long-term vision is a collaborative workflow where humans and LLMs express rules clearly, and Verantyx validates or rejects them with formal proof. Vibe coding is the front door to this vision.

#### 10.6 Final Clarification
Verantyx is not an “anti-LLM” project. It is a post-hallucination project. LLMs generate ideas; Verantyx decides whether those ideas are allowed to stand.

---
---

## 日本語（Japanese）

### 1. なぜあえて「バイブコーディング」を採用したのか

このプロジェクトは、意図的にバイブコーディングを使って開発されました。これは手抜きではありません。設計思想そのものです。Verantyx が示したいのは、次の一点です。
> **正しく構造化された推論システムであれば、プログラミングの専門家でなくても進化させられる。**

その証明として、バイブコーディングを選びました。

---

### 2. Verantyx におけるバイブコーディングとは

ここで言うバイブコーディングとは：
- 対話ベースの開発
- 思考の流れを重視した実装
- 構文より構造
- 意図が先、コードが後

設計・修正・判断は、会話の中で行われました。

---

### 3. Gemini CLI のチャット履歴を公開している理由

このプロジェクトでは、Gemini CLI とのチャット履歴を .txt 形式で保存し、リポジトリのルートディレクトリに配置しています。これは意図的です。

**何が分かるか：**
- 思考の変遷
- 問題の発見過程
- 設計判断の理由
- どこで何を諦め、何を選んだか

すべてが残っています。これらは「資料」ではなく、プロジェクトの一部です。

---

### 4. なぜ重要なのか

多くのAIプロジェクトは「完成物」しか見せません。Verantyx は、どう考えたか、なぜそうなったか、どう修正されたかをそのまま見せます。これは、プログラミングができない人、医療・法律・金融の専門家にとって非常に重要です。

---

### 5. Verantyx が「簡単」にいじれる理由

Verantyx が簡単なのは偶然ではありません。
- 知識は JSONL にある
- ルールは明示的
- 学習状態は存在しない
- 再学習は不要
- コードを触らなくても挙動が変わる

DBを書き換えるだけで思考が変わります。

---

### 6. プログラミング能力は必須ではない

Verantyx を扱うのに必要なのは、論理的思考、ドメイン知識、そして条件を言語化する力です。Python の高度な知識は不要です。これは設計上の選択です。

---

### 7. 非エンジニア向けGUI（将来予定）

今後、Verantyx対応のGUI編集ツールをリリース予定です。CAD風UI、ノーコード、条件・除外の可視化、即時検証を目指しています。誰でも安全にDBを編集できる環境を提供することが目的です。

---

### 8. 伝えたいこと

Verantyx は複雑だからすごいのではありません。簡単なまま、厳密であることが価値です。バイブコーディングは、その証明です。

---

### 9. 最後に

ルールを言葉で説明できるなら、Verantyxに考えさせることができます。それが、このプロジェクトの本質です。

---

### 10. バイブコーディングが示すもう一つの意図

**VerantyxはLLMを置き換えるものではない**

バイブコーディングを採用した理由には、Verantyxの立ち位置を明確に示すという重要な意図も含まれています。VerantyxはLLMを置き換えるためのシステムではなく、LLMと共存するためのシステムです。

#### 10.1 VerantyxとLLMの役割の違い
- **LLMが得意なこと**: 自然言語理解、文章生成、対話インターフェース。
- **Verantyxが得意なこと**: 明示的な論理推論、決定論的検証、反例の構成、安全境界の管理。

競合ではなく、補完関係です。

#### 10.2 なぜバイブコーディングが重要なのか
LLMを使った対話的開発（バイブコーディング）をあえて採用することで、LLMは「敵」ではなく「道具」であり、Verantyxは言語モデルを否定せず、知能よりも「構造」を重視する立場を明確にしています。

#### 10.3 後継ではなく、構造的カウンターパート
Verantyx は、LLM単体では任せてはいけない領域（医療判断、法律、金融ルール）を担当します。ここでは曖昧さは許されません。バイブコーディングはこの境界を強調します：LLMは意図の言語化を助け、Verantyxは構造と制限を課します。

#### 10.4 設計そのものが境界を表している
開発フロー自体が思想を表しています。LLMがルールの設計を補助し、人間が条件を定義し、Verantyxが決定論的に実行します。誰も「万能」を装わない、意図的な分業です。

#### 10.5 想定している理想的なワークフロー
人間とLLMが対話してルールを明示化し、Verantyxがそれを検証・証明・あるいは却下する。不確実性を隠さず残すこの流れの入口が、バイブコーディングです。

#### 10.6 最終的な位置づけ
Verantyxは「反LLM」ではなく、ハルシネーション以後のためのシステムです。LLMが案を出し、Verantyxが「それは通してよいか」を判断します。