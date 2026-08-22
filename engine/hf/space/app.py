"""Ask Vera — the sovereign answering in public, refusals included.

The point of putting this on a Space is not the demo, it is that the
refusals are visible. Anything can look good on questions it can answer;
this shows 今日の天気は coming back UNKNOWN_TIME_DEPENDENT and says why that
one cannot be closed by registering more documents, next to 正当防衛とは
coming back with the statute division it read.

The store is `vera.db`, pulled from the model repo at startup. It is SQLite,
so nothing is unpickled and the file the Space queries is the same file a
visitor can download and audit with `sqlite3`.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import gradio as gr

REPO = os.environ.get("VERA_REPO", "Verantyx/vera-alpha")

#: Each verdict, in one line, in the two languages the sovereigns hold.
WHY = {
    "ANSWER": ("読んだ文書に主語が核として在り、面が答えを支えた。",
               "The subject is held as a core and its facets carried the answer."),
    "SEEDED": ("直接の合議は届かなかったので、階段が核を一つ指し、"
               "推論核はその核だけを種に走った（面を足すと薄まる）。",
               "The census did not reach; the staircase named one core and the "
               "inference ran from that subject alone."),
    "AMBIGUOUS": ("複数の核が同数で並び、同点は割らない。",
                  "Several cores tied, and ties are never broken."),
    "UNKNOWN_NO_EVIDENCE": ("その主語について読んだものが無い。",
                            "Nothing was read about this subject."),
    "UNKNOWN_NOT_PRESENT": ("語は在るが、答えを支える面が無い。",
                            "The term is held but no facet supports an answer."),
    "UNKNOWN_NO_SUBJECT": ("問いに主語が無い。",
                           "The question names no subject."),
    "UNKNOWN_TIME_DEPENDENT": ("「今日」は問いの側の性質で、この store に時計は無い。"
                               "文書を登録しても閉じない。",
                               "The deictic is a property of the question; this "
                               "store has no clock. Registering documents does "
                               "not close it."),
    "UNKNOWN_LANGUAGE_NOT_HELD": ("その言語のソブリンを組んでいない。"
                                  "別のトークナイザに渡せば、読んでいない store が答える。",
                                  "No sovereign was built for this language."),
}

_vera = None


def engine():
    global _vera
    if _vera is None:
        from huggingface_hub import hf_hub_download
        from verantyx.export_sqlite import vera

        db = hf_hub_download(repo_id=REPO, filename="vera.db")
        w = Path(db).parent / "writer.json"
        if not w.exists():
            try:
                w = Path(hf_hub_download(repo_id=REPO, filename="writer.json"))
            except Exception:
                pass
        _vera = vera(Path(db))
    return _vera


def ask(q: str):
    q = (q or "").strip()
    if not q:
        return "", "", ""
    t = time.time()
    r = engine().ask(q)
    ms = (time.time() - t) * 1000

    v = r.get("verdict", "?")
    ja, en = WHY.get(v, ("", ""))
    head = f"### `{v}`  ·  {r.get('language','?')}  ·  {ms:.1f} ms\n\n{ja}\n\n*{en}*"

    body = ""
    if r.get("core"):
        body += f"**核** `{r['core']}`\n\n"
    if r.get("text"):
        body += "**構造の経路** " + " → ".join(str(r["text"]).split()) + "\n\n"
    w = r.get("written") or {}
    for s in (w.get("sentences") or [])[:3]:
        body += f"> {s.get('text') if isinstance(s, dict) else s}\n\n"
    for landed in (r.get("reached") or [])[:3]:
        body += (f"*届いた経路* `{landed.get('verdict')}` "
                 f"{landed.get('term')} → {landed.get('core')}\n\n")

    rem = r.get("remedy") or {}
    tail = ""
    if isinstance(rem, dict) and rem.get("register"):
        closes = ("登録で閉じる / closes by registration"
                  if rem.get("needs_registration")
                  else "登録では閉じない / registration does not close this")
        tail = f"**次の一手** — {rem['register']}  \n*{closes}*"
        if rem.get("why"):
            tail += f"\n\n{rem['why']}"
        elif rem.get("then"):
            tail += f"\n\nthen: {rem['then']}"
    return head, body or "_（構造は返らなかった）_", tail


EXAMPLES = [["正当防衛とは"], ["殺人罪の刑は"], ["契約の成立要件は"],
            ["今日の天気は"], ["こんにちは"], ["フロベニウス双対とは"],
            ["negligence"], ["what is consideration"], ["jurisdiction"]]

with gr.Blocks(title="Vera に訊く / Ask Vera") as demo:
    gr.Markdown(
        "# Vera に訊く / Ask Vera\n"
        "言語モデルではありません。重みも標本抽出もなく、同じ問いは常に同じ答えを返します。"
        "答えられないときは、**なぜ答えられないかを型で**返します。\n\n"
        "*Not a language model. No weights, no sampling — the same question "
        "always gives the same answer, and when it cannot answer it says which "
        "kind of not-knowing it is.*")
    with gr.Row():
        box = gr.Textbox(label="問い / question", scale=4,
                         placeholder="正当防衛とは")
        go = gr.Button("訊く / Ask", variant="primary", scale=1)
    verdict = gr.Markdown()
    struct = gr.Markdown()
    remedy = gr.Markdown()
    gr.Examples(EXAMPLES, inputs=box)
    go.click(ask, box, [verdict, struct, remedy])
    box.submit(ask, box, [verdict, struct, remedy])

if __name__ == "__main__":
    demo.launch()
