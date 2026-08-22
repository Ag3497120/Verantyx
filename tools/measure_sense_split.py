"""Sense-sidecar measurement. Bank-first protocol.

tools/sense_bank_2026-08-14.json is written BEFORE the first
verantyx.sense_split.resolve call on it. The wrapper below refuses
to resolve if that file is missing. Numbers below are burned from
the first bank run after registration.

## Measured — preregistered bank 2026-08-14, 10 surfaces

    sidecar                          122,988 surfaces
    surfaces with >=2 senses         83,050
    (after one alias hop)            165,186
    total sense cores                297,218
    fork SENSE_SPLIT_NAMED_ABSTAIN   pass

    surface list                     10 / 10
    unambiguous RESOLVED             4 / 4     包丁 鉛筆 机 靴
    ambiguous named abstain          6 / 6
    context cases                    3 / 3
        馬 + [麻雀] → ウマ (麻雀)
        馬 + [映画, 麻雀] → AMBIGUOUS_SENSE
        包丁 + [切] → 包丁

    馬 names ウマ (animal) + ウマ (麻雀) + 馬 (映画/姓/シャンチー/曖昧さ回避).
    No silent merge. Bank predates first resolve (mtime 1786712123).

## Measured — registered_amendment 2026-08-14T22:05:00+09:00, primary default

    sidecar                          122,988 surfaces
    surfaces with >=2 senses         83,050
    fork SENSE_SPLIT_NAMED_ABSTAIN   pass

    amendment surfaces               10 / 10
    unambiguous RESOLVED             4 / 4     包丁 鉛筆 机 靴
    RESOLVED_PRIMARY + named others  6 / 6     馬 ウマ 水 平和 愛 リンゴ
    context cases                    3 / 3     (unchanged)
    abstentions                      0

    Old surfaces / first Measured section untouched.
    Amendment registered 2026-08-14T22:05:00+09:00, before this re-run.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verantyx.sense_split import (
    AMBIGUOUS_SENSE,
    OUT,
    RESOLVED,
    RESOLVED_PRIMARY,
    load,
    regression,
    resolve,
    senses_of,
)

BANK = Path(__file__).resolve().parent / "sense_bank_2026-08-14.json"
ALIASES = (Path.home() / "Projects" / "vera-corpus" / "build"
           / "jawiki_aliases.json")

_RESOLVE_CALLS = 0


def _checked_resolve(*args, **kwargs):
    global _RESOLVE_CALLS
    if not BANK.is_file():
        raise SystemExit("bank file missing before first resolve: %s" % BANK)
    _RESOLVE_CALLS += 1
    return resolve(*args, **kwargs)


def _cores(result):
    if result.get("verdict") == RESOLVED:
        return [result.get("core")]
    return [s.get("core") for s in (result.get("senses") or [])]


def _tags(result, items):
    if result.get("verdict") == RESOLVED:
        return []
    return [s.get("domain_tag") or "" for s in (result.get("senses") or [])]


def score_surface(row, result, items):
    verdict = result.get("verdict")
    expect = row["expect_verdict"]
    if expect == RESOLVED:
        if verdict not in (RESOLVED, RESOLVED_PRIMARY):
            return "miss", "verdict %s != %s" % (verdict, expect)
        if result.get("core") != row.get("expect_core"):
            return "miss", "core %s != %s" % (result.get("core"),
                                              row.get("expect_core"))
        return "hit", ""
    if expect == RESOLVED_PRIMARY:
        if verdict != RESOLVED_PRIMARY:
            return "miss", "verdict %s != %s" % (verdict, expect)
        if result.get("core") != row.get("expect_core"):
            return "miss", "core %s != %s" % (result.get("core"),
                                              row.get("expect_core"))
        got_cores = {s.get("core") for s in (result.get("other_senses") or [])}
        got_tags = {s.get("domain_tag") or ""
                    for s in (result.get("other_senses") or [])}
        missing_c = [c for c in (row.get("must_include_other_cores")
                                 or row.get("must_include_cores") or [])
                     if c not in got_cores]
        missing_t = [t for t in (row.get("must_include_other_tags")
                                 or row.get("must_include_tags") or [])
                     if t not in got_tags]
        if missing_c or missing_t:
            return "miss", "missing others cores %s tags %s" % (
                missing_c, missing_t)
        return "hit", ""
    if verdict != expect:
        return "miss", "verdict %s != %s" % (verdict, expect)
    got_cores = {s.get("core") for s in (result.get("senses") or [])}
    got_tags = {s.get("domain_tag") or "" for s in (result.get("senses") or [])}
    missing_c = [c for c in (row.get("must_include_cores") or [])
                 if c not in got_cores]
    missing_t = [t for t in (row.get("must_include_tags") or [])
                 if t not in got_tags]
    if missing_c or missing_t:
        return "miss", "missing cores %s tags %s" % (missing_c, missing_t)
    return "hit", ""


def main() -> int:
    if not BANK.is_file():
        print("REFUSE: bank is not on disk; resolve is not called.",
              file=sys.stderr)
        return 2
    bank_stat = BANK.stat()
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    print("bank", BANK, "n", bank.get("n"), "mtime", int(bank_stat.st_mtime),
          "resolve_calls_so_far", _RESOLVE_CALLS, flush=True)

    print("regression…", flush=True)
    fork = regression()
    print(json.dumps({"fork": fork["fork"], "pass": fork["pass"],
                      "result": fork["result"]}, ensure_ascii=False),
          flush=True)
    if not fork["pass"]:
        raise SystemExit("SENSE_SPLIT_NAMED_ABSTAIN failed")

    if not OUT.is_file():
        raise SystemExit("sense sidecar missing: %s" % OUT)
    senses = load(OUT)
    aliases = json.loads(ALIASES.read_text(encoding="utf-8"))

    rows = []
    hits = misses = 0
    abstentions = 0
    unamb_ok = 0
    unamb_n = 0
    amendment = bank.get("registered_amendment") or {}
    surface_rows = amendment.get("surfaces") or bank["surfaces"]
    for row in surface_rows:
        items = senses_of(row["surface"], senses, aliases)
        result = _checked_resolve(
            row["surface"], row.get("context_tokens") or [],
            senses=senses, aliases=aliases,
        )
        mark, why = score_surface(row, result, items)
        if row.get("expect_verdict") == RESOLVED:
            unamb_n += 1
            if mark == "hit":
                unamb_ok += 1
        if result.get("verdict") == AMBIGUOUS_SENSE:
            abstentions += 1
        if mark == "hit":
            hits += 1
        else:
            misses += 1
        rows.append({
            "surface": row["surface"],
            "expect_verdict": row["expect_verdict"],
            "mark": mark,
            "why": why,
            "verdict": result.get("verdict"),
            "core": result.get("core"),
            "other_senses": result.get("other_senses") or [],
            "senses": result.get("senses") or [
                _named_item(it) for it in items
            ],
            "n_senses": len(items),
        })

    ctx_rows = []
    ctx_hits = ctx_misses = 0
    for row in bank.get("context_cases") or []:
        result = _checked_resolve(
            row["surface"], row.get("context_tokens") or [],
            senses=senses, aliases=aliases,
        )
        ok = result.get("verdict") == row["expect_verdict"]
        if ok and row.get("expect_core"):
            ok = result.get("core") == row["expect_core"]
        if ok:
            ctx_hits += 1
        else:
            ctx_misses += 1
        ctx_rows.append({
            "surface": row["surface"],
            "context_tokens": row.get("context_tokens"),
            "expect_verdict": row["expect_verdict"],
            "got_verdict": result.get("verdict"),
            "got_core": result.get("core"),
            "mark": "hit" if ok else "miss",
        })

    from verantyx.sense_split import report
    stats = report(senses, aliases)
    out = {
        "bank_path": str(BANK),
        "bank_existed_before_first_wrapper_resolve": True,
        "bank_mtime": int(bank_stat.st_mtime),
        "resolve_calls": _RESOLVE_CALLS,
        "fork": {"name": fork["fork"], "pass": fork["pass"]},
        "sidecar": stats,
        "surfaces": {
            "n": len(bank["surfaces"]),
            "hits": hits,
            "misses": misses,
            "abstentions": abstentions,
            "unambiguous_resolved": "%d/%d" % (unamb_ok, unamb_n),
            "score": "%d/%d" % (hits, len(bank["surfaces"])),
            "rows": rows,
        },
        "context_cases": {
            "n": len(ctx_rows),
            "hits": ctx_hits,
            "misses": ctx_misses,
            "rows": ctx_rows,
        },
    }
    print(json.dumps(out, ensure_ascii=False, indent=1), flush=True)
    return 0 if misses == 0 and ctx_misses == 0 and fork["pass"] else 1


def _named_item(it):
    return {"core": it.get("core"), "domain_tag": it.get("domain_tag") or ""}


if __name__ == "__main__":
    raise SystemExit(main())
