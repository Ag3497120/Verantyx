"""Elementary English grammatical decompose (deterministic, LM-free).

Coarse POS/role tags + sentence-ish split + WH query patterns.
Not a full NLP suite — heuristics only. Limitations documented below.

Limitations (honest):
  - No parser / dependency tree; window + lists + suffixes.
  - Nouns ≈ residual content (many verbs/adjs mis-tagged as NOUN).
  - Verb detection via short list + -ed/-ing/-ize; 3sg -s is noisy.
  - No NER, morphology beyond strip, or multiword heads beyond first content.
  - Roughness OK for pour-classify foundation; not fluent QA.

Record shape (per sentence / query):
  {tokens, roles, heads, pattern, content_tokens}
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# --- closed-class lists (function / glue) ---

_DET = frozenset({"a", "an", "the"})
_PRON = frozenset(
    {
        "i",
        "you",
        "he",
        "she",
        "it",
        "we",
        "they",
        "me",
        "him",
        "her",
        "us",
        "them",
        "my",
        "your",
        "his",
        "its",
        "our",
        "their",
        "mine",
        "yours",
        "hers",
        "ours",
        "theirs",
        "this",
        "that",
        "these",
        "those",
        "who",
        "whom",
        "whose",
        "which",
        "what",
    }
)
_WH = frozenset({"who", "what", "where", "when", "why", "how", "which", "whose", "whom"})
_AUX = frozenset(
    {
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "am",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "shall",
        "should",
        "can",
        "could",
        "may",
        "might",
        "must",
        "need",
        "dare",
    }
)
_ADP = frozenset(
    {
        "in",
        "on",
        "at",
        "with",
        "of",
        "to",
        "for",
        "from",
        "by",
        "about",
        "into",
        "onto",
        "over",
        "under",
        "through",
        "across",
        "between",
        "among",
        "against",
        "without",
        "within",
        "during",
        "before",
        "after",
        "near",
        "as",
        "like",
        "than",
        "via",
        "per",
        "upon",
        "around",
        "along",
        "behind",
        "beside",
        "beyond",
        "toward",
        "towards",
        "until",
        "unless",
    }
)
_CONJ = frozenset(
    {
        "and",
        "or",
        "but",
        "nor",
        "so",
        "yet",
        "both",
        "either",
        "neither",
        "while",
        "although",
        "though",
        "because",
        "if",
        "when",
        "whether",
    }
)
_PART = frozenset({"not", "n't", "to"})  # infinitival to handled as ADP too
_ADV_COMMON = frozenset(
    {
        "very",
        "quite",
        "also",
        "just",
        "only",
        "even",
        "still",
        "already",
        "always",
        "never",
        "often",
        "sometimes",
        "here",
        "there",
        "now",
        "then",
        "soon",
        "well",
        "too",
        "more",
        "most",
        "less",
        "much",
        "many",
        "rather",
        "almost",
        "enough",
        "again",
        "away",
        "back",
        "up",
        "down",
        "out",
        "off",
    }
)
_VERB_COMMON = frozenset(
    {
        "go",
        "goes",
        "went",
        "gone",
        "going",
        "come",
        "comes",
        "came",
        "coming",
        "make",
        "makes",
        "made",
        "making",
        "take",
        "takes",
        "took",
        "taken",
        "taking",
        "get",
        "gets",
        "got",
        "getting",
        "see",
        "sees",
        "saw",
        "seen",
        "seeing",
        "know",
        "knows",
        "knew",
        "known",
        "knowing",
        "think",
        "thinks",
        "thought",
        "thinking",
        "say",
        "says",
        "said",
        "saying",
        "tell",
        "tells",
        "told",
        "telling",
        "give",
        "gives",
        "gave",
        "given",
        "giving",
        "find",
        "finds",
        "found",
        "finding",
        "use",
        "uses",
        "used",
        "using",
        "work",
        "works",
        "worked",
        "working",
        "call",
        "calls",
        "called",
        "calling",
        "try",
        "tries",
        "tried",
        "trying",
        "ask",
        "asks",
        "asked",
        "asking",
        "need",
        "needs",
        "needed",
        "needing",
        "want",
        "wants",
        "wanted",
        "wanting",
        "look",
        "looks",
        "looked",
        "looking",
        "seem",
        "seems",
        "seemed",
        "seeming",
        "feel",
        "feels",
        "felt",
        "feeling",
        "become",
        "becomes",
        "became",
        "becoming",
        "leave",
        "leaves",
        "left",
        "leaving",
        "put",
        "puts",
        "putting",
        "mean",
        "means",
        "meant",
        "meaning",
        "keep",
        "keeps",
        "kept",
        "keeping",
        "let",
        "lets",
        "letting",
        "begin",
        "begins",
        "began",
        "begun",
        "beginning",
        "show",
        "shows",
        "showed",
        "shown",
        "showing",
        "hear",
        "hears",
        "heard",
        "hearing",
        "play",
        "plays",
        "played",
        "playing",
        "run",
        "runs",
        "ran",
        "running",
        "move",
        "moves",
        "moved",
        "moving",
        "live",
        "lives",
        "lived",
        "living",
        "believe",
        "believes",
        "believed",
        "believing",
        "hold",
        "holds",
        "held",
        "holding",
        "bring",
        "brings",
        "brought",
        "bringing",
        "happen",
        "happens",
        "happened",
        "happening",
        "write",
        "writes",
        "wrote",
        "written",
        "writing",
        "sit",
        "sits",
        "sat",
        "sitting",
        "stand",
        "stands",
        "stood",
        "standing",
        "lose",
        "loses",
        "lost",
        "losing",
        "pay",
        "pays",
        "paid",
        "paying",
        "meet",
        "meets",
        "met",
        "meeting",
        "include",
        "includes",
        "included",
        "including",
        "continue",
        "continues",
        "continued",
        "continuing",
        "set",
        "sets",
        "setting",
        "learn",
        "learns",
        "learned",
        "learnt",
        "learning",
        "change",
        "changes",
        "changed",
        "changing",
        "lead",
        "leads",
        "led",
        "leading",
        "understand",
        "understands",
        "understood",
        "understanding",
        "watch",
        "watches",
        "watched",
        "watching",
        "follow",
        "follows",
        "followed",
        "following",
        "stop",
        "stops",
        "stopped",
        "stopping",
        "create",
        "creates",
        "created",
        "creating",
        "speak",
        "speaks",
        "spoke",
        "spoken",
        "speaking",
        "read",
        "reads",
        "reading",
        "allow",
        "allows",
        "allowed",
        "allowing",
        "add",
        "adds",
        "added",
        "adding",
        "spend",
        "spends",
        "spent",
        "spending",
        "grow",
        "grows",
        "grew",
        "grown",
        "growing",
        "open",
        "opens",
        "opened",
        "opening",
        "walk",
        "walks",
        "walked",
        "walking",
        "win",
        "wins",
        "won",
        "winning",
        "offer",
        "offers",
        "offered",
        "offering",
        "remember",
        "remembers",
        "remembered",
        "remembering",
        "love",
        "loves",
        "loved",
        "loving",
        "consider",
        "considers",
        "considered",
        "considering",
        "appear",
        "appears",
        "appeared",
        "appearing",
        "buy",
        "buys",
        "bought",
        "buying",
        "wait",
        "waits",
        "waited",
        "waiting",
        "serve",
        "serves",
        "served",
        "serving",
        "die",
        "dies",
        "died",
        "dying",
        "send",
        "sends",
        "sent",
        "sending",
        "build",
        "builds",
        "built",
        "building",
        "stay",
        "stays",
        "stayed",
        "staying",
        "fall",
        "falls",
        "fell",
        "fallen",
        "falling",
        "cut",
        "cuts",
        "cutting",
        "reach",
        "reaches",
        "reached",
        "reaching",
        "kill",
        "kills",
        "killed",
        "killing",
        "raise",
        "raises",
        "raised",
        "raising",
        "pass",
        "passes",
        "passed",
        "passing",
        "sell",
        "sells",
        "sold",
        "selling",
        "decide",
        "decides",
        "decided",
        "deciding",
        "return",
        "returns",
        "returned",
        "returning",
        "explain",
        "explains",
        "explained",
        "explaining",
        "hope",
        "hopes",
        "hoped",
        "hoping",
        "develop",
        "develops",
        "developed",
        "developing",
        "carry",
        "carries",
        "carried",
        "carrying",
        "break",
        "breaks",
        "broke",
        "broken",
        "breaking",
        "receive",
        "receives",
        "received",
        "receiving",
        "agree",
        "agrees",
        "agreed",
        "agreeing",
        "support",
        "supports",
        "supported",
        "supporting",
        "hit",
        "hits",
        "hitting",
        "produce",
        "produces",
        "produced",
        "producing",
        "eat",
        "eats",
        "ate",
        "eaten",
        "eating",
        "cover",
        "covers",
        "covered",
        "covering",
        "catch",
        "catches",
        "caught",
        "catching",
        "draw",
        "draws",
        "drew",
        "drawn",
        "drawing",
        "choose",
        "chooses",
        "chose",
        "chosen",
        "choosing",
        "define",
        "defines",
        "defined",
        "defining",
        "describe",
        "describes",
        "described",
        "describing",
        "flow",
        "flows",
        "flowed",
        "flowing",
        "shine",
        "shines",
        "shined",
        "shone",
        "shining",
        "form",
        "forms",
        "formed",
        "forming",
    }
)
_ADJ_COMMON = frozenset(
    {
        "good",
        "new",
        "first",
        "last",
        "long",
        "great",
        "little",
        "own",
        "other",
        "old",
        "right",
        "big",
        "high",
        "different",
        "small",
        "large",
        "next",
        "early",
        "young",
        "important",
        "few",
        "public",
        "bad",
        "same",
        "able",
        "red",
        "blue",
        "green",
        "black",
        "white",
        "sweet",
        "bright",
        "quiet",
        "ancient",
        "narrow",
        "wide",
        "silent",
        "golden",
        "hidden",
        "rapid",
        "gentle",
        "distant",
        "familiar",
        "complex",
        "simple",
        "true",
        "false",
        "open",
        "free",
        "full",
        "local",
        "national",
        "social",
        "human",
        "natural",
        "economic",
        "political",
        "common",
        "special",
        "certain",
        "possible",
        "available",
        "recent",
        "main",
        "major",
        "real",
        "clear",
        "strong",
        "hard",
        "soft",
        "short",
        "hot",
        "cold",
        "deep",
        "best",
        "better",
        "worse",
        "worst",
    }
)

_FUNCTION_ROLES = frozenset({"DET", "ADP", "AUX", "WH", "PRON", "CONJ", "PART"})
_CONTENT_ROLES = frozenset({"NOUN", "VERB", "ADJ", "ADV"})

_PUNCT_STRIP = re.compile(r"^[\W_]+|[\W_]+$", re.UNICODE)
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[A-Za-z0-9']+")

# Query patterns (coarse)
_WHAT_IS_RE = re.compile(
    r"^\s*what\s+(?:is|are|was|were)\s+(?:an?\s+)?(.+?)\s*\??\s*$",
    re.IGNORECASE,
)
_WHO_IS_RE = re.compile(
    r"^\s*who\s+(?:is|are|was|were)\s+(?:an?\s+)?(.+?)\s*\??\s*$",
    re.IGNORECASE,
)
_WHERE_IS_RE = re.compile(
    r"^\s*where\s+(?:is|are|was|were)\s+(?:an?\s+)?(.+?)\s*\??\s*$",
    re.IGNORECASE,
)
_WHEN_IS_RE = re.compile(
    r"^\s*when\s+(?:is|are|was|were|does|did|do)\s+(?:an?\s+)?(.+?)\s*\??\s*$",
    re.IGNORECASE,
)
_WHY_RE = re.compile(
    r"^\s*why\s+(?:is|are|was|were|does|did|do|can|would)?\s*(?:an?\s+)?(.+?)\s*\??\s*$",
    re.IGNORECASE,
)
_HOW_RE = re.compile(
    r"^\s*how\s+(?:is|are|was|were|does|did|do|can|to)?\s*(?:an?\s+)?(.+?)\s*\??\s*$",
    re.IGNORECASE,
)
_DEFINE_RE = re.compile(
    r"^\s*(?:define|describe|explain)\s+(?:an?\s+)?(.+?)\s*\.?\s*$",
    re.IGNORECASE,
)


def strip_punct(tok: str) -> str:
    return _PUNCT_STRIP.sub("", tok).casefold().strip()


def tokenize(text: str) -> List[str]:
    """Whitespace tokenize + light punctuation strip; keep alnum/' tokens."""
    out: List[str] = []
    for raw in (text or "").strip().split():
        t = strip_punct(raw)
        if not t:
            continue
        # also split glued punct leftovers via word regex
        m = _WORD.findall(t)
        if m:
            out.extend(x.casefold() for x in m)
        elif t:
            out.append(t)
    return out


def split_sentences(text: str) -> List[str]:
    """Sentence-ish split on .!? (keeps non-empty stripped pieces)."""
    s = (text or "").strip()
    if not s:
        return []
    parts = _SENT_SPLIT.split(s)
    return [p.strip() for p in parts if p.strip()]


def tag_roles(tokens) -> list:
    """Role tags with one context rule on top of the per-token guess.

    A token directly after a determiner whose next token is an auxiliary is
    the head noun of its phrase — "the observatory is", "an animal was" —
    whatever its suffix suggests. The suffix guesser reads -ory/-ary/-al/-ic
    as adjectival, which is right for advisory and mandatory and wrong for a
    large family of ordinary nouns: observatory, laboratory, library,
    hospital, clinic, animal, capital. The miss was invisible for as long as
    the test vocabulary happened to avoid that family, and surfaced the
    first time a generalization corpus used fresh nouns — "The observatory
    is closed" filed its claim under the attribution tag's noun instead.

    Determiner position is grammar, not vocabulary, which is what makes this
    a fix rather than another exception list.
    """
    roles = [tag_role(t) for t in tokens]
    for i, role in enumerate(roles):
        if (role == "ADJ" and i > 0 and roles[i - 1] == "DET"
                and (i + 1 == len(roles) or roles[i + 1] in ("AUX", "VERB"))):
            roles[i] = "NOUN"
    return roles


def tag_role(tok: str) -> str:
    """Coarse POS/role tag for a single casefolded token."""
    t = tok.casefold()
    if t in _DET:
        return "DET"
    if t in _WH:
        return "WH"
    if t in _PRON:
        return "PRON"
    if t in _AUX:
        return "AUX"
    if t in _ADP:
        return "ADP"
    if t in _CONJ:
        return "CONJ"
    if t in _PART or t == "not":
        return "PART"
    if t in _ADV_COMMON or t.endswith("ly"):
        return "ADV"
    if t in _COPULAR_VERBS:
        # Copular and linking verbs, a closed class. Without this "remains"
        # fell through to the noun default (no -ing/-ed/-ate ending), so
        # "The observatory remains open" never triggered the determiner rule
        # and the subject was mistagged ADJ again.
        return "VERB"
    if t in _ADJ_COMMON or _looks_adj(t):
        return "ADJ"
    if t in _VERB_COMMON or _looks_verb(t):
        return "VERB"
    return "NOUN"  # residual content default


_COPULAR_VERBS = frozenset({
    "remains", "remained", "remain", "stays", "stayed", "stay",
    "seems", "seemed", "seem", "appears", "appeared", "appear",
    "becomes", "became", "become", "looks", "looked", "sounds", "sounded",
})


def _looks_adj(t: str) -> bool:
    if len(t) < 4:
        return False
    return t.endswith(
        ("ful", "ous", "ive", "ish", "able", "ible", "al", "ic", "ary", "ory", "less")
    )


def _looks_verb(t: str) -> bool:
    if len(t) < 4:
        return False
    if t.endswith(("ing", "ized", "ises", "ized", "ize", "ate")):
        return True
    if t.endswith("ed") and len(t) >= 5:
        return True
    return False


def is_function_role(role: str) -> bool:
    return role in _FUNCTION_ROLES


def is_content_role(role: str) -> bool:
    return role in _CONTENT_ROLES


@dataclass
class DecomposeRecord:
    """Elementary grammatical decompose of one sentence / query string."""

    tokens: List[str] = field(default_factory=list)
    roles: List[str] = field(default_factory=list)
    heads: List[str] = field(default_factory=list)
    pattern: str = "bare"  # what_is|who_is|where_is|when_is|why|how|define|bare|empty
    content_tokens: List[str] = field(default_factory=list)
    raw: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "tokens": list(self.tokens),
            "roles": list(self.roles),
            "heads": list(self.heads),
            "pattern": self.pattern,
            "content_tokens": list(self.content_tokens),
            "raw": self.raw,
        }


def _content_from(tokens: Sequence[str], roles: Sequence[str]) -> List[str]:
    return [t for t, r in zip(tokens, roles) if is_content_role(r)]


def _head_nouns(tokens: Sequence[str], roles: Sequence[str]) -> List[str]:
    """Prefer NOUN content; fall back to any content token."""
    nouns = [t for t, r in zip(tokens, roles) if r == "NOUN"]
    if nouns:
        return nouns
    return _content_from(tokens, roles)


def _decompose_rest(rest: str, *, pattern: str) -> DecomposeRecord:
    tokens = tokenize(rest)
    roles = tag_roles(tokens)
    content = _content_from(tokens, roles)
    heads = _head_nouns(tokens, roles)
    if not heads and content:
        heads = [content[0]]
    return DecomposeRecord(
        tokens=tokens,
        roles=roles,
        heads=heads,
        pattern=pattern if heads else "empty",
        content_tokens=content,
        raw=rest,
    )


def decompose(text: str) -> DecomposeRecord:
    """Decompose one sentence or query (deterministic).

    Patterns (beyond bare activate):
      what_is / who_is / where_is / when_is / why / how / define
    Content head = first NOUN in the pattern rest (else first content token).
    """
    raw = text or ""
    s = raw.strip()
    if not s:
        return DecomposeRecord(pattern="empty", raw=raw)

    for rx, pat in (
        (_WHAT_IS_RE, "what_is"),
        (_WHO_IS_RE, "who_is"),
        (_WHERE_IS_RE, "where_is"),
        (_WHEN_IS_RE, "when_is"),
        (_WHY_RE, "why"),
        (_HOW_RE, "how"),
        (_DEFINE_RE, "define"),
    ):
        m = rx.match(s)
        if m:
            rec = _decompose_rest(m.group(1), pattern=pat)
            rec.raw = raw
            return rec

    tokens = tokenize(s)
    roles = tag_roles(tokens)
    content = _content_from(tokens, roles)
    heads = _head_nouns(tokens, roles)
    if not tokens:
        return DecomposeRecord(pattern="empty", raw=raw)
    if not content:
        return DecomposeRecord(
            tokens=tokens,
            roles=roles,
            heads=[],
            pattern="empty",
            content_tokens=[],
            raw=raw,
        )
    return DecomposeRecord(
        tokens=tokens,
        roles=roles,
        heads=heads or [content[0]],
        pattern="bare",
        content_tokens=content,
        raw=raw,
    )


def decompose_sentences(text: str) -> List[DecomposeRecord]:
    """Split on .!? then decompose each sentence-ish unit."""
    return [decompose(s) for s in split_sentences(text)]


# --- structure-role classify for ingest (core / facet / function) ---

STRUCTURE_CORE = "core"
STRUCTURE_FACET = "facet"
STRUCTURE_FUNCTION = "function"
STRUCTURE_SKIP = "skip"


@dataclass
class ClassifiedToken:
    token: str
    pos: str
    structure: str  # core | facet | function | skip

    def as_dict(self) -> Dict[str, Any]:
        return {"token": self.token, "pos": self.pos, "structure": self.structure}


@dataclass
class ClassifiedSentence:
    """One sentence → one core candidate + facet facts (heuristic)."""

    raw: str
    tokens: List[ClassifiedToken] = field(default_factory=list)
    core: Optional[str] = None
    facts: List[str] = field(default_factory=list)
    decompose: Optional[DecomposeRecord] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "raw": self.raw,
            "tokens": [t.as_dict() for t in self.tokens],
            "core": self.core,
            "facts": list(self.facts),
            "decompose": self.decompose.as_dict() if self.decompose else None,
        }


def classify_sentence(text: str) -> ClassifiedSentence:
    """Classify tokens into core / facet / function for face-role ingest.

    Rules (elementary):
      - DET/ADP/AUX/WH/PRON/CONJ/PART → function (skip for tip; tiny mass)
      - First strong NOUN head → core candidate
      - ADJ immediately before that noun → facet
      - Other nearby content NOUN/ADJ within ±2 of core (not the core) → facet
      - VERB/ADV near core may become facet if contentful and not function

    Tags the **full** sentence (not WH-rest only) so articles/aux stay visible
    as function. ``decompose`` still supplies pattern + preferred heads.
    """
    rec = decompose(text)
    # Full-sentence tokens for structure roles (WH wrappers keep DET/AUX/WH)
    full_tokens = tokenize(text)
    full_roles = tag_roles(full_tokens)
    tagged: List[ClassifiedToken] = []
    for tok, role in zip(full_tokens, full_roles):
        if is_function_role(role):
            tagged.append(ClassifiedToken(tok, role, STRUCTURE_FUNCTION))
        else:
            tagged.append(ClassifiedToken(tok, role, STRUCTURE_SKIP))  # temp

    core: Optional[str] = None
    core_i: Optional[int] = None
    # Prefer decompose head if present in sentence; else first NOUN
    if rec.heads:
        for i, ct in enumerate(tagged):
            if ct.token == rec.heads[0] and not is_function_role(ct.pos):
                core = ct.token
                core_i = i
                ct.structure = STRUCTURE_CORE
                break
    if core is None:
        for i, ct in enumerate(tagged):
            if ct.pos == "NOUN":
                core = ct.token
                core_i = i
                ct.structure = STRUCTURE_CORE
                break

    facts: List[str] = []
    if core_i is not None:
        # adj + noun: ADJ immediately before core
        if core_i > 0 and tagged[core_i - 1].pos == "ADJ":
            tagged[core_i - 1].structure = STRUCTURE_FACET
            facts.append(tagged[core_i - 1].token)
        # window ±2 content as facets (apposition-light)
        for j in range(max(0, core_i - 2), min(len(tagged), core_i + 3)):
            if j == core_i:
                continue
            ct = tagged[j]
            if ct.structure == STRUCTURE_FUNCTION:
                continue
            if ct.pos in ("NOUN", "ADJ", "VERB") and ct.token != core:
                if ct.structure != STRUCTURE_FACET:
                    ct.structure = STRUCTURE_FACET
                if ct.token not in facts and ct.token != core:
                    facts.append(ct.token)
        # leftover content far from core stays skip (not tip cores this sentence)
        for ct in tagged:
            if ct.structure == STRUCTURE_SKIP and is_content_role(ct.pos):
                # secondary nouns can be extra facets if still empty budget
                if ct.pos in ("NOUN", "ADJ") and ct.token not in facts and len(facts) < 4:
                    ct.structure = STRUCTURE_FACET
                    facts.append(ct.token)

    # Cap facts to face budget (4 side faces); order preserved
    facts = facts[:4]
    return ClassifiedSentence(
        raw=text,
        tokens=tagged,
        core=core,
        facts=facts,
        decompose=rec,
    )


def classify_texts(texts: Iterable[str]) -> List[ClassifiedSentence]:
    """Classify each sentence across texts (split on .!?)."""
    out: List[ClassifiedSentence] = []
    for text in texts:
        for sent in split_sentences(str(text)):
            out.append(classify_sentence(sent))
    return out


def content_head(text: str) -> Optional[str]:
    """First content head for query routing (None if empty/function-only)."""
    rec = decompose(text)
    if rec.heads:
        return rec.heads[0]
    if rec.content_tokens:
        return rec.content_tokens[0]
    return None
