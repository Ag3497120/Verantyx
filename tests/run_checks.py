#!/usr/bin/env python3
"""Everything CI checks, runnable on your own machine the same way.

    python3 tests/run_checks.py

Each check prints what it measured, not just whether it passed. A check that
only says PASS tells you nothing when it later starts lying.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str) -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name:34} {detail}")
    if not ok:
        FAILURES.append(f"{name}: {detail}")


# ---------------------------------------------------------------------------
def the_example_runs() -> None:
    """The README's example is the one thing a reader runs first."""
    r = subprocess.run([sys.executable, "examples/black_coat.py"],
                       cwd=ROOT, capture_output=True, text=True, timeout=600)
    out = r.stdout
    check("example runs", r.returncode == 0,
          f"exit {r.returncode}, {len(out.splitlines())} lines")
    for want in ("UNKNOWN_NO_ADOPTER", "CONTESTED_MEASUREMENT", "ANSWER"):
        check(f"example shows {want}", want in out,
              "present" if want in out else "MISSING — the refusal stopped firing")


# ---------------------------------------------------------------------------
def the_pipeline_still_agrees() -> None:
    """The numbers the README quotes, re-measured."""
    from photoloset import Measures
    from photoloset import garment_marks, garment_pattern, garment_sew

    ms = Measures()
    for spot, value in [("body_length", 112.0), ("chest", 108.0),
                        ("shoulder", 46.0), ("sleeve_length", 63.0)]:
        ms.measured(spot, value, "cm", source="tape", by="ci")

    draft = garment_pattern.draft(ms)
    check("draft answers", draft["verdict"] == "ANSWER", draft["verdict"])
    check("three pieces", len(draft["pieces"]) == 3,
          str([p["name"] for p in draft["pieces"]]))
    check("area 7306.1 cm2", abs(draft["total_area_cm2"] - 7306.1) < 0.05,
          f'{draft["total_area_cm2"]} cm2')
    check("17 formulas printed", len(draft["formulas"]) == 17,
          f'{len(draft["formulas"])}')
    structural = [c for c in draft["seam_checks"] if c.get("structural")]
    check("seam checks self-report", len(structural) == len(draft["seam_checks"]),
          f'{len(structural)}/{len(draft["seam_checks"])} labelled structural')

    marks = garment_marks.apply(draft)
    notches = sum(len(v) for v in marks["notches"].values())
    check("16 notches, 8 paired",
          notches == 16 and len(marks["notch_pairs"]) == 8
          and not marks["notch_unpaired"],
          f'{notches} notches, {len(marks["notch_pairs"])} pairs, '
          f'{len(marks["notch_unpaired"])} unpaired')

    built = garment_sew.build(draft, marks=marks)
    mat = {"verdict": "ANSWER", "fabric": "wool melton", "gsm": 420.0,
           "thickness": 0.18, "stiffness": 20.0}
    # The engine default (16x) does NOT close this garment — that is measured
    # and stated in the README. If it ever starts closing, the README is wrong.
    loose = garment_sew.sew_and_drape(built, mat, iterations=2000)["seam_gap"]
    check("default stitch_k leaves it open", not loose["closed"],
          f'worst {loose["worst"]} cm, {loose["over_tolerance"]}/'
          f'{loose["stitches"]} over tolerance')
    tight = garment_sew.sew_and_drape(built, mat, iterations=2000,
                                      stitch_k=20.0 * 64)["seam_gap"]
    check("64x closes it", tight["closed"] and tight["over_tolerance"] == 0,
          f'worst {tight["worst"]} cm, {tight["over_tolerance"]} over')


# ---------------------------------------------------------------------------
def english_is_complete() -> None:
    """The README claims 0 untranslated across every output path."""
    from photoloset import Ledger, Measures, i18n
    from photoloset import garment_drape, garment_marks, garment_pattern, garment_sew
    from photoloset.garment import PARTS
    from photoloset.garment_measure import SPOTS

    led = Ledger(title="ci")
    led.propose("collar", "shape", "notched lapel", source="frame")
    led.adopt("collar", "shape", "notched lapel", by="ci")
    led.infer("body", "silhouette", "A-line", source="from the hem")
    ms = Measures()
    for spot, value in [("body_length", 112.0), ("chest", 108.0),
                        ("shoulder", 46.0), ("sleeve_length", 63.0)]:
        ms.measured(spot, value, "cm", source="tape", by="ci")
    ms.ratio("waist", 0.62, basis="chest", source="assumed")
    ms.measured("sleeve_length", 46.0, "cm", source="again", by="ci")

    outs = {
        "ledger.spec": led.spec(), "ledger.worklist": led.worklist(),
        "ledger.techpack": led.techpack(), "ledger.timeline": led.timeline(),
        "ledger.state": [led.state(p, a) for p, asp in PARTS.items() for a in asp],
        "measures.sheet": ms.sheet(),
        "measures.state": [ms.state(s) for s in SPOTS],
    }
    ms.entries = [m for m in ms.entries
                  if not (m.spot == "sleeve_length" and m.value == 46.0)]
    draft = garment_pattern.draft(ms)
    marks = garment_marks.apply(draft)
    built = garment_sew.build(draft, marks=marks)
    mat = {"verdict": "ANSWER", "fabric": "f", "gsm": 420.0,
           "thickness": 0.18, "stiffness": 20.0}
    outs["draft"] = draft
    outs["marks"] = marks
    outs["build"] = built
    outs["drape"] = garment_sew.sew_and_drape(built, mat, iterations=200,
                                              stitch_k=20.0 * 64)
    outs["drape.validate"] = garment_drape.validate(40, 40, mat, iterations=100)
    outs["no_material"] = garment_drape.material_from(None, "cupro")
    outs["svg"] = garment_pattern.to_svg(marks)
    outs["draft.refused"] = garment_pattern.draft(Measures())

    total_missing = []
    for name, value in outs.items():
        missing = i18n.missing(i18n.translate(value))
        total_missing += missing
        if missing:
            print(f"        {name}: {missing[:2]}")
    check("0 untranslated", not total_missing,
          f"{len(set(total_missing))} strings across {len(outs)} outputs")

    en = i18n.translate(outs["draft"])
    check("pieces read in English",
          en["pieces"][0]["name"] == "back bodice",
          en["pieces"][0]["name"])

    svg_en = i18n.svg(outs["svg"])
    import re
    strip = lambda d: re.sub(r"\s+", " ", re.sub(r"<text.*?</text>", "", d,
                                                 flags=re.S)).strip()
    geom_same = (strip(outs["svg"]).split("viewBox")[1].split(">")[1:]
                 == strip(svg_en).split("viewBox")[1].split(">")[1:])
    check("SVG geometry untouched", geom_same,
          "every path identical apart from the canvas height")


# ---------------------------------------------------------------------------
def the_mcp_server_answers() -> None:
    """Every tool, over the wire — not by import.

    Importing proves the function exists. It does not prove the server hands
    it a dictionary, which is the shape the app casts to; a bare array there
    turned the whole ledger unreadable once already.
    """
    proc = subprocess.Popen([sys.executable, "-m", "photoloset.mcp"],
                            cwd=ROOT, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True)
    rid = [0]

    def rpc(method: str, params: dict | None = None) -> dict:
        rid[0] += 1
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": rid[0],
                                     "method": method,
                                     "params": params or {}}) + "\n")
        proc.stdin.flush()
        return json.loads(proc.stdout.readline())

    try:
        init = rpc("initialize")["result"]
        check("initialize", init["serverInfo"]["name"] == "photoloset",
              f'{init["serverInfo"]["name"]} {init["protocolVersion"]}')
        tools = rpc("tools/list")["result"]["tools"]
        check("37 tools", len(tools) == 37, f"{len(tools)}")
        check("every tool has a schema",
              all(t.get("inputSchema", {}).get("type") == "object" for t in tools),
              "derived from the signatures")

        args = {
            "garment_observe": dict(part="collar", aspect="shape", value="v", source="s"),
            "garment_infer": dict(part="collar", aspect="shape", value="v", basis="b"),
            "garment_propose": dict(part="collar", aspect="shape", value="v", source="s"),
            "garment_adopt": dict(part="collar", aspect="shape", value="v", by="ci"),
            "measure_taken": dict(spot="chest", value=1.0, unit="cm", source="s"),
            "measure_ratio": dict(spot="waist", value=0.6, basis="chest"),
            "design_history": dict(part="collar", aspect="shape"),
            "rights_intent": dict(intent="personal"),
            "intake_register": dict(path=str(ROOT)),
            "intake_add_clip": dict(source_path=str(ROOT), clip_path="/tmp/a.jpg", mark="m"),
            "intake_origin": dict(clip_path="/tmp/a.jpg"),
            "sew_and_drape": dict(fabric="none", iterations=20),
            "drape_validate": dict(fabric="none", iterations=20),
        }
        with tempfile.TemporaryDirectory() as tmp:
            for t in tools:
                name = t["name"]
                a = dict(args.get(name, {}))
                for key in ("path",):
                    if key in t["inputSchema"]["properties"] and key not in a:
                        a[key] = f"{tmp}/out"
                r = rpc("tools/call", {"name": name, "arguments": a})
                body = json.loads(r["result"]["content"][0]["text"])
                if not isinstance(body, dict):
                    check(f"{name} returns an object", False, type(body).__name__)
                elif body.get("verdict") == "ERROR":
                    check(f"{name} does not crash", False,
                          body.get("why", "")[:70])
        check("every tool returns an object", True, f"{len(tools)} checked")

        absent = json.loads(rpc("tools/call", {"name": "garment_cross",
                                               "arguments": {}}
                                )["result"]["content"][0]["text"])
        check("absent tools say so",
              absent["verdict"] == "UNKNOWN_NOT_IN_THIS_BUILD",
              absent["verdict"])
        anon = json.loads(rpc("tools/call", {
            "name": "garment_adopt",
            "arguments": dict(part="collar", aspect="shape", value="v", by="")}
            )["result"]["content"][0]["text"])
        check("anonymous adoption refused",
              anon["verdict"] == "UNKNOWN_NO_ADOPTER", anon["verdict"])
    finally:
        proc.stdin.close()
        proc.wait(timeout=30)


# ---------------------------------------------------------------------------
def no_dependencies() -> None:
    """The badge says none. This is what makes that checkable."""
    import ast
    import re
    third_party = set()
    stdlib_ok = re.compile(r"^(\.|__future__|json|sys|os|re|math|"
                           r"random|inspect|pathlib|typing|dataclasses|http|"
                           r"socket|argparse|traceback|subprocess|tempfile|"
                           r"functools|collections|webbrowser|urllib|itertools|"
                           r"copy|time|datetime|hashlib|struct|unicodedata|"
                           r"textwrap|difflib|shutil|glob|enum|abc|contextlib|"
                           r"threading|queue|base64|uuid|csv|io|warnings|"
                           r"operator|bisect|heapq|statistics|photoloset)$")
    # Parsed, not grepped. A line-based scan reads the import examples inside
    # docstrings as imports, and misreads `from . import x` — which is the
    # package talking to itself — as a third party.
    for path in (ROOT / "photoloset").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.level > 0:              # relative: our own modules
                    continue
                name = (node.module or "").split(".")[0]
            elif isinstance(node, ast.Import):
                name = node.names[0].name.split(".")[0]
            else:
                continue
            if not stdlib_ok.match(name):
                third_party.add(f"{path.name}: {name}")
    check("no third-party imports", not third_party,
          f"{len(third_party)} found" if third_party else "standard library only")
    for t in sorted(third_party):
        print(f"        {t}")


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"photoloset checks — python {sys.version.split()[0]}\n")
    for fn in (no_dependencies, the_example_runs, the_pipeline_still_agrees,
               english_is_complete, the_mcp_server_answers):
        print(f"{fn.__doc__.splitlines()[0]}")
        fn()
        print()
    if FAILURES:
        print(f"{len(FAILURES)} failed:")
        for f in FAILURES:
            print(f"  {f}")
        raise SystemExit(1)
    print("all checks passed")
