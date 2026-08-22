"""Find real subject pairs that can license 「しかし」.

The licence is narrow on purpose: one side must carry an observed ¬T
and the other must assert the same T. Nothing infers opposition from
absence — 「Aは実測あり / Bは実測なし」 is a turn (一方), never a
contrast. This walks the polarity-marked profiles for pairs that
actually meet the licence, so the first rendered opposition in this
project is a found one, not a constructed demonstration.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BUILD = Path.home() / "Projects" / "vera-corpus" / "build"
POLAR = BUILD / "predicate_profiles_polar.json"


def main() -> int:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    data = json.loads(POLAR.read_text(encoding="utf-8"))
    data.pop("extractor", None)

    negators: dict[str, list[str]] = defaultdict(list)
    asserters: dict[str, list[str]] = defaultdict(list)
    for subject, rec in data.items():
        if not isinstance(rec, dict):
            continue
        preds = rec.get("predicates") or {}
        if len(preds) < 3:          # the diff's own min_profile
            continue
        for key in preds:
            if key.startswith("¬"):
                negators[key[1:]].append(subject)
            else:
                asserters[key].append(subject)

    rows = []
    for pred, negs in sorted(negators.items(),
                             key=lambda kv: -len(kv[1])):
        pos = asserters.get(pred) or []
        if not pos:
            continue
        rows.append({"predicate": pred,
                     "negators": len(negs), "asserters": len(pos),
                     "example_pair": [negs[0], pos[0]]})
        if len(rows) >= limit:
            break

    print(json.dumps({"verdict": "ANSWER",
                      "licensable_predicates": len(rows),
                      "rows": rows}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
