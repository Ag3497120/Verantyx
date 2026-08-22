"""Local LLM client (Ollama) — the language surface Vera controls.

Vera never depends on this: everything deterministic works without it.
When present, a local model supplies fluent phrasing while Vera supplies
facts, memory, math, and the decision of *when the LLM is allowed to speak*.

Only stdlib (urllib) — no extra dependencies. Default endpoint is the
standard Ollama daemon at http://localhost:11434.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

OLLAMA_URL = "http://localhost:11434"


def ollama_available(url: str = OLLAMA_URL, timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/api/tags", timeout=timeout):
            return True
    except (urllib.error.URLError, OSError):
        return False


def ollama_generate(
    model: str,
    prompt: str,
    *,
    system: Optional[str] = None,
    url: str = OLLAMA_URL,
    timeout: float = 180.0,
    temperature: float = 0.2,
    num_predict: int = 256,
    think: bool = False,
) -> Dict[str, Any]:
    """Generate via Ollama.

    ``think=False`` by default: reasoning-tuned models (e.g. some Gemma /
    DeepSeek-style finetunes) can burn the entire ``num_predict`` budget on
    hidden chain-of-thought and return an EMPTY ``response`` with
    ``done_reason: "length"``. Vera's agent loop needs one JSON action, not
    a thinking transcript, so thinking is off unless explicitly requested.
    Harmless on models that don't support the field.
    """
    payload: Dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "think": think,
        "options": {"temperature": temperature, "num_predict": num_predict},
    }
    if system:
        payload["system"] = system
    req = urllib.request.Request(
        f"{url}/api/generate",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            d = json.loads(resp.read())
        text = d.get("response", "").strip()
        if not text and d.get("done_reason") == "length":
            return {
                "ok": False,
                "error": "empty_response_thinking_budget_exhausted "
                         "(model spent num_predict on hidden reasoning; "
                         "try think=True with a larger num_predict, or a "
                         "non-reasoning model)",
                "model": model,
            }
        return {"ok": True, "text": text, "model": model}
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "model": model}
