"""A sovereign with every stage in it, not just the ladder.

`constellation.staircase` builds its members out of `resolution.Ladder`
alone. That is why seven of them take 1.5 seconds, and it is also why the
machinery this package spent most of its measurements on was sitting
unwired: placement 699 lines, hierarchy 552, granularity 369, links 216, all
built and none of them reached by a sovereign.

This assembles one member out of all of them, at one setting, so the census
can be run over sovereigns that actually contain what the design says a
sovereign contains — and so the cost of each stage is a number rather than
an assumption.

    1  leaves      the federation as ingested, per source
    2  placement   simulated per leaf; accepted only where it measures better
    3  units       `granularity` splits terms the corpus attests as units
    4  links       `links` bridges a doctrinal name to the article it cites
    5  tree        `hierarchy` binds leaves under their own divisions
    6  ladder      `resolution` indexes cores at this member's grain

Stages 3 and 4 exist because coarsening reaches unseen WORDS and not unseen
MEANINGS: it answered 漁業法第百一条 with 鉱業法第百一条, sharing a numeral
and none of the facets, and it cannot reach 殺人罪 -> 刑法第百九十九条 at
all unless the two share characters. Units attack that from the form side
and links from the citation side.

## What each stage is allowed to do

Add a way to reach a leaf. None of them may add a FACT: a link records that
one document cited another, a unit records that the corpus writes a
substring on its own, and neither invents content. That is the same rule
placement was measured against — placement cannot add information — and the
reason the stages can be composed without asking which one is authoritative.
"""
from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .cross_store import CrossStore
from .resolution import Ladder

#: One member per setting, one axis at a time — the staircase, kept.
DEFAULT_SETTINGS: Tuple[Tuple[str, Dict[str, Any]], ...] = (
    ("whole",       {"rungs": (("whole", 0),), "grammar": "raw", "depth": 1}),
    ("g3",          {"rungs": (("g3", 3),), "grammar": "raw", "depth": 1}),
    ("g2",          {"rungs": (("g2", 2),), "grammar": "raw", "depth": 1}),
    ("nosuffix",    {"rungs": (("whole", 0),), "grammar": "nosuffix", "depth": 1}),
    ("nosuffix.g2", {"rungs": (("g2", 2),), "grammar": "nosuffix", "depth": 1}),
    ("mentions",    {"rungs": (("whole", 0),), "grammar": "raw"}),
    ("cites",       {"rungs": (("whole", 0),), "grammar": "raw",
                     "links_only": True}),
)


@dataclass
class Stage:
    name: str
    verdict: str
    seconds: float
    detail: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {"stage": self.name, "verdict": self.verdict,
                "seconds": round(self.seconds, 2), **self.detail}


def learn_units(store: CrossStore, *, sample: int = 8000,
                min_attest: int = 3) -> Dict[str, List[str]]:
    """Cores the corpus also writes in pieces, and the pieces.

    `granularity.decompose_units` reads the vocabulary as units in LEFT and
    RIGHT position, which is the distinction a window scan cannot make:
    賠償 earns its right-hand slot from 損害賠償 and not from any string
    ending in those two characters. A first version here scanned every
    window instead and was not using that module at all — the point of the
    exercise was to wire what was built, so it is wired.

    A piece is admitted only where the corpus also writes it UNFLANKED.
    事訴 sits inside 民事訴訟法 thousands of times and never alone, and
    admitting it puts a fragment where a reader expects a word; that same
    test raised `granularity`'s advantage over chance from 4.9x to 15x.
    """
    from .granularity import decompose_units
    from .vocabulary import runs

    labels = getattr(store, "source_labels", set()) or set()
    cores = [c for c in store.crosses if c not in labels]
    model = decompose_units(cores)
    text = "".join(
        f"{c}、{'、'.join(sorted(f for f in (store.crosses[c] or ()) if f not in labels))}。"
        for c in cores[:sample])
    seen = runs(text)

    units: Dict[str, List[str]] = {}
    for core in cores:
        if not (3 <= len(core) <= 10):
            continue
        parts: List[str] = []
        for a, b in _SPLITS_FOR(len(core)):
            left, right = core[:a], core[a:]
            # Left AND right must both be units the model saw in that
            # position, and both must stand alone in the corpus. Either
            # test alone admits fragments.
            if (left in model.slots.get((a, "L"), ())
                    and right in model.slots.get((b, "R"), ())
                    and seen.get(left, 0) >= min_attest
                    and seen.get(right, 0) >= min_attest):
                parts += [left, right]
        if parts:
            units[core] = sorted(set(parts))
    return units


def _SPLITS_FOR(n: int) -> Tuple[Tuple[int, int], ...]:
    """Every split of a word this long, from `granularity.SPLITS`."""
    from .granularity import SPLITS

    if n in SPLITS:
        return SPLITS[n]
    return tuple((i, n - i) for i in range(2, n - 1))


def learn_links(paths: Iterable[Any]) -> Dict[str, List[str]]:
    """Doctrinal name -> the article cores an article about it cites.

    This is the bridge coarsening cannot build. 殺人罪 and 刑法第百九十九条
    share two characters out of eight, so no window reaches from one to the
    other, and coarsening's failure case is exactly this shape: it answered
    漁業法第百一条 with 鉱業法第百一条, matching a numeral and none of the
    meaning. What connects the doctrine to the article is that a document
    ABOUT 殺人罪 cites 刑法第百九十九条 by name.

    `links.harvest` takes the topic from the FILENAME, which is how an
    encyclopedia dump is organised — the file is the topic — and records the
    citing document as the source. The direction is the whole point: this is
    evidence about what the encyclopedia said, never a claim the statute
    made.
    """
    from .links import harvest

    ls = harvest(list(paths))
    return {topic: ls.articles(topic) for topic in ls.by_topic}


@dataclass
class FullSovereign:
    """One sovereign at one setting, with every stage present."""

    name: str
    setting: Dict[str, Any] = field(default_factory=dict)
    ladder: Optional[Ladder] = None
    tree: Optional[Any] = None
    units: Dict[str, List[str]] = field(default_factory=dict)
    links: Dict[str, List[str]] = field(default_factory=dict)
    held: Set[str] = field(default_factory=set)
    cores: Set[str] = field(default_factory=set)
    placement: Dict[str, Any] = field(default_factory=dict)
    stages: List[Stage] = field(default_factory=list)

    def build(
        self,
        store: CrossStore,
        leaves: Optional[Dict[str, Dict[str, CrossStore]]] = None,
        *,
        shared: Optional[Dict[str, Any]] = None,
        link_paths: Optional[Iterable[Any]] = None,
        with_tree: bool = True,
        with_placement: bool = True,
    ) -> "FullSovereign":
        """``shared`` carries stage 3/4 results between members.

        Units and links are facts about the CORPUS, not about this member's
        grain, so recomputing them per member would measure the same thing
        seven times and call the total a cost of the constellation.
        """
        from .graded import cores_as_items

        shared = shared if shared is not None else {}

        t = time.time()
        if "units" not in shared:
            shared["units"] = learn_units(store)
        self.units = shared["units"]
        self.stages.append(Stage("units", "ANSWER", time.time() - t,
                                 {"cores_splittable": len(self.units)}))

        t = time.time()
        if "links" not in shared:
            shared["links"] = learn_links(link_paths or [])
        self.links = shared["links"]
        self.stages.append(Stage("links", "ANSWER", time.time() - t,
                                 {"cores_citing": len(self.links)}))

        t = time.time()
        if with_placement and leaves:
            self.placement = self._simulate(leaves, shared)
            v = "ANSWER"
        else:
            self.placement, v = {}, "SKIPPED"
        self.stages.append(Stage("placement", v, time.time() - t,
                                 self.placement))

        t = time.time()
        if with_tree and leaves:
            self.tree = self._tree(leaves, shared)
            v = "ANSWER" if self.tree is not None else "UNKNOWN_NO_TREE"
        else:
            v = "SKIPPED"
        self.stages.append(Stage("tree", v, time.time() - t,
                                 shared.get("tree_shape", {})))

        t = time.time()
        items = cores_as_items(store, depth=self.setting.get("depth"))
        # A unit is another way to REACH a core, never another fact about
        # it: the pieces join the core's own terms and nothing is invented.
        if self.setting.get("units"):
            for core, parts in self.units.items():
                if core in items:
                    items[core] = list(items[core]) + parts

        # Links key the ARTICLE by the topic, which is the direction that
        # answers the question. The first wiring did the reverse — the cited
        # articles were added to the TOPIC's terms — and scored 0 of 387,
        # because asking わいせつ then returns the core わいせつ, which is
        # what it already returned.
        #
        # This member indexes ONLY articles, and only by the topics that
        # cite them. Merging the two into one ladder cannot work either:
        # 「わいせつとは」 wants the doctrinal core and 「わいせつを定める
        # 条文は」 wants the article, both are right, and a ladder holding
        # both abstains on the tie. They are different questions and get
        # different members; the census reports both readings.
        if self.setting.get("links_only"):
            items = {}
            for topic, cited in self.links.items():
                for art in cited:
                    items.setdefault(art, [art]).append(topic)
        # Every term the store holds, for the coverage report. Concord says
        # how many settings agreed on an item; it does not say the question
        # was addressed, and free-form questions are where the two come
        # apart — 「パワハラを受けたら…」 answered 受 at three settings of
        # six, a verb stem agreed on, about nothing the reader asked.
        labels_ = getattr(store, "source_labels", set()) or set()
        self.cores = {c for c in store.crosses if c not in labels_}
        self.held = set(self.cores)
        for cross_ in store.crosses.values():
            self.held |= {f for f in cross_ if f not in labels_}

        self.ladder = Ladder(rungs=self.setting["rungs"],
                             grammar=self.setting.get("grammar", "raw")
                             ).build(items)
        self.stages.append(Stage("ladder", "ANSWER", time.time() - t,
                                 {"items": len(items),
                                  "grains": sum(len(v) for v
                                                in self.ladder.index.values())}))
        return self

    def _simulate(self, leaves: Dict[str, Dict[str, CrossStore]],
                  shared: Dict[str, Any]) -> Dict[str, Any]:
        if "placement" in shared:
            return shared["placement"]
        from .sovereign import simulate_domain

        acc = rej = skip = 0
        for _d, group in leaves.items():
            for lname, st in list(group.items())[:400]:
                r = simulate_domain(lname, st, n_queries=40)
                v = r.get("verdict")
                acc += v == "ACCEPTED"
                rej += v == "REJECTED"
                skip += v not in ("ACCEPTED", "REJECTED")
        shared["placement"] = {"accepted": acc, "rejected": rej,
                               "skipped": skip}
        return shared["placement"]

    def _tree(self, leaves: Dict[str, Dict[str, CrossStore]],
              shared: Dict[str, Any]) -> Optional[Any]:
        if "tree" in shared:
            return shared["tree"]
        from .hierarchy import Node
        from .sovereign import group_into_layers, shape

        domain_nodes: Dict[str, Node] = {}
        for dname, group in leaves.items():
            kids = {k: Node(name=k, store=v) for k, v in group.items()}
            if kids:
                domain_nodes[dname] = group_into_layers(dname, kids)
        root = group_into_layers("主権", domain_nodes) if domain_nodes else None
        shared["tree"] = root
        shared["tree_shape"] = shape(root) if root is not None else {}
        return root

    def cited(self, terms: Sequence[str]) -> Dict[str, Any]:
        """Every article a document about these terms cited. A LIST.

        わいせつ is provided for by 刑法第百七十四条 through 第百七十七条,
        and a ladder asked which ONE abstains: four articles, one point
        each, a tie. That refusal is correct for the question it was asked
        and useless for the question a reader has. Measured over the 130
        topics with a citation, choosing answered 54 and was right every
        time; listing reaches all of them.

        Listing is not choosing, so nothing here can fabricate: each entry
        carries the topic that cited it, and no article is preferred over
        another. The citation remains evidence about the citing document —
        it is never a claim the statute made.
        """
        out: Dict[str, List[str]] = {}
        for t in terms:
            arts = self.links.get(t)
            if arts:
                out[t] = list(arts)
        return {"verdict": "ANSWER" if out else "UNKNOWN_NO_CITATION",
                "by_topic": out,
                "articles": sorted({a for v in out.values() for a in v}),
                "note": "a document about this topic cited these articles; "
                        "that is a fact about the document, not the statute"}

    def report(self) -> Dict[str, Any]:
        return {"name": self.name,
                "setting": {k: str(v)[:40] for k, v in self.setting.items()},
                "stages": [s.as_dict() for s in self.stages]}


@dataclass
class FullConstellation:
    """Every member, and the readings they do not share.

    Three questions come back from one ask, because they are three
    questions and merging them was measured to destroy all of them:

        which core is this      the graded census over grain and grammar
        which articles cite it  `cited`, a LIST, never a choice
        which divisions hold it `gather` over the tree, also a list

    Merging the first two into one ladder scored 0 of 387. 「わいせつとは」
    wants the doctrinal core and 「わいせつを定める条文は」 wants
    刑法第百七十四条 through 第百七十七条; both are right, and a ladder
    holding both abstains on the tie.
    """

    members: List[FullSovereign] = field(default_factory=list)
    shared: Dict[str, Any] = field(default_factory=dict)

    def build(
        self,
        store: CrossStore,
        leaves: Optional[Dict[str, Dict[str, CrossStore]]] = None,
        *,
        settings: Sequence[Tuple[str, Dict[str, Any]]] = DEFAULT_SETTINGS,
        link_paths: Optional[Iterable[Any]] = None,
        with_tree: bool = False,
    ) -> "FullConstellation":
        """``with_tree`` is off by default because it is 97% of the cost.

        Measured on 4,771 leaves: tree 23.8s against 0.2s for a ladder, and
        it answers a question no ladder answers — `gather` found a
        destination for 60 of 60 probes, 2.4 of them on average, and named
        them the way the legislature does (殺人 -> 刑法／第二十六章 殺人の罪).
        Worth paying for deliberately, not by default.
        """
        for name, cfg in settings:
            self.members.append(FullSovereign(name=name, setting=cfg).build(
                store, leaves, shared=self.shared, link_paths=link_paths,
                with_tree=with_tree, with_placement=bool(leaves)))
            with_tree = False          # one tree, shared
        return self

    def ask(self, query: str) -> Dict[str, Any]:
        from .lang import ja_content_runs
        from .resolution import ask as rung_ask

        terms = ja_content_runs(query)
        if not terms:
            # See `graded.GradedJudge.ask`: a greeting is read fine and has
            # no subject, which is a handoff signal, not a parse failure.
            return {"verdict": "UNKNOWN_NO_SUBJECT" if (query or "").strip()
                    else "UNKNOWN_UNPARSED", "query": query, "terms": []}

        readings: Dict[str, Optional[str]] = {}
        cites: Dict[str, Any] = {}
        for m in self.members:
            if m.setting.get("links_only"):
                cites = m.cited(terms)
                continue
            r = rung_ask(m.ladder, terms)
            readings[m.name] = r["item"] if r["verdict"] == "ANSWER" else None

        spoke = [v for v in readings.values() if v]
        tally = Counter(spoke)
        if not spoke:
            verdict, item, agree = "UNKNOWN_NOT_PRESENT", None, 0
        else:
            top = max(tally.values())
            leaders = sorted(k for k, v in tally.items() if v == top)
            if len(leaders) > 1:
                verdict, item, agree = "AMBIGUOUS", None, top
            else:
                item, agree = leaders[0], top
                verdict = ("ANSWER" if readings.get("whole") == item
                           else "ANSWER_BY_COARSENING")
        held, cores = set(), set()
        for m in self.members:
            held |= getattr(m, "held", set())
            cores |= getattr(m, "cores", set())
        # Three states, not two. A term the store holds only as somebody
        # else's facet is one it can recognise and cannot be asked about, and
        # that is exactly the case a bare coverage figure hides:
        # 「パワハラを受けたら…」 scored 100% covered and answered 受,
        # because パワハラ is a facet and 受 is a core.
        as_core = [t for t in terms if t in cores]
        as_facet = [t for t in terms if t not in cores and t in held]
        missing = [t for t in terms if t not in held]
        out = {"verdict": verdict, "item": item, "terms": terms,
               "agreeing": agree, "of": len(readings), "readings": readings,
               "as_core": as_core, "as_facet_only": as_facet, "missing": missing,
               "coverage": round(len(as_core) / max(len(terms), 1), 3),
               "note": "coverage counts terms the store can be ASKED about; "
                       "a facet-only term is recognised and has no subject"}
        if cites.get("by_topic"):
            out["cited_articles"] = cites["articles"]
            out["cited_by_topic"] = cites["by_topic"]
            out["cited_note"] = cites["note"]
        tree = next((m.tree for m in self.members if m.tree is not None), None)
        if tree is not None:
            from .hierarchy import gather
            g = gather(tree, query, limit=8)
            out["divisions"] = [r.get("leaf") for r in g["results"]][:6]
        return out
