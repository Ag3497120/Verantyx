"""Structural and behavioural checks over every registered failure domain.

Two kinds of check, and the structural ones matter more than they look:
they are what keeps a seeded pack from quietly acquiring powers reserved
for verified ones. The rules enforced here ARE the maturity contract:

  R1  every pattern verdict has a remedy, every remedy has a pattern —
      an unclassifiable remedy or an unfixable verdict is dead weight
  R2  remedy kinds and verify methods come from the closed vocabularies
  R3  auto_calibratable=True only with kind="raise_limit", and ONLY in a
      maturity="verified" pack — a guess wearing a regex does not get to
      propose numbers
  R4  a verified pack has at least one provenance="confirmed" fixture;
      promotion is by evidence, not by editing a string
  R5  every fixture classifies as labelled (patterns-outer priority applies,
      so a later pack edit that shadows an earlier verdict fails here)
  R6  every pack's fallback differs from all its verdicts

Run:  python3 -m verantyx.failure_domains_eval
"""
from __future__ import annotations

import sys
from typing import List

from .failure_domains import (all_domains, load_errors, record_typed_failure,
                              validate)
from .growth_signals import GrowthSignals


def main() -> int:
    domains = all_domains()
    print(f"failure domains — {len(domains)} packs "
          f"({sum(1 for d in domains if d.maturity == 'verified')} verified, "
          f"{sum(1 for d in domains if d.maturity == 'seeded')} seeded)\n")

    failures: List[str] = []

    # Any load-time rejection is a failure of this suite: a pack a domain
    # expert edited into an invalid state must be loud, and a registry that
    # silently drops it looks identical to one where the pack was never
    # written.
    for err in load_errors():
        print(f"[FAIL] load error: {err}")
        failures.append(f"load: {err}")
    if load_errors():
        print()

    for dom in domains:
        # One validator, shared with every load path — the eval must not be
        # able to pass rules the loader does not enforce, or vice versa.
        errs: List[str] = validate(dom)
        confirmed = sum(1 for f in dom.fixtures if f.provenance == "confirmed")
        mark = "ok  " if not errs else "FAIL"
        origin = "data" if dom.source_path else "code"
        provs = sorted(set(dom.provenance.values())) or ["(code)"]
        print(f"[{mark}] {dom.name:20} {dom.maturity:9} {origin:5} "
              f"{len(dom.patterns):2d} verdicts, {len(dom.fixtures)} fixtures "
              f"({confirmed} confirmed)  {','.join(provs)[:44]}")
        for e in errs:
            print(f"        {e}")
            failures.append(f"{dom.name}: {e}")
        if not errs and dom.maturity == "seeded" and confirmed == 0:
            print(f"        seeded: no confirmed incident yet — classifies and "
                  f"counts, may not calibrate")
    print()

    # Behavioural: the shared recording path buckets by domain:source and the
    # verdict is the classified one — the contract failure_stats reads.
    g = GrowthSignals()
    out = record_typed_failure(
        g, "search_zero", "shop_search",
        "query=laufschuhe results=0 results_unfiltered=44 active_filters=size:49")
    bucket = list(g.buckets.values())[0]
    ok = (out["verdict"] == "UNKNOWN_OVERFILTER"
          and bucket.dominant_verdict() == "UNKNOWN_OVERFILTER"
          and bucket.normalized)  # bucketed under the domain:source key
    print(f"[{'ok  ' if ok else 'FAIL'}] recording path: seeded pack classifies and "
          f"buckets ({out['verdict']}), maturity surfaced as {out['maturity']!r}")
    if not ok:
        failures.append("recording path")

    unknown = record_typed_failure(g, "no_such_domain", "x", "y")
    ok = "error" in unknown
    print(f"[{'ok  ' if ok else 'FAIL'}] unknown domain is a typed error, not a guess")
    if not ok:
        failures.append("unknown domain")
    print()

    if failures:
        print(f"{len(failures)} failed")
        return 1
    print("all packs satisfy the maturity contract; all fixtures classify as labelled")
    return 0


if __name__ == "__main__":
    sys.exit(main())
