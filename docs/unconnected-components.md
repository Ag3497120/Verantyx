# Photoloset component connection audit

Photoloset distinguishes an implemented Python capability from a capability
that is safe to call through the garment factory or MCP.  A public function is
not automatically a remote tool: many public symbols are data constructors,
validators, numerical kernels, or low-level helpers whose authority and input
contract are supplied by a higher stage.

The `garment_connection_audit` MCP tool makes that boundary inspectable.  It
does not import optional providers while auditing them, and it reports every
stage/component with exactly one of four statuses:

| Status | Meaning |
| --- | --- |
| `CONNECTED` | The typed implementation and every named MCP tool are present. |
| `OPTIONAL_PROVIDER` | The flow can continue with a rights/provenance-bearing provider, a human-authored proposal, or—only after explicit consent—an LLM proposal that remains `PROPOSED`. |
| `HUMAN_RESOLUTION` | The missing value is an observation, cleanup edit, or approval that a model may not grant to itself. |
| `TYPED_STOP` | The transition ends without mutation. Correct typed input or a fresh preceding-stage digest is required. |

Every row also names `accepted_evidence` and `next_action`.  The audit maps
all literal `UNKNOWN_*`, `CONTESTED_*`, and `ESCALATE_*` verdicts found in
`garment_factory.py` to the same actionable-or-terminal contract.  A future
or delegated verdict not present when the source was scanned fails closed as
`TYPED_STOP`; it never becomes an untyped dead end.

## Calling the audit

The empty request returns the connection table and factory refusal contracts:

```json
{"json_text":"{}"}
```

Optional filters are `stage` and `component`.  Setting
`include_inventory=true` adds an AST-only inventory of public top-level
functions/classes, exact-name MCP tools, symbols referenced by the factory,
and registered components:

```json
{
  "json_text": "{\"stage\":\"PATTERN\",\"include_inventory\":true}"
}
```

The inventory parses local source; it does not execute the modules being
inventoried.  `unconnected_public_modules` therefore means “no remote or
factory connection was found,” not “this code is unused” or “it should become
an MCP tool.”

## Newly exposed existing capabilities

These MCP tools are thin adapters over existing engine modules.  They add
typed JSON validation but do not infer omitted dimensions or promote
proposals:

| MCP tool | Existing implementation | Authority boundary |
| --- | --- | --- |
| `garment_structure_sewing_plan` | `structure_sewing_plan.plan` | Orders present seam topology; unspecified seam finishes remain review items. |
| `garment_manufacturing_preview` | `pattern_manufacturing_bundle.build` | Requires an explicit seam allowance, unless the caller explicitly opts into a `PROPOSED` preview default. It does not certify manufacturing. |
| `garment_engineering_review` | `garment_engineering_review.review` | Keeps pattern, repair, manufacturing, sewing, and simulation gates independent. |
| `garment_decorative_pattern` | `decorative_pattern.apply` | Applies only operations with explicit dimensions; it does not classify the garment or consult a corpus. |
| `garment_front_cutout_alternative` | `image_structure_operations.apply_cutout_alternative` | Adds a front-boundary alternative as `PROPOSED`; boundary semantics and candidate choice remain unobserved. |

`photoloset.mcp_server` also registers its existing
`garment_front_candidate_evaluate` extension after that tool exists.  This
keeps the canonical registry in `mcp.py` independent of extension import
order.

## Factory-stage connection map

The runtime audit is authoritative because tool and module availability can
change.  The canonical intended routes are:

| Stage/component | Intended status | Evidence or resolution |
| --- | --- | --- |
| Multimodal visible-front analysis | `CONNECTED` | Typed per-model assertions with model provenance; submit as proposals. |
| FashionSigLIP retrieval runtime | `OPTIONAL_PROVIDER` | Rights-gated hits with source and lineage, or an explicitly consented proposal. |
| Visible-front garment audit | `HUMAN_RESOLUTION` | Named review bound to the current image/analysis digest. |
| Foreground cleanup | `HUMAN_RESOLUTION` | Source-coordinate mask/polygon edits bound to the active revision. |
| Body proxy and avatar fit | `CONNECTED` | Explicit measurements, or a visibly `PROPOSED` image-derived proxy with uncertainty. |
| Second-skin triangle geometry | `CONNECTED` | Typed body surface and explicit offsets. |
| Rear candidate ensemble | `CONNECTED` | Multiple `PROPOSED` rear alternatives or a separately observed rear image. |
| Candidate-specific 3D repair | `CONNECTED` | Candidate-bound mesh/target plus a bounded repair budget. |
| Structure-to-pattern compiler | `CONNECTED` | Approved `garment.structure.v1` and its exact approval digest. |
| Structure sewing plan | `CONNECTED` | Compiled pieces and seam topology. |
| Manufacturing preview | `CONNECTED` | Compiled pattern plus explicit or explicitly proposed preview allowance. |
| Engineering review | `CONNECTED` | Independently typed stage outputs. |
| Decorative pattern operations | `CONNECTED` | Explicit dimensions and layer/attachment inputs. |
| Front cutout alternative | `CONNECTED` | Observed front geometry; result stays `PROPOSED`. |
| Sewing-method search | `OPTIONAL_PROVIDER` | Eligible corpus evidence, or explicit selection of the corpus-free topology order. |
| Shape/material approval | `HUMAN_RESOLUTION` | Named, digest-bound human decision. |
| Consented LLM proposal adapter | `OPTIONAL_PROVIDER` | Explicit consent and model provenance; output authority ceiling is `PROPOSED`. |
| Cross workflow harness | `CONNECTED` when present, otherwise effective `TYPED_STOP` | A typed resolution request and its human/provider/consented-model resolution. |
| Factory refusal boundary | `TYPED_STOP` | No mutation; repair typed input or restart from the named prior stage. |

A configured `CONNECTED` row is downgraded at audit time to `TYPED_STOP` if
its source module or a named MCP tool is absent.  The audit reports the missing
module/tool in `connection_error` instead of importing or guessing it.

## Known front-image limits and resumable routes

`known_limitations` is part of the audit response.  These rows make limits
machine-readable and resumable; they are not plain `UNKNOWN` messages.  Each
contains `mcp_tools`, `factory_events`, and a `resolution_route` naming how to
discover, acquire evidence for, and resume the flow.

| Limitation id | Typed route |
| --- | --- |
| `rear-not-observed-from-front` | Obtain another view or use `garment_rear_candidate_ensemble`; resume `garment_factory` with `SUBMIT_HYPOTHESES` and a digest-bound `APPROVE_HYPOTHESIS`. Rear alternatives remain `PROPOSED`. |
| `material-properties-not-measured-from-image` | Supply laboratory channels to `material_calibrate`, or compare proposed ranges; resume with `SUBMIT_MATERIAL_CANDIDATES` / `APPROVE_MATERIAL`. |
| `wearer-body-not-measured-from-image` | Record sourced values with `measure_taken`, inspect `measure_sheet`, validate `garment_wearer_measurement_contract`, then rerun `GENERATE_PATTERN`. An image body proxy remains preview-only. |
| `arbitrary-garment-fidelity-not-guaranteed` | The universal guarantee is a `TYPED_STOP`. Set a bounded tolerance, run `garment_candidate_3d_repair_loop` and candidate evaluation, then `ITERATE` or approve the remaining mismatch explicitly. |
| `finished-pattern-not-guaranteed` | The universal guarantee is a `TYPED_STOP`. Use the structure compiler, manufacturing preview, and engineering review; resolve typed missing topology/dimensions through `GENERATE_PATTERN` / `REPAIR_PATTERN`. |
| `seam-finishes-undetermined` | Use `garment_structure_sewing_plan` for dependency order; connect `sewing_methods` or bind a human decision, then resume a sewing-method factory event. |
| `real-cloth-error-not-calibrated` | Feed matching tests to `material_calibrate` and `seam_calibrate`, rerun `industrial_cloth_simulate`, and register the residual through `proof_cross_verify`; otherwise the result stays `REVIEW`. |
| `wind-tunnel-validation-not-connected` | Connect registered wind-tunnel/DNS conditions, use `turbulence_validate` / `incompressible_fluid_step`, and resume `SIMULATE` or `ITERATE`. Without those observations there is no validation claim. |
| `fashion-siglip-index-not-connected` | Configure the typed Marqo/FashionSigLIP runtime with rights and lineage, or use explicitly non-retrieval procedural hypotheses; resume `HYBRID_RETRIEVE` / `SUBMIT_RETRIEVAL`. |
| `sewing-corpus-not-connected` | Connect an eligible manifested corpus, or choose the corpus-free topology plan while leaving finishes unresolved; resume the typed sewing event. |

For the two universal guarantees (`arbitrary-garment-fidelity...` and
`finished-pattern...`), `terminal=true` means the guarantee claim itself is
refused.  Their `resolution_route.resumable=true` means work can continue with
a narrower, testable tolerance or represented subset.  It does not turn the
guarantee into an answer.

## Optional components and a future Cross harness

An optional provider or harness may register itself only after it has been
explicitly loaded by the host:

```python
from photoloset import mcp

mcp.register_connection_component(
    "my optional Cross harness",
    stage="CROSS_HARNESS",
    status=mcp.OPTIONAL_PROVIDER,
    module="vendor_package.cross_harness",
    tools=(),
    factory_events=("RESOLVE_CROSS_OBLIGATION",),
    accepted_evidence=("typed provider result with provenance",),
    next_action="connect the provider and resolve the typed obligation",
)
```

Registration stores a descriptor.  Auditing uses package/source-path probing
and never calls `importlib.find_spec` for arbitrary dotted providers, because
finding a child can execute its parent package.  A missing future module is
therefore reported safely rather than causing the MCP server to fail at
startup.

## LLM and UNKNOWN policy

An LLM is never a silent default-value source.  It can participate only where
the audit reports `OPTIONAL_PROVIDER`, after explicit consent, and its output
must remain `PROPOSED`.  It cannot claim:

- an observed rear surface from a front image;
- measured wearer dimensions;
- measured composition, thickness, stretch, friction, or bending stiffness;
- a certified sewing method, strength result, comfort result, or
  manufacturing-ready artifact.

Human observation/approval gaps are `HUMAN_RESOLUTION`.  Invalid, stale,
unsupported, or missing deterministic state is `TYPED_STOP`.  This preserves
the useful property of UNKNOWN—refusing to invent data—while ensuring every
factory stop tells the caller what evidence is accepted and what transition
may be attempted next.
