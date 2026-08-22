"""Connective-licensed rendering of the 30-pair structural-diff bank (W3a).

Protocol (SPEC_2026-08-14_eight_gaps W3a). The axis file
tools/render_axes_2026-08-14.json is written BEFORE the first
render_diff call. Diff inputs reuse the accepted structural_diff
wiring (senses + jawiki-lead provenance) from
measure_structural_diff.py. The bank file is the same 30 pairs.

Machine checks (pass lines):
    (a) every connective in every output carries a license — 100%
    (b) zero negation assembly outside 「」 quotes
        (でない / ではない / られない / しない)
    (c) 「しかし」 count with licenses listed (0 is honest)

Eyeball: three verbatim renders scored on the five preregistered axes.

## Measured — 30-pair bank, senses+provenance, seed 20260814

    axes     tools/render_axes_2026-08-14.json   (written before first render)
    bank     tools/diff_bank_2026-08-14.json     n=30
    fork     CONNECTIVE_EDGE_LICENSE             pass
    subjects 1,419,406   senses 122,988   extractor fugashi
    lattice  527,175 words, 787,333 slots
    render_calls  36   (6 regression + 30 bank)
    wall_seconds  9.6

    bank split
        RENDER                   23
        INSUFFICIENT_PROFILE      7
        AMBIGUOUS_SENSE           0

    machine pass lines
        (a) every connective licensed    697 / 697   PASS
        (b) assembled negation           0           PASS
        (c) しかし count + licenses      0  []       PASS (honest zero)

    connective counts
        そして  611   within-bucket
        また     65   shared-lead-in
        一方     21   bucket-transition
        しかし    0   observed-negation

    Eyeball (5 preregistered axes, 1/0)
        リンゴ/電気  RENDER                 5 / 5
        米/光        INSUFFICIENT_PROFILE   5 / 5
            INSUFFICIENT_PROFILE。米と光。Aの被覆は述語0・面5。Bの被覆は述語0・面2。
        水/音        RENDER (一方)          5 / 5

## Measured — selection fix, same bank, same axes, 2026-08-14

    axes     tools/render_axes_2026-08-14.json   (untouched; preregistered)
    bank     tools/diff_bank_2026-08-14.json     n=30
    fork     CONNECTIVE_EDGE_LICENSE             pass
    subjects 1,419,406   senses 122,988   extractor fugashi
    lattice  527,175 words, 787,333 slots
    render_calls  39   (9 regression + 30 bank)
    wall_seconds  9.3

    bank split
        RENDER                   23
        INSUFFICIENT_PROFILE      7
        AMBIGUOUS_SENSE           0

    machine pass lines (original three, still)
        (a) every connective licensed    243 / 243   PASS
        (b) assembled negation           0           PASS
        (c) しかし count + licenses      0  []       PASS (honest zero)

    machine pass lines (selection)
        (d) duplicate tokens spoken      0           PASS
        (e) max bucket enum              8  (<= 8 + tail)  PASS
        (f) junk tokens spoken           0           PASS

    connective counts
        そして  199   within-bucket
        また     23   shared-lead-in
        一方     21   bucket-transition
        しかし    0   observed-negation

    Eyeball (same 3 pairs)
        リンゴ/電気  RENDER                 5 / 5
        米/光        INSUFFICIENT_PROFILE   5 / 5
        水/音        RENDER (一方)          5 / 5
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from measure_structural_diff import (  # noqa: E402
    ALIASES,
    BANK,
    MIN_PREDS,
    SHELF,
    load_shelf,
)
from verantyx import connective_render as cr  # noqa: E402
from verantyx.connective_render import (  # noqa: E402
    BUCKET_LIMIT,
    CLOSED_CONNECTIVES,
    CONNECTIVE_IPPOU,
    CONNECTIVE_SHIKASHI,
    is_junk_token,
    render_diff,
    regression,
)
from verantyx.lattice import build  # noqa: E402
from verantyx.predicate_profile import OUT, load  # noqa: E402
from verantyx.sense_split import OUT as SENSES_OUT, load as load_senses  # noqa: E402
from verantyx.structural_diff import diff  # noqa: E402

AXES = Path(__file__).resolve().parent / "render_axes_2026-08-14.json"
ASSEMBLED_NEG = ("ではない", "でない", "られない", "しない")
_QUOTED = re.compile(r"「[^」]*」")

_RENDER_CALLS = 0
_ORIG_RENDER = render_diff


def _checked_render(diff_result):
    global _RENDER_CALLS
    if not AXES.is_file():
        raise SystemExit("axes file missing before first render: %s" % AXES)
    _RENDER_CALLS += 1
    return _ORIG_RENDER(diff_result)


cr.render_diff = _checked_render


def _outside_quotes(text: str) -> str:
    return _QUOTED.sub("", text or "")


def connectives_in_text(text: str) -> list:
    """Closed connectives outside 「」 quotes, longest-first, in order."""
    body = _outside_quotes(text)
    found = []
    i = 0
    words = CLOSED_CONNECTIVES  # しかし, そして, 一方, また
    n = len(body)
    while i < n:
        hit = None
        for w in words:
            if body.startswith(w, i):
                hit = w
                break
        if hit:
            found.append(hit)
            i += len(hit)
        else:
            i += 1
    return found


def assembled_negations(text: str) -> list:
    body = _outside_quotes(text)
    return [p for p in ASSEMBLED_NEG if p in body]


def quoted_tokens(text: str) -> list:
    return _QUOTED.findall(text or "")


def bucket_duplicate_count(rendered: dict) -> int:
    n = 0
    items = rendered.get("items") or {}
    for side in ("only_a", "only_b", "shared"):
        toks = [it.get("token") for it in items.get(side) or []]
        n += len(toks) - len(set(toks))
    return n


def bucket_enum_lengths(rendered: dict) -> list:
    items = rendered.get("items") or {}
    return [len(items.get(side) or []) for side in ("only_a", "only_b", "shared")]


def junk_spoken(text: str) -> list:
    hits = []
    for raw in quoted_tokens(text):
        tok = raw[1:-1] if raw.startswith("「") and raw.endswith("」") else raw
        if is_junk_token(tok):
            hits.append(tok)
    return hits


def score_axes(row: dict, axes: list) -> dict:
    """Deterministic checklist against the preregistered axes.

    This is the machine half of the eyeball. The printed verbatim
    text is what a designer reads; the 0/1 here is the same five
    questions applied without fluency judgement.
    """
    text = row.get("text") or ""
    conns = row.get("connectives") or []
    verdict = row.get("verdict") or ""
    cov = row.get("coverage") or {"a": {}, "b": {}}
    out = {}
    for ax in axes:
        aid = ax["id"]
        if aid == "subject_named":
            out[aid] = int(bool(row.get("a")) and bool(row.get("b"))
                           and row["a"] in text and row["b"] in text)
        elif aid == "buckets_distinguishable":
            if verdict in ("INSUFFICIENT_PROFILE", "AMBIGUOUS_SENSE"):
                out[aid] = int(verdict in text)
            else:
                has_excl = ("実測あり" in text and "実測なし" in text)
                has_shared_shape = text.count("実測あり") >= 2
                out[aid] = int(has_excl or has_shared_shape or verdict in text)
        elif aid == "no_negation_assembled":
            out[aid] = int(not assembled_negations(text))
        elif aid == "coverage_spoken_on_abstention":
            if verdict in ("INSUFFICIENT_PROFILE", "AMBIGUOUS_SENSE"):
                nums = [
                    str(cov.get("a", {}).get("predicates", "")),
                    str(cov.get("a", {}).get("facets", "")),
                    str(cov.get("b", {}).get("predicates", "")),
                    str(cov.get("b", {}).get("facets", "")),
                ]
                out[aid] = int(all(n != "" and n in text for n in nums)
                               and "述語" in text and "面" in text)
            else:
                out[aid] = 1
        elif aid == "connectives_licensed":
            in_text = connectives_in_text(text)
            recorded = [c.get("connective") for c in conns]
            licensed = all(c.get("license") for c in conns)
            out[aid] = int(in_text == recorded and licensed)
        else:
            out[aid] = 0
    return out


def main() -> None:
    t0 = time.time()
    if not AXES.is_file():
        raise SystemExit("preregistered axes missing: %s" % AXES)
    if not BANK.is_file():
        raise SystemExit("preregistered bank missing: %s" % BANK)
    axes_stat = AXES.stat()
    bank_stat = BANK.stat()
    axes_doc = json.loads(AXES.read_text(encoding="utf-8"))
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    pairs = bank["pairs"]
    print("axes", AXES, "n", len(axes_doc["axes"]),
          "mtime", int(axes_stat.st_mtime),
          "render_calls_so_far", _RENDER_CALLS, flush=True)
    print("bank", BANK, "n", len(pairs), "mtime", int(bank_stat.st_mtime),
          flush=True)
    if _RENDER_CALLS != 0:
        raise SystemExit("render ran before axes were checked")

    print("regression…", flush=True)
    fork = regression()
    print(json.dumps({"fork": fork["fork"], "pass": fork["pass"],
                      "result": fork["result"]}, ensure_ascii=False),
          flush=True)
    if not fork["pass"]:
        raise SystemExit("CONNECTIVE_EDGE_LICENSE failed")

    print("loading profiles…", flush=True)
    extractor, profiles = load(OUT)
    print("profiles", len(profiles), "extractor", extractor,
          "%.1fs" % (time.time() - t0), flush=True)

    print("loading aliases…", flush=True)
    aliases = json.loads(ALIASES.read_text(encoding="utf-8"))
    print("aliases", len(aliases), flush=True)

    print("loading senses…", flush=True)
    if not SENSES_OUT.is_file():
        raise SystemExit("sense sidecar missing: %s" % SENSES_OUT)
    senses = load_senses(SENSES_OUT)
    print("senses", len(senses), flush=True)

    bank_subjects = []
    for p in pairs:
        bank_subjects.append(p["a"])
        bank_subjects.append(p["b"])
        bank_subjects.append(aliases.get(p["a"], p["a"]))
        bank_subjects.append(aliases.get(p["b"], p["b"]))
    bank_subjects = sorted(set(bank_subjects))

    print("loading shelf…", flush=True)
    shelf = load_shelf(bank_subjects)
    print("shelf cores", len(shelf.crosses), "prov", len(shelf.provenance),
          "%.1fs" % (time.time() - t0), flush=True)

    print("building lattice…", flush=True)
    lat = build(profiles)
    print("lattice", json.dumps(lat.report()),
          "%.1fs" % (time.time() - t0), flush=True)

    rows = []
    licensed_ok = 0
    licensed_total = 0
    assembly_hits = 0
    shikashi_hits = []
    n_render = 0
    n_insufficient = 0
    n_ambiguous = 0
    n_ippou = 0
    n_mata = 0
    n_soshite = 0
    dup_total = 0
    max_enum = 0
    junk_hits = []

    for pair in pairs:
        result = diff(
            pair["a"], pair["b"], profiles=profiles, aliases=aliases,
            lattice=lat, shelf=shelf, k=8, min_profile=MIN_PREDS,
            senses=senses,
        )
        rendered = _checked_render(result)
        in_text = connectives_in_text(rendered["text"])
        recorded = [c.get("connective") for c in rendered["connectives"]]
        licensed = all(bool(c.get("license")) for c in rendered["connectives"])
        match = in_text == recorded and licensed
        n_conn = len(in_text)
        licensed_total += n_conn
        if match:
            licensed_ok += n_conn
        elif n_conn == 0 and not recorded:
            pass
        # A mismatch still counts the text connectives as unchecked.
        assembled = assembled_negations(rendered["text"])
        if assembled:
            assembly_hits += 1
        for c in rendered["connectives"]:
            if c.get("connective") == CONNECTIVE_SHIKASHI:
                shikashi_hits.append({
                    "a": pair["a"], "b": pair["b"],
                    "license": c,
                })
            if c.get("connective") == CONNECTIVE_IPPOU:
                n_ippou += 1
            if c.get("connective") == "また":
                n_mata += 1
            if c.get("connective") == "そして":
                n_soshite += 1
        if rendered["verdict"] == "RENDER":
            n_render += 1
        elif rendered["verdict"] == "INSUFFICIENT_PROFILE":
            n_insufficient += 1
        elif rendered["verdict"] == "AMBIGUOUS_SENSE":
            n_ambiguous += 1
        dups = bucket_duplicate_count(rendered)
        dup_total += dups
        for n_enum in bucket_enum_lengths(rendered):
            if n_enum > max_enum:
                max_enum = n_enum
        junk = junk_spoken(rendered["text"])
        if junk:
            junk_hits.append({"a": pair["a"], "b": pair["b"], "tokens": junk})
        rows.append({
            "a": pair["a"],
            "b": pair["b"],
            "expected_axis": pair.get("expected_axis"),
            "source_verdict": result.get("verdict"),
            "verdict": rendered["verdict"],
            "coverage": rendered["coverage"],
            "text": rendered["text"],
            "connectives": rendered["connectives"],
            "items": rendered.get("items"),
            "tail": rendered.get("tail"),
            "license_match": match,
            "assembled_neg": assembled,
            "n_connectives": n_conn,
            "duplicate_tokens": dups,
            "junk_spoken": junk,
        })

    license_rate = (licensed_ok / licensed_total) if licensed_total else 1.0
    pass_a = licensed_ok == licensed_total
    pass_b = assembly_hits == 0
    pass_c = True  # count is the report; 0 is honest
    pass_d = dup_total == 0
    pass_e = max_enum <= BUCKET_LIMIT
    pass_f = not junk_hits

    def _pick(a, b):
        for r in rows:
            if r["a"] == a and r["b"] == b:
                return r
        return None

    hit_row = _pick("リンゴ", "電気") or rows[0]
    abs_row = _pick("米", "光")
    if abs_row is None:
        for r in rows:
            if r["verdict"] in ("INSUFFICIENT_PROFILE", "AMBIGUOUS_SENSE"):
                abs_row = r
                break
    ippou_row = _pick("水", "音")
    if ippou_row is None:
        for r in rows:
            if any(c.get("connective") == CONNECTIVE_IPPOU
                   for c in r["connectives"]):
                ippou_row = r
                break
    eyeball = []
    for slot, row in (
        ("hit pair (リンゴ/電気)", hit_row),
        ("abstention pair", abs_row),
        ("pair with 一方", ippou_row),
    ):
        if row is None:
            eyeball.append({"slot": slot, "missing": True})
            continue
        eyeball.append({
            "slot": slot,
            "a": row["a"],
            "b": row["b"],
            "verdict": row["verdict"],
            "text": row["text"],
            "connectives": row["connectives"],
            "coverage": row["coverage"],
            "axis_scores": score_axes(row, axes_doc["axes"]),
        })

    out = {
        "axes_path": str(AXES),
        "axes_existed_before_first_wrapper_render": True,
        "axes_mtime": int(axes_stat.st_mtime),
        "bank_path": str(BANK),
        "bank_mtime": int(bank_stat.st_mtime),
        "render_calls": _RENDER_CALLS,
        "extractor": extractor,
        "subjects": len(profiles),
        "senses": len(senses),
        "fork": {"name": fork["fork"], "pass": fork["pass"]},
        "bank": {
            "n": len(pairs),
            "render": n_render,
            "INSUFFICIENT_PROFILE": n_insufficient,
            "AMBIGUOUS_SENSE": n_ambiguous,
        },
        "connective_counts": {
            "そして": n_soshite,
            "また": n_mata,
            "一方": n_ippou,
            "しかし": len(shikashi_hits),
        },
        "machine": {
            "a_license": {
                "ok": licensed_ok,
                "total": licensed_total,
                "rate": round(license_rate, 4),
                "pass": pass_a,
            },
            "b_no_assembled_negation": {
                "hits": assembly_hits,
                "pass": pass_b,
            },
            "c_shikashi": {
                "count": len(shikashi_hits),
                "licenses": shikashi_hits,
                "pass": pass_c,
            },
            "d_duplicate_tokens": {
                "count": dup_total,
                "pass": pass_d,
            },
            "e_max_bucket_enum": {
                "max": max_enum,
                "limit": BUCKET_LIMIT,
                "pass": pass_e,
            },
            "f_junk_spoken": {
                "hits": junk_hits,
                "pass": pass_f,
            },
        },
        "pass_lines": {
            "a_every_connective_licensed": "PASS" if pass_a else "FAIL",
            "b_zero_negation_assembly": "PASS" if pass_b else "FAIL",
            "c_shikashi_count_listed": "PASS",
            "d_duplicate_tokens_zero": "PASS" if pass_d else "FAIL",
            "e_max_enum_le_8": "PASS" if pass_e else "FAIL",
            "f_junk_spoken_zero": "PASS" if pass_f else "FAIL",
        },
        "eyeball": eyeball,
        "rows": rows,
        "seconds": round(time.time() - t0, 1),
    }
    print(json.dumps(out, ensure_ascii=False, indent=1), flush=True)


if __name__ == "__main__":
    main()
