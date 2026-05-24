#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nemotron Knowledge Miner (NDJSON, resumable, validated)
- Generates math KB entries across domains/kinds
- Outputs NDJSON shards + merged file
- Enforces quality gates (links, uniqueness, refutation construction, prerequisites ratio)
- Deduplicates by id, and can re-run safely (resume)

USAGE (example):
  python3 mine_kb_nemotron.py \
    --backend openai_compat \
    --base_url http://localhost:8000/v1 \
    --api_key YOUR_KEY \
    --model nvidia/nemotron-xxx \
    --out_dir avh_math/db/foundation_kb_gen \
    --domains propositional_logic first_order_logic \
    --target_per_domain 250

If you want local transformers:
  python3 mine_kb_nemotron.py --backend transformers --model_path /path/to/model ...
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import random
import re
import sys
import time
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Dict, Iterable, List, Optional, Tuple

# -----------------------------
# Domain plan (edit freely)
# -----------------------------
DEFAULT_DOMAIN_PLAN: Dict[str, Dict[str, int]] = {
    # kind counts per domain (sum ~= target_per_domain, script will scale if needed)
    "propositional_logic": {
        "definition": 50, "axiom": 40, "theorem": 80, "rule": 50, "counterexample_schema": 30
    },
    "first_order_logic": {
        "definition": 60, "axiom": 40, "theorem": 90, "rule": 60, "counterexample_schema": 30
    },
    "model_theory": {
        "definition": 60, "axiom": 30, "theorem": 90, "rule": 40, "counterexample_schema": 30
    },
    "group_theory": {
        "definition": 60, "axiom": 20, "theorem": 110, "rule": 40, "counterexample_schema": 20
    },
    "ring_theory": {
        "definition": 60, "axiom": 20, "theorem": 110, "rule": 40, "counterexample_schema": 20
    },
    "topology": {
        "definition": 70, "axiom": 20, "theorem": 110, "rule": 30, "counterexample_schema": 20
    },
    "category_theory_basic": {
        "definition": 70, "axiom": 20, "theorem": 80, "rule": 40, "counterexample_schema": 20
    },
    "complexity_theory": {
        "definition": 60, "axiom": 20, "theorem": 110, "rule": 40, "counterexample_schema": 20
    },
    "graph_theory": {
        "definition": 60, "axiom": 20, "theorem": 110, "rule": 40, "counterexample_schema": 20
    },
}

# -----------------------------
# Data model
# -----------------------------
@dataclass
class KBEntry:
    id: str
    domain: str
    kind: str  # definition | axiom | theorem | rule | counterexample_schema
    title: str
    statement: str
    prerequisites: List[str]
    yields: List[str]
    refutation: Optional[str]
    patterns: List[str]
    links: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

# -----------------------------
# Backends
# -----------------------------
class LLMBackend:
    def generate_json(self, prompt: str, *, temperature: float = 0.2, max_tokens: int = 1800) -> str:
        raise NotImplementedError

class OpenAICompatBackend(LLMBackend):
    """OpenAI-compatible /v1/chat/completions backend."""
    def __init__(self, base_url: str, api_key: str, model: str, timeout_s: int = 120):
        import requests  # local import
        self._requests = requests
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s

    def generate_json(self, prompt: str, *, temperature: float = 0.2, max_tokens: int = 1800) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You output ONLY valid JSON. No markdown. No commentary."},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        r = self._requests.post(url, headers=headers, json=payload, timeout=self.timeout_s)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"]

class TransformersBackend(LLMBackend):
    """Local transformers backend. (May require GPU depending on model size)."""
    def __init__(self, model_path: str):
        from transformers import AutoTokenizer, AutoModelForCausalLM
        import torch
        self.tok = AutoTokenizer.from_pretrained(model_path, use_fast=True)
        self.model = AutoModelForCausalLM.from_pretrained(model_path, device_map="auto", torch_dtype=torch.float16)
        self.model.eval()

    def generate_json(self, prompt: str, *, temperature: float = 0.2, max_tokens: int = 1800) -> str:
        import torch
        inputs = self.tok(prompt, return_tensors="pt").to(self.model.device)
        with torch.no_grad():
            out = self.model.generate(
                **inputs,
                do_sample=True,
                temperature=temperature,
                max_new_tokens=max_tokens,
                eos_token_id=self.tok.eos_token_id,
            )
        text = self.tok.decode(out[0], skip_special_tokens=True)
        # Return last JSON object found (robust-ish)
        return extract_json_object(text) or text.strip()

# -----------------------------
# Prompting
# -----------------------------
def build_prompt(domain: str, kind: str, n: int, used_ids_sample: List[str]) -> str:
    """
    Ask for EXACTLY n entries as JSON array.
    """
    # A short sample of already-used ids to avoid duplicates
    sample = used_ids_sample[-20:] if used_ids_sample else []
    avoid = "\n".join(sample)

    schema = {
        "id": "string (unique, domain-scoped, e.g. topo.def.001)",
        "domain": domain,
        "kind": kind,
        "title": "short",
        "statement": "one-paragraph precise statement/definition",
        "prerequisites": ["strings"],
        "yields": ["strings"],
        "refutation": "null or a short construction/counterexample procedure",
        "patterns": ["keywords, incl. Japanese variants when common"],
        "links": ["ids of related entries (>=1)"]
    }

    constraints = f"""
You must output ONLY a JSON array of EXACTLY {n} objects.
No markdown. No comments. No trailing text.

Hard constraints:
- Each object must match this schema exactly:
{json.dumps(schema, ensure_ascii=False, indent=2)}

- ids must be unique and follow a consistent prefix for this domain.
- links: must include at least 1 link per entry (no isolated nodes).
- counterexample_schema kind: refutation MUST include a "Construction:" style procedure.
- prerequisites empty ratio should be low; include prerequisites where meaningful.
- Keep statements mathematically correct and standard.

Avoid reusing these ids (already taken):
{avoid if avoid else "(none)"}
""".strip()

    # Some domain-specific anchoring to reduce garbage
    domain_hints = DOMAIN_HINTS.get(domain, "")
    return f"{constraints}\n\nDomain hints:\n{domain_hints}\n\nNow generate {n} entries for domain={domain}, kind={kind}."

DOMAIN_HINTS: Dict[str, str] = {
    "propositional_logic": "Include: syntax/semantics, CNF/DNF, soundness/completeness, inference rules, classic fallacies, non-classical notes.",
    "first_order_logic": "Include: structures, interpretations, quantifiers, Skolemization, compactness, Löwenheim–Skolem, completeness, prenex forms.",
    "model_theory": "Include: types, saturation, elementary embeddings, ultraproducts, quantifier elimination (basic), theories and models.",
    "group_theory": "Include: group actions, Sylow, homomorphisms, normal series, simple groups (basic), abelian invariants.",
    "ring_theory": "Include: ideals, PID/UFD, Noetherian, localization, modules basics, quotient rings, nilpotent/prime/max ideals.",
    "topology": "Include: separation axioms, compactness, connectedness, product topology, quotient, metric spaces basics, counterexamples.",
    "category_theory_basic": "Include: functors, natural transformations, limits/colimits (basic), adjunctions (intro), Yoneda (basic statement).",
    "complexity_theory": "Include: P/NP, reductions, completeness, space classes, randomness basics, PCP (high-level), circuit complexity basics.",
    "graph_theory": "Include: connectivity, matchings, planarity, coloring, flows, extremal basics, classic counterexamples."
}

# -----------------------------
# JSON extraction + validation
# -----------------------------
def extract_json_object(text: str) -> Optional[str]:
    # finds last {...} or [...] block (greedy)
    m = re.findall(r"(\{.*\}|\[.*\])", text, flags=re.DOTALL)
    return m[-1] if m else None

def parse_entries(raw: str) -> List[KBEntry]:
    raw = raw.strip()
    # try to extract JSON array if wrapped
    if not raw.startswith("["):
        maybe = extract_json_object(raw)
        if maybe and maybe.startswith("["):
            raw = maybe
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("Model output must be a JSON array.")
    entries: List[KBEntry] = []
    for obj in data:
        entries.append(KBEntry(
            id=str(obj["id"]),
            domain=str(obj["domain"]),
            kind=str(obj["kind"]),
            title=str(obj["title"]),
            statement=str(obj["statement"]),
            prerequisites=list(obj.get("prerequisites") or []),
            yields=list(obj.get("yields") or []),
            refutation=obj.get("refutation", None),
            patterns=list(obj.get("patterns") or []),
            links=list(obj.get("links") or []),
        ))
    return entries

def validate_entries(entries: List[KBEntry], *, expected_domain: str, expected_kind: str, existing_ids: set) -> Tuple[List[KBEntry], List[str]]:
    errors: List[str] = []
    ok: List[KBEntry] = []

    for e in entries:
        if e.domain != expected_domain:
            errors.append(f"{e.id}: wrong domain {e.domain} != {expected_domain}")
            continue
        if e.kind != expected_kind:
            errors.append(f"{e.id}: wrong kind {e.kind} != {expected_kind}")
            continue
        if e.id in existing_ids:
            errors.append(f"{e.id}: duplicate id")
            continue
        if not e.links or len(e.links) < 1:
            errors.append(f"{e.id}: missing links")
            continue
        if e.kind == "counterexample_schema":
            ref = (e.refutation or "").lower()
            if "construction" not in ref:
                errors.append(f"{e.id}: counterexample_schema missing Construction in refutation")
                continue
        # Basic sanity
        if len(e.title) < 3 or len(e.statement) < 10:
            errors.append(f"{e.id}: too short")
            continue

        ok.append(e)

    return ok, errors

# -----------------------------
# IO helpers (NDJSON + resume)
# -----------------------------
def load_existing_ids(out_dir: str) -> set:
    ids = set()
    if not os.path.isdir(out_dir):
        return ids
    for fn in os.listdir(out_dir):
        if not fn.endswith(".ndjson"):
            continue
        path = os.path.join(out_dir, fn)
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    ids.add(obj["id"])
                except Exception:
                    pass
    return ids

def append_ndjson(path: str, entries: List[KBEntry]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e.to_dict(), ensure_ascii=False) + "\n")

def merge_ndjson(out_dir: str, merged_path: str) -> None:
    all_lines: List[str] = []
    for fn in sorted(os.listdir(out_dir)):
        if fn.endswith(".ndjson") and fn != os.path.basename(merged_path):
            with open(os.path.join(out_dir, fn), "r", encoding="utf-8") as f:
                all_lines.extend([ln for ln in f if ln.strip()])
    # de-dup by id
    seen = set()
    merged: List[str] = []
    for ln in all_lines:
        obj = json.loads(ln)
        if obj["id"] in seen:
            continue
        seen.add(obj["id"])
        merged.append(json.dumps(obj, ensure_ascii=False))
    with open(merged_path, "w", encoding="utf-8") as f:
        f.write("\n".join(merged) + ("\n" if merged else ""))

def file_sha256(path: str) -> str:
    h = sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

# -----------------------------
# Planning
# -----------------------------
def scale_plan(plan: Dict[str, int], target: int) -> Dict[str, int]:
    s = sum(plan.values())
    if s == 0:
        return plan
    # scale and round
    scaled = {k: max(1, int(round(v * target / s))) for k, v in plan.items()}
    # fix sum to target
    diff = target - sum(scaled.values())
    keys = list(scaled.keys())
    i = 0
    while diff != 0 and keys:
        k = keys[i % len(keys)]
        if diff > 0:
            scaled[k] += 1
            diff -= 1
        else:
            if scaled[k] > 1:
                scaled[k] -= 1
                diff += 1
        i += 1
    return scaled

# -----------------------------
# Main mining loop
# -----------------------------
def mine_domain(
    backend: LLMBackend,
    out_dir: str,
    domain: str,
    plan: Dict[str, int],
    *,
    batch_size: int = 25,
    temperature: float = 0.2,
    max_retries: int = 5,
    sleep_s: float = 1.0,
) -> None:
    existing_ids = load_existing_ids(out_dir)
    used_ids_sample: List[str] = sorted(existing_ids)

    for kind, total_n in plan.items():
        remaining = total_n
        shard_path = os.path.join(out_dir, f"{domain}__{kind}.ndjson")

        # Count already present for this shard (resume)
        already = 0
        if os.path.exists(shard_path):
            with open(shard_path, "r", encoding="utf-8") as f:
                for ln in f:
                    if ln.strip():
                        already += 1
        remaining = max(0, total_n - already)
        if remaining == 0:
            print(f"[SKIP] {domain}/{kind}: already {total_n}")
            continue

        print(f"[MINE] {domain}/{kind}: need {remaining} more (target {total_n})")

        while remaining > 0:
            n = min(batch_size, remaining)
            prompt = build_prompt(domain, kind, n, used_ids_sample)

            attempt = 0
            while True:
                attempt += 1
                try:
                    raw = backend.generate_json(prompt, temperature=temperature, max_tokens=1800)
                    entries = parse_entries(raw)
                    if len(entries) != n:
                        raise ValueError(f"Expected {n} entries, got {len(entries)}")

                    ok, errs = validate_entries(entries, expected_domain=domain, expected_kind=kind, existing_ids=existing_ids)
                    if len(ok) != n:
                        raise ValueError("Validation failed: " + "; ".join(errs[:10]))

                    # accept
                    append_ndjson(shard_path, ok)
                    for e in ok:
                        existing_ids.add(e.id)
                        used_ids_sample.append(e.id)

                    remaining -= n
                    print(f"  + wrote {n} entries -> remaining {remaining}")
                    break

                except Exception as e:
                    if attempt >= max_retries:
                        print(f"[FAIL] {domain}/{kind} batch n={n} after {attempt} tries: {e}")
                        raise
                    # jitter then retry with slightly higher temperature to escape loops
                    t2 = min(0.7, temperature + 0.1 * attempt)
                    print(f"[RETRY] {domain}/{kind} batch n={n} attempt {attempt}: {e} (temp->{t2})")
                    temperature = t2
                    time.sleep(sleep_s + random.random())

            time.sleep(sleep_s)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["openai_compat", "transformers"], required=True)
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--domains", nargs="*", default=[])
    ap.add_argument("--target_per_domain", type=int, default=250)
    ap.add_argument("--batch_size", type=int, default=25)
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--max_retries", type=int, default=5)
    ap.add_argument("--sleep_s", type=float, default=0.8)

    # openai compat
    ap.add_argument("--base_url", default="")
    ap.add_argument("--api_key", default="")
    ap.add_argument("--model", default="")

    # transformers
    ap.add_argument("--model_path", default="")

    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    # Backend init
    if args.backend == "openai_compat":
        if not (args.base_url and args.api_key and args.model):
            print("openai_compat requires --base_url --api_key --model", file=sys.stderr)
            sys.exit(2)
        backend: LLMBackend = OpenAICompatBackend(args.base_url, args.api_key, args.model)
    else:
        if not args.model_path:
            print("transformers requires --model_path", file=sys.stderr)
            sys.exit(2)
        backend = TransformersBackend(args.model_path)

    # Decide domains
    domains = args.domains or list(DEFAULT_DOMAIN_PLAN.keys())
    for d in domains:
        if d not in DEFAULT_DOMAIN_PLAN:
            print(f"Unknown domain: {d}. Known: {list(DEFAULT_DOMAIN_PLAN.keys())}", file=sys.stderr)
            sys.exit(2)

    # Mine
    for d in domains:
        base_plan = DEFAULT_DOMAIN_PLAN[d]
        plan = scale_plan(base_plan, args.target_per_domain)
        print(f"\n=== DOMAIN {d} plan={plan} sum={sum(plan.values())} ===")
        mine_domain(
            backend,
            args.out_dir,
            d,
            plan,
            batch_size=args.batch_size,
            temperature=args.temperature,
            max_retries=args.max_retries,
            sleep_s=args.sleep_s,
        )

    # Merge
    merged = os.path.join(args.out_dir, "foundation_kb_merged.ndjson")
    merge_ndjson(args.out_dir, merged)
    print(f"\n[MERGED] {merged}")
    print(f"[SHA256] {file_sha256(merged)}")

if __name__ == "__main__":
    main()