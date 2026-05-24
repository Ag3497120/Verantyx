#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Gemini版: foundation_kb.jsonl を分野ごとにバッチ採掘するツール

- JSONLで追記（1行=1entryのdict）
- 既存IDを読み、重複を避ける
- バッチ生成 → 検証 → 失敗ならリトライ
- response_mime_type=application/json でJSON汚染を防ぐ

使い方例:
  export GEMINI_API_KEY="xxxxx"
  python3 tools/mine_foundation_kb_gemini.py \
    --out avh_math/db/foundation_kb.jsonl \
    --model gemini-3-flash-preview \
    --total_per_domain 240 \
    --per_batch 80
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Gemini SDK
# pip install -U google-genai
from google import genai

# -----------------------------
# Config
# -----------------------------

DEFAULT_DOMAINS = [
    "propositional_logic",
    "first_order_logic",
    "model_theory",
    "group_theory",
    "ring_theory",
    "topology",
    "category_theory_intro",
    "complexity_theory",
    "graph_theory",
]

# 生成させたい entry の最小スキーマ（あなたのKBの雛形に合わせてください）
ENTRY_KEYS = [
    "id",
    "domain",
    "kind",  # definition | axiom | theorem | rule | counterexample_schema
    "title",
    "statement",
    "prerequisites",
    "yields",
    "refutation",
    "patterns",
    "links",
]

KIND_DISTRIBUTION = [
    ("definition", 0.20),
    ("axiom", 0.15),
    ("theorem", 0.35),
    ("rule", 0.20),
    ("counterexample_schema", 0.10),
]

# -----------------------------
# Utilities
# -----------------------------

def now_ms() -> int:
    return int(time.time() * 1000)

def load_existing_ids(jsonl_path: Path) -> Set[str]:
    ids: Set[str] = set()
    if not jsonl_path.exists():
        return ids
    with jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    _id = obj.get("id")
                    if isinstance(_id, str) and _id:
                        ids.add(_id)
            except Exception:
                # 壊れた行があっても採掘を止めない
                continue
    return ids

def append_jsonl(path: Path, entries: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

def safe_sleep(sec: float) -> None:
    time.sleep(sec)

def choose_kind() -> str:
    r = random.random()
    acc = 0.0
    for k, p in KIND_DISTRIBUTION:
        acc += p
        if r <= acc:
            return k
    return KIND_DISTRIBUTION[-1][0]

def normalize_patterns(pats: Any) -> List[str]:
    if pats is None:
        return []
    if isinstance(pats, list):
        out = []
        for x in pats:
            if isinstance(x, str) and x.strip():
                out.append(x.strip())
        return out[:30]
    if isinstance(pats, str) and pats.strip():
        return [pats.strip()]
    return []

def normalize_links(links: Any) -> List[str]:
    if links is None:
        return []
    if isinstance(links, list):
        out = []
        for x in links:
            if isinstance(x, str) and x.strip():
                out.append(x.strip())
        return out[:30]
    if isinstance(links, str) and links.strip():
        return [links.strip()]
    return []

def validate_entry(e: Dict[str, Any], domain: str) -> Tuple[bool, str]:
    if not isinstance(e, dict):
        return False, "entry_not_dict"

    # 必須キー
    for k in ["id", "domain", "kind", "title", "statement"]:
        if k not in e:
            return False, f"missing_{k}"
        if not isinstance(e[k], str) or not e[k].strip():
            return False, f"bad_{k}"

    if e["domain"] != domain:
        return False, "domain_mismatch"

    if e["kind"] not in {"definition", "axiom", "theorem", "rule", "counterexample_schema"}:
        return False, "bad_kind"

    # 配列フィールド整形
    e["prerequisites"] = e.get("prerequisites") or []
    e["yields"] = e.get("yields") or []
    e["patterns"] = normalize_patterns(e.get("patterns"))
    e["links"] = normalize_links(e.get("links"))

    if not isinstance(e["prerequisites"], list):
        return False, "bad_prerequisites"
    if not isinstance(e["yields"], list):
        return False, "bad_yields"

    # refutation は str or null
    ref = e.get("refutation")
    if ref is not None and not isinstance(ref, str):
        return False, "bad_refutation"

    return True, "ok"

def validate_batch(entries: Any, domain: str) -> Tuple[List[Dict[str, Any]], List[Tuple[Any, str]]]:
    ok: List[Dict[str, Any]] = []
    bad: List[Tuple[Any, str]] = []

    if not isinstance(entries, list):
        return [], [(entries, "batch_not_list")]

    for x in entries:
        if not isinstance(x, dict):
            bad.append((x, "entry_not_dict"))
            continue
        v, reason = validate_entry(x, domain)
        if v:
            ok.append(x)
        else:
            bad.append((x, reason))
    return ok, bad

# -----------------------------
# Prompt builder
# -----------------------------

def build_prompt(domain: str, n: int, existing_ids: Set[str], seed_hint: str) -> str:
    # 既存IDを避けるための制約
    # ID規約: {prefix}.{kind}.{nnn}
    # prefix例: prop / fol / mt / grp / ring / top / cat / cx / graph など
    prefix = {
        "propositional_logic": "prop",
        "first_order_logic": "fol",
        "model_theory": "mt",
        "group_theory": "grp",
        "ring_theory": "ring",
        "topology": "top",
        "category_theory_intro": "cat",
        "complexity_theory": "cx",
        "graph_theory": "graph",
    }.get(domain, "kb")

    # 既存ID（多いとトークン増えるので先頭だけ）
    sampled_existing = list(sorted(existing_ids))[:200]

    # 生成ルールを強める（JSON汚染対策）
    return f"""
You are generating entries for a mathematical knowledge base.
Return ONLY a JSON array (no markdown, no commentary).

Domain: {domain}
Count: {n}

Each entry MUST be a JSON object with EXACT keys:
{ENTRY_KEYS}

Constraints:
- "domain" must be exactly "{domain}"
- "kind" must be one of: definition, axiom, theorem, rule, counterexample_schema
- "id" must be unique and follow pattern: "{prefix}.<kind>.<3-digit>" e.g. "{prefix}.def.001" or "{prefix}.thm.042"
  Use kind abbreviations: def, ax, thm, rule, cex
- Use English titles, but include some Japanese in "patterns" where natural.
- "statement" should be concise but mathematically correct.
- "prerequisites" and "yields" should be lists of short tags (strings).
- "refutation" is either null or a short string describing how to refute / produce counterexample.
- "patterns" is list of search phrases (3-15 items).
- "links" is list of related ids (can be empty).

Avoid these existing ids (do NOT reuse):
{json.dumps(sampled_existing, ensure_ascii=False)}

Seed hint for diversity:
{seed_hint}

Now output the JSON array.
""".strip()

# -----------------------------
# Gemini call
# -----------------------------

def call_gemini_json_array(
    *,
    client: genai.Client,
    model: str,
    prompt: str,
    temperature: float,
    max_retries: int,
) -> Any:
    last_err: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = client.models.generate_content(
                model=model,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "temperature": temperature,
                },
            )

            text = getattr(resp, "text", None)
            if not text:
                # 互換：候補から回収
                text = resp.candidates[0].content.parts[0].text

            return json.loads(text)
        except Exception as e:
            last_err = e
            print(f"[WARN] attempt {attempt}/{max_retries} failed: {e} (sleep {attempt:.1f}s)", file=sys.stderr)
            safe_sleep(float(attempt))
    raise RuntimeError(f"Gemini call failed after retries: {last_err}")

# -----------------------------
# Main mining loop
# -----------------------------

@dataclass
class DomainPlan:
    domain: str
    target_total: int

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, help="Output JSONL path (append). e.g. avh_math/db/foundation_kb.jsonl")
    parser.add_argument("--model", default="gemini-3-flash-preview", help="Gemini model id")
    parser.add_argument("--domains", nargs="*", default=DEFAULT_DOMAINS, help="Domains to mine")
    parser.add_argument("--total_per_domain", type=int, default=240, help="Total entries per domain")
    parser.add_argument("--per_batch", type=int, default=80, help="Entries per request")
    parser.add_argument("--max_retries", type=int, default=5)
    parser.add_argument("--temperature", type=float, default=0.4)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Missing GEMINI_API_KEY env var. Set it like: export GEMINI_API_KEY='...'")


    random.seed(args.seed or 0)

    out_path = Path(args.out)
    existing_ids = load_existing_ids(out_path)
    print(f"[INIT] existing ids: {len(existing_ids)}")

    client = genai.Client(api_key=api_key)

    for domain in args.domains:
        target = int(args.total_per_domain)
        print(f"\n[DOMAIN] {domain} target={target}")

        # 現在domainの既存数を数える
        # JSONLが大きくなるので、既存IDからはdomain判定できない。
        # ここでは “総ID数” で進める（domain別厳密カウントが必要なら別indexを作る）。
        mined_this_domain = 0

        # ざっくり “このdomain用のprefix” を変えるためのseed_hint
        seed_hint = f"domain={domain};ts={now_ms()};rand={random.randint(0, 10**9)}"

        while mined_this_domain < target:
            remaining = target - mined_this_domain
            batch_n = min(int(args.per_batch), remaining)

            prompt = build_prompt(
                domain=domain,
                n=batch_n,
                existing_ids=existing_ids,
                seed_hint=seed_hint,
            )

            raw = call_gemini_json_array(
                client=client,
                model=args.model,
                prompt=prompt,
                temperature=float(args.temperature),
                max_retries=int(args.max_retries),
            )

            ok, bad = validate_batch(raw, domain)

            # 重複排除
            deduped: List[Dict[str, Any]] = []
            for e in ok:
                _id = e.get("id")
                if isinstance(_id, str) and _id and _id not in existing_ids:
                    deduped.append(e)
                    existing_ids.add(_id)

            if not deduped:
                print(f"[WARN] batch produced 0 usable entries (bad={len(bad)}). Retrying with new seed_hint.", file=sys.stderr)
                seed_hint = f"domain={domain};ts={now_ms()};rand={random.randint(0, 10**9)}"
                safe_sleep(1.0)
                continue

            append_jsonl(out_path, deduped)
            mined_this_domain += len(deduped)

            print(f"[OK] +{len(deduped)} entries (mined {mined_this_domain}/{target})")
            if bad:
                print(f"[WARN] dropped={len(bad)} (first_reason={bad[0][1]})", file=sys.stderr)

            # 次のバッチは軽く揺らす
            seed_hint = f"domain={domain};ts={now_ms()};rand={random.randint(0, 10**9)}"
            safe_sleep(0.25)

    print("\n[DONE] mining finished.")

if __name__ == "__main__":
    main()