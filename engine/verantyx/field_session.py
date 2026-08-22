"""What a field officer needs between one shift and the next.

Three things the audit page does not do, taken from what the IDE already
solved and rewritten in Vera's terms rather than copied.

    SESSIONS      `SessionMemoryArchiver` keeps chat history in zones —
                  front for the live one, near/mid for recent, far for
                  archived — so old material stays reachable without
                  crowding what is in front of you. A shift handover is the
                  same problem: the officer coming on at 22:00 needs
                  yesterday's audit findable and today's audit open.

    SEARCH        `ProjectSearchEngine` shells out to ripgrep over a repo.
                  A field officer's version of that question is not "which
                  file contains this string" but "what do we know about
                  天草市, and who said it" — so this searches the STORE, not
                  the bytes, and every hit carries the document it came from.

    SILENCE RATE  `ConfusionDetector` watches an LLM's replies for "I don't
                  know" and injects memory when it finds them. Vera has no
                  replies to watch, but it has something better: typed
                  refusals. A run that answers UNKNOWN_* most of the time is
                  the same situation, and it is far more actionable, because
                  the refusal already names WHICH thing is missing. So the
                  detector becomes a rate with the reason attached, and the
                  advice is a procedure rather than a guess.

All of it is local files under the operator's own directory, and none of it
takes a network. A field tool that needs a connection is a field tool that
stops working at exactly the moment it is needed.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HOME = Path.home() / ".verantyx-audit"
SESSIONS = "sessions"

#: Zones, in the archiver's sense: how far back something is, not how old.
#: A shift is the unit because that is what a handover is measured in.
FRONT, RECENT, ARCHIVE = "front", "recent", "archive"
RECENT_DAYS = 7


@dataclass
class Session:
    """One shift's work: what was read, what was found, what was decided."""

    session_id: str
    label: str = ""
    started: str = ""
    updated: str = ""
    documents: List[str] = field(default_factory=list)
    coverage: Optional[float] = None
    detections: List[Dict[str, Any]] = field(default_factory=list)
    #: Vocabulary judgements the operator made, so the queue never re-asks.
    decided: Dict[str, str] = field(default_factory=dict)
    note: str = ""

    def zone(self, now: Optional[float] = None) -> str:
        try:
            age = (now or time.time()) - time.mktime(
                time.strptime(self.updated, "%Y-%m-%dT%H:%M:%S"))
        except (ValueError, TypeError):
            return ARCHIVE
        if age < 12 * 3600:
            return FRONT
        return RECENT if age < RECENT_DAYS * 86400 else ARCHIVE

    def as_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["zone"] = self.zone()
        return d


def _dir(home: Path) -> Path:
    p = Path(home) / SESSIONS
    p.mkdir(parents=True, exist_ok=True)
    return p


def save(session: Session, home: Path = HOME) -> Path:
    session.updated = time.strftime("%Y-%m-%dT%H:%M:%S")
    if not session.started:
        session.started = session.updated
    path = _dir(home) / f"{session.session_id}.json"
    path.write_text(json.dumps(asdict(session), ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return path


def load(session_id: str, home: Path = HOME) -> Optional[Session]:
    path = _dir(home) / f"{session_id}.json"
    if not path.exists():
        return None
    try:
        return Session(**json.loads(path.read_text(encoding="utf-8")))
    except (ValueError, TypeError):
        return None


def listing(home: Path = HOME) -> List[Dict[str, Any]]:
    """Every session, newest first, each carrying its zone.

    Ordered rather than grouped: an officer coming on shift scans one column,
    and a screen that makes them look in three places to find yesterday is a
    screen they will stop using by the second week.
    """
    out = []
    for p in sorted(_dir(home).glob("*.json")):
        try:
            s = Session(**json.loads(p.read_text(encoding="utf-8")))
        except (ValueError, TypeError):
            continue
        out.append(s.as_dict())
    return sorted(out, key=lambda d: d.get("updated") or "", reverse=True)


def new_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


# ---------------------------------------------------------------------------
# Search — over the store, not the bytes
# ---------------------------------------------------------------------------

def search(store, query: str, *, limit: int = 40) -> List[Dict[str, Any]]:
    """What is known about a place, a facility, a route — with its source.

    Matches a core by substring in both directions, so 「天草」 finds 天草市 and
    「天草市の給水所」 finds 天草市 too. Nothing is scored or ranked by
    relevance: an officer looking for their own municipality wants the whole
    row, and a ranking they cannot see the rule for is a ranking they cannot
    check.
    """
    from .ja_grammar import ASPECT_OF

    q = (query or "").strip()
    if not q:
        return []
    prov = getattr(store, "provenance", {}) or {}
    hits: List[Dict[str, Any]] = []
    for core in sorted(store.crosses):
        if q not in core and core not in q:
            continue
        claims = []
        for facet in sorted(store.crosses[core]):
            if ":" not in facet:
                continue
            aspect, value = facet.split(":", 1)
            slot = (prov.get(core) or {}).get(facet)
            claims.append({
                "aspect": aspect,
                "value": value,
                "pole": (ASPECT_OF.get(value.replace("not_", "")) or ("", "?"))[1],
                "evidence": str(slot[2]) if slot and len(slot) > 2 else "",
                "when": str(slot[1]) if slot and len(slot) > 1 else "",
            })
        other = [f for f in sorted(store.crosses[core]) if ":" not in f]
        hits.append({"core": core, "claims": claims, "facets": other[:12]})
        if len(hits) >= limit:
            break
    return hits


# ---------------------------------------------------------------------------
# Silence rate — the confusion detector, in typed-refusal terms
# ---------------------------------------------------------------------------

#: Above this, the run is mostly refusing and the operator needs to know why
#: before they read any finding. Set from the corpora this project measured:
#: the worst honest corpus read 63.9% of its sentences, so a run placing under
#: half is unlike anything that worked.
SILENT = 0.50

#: The refusals this screen can raise. CODES ONLY — the wording lives in the
#: page, in both languages.
#:
#: The remedy used to be Japanese prose returned by the server, which made the
#: whole application monolingual from the API outward: an English-speaking
#: operator got English chrome and a Japanese explanation of what went wrong,
#: which is worse than either language alone. A typed refusal already names
#: what is missing; naming it is the server's job, and saying what to do about
#: it is the screen's.
REMEDIES = (
    "UNKNOWN_NO_READABLE_DOCUMENTS",
    "UNKNOWN_EMPTY_DOCUMENT",
    "UNKNOWN_UNREADABLE",
    "LOW_COVERAGE",
    "NO_OPPOSABLE_PAIRS",
)


def silence(audit) -> Dict[str, Any]:
    """How much the run refused, why, and what to do — before any finding.

    Deliberately computed and shown BEFORE the findings rather than beside
    them. A detection list read without knowing that 60% of the corpus went
    unread is a list that will be trusted for the wrong reasons.
    """
    seen = getattr(audit, "sentences_seen", 0) or 0
    placed = getattr(audit, "sentences_placed", 0) or 0
    pairs = getattr(audit, "opposable_pairs", 0) or 0
    rate = placed / seen if seen else 0.0

    flags: List[Dict[str, str]] = []
    if seen and rate < SILENT:
        flags.append({"code": "LOW_COVERAGE"})
    if not pairs:
        flags.append({"code": "NO_OPPOSABLE_PAIRS"})
    return {
        "read": placed,
        "seen": seen,
        "coverage": round(rate, 4),
        "opposable_pairs": pairs,
        "quiet": bool(flags),
        "flags": flags,
    }
