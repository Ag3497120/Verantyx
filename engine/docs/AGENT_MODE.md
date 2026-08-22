# Agent mode — Vera with hands and feet

Agent mode is a **ReAct loop where Vera is the controller**. Vera decides and
remembers; an optional local LLM proposes the next tool call; every mutating
action is gated behind **arrow-key approval** on the CLI.

```bash
vera setup                       # pick local LLM + allocation dial (once)
vera agent                       # interactive
vera agent "summarize README.md and note the license"
vera agent --yes "..."           # auto-approve (use with care)
```

## The loop

1. **Vera first.** Exact math/code or a grounded knowledge answer can finish
   the task with **no LLM and no tools** (`source: vera_direct`).
2. Otherwise the LLM emits ONE action as JSON:
   `{"thought": "...", "tool": "name", "args": {...}}` or
   `{"thought": "...", "final": "..."}`.
3. **Mutating tools require approval** — a menu appears:

   ```
   ┌─ approval required ─────────────────────────
   │ write_file(path, content)
   │   { "path": "notes.md", "content": "..." }
   └─────────────────────────────────────────────
    ▶ Approve (once)
      Always allow this tool (this session)
      Deny
   ```

   ↑/↓ (or j/k) to move, Enter to choose. "Always" whitelists that tool for
   the session. Read-only tools never prompt.
4. The observation is appended; repeat until `final` or max steps.

Without an LLM, agent mode still works: type `!tool {json-args}` to run any
tool manually (approvals still apply), or a plain line to consult Vera.

## Tools (the 手足)

| Tool | Mutating | |
|------|:--:|--|
| `read_file`, `list_dir` | · | inspect the workspace |
| `write_file`, `edit_file`, `make_dir` | ✋ | create / change files & folders |
| `run_command` | ✋ | shell command |
| `web_search`, `fetch_url` | · | DuckDuckGo search + page fetch |
| `vera_ask`, `vera_recall`, `vera_code_query`, `vera_math` | · | consult the deterministic core |
| `vera_remember`, `vera_code_ingest` | ✋ | write to the knowledge store |

✋ = approval required.

Web search is an independent Python counterpart of the Verantyx IDE's
BrowserBridge (which is JCross-vaulted); it uses the DuckDuckGo lite endpoint
over stdlib `urllib`, no API key.

## Allocation dial — who owns which domain

`vera setup` (or `~/.verantyx.json`) tunes where Vera answers vs where the
LLM speaks:

| Domain | Options | Default |
|--------|---------|---------|
| `math` | `vera` / `llm` | **vera** (exact; never let an LLM guess) |
| `code` | `vera` / `llm` | **vera** (AST facts) |
| `known` | `vera` / `llm_guided` | **llm_guided** (LLM phrases Vera's verified facts) |
| `unknown` | `refuse` / `llm_free` | **refuse** (typed UNKNOWN; `llm_free` = labeled-unverified chat) |

Invariants the dial cannot break: exact math/code values are never
paraphrased by the LLM, and an `AMBIGUOUS` verdict is never resolved by the
LLM. Vera stays the controller.
