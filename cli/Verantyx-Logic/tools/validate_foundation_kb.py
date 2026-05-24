import argparse
import json
from pathlib import Path


REQUIRED_FIELDS = {
    "id": str,
    "domain": str,
    "kind": str,
    "title": str,
    "statement": str,
    "prerequisites": list,
    "yields": list,
    "refutation": (dict, type(None), str),
    "patterns": list,
    "links": list,
}


def _type_ok(value, expected):
    if isinstance(expected, tuple):
        return isinstance(value, expected)
    return isinstance(value, expected)


def validate_kb(path, report_path):
    total = 0
    ok = 0
    bad = 0
    errors = []
    missing_refutation = 0
    wrong_types = 0
    missing_fields = 0

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                obj = json.loads(line)
            except Exception as e:
                bad += 1
                errors.append({"line": total, "error": f"json_decode:{e}"})
                continue

            entry_ok = True
            for k, t in REQUIRED_FIELDS.items():
                if k not in obj:
                    entry_ok = False
                    missing_fields += 1
                    errors.append({"line": total, "error": f"missing_field:{k}"})
                    continue
                if not _type_ok(obj[k], t):
                    entry_ok = False
                    wrong_types += 1
                    errors.append({"line": total, "error": f"type_mismatch:{k}"})

            if obj.get("kind") == "counterexample_schema" and not obj.get("refutation"):
                entry_ok = False
                missing_refutation += 1
                errors.append({"line": total, "error": "missing_refutation"})

            if entry_ok:
                ok += 1
            else:
                bad += 1

    report = {
        "input": str(path),
        "total": total,
        "ok": ok,
        "bad": bad,
        "missing_fields": missing_fields,
        "wrong_types": wrong_types,
        "missing_refutation": missing_refutation,
        "sample_errors": errors[:200],
    }

    if report_path:
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", required=True)
    ap.add_argument("--report", dest="report_path", default="")
    args = ap.parse_args()
    report = validate_kb(args.in_path, args.report_path)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
