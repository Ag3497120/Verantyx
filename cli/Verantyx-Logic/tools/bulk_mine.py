#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests
import yaml


SYSTEM_PROMPT = """You are a mathematics knowledge miner.
Return STRICT JSON ONLY, no markdown, no extra text.
Schema:
{
  "id": "...",
  "name": "...",
  "statement": "...",
  "domain": ["..."],
  "prerequisites": ["..."],
  "tactics": ["..."],
  "counterexample_templates": ["..."],
  "tags": ["..."],
  "proof_sketch_template": ["..."]
}
Keep statements concise but correct.
If unsure, still output best-effort and add tag "uncertain".
"""


def openai_chat(base_url: str, model: str, api_key: str, user_prompt: str, timeout: int = 120) -> Dict[str, Any]:
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }
    r = requests.post(url, headers=headers, json=payload, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    content = data["choices"][0]["message"]["content"]
    return json.loads(content)


def build_prompt(item: Dict[str, Any]) -> str:
    # item: {id, name, hint_domains?}
    tid = item["id"]
    name = item.get("name", tid)
    domains = item.get("domains") or item.get("domain") or []
    extra = ""
    if domains:
        extra = f"\nDomains hint: {domains}"
    return f"""Mine a theorem entry.

id: {tid}
name: {name}{extra}

Output JSON with the exact schema.
Prerequisites/tactics should be useful for solving problems, not just definitions.
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True, help="YAML file with theorem seed list")
    ap.add_argument("--out", required=True, help="Output JSONL path")
    ap.add_argument("--base-url", required=True, help="OpenAI-compatible base URL, e.g. http://127.0.0.1:8000/v1")
    ap.add_argument("--model", required=True, help="Model name")
    ap.add_argument("--api-key", default="", help="API key (if needed)")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--sleep", type=float, default=0.0)
    args = ap.parse_args()

    with open(args.catalog, "r", encoding="utf-8") as f:
        catalog = yaml.safe_load(f)

    items: List[Dict[str, Any]] = catalog.get("theorems", catalog)
    if not isinstance(items, list):
        print("Catalog must be a list or have key 'theorems' as list", file=sys.stderr)
        sys.exit(1)

    start = time.time()
    ok = 0
    fail = 0

    with open(args.out, "w", encoding="utf-8") as out:
        with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
            futures = {}
            for item in items:
                prompt = build_prompt(item)
                fut = ex.submit(openai_chat, args.base_url, args.model, args.api_key, prompt)
                futures[fut] = item["id"]
                if args.sleep > 0:
                    time.sleep(args.sleep)

            for fut in as_completed(futures):
                tid = futures[fut]
                try:
                    entry = fut.result()
                    out.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    ok += 1
                    print(f"[OK] {tid}")
                except Exception as e:
                    fail += 1
                    print(f"[FAIL] {tid}: {e}", file=sys.stderr)

    dur = time.time() - start
    print(f"Done. ok={ok} fail={fail} seconds={dur:.1f}")


if __name__ == "__main__":
    main()
