# verantyx-cli (`vera`)

Research / repro runtime for Verantyx. **Dual-track with the IDE GUI** — this CLI does not replace or gut Verantyx IDE (chat, mirror, Act, MCP, settings stay).

```
vera-core     — event schema, Gap/skill/safety surfaces in logs
verantyx-cli  — formal research/repro interface (`vera run`)
verantyx-gui  — Verantyx IDE visualizes / approves (later: consume JSONL)
```

Event flow: task → Core/CLI runtime → structured stdout + optional JSONL → (future) GUI.

## Build & run

```bash
cd cli/verantyx-cli
swift build
swift run vera run --demo --trace traces/demo.jsonl
```

Dry-run (no live `OPEN_APP` / Accessibility):

```bash
swift run vera run --demo --dry-run --trace traces/demo.jsonl
```

Convenience wrapper from repo `cli/`:

```bash
./vera run --demo --trace verantyx-cli/traces/demo.jsonl
```

## Event schema

Kinds (stdout labels): `MISSION` / `OBSERVATION` / `PROPOSED_ACTION` / `POLICY` / `RESULT` / `GAP` / `SKILL_RECALL`.

```bash
swift run vera schema
```

JSONL fields: `schema_version`, `ts`, `kind`, `mission_id`, `turn`, `summary`, `detail`, `tags`.
Optional `detail.mission_kind` (`act` | `speak`) on `mission` events — aligns with IDE `MissionKindClassifier`.

Shared Swift types live in `Sources/VeraCore/` and are mirrored for the IDE at  
`cli/VerantyxIDE/Sources/Verantyx/Engine/VeraRuntimeEvent.swift` (keep in sync until the app links VeraCore).

## Safety defaults

CLI defaults match in-flight IDE memory hardening:

- `vector_only_sense=true` (AX map preferred; no model pixel inject)
- PromptBudget-aligned caps surfaced on `POLICY` events
- GPU safety notes on `POLICY` (`prefer_cpu_on_low_ram`, pause capture during JGEN)

## Demo path

Scripted Act/sense tags (same vocabulary as `AgentTool` / `JGenActAgent`):

`OPEN_APP` → `DESKTOP_SNAPSHOT` (vector-only AX) → `DONE`

Full JGEN Act loop remains in the IDE; CLI is the reproducible log surface.

## TODO (GUI)

- Thin frontend over JSONL / SSE — do **not** rebuild GUI as inference brain.
- Optionally fan-in IDE `LoopEvent` → `VeraRuntimeEvent` for unified traces.
