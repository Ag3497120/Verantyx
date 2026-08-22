"""Commonsense baseline — three existing routes, no import (W3b).

Protocol (SPEC_2026-08-14_eight_gaps W3b). The bank
`tools/commonsense_bank_2026-08-14.json` is preregistered BEFORE the
first federation ask, the first shelf-lead lookup, or the first
`meaning_descent.descend` call. Fifty 「氷は冷たい」-class items
(物性20 / 生活常識15 / 因果常識15), every gold `expected=yes`.
The hypothesis under test: these are facts nobody writes down.

Routes (read, not extended):
    連邦      published store, the ask path (`Vera.ask` / `stacked.ask`)
    浅層棚    jawiki lead via defs sidecar + one-hop aliases
              (CrossStore holds no lead text; see meaning_descent.py)
    意味降下  `verantyx.meaning_descent.descend` on the subject

Outcomes, per item × route:
    ANSWERED_CORRECT  an axis token (or the property) is in the
                      route's answer / definition
    TYPED_REFUSAL     typed unknown / abstention / not-attested
    WRONG             an asserting answer that does not contain the
                      axis and says something else
誤答 is the enemy. Refusal is honest. No ConceptNet. No LLM.

## Measured — preregistered bank 2026-08-14, 50 questions

    bank predates first route            yes
    n                                    50   物性20 / 生活常識15 / 因果常識15
    no ConceptNet / no LLM

    route × outcome
                    ANSWERED_CORRECT  TYPED_REFUSAL  WRONG
        連邦                      11             37      2
        浅層棚                     11              7     32
        意味降下                    10              6     34

    per-category
        連邦      物性  5/13/2   生活  4/11/0   因果  2/13/0
        浅層棚     物性  3/4/13   生活  7/1/7    因果  1/2/12
        意味降下    物性  3/4/13   生活  6/0/9    因果  1/2/12
        (correct / refusal / wrong)

    連邦 ran: export_sqlite.vera + Vera.ask on published vera.db
              (same door as mcp vera_ask). 89k-core sovereign.
    浅層棚 ran: defs sidecar + aliases via lookup_def.
              jawiki_shallow CrossStore (912MB) not loaded — it
              holds no lead TEXT (meaning_descent.py). Lead
              lookup is the defs sidecar. Shelf file present.
    意味降下 ran: descend() ; lattice writer∪defs 2–5
              555,851 words, 815,082 slots

    defs                                 1,419,406 titles
    aliases                              941,604
    wall_seconds                         9.1
    route_calls                          150

    The hypothesis (nobody writes these down) is the number:
    federation mostly refuses (37/50); the two WRONGs are
    塩→クロイツ/タウブ and レモン→炭酸ガス. Shelf and descent
    mostly return a definition that asserts something else
    (32 and 34 WRONG). ANSWERED_CORRECT is often a short
    axis token inside a taxonomic lead (針/尖, 紙/薄, 靴/履)
    or a facet substring (火/熱, 鉄/重), not a written
    「氷は冷たい」.

    Verbatim (5; every federation WRONG, then shelf WRONG)
        塩はしょっぱいですか  連邦  SEEDED  WRONG
            塩 クロイツ タウブ 代表 代表例
        レモンは酸っぱいですか  連邦  ATTESTED  WRONG
            レモン 酸 炭酸ガス レモンは、炭酸ガス（がいしょくほう）である。
        氷は冷たいですか  浅層棚  SHELF_LEAD  WRONG
            なお、天文学では宇宙空間に存在する一酸化炭素や二酸化炭素、
            メタンなど水以外の低分子物質の固体をも氷…と呼ぶこともある。
        火は熱いですか  浅層棚  SHELF_LEAD  WRONG
            火（ひ）とは、化学的には物質の燃焼（物質の急激な酸化）に
            伴って発生するプラズマ、あるいは燃焼の一部、と考えられて
            いる現象である。
        塩はしょっぱいですか  浅層棚  SHELF_LEAD  WRONG
            塩（しお、）は、塩化ナトリウムを主な成分とし、海水の乾燥・
            岩塩の採掘によって生産される物質。

## Measured — federation repair 2026-08-14, same bank, federation route only

    bank predates first route            yes (untouched)
    n                                    50
    no ConceptNet / no LLM
    ingest rule                          ja_chosen_core: named-compound
                                         last-run / first-run prefix /
                                         kata-sense paren → hole
    store repair                         rule-derived provenance filter
                                         on federation.pkl + re-export
                                         vera.db; holes not refilled
    ask rule                             yes_no with no content-run
                                         property → NOT_ATTESTED
                                         (does not dump the census)

    route × outcome  (連邦 only; 浅層棚 / 意味降下 not re-run)
                    ANSWERED_CORRECT  TYPED_REFUSAL  WRONG
        連邦                       9             41      0

    per-category
        連邦      物性  5/15/0   生活  2/13/0   因果  2/13/0
        (correct / refusal / wrong)

    pass line federation WRONG = 0          yes
    the two prior WRONGs
        塩はしょっぱいですか   NOT_ATTESTED  TYPED_REFUSAL
        レモンは酸っぱいですか NOT_ATTESTED  TYPED_REFUSAL
    がいしょくほう / クロイツ / タウブ / 炭酸ガス  gone from the answers

    known-good still answering (spot)
        火は熱いですか  ATTESTED  火 熱
        鉄は重いですか  ATTESTED  鉄 重
        正当防衛とは    SEEDED    正当防衛 行為 防衛 成立 他人
        時効とは        SEEDED    時効 援用 中断 成立 完成
    針 / 紙 / 靴 were prior corrects whose axis hit sat on a stolen-run
    claim (針・棘, タイムズ紙, 靴・履物). The hole is a refusal.

    repair ledger  federation_repair_ledger_2026-08-14.jsonl
        slots removed                    103599
        unique (core, facet) dropped     98987
        by pattern
            first_run_compound_prefix         43655
            content_paren_before_ha           30714
            core_changed                      15244
            topic_name_compound_last_run       8995
            topic_particle_retargeted          4716
            no_identifiable_topic               275
        vera.db facets  1472829 → 1369230
"""
from __future__ import annotations

import gc
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BANK = Path(__file__).resolve().parent / "commonsense_bank_2026-08-14.json"
ROOT = Path.home() / "Projects" / "vera-corpus" / "build"
VERA_DB = ROOT / "vera.db"
DEFS = ROOT / "jawiki_defs.json"
ALIASES = ROOT / "jawiki_aliases.json"
SHELF = ROOT / "jawiki_shallow.json"
WRITER = ROOT / "writer.json"

CATEGORIES = ("物性", "生活常識", "因果常識")
ROUTES = ("連邦", "浅層棚", "意味降下")
OUTCOMES = ("ANSWERED_CORRECT", "TYPED_REFUSAL", "WRONG")

_ROUTE_CALLS = 0
_FIRST_ROUTE_AT = 0.0
_FED_NOTE = ""
_SHELF_NOTE = ""
_DESCENT_NOTE = ""


def _require_bank() -> Dict[str, Any]:
    if not BANK.is_file():
        print("REFUSE: bank is not on disk; no route is called.", file=sys.stderr)
        raise SystemExit(2)
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    items = bank.get("items") or []
    if len(items) != 50:
        print("REFUSE: bank size %d, not 50." % len(items), file=sys.stderr)
        raise SystemExit(2)
    by = Counter(i.get("category") for i in items)
    if by.get("物性") != 20 or by.get("生活常識") != 15 or by.get("因果常識") != 15:
        print("REFUSE: category split %s, not 20/15/15." % dict(by),
              file=sys.stderr)
        raise SystemExit(2)
    for i, row in enumerate(items, 1):
        for k in ("subject", "property", "question", "expected", "axis_tokens"):
            if k not in row:
                print("REFUSE: item %d missing %s." % (i, k), file=sys.stderr)
                raise SystemExit(2)
        if row["expected"] != "yes":
            print("REFUSE: item %d expected %r, not yes." % (i, row["expected"]),
                  file=sys.stderr)
            raise SystemExit(2)
    return bank


def _mark_route_call() -> None:
    global _ROUTE_CALLS, _FIRST_ROUTE_AT
    if _ROUTE_CALLS == 0:
        _FIRST_ROUTE_AT = time.time()
    _ROUTE_CALLS += 1


def axis_tokens_of(item: Dict[str, Any]) -> List[str]:
    toks = [t for t in (item.get("axis_tokens") or []) if t]
    prop = (item.get("property") or "").strip()
    if prop and prop not in toks:
        toks.append(prop)
    return toks


def axis_hit(text: str, tokens: Sequence[str]) -> Optional[str]:
    blob = text or ""
    for t in tokens:
        if t and t in blob:
            return t
    return None


def is_typed_refusal(verdict: str) -> bool:
    v = verdict or ""
    if v.startswith("UNKNOWN"):
        return True
    if v.startswith("ABSTAIN"):
        return True
    if v.startswith("UNGROUNDED"):
        return True
    return v in {
        "NOT_ATTESTED",
        "UNKNOWN_NO_LEAD",
        "AMBIGUOUS_SENSE",
        "INSUFFICIENT_PROFILE",
        "TYPO_CANDIDATE",
        "UNKNOWN_NO_CANDIDATE",
    }


def is_asserting(verdict: str) -> bool:
    v = verdict or ""
    if v.startswith("ANSWER"):
        return True
    return v in {
        "SEEDED",
        "ATTESTED",
        "UNITS",
        "CONTAINMENT",
        "EXPLAINED_BY_UNIT_DEFS",
        "EXPLAINED_BY_UNITS",
        "KIN_NEIGHBOURHOOD",
        "SHELF_LEAD",
        "MAJORITY",
    }


def classify(verdict: str, text: str, tokens: Sequence[str]) -> str:
    """Refusal first, then axis hit, then asserting-without-axis = WRONG."""
    if is_typed_refusal(verdict):
        return "TYPED_REFUSAL"
    hit = axis_hit(text, tokens)
    if hit:
        return "ANSWERED_CORRECT"
    if is_asserting(verdict) and (text or "").strip():
        return "WRONG"
    return "TYPED_REFUSAL"


def ask_blob(out: Dict[str, Any]) -> str:
    parts: List[str] = []
    if out.get("text"):
        parts.append(str(out["text"]))
    written = out.get("written") or {}
    if isinstance(written, dict):
        for s in written.get("sentences") or []:
            if isinstance(s, dict) and s.get("text"):
                parts.append(str(s["text"]))
            elif isinstance(s, str):
                parts.append(s)
    attested = out.get("attested") or {}
    if isinstance(attested, dict):
        for cond, facets in attested.items():
            parts.append(str(cond))
            if isinstance(facets, list):
                parts.extend(str(f) for f in facets)
    return " ".join(p for p in parts if p)


def clip(text: str, n: int = 180) -> str:
    t = (text or "").replace("\n", " ")
    return t if len(t) <= n else t[: n - 1] + "…"


# --- Route 1: federation ask -------------------------------------------------

def load_federation() -> Tuple[Any, str]:
    """Published store, same door measure tools and mcp vera_ask use.

    Prefer `export_sqlite.vera` + `Vera.ask` (mcp `_vera().ask`).
    If that path cannot be built, fall back to the ja sovereign from
    `export_sqlite.load` + `stacked.ask` — the function `Vera.ask`
    calls for the answer itself. Honesty over completeness.
    """
    if not VERA_DB.is_file():
        return None, "vera.db missing at %s" % VERA_DB
    try:
        from verantyx.export_sqlite import vera as load_published

        v = load_published(VERA_DB)
        if not getattr(v, "ask", None):
            return None, "published Vera has no ask"
        return ("vera", v), "export_sqlite.vera + Vera.ask (published vera.db, same as mcp vera_ask)"
    except Exception as e:
        try:
            from verantyx.export_sqlite import load as load_stores
            from verantyx.stacked import ask as stacked_ask  # noqa: F401

            stores = load_stores(VERA_DB)
            ja = stores.get("ja")
            if ja is None:
                return None, "published store has no ja sovereign: %s" % e
            return ("stacked", ja), (
                "fallback stacked.ask on published ja store "
                "(full Vera.ask failed: %s)" % e
            )
        except Exception as e2:
            return None, "federation load failed: %s / %s" % (e, e2)


def ask_federation(handle: Tuple[str, Any], question: str) -> Dict[str, Any]:
    kind, obj = handle
    _mark_route_call()
    if kind == "vera":
        return obj.ask(question)
    from verantyx.stacked import ask as stacked_ask

    return stacked_ask(obj, question)


def measure_federation(items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], str]:
    loaded, note = load_federation()
    if loaded is None:
        return [], note
    rows = []
    for item in items:
        t0 = time.time()
        try:
            out = ask_federation(loaded, item["question"])
        except Exception as e:
            out = {"verdict": "UNKNOWN_ROUTE_ERROR", "text": "", "note": str(e)}
        text = ask_blob(out)
        verdict = str(out.get("verdict") or "")
        tokens = axis_tokens_of(item)
        rows.append({
            "id": item["id"],
            "category": item["category"],
            "subject": item["subject"],
            "property": item["property"],
            "question": item["question"],
            "route": "連邦",
            "verdict": verdict,
            "text": text,
            "hit": axis_hit(text, tokens),
            "outcome": classify(verdict, text, tokens),
            "ms": round((time.time() - t0) * 1000, 3),
        })
    del loaded
    gc.collect()
    return rows, note


# --- Route 2: shallow-shelf lead lookup --------------------------------------

def measure_shelf(items: List[Dict[str, Any]],
                  defs: Dict[str, str],
                  aliases: Dict[str, str]) -> Tuple[List[Dict[str, Any]], str]:
    from verantyx.meaning_descent import lookup_def

    note = (
        "defs sidecar + aliases via meaning_descent.lookup_def; "
        "jawiki_shallow CrossStore not loaded (912MB, and it holds no "
        "lead TEXT — meaning_descent.py). Lookup = does the subject's "
        "lead contain the property."
    )
    if SHELF.is_file():
        note += " shelf file present (%d bytes)." % SHELF.stat().st_size
    else:
        note += " shelf file absent."
    rows = []
    for item in items:
        t0 = time.time()
        _mark_route_call()
        lead, source = lookup_def(item["subject"], defs, aliases)
        if lead is None:
            verdict, text = "UNKNOWN_NO_LEAD", ""
        else:
            verdict, text = "SHELF_LEAD", lead
        tokens = axis_tokens_of(item)
        rows.append({
            "id": item["id"],
            "category": item["category"],
            "subject": item["subject"],
            "property": item["property"],
            "question": item["question"],
            "route": "浅層棚",
            "verdict": verdict,
            "text": text,
            "source": source,
            "hit": axis_hit(text, tokens),
            "outcome": classify(verdict, text, tokens),
            "ms": round((time.time() - t0) * 1000, 3),
        })
    return rows, note


# --- Route 3: meaning descent ------------------------------------------------

def measure_descent(items: List[Dict[str, Any]],
                    defs: Dict[str, str],
                    aliases: Dict[str, str]) -> Tuple[List[Dict[str, Any]], str]:
    from verantyx.lattice import build
    from verantyx.meaning_descent import descend
    from verantyx.writer import Writer

    words = {item["subject"] for item in items}
    note = "descend() on subject; lattice = "
    if WRITER.is_file():
        vocab = Writer.load(WRITER).vocab
        words |= set(vocab.attested)
        note += "writer vocab ∪ bank subjects"
    else:
        note += "bank subjects only (writer.json missing)"
    # Same increment W2b used so a unit that has a sentence can split.
    extra = 0
    for title in defs:
        if 2 <= len(title) <= 5:
            words.add(title)
            extra += 1
    note += " ∪ def titles 2–5 (%d titles added)" % extra
    lat = build(words)
    note += "; %s" % json.dumps(lat.report(), ensure_ascii=False)

    rows = []
    for item in items:
        t0 = time.time()
        _mark_route_call()
        got = descend(item["subject"], lattice=lat, defs=defs, aliases=aliases)
        text = str(got.get("text") or "")
        verdict = str(got.get("verdict") or "")
        tokens = axis_tokens_of(item)
        rows.append({
            "id": item["id"],
            "category": item["category"],
            "subject": item["subject"],
            "property": item["property"],
            "question": item["question"],
            "route": "意味降下",
            "verdict": verdict,
            "text": text,
            "grounding": got.get("grounding"),
            "hit": axis_hit(text, tokens),
            "outcome": classify(verdict, text, tokens),
            "ms": round((time.time() - t0) * 1000, 3),
        })
    return rows, note


def table(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    grid = {r: {o: 0 for o in OUTCOMES} for r in ROUTES}
    by_cat = {
        r: {c: {o: 0 for o in OUTCOMES} for c in CATEGORIES}
        for r in ROUTES
    }
    for row in rows:
        grid[row["route"]][row["outcome"]] += 1
        by_cat[row["route"]][row["category"]][row["outcome"]] += 1
    return {"route_x_outcome": grid, "per_category": by_cat}


def pick_examples(rows: List[Dict[str, Any]], n: int = 5) -> List[Dict[str, Any]]:
    """Every WRONG first (up to n), then fill from other outcomes."""
    wrongs = [r for r in rows if r["outcome"] == "WRONG"]
    rest = [r for r in rows if r["outcome"] != "WRONG"]
    chosen = wrongs[:n]
    i = 0
    while len(chosen) < n and i < len(rest):
        chosen.append(rest[i])
        i += 1
    out = []
    for r in chosen:
        out.append({
            "id": r["id"],
            "route": r["route"],
            "outcome": r["outcome"],
            "verdict": r["verdict"],
            "question": r["question"],
            "subject": r["subject"],
            "property": r["property"],
            "hit": r.get("hit"),
            "text": clip(r.get("text") or "", 240),
        })
    return out


def render(report: Dict[str, Any]) -> str:
    g = report["route_x_outcome"]
    lines = [
        "route × outcome (n=50 per route)",
        "%-8s %18s %16s %8s" % ("", *OUTCOMES),
    ]
    for r in ROUTES:
        row = g.get(r) or {}
        lines.append("%-8s %18d %16d %8d" % (
            r,
            row.get("ANSWERED_CORRECT", 0),
            row.get("TYPED_REFUSAL", 0),
            row.get("WRONG", 0),
        ))
    lines.append("")
    lines.append("per-category")
    for r in ROUTES:
        lines.append("  %s" % r)
        for c in CATEGORIES:
            cell = report["per_category"][r][c]
            lines.append("    %-8s  correct %2d  refusal %2d  wrong %2d" % (
                c,
                cell["ANSWERED_CORRECT"],
                cell["TYPED_REFUSAL"],
                cell["WRONG"],
            ))
    lines.append("")
    lines.append("examples (WRONG first, up to 5)")
    for ex in report["examples"]:
        lines.append("  [%s] %s  %s  %s / %s" % (
            ex["outcome"], ex["route"], ex["question"],
            ex["verdict"], ex.get("hit"),
        ))
        lines.append("    %s" % ex["text"])
    return "\n".join(lines)


def main() -> int:
    global _FED_NOTE, _SHELF_NOTE, _DESCENT_NOTE
    t_all = time.time()
    bank = _require_bank()
    items = bank["items"]
    bank_mtime = BANK.stat().st_mtime
    print("bank: %s  n=%d  mtime=%.0f" % (BANK, len(items), bank_mtime),
          flush=True)

    fed_rows, _FED_NOTE = measure_federation(items)
    print("連邦: %s  rows=%d" % (_FED_NOTE, len(fed_rows)), flush=True)

    if not DEFS.is_file():
        print("REFUSE: defs sidecar missing: %s" % DEFS, file=sys.stderr)
        defs, aliases = {}, {}
        shelf_rows, _SHELF_NOTE = [], "defs sidecar missing"
        desc_rows, _DESCENT_NOTE = [], "defs sidecar missing"
    else:
        t0 = time.time()
        defs = json.loads(DEFS.read_text(encoding="utf-8"))
        aliases = (json.loads(ALIASES.read_text(encoding="utf-8"))
                   if ALIASES.is_file() else {})
        print("defs: %d  aliases: %d  load %.1fs" % (
            len(defs), len(aliases), time.time() - t0), flush=True)
        shelf_rows, _SHELF_NOTE = measure_shelf(items, defs, aliases)
        print("浅層棚: %s" % _SHELF_NOTE, flush=True)
        desc_rows, _DESCENT_NOTE = measure_descent(items, defs, aliases)
        print("意味降下: %s" % _DESCENT_NOTE, flush=True)

    rows = fed_rows + shelf_rows + desc_rows
    tallies = table(rows)
    examples = pick_examples(rows)
    wrongs = [r for r in rows if r["outcome"] == "WRONG"]
    report = {
        "bank": str(BANK),
        "bank_registered": bank.get("registered"),
        "n": len(items),
        "split": {"物性": 20, "生活常識": 15, "因果常識": 15},
        "bank_predates_first_route": (
            _FIRST_ROUTE_AT == 0.0 or bank_mtime < _FIRST_ROUTE_AT
        ),
        "route_notes": {
            "連邦": _FED_NOTE,
            "浅層棚": _SHELF_NOTE,
            "意味降下": _DESCENT_NOTE,
        },
        "route_ran": {
            "連邦": bool(fed_rows),
            "浅層棚": bool(shelf_rows),
            "意味降下": bool(desc_rows),
        },
        "route_x_outcome": tallies["route_x_outcome"],
        "per_category": tallies["per_category"],
        "wrong_count": len(wrongs),
        "examples": examples,
        "timing": {
            "wall_seconds": round(time.time() - t_all, 1),
            "route_calls": _ROUTE_CALLS,
        },
        "rows": rows,
    }
    print(render(report), flush=True)
    print(json.dumps({k: v for k, v in report.items() if k != "rows"},
                     ensure_ascii=False, indent=1), flush=True)
    # Full rows last so the summary is readable above.
    print(json.dumps({"rows": [
        {k: r[k] for k in (
            "id", "route", "category", "question", "verdict",
            "outcome", "hit", "text",
        )}
        for r in rows
    ]}, ensure_ascii=False, indent=1), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
