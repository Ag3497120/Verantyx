# Verantyx Database Editing Guide

This guide explains how to modify the internal knowledge base of Verantyx, where the files are located, potential risks, and the project's current status.

---

## English Guide

### 1. Database Locations

Verantyx does not use a black-box database. All knowledge is stored in plain text (JSONL) files within the repository.

- **Main Knowledge Base (Axioms, Theorems):**
  `avh_math/db/foundation_kb.jsonl`
  *(Contains mathematical definitions, logical axioms, and known theorems.)*

- **Word Memory (Semantic Roles):**
  `avh_math/db/word_memory.json`
  *(Defines how English words are interpreted, e.g., "always" -> Quantifier.)*

- **Semantic Patterns (Grammar):**
  `avh_math/db/semantic_patterns.jsonl`
  *(Defines sentence structures for parsing natural language queries.)*

### 2. How to Edit

The database files are in **JSONL (JSON Lines)** format.
- Each line is a valid, independent JSON object.
- You can add, delete, or modify lines using any text editor (VS Code, Notepad, Vim, etc.).

**Example: Adding a new axiom**
Open `foundation_kb.jsonl` and append a new line:
```json
{"id": "my_custom_axiom", "domain": "modal_logic", "kind": "axiom", "statement": "[]p -> p", "logic_system": ["T"]}
```

### 3. Risks & Caveats (What could go wrong?)

Since Verantyx relies entirely on these files for reasoning, editing them carries some risks:

- **JSON Syntax Errors:**
  If a line contains invalid JSON (e.g., missing comma, unclosed quote), the system may crash or fail to load that specific entry. The loader is designed to skip broken lines, but large errors can disrupt the index.

- **Contradictory Knowledge:**
  If you add axioms that contradict existing ones (e.g., `A -> B` and `A -> ~B`), the system may produce `DISPROVED` for valid formulas or `PROVED` for invalid ones, depending on which axiom is prioritized. Verantyx detects logical contradictions during derivation, but it assumes the DB itself is consistent.

- **Performance Impact:**
  Adding thousands of entries without optimization may slow down the startup time or the retrieval process (`KB Matcher`).

### 4. Project Status: Research & Experimental

**Verantyx is an active research project.**

- **Not Production Ready:** This system is designed for experimental logic verification and educational purposes. Do not use it for critical financial, medical, or legal decisions without expert supervision.
- **Evolving Architecture:** The internal structure of the database or the solver pipeline may change in future versions.
- **Community Driven:** We encourage you to fork, experiment, and break things. Discovering edge cases is part of the process.

---
---

## 日本語ガイド

### 1. データベースの場所

Verantyx はブラックボックスなデータベースを使用しません。すべての知識はリポジトリ内のプレーンテキスト（JSONL）ファイルに保存されています。

- **メイン知識ベース（公理・定理）:**
  `avh_math/db/foundation_kb.jsonl`
  *(数学的定義、論理公理、既知の定理が含まれます。)*

- **単語記憶（意味役割）:**
  `avh_math/db/word_memory.json`
  *(英単語の解釈を定義します。例: "always" -> 全称記号)*

- **意味パターン（文法）:**
  `avh_math/db/semantic_patterns.jsonl`
  *(自然言語クエリを解析するための文構造を定義します。)*

### 2. 編集方法

データベースファイルは **JSONL (JSON Lines)** 形式です。
- 各行が独立した有効な JSON オブジェクトです。
- 任意のテキストエディタ（VS Code, メモ帳, Vim など）を使用して、行の追加、削除、修正が可能です。

**例：新しい公理の追加**
`foundation_kb.jsonl` を開き、新しい行を追加します：
```json
{"id": "my_custom_axiom", "domain": "modal_logic", "kind": "axiom", "statement": "[]p -> p", "logic_system": ["T"]}
```

### 3. リスクと注意点（編集時に起こりうること）

Verantyx は推論のためにこれらのファイルに完全に依存しているため、編集にはいくつかのリスクが伴います。

- **JSON 構文エラー:**
  行に無効な JSON（カンマの欠落、閉じられていないクォートなど）が含まれている場合、システムがクラッシュするか、そのエントリの読み込みに失敗する可能性があります。ローダーは壊れた行をスキップするように設計されていますが、大規模なエラーはインデックス作成を妨げる可能性があります。

- **矛盾する知識:**
  既存の知識と矛盾する公理（例：`A -> B` と `A -> ~B` の両方）を追加した場合、どの公理が優先されるかによって、正しい式に対して `DISPROVED` が出たり、その逆が起きたりする可能性があります。Verantyx は推論中に論理的矛盾を検知しますが、DB 自体は整合していることを前提としています。

- **パフォーマンスへの影響:**
  最適化なしに数千件のエントリを追加すると、起動時間や検索プロセス（KB Matcher）が遅くなる可能性があります。

### 4. プロジェクトのステータス：研究・実験段階

**Verantyx は現在進行中の研究プロジェクトです。**

- **商用利用への注意:** 本システムは、実験的な論理検証および教育目的で設計されています。専門家の監修なしに、金融、医療、法律などの重大な意思決定に使用しないでください。
- **進化するアーキテクチャ:** データベースの内部構造やソルバーのパイプラインは、将来のバージョンで変更される可能性があります。
- **コミュニティ主導:** フォークし、実験し、壊してみることを推奨します。エッジケースを発見することもプロセスの一部です。
