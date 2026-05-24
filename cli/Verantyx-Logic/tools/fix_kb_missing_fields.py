import argparse
import json
from pathlib import Path


DEFAULTS = {
    "prerequisites": [],
    "yields": [],
    "patterns": [],
    "links": [],
}


def fix_file(in_path, out_path, log_path):
    total = 0
    fixed = 0

    with open(in_path, "r", encoding="utf-8") as src, open(out_path, "w", encoding="utf-8") as dst:
        for line in src:
            line = line.strip()
            if not line:
                continue
            total += 1
            obj = json.loads(line)
            changed = False
            for k, v in DEFAULTS.items():
                if k not in obj:
                    obj[k] = list(v)
                    changed = True
            if changed:
                fixed += 1
            dst.write(json.dumps(obj, ensure_ascii=False) + "\n")

    if log_path:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "input": str(in_path),
                        "output": str(out_path),
                        "total": total,
                        "fixed": fixed,
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
    fix_file(args.in_path, args.out_path, args.log_path)


if __name__ == "__main__":
    main()
