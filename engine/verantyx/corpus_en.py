"""English corpus streaming for large-scale reconstitution (LM-free store).

WikiText: prefer lock-free offline arrow cache under
  ~/.cache/huggingface/datasets/wikitext/...
Runners that call HuggingFace `load_dataset` need filesystem write access to
the HF datasets cache (lock files). Sandboxes that block those locks should
use the arrow-cache path (default) or `required_permissions: ["all"]`.
"""
from __future__ import annotations

import os
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

_TOKEN = re.compile(r"[a-z0-9']+")

_HF_DATASETS_ROOT = Path.home() / ".cache" / "huggingface" / "datasets"
_WIKITEXT_ROOT = _HF_DATASETS_ROOT / "wikitext"


@dataclass
class CorpusLoad:
    records: List[str]
    source: str
    fallback_reason: Optional[str] = None
    detail: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)

    def as_meta(self) -> Dict[str, Any]:
        out = {
            "source": self.source,
            "fallback_reason": self.fallback_reason,
            "detail": self.detail,
            "n_records": len(self.records),
        }
        out.update(self.meta)
        return out


def tokenize_en(text: str) -> List[str]:
    return _TOKEN.findall(text.lower())


def iter_tokens_from_texts(texts: Iterable[str]) -> Iterator[str]:
    for t in texts:
        for tok in tokenize_en(t):
            if len(tok) >= 2:
                yield tok


def iter_wikitext_arrow_rows(
    *,
    config: str = "wikitext-2-raw-v1",
    split: str = "train",
    max_rows: Optional[int] = None,
) -> Iterator[str]:
    """Yield non-empty WikiText rows from arrow cache without a full list."""
    arrow = find_wikitext_arrow(config=config, split=split)
    if arrow is None:
        raise FileNotFoundError(
            f"No WikiText arrow cache under {_WIKITEXT_ROOT / config}"
        )
    from datasets import Dataset

    ds = Dataset.from_file(str(arrow))
    n = 0
    for ex in ds:
        t = (ex.get("text") or "").strip()
        if not t:
            continue
        yield t
        n += 1
        if max_rows is not None and n >= max_rows:
            break


def iter_local_rows(path: Path) -> Iterator[str]:
    with Path(path).open(encoding="utf-8", errors="ignore") as f:
        for ln in f:
            s = ln.strip()
            if s:
                yield s


def iter_synthetic_rows(n_rows: int = 2000) -> Iterator[str]:
    for row in _synthetic_english(n_rows=n_rows):
        yield row


def iter_english_rows(
    *,
    source: str = "auto",
    max_rows: Optional[int] = 2000,
    local_path: Optional[Path] = None,
) -> Tuple[Iterator[str], str, Optional[str], Dict[str, Any]]:
    """Row iterator + (source_tag, fallback_reason, meta). No full materialization.

    Callers that need a list may still use load_english_corpus_ex.
    """
    meta: Dict[str, Any] = {"stream": True}
    if source == "local" or (source == "auto" and local_path and Path(local_path).is_file()):
        p = Path(local_path) if local_path else Path("corpus_en.txt")
        meta.update({"load_path": "local_stream", "path": str(p)})
        return iter_local_rows(p), f"local:{p}", None, meta

    if source == "synthetic":
        n = max_rows or 2000
        meta.update({"load_path": "synthetic_stream", "n_rows": n})
        return iter_synthetic_rows(n), "synthetic_en", None, meta

    if source.startswith("hf:"):
        # e.g. "hf:ag_news" / "hf:ag_news:text" — HF datasets, hard-fail
        # (no silent synthetic for an explicit source).
        parts = source.split(":")
        name = parts[1]
        text_field = parts[2] if len(parts) > 2 else "text"
        config = None
        if "#" in name:
            name, config = name.split("#", 1)
        from datasets import load_dataset  # type: ignore

        if config:
            ds = load_dataset(name, config, split="train")
        else:
            ds = load_dataset(name, split="train")

        def _hf_rows():
            n = 0
            for rec in ds:
                if max_rows is not None and n >= max_rows:
                    return
                txt = rec.get(text_field)
                if txt:
                    n += 1
                    yield str(txt)

        meta.update({"load_path": "hf_stream", "dataset": name, "field": text_field})
        return _hf_rows(), f"hf:{name}", None, meta

    if source in ("auto", "wikitext"):
        try:
            arrow = find_wikitext_arrow()
            if arrow is None:
                raise FileNotFoundError("no_wikitext_arrow_cache")
            meta.update({"load_path": "arrow_stream", "arrow": str(arrow)})
            it = iter_wikitext_arrow_rows(max_rows=max_rows)
            return it, "wikitext-2-raw-v1", None, meta
        except Exception as e:
            reason = f"{type(e).__name__}:{e}"
            if source == "wikitext":
                raise RuntimeError(
                    f"source=wikitext stream failed ({reason}). "
                    "Ensure arrow cache or HF lock write access."
                ) from e
            warnings.warn(
                f"WikiText stream unavailable ({reason}); synthetic_en",
                RuntimeWarning,
                stacklevel=2,
            )
            n = max_rows or 2000
            meta.update({"load_path": "auto_fallback_synthetic_stream", "n_rows": n})
            return iter_synthetic_rows(n), "synthetic_en", reason, meta

    n = max_rows or 2000
    meta.update({"load_path": f"unknown_stream:{source}", "n_rows": n})
    return (
        iter_synthetic_rows(n),
        "synthetic_en",
        f"unknown_source:{source}",
        meta,
    )


def iter_english_tokens(
    *,
    source: str = "auto",
    max_rows: Optional[int] = 2000,
    max_tokens: Optional[int] = None,
    local_path: Optional[Path] = None,
) -> Tuple[Iterator[str], str, Optional[str], Dict[str, Any]]:
    """Token iterator over streamed rows (no full text list)."""
    rows, tag, reason, meta = iter_english_rows(
        source=source, max_rows=max_rows, local_path=local_path
    )

    def _gen() -> Iterator[str]:
        n = 0
        for tok in iter_tokens_from_texts(rows):
            yield tok
            n += 1
            if max_tokens is not None and n >= max_tokens:
                break

    meta = dict(meta)
    meta["token_stream"] = True
    meta["max_tokens"] = max_tokens
    return _gen(), tag, reason, meta


def load_local_text(path: Path) -> List[str]:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    return [ln for ln in raw.splitlines() if ln.strip()]


def find_wikitext_arrow(
    *,
    config: str = "wikitext-2-raw-v1",
    split: str = "train",
) -> Optional[Path]:
    """Locate cached WikiText arrow file without touching HF locks."""
    cfg_root = _WIKITEXT_ROOT / config
    if not cfg_root.is_dir():
        return None
    # Prefer newest revision dir that contains the split arrow.
    name = f"wikitext-{split}.arrow"
    candidates: List[Path] = []
    for rev in sorted(cfg_root.glob("0.0.0/*"), key=lambda p: p.stat().st_mtime, reverse=True):
        if rev.is_dir():
            arrow = rev / name
            if arrow.is_file():
                candidates.append(arrow)
    if candidates:
        return candidates[0]
    # Fallback: any matching arrow under config
    hits = list(cfg_root.rglob(name))
    return hits[0] if hits else None


def load_wikitext_arrow_cache(
    *,
    config: str = "wikitext-2-raw-v1",
    split: str = "train",
    max_rows: Optional[int] = None,
) -> Tuple[List[str], Path]:
    """Lock-free load from local HF arrow cache (no FileLock / hub)."""
    arrow = find_wikitext_arrow(config=config, split=split)
    if arrow is None:
        raise FileNotFoundError(
            f"No WikiText arrow cache under {_WIKITEXT_ROOT / config} "
            f"(expected wikitext-{split}.arrow). Prefetch with datasets online once."
        )
    from datasets import Dataset

    ds = Dataset.from_file(str(arrow))
    rows: List[str] = []
    for ex in ds:
        t = (ex.get("text") or "").strip()
        if t:
            rows.append(t)
        if max_rows is not None and len(rows) >= max_rows:
            break
    if not rows:
        raise RuntimeError(f"WikiText arrow at {arrow} yielded 0 non-empty rows")
    return rows, arrow


def load_wikitext_hf(
    *,
    config: str = "wikitext-2-raw-v1",
    split: str = "train",
    max_rows: Optional[int] = None,
    offline: bool = True,
) -> List[str]:
    """Load WikiText via datasets.load_dataset (needs HF cache lock write access)."""
    if offline:
        os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
    from datasets import load_dataset

    ds = load_dataset("wikitext", config, split=split)
    rows: List[str] = []
    for ex in ds:
        t = (ex.get("text") or "").strip()
        if t:
            rows.append(t)
        if max_rows is not None and len(rows) >= max_rows:
            break
    return rows


def load_wikitext(
    *,
    config: str = "wikitext-2-raw-v1",
    split: str = "train",
    max_rows: Optional[int] = None,
    prefer_arrow_cache: bool = True,
) -> Tuple[List[str], str, Dict[str, Any]]:
    """Load WikiText; prefer lock-free arrow cache, then HF loader.

    Returns (rows, source_tag, meta).
    """
    errors: List[str] = []
    if prefer_arrow_cache:
        try:
            rows, arrow = load_wikitext_arrow_cache(
                config=config, split=split, max_rows=max_rows
            )
            return rows, config, {
                "load_path": "arrow_cache",
                "arrow": str(arrow),
            }
        except Exception as e:
            errors.append(f"arrow_cache:{type(e).__name__}:{e}")

    for offline in (True, False):
        try:
            rows = load_wikitext_hf(
                config=config, split=split, max_rows=max_rows, offline=offline
            )
            if rows:
                return rows, config, {
                    "load_path": "hf_load_dataset",
                    "offline": offline,
                }
            errors.append(f"hf_offline={offline}:empty")
        except Exception as e:
            errors.append(f"hf_offline={offline}:{type(e).__name__}:{e}")

    raise RuntimeError(
        "WikiText load failed. "
        "Need offline arrow cache under ~/.cache/huggingface/datasets/wikitext/ "
        "or filesystem write access for HF dataset locks. Errors: "
        + " | ".join(errors)
    )


def load_english_corpus(
    *,
    source: str = "auto",
    max_rows: Optional[int] = 2000,
    local_path: Optional[Path] = None,
) -> Tuple[List[str], str]:
    """Return (records, source_tag). Prefer load_english_corpus_ex for metadata."""
    loaded = load_english_corpus_ex(
        source=source, max_rows=max_rows, local_path=local_path
    )
    return loaded.records, loaded.source


def load_english_corpus_ex(
    *,
    source: str = "auto",
    max_rows: Optional[int] = 2000,
    local_path: Optional[Path] = None,
) -> CorpusLoad:
    """Return CorpusLoad with source tag and optional fallback_reason."""
    if source == "local" or (source == "auto" and local_path and Path(local_path).is_file()):
        p = Path(local_path) if local_path else Path("corpus_en.txt")
        return CorpusLoad(
            records=load_local_text(p),
            source=f"local:{p}",
            detail="local_file",
        )

    if source == "synthetic":
        return CorpusLoad(
            records=_synthetic_english(n_rows=max_rows or 2000),
            source="synthetic_en",
            detail="requested_synthetic",
        )

    if source in ("auto", "wikitext"):
        try:
            rows, tag, meta = load_wikitext(max_rows=max_rows, prefer_arrow_cache=True)
            return CorpusLoad(
                records=rows,
                source=tag,
                detail=str(meta.get("load_path", "wikitext")),
                meta=meta,
            )
        except Exception as e:
            reason = f"{type(e).__name__}:{e}"
            if source == "wikitext":
                # Hard fail for explicit wikitext — do not silently lie.
                raise RuntimeError(
                    f"source=wikitext failed ({reason}). "
                    "Ensure ~/.cache/huggingface/datasets/wikitext exists "
                    "or run outside sandbox so HF cache locks can be written."
                ) from e
            warnings.warn(
                f"WikiText unavailable ({reason}); falling back to synthetic_en",
                RuntimeWarning,
                stacklevel=2,
            )
            return CorpusLoad(
                records=_synthetic_english(n_rows=max_rows or 2000),
                source="synthetic_en",
                fallback_reason=reason,
                detail="auto_fallback_synthetic",
            )

    return CorpusLoad(
        records=_synthetic_english(n_rows=max_rows or 2000),
        source="synthetic_en",
        detail=f"unknown_source:{source}",
        fallback_reason=f"unknown_source:{source}",
    )


def _synthetic_english(n_rows: int = 2000) -> List[str]:
    nouns = [
        "river", "mountain", "city", "forest", "ocean", "bridge", "market",
        "school", "garden", "castle", "village", "desert", "island", "harbor",
        "temple", "library", "station", "museum", "factory", "meadow",
    ]
    verbs = [
        "flows", "stands", "grows", "shines", "moves", "opens", "holds",
        "carries", "builds", "keeps", "finds", "shows", "leads", "forms",
    ]
    adjs = [
        "bright", "quiet", "ancient", "narrow", "wide", "silent", "golden",
        "hidden", "rapid", "gentle", "distant", "familiar", "complex", "simple",
    ]
    rows = []
    for i in range(n_rows):
        n1 = nouns[i % len(nouns)]
        n2 = nouns[(i * 3) % len(nouns)]
        v = verbs[i % len(verbs)]
        a = adjs[(i * 5) % len(adjs)]
        rows.append(
            f"The {a} {n1} {v} near the {n2} while people watch the {a} sky."
        )
    return rows


def count_tokens(
    records: Sequence[str],
    *,
    max_tokens: Optional[int] = None,
) -> Tuple[Dict[str, int], int]:
    freq: Dict[str, int] = {}
    n = 0
    for tok in iter_tokens_from_texts(records):
        freq[tok] = freq.get(tok, 0) + 1
        n += 1
        if max_tokens is not None and n >= max_tokens:
            break
    return freq, n
