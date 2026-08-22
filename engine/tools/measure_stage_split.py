"""Stage-boundary splitter measurement. Bank-first protocol.

tools/stage_bank_2026-08-14.json is written BEFORE the first
verantyx.stage_split.split call. The wrapper below refuses to split
if that file is missing. Numbers below are burned from the first
bank run after registration.

## Measured — preregistered bank 2026-08-14, 30 questions

    exact-match (whole chain)        30 / 30
    boundary precision               1.0000
    boundary recall                  1.0000
    false-split rate (10 nosplit)    0 / 10   the bad failure
    abstention count                 10
    (UNKNOWN_UNSEGMENTED; all 10 hard items)

    by kind
        multihop exact               10 / 10
        nosplit exact                10 / 10
        hard abstain                 10 / 10

    fork STAGE_SPLIT_DEFENSE         pass
    tokenizer                        surface-rules
    bank predates first split        yes
    (bank mtime 1786710138 < first split 1786710178)

The 30/30 is rule-consistency: expected chains were handwritten
from the same frozen tables before the first split call, not an
independent linguistic gold. False-split 0/10 is the acceptance
line — splitting 東京の人口 is worse than abstaining on 背任罪.

## Measured — amendment 2026-08-14T21:26:00+09:00 (temporal exclusion)

    exact-match (old 30 + 10 new)    40 / 40
    boundary precision               1.0000
    boundary recall                  1.0000
    false-split rate (18 nosplit)    0 / 18   the bad failure
    (old 10 + 8 temporal lefts)
    abstention count                 10
    (still the original 10 hard items)

    by kind
        multihop exact               12 / 12
        nosplit exact                18 / 18
        hard abstain                 10 / 10

    fork STAGE_SPLIT_DEFENSE         pass
    (今年の予算額 / 昨日の提出先 stay 1 stage;
     殺人罪の刑の上限 → 殺人罪 → 刑の上限)
    amendment predates first
    amendment split                  yes
    (registered_amendment set; first
     amendment split at call 31)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verantyx.stage_split import regression, split

BANK = Path(__file__).resolve().parent / "stage_bank_2026-08-14.json"

_SPLIT_CALLS = 0
_FIRST_SPLIT_AT: float = 0.0


def _checked_split(query: str) -> Dict[str, Any]:
    global _SPLIT_CALLS, _FIRST_SPLIT_AT
    if not BANK.is_file():
        raise SystemExit("bank file missing before first split: %s" % BANK)
    if _SPLIT_CALLS == 0:
        _FIRST_SPLIT_AT = time.time()
    _SPLIT_CALLS += 1
    return split(query)


def _pairs(stages: Sequence[Dict[str, Any]]) -> List[Tuple[str, str]]:
    return [(str(s.get("condition", "")), str(s.get("head", "")))
            for s in stages]


def _expected_cuts(text: str, stages: Sequence[Dict[str, Any]]) -> List[int]:
    pos = 0
    cuts: List[int] = []
    for i, st in enumerate(stages):
        frag = str(st.get("condition", "")) + str(st.get("head", ""))
        j = text.find(frag, pos)
        if j < 0:
            return []
        end = j + len(frag)
        if i < len(stages) - 1:
            cuts.append(end)
        pos = end
    return cuts


def _exact(got: Dict[str, Any], exp: Dict[str, Any]) -> bool:
    if got.get("verdict") != exp.get("verdict"):
        return False
    if exp.get("verdict") == "UNKNOWN_UNSEGMENTED":
        return True
    return _pairs(got.get("stages") or []) == _pairs(exp.get("stages") or [])


def main() -> None:
    if not BANK.is_file():
        raise SystemExit("preregistered bank missing: %s" % BANK)
    bank_stat = BANK.stat()
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    items = list(bank["items"])
    amendment = list(bank.get("amendment_items") or [])
    if amendment and not bank.get("registered_amendment"):
        raise SystemExit("amendment_items present without registered_amendment")
    print("bank", BANK, "n", len(items), "amendment", len(amendment),
          "mtime", int(bank_stat.st_mtime),
          "registered", bank.get("registered"),
          "registered_amendment", bank.get("registered_amendment"),
          "split_calls_so_far", _SPLIT_CALLS, flush=True)
    if _SPLIT_CALLS != 0:
        raise SystemExit("split ran before the bank was loaded")

    from verantyx.stage_split import _strip

    tp = fp = fn = 0
    exact = 0
    abstain = 0
    false_split = 0
    n_nosplit = 0
    by_kind = {"multihop": [0, 0], "nosplit": [0, 0], "hard": [0, 0]}
    rows: List[Dict[str, Any]] = []

    all_items = items + amendment
    for it in all_items:
        q = it["q"]
        exp = it["expected"]
        kind = it["kind"]
        if it is amendment[0] if amendment else False:
            print("protocol_amendment_predates_first_amendment_split",
                  bool(bank.get("registered_amendment")),
                  "registered_amendment", bank.get("registered_amendment"),
                  "split_calls_so_far", _SPLIT_CALLS, flush=True)
        got = _checked_split(q)
        if it is all_items[0]:
            print("protocol_bank_predates_first_split",
                  bank_stat.st_mtime <= _FIRST_SPLIT_AT,
                  "bank_mtime", int(bank_stat.st_mtime),
                  "first_split_at", int(_FIRST_SPLIT_AT),
                  flush=True)
        ok = _exact(got, exp)
        if ok:
            exact += 1
            by_kind[kind][0] += 1
        by_kind[kind][1] += 1
        if got.get("verdict") == "UNKNOWN_UNSEGMENTED":
            abstain += 1
        if kind == "nosplit":
            n_nosplit += 1
            n_st = len(got.get("stages") or [])
            if got.get("verdict") == "STAGED" and n_st > 1:
                false_split += 1

        text = _strip(q)
        if exp.get("verdict") == "STAGED":
            exp_cuts = _expected_cuts(text, exp.get("stages") or [])
        else:
            exp_cuts = []
        pred_cuts = list(got.get("cuts") or []) if got.get("verdict") == "STAGED" else []
        exp_set, pred_set = set(exp_cuts), set(pred_cuts)
        tp += len(exp_set & pred_set)
        fp += len(pred_set - exp_set)
        fn += len(exp_set - pred_set)
        rows.append({
            "id": it["id"], "kind": kind, "ok": ok,
            "q": q, "got_verdict": got.get("verdict"),
            "got_stages": _pairs(got.get("stages") or []),
            "exp_stages": _pairs(exp.get("stages") or []),
            "reason": got.get("reason"),
            "chain": got.get("chain"),
        })

    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    fs_rate = false_split / n_nosplit if n_nosplit else 0.0

    print("regression…", flush=True)
    fork = regression()
    print(json.dumps({"fork": fork["fork"], "pass": fork["pass"],
                      "result": fork["result"]}, ensure_ascii=False),
          flush=True)
    if not fork["pass"]:
        raise SystemExit("STAGE_SPLIT_DEFENSE failed")

    report = {
        "n": len(all_items),
        "n_original": len(items),
        "n_amendment": len(amendment),
        "exact_match": exact,
        "exact_rate": exact / len(all_items) if all_items else 0.0,
        "boundary_tp": tp,
        "boundary_fp": fp,
        "boundary_fn": fn,
        "boundary_precision": prec,
        "boundary_recall": rec,
        "false_split": false_split,
        "false_split_rate": fs_rate,
        "n_nosplit": n_nosplit,
        "abstention": abstain,
        "by_kind": {k: {"exact": v[0], "n": v[1]} for k, v in by_kind.items()},
        "split_calls": _SPLIT_CALLS,
        "tokenizer": bank.get("tokenizer"),
        "head_nouns": bank.get("head_nouns"),
        "temporal_nouns": bank.get("temporal_nouns"),
        "registered_amendment": bank.get("registered_amendment"),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    print("MISMATCHES", flush=True)
    for r in rows:
        if not r["ok"]:
            print(json.dumps(r, ensure_ascii=False), flush=True)
    flag = next(r for r in rows if r["id"] == "M01")
    print("FLAGSHIP", json.dumps(flag, ensure_ascii=False), flush=True)
    print(
        "MEASURED exact %d/%d  prec %.4f  rec %.4f  "
        "false-split %d/%d  abstain %d"
        % (exact, len(all_items), prec, rec, false_split, n_nosplit, abstain),
        flush=True,
    )


if __name__ == "__main__":
    main()
