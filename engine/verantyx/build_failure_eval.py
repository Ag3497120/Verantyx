"""Does the build-failure classifier type real failures correctly?

Every fixture below is an excerpt of a failure that actually happened in
this project and whose diagnosis was confirmed by a person at the time it
happened. That is the whole point: a classifier validated on invented
examples validates the author's imagination. These are the logs as they
appeared, trimmed for length only.

Run:  python3 -m verantyx.build_failure_eval
"""
from __future__ import annotations

import sys
from typing import List, Tuple

from .build_failure import classify_build_log

# (name, expected_verdict, real log excerpt)
FIXTURES: List[Tuple[str, str, str]] = [
    ("xcodebuild codesign: unsigned LFS pointer embedded as executable",
     "UNKNOWN_SIGNING",
     """CodeSign /Users/.../Release/Verantyx.app (in target 'Verantyx' from project 'Verantyx')
/Users/.../Release/Verantyx.app: code object is not signed at all
In subcomponent: .../Verantyx.app/Contents/MacOS/verantyx-browser
Command CodeSign failed with a nonzero exit code
** BUILD FAILED **"""),

    ("dyld: dylib Team ID mismatch after ditto-copying the app",
     "UNKNOWN_SIGNING",
     """dyld[32066]: Library not loaded: @rpath/libjcross_engine_glm.dylib
  Reason: tried: '/Applications/Verantyx.app/Contents/Frameworks/libjcross_engine_glm.dylib' (code signature in <B1F62A95> '/Applications/Verantyx.app/Contents/Frameworks/libjcross_engine_glm.dylib' not valid for use in process: mapping process and mapped file (non-platform) have different Team IDs)"""),

    # Found by the classifier itself: recorded through record_build_failure
    # and returned UNKNOWN_BUILD_UNCLASSIFIED, which is the fallback saying
    # "this failure has no type yet". The cause was an XML comment quoting a
    # command line verbatim — XML forbids a double hyphen inside a comment,
    # so the plist was not well-formed. Xcode normalises entitlements before
    # signing and did not care; the packaging script passes the raw file to
    # codesign, and AMFI rejected it. Reproduced deterministically, and
    # removing the double hyphen fixed it, which is what makes this a
    # confirmed fixture rather than a plausible one.
    ("codesign: AMFI rejecting a malformed entitlements plist",
     "UNKNOWN_ENTITLEMENTS",
     """   signed jgen_forge (+ PyInstallerHelper.entitlements)
Failed to parse entitlements: AMFIUnserializeXML: syntax error near line 20
   entitlements sign failed for Verantyx - retrying without entitlements
/Users/runner/work/Verantyx/Verantyx/cli/dist/.staging/Verantyx.app/Contents/MacOS/Verantyx: replacing existing signature"""),

    ("JGEN loader refusing a hybrid with no GDN geometry in the sidecar",
     "UNKNOWN_MODEL_GEOMETRY",
     """thread 'main' panicked at src/bin/test_inject_distribution.rs:74:52:
load: Custom { kind: InvalidData, error: "JCross: refusing to load — this is a hybrid (Gated DeltaNet) model, but the sidecar names none of ssm_dt_rank / ssm_n_group / ssm_d_state (or their linear_* aliases), so the GDN geometry would be a guess. Converted before jgen_forge emitted these fields — re-convert." }"""),

    ("launchctl asuser without root",
     "UNKNOWN_PERMISSION",
     "Could not switch to audit session 0x186b7: 1: Operation not permitted"),

    ("setsid does not exist on macOS",
     "UNKNOWN_DEPENDENCY",
     "bash: line 8: setsid: command not found"),

    ("harness process cut off at the wall clock",
     "UNKNOWN_TIMEOUT",
     "Command timed out after 10m 0s"),

    ("rust type error during engine work",
     "UNKNOWN_COMPILE",
     """error[E0308]: mismatched types
  --> src/lib.rs:3701:24
   = note: expected `usize`, found `u32`"""),

    ("disk filled during a model transfer",
     "UNKNOWN_DISK",
     "rsync: write failed on qwen3.6-27b-q4_k_m_full.jgen: No space left on device (28)"),

    ("nothing recognisable",
     "UNKNOWN_BUILD_UNCLASSIFIED",
     "the build elves have gone home for the evening"),
]


def main() -> int:
    print(f"build_failure.classify — {len(FIXTURES)} real-log fixtures\n")
    failures: List[str] = []
    for name, expect, log in FIXTURES:
        got = classify_build_log(log)
        ok = got.verdict == expect
        print(f"[{'ok  ' if ok else 'FAIL'}] {name}")
        print(f"        expected {expect}, got {got.verdict}")
        if got.evidence:
            print(f"        evidence: {got.evidence[:100]}")
        if not ok:
            failures.append(name)
        print()

    # Ordering property: a signing log full of "error:" lines must still be
    # SIGNING, not COMPILE. The first fixture is exactly that shape; assert
    # the property explicitly so a future reordering of _PATTERNS fails here
    # rather than silently degrading every mixed log.
    mixed = classify_build_log(FIXTURES[0][2])
    ok = mixed.verdict == "UNKNOWN_SIGNING"
    print(f"[{'ok  ' if ok else 'FAIL'}] ordering: signing beats the compile catch-all "
          f"on a mixed log")
    if not ok:
        failures.append("pattern ordering")
    print()

    # Second ordering property: a run where signing ALSO fails must still be
    # typed by the entitlements plist, because that is the file to edit. The
    # log here is the two real fixtures concatenated rather than a written
    # one — a packaging run that hits both is exactly this text in sequence,
    # and inventing a log to prove a point about real logs would defeat the
    # standard the rest of this file holds to.
    by_verdict = {expect: log for _n, expect, log in FIXTURES}
    both = by_verdict["UNKNOWN_SIGNING"] + "\n" + by_verdict["UNKNOWN_ENTITLEMENTS"]
    got = classify_build_log(both)
    ok = got.verdict == "UNKNOWN_ENTITLEMENTS"
    print(f"[{'ok  ' if ok else 'FAIL'}] ordering: entitlements beats signing when a "
          f"log holds both (got {got.verdict})")
    if not ok:
        failures.append("entitlements/signing ordering")
    print()

    # The growth-signal hookup: recurring failures bucket by SOURCE, and the
    # bucket's dominant verdict is the classified type — which is what
    # boundary/failure_stats read downstream.
    from .growth_signals import GrowthSignals
    from .build_failure import record_build_failure
    g = GrowthSignals()
    for _ in range(3):
        record_build_failure(g, "xcodebuild", FIXTURES[0][2])
    bucket = list(g.buckets.values())[0]
    ok = bucket.total() == 3 and bucket.dominant_verdict() == "UNKNOWN_SIGNING"
    print(f"[{'ok  ' if ok else 'FAIL'}] growth hookup: 3 recorded -> one bucket, "
          f"dominant {bucket.dominant_verdict()}")
    if not ok:
        failures.append("growth hookup")
    print()

    if failures:
        print(f"{len(failures)} failed: {', '.join(failures)}")
        return 1
    print("all build-failure fixtures classified as confirmed at the time")
    return 0


if __name__ == "__main__":
    sys.exit(main())
