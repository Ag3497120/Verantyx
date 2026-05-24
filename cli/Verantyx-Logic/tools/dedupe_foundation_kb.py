import argparse
import json
from collections import OrderedDict
from pathlib import Path


def _merge_list(a, b):
    out = []
    seen = set()
    for x in (a or []):
        if x not in seen:
            seen.add(x)
            out.append(x)
    for x in (b or []):
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _merge_entries(base, other):
    merged = dict(base)
    merged["patterns"] = _merge_list(base.get("patterns"), other.get("patterns"))
    merged["prerequisites"] = _merge_list(base.get("prerequisites"), other.get("prerequisites"))
    merged["yields"] = _merge_list(base.get("yields"), other.get("yields"))
    merged["links"] = _merge_list(base.get("links"), other.get("links"))
    if merged.get("refutation") is None and other.get("refutation") is not None:
        merged["refutation"] = other.get("refutation")
    return merged


def dedupe_kb(in_path, out_path, log_path):
    seen = OrderedDict()
    dup_count = 0
    total = 0

    with open(in_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total += 1
            obj = json.loads(line)
            key = (
                obj.get("domain", ""),
                obj.get("kind", ""),
                (obj.get("statement") or "").strip(),
            )
            if key not in seen:
                seen[key] = obj
            else:
                seen[key] = _merge_entries(seen[key], obj)
                dup_count += 1

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for obj in seen.values():
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    if log_path:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "input": str(in_path),
                        "output": str(out_path),
                        "total_in": total,
                        "total_out": len(seen),
                        "duplicates_merged": dup_count,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", required=True)
    ap.add_argument("--out", dest="out_path", required=True)
    ap.add_argument("--log", dest="log_path", default="")
    args = ap.parse_args()
    dedupe_kb(args.in_path, args.out_path, args.log_path)


if __name__ == "__main__":
    main()
