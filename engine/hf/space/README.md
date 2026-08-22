---
title: Ask Vera
emoji: ✚
colorFrom: gray
colorTo: blue
sdk: gradio
sdk_version: 5.9.1
app_file: app.py
pinned: false
license: mit
---

Ask a knowledge structure that answers with a citation, and refuses in
types when it cannot. No weights, no sampling, no LLM: the same question
always produces the same answer.

The store is [Verantyx/vera-alpha](https://huggingface.co/Verantyx/vera-alpha),
a single SQLite file — download it and check any claim with `sqlite3`.
