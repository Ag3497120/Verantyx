"""Lay the federation out in 3D as the crosses it actually is.

A flat force graph draws a hairball and says nothing true: the nodes here
are not points with springs between them, they are orthoplexes — six arms
(+x -x +y -y +z -z) times four faces (north south east west), capacity 24,
measured to saturate at exactly that. Drawing them as dots discards the one
structural fact the whole engine is built on.

So the layout is computed, not simulated. Every position follows from the
geometry:

    sovereign   origin
    domain      one arm of the root cross
    leaf        an arm/face slot of its domain's cross
    core        an arm/face slot of its leaf's cross

A leaf holding more than 24 cores cannot place them on one cross, which is
the capacity law rather than a rendering limit. It grows a nested cross at
each arm tip and recurses, so a big statute chapter LOOKS like what it is —
a tree of crosses — and a small one looks like a single cross.

Deterministic placement also removes the flicker. A force simulation moves
every node every frame, so labels and detail swim; here a node is where the
structure puts it and stays there.
"""
from __future__ import annotations

from .paths import corpus_root  # noqa: E402

import argparse
import json
import math
import pickle
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

#: The real geometry, imported rather than restated so the picture cannot
#: drift from the engine.
from .consensus import AXES
from .face_roles import FACET_FACES

#: Unit vector per arm, in the order `AXES` names them.
ARM_VEC: Tuple[Tuple[float, float, float], ...] = (
    (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1),
)
CAPACITY = len(AXES) * len(FACET_FACES)


def _perp(v: Tuple[float, float, float]) -> Tuple[Tuple[float, float, float],
                                                  Tuple[float, float, float]]:
    """Two unit vectors spanning the face plane of an arm."""
    a = (0.0, 0.0, 1.0) if abs(v[2]) < 0.9 else (1.0, 0.0, 0.0)
    u = (v[1]*a[2] - v[2]*a[1], v[2]*a[0] - v[0]*a[2], v[0]*a[1] - v[1]*a[0])
    n = math.sqrt(sum(c*c for c in u)) or 1.0
    u = (u[0]/n, u[1]/n, u[2]/n)
    w = (v[1]*u[2] - v[2]*u[1], v[2]*u[0] - v[0]*u[2], v[0]*u[1] - v[1]*u[0])
    return u, w


#: face index -> (along u, along w), the four faces of one arm.
FACE_OFF = ((0.0, 1.0), (0.0, -1.0), (1.0, 0.0), (-1.0, 0.0))


def slots(centre: Tuple[float, float, float], arm_len: float,
          face_len: float) -> List[Tuple[Tuple[float, float, float], int, int]]:
    """The 24 places a cross has, as (position, arm index, face index)."""
    out = []
    for ai, v in enumerate(ARM_VEC):
        tip = (centre[0] + v[0]*arm_len, centre[1] + v[1]*arm_len,
               centre[2] + v[2]*arm_len)
        u, w = _perp(v)
        for fi, (du, dw) in enumerate(FACE_OFF):
            out.append(((tip[0] + u[0]*du*face_len + w[0]*dw*face_len,
                         tip[1] + u[1]*du*face_len + w[1]*dw*face_len,
                         tip[2] + u[2]*du*face_len + w[2]*dw*face_len), ai, fi))
    return out


def place(items: List[Any], centre: Tuple[float, float, float],
          arm_len: float, face_len: float, depth: int = 0
          ) -> List[Tuple[Any, Tuple[float, float, float], int, int, int]]:
    """Put ``items`` on a cross, nesting when they exceed capacity.

    Nesting rather than crowding: 24 is a measured ceiling on what one node
    distinguishes, so a 25th item genuinely belongs to a cross one level in.
    """
    s = slots(centre, arm_len, face_len)
    if len(items) <= CAPACITY:
        return [(it, s[i][0], s[i][1], s[i][2], depth)
                for i, it in enumerate(items)]
    out = []
    per = -(-len(items) // len(ARM_VEC))          # fill the arms
    for ai, v in enumerate(ARM_VEC):
        chunk = items[ai*per:(ai+1)*per]
        if not chunk:
            continue
        tip = (centre[0] + v[0]*arm_len, centre[1] + v[1]*arm_len,
               centre[2] + v[2]*arm_len)
        out += place(chunk, tip, arm_len*0.42, face_len*0.42, depth+1)
    return out


def build(root: Path, *, max_cores_per_leaf: Optional[int] = None) -> Dict[str, Any]:
    from .cross_store import CrossStore
    from .full_sovereign import learn_links, learn_units

    doms = pickle.loads((root / "build" / "federation.pkl").read_bytes())
    st = CrossStore()
    home: Dict[str, str] = {}
    for d in sorted(doms):
        for name, s in doms[d].items():
            st.source_labels |= getattr(s, "source_labels", set())
            for c, cr in s.crosses.items():
                st.crosses.setdefault(c, {}).update(cr)
                home.setdefault(c, f"{d}|{name}")
    lab = st.source_labels
    lp = (sorted((root / "wikipedia_doctrine").glob("*.txt"))
          + sorted((root / "wikipedia_cited").glob("*.txt")))
    links = learn_links(lp)
    units = learn_units(st)

    labels: List[str] = []
    kind: List[int] = []          # 0 sovereign 1 domain 2 leaf 3 core
    dom_i: List[int] = []
    pos: List[float] = []
    arm: List[int] = []
    face: List[int] = []
    idx: Dict[str, int] = {}
    dom_names = sorted(doms)

    def add(key: str, label: str, k: int, di: int,
            p: Tuple[float, float, float], a: int, f: int) -> int:
        i = len(labels)
        idx[key] = i
        labels.append(label); kind.append(k); dom_i.append(di)
        pos.extend((round(p[0], 1), round(p[1], 1), round(p[2], 1)))
        arm.append(a); face.append(f)
        return i

    add("root", "主権", 0, -1, (0.0, 0.0, 0.0), -1, -1)
    dom_slots = slots((0.0, 0.0, 0.0), 4200.0, 900.0)
    for di, d in enumerate(dom_names):
        # One arm per domain, not one slot: four domains on four faces of a
        # single arm would sit almost on top of each other.
        p = dom_slots[(di % len(ARM_VEC)) * len(FACET_FACES)][0]
        add(f"dom:{d}", d, 1, di, p, di, 0)

    edges: List[int] = []
    for di, d in enumerate(dom_names):
        dp = tuple(pos[idx[f"dom:{d}"]*3: idx[f"dom:{d}"]*3+3])
        leaves = sorted(doms[d])
        for (lname, lp3, la, lf, ld) in place(leaves, dp, 1500.0, 420.0):
            li = add(f"leaf:{lname}", lname.split("／")[-1][:44], 2, di,
                     lp3, la, lf)
            edges += [idx[f"dom:{d}"], li]
            s = doms[d][lname]
            cores = [c for c in sorted(s.crosses,
                                       key=lambda x: -len(s.crosses[x]))
                     if c not in lab and idx.get(f"core:{c}") is None]
            if max_cores_per_leaf:
                cores = cores[:max_cores_per_leaf]
            for (c, cp, ca, cf, cd) in place(cores, lp3, 220.0, 62.0):
                ci = add(f"core:{c}", c, 3, di, cp, ca, cf)
                edges += [li, ci]

    cite: List[int] = []
    for topic, arts in links.items():
        a = idx.get(f"core:{topic}")
        if a is None:
            continue
        for art in arts:
            b = idx.get(f"core:{art}")
            if b is not None:
                cite += [a, b]
    unit: List[int] = []
    for core, parts in units.items():
        a = idx.get(f"core:{core}")
        if a is None:
            continue
        for u in parts:
            b = idx.get(f"core:{u}")
            if b is not None:
                unit += [a, b]

    return {
        "labels": labels, "kind": kind, "dom": dom_i, "pos": pos,
        "arm": arm, "face": face,
        "edges": edges, "cite": cite, "unit": unit,
        "domains": dom_names,
        "meta": {
            "nodes": len(labels), "cores": sum(1 for k in kind if k == 3),
            "leaves": sum(1 for k in kind if k == 2),
            "arms": len(AXES), "faces": len(FACET_FACES), "capacity": CAPACITY,
            "links": sum(len(v) for v in links.values()),
            "units": len(units),
            "domain_counts": {d: len(doms[d]) for d in dom_names},
        },
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(corpus_root()))
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-cores-per-leaf", type=int, default=0)
    a = ap.parse_args(argv)
    d = build(Path(a.root),
              max_cores_per_leaf=a.max_cores_per_leaf or None)
    Path(a.out).write_text(json.dumps(d, ensure_ascii=False,
                                      separators=(",", ":")), encoding="utf-8")
    print(json.dumps({"verdict": "ANSWER", "out": a.out,
                      "bytes": Path(a.out).stat().st_size, **d["meta"]},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
