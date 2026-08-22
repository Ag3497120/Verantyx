"""What wiring observed negation into ingest WOULD write. Nothing is stored.

Runs the proposed rule over a slice of real jawiki lead sentences and
reports the four quantities the pre-registration
(`docs/PREREGISTERED_2026-08-16_polarity_ingest.md`) fixed before any
result was seen. The store is not opened for writing, so P2 (purely
additive) is satisfied by construction here and must be re-checked when
the write actually lands.

G0 is enforced first and hard. Without fugashi the existence gate knows
only ある/いる/する/できる/来る/である and the lexicalized-ない list, so
almost every negation goes silent — measured today:

    python3     水が流れない。 → positive, observed ()
    python3.11  水が流れない。 → negative, observed (¬流れる)

A run under the wrong interpreter produces a small, plausible, entirely
wrong number. That is worse than an error, so it is an error.

    python3.11 tools/measure_polarity_ingest.py [N]
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def gate_g0() -> str:
    try:
        import fugashi  # noqa: F401
        import unidic_lite  # noqa: F401
    except Exception as exc:  # pragma: no cover - the whole point
        raise SystemExit(
            "G0 UNMET: fugashi/unidic-lite not importable (%s).\n"
            "This run is VOID, not a null result — the existence gate "
            "would silence nearly every negation and the numbers would "
            "look like 'no effect'." % exc)
    return "%d.%d.%d" % sys.version_info[:3]


def main(n: int = 10000) -> int:
    py = gate_g0()

    from verantyx.lang import ja_chosen_core
    from verantyx.meaning_index import connection
    from verantyx.polarity import (ObservedNegation, observe_negation,
                                   polarity_key)

    conn = connection()
    if conn is None:
        raise SystemExit("meaning_index.db not built")

    rows = conn.execute("SELECT k, v FROM defs LIMIT ?", (n,)).fetchall()

    seen_sentences = 0
    with_negation = 0
    facets: list[tuple[str, str]] = []          # (core, ¬lemma)
    lemmas: Counter = Counter()
    cores: set = set()
    verdict_positive_but_observed = 0
    no_core = 0

    for _title, text in rows:
        sent = (text or "").strip()
        if not sent:
            continue
        seen_sentences += 1
        reading = observe_negation(sent)
        if not reading.observed:
            continue
        with_negation += 1
        if reading.verdict == "positive":
            # The imperative/attributive case the pre-registration named
            # in advance: testimony exists but the sentence did not fold
            # negative. Counted, not discarded.
            verdict_positive_but_observed += 1
        core = ja_chosen_core(sent)
        if not core:
            no_core += 1
            continue
        cores.add(core)
        for obs in reading.observed:
            if not isinstance(obs, ObservedNegation):
                continue
            key = polarity_key(obs)              # raises on InferredNegation
            facets.append((core, key))
            lemmas[obs.lemma] += 1

    # P1 — independently re-check every lemma against the gate rather
    # than trusting that the reader already did. A pass line verified by
    # the same code that produced the data is not a pass line.
    from verantyx.polarity import _lemma_is_real  # noqa: PLC2701
    fabricated = sorted({lm for lm in lemmas if not _lemma_is_real(lm)})

    out = {
        "G0": {"interpreter": py, "fugashi": True},
        "slice": {"requested": n, "sentences_read": seen_sentences},
        "Q1_negation_rate": {
            "sentences_with_observed_negation": with_negation,
            "rate": round(with_negation / max(seen_sentences, 1), 5),
        },
        "Q2_top_lemmas": lemmas.most_common(20),
        "Q3_cores_gaining_a_mark": len(cores),
        "facets_that_would_be_written": len(facets),
        "P1_fabricated_lemmas": fabricated,
        "P1": "PASS" if not fabricated else "FAIL",
        "named_in_advance": {
            "observed_but_verdict_positive": verdict_positive_but_observed,
            "note": "imperative/attributive negation — the instruction "
                    "side must read `observed`, never `verdict`",
        },
        "dropped_no_identifiable_core": no_core,
        "wrote_to_store": False,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if not fabricated else 1


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 10000))
