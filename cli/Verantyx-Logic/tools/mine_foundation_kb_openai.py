import os
import json
import time
import argparse
from typing import List, Dict, Set
from tqdm import tqdm
from openai import OpenAI

DOMAINS = [
    "propositional_logic",
    "first_order_logic",
    "model_theory",
    "group_theory",
    "ring_theory",
    "topology",
    "category_theory",
    "computational_complexity",
    "graph_theory",
]

ENTRY_SCHEMA = {
    "id": "",
    "domain": "",
    "kind": "",  # definition | axiom | theorem | rule | counterexample_schema
    "title": "",
    "statement": "",
    "prerequisites": [],
    "yields": [],
    "refutation": None,
    "patterns": [],
    "links": [],
}

SYSTEM_PROMPT = """
You are generating entries for a formal mathematics knowledge base.

Rules:
- Output MUST be a JSON array only (no prose).
- Each entry MUST follow this schema exactly:
  {
    "id": string,
    "domain": string,
    "kind": "definition" | "axiom" | "theorem" | "rule" | "counterexample_schema",
    "title": string,
    "statement": string,
    "prerequisites": string[],
    "yields": string[],
    "refutation": string | null,
    "patterns": string[],
    "links": string[]
  }

- Entries must be mathematically correct.
- Include counterexample_schema entries whenever possible.
- IDs must be unique.
"""

def load_existing_ids(path: str) -> Set[str]:
    ids = set()
    if not os.path.exists(path):
        return ids
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
                ids.add(obj["id"])
            except Exception:
                pass
    return ids

def call_openai_batch(
    client: OpenAI,
    model: str,
    domain: str,
    n: int,
    seed_hint: str,
    max_retries: int = 5,
) -> List[Dict]:
    user_prompt = f"""
Generate {n} high-quality knowledge base entries for the domain: {domain}.

Constraints:
- Mix kinds: definition, axiom, theorem, rule, counterexample_schema
- Use IDs prefixed with domain short name
- Avoid trivial duplicates
- Seed hint: {seed_hint}
"""
    last_err = None
    for attempt in range(max_retries):
        try:
            resp = client.responses.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.4,
                max_output_tokens=6000,
            )
            text = resp.output_text
            data = json.loads(text)
            if isinstance(data, list):
                return data
        except Exception as e:
            last_err = e
            time.sleep(1 + attempt)
    raise RuntimeError(f"OpenAI call failed: {last_err}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--total", type=int, default=20000)
    parser.add_argument("--per_batch", type=int, default=50)
    args = parser.parse_args()

    client = OpenAI()
    existing_ids = load_existing_ids(args.out)
    print(f"[INIT] existing ids: {len(existing_ids)}")

    per_domain = args.total // len(DOMAINS)

    with open(args.out, "a", encoding="utf-8") as fout:
        for domain in DOMAINS:
            mined = 0
            seed = "core"
            print(f"\n[DOMAIN] {domain} target={per_domain}")
            pbar = tqdm(total=per_domain)

            while mined < per_domain:
                batch_n = min(args.per_batch, per_domain - mined)
                entries = call_openai_batch(
                    client=client,
                    model=args.model,
                    domain=domain,
                    n=batch_n,
                    seed_hint=seed,
                )

                usable = []
                for e in entries:
                    if e.get("id") and e["id"] not in existing_ids:
                        existing_ids.add(e["id"])
                        usable.append(e)

                if not usable:
                    seed = f"retry-{time.time()}"
                    continue

                for e in usable:
                    fout.write(json.dumps(e, ensure_ascii=False) + "\n")

                mined += len(usable)
                pbar.update(len(usable))
                seed = usable[-1]["id"]
                time.sleep(0.2)  # レート制御

            pbar.close()

    print("\n[DONE] Mining completed.")

if __name__ == "__main__":
    main()