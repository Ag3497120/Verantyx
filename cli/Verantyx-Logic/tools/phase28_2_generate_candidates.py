#!/usr/bin/env python3
# tools/phase28_2_generate_candidates.py

import argparse, json, random, os

def has_pattern(entry, pat: str) -> bool:
    pats = entry.get("patterns", [])
    return isinstance(pats, list) and pat in pats

def any_prefix(entry, prefix: str) -> bool:
    pats = entry.get("patterns", [])
    if not isinstance(pats, list):
        return False
    return any(p.startswith(prefix) for p in pats)

def should_target(entry) -> bool:
    """
    Phase 28.2 target policy:
      - counterexample_schema only
      - skip already min_verified:true
      - include:
          a) min_verified tag missing
          b) min_verified:unknown
          c) needs_review
          d) no refutation_candidate yet
          e) refutation is missing/weak
    """
    if entry.get("kind") != "counterexample_schema":
        return False

    if has_pattern(entry, "min_verified:true"):
        return False

    no_min_tag = not any_prefix(entry, "min_verified:")
    unknown = has_pattern(entry, "min_verified:unknown")
    needs_review = has_pattern(entry, "needs_review") or has_pattern(entry, "needs_review:true")
    no_candidate = "refutation_candidate" not in entry

    ref = entry.get("refutation")
    ref_weak = (ref is None) or (not isinstance(ref, dict)) or (
        isinstance(ref, dict) and not {"domain","structure","dropped_assumption","failure_point"}.issubset(ref.keys())
    )

    return no_min_tag or unknown or needs_review or no_candidate or ref_weak

def pick_template(entry, templates_obj):
    domain = entry.get("domain", "unknown")
    templates = templates_obj["templates"]

    candidates = []
    for _, t in templates.items():
        if t["template"].get("domain") == domain:
            candidates.append(t)

    if not candidates:
        # fallback: any template
        candidates = list(templates.values())
        if not candidates:
            return None

    text = " ".join([
        entry.get("title", ""),
        entry.get("statement", ""),
        " ".join(entry.get("patterns", []) if isinstance(entry.get("patterns"), list) else [])
    ]).lower()

    scored = []
    for t in candidates:
        dropped = str(t["template"].get("dropped_assumption", "")).lower()
        failure = str(t["template"].get("failure_point", "")).lower()
        score = 0
        if dropped and dropped in text: score += 2
        if failure and failure in text: score += 2
        scored.append((score, t))

    scored.sort(key=lambda x: x[0], reverse=True)
    best = scored[0][0]
    top = [t for s, t in scored if s == best]
    return random.choice(top)

def build_candidate(entry, templ):
    base = templ["template"]
    return {
        "domain": base.get("domain", entry.get("domain")),
        "dropped_assumption": base.get("dropped_assumption"),
        "failure_point": base.get("failure_point"),
        "structure": base.get("structure_schema", {}),
        "source": "phase28.2_template",
        "template_sig": templ.get("signature"),
        "template_examples": templ.get("examples", [])[:3],
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", required=True)
    ap.add_argument("--templates", required=True)
    ap.add_argument("--out_patches", required=True)
    ap.add_argument("--limit", type=int, default=12000)
    args = ap.parse_args()

    with open(args.templates, "r", encoding="utf-8") as f:
        templates_obj = json.load(f)

    os.makedirs(os.path.dirname(args.out_patches), exist_ok=True)
    if os.path.exists(args.out_patches):
        os.remove(args.out_patches)

    wrote = 0
    with open(args.kb, "r", encoding="utf-8") as f, open(args.out_patches, "a", encoding="utf-8") as w:
        for line in f:
            if wrote >= args.limit:
                break
            if not line.strip():
                continue
            e = json.loads(line)

            if not should_target(e):
                continue

            templ = pick_template(e, templates_obj)
            if not templ:
                continue

            cand = build_candidate(e, templ)

            patch = {
                "id": e["id"],
                "op": "merge",
                "fields": {
                    "refutation_candidate": cand,
                    "patch_note": "Phase 28.2 template candidate injected",
                }
            }
            w.write(json.dumps(patch, ensure_ascii=False) + "\n")
            wrote += 1

    print(f"[OK] patches={wrote} -> {args.out_patches}")

if __name__ == "__main__":
    main()
