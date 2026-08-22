"""Gap nodes: what a sovereign lacks, held as crosses it can read.

The conception: the geometry's spare capacity should hold CONTEXT, and the
sovereign's own gaps should live close to it — close enough that comparing
sovereigns drives the ones that stopped evolving. Implemented as three
measurable pieces:

    debt        subjects at least two PEER witnesses hold as cores while
                this one does not. Measured on the five selection rules:
                多分野 owes 999 (事実認定, 会社法 — legal concepts it
                brushes past), 法令 owes 3,971 (アメリカ, イギリス —
                country names statutes never define), 指名 owes 3,164
    gap store   every gap becomes a CROSS: the missing subject is the
                centre, and the faces carry typed context — which
                sovereign lacks it, how many peers hold it, and a preview
                of the peers' strongest facets. A gap is thereby readable
                by the same engines that read knowledge, which is what
                "memory sitting close" means operationally
    the loop    gaps whose selection rule can accept them are appended to
                the grow queue, and `grow` already fetches, rebuilds and
                verifies. Refusals fed one loop; peer comparison feeds
                the same loop from the other side

## Debt is read against the selection rule

法令's debt in country names is not a defect — a statute corpus CANNOT
define アメリカ, and fetching it in would break the rule that makes the
witness a witness. Only the rule-free sovereign (指名, whose stated rule
IS "what operation showed missing") may take arbitrary debt. The others'
debt is still worth holding as gap nodes: it is the map of what each
selection rule structurally cannot see, which is context about the
sovereign itself.

## Typed facets, closed vocabulary

Gap crosses use prefixed facets (gap:, peers:, held_by:, via:) so nothing
in them can be mistaken for corpus knowledge by a reader — the same
discipline that keeps citation labels off the faces. The preview facets
are copied from peers verbatim, so closure holds: every symbol in a gap
cross exists in some witness's store.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

#: A gap must be a plausible subject, not an extraction fragment.
_WORDISH = re.compile(r"^[㐀-䶿一-鿿ァ-ヺー]{2,8}$")

#: Two peers make evidence; one makes an accident of a single corpus.
MIN_PEERS = 2


def peer_gaps(witnesses: Dict[str, Any], *, min_peers: int = MIN_PEERS
              ) -> Dict[str, List[Tuple[str, int]]]:
    """Per witness: subjects its peers hold that it does not, ranked."""
    names = sorted(witnesses)
    out: Dict[str, List[Tuple[str, int]]] = {}
    for w in names:
        mine = set(witnesses[w].crosses)
        counts: Dict[str, int] = {}
        for o in names:
            if o == w:
                continue
            for c in witnesses[o].crosses:
                if c not in mine and _WORDISH.match(c):
                    counts[c] = counts.get(c, 0) + 1
        owed = [(c, n) for c, n in counts.items() if n >= min_peers]
        owed.sort(key=lambda t: (-t[1], t[0]))
        out[w] = owed
    return out


def gap_store(witnesses: Dict[str, Any], *,
              min_peers: int = MIN_PEERS, per_witness: int = 500) -> Any:
    """The gaps as a store of crosses, context on the faces."""
    from .cross_store import CrossStore

    st = CrossStore()
    debts = peer_gaps(witnesses, min_peers=min_peers)
    for w, owed in debts.items():
        for subject, n in owed[:per_witness]:
            holders = [o for o in sorted(witnesses)
                       if o != w and subject in witnesses[o].crosses]
            # Preview: the strongest facet each holder attaches, verbatim.
            preview = []
            for o in holders[:2]:
                cr = witnesses[o].crosses[subject]
                if cr:
                    preview.append(max(cr.items(), key=lambda kv: (kv[1], kv[0]))[0])
            facts = ([f"gap:{w}", f"peers:{n}"]
                     + [f"held_by:{o}" for o in holders[:3]] + preview)
            st.add(subject, dict.fromkeys(facts), source=f"gapnode:{w}")
    return st


def enqueue(witnesses: Dict[str, Any], queue_path: str, *,
            witness: str = "指名", limit: int = 30) -> Dict[str, Any]:
    """Feed one witness's debt into the grow queue — the loop's other inlet.

    Only the rule-free witness by default: its stated selection rule is
    "what operation showed missing", and peer comparison is exactly that,
    seen from the other side. Feeding rule-bound witnesses would break the
    rules that make them witnesses.
    """
    import json
    import time

    owed = peer_gaps(witnesses).get(witness, [])[:limit]
    with open(queue_path, "a", encoding="utf-8") as f:
        for subject, n in owed:
            f.write(json.dumps({"subject": subject, "peers": n,
                                "rule": "peer_gap:%s" % witness,
                                "asked": time.strftime("%Y-%m-%d")},
                               ensure_ascii=False) + "\n")
    return {"queued": len(owed), "witness": witness,
            "top": [s for s, _ in owed[:8]]}
