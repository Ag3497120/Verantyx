"""Exact-match measurement of the closed intent-frame table.

Protocol (SPEC_2026-08-14_eight_gaps W1b). The bank
`tools/intent_bank_2026-08-14.json` is preregistered BEFORE the first
`parse` call. 50 in-table instructions carry a hand-written {op, object};
15 out-of-table instructions (novel verb / pure question / verbless
fragment) carry UNKNOWN_INTENT. A single fabricated intent on the 15
is a design failure.

Scoring
    exact     op and object both match (50)
    op-only   op matches, object may miss (50)
    refusal   verdict is UNKNOWN_INTENT (15). Pass line is 15/15.

## Measured — intent_bank_2026-08-14, closed table, no LLM

    in-table                 50
    out-of-table             15
    exact (op+object)        50/50   1.0000
    op-only                  50/50   1.0000
    refusal (UNKNOWN_INTENT) 15/15   1.0000   pass line PASS
    exact misses             (none)
    fabricated intents       (none)

    Refusal is the pass line: 15/15. A single invented op on an
    out-of-table row would fail the deliverable. None were invented.

    Verbatim
        geminiを開いて
            {"verdict": "INTENT", "op": "OPEN", "args": {"object": "gemini"}}
        東京から大阪まで距離を測りたい
            {"verdict": "INTENT", "op": "MEASURE",
             "args": {"from": "東京", "to": "大阪", "object": "距離"}}
        カレーを料理する
            {"verdict": "UNKNOWN_INTENT"}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verantyx.intent_frames import parse

BANK = Path(__file__).resolve().parent / "intent_bank_2026-08-14.json"


def main() -> int:
    if not BANK.is_file():
        print("REFUSE: bank is not on disk; parse is not called.", file=sys.stderr)
        return 2
    bank = json.loads(BANK.read_text())
    in_table = bank["in_table"]
    out_table = bank["out_of_table"]
    if len(in_table) != 50 or len(out_table) != 15:
        print(f"REFUSE: bank size {len(in_table)}+{len(out_table)}, not 50+15.",
              file=sys.stderr)
        return 2

    exact = 0
    op_only = 0
    exact_miss = []
    op_miss = []
    for row in in_table:
        got = parse(row["text"])
        op = got.get("op")
        args = got.get("args") or {}
        obj = args.get("object") if isinstance(args, dict) else None
        op_ok = got.get("verdict") == "INTENT" and op == row["op"]
        obj_ok = obj == row["object"]
        if op_ok:
            op_only += 1
        else:
            op_miss.append((row, got))
        if op_ok and obj_ok:
            exact += 1
        else:
            exact_miss.append((row, got))

    refuse_ok = 0
    refuse_miss = []
    for row in out_table:
        got = parse(row["text"])
        if got.get("verdict") == "UNKNOWN_INTENT":
            refuse_ok += 1
        else:
            refuse_miss.append((row, got))

    n50, n15 = 50, 15
    print(f"bank        {BANK.name}  registered {bank.get('registered')}")
    print(f"exact       {exact}/{n50}  {exact / n50:.4f}")
    print(f"op-only     {op_only}/{n50}  {op_only / n50:.4f}")
    print(f"refusal     {refuse_ok}/{n15}  {refuse_ok / n15:.4f}"
          f"  pass_line={'PASS' if refuse_ok == n15 else 'FAIL'}")

    print("\n--- exact misses ---")
    if not exact_miss:
        print("(none)")
    for row, got in exact_miss:
        print(f"  id={row['id']} text={row['text']!r}")
        print(f"    expected op={row['op']!r} object={row['object']!r}")
        print(f"    got      {got}")

    print("\n--- refusal misses (fabricated intent) ---")
    if not refuse_miss:
        print("(none)")
    for row, got in refuse_miss:
        print(f"  id={row['id']} text={row['text']!r} why={row.get('why')}")
        print(f"    got {got}")

    print("\n--- verbatim ---")
    for label, text in (
        ("clean", "geminiを開いて"),
        ("multi-arg", "東京から大阪まで距離を測りたい"),
        ("refused", "カレーを料理する"),
    ):
        print(f"  {label}: {text!r} -> {parse(text)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
