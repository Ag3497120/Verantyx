"""Software watermarking via the obfuscation naming-variant, not the key.

Reframing, not a new claim: earlier drafts of "personal-fingerprint-derived
obfuscation" were pitched as making obfuscated code harder to *read* — that
claim doesn't survive scrutiny (see docs/OBFUSCATE_V2_PLAN.md, section 3).
The same mechanism (deterministically picking a naming scheme from a
store's fingerprint) is genuinely useful for a different, older, and more
modest goal: **after-the-fact leak attribution**, a real technique known as
software watermarking (Collberg & Thomborson). It doesn't need to win an
arms race against a reader — it only needs to survive ordinary
redistribution (copy/paste, file rename) long enough to be checked later.

What this gives you: if a `.obf` file surfaces somewhere it shouldn't,
`identify_candidates()` tells you which registered owners' variant
signature matches it. Because the variant space is small (96 points,
see `obfuscate.variant_space_size()`), a match is **evidence that narrows
a candidate list**, not proof of a single identity — say so honestly
every time this is surfaced to a user, and combine with other evidence
(who had access, timing) before acting on it.

Registry storage note: only the small derived `signature_id()` is ever
stored, never the raw fingerprint (which could be used to recompute the
AES key via `derive_key()`). The registry file is safe to share with
whoever needs to check a leak; the store/fingerprint is not.
"""
from __future__ import annotations

import ast
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from .cross_store import CrossStore
from .obfuscate import (
    VariantSignature,
    _HEX_LENS,
    _PREFIXES,
    _SEPS,
    fingerprint_store,
    variant_from_fingerprint,
    variant_space_size,
)

_NAME_RE = re.compile(
    r"^(" + "|".join(re.escape(p) for p in _PREFIXES) + r")"
    r"(" + "|".join(re.escape(s) for s in _SEPS if s) + r")?"
    r"([0-9a-fA-F]+)$"
)


def _collect_identifiers(source: str) -> List[str]:
    tree = ast.parse(source)
    names: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.append(node.id)
        elif isinstance(node, ast.arg):
            names.append(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
    return names


def detect_variant(obfuscated_source: str) -> Optional[VariantSignature]:
    """Infer which naming-scheme point produced this file's identifiers.

    Requires the file's renamed identifiers to be internally consistent
    (all produced by the same variant) — if they're not (hand-edited,
    mixed source, or not one of ours), returns None rather than guessing.
    """
    candidates: Dict[str, VariantSignature] = {}
    for name in _collect_identifiers(obfuscated_source):
        m = _NAME_RE.match(name)
        if not m:
            continue
        prefix, sep, hexpart = m.group(1), m.group(2) or "", m.group(3)
        if len(hexpart) not in _HEX_LENS:
            continue
        upper = hexpart == hexpart.upper() and hexpart != hexpart.lower()
        v = VariantSignature(prefix=prefix, hex_len=len(hexpart), upper=upper, sep=sep)
        candidates[v.signature_id()] = v

    if len(candidates) != 1:
        # zero matches (not our scheme) or inconsistent (multiple distinct
        # signatures in one file) — either way, don't guess.
        return None
    return next(iter(candidates.values()))


# ---------------------------------------------------------------------------
# registry — signature_id only, never the raw fingerprint
# ---------------------------------------------------------------------------

def register_owner(registry_path: Path, owner_id: str, store: CrossStore) -> Dict[str, Any]:
    variant = variant_from_fingerprint(fingerprint_store(store))
    registry: Dict[str, Any] = {}
    p = Path(registry_path)
    if p.exists():
        registry = json.loads(p.read_text())
    registry[owner_id] = variant.signature_id()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True))
    return {"ok": True, "owner_id": owner_id, "signature_id": variant.signature_id()}


def identify_candidates(registry_path: Path, obfuscated_source: str) -> Dict[str, Any]:
    variant = detect_variant(obfuscated_source)
    if variant is None:
        return {"ok": False, "error": "not_a_recognized_single_variant",
                "candidates": []}
    p = Path(registry_path)
    registry: Dict[str, str] = json.loads(p.read_text()) if p.exists() else {}
    sig = variant.signature_id()
    candidates = [owner for owner, s in registry.items() if s == sig]
    n = variant_space_size()
    return {
        "ok": True,
        "signature_id": sig,
        "candidates": candidates,
        "note": (
            f"variant space has only {n} points — a match narrows a "
            "candidate list, it does not prove identity on its own. "
            "Expect coincidental collisions once a registry holds roughly "
            f"sqrt({n})≈{int(n ** 0.5)} owners (birthday bound)."
        ),
    }
