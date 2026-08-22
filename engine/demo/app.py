"""Verantyx Vera α — the truth board demo.

Pour documents in; get settled / updated / contested / unanswered, every
claim carrying its source. No LLM anywhere in the pipeline: the same input
always produces the same board, which is the property the whole system is
built around and the one a demo must not quietly break.

The analysis functions are pure and importable without Gradio, so the
pipeline this demo runs is testable in CI exactly as the users run it.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional, Tuple

# The Space clones the whole repository; the package sits one level up.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verantyx.arm_schema import ArmIndex                       # noqa: E402
from verantyx.cross_store import CrossStore                    # noqa: E402
from verantyx.document_ingest import (Document, deep_report,   # noqa: E402
                                      ingest_documents)
from verantyx.document_loaders import load_path                # noqa: E402
from verantyx.intake_quality import assess                     # noqa: E402

# ---------------------------------------------------------------------------
# Fictional sample — two "outlets", one afternoon, one road reopening.
# Fictional on purpose: what goes into a public demo goes to a server.
# ---------------------------------------------------------------------------

SAMPLE_A = ("国道9号は土砂崩れで通行止です。中央公民館の避難所は開設されました。"
            "毛布と飲料水を配布しています。給水車が巡回しています。")
SAMPLE_A_META = ("架空新聞", "2026-08-06 09:00")
SAMPLE_B = ("国道9号は復旧作業が完了し通行可能になりました。"
            "中央公民館の避難所は閉鎖されました。水道は復旧しています。")
SAMPLE_B_META = ("架空放送", "2026-08-06 15:00")


def analyze(docs: List[Document]) -> str:
    """Documents → the board, as Markdown. Pure, deterministic, testable."""
    if not docs:
        return "文書がありません。/ No documents."
    store, arms = CrossStore(), ArmIndex()
    rep = ingest_documents(store, docs, arms)
    intake = assess(store, rep)

    out: List[str] = []
    m = intake["metrics"]
    out.append(f"**取り込み / Intake**: {m['sentences_placed']} 文 / "
               f"{m['sources']} 出典 / 被覆率 {m['coverage']}"
               f" — 判定 **{intake['verdict']}**")
    for f in intake["findings"]:
        out.append(f"> ⚠️ {f['verdict']}: {f['meaning']}")
    out.append("")

    cores = sorted(set(rep.cores),
                   key=lambda c: -store.core_count.get(c, 0))
    contested_any = updated_any = False
    for core in cores:
        d = deep_report(store, core, arms)
        if not (d["disputed"] or d["updated"] or d["settled"]):
            continue
        out.append(f"### {core} — {d['confidence']}")
        for e in d["disputed"]:
            contested_any = True
            sides = " **対** ".join(
                f"{s['claim']}（{', '.join(s['sources']) or '出典不明'}）"
                for s in e["sides"])
            out.append(f"- 🔴 **係争**: {sides} — この点は未確定です")
        for e in d["updated"]:
            updated_any = True
            cur = e["current"]
            olds = "、".join(f"{s['claim']}（{', '.join(s['sources'])}・{s['when']}）"
                             for s in e["superseded"])
            out.append(f"- 🔄 **更新**: 現在は **{cur['claim']}**"
                       f"（{', '.join(cur['sources'])}・{cur['when']} 時点）。"
                       f" それ以前: {olds}")
        for sitem in d["settled"][:6]:
            out.append(f"- ⚪ {sitem['claim']}"
                       f"（{', '.join(sitem['sources']) or '—'}）")
        missing = d.get("missing") or []
        if missing:
            out.append(f"- ❔ 未回答: {'、'.join(x['arm'] for x in missing)}")
        out.append("")

    out.append("---")
    out.append("🔴 係争 = 出典が食い違い、どちらも現役。"
               " 🔄 更新 = 時刻が順序づく同一の話(新しい方が現在)。"
               " 判定は決定論的 — 同じ入力は必ず同じ板になります。")
    if not contested_any and not updated_any:
        out.append("係争・更新は検出されませんでした。既知の対義語彙に"
                   "ある状態語(通行止/通行可能、開設/閉鎖…)が対象です。")
    return "\n".join(out)


def analyze_texts(text_a: str, src_a: str, when_a: str,
                  text_b: str, src_b: str, when_b: str) -> str:
    docs = []
    if (text_a or "").strip():
        docs.append(Document(src_a or "出典A", text_a, when_a or ""))
    if (text_b or "").strip():
        docs.append(Document(src_b or "出典B", text_b, when_b or ""))
    return analyze(docs)


def analyze_files(files: Optional[List[str]]) -> str:
    docs, skipped = [], []
    for fp in files or []:
        res = load_path(str(fp))
        if res["verdict"] == "ANSWER":
            docs.append(res["document"])
        else:
            skipped.append(f"{Path(str(fp)).name}: {res['verdict']}")
    board = analyze(docs)
    if skipped:
        board = ("読めなかったファイル: " + "、".join(skipped) + "\n\n") + board
    return board


def _sample() -> Tuple[str, str, str, str, str, str]:
    return (SAMPLE_A, *SAMPLE_A_META, SAMPLE_B, *SAMPLE_B_META)


try:
    import gradio as gr
except ImportError:                                   # CI imports the pure half
    gr = None

if gr is not None:
    with gr.Blocks(title="Verantyx Vera — truth board") as demo:
        gr.Markdown(
            "# 🧭 Verantyx Vera α — 矛盾が消えない状況板\n"
            "複数の文書から **確定 / 更新 / 係争 / 未回答** を出典付きで分離。"
            "LLM 不使用・完全決定論。\n\n"
            "⚠️ 投入した文書はサーバに送信されます。**架空データ・公開資料のみ**で。")
        with gr.Tab("テキスト2件で試す"):
            with gr.Row():
                with gr.Column():
                    ta = gr.Textbox(label="文書A", lines=5)
                    sa = gr.Textbox(label="出典A", value="出典A")
                    wa = gr.Textbox(label="発表日時A (例 2026-08-06 09:00)")
                with gr.Column():
                    tb = gr.Textbox(label="文書B", lines=5)
                    sb = gr.Textbox(label="出典B", value="出典B")
                    wb = gr.Textbox(label="発表日時B")
            with gr.Row():
                fill = gr.Button("架空サンプルを読み込む")
                run = gr.Button("状況板を作る", variant="primary")
            board = gr.Markdown()
            fill.click(_sample, outputs=[ta, sa, wa, tb, sb, wb])
            run.click(analyze_texts, inputs=[ta, sa, wa, tb, sb, wb],
                      outputs=board)
        with gr.Tab("ファイルで試す"):
            up = gr.Files(label="PDF / Word / HTML / CSV / テキスト",
                          file_count="multiple", type="filepath")
            run2 = gr.Button("状況板を作る", variant="primary")
            board2 = gr.Markdown()
            run2.click(analyze_files, inputs=up, outputs=board2)

    if __name__ == "__main__":
        demo.launch()
