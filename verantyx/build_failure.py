"""Typed classification of build / CI / conversion failures.

"CI failed" is the log entry this whole failure-typing exercise exists to
replace. A build can fail because a dependency is missing, because a test is
red, because the disk filled, because codesign rejected a Team ID, because a
model conversion lacked its GDN geometry — and every one of those has a
different remedy owned by a different kind of fix. A system that keeps only
"failed" learns nothing from a hundred failures; one that keeps the type can
say "signing dominates this month" and mean something.

The patterns below are not invented. Each one is anchored to a failure that
actually happened in this project's own history and whose diagnosis was
confirmed at the time — the fixtures in `build_failure_eval` are excerpts of
those real logs. That is the standard the boundary-classifier work set:
a classifier is trusted only as far as the cases it has been run against,
and a pattern with no confirmed example is a guess wearing a regex.

Order matters and is part of the contract: earlier entries are more specific.
`UNKNOWN_COMPILE` is nearly a catch-all for "error:" and must come last of
the error-shaped patterns, or it eats the signing/dependency cases whose logs
also contain the word.

The verdicts deliberately reuse the UNKNOWN_* convention so these failures
flow into the SAME growth_signals / boundary / failure_stats machinery as
every other typed unknown — one taxonomy, not a parallel one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

# (verdict, compiled_pattern, note) — first match wins, order is meaningful.
_PATTERNS: List[Tuple[str, "re.Pattern[str]", str]] = [
    # A malformed entitlements plist, which is NOT a signing-identity problem
    # even though it surfaces during signing. codesign hands the file to AMFI,
    # whose parser is stricter than Xcode's: Xcode normalises the plist first,
    # so a file that builds locally can still be rejected by a packaging
    # script that passes the raw XML through.
    #
    # Above UNKNOWN_SIGNING on purpose. The remedy is to edit a plist, not to
    # touch a certificate or a Team ID, and a fuller log — where codesign then
    # reports its own failure — would otherwise be typed as generic signing
    # and send the reader to the wrong file entirely.
    ("UNKNOWN_ENTITLEMENTS", re.compile(
        r"Failed to parse entitlements|AMFIUnserializeXML|"
        r"entitlements sign failed",
        re.IGNORECASE), "entitlements plist malformed — AMFI rejected it"),
    # Signing / notarisation. Two real shapes from this project: xcodebuild's
    # CodeSign step refusing an unsigned subcomponent (a Git-LFS pointer file
    # embedded as an executable), and dyld refusing a dylib whose signature
    # carries a different Team ID than the app that loads it.
    ("UNKNOWN_SIGNING", re.compile(
        r"code object is not signed|codesign.*failed|"
        r"different Team IDs|code signature in .* not valid",
        re.IGNORECASE), "codesign / dyld signature rejection"),
    # JGEN conversion refusals — the engine's own honesty gate. Real shape:
    # a hybrid model whose sidecar names none of the GDN geometry fields.
    ("UNKNOWN_MODEL_GEOMETRY", re.compile(
        r"refusing to load.*(?:ssm_dt_rank|GDN geometry)|"
        r"names none of ssm_dt_rank",
        re.IGNORECASE), "hybrid sidecar missing GDN geometry — re-convert"),
    ("UNKNOWN_MODEL_TOKENIZER", re.compile(
        r"tokenizer.*(?:not found|missing|No such file)|"
        r"missing.*tokenizer\.json",
        re.IGNORECASE), "tokenizer sidecar missing or path stale"),
    ("UNKNOWN_DISK", re.compile(
        r"No space left on device|NSFileWriteOutOfSpaceError|disk full",
        re.IGNORECASE), "out of disk"),
    ("UNKNOWN_PERMISSION", re.compile(
        r"Operation not permitted|Permission denied|EACCES|EPERM",
        re.IGNORECASE), "OS permission refusal"),
    ("UNKNOWN_TIMEOUT", re.compile(
        r"timed? ?out|Command timed out|ETIMEDOUT",
        re.IGNORECASE), "hit a time limit"),
    ("UNKNOWN_DEPENDENCY", re.compile(
        r"command not found|No such module|cannot find crate|"
        r"error\[E0433\]|ModuleNotFoundError|npm ERR!.*missing|"
        r"Library not loaded",
        re.IGNORECASE), "missing tool, module, or library"),
    ("UNKNOWN_TEST", re.compile(
        r"Test Suite .* failed|test result: FAILED|XCTAssert|"
        r"\d+ tests?, \d+ failures|FAILED \(failures=",
        re.IGNORECASE), "tests ran and failed"),
    # Near-catch-all: must stay last.
    ("UNKNOWN_COMPILE", re.compile(
        r"error\[E\d+\]|error: .+|\*\* BUILD FAILED \*\*",
        re.IGNORECASE), "compiler/build error not matched above"),
]

FALLBACK = "UNKNOWN_BUILD_UNCLASSIFIED"


@dataclass
class BuildFailure:
    verdict: str
    #: The first line that matched — the evidence a reviewer sees, so a
    #: misclassification is inspectable instead of silent.
    evidence: str
    note: str


def classify_build_log(log_text: str) -> BuildFailure:
    """Highest-priority pattern found ANYWHERE in the log wins; the matching
    line is kept as evidence.

    Patterns are the outer loop and lines the inner loop, and that order is
    the fix for a bug this classifier's own eval caught on a real log: dyld's
    Team-ID rejection prints `Library not loaded:` on line one (a dependency
    symptom) and the actual cause — `different Team IDs`, a signing failure —
    on line two. Scanning line-by-line let the ambiguous first-line symptom
    outrank the specific second-line cause, which is precisely the
    misdiagnosis a person made when this failure first happened. Priority
    must mean priority across the whole log, not within a line.
    """
    lines = [ln.strip() for ln in (log_text or "").splitlines() if ln.strip()]
    for verdict, pattern, note in _PATTERNS:
        for line in lines:
            if pattern.search(line):
                return BuildFailure(verdict=verdict,
                                    evidence=line[:240], note=note)
    return BuildFailure(verdict=FALLBACK, evidence="", note="no pattern matched")


def record_build_failure(growth, source: str, log_text: str) -> BuildFailure:
    """Classify and feed the shared growth-signal store.

    `source` is a stable label ("xcodebuild", "cargo", "jgen_convert", a CI
    job name) so recurrences bucket by pipeline rather than by log content —
    log text is far too volatile for normalize_query to bucket usefully.
    The bucket then flows through the SAME boundary/failure_stats path as
    every other typed unknown: no parallel bookkeeping.
    """
    failure = classify_build_log(log_text)
    growth.record_unknown(f"build:{source}", failure.verdict)
    return failure
