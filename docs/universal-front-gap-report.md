# Universal front-only pipeline: adversarial gap report

The contract tested here is deliberately narrower than “one photograph proves a
production-ready garment.” It is: one front image may start a deterministic,
auditable candidate loop, while every invisible or under-determined property
remains `PROPOSED` or a typed `UNKNOWN` until a person or a stronger observation
closes it.

Primary regression: `tests/test_universal_front_pipeline.py`. Repository-wide
checks also exercise the MCP surface, export transport, repair catalogue and
Vera convergence boundaries.

## What passes now

- The app starts image analysis by running its configured multimodal vision
  route and `Marqo/marqo-fashionSigLIP` adapter concurrently. Local,
  endpoint/API and precomputed adapter modes are typed; missing weights or an
  index are visible review results and do not trigger an implicit download.
- The production factory stops after AI analysis for a named human audit of
  visible garments, layer order and visible parts. The fused front target has
  a second revision/digest-bound cleanup gate, and only those reviewed
  visible-front facts are recorded to Vera's stereo-cross.
- Anime-exaggerated silhouettes, ordinary separates, overlay/cape-like layers,
  and gathered ruffle/frill interpretations reach multiple deterministic
  structure candidates.
- The RegionPicker transports separately selected clothing components and
  sufficiently large closed inner loops instead of collapsing all local
  evidence into one outer envelope. Inner-loop meaning remains `PROPOSED` and
  `UNKNOWN`; a human clothing seed confirms the region, not “this is a seam.”
- Inside the selected clothing mask, a bounded eight-direction weak-gradient
  detector can also propose long open switch/fold/overlap-like lines. It
  rejects the outer three pixels, short/noisy/strong transitions and duplicate
  candidates, and exports at most eight `PROPOSED / UNKNOWN` polylines.
- Geometry cues can use outer silhouette, component regions and closed internal
  boundaries to propose `BODY_SHELL`, `OVERLAY`, `BAND`, `LAYER` and `GATHER`
  combinations. The graph is compositional rather than a growing list of named
  garment classes.
- Each structure/back candidate carries its own digest, procedural 3D preview,
  compiled-pattern digest, sewing topology, manufacturing preview and lineage.
  Candidate A cannot silently reuse candidate B's 3D or flat pattern.
- Front-only back alternatives stay `PROPOSED`; no centre-back opening, closed
  stretch back or side opening is promoted to `OBSERVED`.
- Ten default preview body profiles are selectable. A chosen profile, target
  cleanup, pull/stretch modifier, thickness and bounded wind preview all enter
  the target digest, while the body profile remains a proposed proxy rather
  than a wearer measurement.
- Rear and sewing reference searches start autonomously beside the local
  retrieval route. Returned URLs remain review-only leads with explicit page
  content and rights gates; search snippets never become geometry or sewing
  facts.
- The CAD view publishes a red-to-blue per-face geometric-clearance map. It is
  explicitly not pressure, temperature, comfort or calibrated fit.
- Re-adopting an edited target invalidates candidate, pattern, simulation and
  sewing outputs, then reopens compilation/retrieval/redressing. Regenerated
  pattern and repair artifacts bind the exact CAD revision and carry an
  explicit `UNKNOWN_NOT_PROVEN` inverse-flattening boundary.
- Wide compiler-authored flare and ruffle pieces first fail fabric-width checks,
  then can be split deterministically while preserving compiler seam topology
  and named source-edge lineage. Arbitrary imported patterns still fail closed
  when that topology cannot be reconstructed.
- The export bundle contains SVG, DXF and JSON artifacts plus one manifest. The
  verifier checks strict transport decoding, file hashes and byte lengths,
  manifest and package digests, candidate/structure/source lineage, readiness
  state and embedded SVG/DXF/JSON lineage. This is transport-integrity
  verification, not a manufacturing certificate.
- The beginner UI reads the same Vera ReAct/job state as the expert workbench,
  separates 3D preview from named human approval, shows manufacturing cards and
  gates file export on a verified bundle. Re-selecting the same image republishes
  the operation and clears the stale confirmed outline.
- When no rights-cleared sewing corpus is connected, the loop can continue
  with the dependency order derived from the approved pattern topology. That
  route carries `corpus_used=false`, `UNKNOWN_NO_SEWING_CORPUS` and
  non-certification flags; it is not presented as precedent or shop-floor
  stitch/machine evidence.
- Invalid or incomplete input fails closed with typed causes; an empty candidate
  set is not reported as successful generation.

## Exact remaining gaps

1. **Internal evidence is incomplete and does not determine semantics.**
   Closed holes, separately coloured/connected components and sufficiently
   long weak open gradients are available. A genuinely invisible same-colour
   line, a transition without usable pixel gradient, or a heavily occluded
   line cannot be recovered from the photograph. Even when a line is detected,
   one front view cannot decide whether it is a
   seam, print, fold, overlap edge, opening, shadow or decoration. Such lines
   must enter as alternative `PROPOSED` construction hypotheses.

2. **A single front image cannot prove the back or depth.**
   Rear structure, closure, hidden layer order, armhole geometry and true depth
   remain candidates. A named human approval can select a candidate; it cannot
   turn the original photograph into a rear observation.

3. **Body and material inputs are still real gates.**
   Preview-mannequin dimensions are not wearer measurements. Material mass,
   warp/weft stretch, bending, friction and seam behaviour require measured or
   explicitly approved values before fit, strength or comfort claims can rise
   above review status.

4. **The 3D result is a candidate-specific procedural preview.**
   It is useful for comparing shape, back alternatives and layer placement, but
   it is not yet a calibrated drape/fit twin and does not establish industrial
   mannequin contact or manufacturing validity.

5. **Arbitrary CAD sculpt to 2D is not a solved inverse.**
   Pull/stretch/erase/wind edits are revision-bound and force deterministic
   recompilation/redressing, but the edited surface itself is not yet flattened
   into a unique manufacturing-grade pattern. Artifacts state
   `target_geometry_compiled_into_pattern=false` and
   `inverse_flattening=UNKNOWN_NOT_PROVEN` instead of hiding this boundary.

6. **The flat pattern remains a geometric prototype until gates close.**
   Seam topology, cut counts, grain and sewing order now exist, but production
   release still needs body dimensions, closure/donning review, seam allowance,
   material selection/calibration, notches, strength/comfort review and a named
   approval of the exact candidate digest.

7. **The operation vocabulary is wider than the compiler.**
   `garment.structure.v1` names `SPLIT`, `CUTOUT`, `MIRROR` and `ASYMMETRY`, but
   the deterministic pattern compiler does not yet implement all of their
   topology-changing geometry. It correctly refuses an unsupported operation
   instead of fabricating a pattern.

8. **There is no bundled rights-cleared industrial sewing corpus.**
   Procedural geometry can produce a candidate seam topology without a corpus,
   but precedent-based construction search still stops when no licensed,
   lineage-bearing corpus is connected. Embedding similarity alone is not a
   construction instruction.

9. **Engineering review is not industrial certification.**
   The present cross-cloth, collision, shell, fluid, seam and comfort paths are
   typed reference/verification kernels. They do not substitute for calibrated
   fabric tests, wearer studies, continuous industrial remeshing, machine
   process validation, or a qualified pattern maker's release.

## Current measured baseline

```text
python3 tests/run_checks.py
254 checks passed

python3 -m unittest discover -s tests -p 'test_*.py'
916 tests passed
```

These numbers establish the repository's current deterministic contracts. They
do not establish that an arbitrary front-only image can always become a safe,
comfortable and production-ready garment without additional evidence.
