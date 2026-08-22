"""Facet co-occurrence sense clustering — 「軸ずらしでニュアンス選択」の実体.

混合した core の十字（例: sun = 天文 + 企業 + 新聞）を、facet 同士の
類縁で語義クラスタに分割し、クエリの指定語（astronomy / sky / software…）
でクラスタを選択して読み出す。

類縁のオラクルはストア自身: facet f の「世界」= f 自身の十字の上位語。
  cross_words(f) = {f} ∪ top_facets(f)
  f ~ g  ⟺  g ∈ cross_words(f) ∨ f ∈ cross_words(g)
             ∨ |cross_words(f) ∩ cross_words(g)| ≥ min_shared
連結成分 = 語義クラスタ（決定論: count 降順 → アルファベット順）。

新規データを投入しても追加の格納は不要 — クラスタはクエリ時にストアから
再計算されるため、pour パイプラインはそのまま恩恵を受ける。

W2a (SPEC_2026-08-14_eight_gaps) adds a separate jawiki parenthetical
sidecar below (`build` / `resolve` / `senses_of`). The clustering API
above is unchanged. Sidecar, never a census.

## Measured — preregistered bank 2026-08-14, 10 surfaces

    sidecar surfaces                 122,988
    surfaces with >=2 senses         83,050
    (after one alias hop)            165,186
    total sense cores                297,218
    fork SENSE_SPLIT_NAMED_ABSTAIN   pass
    surface list                     10 / 10
    unambiguous RESOLVED             4 / 4
    context cases                    3 / 3
"""
from __future__ import annotations

from .paths import corpus_root  # noqa: E402

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from .cross_store import CrossStore
from .lex_filters import norm_words


def cross_words(
    store: CrossStore, sym: str, *, top: int = 12, max_mass: float = 800.0
) -> Set[str]:
    """f 自身の十字の上位語 + f の構成語 (十字が無ければ {f} のみ).

    汎用高頻度語 (mass > max_mass: "new", "open", "full"…) は世界から除外 —
    それ経由の類縁は語義ではなくコーパス頻度の産物なので (過連結の原因)。
    """
    out: Set[str] = set(norm_words(sym))
    for key in (sym, sym + "#p"):
        for f, _cnt in store.top_facets(key, top):
            for w in norm_words(f):
                if store.mass(w) + store.mass(w + "#p") <= max_mass:
                    out.add(w)
    return out


def facet_clusters(
    store: CrossStore,
    core: str,
    *,
    top: int = 20,
    min_shared: int = 3,
    max_mass: float = 800.0,
) -> List[List[str]]:
    """core の上位 facets を語義クラスタへ分割 (連結成分・決定論)."""
    facets = [f for f, _ in store.top_facets(core, top)]
    if not facets:
        return []
    words = {f: cross_words(store, f, max_mass=max_mass) for f in facets}

    def specific(sym: str) -> Set[str]:
        # containment 判定にも汎用語遮断を適用
        return {
            w
            for w in norm_words(sym)
            if store.mass(w) + store.mass(w + "#p") <= max_mass
        }

    parent: Dict[str, str] = {f: f for f in facets}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            # deterministic root: lexicographically smaller wins
            if rb < ra:
                ra, rb = rb, ra
            parent[rb] = ra

    for i, f in enumerate(facets):
        for g in facets[i + 1:]:
            linked = (
                bool(specific(g) & words[f])
                or bool(specific(f) & words[g])
                or len(words[f] & words[g]) >= min_shared
            )
            if linked:
                union(f, g)

    groups: Dict[str, List[str]] = {}
    for f in facets:
        groups.setdefault(find(f), []).append(f)

    counts = dict(store.top_facets(core, top))

    def cluster_weight(members: List[str]) -> Tuple[int, str]:
        return (-sum(counts.get(m, 0) for m in members), members[0])

    clusters = sorted(groups.values(), key=cluster_weight)
    for c in clusters:
        c.sort(key=lambda m: (-counts.get(m, 0), m))
    return clusters


def select_cluster(
    store: CrossStore,
    clusters: List[List[str]],
    specifiers: Set[str],
) -> Optional[int]:
    """指定語で語義クラスタを選ぶ。

    スコア = メンバー直接一致×3 + メンバーの世界 (cross_words) 一致×1。
    正のスコアが無ければ None (指定が効かない → 既定順)。
    """
    if not specifiers or not clusters:
        return None
    best_i: Optional[int] = None
    best_score = 0
    for i, members in enumerate(clusters):
        score = 0
        for m in members:
            if norm_words(m) & specifiers:
                score += 3
            if cross_words(store, m) & specifiers:
                score += 1
        if score > best_score:
            best_score = score
            best_i = i
    return best_i


def sense_facets(
    store: CrossStore,
    core: str,
    specifiers: Set[str],
    *,
    k: int = 4,
    top: int = 20,
    min_shared: int = 2,
) -> Dict[str, Any]:
    """指定語つき読み出し: 選ばれたクラスタの facets を count 順で返す."""
    clusters = facet_clusters(store, core, top=top, min_shared=min_shared)
    idx = select_cluster(store, clusters, specifiers)
    if idx is None:
        return {
            "selected": None,
            "clusters": clusters,
            "facets": [f for f, _ in store.top_facets(core, k)],
        }
    return {
        "selected": idx,
        "clusters": clusters,
        "facets": clusters[idx][:k],
    }


# ---------------------------------------------------------------------------
# W2a — jawiki parenthetical sense sidecar
# ---------------------------------------------------------------------------
#
# Short cores are collision dumps. 馬 aliases to ウマ; ingest of
# 「ウマ (麻雀)は、…」 fails the topic regex (')' sits before は) and
# first-run cores as ウマ, so the 馬/自転車 diff's only_a is 麻雀.
# Parenthetical titles stay separate cores here. resolve never merges
# them silently: one matching sense is RESOLVED, anything else is
# AMBIGUOUS_SENSE with the named list.

RESOLVED = "RESOLVED"
RESOLVED_PRIMARY = "RESOLVED_PRIMARY"
AMBIGUOUS_SENSE = "AMBIGUOUS_SENSE"
DAB_TAG = "曖昧さ回避"

OUT = (corpus_root() / "build"
       / "jawiki_senses.json")

# Surface is everything before the last parenthetical. Halfwidth and
# fullwidth brackets, optional space: 馬 (麻雀) / 水（曖昧さ回避）.
_PAREN = re.compile(r"^(?P<surface>.+?)\s*[\(（](?P<tag>.+)[\)）]$")


def parse_parenthetical(title: str) -> Optional[Tuple[str, str]]:
    """(surface, domain_tag) for a disambiguation title, else None."""
    t = (title or "").strip()
    if not t or ":" in t:
        return None
    m = _PAREN.match(t)
    if not m:
        return None
    surface = m.group("surface").strip()
    tag = m.group("tag").strip()
    if not surface or not tag:
        return None
    return surface, tag


def _lead_tokens(lead: str) -> List[str]:
    from .lang import ja_content_runs
    seen: List[str] = []
    for tok in ja_content_runs(lead or ""):
        if tok and tok not in seen:
            seen.append(tok)
    return seen


def _sense_sort_key(item: Dict[str, Any]) -> Tuple[int, str, str]:
    tag = str(item.get("domain_tag") or "")
    core = str(item.get("core") or "")
    return (0 if not tag else 1, tag, core)


def _named(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "core": item["core"],
        "domain_tag": item.get("domain_tag") or "",
    }


def build(
    pages: Iterable[Tuple[str, str]],
    *,
    aliases: Optional[Dict[str, str]] = None,
    extra_titles: Optional[Iterable[str]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """表層 → [{core, domain_tag, lead_tokens}].

    Every parenthetical title is its own core. A base article (the
    unmarked title) keeps its own entry on that surface. Redirects
    contribute their title with empty lead tokens. No census: this
    is a lookup table, not a vote.
    """
    leads: Dict[str, str] = {}
    titles: Set[str] = set()
    for title, lead in pages:
        if not title or ":" in title:
            continue
        titles.add(title)
        if lead:
            leads[title] = lead
    for t in extra_titles or ():
        if t and ":" not in t:
            titles.add(t)
    for t in (aliases or {}):
        if t and ":" not in t:
            titles.add(t)
        tgt = (aliases or {}).get(t)
        if tgt and ":" not in tgt:
            titles.add(tgt)

    redirects = {k for k in (aliases or {}) if k}
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    paren_titles: Set[str] = set()
    for title in titles:
        parsed = parse_parenthetical(title)
        if not parsed:
            continue
        surface, tag = parsed
        paren_titles.add(title)
        grouped.setdefault(surface, []).append({
            "core": title,
            "domain_tag": tag,
            "lead_tokens": _lead_tokens(leads.get(title, "")),
        })

    for surface, items in list(grouped.items()):
        # Redirects are not base articles (馬 → ウマ). The hop in
        # senses_of names the canonical unmarked sense.
        if (surface in titles and surface not in paren_titles
                and surface not in redirects):
            items.append({
                "core": surface,
                "domain_tag": "",
                "lead_tokens": _lead_tokens(leads.get(surface, "")),
            })
        # Dedup by core, deterministic order.
        by_core: Dict[str, Dict[str, Any]] = {}
        for it in items:
            by_core.setdefault(it["core"], it)
        grouped[surface] = sorted(by_core.values(), key=_sense_sort_key)
    return grouped


def senses_of(
    surface: str,
    senses: Dict[str, List[Dict[str, Any]]],
    aliases: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """Named sense list for a surface, one alias hop, deterministic.

    馬 redirects to ウマ, so ウマ's unmarked article and ウマ (麻雀)
    join 馬 (映画) / 馬 (姓) / 馬 (シャンチー). Never invents a sense
    that is not a title or that hop.
    """
    surface = (surface or "").strip()
    if not surface:
        return []
    aliases = aliases or {}
    by_core: Dict[str, Dict[str, Any]] = {}

    def _add(items: Iterable[Dict[str, Any]]) -> None:
        for it in items:
            core = it.get("core")
            if core and core not in by_core:
                by_core[core] = it

    _add(senses.get(surface) or [])
    hop = aliases.get(surface)
    if hop and hop != surface:
        hopped = senses.get(hop) or []
        _add(hopped)
        if hop not in senses and not parse_parenthetical(hop):
            _add([{"core": hop, "domain_tag": "", "lead_tokens": []}])
        elif hop in senses and not any(
            not (it.get("domain_tag") or "") for it in hopped
        ):
            _add([{"core": hop, "domain_tag": "", "lead_tokens": []}])
    return sorted(by_core.values(), key=_sense_sort_key)


def dab_base_target(
    surface: str,
    aliases: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """When a surface hops to 「X (曖昧さ回避)」, what bare X points at.

    みかん hops to ミカン (曖昧さ回避) and stops — the one-hop rule is
    right to stop, because a disambiguation page is not a sense. But
    Wikipedia's own title convention says the page is ABOUT the bare
    surface, and bare ミカン redirects to ウンシュウミカン, an article
    with a profile. Reporting that is not guessing the asker's meaning:
    it is naming one more candidate the encyclopedia itself wrote down,
    returned BESIDE the parenthetical senses and never substituted for
    them. Nil when the base has no redirect, or redirects to another
    disambiguation page (a chain this refuses to walk).
    """
    a = aliases or {}
    hop = a.get((surface or "").strip(), "")
    parsed = parse_parenthetical(hop)
    if not parsed or parsed[1] != DAB_TAG:
        return None
    target = a.get(parsed[0])
    if not target or target == hop:
        return None
    again = parse_parenthetical(target)
    if again and again[1] == DAB_TAG:
        return None
    return target


def is_disambiguation_title(
    title: str,
    aliases: Optional[Dict[str, str]] = None,
) -> bool:
    """Bare title is a 曖昧さ回避 page, or redirects to one."""
    t = (title or "").strip()
    if not t:
        return False
    hop = (aliases or {}).get(t, t)
    for cand in (t, hop):
        parsed = parse_parenthetical(cand)
        if parsed and parsed[1] == DAB_TAG:
            return True
    return False


def primary_sense(
    surface: str,
    items: List[Dict[str, Any]],
    aliases: Optional[Dict[str, str]] = None,
) -> Optional[Dict[str, Any]]:
    """Wikipedia's unmarked article, or the redirect target of the bare surface.

    None when the bare surface is a disambiguation page (or redirects to
    one): there is no primary to default to.
    """
    aliases = aliases or {}
    if is_disambiguation_title(surface, aliases):
        return None
    hop = aliases.get(surface, surface)
    if is_disambiguation_title(hop, aliases):
        return None
    unmarked = [
        it for it in items
        if not (it.get("domain_tag") or "")
        and not is_disambiguation_title(str(it.get("core") or ""), aliases)
    ]
    for it in unmarked:
        if it.get("core") == hop:
            return it
    if unmarked:
        return unmarked[0]
    if hop and not parse_parenthetical(hop):
        return {"core": hop, "domain_tag": "", "lead_tokens": []}
    return None


def _matches(item: Dict[str, Any], ctx: Set[str]) -> bool:
    if not ctx:
        return False
    tag = item.get("domain_tag") or ""
    if tag and tag in ctx:
        return True
    if tag:
        from .lang import ja_content_runs
        if any(tok in ctx for tok in ja_content_runs(tag)):
            return True
    leads = item.get("lead_tokens") or []
    return any(tok in ctx for tok in leads)


def resolve(
    surface: str,
    context_tokens: Optional[Iterable[str]] = None,
    *,
    senses: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    aliases: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Pick a core, default to Wikipedia's primary, or abstain.

    Context that hits exactly one sense is RESOLVED (unchanged).
    Two-or-more context hits stay AMBIGUOUS_SENSE. Context-free
    (or zero context hits) defaults to the unmarked base article
    — or the redirect target of the bare surface — as
    RESOLVED_PRIMARY, with the other senses named, not merged.
    AMBIGUOUS_SENSE only when no primary exists: the bare title
    is a 曖昧さ回避 page or redirects to one.
    """
    surface = (surface or "").strip()
    aliases = aliases or {}
    table = senses if senses is not None else {}
    items = senses_of(surface, table, aliases)
    ctx = {str(t) for t in (context_tokens or []) if t}

    def _resolved(item: Dict[str, Any], verdict: str) -> Dict[str, Any]:
        others = [_named(it) for it in items if it.get("core") != item.get("core")]
        out: Dict[str, Any] = {
            "verdict": verdict,
            "core": item["core"],
            "lead_tokens": list(item.get("lead_tokens") or []),
        }
        if others:
            out["other_senses"] = others
        return out

    if ctx:
        matched = [it for it in items if _matches(it, ctx)]
        if len(matched) == 1:
            return _resolved(matched[0], RESOLVED)
        if len(matched) >= 2:
            return {
                "verdict": AMBIGUOUS_SENSE,
                "senses": [_named(it) for it in items],
            }

    if is_disambiguation_title(surface, aliases):
        out = {
            "verdict": AMBIGUOUS_SENSE,
            "senses": [_named(it) for it in items] or [
                {"core": aliases.get(surface, surface), "domain_tag": DAB_TAG}
            ],
        }
        base = dab_base_target(surface, aliases)
        if base:
            out["base_target"] = base
        return out

    prim = primary_sense(surface, items, aliases)
    if prim is None:
        return {
            "verdict": AMBIGUOUS_SENSE,
            "senses": [_named(it) for it in items],
        }
    if not items:
        return {
            "verdict": RESOLVED,
            "core": prim["core"],
            "lead_tokens": list(prim.get("lead_tokens") or []),
        }
    others = [_named(it) for it in items if it.get("core") != prim.get("core")]
    if others:
        return _resolved(prim, RESOLVED_PRIMARY)
    return _resolved(prim, RESOLVED)


def save(
    senses: Dict[str, List[Dict[str, Any]]],
    path: Path = OUT,
    *,
    meta: Optional[Dict[str, Any]] = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    n_ge2 = sum(1 for v in senses.values() if len(v) >= 2)
    cores = {it["core"] for items in senses.values() for it in items}
    payload: Dict[str, Any] = {
        "source": "jawiki-parenthetical-titles",
        "n_surfaces": len(senses),
        "n_surfaces_ge2": n_ge2,
        "n_sense_cores": len(cores),
        "senses": senses,
    }
    if meta:
        payload.update(meta)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8")
    return path


def load(path: Path = OUT) -> Dict[str, List[Dict[str, Any]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get("senses", data)
    out: Dict[str, List[Dict[str, Any]]] = {}
    for surface, items in raw.items():
        if surface in ("source", "n_surfaces", "n_surfaces_ge2",
                       "n_sense_cores", "extractor"):
            continue
        if not isinstance(items, list):
            continue
        out[str(surface)] = items
    return out


def report(
    senses: Dict[str, List[Dict[str, Any]]],
    aliases: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    cores = {it["core"] for items in senses.values() for it in items}
    ge2 = sum(1 for v in senses.values() if len(v) >= 2)
    hopped_ge2 = 0
    if aliases:
        surfaces = set(senses) | {k for k in aliases if k in senses or aliases[k] in senses}
        for s in surfaces:
            if len(senses_of(s, senses, aliases)) >= 2:
                hopped_ge2 += 1
    return {
        "n_surfaces": len(senses),
        "n_surfaces_ge2": ge2,
        "n_surfaces_ge2_with_alias_hop": hopped_ge2 or ge2,
        "n_sense_cores": len(cores),
    }


def regression() -> Dict[str, Any]:
    """Fork-equivalent: toy sidecar, no corpus. Primary default, named others."""
    senses = {
        "馬": [
            {"core": "ウマ", "domain_tag": "", "lead_tokens": ["哺乳", "動物"]},
            {"core": "ウマ (麻雀)", "domain_tag": "麻雀",
             "lead_tokens": ["点数", "順位"]},
            {"core": "馬 (映画)", "domain_tag": "映画",
             "lead_tokens": ["作品"]},
        ],
        "ウマ": [
            {"core": "ウマ", "domain_tag": "", "lead_tokens": ["哺乳", "動物"]},
            {"core": "ウマ (麻雀)", "domain_tag": "麻雀",
             "lead_tokens": ["点数", "順位"]},
        ],
        "自転車": [
            {"core": "自転車", "domain_tag": "",
             "lead_tokens": ["車輪", "車両"]},
        ],
        "水 (曖昧さ回避)": [
            {"core": "水 (曖昧さ回避)", "domain_tag": "曖昧さ回避",
             "lead_tokens": ["曖昧", "回避"]},
        ],
    }
    aliases = {"馬": "ウマ"}
    empty = resolve("馬", [], senses=senses, aliases=aliases)
    mahjong = resolve("馬", ["麻雀"], senses=senses, aliases=aliases)
    animal = resolve("馬", ["哺乳"], senses=senses, aliases=aliases)
    two = resolve("馬", ["麻雀", "映画"], senses=senses, aliases=aliases)
    bike = resolve("自転車", [], senses=senses, aliases=aliases)
    knife = resolve("包丁", [], senses=senses, aliases=aliases)
    dab = resolve("水 (曖昧さ回避)", [], senses=senses, aliases=aliases)
    others = {s["core"] for s in (empty.get("other_senses") or [])}
    ok = all([
        empty.get("verdict") == RESOLVED_PRIMARY and empty.get("core") == "ウマ",
        "ウマ (麻雀)" in others and "馬 (映画)" in others,
        mahjong.get("verdict") == RESOLVED and mahjong.get("core") == "ウマ (麻雀)",
        animal.get("verdict") == RESOLVED and animal.get("core") == "ウマ",
        two.get("verdict") == AMBIGUOUS_SENSE,
        bike.get("verdict") == RESOLVED and bike.get("core") == "自転車",
        knife.get("verdict") == RESOLVED and knife.get("core") == "包丁",
        dab.get("verdict") == AMBIGUOUS_SENSE,
        parse_parenthetical("ウマ (麻雀)") == ("ウマ", "麻雀"),
        parse_parenthetical("水（曖昧さ回避）") == ("水", "曖昧さ回避"),
        parse_parenthetical("ウマ") is None,
        is_disambiguation_title("水 (曖昧さ回避)"),
        not is_disambiguation_title("馬", aliases),
    ])
    return {
        "experiment": "sense_split",
        "fork": "SENSE_SPLIT_NAMED_ABSTAIN",
        "pass": bool(ok),
        "result": {
            "empty": empty.get("verdict"),
            "primary": empty.get("core"),
            "mahjong": mahjong.get("core"),
            "animal": animal.get("core"),
            "two": two.get("verdict"),
            "bike": bike.get("core"),
            "knife": knife.get("core"),
            "dab": dab.get("verdict"),
        },
    }
