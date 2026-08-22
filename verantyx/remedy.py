"""What to register so a refusal becomes an answer.

Every refusal here is typed, and each type has a different repair. An expert
looking at UNKNOWN_SUBJECT_TOO_THIN and UNKNOWN_LANGUAGE_NOT_HELD is looking
at two problems that share nothing: one needs three more sentences, the
other needs a sovereign built from documents in another language. Without
this the refusal says what happened and leaves the repair to be guessed.

Measured end to end, registering and re-asking:

    UNKNOWN_NOT_PRESENT        3 sentences  -> ANSWER 超伝導      1.4s
    UNKNOWN_SUBJECT_TOO_THIN   1 fact NOT_HELD, 4 facts -> ANSWER
    UNKNOWN_NO_CITATION        one citing document -> 民法第七百九条
    UNKNOWN_LANGUAGE_NOT_HELD  an English sovereign -> ANSWER negligence
    UNKNOWN_TIME_DEPENDENT     unchanged by registration; resolve the
                               deictic first, then the store answers
    UNKNOWN_NO_SUBJECT         registrable and should not be registered

## Two of the six are not knowledge gaps

`UNKNOWN_TIME_DEPENDENT` does not move when the fact is added. The store now
holds 「2026年8月10日の東京の天気は晴れである」 and 「今日の天気は」 still
routes to a tool, because 今日 is a property of the QUESTION and the store
has no clock. Asking with the date answers. The repair is upstream: whoever
knows what day it is resolves the deictic, and then this is an ordinary
lookup.

`UNKNOWN_NO_SUBJECT` can be registered — 「こんにちはは挨拶である」 makes a
greeting answerable — and a knowledge store answering こんにちは with 挨拶
is not an improvement. It is a routing decision, not a gap, and `remedy`
says so rather than offering a form to fill in.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

#: verdict -> what closes it. `register` is what an expert supplies;
#: `then` is what should happen afterwards; `not_a_gap` marks the refusals
#: that are correct and should be routed rather than repaired.
REMEDIES: Dict[str, Dict[str, Any]] = {
    # The census returning nothing at all, which is a different claim from
    # NOT_PRESENT: there the term is held and unsupported, here the store has
    # no purchase on the question whatsoever. It was missing from this table
    # until the public page surfaced it — こんにちは reaches the inference core
    # and comes back NO_EVIDENCE, not NO_SUBJECT, so the commonest refusal on
    # the demo showed a reader an empty box.
    "UNKNOWN_NO_EVIDENCE": {
        "register": "sentences about the subject — the census found nothing "
                    "to count",
        "how": "remember / propose_ai_facts then accept_ai_fact",
        "then": "rebuild the judge — measured 1.4s on 86,967 cores",
        "minimum": 3,
        "note": "if the question names no content word at all, the honest "
                "route is a generator rather than a registration; see "
                "UNKNOWN_NO_SUBJECT",
    },
    "UNKNOWN_NOT_PRESENT": {
        "register": "sentences about the subject, in the register the "
                    "corpus is judged in",
        "how": "remember / propose_ai_facts then accept_ai_fact",
        "then": "rebuild the judge — measured 1.4s on 54,244 cores",
        "minimum": 3,
    },
    "UNKNOWN_SUBJECT_TOO_THIN": {
        "register": "more facts about a subject the store already holds",
        "how": "remember",
        "then": "the subject becomes judgeable at MIN_FACETS",
        "minimum": 3,
        "note": "one fact left it NOT_HELD; four made it answerable",
    },
    "UNKNOWN_NO_CITATION": {
        "register": "a document ABOUT the topic that cites articles by name",
        "how": "ingest the document; links.harvest takes the topic from the "
               "filename",
        "then": "cited articles are listed, never chosen",
    },
    "UNKNOWN_LANGUAGE_NOT_HELD": {
        "register": "documents in that language, as their own sovereign",
        "how": "build a store and Polyglot.add(lang, store)",
        "then": "questions in that language route to it and never pool with "
                "the others",
    },
    "UNKNOWN_SUBJECT_NOT_A_WORD": {
        "register": "nothing — the path is the answer",
        "not_a_gap": True,
        "why": "the centre is a retrieval key the corpus does not write "
               "standalone. Admitting it as a word was measured to cost more "
               "than it buys: MIN_ATTEST 3 -> 1 lifted speakable centres to "
               "64% at 4% real words",
    },
    "UNKNOWN_TIME_DEPENDENT": {
        "register": "nothing here — resolve the deictic first",
        "not_a_gap": True,
        "why": "今日 is a property of the question and the store has no "
               "clock. Registering the fact does not change the verdict; "
               "asking with the date does. Ingest the tool result with its "
               "timestamp as the source label to make the answer citable",
    },
    "UNKNOWN_NO_SUBJECT": {
        "register": "nothing — route it to a generator",
        "not_a_gap": True,
        "why": "the text read fine and holds no content word. It CAN be "
               "registered — 「こんにちはは挨拶である」 makes a greeting "
               "answerable — and a knowledge store answering こんにちは with "
               "挨拶 is not an improvement",
    },
    "UNKNOWN_UNPARSED": {
        "register": "nothing — the input was empty or unreadable",
        "not_a_gap": True,
    },
    "NOT_ATTESTED": {
        "register": "sentences connecting the subject to the asked "
                    "condition, if the connection is in fact true",
        "how": "remember / propose_ai_facts then accept_ai_fact",
        "then": "the same question returns ATTESTED with the new facet "
                "as the citation",
        "minimum": 1,
        "note": "this verdict is a coverage gap, not a denial — the "
                "corpus never wrote the negative either, and closure "
                "forbids inventing it",
    },
    "UNKNOWN_UNDERDETERMINED": {
        "register": "nothing — supply another condition instead",
        "not_a_gap": True,
        "why": "the conditions given leave several cores standing and "
               "ties must abstain; a fourth condition narrows where "
               "registration would only thicken the tie",
    },
    "UNKNOWN_CONDITIONS_CONFLICT": {
        "register": "nothing about the corpus — the conditions cannot all "
                    "hold together",
        "not_a_gap": True,
        "why": "a finding about the question, not about coverage",
    },
}


def remedy(result: Dict[str, Any]) -> Dict[str, Any]:
    """What would turn this refusal into an answer, if anything would.

    Carries the subject and the missing terms through, so the form an expert
    is asked to fill in is already addressed to something.
    """
    verdict = str(result.get("verdict", ""))
    if verdict.startswith("ANSWER") or verdict in ("SEEDED", "AGREED", "LEAD",
                                                   "ATTESTED", "COMPARISON"):
        return {"verdict": verdict, "needs_registration": False}
    spec = REMEDIES.get(verdict)
    if spec is None:
        return {"verdict": verdict, "needs_registration": None,
                "note": "no remedy recorded for this verdict"}
    out = {
        "verdict": verdict,
        "needs_registration": not spec.get("not_a_gap", False),
        **{k: v for k, v in spec.items() if k != "not_a_gap"},
    }
    for key in ("subject", "terms", "missing", "language", "deictic"):
        if result.get(key):
            out[key] = result[key]
    return out
