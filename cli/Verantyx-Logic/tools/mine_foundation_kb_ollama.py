#!/usr/bin/env python3
import argparse
import json
import os
import time
import requests
from typing import Dict, Tuple, List, Any, Set

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"

DOMAINS = [
    "propositional_logic",
    "first_order_logic",
    "model_theory",
    "group_theory",
    "ring_theory",
    "topology",
    "category_theory",
    "complexity_theory",
    "graph_theory",
]

ENTRY_SCHEMA = {
    "id": "",
    "domain": "",
    "kind": "",
    "title": "",
    "statement": "",
    "prerequisites": [],
    "yields": [],
    "refutation": None,
    "patterns": [],
    "links": [],
}

ALLOWED_KINDS = {"definition", "axiom", "theorem", "rule", "counterexample_schema"}


def load_existing(path: str) -> Tuple[Set[str], Dict[str, int]]:
    """
    Read JSONL and return:
      - ids set
      - domain_counts[domain] = count
    """
    ids: Set[str] = set()
    domain_counts: Dict[str, int] = {d: 0 for d in DOMAINS}

    if not os.path.exists(path):
        return ids, domain_counts

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                _id = obj.get("id")
                dom = obj.get("domain")
                if _id:
                    ids.add(_id)
                if dom in domain_counts:
                    domain_counts[dom] += 1
            except Exception:
                # ignore malformed lines
                pass

    return ids, domain_counts


def ollama_generate(model: str, prompt: str, retries: int = 8) -> str:
    last_err = None
    for i in range(retries):
        try:
            r = requests.post(
                OLLAMA_URL,
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    # ここが重要：可能ならJSON出力を強制
                    "format": "json",
                    "options": {
                        "temperature": 0.2,
                        "top_p": 0.9,
                        # 長めに返せるように（モデルや環境により上限あり）
                        "num_predict": 4096,
                    },
                },
                timeout=900,
            )
            r.raise_for_status()
            return r.json().get("response", "")
        except Exception as e:
            last_err = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"Ollama failed after retries: {last_err}")


def build_prompt(domain: str, n: int, existing_ids_sample: List[str]) -> str:
    # JSON以外を禁止＆“配列のみ”を強制。idはユニーク。
    return f"""
You are generating entries for a mathematics knowledge base.

DOMAIN = {domain}

OUTPUT RULES (must follow):
- Output ONLY a JSON array (no markdown, no backticks, no commentary).
- The JSON array length must be exactly {n}.
- Each element MUST be an object with EXACTLY these keys:
  id, domain, kind, title, statement, prerequisites, yields, refutation, patterns, links
- kind must be one of: definition, axiom, theorem, rule, counterexample_schema
- domain must be exactly "{domain}"
- prerequisites, yields, patterns, links must be arrays (possibly empty)
- refutation must be a string or null
- Avoid duplicate IDs. Do NOT use any ID in this sample list:
{existing_ids_sample}

Quality rules:
- Keep statements mathematically standard and precise.
- Prefer entries that are useful for verification / refutation.
- Include patterns with a few English/Japanese keywords when natural.

Return ONLY the JSON array now.
""".strip()


def extract_json_array(text: str) -> List[Any]:
    """
    Robustly extract the first JSON array from a model response.
    Handles cases where model adds extra text or code fences.
    """
    if not text:
        return []

    # Fast path: direct JSON
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except Exception:
        pass

    # Strip common code fences
    t = text.strip()
    t = t.replace("```json", "").replace("```", "").strip()

    # Find first '[' and last ']'
    l = t.find("[")
    r = t.rfind("]")
    if l == -1 or r == -1 or r <= l:
        return []

    candidate = t[l : r + 1]
    try:
        data = json.loads(candidate)
        if isinstance(data, list):
            return data
    except Exception:
        return []

    return []


def validate_entry(e: dict, domain: str, existing_ids: Set[str]) -> bool:
    if not isinstance(e, dict):
        return False

    # keys check（余計なキーがあると後工程が壊れるので厳しめ）
    required_keys = set(ENTRY_SCHEMA.keys())
    if set(e.keys()) != required_keys:
        return False

    _id = e.get("id")
    if not isinstance(_id, str) or not _id or _id in existing_ids:
        return False

    if e.get("domain") != domain:
        return False

    k = e.get("kind")
    if k not in ALLOWED_KINDS:
        return False

    # type checks
    for arr_key in ["prerequisites", "yields", "patterns", "links"]:
        if not isinstance(e.get(arr_key), list):
            return False

    ref = e.get("refutation")
    if ref is not None and not isinstance(ref, str):
        return False

    # text fields
    for s_key in ["title", "statement"]:
        if not isinstance(e.get(s_key), str) or not e.get(s_key).strip():
            return False

    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="nemotron-3-nano:30b")
    ap.add_argument("--total_per_domain", type=int, default=240)
    ap.add_argument("--per_batch", type=int, default=20)
    ap.add_argument("--max_empty_batches", type=int, default=30)
    args = ap.parse_args()

    existing_ids, domain_counts = load_existing(args.out)
    print(f"[INIT] existing ids: {len(existing_ids)}")

    for domain in DOMAINS:
        target = int(args.total_per_domain)
        mined = int(domain_counts.get(domain, 0))
        print(f"\n[DOMAIN] {domain} target={target} (already={mined})")

        if mined >= target:
            print("[SKIP] already satisfied")
            continue

        empty_batches = 0

        while mined < target:
            need = min(int(args.per_batch), target - mined)

            # 既存IDを少し見せる（プロンプトの肥大化を防ぐため）
            existing_sample = list(existing_ids)[:80]

            prompt = build_prompt(domain, need, existing_sample)
            raw = ollama_generate(args.model, prompt)

            entries_raw = extract_json_array(raw)
            if not entries_raw:
                empty_batches += 1
                print(f"[WARN] batch produced 0 usable entries (empty_batches={empty_batches}), retrying…")
                if empty_batches >= int(args.max_empty_batches):
                    raise RuntimeError(
                        f"Too many empty batches for {domain}. "
                        f"Try lowering --per_batch (e.g. 10) or increasing num_predict, or check model output."
                    )
                continue

            # validate & append
            added = 0
            with open(args.out, "a", encoding="utf-8") as f:
                for e in entries_raw:
                    if validate_entry(e, domain, existing_ids):
                        f.write(json.dumps(e, ensure_ascii=False) + "\n")
                        existing_ids.add(e["id"])
                        added += 1

            if added == 0:
                empty_batches += 1
                print(f"[WARN] 0 valid entries after validation (empty_batches={empty_batches}), retrying…")
                continue

            mined += added
            domain_counts[domain] = mined
            empty_batches = 0
            print(f"[OK] +{added} entries (mined {mined}/{target})")

    print("\n[DONE] mining complete")


if __name__ == "__main__":
    main()