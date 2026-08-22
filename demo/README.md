---
title: Verantyx Vera — 矛盾が消えない状況板 / The board where disagreement survives
emoji: 🧭
colorFrom: indigo
colorTo: gray
sdk: gradio
sdk_version: "5.9.1"
app_file: app.py
pinned: false
license: mit
---

# Verantyx Vera α — deterministic truth board

複数の文書を入れると、**確定 / 更新 / 係争 / 未回答** を出典付きで分離した
状況板を作ります。LLM 不使用・完全決定論 — 同じ入力は必ず同じ板になります。

Pour in documents; get settled / updated / contested / unanswered,
each claim with its source. No LLM anywhere: the same input always
produces the same board.

⚠️ このデモに投入した文書は Hugging Face のサーバに送信されます。
**架空データ・公開資料のみ**でお試しください。実データはオフライン版で。
