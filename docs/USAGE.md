# Usage

Everything below is runnable. The numbers quoted are the ones the tool actually
prints; if yours differ, yours are right and this document is stale.

- [Requirements](#requirements)
- [Run the application](#run-the-application)
- [As an MCP server](#as-an-mcp-server)
- [English](#english)
- [The five states](#the-five-states)
- [1. Record what a model proposed](#1-record-what-a-model-proposed)
- [2. Adopt it, by name](#2-adopt-it-by-name)
- [3. See what is still missing](#3-see-what-is-still-missing)
- [4. Measure the real garment](#4-measure-the-real-garment)
- [5. When two measurements disagree](#5-when-two-measurements-disagree)
- [6. Draft the pattern](#6-draft-the-pattern)
- [7. Notches, seam allowance, grain](#7-notches-seam-allowance-grain)
- [8. Sew it and let it fall](#8-sew-it-and-let-it-fall)
- [9. Export at 1:1 and print it](#9-export-at-11-and-print-it)
- [Reading a refusal](#reading-a-refusal)
- [Module map](#module-map)
- [Things that will bite you](#things-that-will-bite-you)

---

## Requirements

Python 3.9 or newer. No third-party packages — no numpy, no scipy, nothing to
install.

```bash
git clone https://github.com/Ag3497120/photoloset.git
cd photoloset
python3 examples/black_coat.py
```

That example is the same nine steps as this document, end to end, in about
five seconds.

---

## Run the application

```bash
python3 -m photoloset --lang en
```

A local page on `127.0.0.1:8910`. Standard library only — no build step, no
framework, no network calls. It is the ledger drawn as a garment: colour is
state, clicking a part opens the structure inspector, a proposal carries an
adopt button that refuses to submit without a name, and the tech pack prints.

| Flag | |
| --- | --- |
| `--lang en` / `--lang ja` | interface and API language (default `ja`) |
| `--port N` | default 8910 |
| `--lan` | serve to this LAN as well; it prints your address and warns you |
| `--no-browser` | do not open a browser |

The ledger lives in `~/.photoloset/ledger.json` and measurements in
`~/.photoloset/measures.json`. Routes:

| Route | |
| --- | --- |
| `GET /` | the page |
| `GET /api/spec` | the ledger, its timeline and the parts |
| `GET /api/techpack` | the tech pack |
| `GET /api/pattern.svg` | the pattern, or a typed refusal if the measurements are not there |
| `POST /api/add` | record an observation, inference or proposal |
| `POST /api/adopt` | adopt a proposal — **400 `UNKNOWN_NO_ADOPTER` without a name** |

`?lang=en` works per request, so one running server can answer in either
language.

**What the browser app does not cover.** Drafting, marks, sewing and draping
are driven from Python; the page shows the ledger and the pattern. The frames
in the README come from the macOS app in **`app/`**, which is in this
repository and covers all of it — see [The macOS
app](#the-macos-app).

---

## As an MCP server

```bash
python3 -m photoloset.mcp
```

JSON-RPC 2.0 over stdin/stdout — `initialize`, `tools/list`, `tools/call`. No
MCP SDK: the whole package promises no dependencies, and the three methods a
tool server needs are about a hundred lines of `json` and a loop.

Point Claude Code, Claude Desktop or Cursor at it:

```json
{ "mcpServers": { "photoloset": {
    "command": "python3", "args": ["-m", "photoloset.mcp"],
    "cwd": "/path/to/photoloset" } } }
```

42 tools: intake, the ledger, measurements, the pattern and its marks, sewing
and drape, the reference body, the solid, design and rights. The store is
`~/.photoloset/`.

**Five of them are absent and say so.** `garment_cross` and the four `fabric_*`
tools need the coordinate memory and its language engine — about 15,700 lines
that are not part of this package. They return `UNKNOWN_NOT_IN_THIS_BUILD`
with what would close it, rather than failing. Fabric properties are read from
`~/.photoloset/fabrics.json` instead; an entry missing `gsm`, `thickness` or
`stiffness` refuses rather than being filled in with a default, because a
guessed weight changes how the whole garment hangs.

A refusal crosses the wire as a normal return value with a verdict beginning
`UNKNOWN_` or `CONTESTED_`, never as an exception — so a caller cannot mistake
"it declined" for "it crashed". A genuine crash returns `ERROR` with a
traceback, and is not dressed up as a refusal.

---

## The macOS app

```bash
open app/Verantyx.xcodeproj      # then run it
```

It opens on the Atelier and drives this package over MCP: a build phase copies
`photoloset/` into the app's `Contents/Resources`, and `MCPEngine` launches
`python3 -m photoloset.mcp` from there. No separate install, no frozen helper —
the 78 MB binary the app used to embed did the same 42 tools in 250 KB less
readable form.

If you move the built `.app` somewhere odd and the ledger comes up
`UNKNOWN_ENGINE_UNREACHABLE`, that is the resolver failing to find
`photoloset/mcp.py`. It looks in the bundle's Resources first, then walks up
from the running binary; each candidate is checked for that file before it is
used. Rebuilding restores the embedded copy.

`app/` is macOS only. Everything else in this package runs anywhere Python does.

---

## English

The engine's own strings are Japanese. English is produced by a translation
layer over its output rather than by rewriting it, because the drafting code is
shared with a larger project and forking it would let the two copies drift.

```python
import photoloset
photoloset.set_language("en")      # every entry point returns English
photoloset.set_language("ja")      # and back; the wrappers are removed
```

Three ways in, depending on how explicit you want to be:

```python
photoloset.set_language("en")      # a default for the whole process
photoloset.en(result)              # one value, default untouched
photoloset.i18n.svg(document)      # a pattern SVG
```

The honest edge of this design is that a string the table does not know comes
back in Japanese. So the layer reports it:

```python
photoloset.i18n.missing(result)    # every Japanese string with no translation
photoloset.i18n.coverage(result)   # (translated, total)
```

If `missing()` returns anything, the English is incomplete at exactly those
strings and you can see which. Measured across every output path the engine
has — ledger, worklist, tech pack, measurement sheet, contested measurements,
draft, marks, build, drape, all five refusal verdicts and the SVG —
**0 untranslated**.

For the SVG there is one more thing to know. `to_svg` hard-wraps its notes
across several `<text>` elements, so `i18n.svg` rejoins each paragraph,
translates it as one, and re-wraps it for English, which needs about twice the
characters per line at the same font size. That can produce more lines than the
Japanese had, so the text below shifts and the canvas grows (210x220 becomes
210x238 on the demo coat). Every coordinate belonging to the pattern itself is
byte-identical.

---

## The five states

Every claim the tool holds is in exactly one of these. The state is the point
of the whole design — it is what stops a guess from reaching a cutting table.

| State | Means | Can it reach a pattern? |
| --- | --- | --- |
| `PROPOSED` | Something suggested it — a model, a person, a catalogue | **No** |
| `OBSERVED` | A named person adopted it, and the source is openable | Yes |
| `CONTESTED` | Two readings of the same thing disagree | **No** |
| `INFERRED` | Derived from other entries, not seen directly | Marked, never silent |
| `UNKNOWN_NOT_OBSERVED` | Nobody has looked yet | **No**, and it says what would close it |

A refusal is a normal return value here, not an exception and not an error
code. It carries a `how_to_close` field describing the action that would
resolve it.

---

## 1. Record what a model proposed

```python
from photoloset import Ledger

ledger = Ledger(title="Black Coat")
ledger.propose("collar", "shape", "notched lapel",
               source="vision model, frame t001.89",
               ref_path="frames/t001.89.jpg", ref_mark="t001.89")
ledger.propose("pocket", "existence", "flap pocket",
               source="vision model, frame t001.89",
               ref_path="frames/t001.89.jpg", ref_mark="t001.89")

ledger.state("collar", "shape")["state"]
# 'PROPOSED'
```

`ref_path` and `ref_mark` are the frame the claim came from. They are what makes
the claim checkable later: the ledger reports whether the reference still
resolves, so a proposal whose evidence has been deleted stops looking like a
proposal whose evidence is intact.

Ten confident proposals from a model are ten proposals and zero facts. The
drafting step never reads `PROPOSED` entries.

---

## 2. Adopt it, by name

```python
ledger.adopt("collar", "shape", "notched lapel", by="")
# ValueError: UNKNOWN_NO_ADOPTER — an adoption nobody can be traced to
#             erases responsibility for the mistake

entry = ledger.adopt("collar", "shape", "notched lapel", by="Kodai Motonishi")
ledger.state("collar", "shape")["state"]
# 'OBSERVED'
```

Anonymous adoption raises. This is deliberate and it is the single line that
separates this tool from one that autocompletes garments: a fact has an owner,
and the owner is a person, not a model.

Two independent readings of *different* frames agreeing is corroboration, and
`state()` reports how many agreed. It is not proof — both frames stay openable,
so you can go and look.

---

## 3. See what is still missing

```python
work = ledger.worklist()
len(work)
# 22

work[0]
# {'part': 'collar', 'aspect': 'material',
#  'state': 'UNKNOWN_NOT_OBSERVED',
#  'how_to_close': '...find a shot where the collar material is visible...'}
```

The worklist is the tool's own to-do list. Twenty-two unknowns on a coat is not
a failure report; it is an accurate description of how much of a garment one
clip actually shows you.

---

## 4. Measure the real garment

```python
from photoloset import Measures

ms = Measures()
for spot, value in [("body_length", 112.0), ("chest", 108.0),
                    ("shoulder", 46.0), ("sleeve_length", 63.0)]:
    ms.measured(spot, value, "cm",
                source="tape measure, reference coat laid flat",
                by="Kodai Motonishi")
```

**These do not come out of the footage.** A frame has no scale in it, so the
tool refuses to derive a dimension from one. A person measures a real reference
garment with a tape and types the numbers in, with the basis recorded.

Units are converted through an explicit table (`cm`, `mm`, `inch`, `in`). An
unrecognised unit does **not** default to centimetres — the measurement drops
to *missing*, because assuming 1.0 is the quietest way to be wrong. A pattern
entered in inches and drafted as centimetres turns 6027 cm² into 511 cm² with
no warning at all, which is exactly the bug this table exists to prevent.

`draft()` needs `body_length`, `chest` and `shoulder`. `sleeve_length` is
needed only if you want a sleeve; without it the sleeve is reported as missing
rather than invented.

---

## 5. When two measurements disagree

```python
ms.measured("sleeve_length", 46.0, "cm",
            source="tape measure, measured again", by="Kodai Motonishi")

ms.state("sleeve_length")
# {'spot': 'sleeve_length',
#  'state': 'CONTESTED_MEASUREMENT',
#  'sides': [{'value': 63.0, 'unit': 'cm', 'source': ..., 'by': ...},
#            {'value': 46.0, 'unit': 'cm', 'source': ..., 'by': ...}],
#  'tolerance_cm': 0.5,
#  'how_to_close': '...measure the sleeve again and decide which is right...'}
```

Both sides are returned. Neither is chosen for you, and the first one entered
does not silently win. Resolve it by removing the wrong entry:

```python
ms.entries = [m for m in ms.entries
              if not (m.spot == "sleeve_length" and m.value == 46.0)]
```

The tolerance is 0.5 cm — two tape readings of the same spot that differ by
less than that are treated as the same measurement, not as a conflict.

---

## 6. Draft the pattern

```python
from photoloset import garment_pattern

draft = garment_pattern.draft(ms)

draft["verdict"]          # 'ANSWER'
draft["total_area_cm2"]   # 7306.1
[p["name"] for p in draft["pieces"]]
# ['後身頃', '前身頃', '袖']   (back bodice, front bodice, sleeve)
len(draft["formulas"])    # 17
```

All seventeen drafting formulas are in the output, including the six constants
that decide the armhole and cap curves. Nothing that determines the shape lives
only in the source, so a pattern-maker who disagrees with the block can see
exactly what to disagree with.

Read `draft["seam_checks"]` carefully:

```python
for c in draft["seam_checks"]:
    print(c["label"], c["difference"], c.get("structural"))
# 肩線          0.0   True
# 脇線          0.0   True
# 袖山と袖ぐり   2.0   True
```

`structural: True` means the check **cannot fail** — it compares a point list
to itself, so the zero difference proves nothing. The tool detects that by
comparing the point lists rather than by a hardcoded label, and reports it
instead of presenting a tautology as a verification. If the block is ever
changed so front and back carry different curves, these become real tests again
on their own.

> This block is the tool's own simplification. It is **not** Bunka, not Dorémé,
> and not any other published drafting system, and it does not claim to be.

---

## 7. Notches, seam allowance, grain

```python
from photoloset import garment_marks

marks = garment_marks.apply(draft)

sum(len(v) for v in marks["notches"].values())   # 16
len(marks["notch_pairs"])                        # 8
len(marks["notch_unpaired"])                     # 0
len(marks["grain"])                              # 3
```

Notches come in pairs by construction — a notch on one piece that has no
partner on the piece it is sewn to is reported as unpaired rather than drawn.
They are placed at 2.5 mm deep, which is their real size: almost invisible on
screen, correct on paper.

Seam allowance per edge, with the imperial equivalent printed:

```python
garment_marks.SEAM_ALLOWANCE
# {'肩線':   (1.27, '1/2"', ...),   shoulder
#  '袖ぐり': (0.95, '3/8"', ...),   armhole
#  '衿ぐり': (0.64, '1/4"', ...),   neckline
#  '裾':     (2.54, '1"',   ...),   hem
#  '中心線': (0.0,  '—',    ...)}   centre fold — no allowance, it is a fold
```

Allowance is never stored as a value on the piece. It is the geometric offset
between the cut line and the sewing line, so the two cannot drift apart. The
offset is mitre-limited, and an offset that would run *inward* — which would
silently shrink the garment — is caught and reported rather than drawn.

---

## 8. Sew it and let it fall

```python
from photoloset import garment_sew

material = {"verdict": "ANSWER", "fabric": "wool melton",
            "gsm": 420.0, "thickness": 0.18, "stiffness": 20.0,
            "source": "supplier spec sheet"}

built = garment_sew.build(draft, marks=marks)
# 303 points, 954 edges, 5 seams

drape = garment_sew.sew_and_drape(built, material, iterations=2000,
                                  stitch_k=material["stiffness"] * 64.0)

drape["seam_gap"]
# {'worst': 0.0614, 'over_tolerance': 0, 'stitches': 41, 'closed': True}
```

**About `stitch_k`.** The engine default is `STITCH_STIFFNESS_RATIO = 16`,
meaning thread sixteen times stiffer than cloth. Measured on this three-piece
coat that is not enough — the worst stitch stays 0.91 cm open with 15 of 41
past the 1 mm tolerance. At 64× it closes to 0.06 cm with none over. Pass it
explicitly rather than accepting a seam the tool itself reports as open, and
always read `seam_gap`: `closed` is judged by the **worst** stitch, never the
mean, because a mean hides exactly the failure the check exists to catch.

The solve stops when the seams are within tolerance and have stopped moving,
or when it hits the cap — `stopped_because` tells you which. Note that running
it *longer* can make the gap worse rather than better, because gravity is
winning against the stitch springs; see the limits section in the README.

Order invariance is guaranteed by construction: the solver uses a Jacobi
update, so the answer does not depend on the order vertices are visited. The
measured difference is exactly 0.000000, and for that reason the tool labels the
order check `structural` and notes that passing it confirms nothing. A property
proved by construction must not be reported as a test that passed.

The material dict needs `fabric`, `gsm`, `thickness` and `stiffness`, plus
`verdict: "ANSWER"`. Without real fabric properties nothing is draped:

```python
from photoloset import garment_drape
garment_drape.material_from(None, "cupro")
# {'verdict': 'UNKNOWN_NO_MATERIAL', 'fabric': 'cupro',
#  'missing': ['weight', 'thickness'],
#  'how_to_close': '...supply cupro weight and thickness with a source...'}
```

---

## 9. Export at 1:1 and print it

```python
svg = garment_pattern.to_svg(marks)     # pass marks, not draft, for all 4 layers
open("coat.svg", "w").write(svg)
```

Four layers: cut line, notch, grain, sewing line. The `viewBox` is in
centimetres at 1:1, so printing at 100% scale — no "fit to page" — gives a
pattern you can lay on cloth. Check the scale with a ruler on the printed sheet
before you cut anything.

`to_svg(draft)` gives you the pieces only. `to_svg(marks)` gives you the pieces
plus the marks, which is almost always what you want.

> Layer numbers are an internal naming convention. ASTM D6673-10 was withdrawn
> in January 2019 with no replacement, so this tool does not claim conformance.

---

## Reading a refusal

A refusal is a dict, not an exception (with one exception: anonymous adoption
raises, because there is no sensible value to return). Every refusal has a
verdict beginning `UNKNOWN_` or `CONTESTED_`, and a `how_to_close`.

| Verdict | What it means | What closes it |
| --- | --- | --- |
| `CONTESTED_MEASUREMENT` | Two readings of one spot differ by more than 0.5 cm | Measure again, drop the wrong one |
| `UNKNOWN_NOT_OBSERVED` | Nobody has looked at this aspect | Find a shot, or ask the client |
| `UNKNOWN_NO_MATERIAL` | No fabric weight or thickness | Supply them with a source |
| `UNKNOWN_PIECE_MISSING` | A piece it was asked to sew was never drafted | Supply the measurement that piece needs |
| `UNKNOWN_SEAM_ALLOWANCE_WENT_INWARD` | The offset would shrink the piece | Fix the outline direction |
| `UNKNOWN_NO_ADOPTER` | Adoption without a name (**raises**) | Pass `by="..."` |
| `ORDER_DEPENDENT` / `LOCAL_MINIMUM` | The drape did not settle to one answer | Nothing you can pass — the shape is genuinely not determined |

The last row is the important one. When a sleeve is sewn into a tube it can
rotate about its own axis, so different starting positions land on different
shapes — measured disagreement 11.4 cm on this coat. The tool names the piece
and returns nothing rather than picking one. The same garment without a sleeve
settles to 0.9 cm and returns its shape: it gives you what it can determine and
names what it cannot.

---

## Module map

| Module | What lives there |
| --- | --- |
| `garment` | `Ledger`, `Entry`, the five states, worklist, tech pack |
| `garment_measure` | `Measures`, `Measure`, unit handling, conflict detection |
| `garment_pattern` | `draft`, `to_svg`, the 17 formulas, seam checks |
| `garment_marks` | notches, seam allowance offsets, grain lines |
| `garment_sew` | `build`, `sew_and_drape`, `validate`, seam definitions |
| `garment_drape` | the mass-spring solver and its five checks |
| `garment_draw` | ledger-to-drawing |
| `garment_rights` | provenance and derivation records |
| `garment_app` | the browser application, standard library only |
| `garment_body` | the reference body, grading and ease |
| `garment_solid` | the proportion block — not a fit simulation |
| `mcp` | an MCP server over stdio, 42 tools, standard library only |
| `i18n` | English output, and the report of what it could not translate |
| `__main__` | `python3 -m photoloset` |

---

## Things that will bite you

1. **The engine speaks Japanese by default.** `'後身頃'`, `'前身頃'`, `'袖'` are
   back bodice, front bodice, sleeve. Call `photoloset.set_language("en")` and
   they come back in English — and check `i18n.missing()` if you are relying on
   it, because an unknown string falls through untranslated rather than
   guessing.
2. **`to_svg(draft)` silently omits the marks.** Pass `marks`.
3. **The default `stitch_k` does not close this garment.** See step 8.
4. **`closed` is not `verdict`.** A drape can return `ANSWER` and still report
   `closed: False`. Read `seam_gap` every time.
5. **The draped shape is generated, not observed.** It cannot be used as the
   source of an entry, and the tool marks its own SVG output as generated.
6. **There is no amendment path.** Once a fact is adopted, there is currently no
   supported way to correct it in place. Rebuild the ledger.
