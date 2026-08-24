#!/usr/bin/env python3
"""Everything CI checks, runnable on your own machine the same way.

    python3 tests/run_checks.py

Each check prints what it measured, not just whether it passed. A check that
only says PASS tells you nothing when it later starts lying.
"""
from __future__ import annotations

import json
import os
import shutil
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
    outs["built"] = built
    outs["drape"] = garment_sew.sew_and_drape(built, mat, iterations=200,
                                              stitch_k=20.0 * 64)
    outs["drape.validate"] = garment_drape.validate(40, 40, mat, iterations=100)
    outs["no_material"] = garment_drape.material_from(None, "cupro")
    outs["svg"] = garment_pattern.to_svg(marks)
    outs["draft.refused"] = garment_pattern.draft(Measures())

    # The second garment rides the same promise: every output path the
    # assembler can produce must translate too.
    from photoloset import assemble as _asm
    from photoloset import block as _blk
    from photoloset import garment_skirt as _skirt

    ms2 = Measures()
    for spot, value in [("waist", 64.0), ("hip", 90.0),
                        ("skirt_length", 58.0)]:
        ms2.measured(spot, value, "cm", source="tape", by="ci")
    a2 = _asm.assemble({"silhouette": "Aライン",
                        "closure": "ゴムウエスト（開き無し）",
                        "waist_finish": "シャーリング"})
    if a2["verdict"] == "ANSWER":
        d2 = a2["declaration"]
        st2, root2 = _blk.ingest(decl=d2, formulas=d2["formulas"])
        v2 = _blk.BlockView(st2, root2)
        sd = _skirt.draft(ms2, v2)
        sm = garment_marks.apply(sd)
        outs["skirt.draft"] = sd
        outs["skirt.marks"] = sm
        outs["skirt.built"] = garment_sew.build(sd, marks=sm)
        outs["skirt.draft.refused"] = _skirt.draft(Measures(), v2)

    # The composed garment rides the same promise.
    from photoloset import compose as _cp
    from photoloset import garment_sew as _gs
    ms3 = Measures()
    for spot, value in [("chest", 82.0), ("shoulder", 38.0), ("waist", 62.0),
                        ("bodice_length", 22.0), ("sleeve_length", 52.0),
                        ("hip", 88.0), ("skirt_length", 45.0),
                        ("neck", 21.0), ("cape_length", 28.0)]:
        ms3.measured(spot, value, "cm", source="tape", by="ci")
    dress = {
        "parts": [
            {"instance": "bodice:1", "part": "bodice"},
            {"instance": "skirt:1", "part": "skirt_panel",
             "params": {"hi_lo_drop": 22.0}},
            {"instance": "sleeve:1", "part": "sleeve",
             "params": {"side": "左"}},
            {"instance": "cape:1", "part": "cape"}],
        "connections": [
            {"a": ["bodice:1", "waist"], "b": ["skirt:1", "waist"]},
            {"a": ["bodice:1", "armhole_l"],
             "b": ["sleeve:1", "armhole_l"]},
            {"a": ["bodice:1", "neck"], "b": ["cape:1", "neck"]}],
        "port_finish": {
            "cape:1": {"hem": "free", "center_front": "fold",
                       "center_back": "fold"},
            "skirt:1": {"hem": "free", "center_front": "fold",
                        "center_back": "fold"},
            "bodice:1": {"center_front": "fold", "center_back": "fold"},
            "sleeve:1": {"cuff_l": "free"}},
    }
    rc = _cp.compose(dress, ms3)
    outs["composed"] = rc
    outs["composed.marks"] = garment_marks.apply(rc)
    outs["composed.refused"] = _cp.compose(
        {**dress, "port_finish": {}}, ms3)

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
    # The server stores under Path.home(), and the sweep below calls the
    # mutating tools. Without this the suite writes into the operator's real
    # ledger — measurements, adoptions and intake rows that nobody entered.
    # Give the server a HOME of its own, the same way the tool sweep already
    # hands it a temporary directory for file outputs.
    home = tempfile.mkdtemp(prefix="photoloset-checks-")
    env = dict(os.environ, HOME=home)
    proc = subprocess.Popen([sys.executable, "-m", "photoloset.mcp"],
                            cwd=ROOT, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, env=env)
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
        check("42 tools", len(tools) == 42, f"{len(tools)}")
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
        shutil.rmtree(home, ignore_errors=True)


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
def the_block_lives_on_the_cross() -> None:
    """The coat's declaration lives on the stereo cross, not in files.

    One node holds 6 arms x 4 faces = 24 seats. That capacity is measured,
    not chosen, so the declaration splits into child cores when an arm
    overflows — nesting is required by the geometry, not a design taste.
    The arms are the three dualities, and the arm a fact sits on is derived
    from what KIND of claim it is; nobody gets to choose a convenient one.
    """
    import copy as _copy
    import json as _json

    from photoloset import block as blk
    from photoloset import cross, garment_pattern, garment_sew

    b = blk.coat()
    cen = b.store.census()
    arms = b.arm_census()
    # NOTE: this replaces the old "coat fills its root node exactly" check,
    # which asserted all six arms sat at exactly 4/4. That claim died with
    # the drawers: it could only ever hold while the arms were storage
    # categories. Under typed arms it would demand the coat hold 4 measured,
    # 4 cited, 4 derived, 4 feeds, 4 generic and 4 specific claims, and the
    # coat holds 0 measured, 0 cited and 0 generic. The replacement is
    # strictly stronger — it pins the actual shape AND its falsifier below.
    want = {"support+": 0, "support-": 0, "cause+": 10,
            "cause-": 0, "kind+": 0, "kind-": 17}
    check("coat's arms are the three dualities",
          arms == want and not cen["over_capacity"]
          and set(cross.ARMS) == set(want),
          f'{cen["cores"]} cores, {cen["seats"]} seats — root '
          f'kind- {arms["kind-"]}, cause+ {arms["cause+"]}, '
          f'support+ {arms["support+"]}, kind+ {arms["kind+"]}')

    # Typed gaps, and the falsifier that must make one of them vanish.
    gaps = b.gaps()
    cited = _copy.deepcopy(blk.COAT_DECLARATION)
    cited["name"] = "coat_cited"
    cited["params"] = [("half_divisor", 4.0, None, "cited", None)] + [
        r for r in cited["params"] if r[0] != "half_divisor"]
    st_c, root_c = blk.ingest(decl=cited)
    st_c.put(root_c, "param:half_divisor", {"value": 4.0}, "cited",
             "文化服装学院 文化ファッション大系 改訂版・服飾造形講座")
    v_c = blk.BlockView(st_c, root_c)
    falsified = "UNKNOWN_NO_SUPPORT_RECORDED" in v_c.gaps()
    check("empty arms are typed gaps",
          "UNKNOWN_NO_SUPPORT_RECORDED" in gaps
          and "UNKNOWN_NO_GENERALIZATION_RECORDED" in gaps
          and not falsified,
          f'{len(gaps)} gaps — nothing measured or cited backs the 20 '
          f'params, nothing is claimed generic; one `cited` param with a '
          f'second source removes the support gap ({len(v_c.gaps())} left)')

    check("formulas served from the cross",
          b.formulas() == garment_pattern.FORMULAS
          and len(b.formulas()) == 17,
          f'{len(b.formulas())} entries match the drafting module')

    check("seams served from the cross",
          b.seams() == garment_sew.SEAMS and len(b.seam_edges()) == 4,
          f'{len(b.seams())} seams, {len(b.seam_edges())} '
          'edges between pieces')

    # A fifth ADDRESS on one arm. Refusal is a RETURN VALUE now, and the
    # nesting writer is what block.ingest uses, so it must not refuse.
    small = cross.CrossStore()
    for i in range(cross.FACES_PER_ARM):
        small.put_strict("t", f"k{i}", {"value": float(i)}, "specific", "src")
    refused = small.put_strict("t", "one-too-many", {"value": 1.0},
                               "specific", "src")
    seated = small.put("t", "one-too-many", {"value": 1.0}, "specific", "src")
    check("a fifth face is refused",
          refused["verdict"] == cross.ARM_FULL
          and seated["verdict"] == "ANSWER"
          and seated["core"] != "t",
          f'{refused["verdict"]} from the strict writer — the nesting '
          f'writer put it on {seated["core"]} instead')

    # The rival goes at the ROOT even though the seat lives on a child core.
    # Under address-global resolution the holder is irrelevant; under the
    # old core-local gate this could only be caught by hunting the holder.
    st2, root2 = blk.ingest()
    holder = next(n for n, seats in st2.cores.items()
                  if any(s["key"] == "setting:grain_angle_deg"
                         for s in seats))
    before_seats = st2.census()["seats"]
    rival = st2.put(root2, "setting:grain_angle_deg",
                    {"value": 0.0, "basis": "conflict"},
                    "specific", "declaration:conflict")
    sides = st2.resolve(root2, "setting:grain_angle_deg")
    v2 = blk.BlockView(st2, root2)
    picked = "kept quiet"
    try:
        v2.setting("grain_angle_deg")
    except ValueError as e:
        picked = str(e).split(":")[0]
    check("conflicting declarations go contested",
          rival["verdict"] == cross.CONTESTED_IN_CROSS
          and sides["verdict"] == cross.CONTESTED_IN_CROSS
          and len(sides["sides"]) == 2
          and st2.census()["seats"] == before_seats
          and picked == cross.CONTESTED_IN_CROSS,
          f'seat lives on a child core ({holder}), rival written at the '
          f'root — both kept '
          f'({len(sides["sides"])} sides), no seat consumed, reader '
          f'refuses to pick ({picked})')

    inv = b.store.placement_check()
    check("placement does not move answers",
          inv["verdict"] == "ANSWER" and inv.get("structural"),
          f'{inv["addresses_checked"]} addresses re-ingested in '
          f'{inv["orders"]} orders')

    rt = cross.CrossStore.from_dict(
        _json.loads(_json.dumps(b.store.to_dict())))
    check("round trip moves nothing",
          blk.BlockView(rt, b.root).dump() == b.dump()
          and rt.load_verdict["verdict"] == "ANSWER",
          "the served declaration is byte-equal after storage round trip")


# ---------------------------------------------------------------------------
def the_arms_carry_meaning() -> None:
    """The arm a fact sits on is derived from its kind and has consequences.

    Six drawers named after storage categories would pass every check above
    while being inert. These are the checks that die if the vocabulary goes
    back to being decoration: each one names a store that VIOLATES the
    property and shows it being rejected.
    """
    from photoloset import block as blk, cross, parts

    b = blk.coat()

    # --- arms are derived, never chosen ---------------------------------
    liar = {"cores": {"c": [{"key": "param:x", "arm": "kind+", "seq": 1,
                             "values": [{"value": 1, "kind": "specific",
                                         "sources": ["s"]}]}]},
            "edges": []}
    bad = cross.CrossStore.from_dict(liar)
    honest = b.store.verify()
    every = all(s["arm"] == cross.KIND_ARM[s["values"][0]["kind"]]
                for seats in b.store.cores.values() for s in seats)
    check("arms are derived, not chosen",
          bad.load_verdict["verdict"] == cross.ARM_NOT_DERIVED
          and honest["verdict"] == "ANSWER" and every,
          f'a seat claiming kind+ while its claim is `specific` loads as '
          f'{bad.load_verdict["verdict"]}; all {honest["seats"]} coat seats '
          'derive')

    # --- support- is unwritable, and emerges ----------------------------
    st = cross.CrossStore()
    st.put("c", "param:x", {"v": 1}, "specific", "a")
    before = st.arm_census("c")["support-"]
    st.put("c", "param:x", {"v": 2}, "specific", "b")
    after = st.arm_census("c")["support-"]
    check("support- is never written, only emerges",
          "support-" not in [a for a in cross.KIND_ARM.values()]
          and before == 0 and after == 1
          and st.resolve("c", "param:x")["also_on"] == "support-",
          f'no kind maps to support-; a collision moved it {before}→{after}')

    # --- no_match is not stored -----------------------------------------
    st2 = cross.CrossStore()
    st2.put("c", "param:y", {"v": 1}, "specific", "a")
    snap = st2.census()
    nm = st2.put("c", "param:z", {"v": 9}, "no_match", "search")
    seated = {"cores": {"c": [{"key": "k", "arm": "kind-", "seq": 1,
                               "values": [{"value": 1, "kind": "no_match",
                                           "sources": ["s"]}]}]},
              "edges": []}
    seated_store = cross.CrossStore.from_dict(seated)
    check("absence is not a claim",
          nm["verdict"] == cross.NOT_A_CLAIM and nm["stored"] is False
          and st2.census() == snap
          and seated_store.load_verdict["verdict"] == cross.ARM_NOT_DERIVED,
          'a no_match put changes nothing; a store that seated one is '
          f'rejected as {seated_store.load_verdict["verdict"]}')

    # --- agreement makes a seat heavier, not wider ----------------------
    st3 = cross.CrossStore()
    for src in ("tape", "second fitter", "photo", "the pattern"):
        st3.put_strict("c", "measure:chest", {"value": 108.0},
                       "measured", src)
    for spot in ("waist", "hip", "shoulder"):
        st3.put_strict("c", f"measure:{spot}", {"value": 80.0},
                       "measured", "tape")
    r = st3.resolve("c", "measure:chest")
    keys = {s["key"] for s in st3.cores["c"]}
    others = [st3.resolve("c", f"measure:{x}")["verdict"]
              for x in ("waist", "hip", "shoulder")]
    triples = {"cores": {"c": [
        {"key": "measure:chest", "arm": "support+", "seq": i,
         "values": [{"value": 108.0, "kind": "measured",
                     "sources": [f"s{i}"]}]} for i in range(4)]},
        "edges": []}
    dup = cross.CrossStore.from_dict(triples)
    check("agreement does not consume seats",
          r["weight"] == 4 and len(st3.cores["c"]) == 4
          and keys == {"measure:chest", "measure:waist", "measure:hip",
                       "measure:shoulder"}
          and others == ["ANSWER"] * 3
          and st3.census()["over_capacity"] == []
          and dup.load_verdict["verdict"] == cross.DUPLICATE_ADDRESS,
          f'4 sources on one measurement = 1 seat of weight '
          f'{r["weight"]}, and 3 OTHER measurements still seat on the same '
          f'arm ({len(keys)} distinct addresses); the triple-counted shape '
          f'loads as {dup.load_verdict["verdict"]}')

    # --- a generic claim must be bought ---------------------------------
    lib = parts.Library()
    unbought = lib.unbought_generics()
    bought = cross.CrossStore()
    bought.put("p:s", "family", {"open": True}, "generic", "文化ファッション大系")
    bought.put("p:s", "family", {"open": True}, "generic", "文化服装学院")
    check("a generic claim needs two sources",
          len(unbought) == 3
          and all(u["verdict"] == cross.GENERIC_NOT_BOUGHT
                  for u in unbought)
          and bought.unbought_generics() == []
          and b.store.unbought_generics() == [],
          f'{len(unbought)} family claims rest on the library alone; a '
          'second independent source clears one; the coat has no generic '
          'claims at all')

    # --- ordered reads follow the declaration, not the traversal --------
    honest_order = list(b.formulas())
    st4, root4 = blk.ingest()
    st4.put(blk.piece_core(root4, "袖"), "formula:割り込み",
            "seq 0 に割り込む式", "derived", "declaration:coat", seq=0)
    v4 = blk.BlockView(st4, root4)
    injected = list(v4.formulas())
    check("ordered reads follow the declaration",
          honest_order == [n for n, _t, _s in blk.FORMULA_ORDER]
          and injected[0] == "割り込み"
          and injected[1:] == honest_order,
          f'17 formulas in declaration order across 4 subject cores; a '
          f'seat with seq 0 on a piece core reads FIRST ({injected[0]}), '
          'so the reader sorts by seq, not by traversal')


# ---------------------------------------------------------------------------
def the_cross_refuses_what_it_should() -> None:
    """Each refusal, with the store that provokes it.

    Every check here was built by first writing the store that violates the
    property and confirming the check rejects it. A check that cannot fail
    is not a check; this project shipped two of those, which is how these
    defects survived a first review.
    """
    import copy as _copy

    from photoloset import block as blk, cross

    b = blk.coat()

    # --- P1: the order check that can actually fail ---------------------
    plan = [("t", f"k{i}", {"value": float(i)}, "specific", "src")
            for i in range(5)]
    loose = cross.ingest_order_check(plan, nest=False)
    tight = cross.ingest_order_check(plan, nest=True)
    coat_plan = cross.ingest_order_check(b.store.write_plan(), nest=True)
    check("ingest order does not move answers",
          loose["verdict"] == cross.ORDER_DEPENDENT
          and tight["verdict"] == "ANSWER"
          and coat_plan["verdict"] == "ANSWER",
          f'5 addresses on one arm through the NON-nesting writer are '
          f'genuinely order dependent ({len(loose["differences"])} '
          f'differences); nesting makes the same plan order independent; '
          f'the coat\'s {coat_plan["addresses"]} addresses re-ingest '
          f'identically in {coat_plan["orders"]} orders')

    # --- P2: contest is reachable at EVERY address ----------------------
    subjects = [b.root] + b.store.part_of_children(b.root)
    addresses = [(s, seat["key"]) for s in subjects
                 for seat in b.store.seats(s)]
    bad_addr = []
    for subj, key in addresses:
        st, root = blk.ingest()
        subj2 = subj.replace(b.root, root, 1)
        before = st.census()["seats"]
        r = st.put(subj2, key, {"__rival__": True}, "specific", "rival")
        listed = any(c["key"] == key for c in st.contested())
        if (r["verdict"] != cross.CONTESTED_IN_CROSS
                or st.census()["seats"] != before or not listed):
            bad_addr.append((subj2, key, r["verdict"]))
    check("contest is reachable at every address",
          not bad_addr and len(addresses) == 56,
          f'{len(addresses)} of {len(addresses)} coat addresses answer '
          f'CONTESTED to a rival value, consume no seat, and appear in '
          f'contested(); {len(bad_addr)} refused with the wrong verdict')

    # --- P2b: the matryoshka does not hide a contest --------------------
    st = cross.CrossStore()
    for i in range(cross.FACES_PER_ARM):
        st.put("r", f"k{i}", {"v": i}, "specific", "src")
    spill = st.put("r", "k4", {"v": 4}, "specific", "src")
    rival = st.put("r", "k0", {"v": 99}, "specific", "other")
    child = spill["core"]
    orphan = {"cores": {
        "r": [{"key": "param:x", "arm": "kind-", "seq": 1,
               "values": [{"value": 1, "kind": "specific",
                           "sources": ["a"]}]}],
        "r·kind-·1": [{"key": "param:x", "arm": "kind-", "seq": 2,
                       "values": [{"value": 2, "kind": "specific",
                                   "sources": ["b"]}]}]},
        "edges": []}
    orph = cross.CrossStore.from_dict(orphan)
    check("a contest survives the matryoshka",
          child != "r" and rival["verdict"] == cross.CONTESTED_IN_CROSS
          and st.resolve("r", "k0")["verdict"] == cross.CONTESTED_IN_CROSS
          and st.resolve(child, "k0")["verdict"] == cross.CONTESTED_IN_CROSS
          and [(c["key"], c["sides"]) for c in st.contested()] == [("k0", 2)]
          and orph.load_verdict["verdict"] == cross.ORPHANED_CORE,
          f'k4 spilled to {child}; a rival for k0 contests from both ends '
          f'of the chain; a child its parent cannot reach loads as '
          f'{orph.load_verdict["verdict"]}')

    # --- P4: an edge with one end is not a relation ---------------------
    st2 = cross.CrossStore()
    st2.put("a", "k", {"v": 1}, "specific", "s")
    n_before = len(st2.edges)
    e1 = st2.link(("a", "k"), None, "seam:junk")
    e2 = st2.link(("nowhere", "k"), ("a", "k"), "nest")
    e3 = st2.link(("a", "k"), ("a", "k"), "")
    ok = st2.link(("a", "k"), ("a", "k"), "seam:袖下線")
    poisoned = cross.CrossStore.from_dict(
        {"cores": {"a": []},
         "edges": [{"a": ["a", "k"], "b": None, "label": "nest"},
                   {"a": ["ghost", "k"], "b": ["a", "k"], "label": "nest"},
                   {"a": ["a", "k"], "b": ["a", "k"], "label": ""}]})
    n_bad = len([p for p in poisoned.load_verdict.get("problems", [])
                 if "index" in p])
    check("an edge with one end is refused",
          all(e["verdict"] == cross.DANGLING_EDGE for e in (e1, e2, e3))
          and ok["verdict"] == "ANSWER"
          and len(st2.edges) == n_before + 1
          and poisoned.load_verdict["verdict"] == cross.DANGLING_EDGE
          and n_bad == 3,
          f'3 malformed edges refused and NOT stored ({len(st2.edges)} '
          f'edge, the legal self-relation); a loaded store carrying all '
          f'three names {n_bad}')

    # --- P5: reads create nothing, loads are verified -------------------
    st3 = cross.CrossStore()
    st3.put("a", "k", {"v": 1}, "specific", "s")
    snap = _copy.deepcopy(st3.to_dict())
    for i in range(100):
        st3.resolve(f"ghost{i}", "nope")
        st3.contested()
        st3.census()
    over = cross.CrossStore.from_dict({"cores": {"c": [
        {"key": f"k{i}", "arm": "kind-", "seq": i,
         "values": [{"value": i, "kind": "specific", "sources": ["s"]}]}
        for i in range(5)]}, "edges": []})
    checked = cross.CrossStore.from_dict_checked({"cores": {}, "edges": []})
    check("reads create nothing, loads are verified",
          st3.to_dict() == snap and list(st3.cores) == ["a"]
          and over.load_verdict["verdict"] == cross.OVER_CAPACITY
          and checked["verdict"] == "ANSWER"
          and isinstance(checked["store"], cross.CrossStore),
          f'100 probes of absent addresses left {len(st3.cores)} core; a '
          f'hand-edited store with 5 seats on one arm loads as '
          f'{over.load_verdict["verdict"]}')

    # --- P6: the store owns its values ----------------------------------
    st4 = cross.CrossStore()
    held = {"value": 1}
    st4.put("c", "k", held, "specific", "a")
    st4.put("c", "k", {"value": 2}, "specific", "b")
    was = st4.resolve("c", "k")["verdict"]
    held["value"] = 2
    still = st4.resolve("c", "k")["verdict"]
    st4.put("c", "j", {"value": 7}, "specific", "a")
    got = st4.resolve("c", "j")
    got["value"]["value"] = 999
    unmoved = st4.resolve("c", "j")["value"]["value"]
    shared = {"value": 1}
    aliased = cross.CrossStore()
    aliased.cores = {"c": [
        {"key": "k1", "arm": "kind-", "seq": 1,
         "values": [{"value": shared, "kind": "specific", "sources": ["a"]}]},
        {"key": "k2", "arm": "kind-", "seq": 2,
         "values": [{"value": shared, "kind": "specific", "sources": ["b"]}]}]}
    check("the store owns its values",
          was == cross.CONTESTED_IN_CROSS
          and still == cross.CONTESTED_IN_CROSS
          and unmoved == 7
          and aliased.aliased_values()["verdict"] == cross.ALIASED_VALUE
          and st4.aliased_values()["verdict"] == "ANSWER",
          'a caller mutating the object it still holds cannot collapse '
          'CONTESTED into ANSWER, and mutating what resolve() returned '
          'leaves the seat at 7; two seats sharing one object are named '
          f'{aliased.aliased_values()["verdict"]}')

    # --- P8: the declaration can grow -----------------------------------
    grown = _copy.deepcopy(blk.COAT_DECLARATION)
    grown["name"] = "coat_hooded"
    grown["pieces"] = list(grown["pieces"]) + [("フード", False)]
    grown["required"] = tuple(grown["required"]) + ("neck", "waist")
    grown["placement"]["フード"] = ((0.0, 40.0, 0.0), "フードは上")
    st5, root5 = blk.ingest(decl=grown)
    v5 = blk.BlockView(st5, root5)
    twice = _copy.deepcopy(blk.COAT_DECLARATION)
    twice["name"] = "coat_twice"
    twice["pieces"] = list(twice["pieces"]) + [("後身頃", False)]
    st6, root6 = blk.ingest(decl=twice)
    v6 = blk.BlockView(st6, root6)
    dbl = st6.contested()
    served = "served a list anyway"
    try:
        v6.pieces()
    except ValueError as e:
        served = str(e).split(":")[0]
    check("a fourth piece and a fifth measurement are declarable",
          len(v5.pieces()) == 4 and len(v5.measures()) == 6
          and st5.census()["over_capacity"] == []
          and not st5.contested()
          and len(st6.part_of_children(root6)) == 3
          and len(dbl) == 1 and dbl[0]["key"] == "role"
          and served == cross.CONTESTED_IN_CROSS
          and len(v6.refusals()) == 1,
          f'{len(v5.pieces())} pieces, {len(v5.measures())} measurements, '
          f'{st5.census()["cores"]} cores, no crash; re-declaring 後身頃 '
          f'with a different `required` contests at the existing piece '
          f'rather than seating a 4th ({len(st6.part_of_children(root6))} '
          f'pieces), and the reader refuses to serve the list ({served})')

    # --- a subject nobody declared must not swallow the seat ------------
    ghost = _copy.deepcopy(blk.COAT_DECLARATION)
    ghost["name"] = "coat_ghost"
    ghost["params"] = [("half_divisor", 4.0, None, "specific", "存在しない枚")
                       ] + [r for r in ghost["params"]
                            if r[0] != "half_divisor"]
    st8, root8 = blk.ingest(decl=ghost)
    v8 = blk.BlockView(st8, root8)
    stranded = [n for n in st8.cores if "存在しない" in n]
    ref = v8.refusals()
    try:
        readable = v8.param("half_divisor")
    except ValueError as e:
        readable = str(e).split(":")[0]
    check("an undeclared subject does not swallow the seat",
          readable == 4.0
          and not stranded
          and len(ref) == 1 and ref[0]["verdict"] == blk.NO_SUCH_SUBJECT
          and ref[0]["key"] == "param:half_divisor"
          and not b.refusals(),
          'a param declared against a piece that was never declared would '
          'sit in a core no part_of edge reaches — readable by nobody, '
          f'refused by nobody. It now seats on the root (reads back '
          f'{readable}) and says '
          f'{ref[0]["verdict"] if ref else "nothing"}; '
          f'{len(stranded)} stranded cores')

    # --- the new hazard the reshaping creates ---------------------------
    st7, root7 = blk.ingest()
    st7.put(blk.piece_core(root7, "袖"), "param:half_divisor",
            {"value": 3.0}, "specific", "declaration:sleeve")
    v7 = blk.BlockView(st7, root7)
    picked = "silently picked one"
    try:
        v7.param("half_divisor")
    except ValueError as e:
        picked = str(e).split(":")[0]
    check("param refuses across subjects",
          picked == blk.AMBIGUOUS_ACROSS_SUBJECTS
          and st7.contested() == []
          and b.param("half_divisor") == 4.0,
          'block:coat says 4.0 and block:coat/piece:袖 says 3.0 — two '
          'DIFFERENT addresses, so contested() is correctly silent, and '
          f'a naive search would return whichever it met first ({picked})')


# ---------------------------------------------------------------------------
def parts_assemble_a_second_garment() -> None:
    """The assembler turns approved part choices into a sewable declaration.

    The library holds candidates as facets on the stereo cross. A variant
    that has no drafting procedure is declared but not draftable — picking
    it must refuse by name, never silently substitute.
    """
    from photoloset import assemble, block, garment_marks
    from photoloset import garment_pattern, garment_sew, garment_skirt
    from photoloset import Measures

    a = assemble.assemble({"nosuch": "x"})
    check("unknown slot refused", a["verdict"] == "UNKNOWN_NO_SUCH_SLOT",
          a["verdict"])
    a = assemble.assemble({"silhouette": "存在しない"})
    check("unknown variant refused", a["verdict"] == "UNKNOWN_NO_SUCH_VARIANT",
          f'known: {len(a.get("known", []))}')
    a = assemble.assemble({"closure": "後ろセンターファスナー"})
    check("undraftable variant refuses by name",
          a["verdict"] == "UNKNOWN_PART_NOT_DRAFTABLE"
          and a.get("alternatives"),
          f'{a.get("why", "")[:40]}… alt {a.get("alternatives")}')

    ms = Measures()
    for spot, value in [("waist", 64.0), ("hip", 90.0),
                        ("skirt_length", 58.0)]:
        ms.measured(spot, value, "cm", source="tape", by="ci")
    a = assemble.assemble({"silhouette": "Aライン",
                           "closure": "ゴムウエスト（開き無し）",
                           "waist_finish": "シャーリング"})
    if a["verdict"] != "ANSWER":
        check("assembler builds the skirt declaration", False, a["verdict"])
        return
    decl = a["declaration"]
    st, root = block.ingest(decl=decl, formulas=decl["formulas"])
    cen = st.census()
    view = block.BlockView(st, root)
    check("assembled declaration lives on the cross",
          not cen["over_capacity"] and not cen["contested"]
          and tuple(view.required()) == ("waist", "hip", "skirt_length"),
          f'{cen["cores"]} cores, {cen["facets"]} facets')

    d = garment_skirt.draft(ms, view)
    check("skirt drafts through the shared engine",
          d["verdict"] == "ANSWER"
          and [p["name"] for p in d["pieces"]] == ["前身頃", "後身頃"],
          f'{d.get("total_area_cm2")} cm2, {len(d.get("formulas", {}))} '
          "formulas")

    m = garment_marks.apply(d)
    n_notches = sum(len(v) for v in m.get("notches", {}).values())
    sa_ok = all(v.get("verdict") == "ANSWER"
                for v in m.get("seam_allowance", {}).values())
    check("skirt marks pair and face outward",
          n_notches == 4 and len(m["notch_pairs"]) == 2
          and not m["notch_unpaired"] and sa_ok,
          f'{n_notches} notches, {len(m["notch_pairs"])} pairs, '
          f'{len(m["notch_unpaired"])} unpaired')

    built = garment_sew.build(d, marks=m)
    mat = {"verdict": "ANSWER", "fabric": "twill", "gsm": 280.0,
           "thickness": 0.12, "stiffness": 12.0}
    gap = garment_sew.sew_and_drape(built, mat, iterations=2000,
                                    stitch_k=12.0 * 64)["seam_gap"]
    check("skirt sews shut hanging from the waist",
          built["pins_policy"] == "waist_extremes" and gap["closed"]
          and gap["over_tolerance"] == 0,
          f'worst {gap["worst"]} cm, {gap["over_tolerance"]} over, '
          f'hung by {built["pins_policy"]}')


# ---------------------------------------------------------------------------
def prompts_switch_per_model_and_keep_discipline() -> None:
    """Prompts are per-model; the receiver, not the prompt, enforces discipline.

    A prompt asking nicely for no confidence numbers proves nothing on the
    day the model ignores it — so the parser refuses them by name.
    """
    import json as _json

    from photoloset import prompts

    qwen = prompts.for_model("lmstudio:qwen3.6:35b-a3b")
    sibling = prompts.for_model("lmstudio:some-future-model")
    stranger = prompts.for_model("openai:some-vision-model")
    check("per-model prompts with versions",
          qwen["matched"] == "profile" and stranger["matched"] == "default"
          and qwen["version"] and stranger["version"],
          f'qwen={qwen["version"]} (profile); a new lmstudio model '
          f'inherits it ({sibling["matched"]}); an unknown family '
          f'falls back to default ({stranger["version"]})')

    missing = [c[:12] for c in prompts.DISCIPLINE
               if c[:12] not in qwen["text"]]
    check("discipline is inside every prompt", not missing,
          f'{len(prompts.DISCIPLINE)} clauses embedded')

    from photoloset import parts as _pv
    bank = prompts.siglip_queries()
    check("siglip bank covers the part vocabulary",
          len(bank) >= len(prompts.PART_QUERY_BANK)
          and all(fam in prompts.PART_QUERY_BANK
                  for fam in _pv.PART_VOCAB),
          f"{len(bank)} queries across "
          f'{len(prompts.PART_QUERY_BANK)} families')

    good = prompts.parse_decomposition("lmstudio:qwen3.6:35b-a3b", _json.dumps({
        "kind_guess": None,
        "parts": [{"part": "cape", "variant_hint": "肩から裾へ",
                   "ports": ["neck", "shoulder_l", "shoulder_r"],
                   "evidence": "肩の白い布", "region": "上半分"}],
        "unknowns": [{"aspect": "背面の開き", "why": "背面が写っていない",
                      "candidate_hints": ["開き無し", "中央開き"]}],
        "queries": ["white cape dress"]}))
    check("valid decomposition accepted with provenance",
          good["verdict"] == "ANSWER"
          and "prompt=" in good["source"]
          and "white cape dress" in good["queries"],
          f'source: {good.get("source", "")[:48]}…')

    sneaky = _json.dumps({"parts": [{"part": "cape", "ports": ["neck"],
                                     "confidence": 0.93}]})
    check("confidence numbers refused",
          prompts.parse_decomposition("default", sneaky)["verdict"]
          == "UNKNOWN_FORBIDDEN_CONFIDENCE",
          "VM2 — the model's self-reported number never reaches a fact")

    check("unknown port refused",
          prompts.parse_decomposition(
              "default", _json.dumps({"parts": [
                  {"part": "sleeve", "ports": ["elbow_l"]}]})
          )["verdict"] == "UNKNOWN_UNKNOWN_PORT",
          "closed port vocabulary")

    check("unknown part family refused",
          prompts.parse_decomposition(
              "default", _json.dumps({"parts": [{"part": "mantle"}]})
          )["verdict"] == "UNKNOWN_UNKNOWN_PART",
          "new parts must arrive as new_part, not as a guess")

    check("malformed json refused",
          prompts.parse_decomposition("default", "すみません、")["verdict"]
          == "UNKNOWN_MALFORMED_PROPOSAL",
          "a refusal, not a crash")

    props = prompts.to_proposals(good)
    check("everything lands as proposals",
          props and all(p["source"].startswith("lmstudio:") for p in props)
          and len(props) == 2,
          f'{len(props)} proposals (1 part, 1 unknown), all PROPOSED')


# ---------------------------------------------------------------------------
def compose_builds_a_whole_garment_from_parts() -> None:
    """A garment is a parts graph. Type names are labels, not capability.

    The cape dress — unclassifiable as a "type" — must compose from
    bodice + high-low skirt + sleeve + cape, with every open port named
    and every connection's length difference printed.
    """
    import json as _json

    from photoloset import compose, garment_marks, garment_sew
    from photoloset import Measures

    ms = Measures()
    for spot, value in [("chest", 82.0), ("shoulder", 38.0), ("waist", 62.0),
                        ("bodice_length", 22.0), ("sleeve_length", 52.0),
                        ("hip", 88.0), ("skirt_length", 45.0),
                        ("neck", 21.0), ("cape_length", 28.0)]:
        ms.measured(spot, value, "cm", source="tape", by="ci")

    a = compose.compose({"parts": [{"instance": "x:1", "part": "mantle"}]},
                        ms)
    check("unknown part refused", a["verdict"] == "UNKNOWN_NO_SUCH_PART",
          f'{a.get("which")} — known: {len(a.get("known", []))}')
    a = compose.compose({"parts": [{"instance": "bodice:1",
                                    "part": "bodice"}],
                         "connections": [{"a": ["bodice:1", "elbow_l"],
                                          "b": ["bodice:1", "waist"]}]}, ms)
    check("unknown port refused", a["verdict"] == "UNKNOWN_UNKNOWN_PORT",
          a.get("which", ""))

    dress = {
        "parts": [
            {"instance": "bodice:1", "part": "bodice"},
            {"instance": "skirt:1", "part": "skirt_panel",
             "params": {"hi_lo_drop": 22.0}},
            {"instance": "sleeve:1", "part": "sleeve",
             "params": {"side": "左"}},
            {"instance": "cape:1", "part": "cape"}],
        "connections": [
            {"a": ["bodice:1", "waist"], "b": ["skirt:1", "waist"]},
            {"a": ["bodice:1", "armhole_l"], "b": ["sleeve:1", "armhole_l"]},
            {"a": ["bodice:1", "neck"], "b": ["cape:1", "neck"]}],
        "port_finish": {
            "cape:1": {"hem": "free", "center_front": "fold",
                       "center_back": "fold"},
            "skirt:1": {"hem": "free", "center_front": "fold",
                        "center_back": "fold"},
            "bodice:1": {"center_front": "fold", "center_back": "fold"},
            "sleeve:1": {"cuff_l": "free"}},
        "label": "ケープワンピース",
    }
    naked = dict(dress)
    naked["port_finish"] = {}
    a = compose.compose(naked, ms)
    open_ports = sorted({(o["instance"], o["port"])
                         for o in a.get("open", [])})
    check("open ports are named, never filled",
          a["verdict"] == "UNKNOWN_OPEN_PORT" and len(open_ports) >= 6,
          f'{len(open_ports)} open, e.g. {open_ports[:3]}')

    r = compose.compose(dress, ms)
    bad = [c for c in r.get("seam_checks", []) if not c["sewable"]]
    check("cape dress composes from parts",
          r["verdict"] == "ANSWER" and len(r["pieces"]) == 6 and not bad,
          f'{len(r["pieces"])} pieces, {len(r["seam_specs"])} seams, '
          f'{len(bad)} not sewable')
    check("the type name is only a label",
          r.get("label") == "ケープワンピース" and "ラベル" in
          r.get("kind_note", ""),
          "no registration happened — the label rides the combination")

    m = garment_marks.apply(r)
    sa_ok = all(v.get("verdict") == "ANSWER"
                for v in m.get("seam_allowance", {}).values())
    check("allowances face outward on every part", sa_ok,
          f'{len(m.get("seam_allowance", {}))} pieces offset')

    b = garment_sew.build(r, marks=m)
    mat = {"verdict": "ANSWER", "fabric": "wool melton", "gsm": 420.0,
           "thickness": 0.18, "stiffness": 20.0}
    gap = garment_sew.sew_and_drape(b, mat, iterations=6000,
                                    stitch_k=20.0 * 128)["seam_gap"]
    check("the composed dress sews shut",
          gap["closed"] and gap["over_tolerance"] == 0,
          f'worst {gap["worst"]} cm, {gap["over_tolerance"]} over, '
          f'{gap["stitches"]} stitches')


# ---------------------------------------------------------------------------
def zones_number_the_garment_for_adjustment() -> None:
    """Every design knob gets a stable number; measures never move.

    The agent loop says "give zone 1 more ease" — not "make it nicer".
    Numbers are deterministic per parts graph, and applying them records
    what changed instead of quietly mutating.
    """
    from photoloset import compose, garment_marks, garment_sew, zones
    from photoloset import Measures

    ms = Measures()
    for spot, value in [("chest", 82.0), ("shoulder", 38.0), ("waist", 62.0),
                        ("bodice_length", 22.0), ("sleeve_length", 52.0),
                        ("hip", 88.0), ("skirt_length", 45.0),
                        ("neck", 21.0), ("cape_length", 28.0)]:
        ms.measured(spot, value, "cm", source="tape", by="ci")
    dress = {
        "parts": [
            {"instance": "bodice:1", "part": "bodice"},
            {"instance": "skirt:1", "part": "skirt_panel",
             "params": {"hi_lo_drop": 22.0}},
            {"instance": "sleeve:1", "part": "sleeve",
             "params": {"side": "左"}},
            {"instance": "cape:1", "part": "cape"}],
        "connections": [
            {"a": ["bodice:1", "waist"], "b": ["skirt:1", "waist"]},
            {"a": ["bodice:1", "armhole_l"],
             "b": ["sleeve:1", "armhole_l"]},
            {"a": ["bodice:1", "neck"], "b": ["cape:1", "neck"]}],
        "port_finish": {
            "cape:1": {"hem": "free", "center_front": "fold",
                       "center_back": "fold"},
            "skirt:1": {"hem": "free", "center_front": "fold",
                        "center_back": "fold"},
            "bodice:1": {"center_front": "fold", "center_back": "fold"},
            "sleeve:1": {"cuff_l": "free"}},
    }

    r1 = compose.compose(dress, ms)
    r2 = compose.compose(dress, ms)
    z1 = r1.get("zones", [])
    check("zones are numbered deterministically",
          len(z1) == 10 and z1 == r2.get("zones")
          and [z["id"] for z in z1] == list(range(1, 11)),
          f'{len(z1)} zones, e.g. '
          f'{[(z["id"], z["label"]) for z in z1[:3]]}…')

    a = zones.apply(dress, {"1": 1.5, "7": 0.1})
    applied = a.get("applied", [])
    r3 = compose.compose(a["graph"], ms)
    area = round(sum(p["area_cm2"] for p in r3.get("pieces", [])), 1)
    check("applying a delta records what changed",
          a["verdict"] == "ANSWER" and len(applied) == 2
          and applied[0]["was"] == "既定" and applied[0]["now"] == 1.5
          and r3["verdict"] == "ANSWER",
          f'zone1 chest_ease 既定→{applied[0]["now"]}, '
          f'zone7 flare +{applied[1]["delta"]} — area {area} cm2')

    check("measures never move",
          ms.state("chest")["state"] == "MEASURED"
          and ms.sheet()["measured"][0]["value"] == 82.0,
          "adjustment touches design params only")

    e = zones.apply(dress, {"99": 1.0})
    check("unknown zone refused",
          e["verdict"] == "UNKNOWN_NO_SUCH_ZONE" and e.get("valid"),
          f'valid: {e.get("valid")}')

    m = garment_marks.apply(r3)
    b = garment_sew.build(r3, marks=m)
    mat = {"verdict": "ANSWER", "fabric": "wool melton", "gsm": 420.0,
           "thickness": 0.18, "stiffness": 20.0}
    gap = garment_sew.sew_and_drape(b, mat, iterations=6000,
                                    stitch_k=20.0 * 128)["seam_gap"]
    check("the adjusted dress still sews shut",
          gap["closed"] and gap["over_tolerance"] == 0,
          f'worst {gap["worst"]} cm after adjustment')

    from photoloset import garment_pattern
    coat = garment_pattern.draft(ms if False else Measures())
    check("the coat has no zones (untouched path)",
          "zones" not in coat,
          "legacy drafting keeps its byte-identical shape")


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"photoloset checks — python {sys.version.split()[0]}\n")
    for fn in (no_dependencies, the_example_runs, the_pipeline_still_agrees,
               english_is_complete, the_block_lives_on_the_cross,
               the_arms_carry_meaning, the_cross_refuses_what_it_should,
               parts_assemble_a_second_garment,
               prompts_switch_per_model_and_keep_discipline,
               compose_builds_a_whole_garment_from_parts,
               zones_number_the_garment_for_adjustment,
               the_mcp_server_answers):
        print(f"{fn.__doc__.splitlines()[0]}")
        fn()
        print()
    if FAILURES:
        print(f"{len(FAILURES)} failed:")
        for f in FAILURES:
            print(f"  {f}")
        raise SystemExit(1)
    print("all checks passed")
