# MCP server — Vera as external memory for LLM agents

Vera's MCP server turns any MCP client (Claude Code, Claude Desktop, …) into
an agent with **persistent, auditable, deletable memory** that never
hallucinates: `ask` returns typed verdicts, and anything ungrounded comes
back as `UNKNOWN_*` instead of a plausible-sounding guess.

## Install & run

```bash
pip install -e ".[mcp]"
vera --store ~/vera_memory.json mcp
```

## Claude Code

```bash
claude mcp add vera -- vera --store ~/vera_memory.json mcp
```

## Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "vera": {
      "command": "vera",
      "args": ["--store", "/Users/you/vera_memory.json", "mcp"]
    }
  }
}
```

## Tools

| Tool | What it does |
|------|--------------|
| `remember(sentence)` | teach one fact; usable immediately |
| `ask(query)` | grounded QA with typed verdict + provenance counts |
| `recall(core, k)` | dump a concept's accumulated facets (both sense channels) |
| `forget(core)` | **really** delete a concept |
| `math(query)` | exact arithmetic / typed equation solving |
| `code_ingest(repo_path)` | AST-ingest a Python repo |
| `code_query(query)` | who-calls / calls-of / impact analysis |
| `stats()` | store size and provenance counters |
| `propose_ai_facts(text, source)` | quarantine fact candidates split from an assistant's **final** reply (never thinking/CoT) — hedge/meta sentences filtered out |
| `list_pending_ai_facts()` | list quarantined candidates awaiting human review |
| `accept_ai_fact(index)` | promote one candidate into the trusted store — the only path in, always explicit |
| `reject_ai_fact(index)` | discard one candidate |

### Passive memory from an assistant's own output (quarantined)

An agent can call `propose_ai_facts` with its own final answer text after
each turn to passively build up candidate memories — without ever risking
its own hallucinations landing in the trusted store as "verified" facts.
Nothing proposed is queryable via `ask` until a human runs
`list_pending_ai_facts` → `accept_ai_fact`. Design rationale, hedge-word
filtering, and why *thinking* text is deliberately out of scope:
[docs/DESIGN.md](DESIGN.md#passive-memory-from-ai-output-quarantined).

## Why pair an LLM with Vera

The LLM does what it is good at (language, fluency, planning); Vera holds
what the LLM is bad at holding (facts that must not drift, memories that must
survive sessions, deletions that must be real). The division is clean because
Vera is a separate deterministic process — it works identically well with no
LLM at all.
