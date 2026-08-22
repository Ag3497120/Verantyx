"""Global token mass — the sovereign-wide half of a structural signature.

Why this exists
---------------
`structural_diff` compares two subjects through a k=8 neighbourhood, and
that locality was a deliberate trade: "scanning 300k cores per query is
unnecessary". The trade leaks. Measured on りんご/電気:

    のこと   local a_ratio 0.286   ranked 1st in only_a
    果実     local a_ratio 0.143   ranked below it

From inside a window of eight, both look identical in kind — attested on
A, unattested on B. Across the whole sovereign they are not remotely
alike:

    のこと    17,709 定義文 (1.25%)
    の一種    12,510        (0.88%)
    果実         257        (0.02%)      ← 69× rarer than のこと

「のこと」 distinguishes nothing; it is how Japanese definitions are
written. 「果実」 is most of what りんご IS. Local ratio cannot tell them
apart, and no amount of care inside the window will.

The cost argument that killed the whole-sovereign version assumed the
scan happens per query. It does not have to. Presence is counted ONCE,
here, into one integer per token; a query then divides by a stored
constant. Insertion pays the tax, lookup stays local, and the sovereign
gets to say — as it should — that a token appearing everywhere carries
no information about anywhere.

What this does NOT fix
----------------------
Layer ③ (kin) draws neighbours from surface form, which is how カベンゴ
and サンゴ ended up beside りんご. Dividing by global mass demotes them;
it does not make them kin. That is the lattice's measured 4% ceiling and
it is a different defect with a different repair.

Scope
-----
Predicates only (layers ① and ②), because `profiles` already stores them
as {token: count} and that is exactly where the 定型句 problem sits. The
definition/facet layers need the diff's own tokenizer to be counted
consistently and are left alone rather than counted a second, different
way — two notions of "how often" in one store is the pooling mistake.

This writes a TABLE. It changes no ranking by itself: `structural_diff`
must be told to use it, and that is a scoring change which goes through
pre-registration and a prospectus first.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verantyx.meaning_index import INDEX  # noqa: E402

TABLE = "global_mass"


def build(path: Path = INDEX) -> dict:
    if not Path(path).is_file():
        return {"verdict": "UNKNOWN_INDEX_ABSENT", "path": str(path)}

    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("DROP TABLE IF EXISTS %s" % TABLE)
    conn.execute(
        "CREATE TABLE %s (k TEXT PRIMARY KEY, df INTEGER NOT NULL)" % TABLE)

    df: dict = {}
    cores = 0
    t0 = time.time()
    for (_k, v) in conn.execute("SELECT k, v FROM profiles"):
        cores += 1
        try:
            preds = (json.loads(v) or {}).get("predicates") or {}
        except Exception:
            continue
        # Document frequency, not term frequency: in how many cores does
        # this predicate appear at all. A token repeated ten times inside
        # one definition is still one core's worth of evidence that the
        # token is common, and counting occurrences would let a single
        # verbose article inflate a token into "ubiquitous".
        for tok in preds:
            df[tok] = df.get(tok, 0) + 1
        if cores % 200000 == 0:
            print("  %,d 核 … %.0fs" % (cores, time.time() - t0)
                  if False else "  %d 核 … %.0fs" % (cores, time.time() - t0))

    conn.executemany("INSERT INTO %s (k, df) VALUES (?, ?)" % TABLE,
                     df.items())
    # The denominator lives in the same table under a key no predicate can
    # collide with, so a reader can never have the counts without it.
    conn.execute("INSERT INTO %s (k, df) VALUES (?, ?)" % TABLE,
                 ("\x00__cores__", cores))
    conn.commit()

    top = sorted(df.items(), key=lambda kv: -kv[1])[:12]
    conn.close()
    return {"verdict": "BUILT", "cores": cores, "tokens": len(df),
            "seconds": round(time.time() - t0, 1),
            "most_common": [{"token": t, "df": n,
                             "share": round(100.0 * n / cores, 3)}
                            for t, n in top]}


if __name__ == "__main__":
    r = build()
    print(json.dumps(r, ensure_ascii=False, indent=2))
