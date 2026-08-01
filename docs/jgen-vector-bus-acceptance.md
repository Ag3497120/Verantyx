# JGEN vector-bus acceptance checklist

Polarity: Vera / Vision / AX are adapters; **only JGEN owns the residual stream**. Preset: `jgen-vector-bus` (no Ollama L3, no AgentLoop / Nano).

## Phase A — memory bus

1. Load a `.jgen` (e.g. Qwen2.5-0.5B instruct).
2. Apply architecture template **JGEN vector bus (no escalation)**.
3. Enable council for chat.
4. Trigger a desktop observation (`[DESKTOP_SNAPSHOT]` via Vector Lab tool harness, or ask a UI-repro question so L2 Act runs a snapshot).
5. Confirm:
   - Log shows **JGEN native / JGenSpeak** or **JGEN Act** (not Nano / `[MEM:check]`).
   - `~/.verantyx_chrono_swift/cortex.nodes.jsonl` gains a `UI observe: desktop_snapshot` (or act) line.
   - Optional: `~/.verantyx_chrono_swift/ui_traces/<session>.nodes.jsonl` gains a step.
6. Next chat turn (non-greeting) should inject eternal / visual-label / UI-trace recall into council or speak prompts.

## Phase B — act loop (UI repro)

1. Same preset; ask e.g. 「この操作でボタンが押せない — 再現して確認して」.
2. L2 log: **JGEN Act** (desktop/AX via vector bus).
3. Loop may emit `[OPEN_APP]` / `[DESKTOP_SNAPSHOT]` / `[AX_ACT]` / `[DESKTOP_ACT]` / `[DONE:…]`.
4. Each observe/act stamps eternal + UITestVectorTrace again.
5. Final `[DONE]` conclusion stays on the same `.jgen` (no L3 escalation).

## Closed loop (target)

`observe → JGEN encode → EternalMemory/UITestVectorTrace → council inject/recall → JGenAct operate → re-observe`

Vision feature-print inject (`VisualHiddenStateBridge`) is experimental fallback only; preferred path is AX/text `encodeText` → inject.
