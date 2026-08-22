# Verantyx — Quick start

Five settings decide how the app behaves. Everything else can wait.

1. **Interface language / 表示言語** — Switches the interface between English and Japanese.
   Settings › General › Interface language

2. **Ollama model / Ollama モデル** — Which Ollama model local requests use.
   Settings › Model › Ollama model

3. **Ollama endpoint / Ollama エンドポイント** — URL the Ollama client connects to.
   Settings › Model › Ollama endpoint

4. **Anthropic API key / Anthropic API キー** — Credential for Anthropic requests.
   Settings › API Keys › Anthropic API key

5. **Agent loop / エージェントループ** — Whether the agent keeps working across turns on its own.
   Settings › Agent › Agent loop

Then pick two modes:

- **Operation mode / 動作モード** (How much the agent asks before it acts.)
  - `Gatekeeper` — Shared or production code, where an unreviewed edit is expensive.
  - `Automatic` — A task you have already scoped and want finished unattended.
  - `Detailed` — An unclear task, where the first answer is likely to be the wrong one.

- **Inference route / 推論経路** (Where your text goes: local machine, cloud, or masked before sending.)
  - `Local Only` — Anything you cannot send to a third party.
  - `Cloud Direct` — Public code, where capability matters more than exposure.
  - `Privacy Shield` — Cloud capability on code with names you would rather not ship.
  - `Paranoia Mode` — The strictest option that still uses the cloud.

Stuck? Ask the support bot in the app. It answers from this same registry, so it will tell you a setting does not exist rather than inventing where it lives.
