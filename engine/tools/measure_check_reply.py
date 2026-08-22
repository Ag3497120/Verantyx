"""check_reply's failure modes, measured BEFORE the IDE wires it in.

The audit the IDE is about to display beside every Vera-session answer
is `Register.check` — the covenant layer (did the reply break something
the user settled). The sorry-trap discipline applies: measure the
verifier's failure shapes first, then wire, and let the wiring's
strength match the measured reality (display beside, never gate).

Five groups:
  A  no covenants registered, any reply        -> must always be KEPT
  B  one covenant, replies OUT of its scope    -> KEPT (the topic gate)
  C  violating replies in scope                -> BROKEN, naming the term
  D  one-word on-topic reply with `asked` set  -> BROKEN (the exchange
     is the scope, per the register's own docstring)
  E  degenerate replies (empty, code-only)     -> KEPT, never a crash

## Measured — 2026-08-14

    A  3/3 KEPT    no covenants is silent, always
    B  4/4 KEPT    the topic gate holds; "テストは全て通りました" and a
                   legal answer never brush a language covenant
    C  2/2 BROKEN  one violation each, the forbidden term named
    D  1/1 BROKEN  「Python。」 against 実装言語は? — exchange scope works
    E  code-only KEPT; the EMPTY reply with an in-scope `asked` reads
       BROKEN (required_missing) — the one failure shape found. It is
       fenced in the IDE wiring by the existing `!saveAnswer.isEmpty`
       guard (empty answers are never audited), and recorded here so
       nobody removes that guard without knowing what it holds back.

Zero false positives outside the fenced shape; the display-only wiring
(beside the answer, never gating it) matches this profile.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verantyx.covenant import Covenant, Register


def fresh() -> Register:
    r = Register()
    r.covenants.append(Covenant(
        name="実装言語はTypeScriptを用いる",
        requires=["TypeScript"], forbids=["JavaScript"],
        topic=["実装言語", "言語"],
        quote="実装言語はTypeScriptを用いる。"))
    return r


empty = Register()
groups = {
    "A_no_covenants": [
        (empty, "こんにちは", ""),
        (empty, "時効の中断は民法にある。", "時効とは"),
        (empty, "The build succeeded.", "did it build?"),
    ],
    "B_out_of_scope": [
        (fresh(), "時効の中断は民法にある。", "時効とは"),
        (fresh(), "こんにちは", ""),
        (fresh(), "テストは全て通りました。", "テスト結果は"),
        (fresh(), "気温は25度です。", "今日の天気は"),
    ],
    "C_violation_in_scope": [
        (fresh(), "実装言語はJavaScriptです。", "実装言語は何にしますか"),
        (fresh(), "この機能はJavaScriptで書きます。実装言語として最適です。",
         "実装言語の方針は"),
    ],
    "D_one_word_exchange": [
        (fresh(), "Python。", "実装言語は何にしますか"),
    ],
    "E_degenerate": [
        (fresh(), "", "実装言語は"),
        (fresh(), "```py\nprint(1)\n```", ""),
    ],
}

out = {}
for name, cases in groups.items():
    rows = []
    for reg, reply, asked in cases:
        r = reg.check(reply, asked=asked)
        rows.append({"reply": reply[:24], "verdict": r["verdict"],
                     "violations": len(r.get("violations") or [])})
    out[name] = rows
print(json.dumps(out, ensure_ascii=False, indent=1))
