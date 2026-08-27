<h1 align="center">photoloset</h1>

<p align="center">
  <b>A garment engine built to refuse. Handed a shape it cannot support, it
  says so by name — 152 distinct refusal codes — instead of guessing, and
  the 13,231 lines that check the 17,599-line engine come to 75% of its
  size, not a footnote.</b>
</p>

<p align="center">
  <a href="LICENSE"><img alt="MIT" src="https://img.shields.io/badge/license-MIT-black.svg"></a>
  <img alt="Python 3.9+" src="https://img.shields.io/badge/python-3.9%2B-black.svg">
  <img alt="no dependencies" src="https://img.shields.io/badge/dependencies-none-black.svg">
  <img alt="English and Japanese" src="https://img.shields.io/badge/output-English%20%2F%20%E6%97%A5%E6%9C%AC%E8%AA%9E-black.svg">
  <a href="https://github.com/Ag3497120/photoloset/actions/workflows/ci.yml"><img alt="checks" src="https://github.com/Ag3497120/photoloset/actions/workflows/ci.yml/badge.svg"></a>
</p>

---

## This is not a photo-to-pattern tool

If you came here for a photo in and a sewing pattern out — an anime dress,
a screenshot, any garment nobody has measured — this is not that tool, and
saying so first is the point. A fresh interpreter finds this, every run:

```bash
python3 -c "from photoloset import resemble; print(resemble.backends())"
# []
```

**0 image-similarity backends, 0 segmenters, 0 sewing-method corpora.**
That is measured by the check suite on every push, not a claim written once
in this file (`docs/architecture.md` → "No models are shipped"). Entering
the "AI turns a photo into a pattern" category while unable to do the thing
that category promises is a worse position than not entering it — so this
page does not open with a photo becoming a pattern.

**What this actually is: a deterministic garment engine that refuses by
default.** A claim it cannot support does not become a weaker claim — it
becomes a typed refusal naming what would close it, and there are **152 of
them** in the engine today:

```bash
grep -rhoE '"UNKNOWN_[A-Z0-9_]+"' photoloset/*.py | sort -u | wc -l
# 152
```

One refusal is the shape of the whole project. Hand it a shape a named
person has already approved and ask for a sewing method, and it does not
answer with an empty list — an empty list says "there are no methods," and
the true sentence is "nothing was asked." It answers this instead:

```
UNKNOWN_NO_SEWING_CORPUS
  naming: SewFactory (Sewformer, SIGGRAPH Asia 2023),
          GarmentCodeData (ECCV 2024),
          GarmentCode (the parametric program, as a retrieval target)
  entry point: sewing_search.register_corpus()
```

(`photoloset/sewing_search.py`. The same door refuses a corpus declaring
`modality="image_embedding"` outright, and refuses two corpora that agree
while sharing a generator — GarmentCodeData is generated FROM GarmentCode —
as `UNKNOWN_SHARED_LINEAGE` rather than counting them as independent.)

Making sure every one of those 152 refusals actually fires, and keeps
firing as the code under it changes, is most of the work in this
repository — more of it than the garment code itself:

```bash
python3 tests/run_checks.py
# ... 196 checks ran, 196 pinned by name, 3 retired on the record
# all checks passed
```

```bash
python3 -c "
import sys; sys.path.insert(0, 'tests')
import falsifiers as f
print(len(f.MUTATIONS) + len(f.LOOP_MUTATIONS) + len(f.WHOLE_SUITE))"
# 207
```

Each of those 207 is a mutation of the implementation that a named check is
required to catch, by turning red — a mutation that leaves everything green
is a MISS, and the harness scores it as one rather than as a pass. The
verification code is **13,231 lines** across 5 files; the engine it checks
is **17,599 lines** across **40** standard-library-only modules —
verification at **75%** of the engine's size:

```bash
wc -l photoloset/*.py                                          # 17599, 40 files
wc -l tests/dress_digest.py tests/unfalsifiable.py \
      tests/falsifiers.py tests/run_checks.py tests/coat_digest.py  # 13231
```

Deeper machinery — the falsification harness, the scanner that reads
checks for whether they could ever fail, what all of this does not
claim — is in **[docs/verification.md](docs/verification.md)**. The
store's address space and the gate in front of sewing-method search are in
**[docs/architecture.md](docs/architecture.md)**.

<br>

## What it cannot do — before you look at anything else

| It does | It does not |
| --- | --- |
| Draft two garments from tape measurements: a 3-piece coat, and a 7-cut-piece cape dress with a collar | Handle any *other* garment, or infer a garment type — each block is hand-built; there is no generic type system |
| Print all drafting formulas so you can argue with them | Implement a published system (Bunka, Dorémé, …) |
| Place notches, seam allowance and grain lines | Darts beyond a fixed set, pleats, gathers, facings, linings |
| Detect two measurements of the same spot disagreeing | Decide which of them is right |
| Sew the pieces and drape them under gravity | Model collision or friction — 101 of the coat's 297 draped points land *inside* the body, worst −14.4 cm, because nothing stops them |
| Convert cm / mm / inch, and refuse unknown units | Guess a unit that was not given, or reproduce decoration — ever |
| Export a plain DXF R12 a real CAD application opens | Claim DXF-AAMA / ASTM D6673 conformance (withdrawn 2019, no replacement) |
| Say `UNKNOWN_NO_SEWING_CORPUS` and name what would close it | Search a sewing-method corpus — none is registered; see above |
| Identify a garment from footage, per part, once a corpus and segmenter exist | Do any of that *today* — 0 backends, 0 segmenters, 0 corpora, measured |

**Measured limits worth knowing before you trust a number:**

- **No corpus, no segmenter, no similarity backend.** All three are 0 on a
  fresh import, checked by the suite, not asserted here. Nothing in this
  repository can turn a photo of a garment it has not been measured against
  into a pattern — including, and especially, an anime dress, a stylised
  drawing, or footage with no reference garment on hand.
- **Decoration is never reproduced**, now or in any planned version. Prints,
  embroidery, appliqué — none of it enters the geometry.
- **Fit is a distance map, not comfort.** The drape has no collision and no
  friction, so "fit" here means how far a draped point sits from the body's
  surface, not whether the garment feels right. On the reference coat that
  distance is negative — inside the body — for 101 of 297 points, worst
  −14.4256 cm, measured by `python3 tests/run_checks.py` and reported
  against the project's own interest, not hidden.
- **Two garments exist, both from measurements, neither from a photo.** The
  coat (3 pieces, one clip, one lighting condition) and a cape dress (5
  parts including a collar, 7 cut pieces) are both hard-coded blocks
  drafted from a tape measure. There is still no notion of a garment
  *type* — adding a third garment is a new block with new formulas, not a
  parameter change.
- The default stitch stiffness (16× the cloth) **does not close the coat**.
  Measured: worst stitch 0.9154 cm open, 15 of 41 stitches past the 1 mm
  tolerance. At 64× it closes at 0.0614 cm with 0 over tolerance
  (`python3 tests/coat_digest.py --check`). The example passes `stitch_k`
  explicitly rather than accepting a seam the tool itself reports as open.
- The drape is a **generated shape**. It is not evidence and cannot be
  cited as an observation. The tool says so in its own output, not only
  here.
- English output is a **translation layer over the engine**, not a rewrite
  of it, because the drafting code is shared with a larger project. A
  string the table does not know comes back in Japanese, and
  `i18n.missing(result)` lists exactly which — measured at **0 untranslated**
  across the reader and refusal paths the suite sweeps, with the residue
  that is deliberately NOT translated (store addresses, whole documents,
  prompt-bank instructions to a model) classified by name rather than
  waved at. Full accounting: **[docs/USAGE.md](docs/USAGE.md)**.

<br>

## The DXF is the part you do not have to take our word for

Everything above is self-reported. This is not: the pattern export is a
plain-text DXF R12 file, and it opens in **QCAD** — an Apple-notarized,
independently built CAD application (RibbonSoft GmbH, no relation to this
project, installs with no admin password; the extraction tool used below
ships in every edition, including the free, open-source Community Edition)
— not just a Python parser that happens to agree with itself.

That distinction found a real bug. Every Japanese piece name used to draw
as a literal **"?"** in QCAD, because no `STYLE` table told the renderer
which font to use — and a *parser* could not have caught it: `ezdxf`
decoded the same bytes into the correct string with or without the table,
because a parser decodes bytes and a CAD application draws glyphs. Only
the renderer can be missing a kanji glyph. One independent parser is not
one independent application, and that is the difference, measured.

Re-derive it yourself, from the command line, no GUI needed — this is
exactly what was run to write this section, today:

```bash
python3 -c "
from photoloset import Measures, dxf
ms = Measures()
for spot, value in [('body_length', 112.0), ('chest', 108.0),
                    ('shoulder', 46.0), ('sleeve_length', 63.0)]:
    ms.measured(spot, value, 'cm', source='tape', by='you')
dxf.save(ms, 'coat.dxf')"

/Applications/QCAD.app/Contents/Resources/dwg2csv -t Text -p Text coat.dxf
#  → 後身頃 / 前身頃 / 袖   (read correctly — a STYLE table now names a
#     font, MS-Gothic, with the glyphs the implicit default lacked)

/Applications/QCAD.app/Contents/Resources/dwg2csv -t Polyline -p Length -p Layer coat.dxf
#  → 6 closed polylines (3 SEWING_LINE + 3 CUT_LINE). 後身頃's
#     SEWING_LINE measures 269.131937646584 cm — matching an independent
#     perimeter recomputation from the same file's vertices to six
#     decimal places.

python3 -c "import ezdxf; ezdxf.readfile('coat.dxf'); print('strict, no exception')"
# strict, no exception — and ezdxf's own recover+audit reports 0 errors,
# 0 fixes: the file was never malformed, only under-declared for a
# renderer.
```

The same check on the second garment — a five-part cape dress with a
collar, composed today — reads **7** piece names
(`前身頃 後身頃 スカート前 スカート後 袖(左) ケープ 衿`) and **14**
closed polylines, ケープ's `CUT_LINE` at exactly 174.761110623154 cm.
**Both of those counts are one pair short of what an older description of
this dress states (6 names, 12 polylines)** — that description predates
the collar (衿) being merged into the dress; `tests/dress_digest.py
--check` pins the current, 7-piece geometry (digest
`493f74a274d4dac5a97c0bdf57b20037`) and reports it unmoved on this tree.
If you reproduce a 6/12 dress, you are looking at an older commit.

The full version of this section — the exact bug reproduced from a clean
DXF, before/after renders, the complete perimeter table, ezdxf's audit, and
what this project measured about itself rather than had an outsider confirm
— is **[docs/evidence.md](docs/evidence.md)**.

<br>

## What it draws, step by step

<p align="center">
  <img src="docs/hero.gif" alt="photoloset turning a coat from film footage into a sewable pattern" width="660">
</p>

Most garment AI tools answer every question. This one is built the other way
round: it will tell you the pattern it can draft, and it will tell you, by
name, what it was never given. A guess that reaches a cutting table costs
fabric, so nothing that was not measured is allowed to look like something
that was.

The pipeline below is the whole tool for the first garment. Each step can
refuse, and a refusal says what would close it.

<br>

<table>
<tr>
<td width="55%"><img src="docs/frames/01-footage.jpg" alt="Eight frames cut from six seconds of footage"></td>
<td width="45%" valign="top">
<h3>1 &nbsp;·&nbsp; Footage</h3>
<p><b>What happens.</b> A clip goes in. Frames are cut at fixed timestamps and
stored. From here on, every claim about this garment has to point back at one
of them.</p>
<p><b>Under the hood.</b> Frames are held as <code>Source</code> and
<code>Clip</code> records carrying the file, the byte count and the mark in
the clip. A claim that cannot name a frame has nowhere to live.</p>
</td>
</tr>
</table>

<p align="center"><sub>│</sub><br><sub>▼</sub></p>

<table>
<tr>
<td width="55%"><img src="docs/frames/02-observe.jpg" alt="Ten proposals and zero facts"></td>
<td width="45%" valign="top">
<h3>2 &nbsp;·&nbsp; Observe</h3>
<p><b>What happens.</b> A vision model reads one frame and proposes ten things.
The tool writes down ten proposals and zero facts.</p>
<p><b>Under the hood.</b> Model output lands as <code>PROPOSED</code> entries
tagged with the model id and the frame. The drafting step reads only
<code>OBSERVED</code>, so a proposal cannot reach a pattern no matter how
confident it is.</p>
</td>
</tr>
</table>

<p align="center"><sub>│</sub><br><sub>▼</sub></p>

<table>
<tr>
<td width="55%"><img src="docs/frames/03-adopt.jpg" alt="Proposed, a person adopts, observed"></td>
<td width="45%" valign="top">
<h3>3 &nbsp;·&nbsp; Adopt</h3>
<p><b>What happens.</b> A proposal becomes a fact only when a person adopts it,
by name.</p>
<p><b>Under the hood.</b> <code>Entry.adopted_by</code> is required for
<code>kind="observed"</code>; anonymous adoption is refused at the ledger.
Two independent readings of different frames agreeing is corroboration, not
proof — both frames stay openable, and you can go look.</p>
</td>
</tr>
</table>

<p align="center"><sub>│</sub><br><sub>▼</sub></p>

<table>
<tr>
<td width="55%"><img src="docs/frames/04-measure.jpg" alt="Footage cannot be measured"></td>
<td width="45%" valign="top">
<h3>4 &nbsp;·&nbsp; Measure</h3>
<p><b>What happens.</b> Footage cannot be measured. The numbers come off a
tape, on a real garment, typed in by a person.</p>
<p><b>Under the hood.</b> A <code>Measure</code> carries value, unit, basis,
source and <code>by</code>. Units are converted through an explicit table; an
unrecognised unit drops to <i>missing</i> rather than being assumed to be
centimetres. Assuming 1.0 is the quietest way to be wrong.</p>
</td>
</tr>
</table>

<p align="center"><sub>│</sub><br><sub>▼</sub></p>

<table>
<tr>
<td width="55%"><img src="docs/frames/05-sew.jpg" alt="Four measured numbers become a pattern, and it is sewn"></td>
<td width="45%" valign="top">
<h3>5 &nbsp;·&nbsp; Draft &amp; sew</h3>
<p><b>What happens.</b> Four measured numbers become three pieces. The pieces
get notches, seam allowance and a grain line, then they are sewn and the cloth
is allowed to fall.</p>
<p><b>Under the hood.</b> Seventeen drafting formulas are printed in the
output — no shape constant is left hidden in the source. The cloth is a
mass-spring mesh minimised by gradient descent with a <b>Jacobi</b> update, so
the answer does not depend on the order vertices are visited: that is true by
construction, and the tool labels the order check <code>structural</code>
rather than reporting it as a test that passed.</p>
</td>
</tr>
</table>

<p align="center"><sub>│</sub><br><sub>▼</sub></p>

<table>
<tr>
<td width="55%"><img src="docs/frames/06-refuse.jpg" alt="46.0 cm or 63.0 cm, contested"></td>
<td width="45%" valign="top">
<h3>6 &nbsp;·&nbsp; Refuse</h3>
<p><b>What happens.</b> Forty-six centimetres, or sixty-three. It can draft a
sleeve from either. It will not draft one from two, and it does not quietly
pick the first.</p>
<p><b>Under the hood.</b> Two readings of the same spot differing by more than
0.5&nbsp;cm become <code>CONTESTED_MEASUREMENT</code>, and the refusal carries a
<code>how_to_close</code> field. The same discipline covers shape: a sleeve
sewn into a tube can rotate about its axis, so multiple starts disagree, and
the refusal names the piece rather than returning one of the answers.</p>
</td>
</tr>
</table>

<p align="center"><sub>│</sub><br><sub>▼</sub></p>

<table>
<tr>
<td width="55%"><img src="docs/frames/07-ledger.jpg" alt="The ledger, ending in UNKNOWN_PIECE_MISSING"></td>
<td width="45%" valign="top">
<h3>7 &nbsp;·&nbsp; Ledger</h3>
<p><b>What happens.</b> Every claim about the garment sits on one page with its
state, and the page ends with the thing that was never observed.</p>
<p><b>Under the hood.</b> Five states — <code>OBSERVED</code>,
<code>CONTESTED</code>, <code>INFERRED</code>, <code>PROPOSED</code>,
<code>UNKNOWN_NOT_OBSERVED</code>. An <code>UNKNOWN_*</code> is a first-class
result, not an error: it is the tool reporting the shape of its own ignorance.</p>
</td>
</tr>
</table>

<br>

## What this project actually is

The demo is a coat becoming a pattern. The engineering is somewhere else.

A conventional agent pipeline decides, passes the decision on, decides again,
and produces a finished thing. Nothing in that chain separates *measured* from
*guessed*, so the output looks right and may be wrong in ways nobody can point
at. At the end of this particular chain, somebody cuts cloth.

photoloset puts a deterministic layer between every pair of stages. A claim
that cannot be supported does not become a weaker claim — it becomes a **typed
refusal** carrying what somebody would have to do to earn the answer. There
are 152 of them (re-derivation and command above).

The consequence is that most of the work here is not the garment code:

| | lines |
|---|---|
| engine | 17,599 |
| verification | 13,231 |

The verification is 75% the size of the thing it verifies, and it does not
only ask whether the checks pass. It mutates the implementation and requires
each check to **actually go red** — because a check that cannot fail is a
defect that reads as a pass forever.

```
196  checks, all passing
207  falsification mutations, all required to go red, 0 MISS
152  distinct typed refusals
 40  engine modules, standard library only
```

The scanner that reads checks for whether they could ever fail
(`python3 tests/unfalsifiable.py`) currently names 10 hits against the
current check set — 4 it calls real, 6 borderline — each argued by name in
the source rather than swept under a passing total; a falsifier that
changed nothing has been caught scored MISS instead of green; and a
collision between two features has surfaced as a refusal rather than as a
wrong pattern months later. Details, with the actual incidents, in
`docs/verification.md`.

- **[docs/verification.md](docs/verification.md)** — how falsification works
  here, three things it caught, and why this is slower on purpose
- **[docs/architecture.md](docs/architecture.md)** — the store, the two
  address spaces, the gate

<br>

## The pattern it produces

<p align="center">
  <img src="docs/pattern.svg" alt="Three pattern pieces with cut line, sewing line, notches and grain" width="760">
</p>

Drawn at 1:1 in centimetres, on four layers: cut line, notch, grain and sewing
line. Seam allowance is not a stored number — it is the offset between the cut
line and the sewing line, so the two can never disagree. Notches are drawn at
their real 2.5&nbsp;mm, which means they are almost invisible on screen and
correct on paper.

> Layer numbers are an internal naming convention. ASTM D6673-10 was withdrawn
> in January 2019 with no replacement, so this tool does not claim conformance
> to it.

<br>

## The translation layer, measured rather than asserted

(The what-it-does/does-not table and the headline measured limits moved to
the top of this page. This is the one piece of that section detailed enough
to deserve its own room.)

English output is a **translation layer over the engine**, not a rewrite of
  it, because the drafting code is shared with a larger project and two copies
  would drift. A string the table does not know comes back in Japanese — and
  `i18n.missing(result)` lists exactly which, so the gap is visible rather than
  papered over. Measured across the **51 output paths the suite sweeps** —
  ledger, worklist, tech pack, measurements, draft, marks, sew, drape, the SVG,
  the skirt and composed garments, the look loop's retrieval, construction,
  confirmation, approval and sewing-method paths, and every refusal the cross
  store, the parts library, the zone catalogue, the measurement writer, the
  prompt parser and the ledger's own adoption door can return:
  **0 untranslated**. The three look-loop modules answer in English, like
  `mcp.py`, the boundary they are read through; they are swept as such rather
  than exempted.

  **What that number does not cover — measured by a check, not by a
  sentence.** The claim above used to say "every output path the engine has",
  and when the block/cross/parts/zones/prompts surface became load-bearing
  that stopped being true. The scope sentence then carried a hand-written
  number (67, then 42) that nothing re-measured, so it drifted the same way
  the first claim had: an independent sweep found 43, not 42, and three of
  the strings it found were prose rather than the addresses the sentence
  described. Turning that sweep into a check found a fourth.

  So the wide sweep is a check now (`the untranslated residue is measured`):
  **55 reader and refusal paths** across block, cross, parts, prompts, zones
  and compose leave **39** untranslated strings, and every one of them is
  classified —

  - **32 store addresses** — core names and seat keys (`formula:袖山の高さ`,
    `block:coat/piece:袖`, `seam:…`, `placement:…`) in `to_dict()`,
    `write_plan()`, `seats()` and `seam_edges()`. These are the store's
    coordinates, not prose; translating them would make two languages address
    different seats.
  - **2 whole Japanese documents** — the coat's own `dump()`, and the JSON
    schema the prompt bank asks a model to fill.
  - **5 further prompt-bank strings** — `prompts.for_model()` returns the
    instruction sent to a vision model, in the language the profile was
    written in. It is input to a model, not output to a reader.

  Anything outside those three groups turns the check red, which is what
  caught the four that were prose after all: the sleeve's placement reason,
  two settings reasons and one `how_to_close`. They are translated.

  `python3 tests/run_checks.py` pins every number in this section — the 51
  paths and their 0, and the 55 paths, the 39 and each group — and
  `tests/unfalsifiable.py` makes sure the checks that measure them cannot pass
  by covering nothing.

<br>

## Install and run

No dependencies. Python 3.9 or newer.

```bash
git clone https://github.com/Ag3497120/photoloset.git
cd photoloset
python3 -m photoloset --lang en
```

That is the application: a local page on `127.0.0.1:8910`, stdlib only, no
build step and no framework. It shows the ledger as a garment — colour is
state, clicking a part opens the structure inspector on the right, proposals
carry an adopt button that demands a name, and the tech pack prints. Nothing
leaves the machine unless you pass `--lan`, which opens it to your own network
and says so when it starts.

<p align="center">
  <img src="docs/frames/03-adopt.jpg" alt="The ledger as a garment, with a proposal waiting to be adopted" width="720">
</p>

### The macOS app in the film

The frames throughout this README come from **`app/`**, which is in this
repository. It is a macOS agent IDE, it opens on this workbench, and it is
what the demo shows.

```bash
open app/Verantyx.xcodeproj      # ⌘R, or:
cd app && xcodebuild -scheme Verantyx -configuration Debug build
```

Building the workbench on an agent IDE rather than as a purpose-built garment
app is deliberate. It arrives carrying the parts a garment tool would otherwise
have to grow itself: model clients for the vision step, an MCP host, a file
tree, a console. What this package adds is the half that has to be exact.

**It runs on this package's engine.** The app used to embed a 78 MB frozen
helper for the same 48 tools; it now launches `python3 -m photoloset.mcp`
instead, found in its own bundle Resources, where a build phase copies the
250 KB Python package. So the two halves are one program, and the tool surface
is the seam between them.

Three things did not come across, and it is worth knowing why:

| | |
| --- | --- |
| the 78 MB `vera-memory` binary | replaced by `photoloset.mcp` |
| a 75 MB backup of it | a stale copy of the same thing |
| `verantyx-browser/` | a separate Rust project — and the source of four paths with colons in their names, which cannot be checked out on Windows at all |

Five of the 48 tools answer `UNKNOWN_NOT_IN_THIS_BUILD` rather than working:
`garment_cross` and the four `fabric_*` tools need a coordinate memory and its
language engine, about 15,700 lines that are not part of this package. Fabric
properties are read from `~/.photoloset/fabrics.json` instead.

To see the whole pipeline run end to end, with no app at all:

```bash
python3 examples/black_coat.py
```

Or drive it from any agent, which is what the app does:

```bash
python3 -m photoloset.mcp        # 48 tools over stdio, standard library only
```

## Thirty seconds of it

```python
import photoloset
photoloset.set_language("en")     # or leave it and get the engine's Japanese

from photoloset import Measure, Measures
from photoloset import garment_marks, garment_pattern, garment_sew

ms = Measures()
for spot, value in [("body_length", 112.0), ("chest", 108.0),
                    ("shoulder", 46.0), ("sleeve_length", 63.0)]:
    ms.entries.append(Measure(
        spot=spot, kind="measured", value=value, unit="cm",
        basis="reference coat, laid flat",
        source="tape measure", by="your name here"))

draft = garment_pattern.draft(ms)      # verdict ANSWER, 3 pieces, 7306.1 cm2
marks = garment_marks.apply(draft)     # 16 notches, 8 paired, 3 grain lines
open("coat.svg", "w").write(garment_pattern.to_svg(marks))
```

Add a second, conflicting reading of the same spot and the tool stops:

```python
ms.entries.append(Measure(spot="sleeve_length", kind="measured", value=46.0,
                          unit="cm", basis="the real coat, measured again",
                          source="tape measure", by="your name here"))

ms.state("sleeve_length")
# {'state': 'CONTESTED_MEASUREMENT',
#  'sides': [{'value': 63.0, ...}, {'value': 46.0, ...}],
#  'tolerance_cm': 0.5,
#  'how_to_close': 'measure the sleeve again and decide which one is right'}
```

**Full walkthrough: [docs/USAGE.md](docs/USAGE.md).**

### Language

```python
import photoloset
photoloset.set_language("en")        # every entry point returns English
photoloset.i18n.missing(result)      # what it could not translate — should be []
photoloset.i18n.coverage(result)     # (translated, total)
```

`photoloset.en(value)` translates a single value without changing the default,
and `i18n.svg(document)` translates a pattern SVG — labels and notes only, with
the notes re-wrapped for English line lengths and the canvas grown to fit.
Every coordinate is left exactly as the engine emitted it.

<br>

## One photograph, and the gate in front of the sewing methods

A single front-facing image can say a garment RESEMBLES A and B. It can also
mislead, and from the outside the two are the same sentence. So this package
takes the long way round: recognise "close to A and B" per part, CONSTRUCT the
garment that resemblance implies, drop it to 3D, and have a person confirm it
is the garment they had in mind. **Only then does the search for sewing methods
run at all.**

**Why per part.** An embedding model produces one global vector for the whole
image, and one vector answers one question: which image is most similar. An
unclassifiable garment is compositional — cape + bodice + high-low skirt +
sleeve — and a global embedding cannot say the cape resembles A while the skirt
resembles B. Per-part retrieval needs segmentation before embedding, so
`resemble.per_part()` refuses a whole-image-only stack by name
(`UNKNOWN_WHOLE_IMAGE_ONLY`, naming `UNKNOWN_NO_SEGMENTER` as the missing
stage) rather than answering the easier question and calling it the harder one.

**Why not a ranking.** On this project's own earlier benchmark
Marqo-FashionSigLIP beat Apple by dMRR +0.292 for same-garment retrieval, and
its material ranking flipped 8.5% under a horizontal flip while uniform noise
was indistinguishable from real photographs by margin. Similarity is usable for
"which garment" and is not trustworthy as a ranking of construction. That
finding is enforced structurally, in two places: retrieval hits land at an
address derived from the ASPECT alone, so two backends that disagree collide at
one address and come back `CONTESTED_IN_CROSS` with both sides kept and neither
chosen; and `sewing_search.register_corpus()` refuses a backend declaring
`modality="image_embedding"` outright.

**Why the 3D is not decoration.** "Cosine 0.83 to garment A" cannot be checked
by a person. "Here is the garment that similarity implies" can be checked in
two seconds. The solid is the falsifier for the retrieval — it turns an
unverifiable claim into a verifiable one, which is what this whole package is
for. It is built out of the composed draft's own edge lengths, it is a
proportion block and not a fit simulation, and the confirmation sheet says so
by quoting the objects themselves rather than by a sentence written once in a
docstring.

**Why the order is load-bearing.** Approval comes before the sewing-method
search, never after. A method retrieved for the wrong garment is worse than no
method: it is a plausible wrong answer, and plausible wrong answers reach
cutting tables. The block is therefore on the SEARCH, and it is enforced by the
argument surface rather than by discipline —

```python
sewing_search.methods_for(approval_id: str, corpus: str = "") -> dict
```

and nothing else. No public callable in that module, and no MCP tool that
reaches it, accepts a draft, a part graph, a structure, an image path or a
`json_text` blob. A check walks `inspect.signature` over the module and over
the tool schemas against 30 forbidden parameter names, so adding a convenience
overload turns the suite red. The module reads the shape back out of the
ADOPTED ledger entries the approval names, recomposes it against the current
measurements, and refuses `UNKNOWN_APPROVAL_STALE` if the digest has moved —
which is what kills an approval after `zones.apply()` nudges a parameter. A
person approved a shape, not a session.

**Nothing here ships a model.** `resemble.backends()` is empty on a fresh
import and a check starts a fresh interpreter to measure that rather than
assert it. There is a fixture backend for driving the loop end to end without
a model, and it is unmistakable at four levels: its model id starts
`fixture:`, `register()` refuses it under any other name, every hit it returns
carries `"fixture": true`, and the source string it stamps on every landed
claim begins with the same prefix. A fixture that could pass for a backend is
how a demo becomes a claim.

**And the search itself queries nothing, today.** There is no image-to-pattern
corpus in this tree, so with a shape approved and no corpus registered the
honest answer is `UNKNOWN_NO_SEWING_CORPUS`, naming SewFactory, GarmentCodeData
and GarmentCode as the corpora that would serve and `register_corpus()` as the
entry point. It is not a stub returning `[]`: an empty list says "there are no
methods" and the true sentence is "nothing was asked". Nothing about those
datasets has been measured here — verify every count and licence from the
dataset card before any of it reaches an output. One trap is closed before any
of them is wired: GarmentCodeData is generated FROM GarmentCode, so two corpora
that agree while sharing a root are refused `UNKNOWN_SHARED_LINEAGE` rather
than counted as the two independent sources a generic construction claim costs.
`cross._source_key` can see that two names differ; it cannot see lineage.

**Is the loop finished?** `convergence.check()` counts it: open ports +
contested measurements + unresolved refusals + unsewable seams + failed
physical checks + claims the human keeps rejecting. Three identical rounds and
it escalates to a person, naming the likely cause — "no procedure for
`<part>`; register one in `garment_parts` and add it to `parts.PART_GEOMETRY`"
— rather than saying try again.

**`mannequin.dress()` is not part of this.** It is left alone deliberately.
Nothing in this loop calls it: the question here is "is this my garment", which
is about structure, while `dress()` answers "how does it sit on a form", which
is about fit. It also does not work — `mannequin.build()` lays y = 0 at the hip
and increases upward while the sewn drape returns y negative downward, so
`radius_at()` raises `ValueError: max() arg is an empty sequence` on every
garment. Two things are wrong there and both need an owner's decision: the
raise crosses a tool boundary (it should be a typed `UNKNOWN_FRAME_MISMATCH`
naming both ranges) and the frame conversion between the two modules is assumed
rather than declared. Neither is on this loop's critical path and neither was
fixed opportunistically.

## How it is checked

```bash
python3 tests/run_checks.py
```

The same thing CI runs, on every push and pull request, across Python 3.9 and
3.12 on Linux and macOS, plus a macOS build of the app. Each check prints what
it measured rather than just PASS, because a check that only says PASS tells
you nothing on the day it starts lying.

It re-measures the numbers quoted in this file, so the document cannot drift
away from the code in silence — and it asserts that the default stitch
stiffness still **fails** to close the garment. If that ever starts passing,
this README is the thing that is wrong.

Behaviour is pre-registered: the falsifying condition is written down before
the check is run, so a check that cannot fail is caught as a check that cannot
fail rather than counted as a pass. Three examples of what that discipline
found, each of which had been reported as working:

- A seam-closed check that judged by the **mean**, reporting `closed=true`
  while one stitch of 23 stood 3.66&nbsp;cm open. It now judges by the worst
  stitch and prints the count over tolerance beside it.
- Units read from the input and then **ignored** — a pattern entered in inches
  drafted as centimetres, 6027&nbsp;cm² silently becoming 511&nbsp;cm².
- Three seam checks that **could not fail**, because they compared a point list
  to itself. They now detect the tautology by comparing the point lists, and
  say `structural` in the output instead of claiming a verification.

### The checks that could not fail, and why looking harder is not a method

This project has now found **eleven** checks that could not fail, in five
separate passes — one, then three, then two, then two, then three. Every pass
someone read the suite more carefully and found more. That is not bad luck; it
is a search method that does not scale, and the honest response is to stop
searching by hand. (Those eleven found and the **10** entries currently
argued in `KNOWN_UNFALSIFIABLE`, below, are different tallies on purpose:
"found once, across five passes" and "still open today" are not the same
count. Some findings were fixed outright — the property strengthened so the
shape no longer applies — rather than kept as an argued exception, so they
count toward the eleven but not toward the ten. Run
`python3 tests/unfalsifiable.py` for the live residue rather than trusting
either number as fixed.)

```bash
python3 tests/unfalsifiable.py     # every condition, read as an AST
python3 tests/unfalsifiable.py --self-test   # the detectors, on planted shapes
python3 tests/unfalsifiable.py --runtime --write-ledger --jobs 4
                                   # freeze each served reader, re-run the suite
python3 tests/falsifiers.py        # every check, regressed and re-run
python3 tests/falsifiers.py --self-test   # the harness's own stopping defect
python3 tests/coat_digest.py --check      # the coat, bit for bit
```

`tests/unfalsifiable.py` reads the AST of every `check(name, condition,
detail)` call and reports eight shapes that make a line green whatever the code
does: both sides of a comparison being one value; `all()`/`any()` over a
sequence that can be empty; the subject under test being a refusal object; a
property true by construction; a ratio that holds at zero; the real number
living in the detail while the condition asserts something weaker; a served
reader no check pins to a literal; and a mutation harness that stops at the
first raise. It is wired into the suite as a check of its own, with the
residue enumerated by name and argued in `KNOWN_UNFALSIFIABLE` — **a hit that
is not on that list turns the suite red.**

**One of those shapes cannot be decided by reading, and the tool says so.**
A served reader "pinned to a literal" is not pinned at all: freezing it to the
literal it returns TODAY satisfies exactly that comparison, so the *static*
answer is a heuristic reported as a property — not a verdict. The module's
own record of what the static reading actually caught: **five readers passed
that test and could have been replaced by a constant.** The real verdict
comes from mutation — `--runtime` freezes each reader in turn, re-runs the
whole suite and records what reddened in `tests/t7_readers.json`, keyed by a
digest of the reader's own source. Those five are fixed now, pinned against a
second store, and the ledger currently reads **18 readers, 0 bypassable**,
re-measured with `PHOTOLOSET_T7_RUNTIME=1`. (An earlier draft of this section
quoted "seven of eighteen readers" for that first runtime run — that number
came from a working note, not from anything in the tree, and could not be
reproduced from a commit or from `tests/t7_readers.json`'s own history; it
has been withdrawn in favour of the figure above, which does reproduce.) And
the detectors themselves are tested: 20 checks that pass and cannot fail are
planted in `tests/corpus/`, alongside 12 honest checks in the same shapes
that must NOT be called certainties.

It also states what it cannot see, every time it runs: anything inside the code
under test, whether a property is the RIGHT one, checks nobody wrote, and
whether a pinned number is the correct number. Those remain a reader's job.

`tests/coat_digest.py` answers a different version of the same question. Every
pass carried a sentence like "the coat is unmoved, digest 7ce1a667…" — and the
pass that tried to verify one could not reproduce it, because the script that
made it lived in its author's scratch directory. **A number only its author can
recompute is not a measurement**, which is a check that cannot fail one level
up. The generator is in the tree, it canonicalises every float to its IEEE-754
bit pattern with no tolerance, and the suite runs it: geometry
`bbc1d025184d1cff58977def178faf49` over the draft, the marks, the built mesh
and seams, both 2000-iteration drapes, the SVG and the headline figures.

`tests/falsifiers.py` is the other direction: it copies the tree, regresses one
repair at a time back to the behaviour a finding measured, and requires the
named check to go red. **The harness had the same defect one level up** — a
raise inside its own loop ended the sweep at mutation N, the rest neither ran
nor were named, no summary printed, and the mutated file was never restored.
`--self-test` poisons a three-entry sweep in two different ways and passes only
if the entries after the poison still ran, the tree came back clean and the
counts printed; the suite runs it.

### One decision this pass deliberately did not make

The arm a claim sits on is derived from its kind — nobody chooses it. But a
seat that is reached by **two** kinds is charged to whichever kind seated
first, and that is still a write-order effect. The store no longer hides it:
`census()` reports `budget_arm_rule`, every two-kind address and every arm that
rode free without paying a face — **derived from the seats, so it survives
`to_dict()`/`from_dict()`**, which the write-session log it used to be did not
— `ingest_order_check()` counts the differences that are the budget arm alone,
and `put_strict()` returns `charged_arm` on **every** accepted write, including
the one that creates the seat and therefore chooses the arm. The coat and the parts library have **zero** two-kind addresses, so no
answer moves today. The three ways to close it, and what each one costs, are in
`photoloset/cross.py` under `_arm_load` — the choice belongs to whoever owns
the store's meaning, not to whoever is fixing checks this week.

<br>

## Where this actually stands

This is one working pipeline, not a product. The four things below are the
ones most likely to matter to you, and none of them is close to solved.

Each is open as an issue with the experiment that would settle it, because
these are questions rather than tasks — if you have a garment, a tape and some
footage, you can answer one of them without touching the code:

| | |
| --- | --- |
| [#1](https://github.com/Ag3497120/photoloset/issues/1) | Does the observe step fail loudly or quietly on cinematic footage? |
| [#2](https://github.com/Ag3497120/photoloset/issues/2) | Why does the seam gap widen with more iterations, and is 16x the right default? |
| [#3](https://github.com/Ag3497120/photoloset/issues/3) | Second clip — does any of this generalise? |
| [#4](https://github.com/Ag3497120/photoloset/issues/4) | The sleeve is non-unique. Is refusing right, or is there a principled pick? |

**Two garments, and no notion of a garment *type*.** The drafting blocks are
hand-built, not parametrised: a three-piece coat (front bodice, back bodice,
sleeve) and a five-part cape dress (bodice, skirt panel, sleeve, cape,
collar — 7 cut pieces). A jacket with darts and a canvas front, a shirt with
a yoke and a collar stand, trousers, anything knitted, anything cut on the
bias: none of these exist here, and adding one is not a parameter change, it
is a new block with new formulas and new seams. Treat the two garments as
worked examples of the discipline, not as coverage — and note that both were
drafted from a tape measure, not recognised from a photograph; see the
opening section for why that gap is not closing soon.

**Numbers do not come out of the footage.** This is the caveat to read twice.
The footage is used to *identify* things — this collar, that pocket — and a
person then measures a real reference garment with a tape and types the numbers
in. The tool refuses to derive a dimension from a frame, on purpose, because a
frame has no scale in it. So "film to pattern" is honest about identification
and dishonest if you read it as "film to measurements". If you do not have the
physical garment, or something close enough to measure, this tool cannot draft
for you.

**It has been run end to end on one clip and one lighting condition**
([#3](https://github.com/Ag3497120/photoloset/issues/3)). That clip happened
to suit it: the coat is presented plainly, the light is even, the framing is
stable, and a reference garment was on hand. The dress has no footage behind
it at all — it was composed directly from measured parts, to prove the parts
graph and every downstream stage (mannequin, marker, BOM, DXF) generalise
past one hard-coded three-piece shape. There is no second clip, no held-out
set, and therefore no evidence about how the *observe* step behaves on
footage it has not seen.

**Cinematic footage is untested, and it is the intended target** ([#1](https://github.com/Ag3497120/photoloset/issues/1)). A film frame
is graded, key-lit, shadowed, often motion-blurred and often grainy. All of
those change what a vision model reads out of a frame, and none of them has been
measured here. The honest position is that we do not know whether the observe
step degrades *loudly* — proposing less, so the ledger simply stays emptier —
or *quietly*, proposing confident nonsense that a person then adopts. Those two
failure modes are not equally bad, and which one happens is exactly the
experiment that has not been run. Until it has, treat any proposal drawn from
stylised footage as untrustworthy in a way the tool cannot currently flag for
you.

**Computation is not solved either** ([#2](https://github.com/Ag3497120/photoloset/issues/2), [#4](https://github.com/Ag3497120/photoloset/issues/4)). The solver is pure Python, roughly
O(iterations x edges): about 4 seconds for 2000 iterations over 303 points and
954 edges. It stops because it hits the iteration cap, not because it converged
— and at low iteration counts the worst seam gap *grows*, not shrinks, as the
cap rises (measured on this coat at the default stitch stiffness: 0.92 cm at
2000 iterations, 2.44 cm at 8000, 3.25 cm at 20000).

That is not the solver diverging — left running far past any iteration count a
check can afford (2026-08-27: several hundred thousand iterations, off this
repository's own test budget), it does reach a genuine fixed point rather than
climbing forever: 3.39 cm at 16x, 0.85 cm at 64x. Neither closes the 0.1 cm
seam tolerance; the code's own "64x closes it" reading is a snapshot at 2000
iterations, taken while a fast, local, and misleadingly small dip is still
underway, before the slow part — the whole coat settling under gravity —
finishes. The growth is genuine: a stitched vertex is touched by many springs
at once, and one uniform step size, sized for the single stiffest spring, gives
every less-connected vertex an unnecessarily tiny step, so gravity's effect on
the coat has to cross the mesh one edge per iteration. `sew_and_drape` now
takes an opt-in `precondition=True` that sizes the step per vertex from that
vertex's own total incident stiffness instead of the single global worst case.
**An earlier version of this README claimed that was a real ~3-4x speed-up to
the same 0.85 cm fixed point (~80000 iterations against ~300000 without).
That claim was wrong** (caught 2026-08-27, in an outside check, reproduced
independently here): run without early stopping, the preconditioned worst
seam gap dips to about 0.04-0.06 cm around 80000-120000 iterations and is
already rising again by 120000 — not a fixed point, a trough on a curve that
is still moving. An independent, longer replica run (~1,000,000 iterations)
still had not reached anywhere near 0.85 cm and was still climbing. Whether
preconditioning eventually reaches the same fixed point as the unmodified
solver is unverified — there is a reason to expect it should (both are
descending the same convex elastic energy, so the true minimum does not
depend on the step-size schedule), but that has not been shown by measurement.
What IS measured and real: preconditioning pushes the worst seam gap under
the 0.1 cm sewing tolerance far sooner than the unmodified solver does within
any budget tested here — useful for getting a quick, closed-looking snapshot,
worthless as evidence of having reached equilibrium. Because "worst" is a
maximum over a finite set of seam pairs rather than a smooth quantity,
`sew_and_drape` no longer trusts a quiet 50-iteration window as proof of
settling when `precondition=True` — it now always runs the full iteration
count requested rather than declaring an early, possibly false, "closed".
None of this is a fix for the underlying diffusive propagation, and it is not
the default: turning it on moves every solved coordinate, including the two
the coat's own digest pins.

There is no self-collision or friction, so the fall of the cloth is a
plausible-looking artefact of a spring mesh rather than a simulation of
fabric. Bending is now representable — a fabric can declare `bending`
alongside its weight, thickness and stretch stiffness, and a fabric that omits
it is refused rather than defaulted, the same as the other two — but it is a
diagonal-spring approximation to a true hinge (this mesh's cells carry both
diagonals as stretch edges already; adding bending as a genuinely separate
face-angle hinge would mean choosing one diagonal as a triangulation, which
moves the pinned edge count), and it has not been measured against a
cantilever or any other physical reference — only that raising it visibly
stiffens the drape (a jersey-weight fabric's own vertical spread under gravity
falls monotonically as its bending value rises, from 164.1 cm undeclared or
zero, to 156.8 cm at a low value, to 112.5 cm at a high one — the same coat,
the same weight, the same everything else). A sleeve sewn into a tube is
genuinely non-unique — it can rotate about its own axis — and multiple starts
disagree by 11.4 cm, which is why the tool names the piece and declines
instead of returning one of them.

## Licence

MIT — see [LICENSE](LICENSE).

The drafting block is this tool's own simplification, not a published system,
and the pattern is derived from measurements rather than traced from anyone's
pattern. If you feed it a garment you do not own the rights to, that is between
you and them; the ledger records where you said each thing came from, which is
the point.
