# Garment generation typed contract (v1)

This contract is the shared boundary between the beginner UI, deterministic
garment engine, optional language model phrasing, and cloth simulation.  A
language model may propose an envelope, but only the deterministic parser and
validator may accept it. Fashion retrieval, rights-reviewed sewing corpora and
review-only web reference discovery plug in above the same proposal boundary;
none may approve a shape or promote a claim by score.

## Image-to-garment production flow

The macOS Atelier uses `garment.factory.v1` as the production foreman:

1. Confirm one front/oblique image and start the append-only job.
2. Run the configured multimodal image model and
   `Marqo/marqo-fashionSigLIP` concurrently. Missing weights, endpoint or index
   is a typed non-blocking review result; no model is downloaded implicitly.
3. Store every model assertion as `PROPOSED`, then require a named human to
   audit only visible garments, layer order and visible parts.
4. In parallel, let the human erase/restore background, hair, source body and
   other garments from the fused front 2.5D surface. The accepted target is
   revision- and digest-bound with undo lineage.
5. Record the reviewed visible-front facts in the factory journal and Vera's
   stereo-cross memory. Rear construction, material identity, body dimensions
   and sewing remain unobserved.
6. Compile reviewed parts into candidate-bound 3D and flat-pattern artifacts.
   The accepted image front is preserved; multiple rear/depth candidates stay
   `PROPOSED` and can be compared on ten default body proxies or a user body.
7. Search local/endpoint fashion evidence and rights-gated sewing corpora.
   The autonomous web agent also discovers rear/sewing URLs, but keeps them as
   `PROPOSED_WEB_REFERENCE` until page content and use rights are reviewed.
8. Edit the target with erase/restore, pull, stretch, thickness and bounded
   wind preview. The red-to-blue map is per-face avatar-envelope clearance,
   not measured pressure, temperature, comfort or material fit.
9. Re-adopting a changed target appends a cleanup revision, invalidates old
   candidate, pattern, simulation and sewing artifacts, then recompiles and
   redresses against the new target. Every regenerated pattern/repair carries
   `garment.cad-target-iteration-binding.v1` with the exact target, cleanup,
   front-audit and front-compilation lineage. Old revisions remain in the
   journal.

## Command envelope

Every command is a JSON object with these fields:

- `schema`: literal `garment.command.v1`
- `command_id`: stable caller-supplied identifier
- `intent`: one of `NAVIGATE`, `INSPECT`, `ADJUST_PATTERN_SPAN`, `ADD_EASE`,
  `CHANGE_LENGTH`, `CHANGE_MATERIAL`, `GENERATE_FROM_IMAGE`,
  `PROPOSE_STRUCTURE`, `RUN_SIMULATION`, `COMPARE_SIMULATIONS`, `APPROVE`,
  `REJECT`, or `UNDO`
- `target`: typed object; pattern spans use integer `first` and `last`
- `operation`: typed object; dimensional values use `value` plus explicit
  `unit` (`cm`, `mm`, or `m`)
- `job_id`: optional existing generation job
- `commit`: boolean; parsing and preview default to `false`
- `provenance`: `DETERMINISTIC_PARSE`, `MODEL_PROPOSAL`, or `HUMAN_INPUT`

Unknown words, missing units, ambiguous targets, and unsupported operations are
typed refusals.  They are never converted into a nearby intent.

## Job states

`GarmentGenerationJob` is the generic preview/approval ledger. Its audited
front path starts with:

`IMAGE_RECEIVED`, `AI_ANALYSIS_PROPOSED`,
`HUMAN_GARMENT_AUDIT_REQUIRED`, `FOREGROUND_CLEANUP_REQUIRED`,
`CLEANUP_REVIEW_REQUIRED`, `FRONT_FACTS_RECORDED`, and `TARGET_2_5D_READY`.

Its legacy generic path then transitions through:

`IMAGE_RECEIVED`, `REGIONS_CONFIRMED`, `GEOMETRY_CONTESTED`,
`BACK_CANDIDATES_READY`, `STRUCTURE_APPROVED`, `MATERIAL_CONTESTED`,
`SIMULATION_READY`, `SHAPE_APPROVED`, `PATTERN_VALIDATED`,
`SEWING_BLOCKED_NO_CORPUS`, and `COMPLETE`.

Transitions require named evidence/artifact digests.  Invalid skips return
`UNKNOWN_INVALID_JOB_TRANSITION`.  `UNDO` appends a compensating event and
restores the previous immutable snapshot; it never deletes history.

## Preview and approval

Mutating commands first produce a `garment.preview.v1` object containing before
and after snapshots, changed addresses, validation results, and a digest.
Approval must name that digest.  A stale digest is refused.  Only an approved
preview may update the active job snapshot.

## Structure graph

The structure representation is `garment.structure.v1`: typed primitive nodes
and typed joins.  Initial primitives are `BODY_SHELL`, `TUBE`, `FRUSTUM`,
`FLARE`, `GORE`, `GUSSET`, `YOKE`, `COLLAR`, `HOOD`, `SLEEVE`, `BAND`,
`OVERLAY`, `OPENING`, and `DRAPE_ANCHOR`.  Initial operations are `SPLIT`,
`JOIN`, `OVERLAP`, `FOLD`, `GATHER`, `PLEAT`, `DART`, `CUTOUT`, `MIRROR`,
`ASYMMETRY`, and `LAYER`.

Back and material inference returns candidates, never an adopted fact.  Every
candidate carries constraints, assumptions, source evidence, and a digest;
human approval is required for promotion.

`garment.factory.v1`, rather than the generic job's declared future-stage
placeholders, owns the live parts/retrieval/pattern/material/simulation/sewing
loop used by the app. A newly accepted CAD target clears all downstream fields
and reopens reviewed-front compilation.

## Simulation

The existing `cross_cloth_simulate` schema remains valid.  A v2 solver may add
`solver: xpbd`, compliance values, adaptive substeps, continuous-collision
settings, and diagnostics without changing the old default.  All six-arm
updates read the same old state; different signal meanings remain typed and
stacked; disagreement abstains; coarse, medium, and fine solve the same target.

The current wind button is a bounded proposal preview, not computational fluid
dynamics. The clearance colour map is deterministic geometry, not a physical
pressure or thermal field. `wearer_comfort` can consume real sensor samples,
but the CAD screen does not fabricate those samples from one photograph.

## Remaining engineering boundaries

- Arbitrary sculpt edits do not yet have a manufacturing-certified inverse
  flattening proof. The live loop safely invalidates, recompiles and redresses;
  it does not claim that a pulled 3D mesh uniquely determines a sewable 2D
  pattern. The CAD iteration binding therefore says
  `target_geometry_compiled_into_pattern: false` and
  `inverse_flattening.verdict: UNKNOWN_NOT_PROVEN`.
- Web results are discovered autonomously but are not copied into geometry or
  sewing instructions until content, provenance and licence are reviewed.
- Real FashionSigLIP/VLM output requires a configured local model, API,
  endpoint or precomputed fixture. A missing backend degrades to typed
  geometry/model proposals instead of pretending the model ran.
- Rear surfaces, hidden seams, material mechanics, wearer dimensions and
  industrial strength cannot become observations from a single front image.

## Answer envelope

UI-visible engine output is `garment.answer.v1` with `verdict`, `facts`,
`allowed_suggestions`, `forbidden_claims`, `artifacts`, and `provenance`.
Optional LLM phrasing may only restate this envelope.  The deterministic text
is always available and wins if phrasing invents a number, fact, verdict, or
promotion.
