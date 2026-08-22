"""Documents in, one sovereign node out — the whole procedure, run for real.

Everything the tree needs was measured separately. This assembles it into an
ordered build, because the order matters and each stage constrains the next:

    1  ingest      documents -> one store per domain, kept SEPARATE
    2  simulate    per-domain placement, gated on held-out questions
    3  plan        capacity -> how many layers this vocabulary requires
    4  assemble    routers, with intermediate layers inserted where needed
    5  federate    domain nodes under one sovereign
    6  verify      descend real questions and record what refused

Nothing here is new machinery. `egov` and `document_ingest` do stage 1,
`placement` does stage 2, `hierarchy` does 3–5. What this module adds is the
sequence and the refusal to skip a stage — a tree assembled without stage 2
routes on whichever four facts sorted first, and the measurement that
motivated the whole design says that is the difference between a 30.9% and a
13.2% fabrication rate.

## Why stage 3 cannot be a preference

A node has six arms and four fact faces, so it routes on 24 terms and, past
that, on nothing: measured, terms on the faces reached the right domain 20
of 24 times and terms off them 0 of 60. Depth follows arithmetically,

    depth ~= log6(V / 4)

and `plan` reports it rather than accepting a number from the caller. A
caller who wants a shallower tree is asking for a router that cannot route.

## Why the leaves stay apart

Flat, the six statutes here share 184 terms across three or more of them and
行為 across all six; 民法's 法律行為 is not 刑法's. Merging domains into one
store is the failure this shape exists to avoid, so no stage ever writes two
domains into the same CrossStore — `_merged` in `hierarchy` builds a view for
ranking router terms and is never what a question is answered from.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .cross_store import CrossStore
from .hierarchy import (
    CAPACITY,
    gather,
    N_FACES,
    Node,
    build_router,
    descend,
    federate,
    over_capacity,
    shape,
)
from .consensus_store import MAX_ARMS

#: File suffixes routed to the statute reader rather than the document reader.
_STATUTE_SUFFIX = {".xml"}


@dataclass
class Stage:
    """One step's outcome, kept whole so the build can be read afterwards."""

    name: str
    verdict: str
    detail: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 1 — ingest
# ---------------------------------------------------------------------------

def _store_from_sentences(sentences: List[str], source: str) -> CrossStore:
    from .document_ingest import Document, ingest_documents

    st = CrossStore()
    if sentences:
        ingest_documents(st, [Document(source=source, text="".join(sentences))])
    return st


def ingest_domain(name: str, source: Path) -> Tuple[Dict[str, CrossStore], Dict[str, Any]]:
    """One folder becomes a domain's LEAF STORES — plural, and that is stage 3
    doing its work at ingest rather than being discovered later.

    A statute is already a tree the legislature drew: 刑法 is two 編 over 55
    章 over 357 条. So a law's leaves are its 章, not the law itself. The
    first version made one store per domain, the whole of 法律 hung under a
    single 24-term router, and every question refused at the root — the
    capacity report said "3 more layers" and it was right.

    Partitioning any other way (article-number buckets, term clustering)
    would invent divisions where authoritative ones exist, and a routing
    path through an invented group tells a reader nothing about why the
    question went that way. Non-statute documents split per document, which
    is the same principle: the source is the division.
    """
    from .document_ingest import Document, ingest_documents
    from .document_loaders import load_directory, load_paths
    from .egov import divisions, law_title

    src = Path(source)
    paths = sorted(p for p in (src.rglob("*") if src.is_dir() else [src])
                   if p.is_file() and not p.name.startswith("."))
    statutes = [p for p in paths if p.suffix.lower() in _STATUTE_SUFFIX]
    others = [p for p in paths if p.suffix.lower() not in _STATUTE_SUFFIX]

    leaves: Dict[str, CrossStore] = {}
    groups: Dict[str, List[str]] = {}
    n_articles = 0

    for p in statutes:
        law = law_title(p)
        for div in divisions(p, law=law):
            label = f"{law}／{div['division']}"
            sents = [f"{core}は{t}である。"
                     for core, _cap, terms in div["articles"] for t in terms]
            if not sents:
                continue
            st = _store_from_sentences(sents, law)
            if st.n_cores() == 0:
                continue
            leaves[label] = st
            groups.setdefault(law, []).append(label)
            n_articles += len(div["articles"])

    n_docs = 0
    if others:
        loaded = (load_directory(str(src)) if src.is_dir()
                  else load_paths([str(p) for p in others]))
        for doc in loaded["documents"]:
            if Path(getattr(doc, "source", "")).suffix.lower() in _STATUTE_SUFFIX:
                continue
            st = CrossStore()
            ingest_documents(st, [doc])
            if st.n_cores() == 0:
                continue
            label = f"{name}／{doc.source}"
            leaves[label] = st
            groups.setdefault(name, []).append(label)
            n_docs += 1

    return leaves, {
        "domain": name,
        "source": str(src),
        "statutes": len(statutes),
        "articles": n_articles,
        "documents": n_docs,
        "leaves": len(leaves),
        "groups": {k: len(v) for k, v in groups.items()},
        "cores": sum(st.n_cores() for st in leaves.values()),
        "_groups": groups,
    }


# ---------------------------------------------------------------------------
# 2 — simulate placement
# ---------------------------------------------------------------------------

def simulate_domain(name: str, store: CrossStore, *, n_queries: int = 200,
                    write: bool = True) -> Dict[str, Any]:
    """Pre-compute what goes on the faces, and refuse to bake it if it loses.

    The gate is the one from `placement`: the answer rate must not fall,
    uncovered query terms must not rise, and something must actually improve.
    A domain whose questions are flat has nothing to learn and is left on the
    frequency rule — that is a correct outcome, not a failure, and the
    report says which happened.
    """
    from .placement import accept, compare, derive_split, simulate

    train, test = derive_split(store, n_queries, demand="zipf")
    if not train or not test:
        return {"domain": name, "verdict": "SKIPPED",
                "reason": "not enough contested cores to form a query split"}
    cmp_ = compare(store, test, train=train, weight=0.0)
    gate = accept(cmp_)
    out = {
        "domain": name,
        "verdict": gate["verdict"],
        "reasons": gate["reasons"],
        "delta": cmp_["delta"],
        "mean_arms": cmp_["mean_arms"],
        "n_train": len(train),
        "n_test": cmp_["n_queries"],
    }
    if gate["verdict"] == "ACCEPTED" and write:
        placement = simulate(store, queries=train, weight=0.0)
        store.placement = placement
        store.placement_meta = {"policy": "simulated", "weight": 0.0,
                                "n_cores": len(placement),
                                "delta": cmp_["delta"]}
        out["placed_cores"] = len(placement)
    return out


# ---------------------------------------------------------------------------
# 3 — plan
# ---------------------------------------------------------------------------

def _flatten(leaves: Dict[str, CrossStore]) -> CrossStore:
    """A read-only view of a domain's leaves, for counting only.

    Never answered from, never routed on. Two domains are never flattened
    together — that is the merge the whole shape exists to avoid.
    """
    out = CrossStore()
    for st in leaves.values():
        for core, cross in st.crosses.items():
            out.crosses.setdefault(core, {}).update(cross)
            out.core_count[core] = out.core_count.get(core, 0) + 1
    return out


def plan(domains: Dict[str, CrossStore]) -> Dict[str, Any]:
    """How deep this vocabulary forces the tree to be.

    Reported, never accepted from the caller. Asking for fewer layers than
    the vocabulary needs is asking for a router that cannot route, and the
    measured failure is not graceful — it is zero.
    """
    per: Dict[str, Any] = {}
    total_terms = 0
    for name, st in domains.items():
        terms = len({t for c in st.crosses.values() for t in c})
        total_terms += terms
        per[name] = {
            "cores": st.n_cores(),
            "distinct_terms": terms,
            "layers_required": _layers_for(terms),
        }
    return {
        "capacity_per_node": CAPACITY,
        "arms": MAX_ARMS,
        "faces": N_FACES,
        "domains": per,
        "total_terms": total_terms,
        "domain_layer_required": _layers_for(len(domains) * N_FACES),
        "sovereign_layers_required": _layers_for(total_terms),
    }


def _layers_for(v: int) -> int:
    if v <= N_FACES:
        return 1
    return max(1, math.ceil(math.log(v / N_FACES, MAX_ARMS)))


# ---------------------------------------------------------------------------
# 4 — assemble, inserting layers where the arms run out
# ---------------------------------------------------------------------------

_KANJI = "〇一二三四五六七八九"


def _kanji(n: int) -> str:
    """Small integers as kanji, so a synthetic node name survives the
    Japanese run splitter that every core name goes through."""
    if n < 10:
        return _KANJI[n]
    return "".join(_KANJI[int(c)] for c in str(n))


def group_into_layers(name: str, children: Dict[str, Node],
                      *, asked: Optional[Sequence[str]] = None) -> Node:
    """Bind children under one node, adding intermediate layers if needed.

    Six arms is a hard count. Seven children do not "mostly fit" — the
    seventh is not placed at all, so groups of at most MAX_ARMS are formed
    and the grouping repeats until one node can hold them. Group names carry
    their members, because a routing path through a node called "group 2"
    tells a reader nothing about why the question went that way.
    """
    nodes = dict(children)
    level = 0
    while len(nodes) > MAX_ARMS:
        level += 1
        grouped: Dict[str, Node] = {}
        keys = list(nodes)
        # Fill the arms, do not minimise the groups. Chunking by MAX_ARMS
        # put twelve fields into TWO groups of six, so the root used two of
        # its six arms and could route 2 x 4 = 8 terms — which is exactly
        # how many of 24 questions escaped it. Sizing the chunk instead by
        # ceil(n / MAX_ARMS) gives six groups of two and the full 24.
        # A node that leaves arms empty has thrown away capacity it cannot
        # get back at any depth.
        size = -(-len(keys) // MAX_ARMS)
        for i in range(0, len(keys), size):
            chunk = keys[i:i + size]
            # Kanji numerals, not "群1-1". The Japanese run splitter cuts a
            # name at the ASCII digit boundary, so 主権群1-1 became the core
            # 主権群1 and no longer matched the child key — the router held
            # exactly the right terms and still routed nothing, because the
            # thing it named was not a branch. Node names travel through the
            # same tokeniser as the documents; they have to survive it.
            label = f"{name}群{_kanji(level)}{_kanji(i // size + 1)}"
            sub = Node(name=label, children={k: nodes[k] for k in chunk})
            sub.router = build_router(sub.children, asked=asked)
            grouped[label] = sub
        nodes = grouped
    root = Node(name=name, children=nodes)
    root.router = build_router(root.children, asked=asked)
    return root


def assemble(
    domains: Dict[str, Dict[str, CrossStore]],
    grouping: Dict[str, Dict[str, List[str]]],
    *,
    sovereign: str = "主権",
    asked: Optional[Sequence[str]] = None,
) -> Node:
    """Leaves -> their own document's divisions -> domain -> sovereign.

    Four named levels before any synthetic grouping, all of them drawn from
    the sources: a chapter of a law, a law, a field, the federation. Only
    when one of those has more than six members does `group_into_layers`
    add a level of its own, and it says so in the name.
    """
    domain_nodes: Dict[str, Node] = {}
    for dname, leaves in domains.items():
        groups = grouping.get(dname) or {dname: list(leaves)}
        mid: Dict[str, Node] = {}
        for gname, members in groups.items():
            kids = {m: Node(name=m, store=leaves[m]) for m in members if m in leaves}
            if not kids:
                continue
            mid[gname] = (next(iter(kids.values())) if len(kids) == 1
                          else group_into_layers(gname, kids, asked=asked))
        if not mid:
            continue
        domain_nodes[dname] = (next(iter(mid.values())) if len(mid) == 1
                               else group_into_layers(dname, mid, asked=asked))
    return group_into_layers(sovereign, domain_nodes, asked=asked)


# ---------------------------------------------------------------------------
# 6 — verify
# ---------------------------------------------------------------------------

def verify(root: Node, questions: Sequence[str]) -> Dict[str, Any]:
    """Ask real questions and record what happened, refusals included.

    A refusal is reported beside its candidates rather than as a failure.
    The tree is built so that a question it cannot place goes nowhere, and
    a verification that treated that as an error would pressure the next
    change toward guessing.
    """
    rows: List[Dict[str, Any]] = []
    reached = refused = 0
    for q in questions:
        out = descend(root, q)
        bare = descend(root, q, use_probe=False)
        many = gather(root, q)
        v = out.get("verdict")
        if v == "ANSWER":
            reached += 1
        else:
            refused += 1
        rows.append({
            "question": q,
            "verdict": v,
            "path": out.get("path"),
            "via": out.get("via"),
            "core": out.get("core"),
            "text": out.get("text"),
            "stopped_at": out.get("stopped_at"),
            "candidates": out.get("candidates", [])[:4],
            "router_only": bare.get("verdict"),
            "destinations": many["destinations"],
            "listed": [{"leaf": r["leaf"], "text": r["text"][:60]}
                       for r in many["results"] if r["verdict"] == "ANSWER"][:4],
        })
    router_only = sum(1 for r in rows if r["router_only"] == "ANSWER")
    listed = sum(1 for r in rows if r["listed"])
    return {"asked": len(rows), "answered_single_branch": reached,
            "refused_single_branch": refused,
            "answered_by_router_alone": router_only,
            "answered_as_list": listed, "rows": rows}


# ---------------------------------------------------------------------------
# the procedure
# ---------------------------------------------------------------------------

def build_sovereign(
    sources: Dict[str, Path],
    *,
    questions: Optional[Sequence[str]] = None,
    n_queries: int = 200,
    sovereign: str = "主権",
) -> Dict[str, Any]:
    """Run every stage in order and return the whole record."""
    stages: List[Stage] = []

    domains: Dict[str, Dict[str, CrossStore]] = {}
    grouping: Dict[str, Dict[str, List[str]]] = {}
    ing: List[Dict[str, Any]] = []
    for name, src in sources.items():
        leaves, rec = ingest_domain(name, Path(src))
        grouping[name] = rec.pop("_groups", {})
        if not leaves:
            stages.append(Stage("ingest", "UNKNOWN_EMPTY_DOMAIN", rec))
            continue
        domains[name] = leaves
        ing.append(rec)
    stages.append(Stage("ingest", "ANSWER" if domains else "UNKNOWN_NO_DOMAINS",
                        {"domains": ing}))
    if not domains:
        return ({"verdict": "UNKNOWN_NO_DOMAINS",
                 "stages": [s.__dict__ for s in stages]}, None)

    # Placement is simulated PER LEAF, because that is where the faces are.
    sim: List[Dict[str, Any]] = []
    for dname, leaves in domains.items():
        acc = rej = skip = 0
        deltas: List[float] = []
        for lname, st in leaves.items():
            r = simulate_domain(lname, st, n_queries=n_queries)
            if r["verdict"] == "ACCEPTED":
                acc += 1
                deltas.append(r["delta"]["uncovered_terms"])
            elif r["verdict"] == "REJECTED":
                rej += 1
            else:
                skip += 1
        sim.append({
            "domain": dname, "leaves": len(leaves),
            "accepted": acc, "rejected": rej, "skipped": skip,
            "mean_uncovered_delta": (round(sum(deltas) / len(deltas), 4)
                                     if deltas else None),
        })
    stages.append(Stage("simulate", "ANSWER", {"domains": sim}))

    flat = {d: _flatten(leaves) for d, leaves in domains.items()}
    p = plan(flat)
    stages.append(Stage("plan", "ANSWER", p))

    root = assemble(domains, grouping, sovereign=sovereign,
                    asked=questions or None)
    cap = over_capacity(root)
    stages.append(Stage("assemble", "ANSWER" if not cap["over"] else "OVER_CAPACITY",
                        {"shape": shape(root), "capacity": cap}))

    ver = verify(root, questions or [])
    stages.append(Stage("verify", "ANSWER", ver))

    return ({
        "verdict": "ANSWER",
        "sovereign": sovereign,
        "shape": shape(root),
        "stages": [s.__dict__ for s in stages],
    }, root)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Build one sovereign node from documents, stage by stage.")
    ap.add_argument("--domain", action="append", metavar="NAME=PATH",
                    required=True,
                    help="a domain and the folder its documents live in")
    ap.add_argument("--ask", action="append", default=[],
                    help="a question to descend after the build")
    ap.add_argument("--questions", help="a file of questions, one per line")
    ap.add_argument("--n-queries", type=int, default=200)
    ap.add_argument("--name", default="主権")
    ap.add_argument("--out", help="write the build record as JSON")
    a = ap.parse_args(argv)

    sources: Dict[str, Path] = {}
    for spec in a.domain:
        if "=" not in spec:
            print(json.dumps({"verdict": "UNKNOWN_BAD_DOMAIN_SPEC",
                              "got": spec, "want": "NAME=PATH"},
                             ensure_ascii=False))
            return 1
        name, path = spec.split("=", 1)
        sources[name.strip()] = Path(path.strip())

    qs = list(a.ask)
    if a.questions:
        qs += [ln.strip() for ln in
               Path(a.questions).read_text(encoding="utf-8").splitlines()
               if ln.strip()]

    record, _root = build_sovereign(sources, questions=qs,
                                    n_queries=a.n_queries, sovereign=a.name)
    text = json.dumps(record, ensure_ascii=False, indent=2)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        print(json.dumps({"verdict": record["verdict"], "wrote": a.out,
                          "shape": record["shape"]}, ensure_ascii=False, indent=2))
    else:
        print(text)
    return 0 if record["verdict"] == "ANSWER" else 1


if __name__ == "__main__":
    sys.exit(main())
