"""Forks for the fingerprint-derived naming-variant watermark.

Verifies the properties the watermark reframing actually depends on:
same store -> same variant every time (determinism, needed for a stable
watermark), a spread of different stores doesn't collapse to one constant
variant (the axis derivation is sensitive to input, not a broken no-op),
detection recovers the variant that produced a file and stays silent
(returns None) on code it didn't produce, and the registry never stores
raw fingerprints -- only the small derived signature_id.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List

from .cross_store import CrossStore
from .obfuscate import (
    fingerprint_store,
    plan_obfuscation,
    variant_from_fingerprint,
    variant_space_size,
)
from .watermark import detect_variant, identify_candidates, register_owner

_SAMPLE = '''
def calculate_total(price, tax_rate):
    subtotal = price * tax_rate
    return subtotal + price
'''


def wm_variant_determinism_fork() -> Dict[str, Any]:
    """Same store state -> same variant every time (a watermark that
    changes on every run is useless)."""
    st = CrossStore()
    st.add("apple", ["fruit", "sweet"])
    v1 = variant_from_fingerprint(fingerprint_store(st))
    v2 = variant_from_fingerprint(fingerprint_store(st))
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "s.json"
        st.save(p)
        st2 = CrossStore.load(p)
        v3 = variant_from_fingerprint(fingerprint_store(st2))
    ok = v1 == v2 == v3
    return {"experiment": "watermark", "fork": "WM_VARIANT_DETERMINISM",
            "pass": bool(ok), "result": {"signature_id": v1.signature_id()}}


def wm_variant_sensitivity_fork() -> Dict[str, Any]:
    """A spread of distinct stores must not all collapse onto the same
    variant (that would mean the axis derivation is a broken constant
    function). Not a pairwise-inequality guarantee -- with 96 points,
    coincidental collisions between two SPECIFIC stores are expected and
    fine; what would indicate a real bug is EVERY store in a reasonably
    sized, distinct sample landing on the same point."""
    ids = set()
    for i in range(24):
        st = CrossStore()
        st.add(f"item{i}", [f"facet{i}", f"n:{i}"])
        ids.add(variant_from_fingerprint(fingerprint_store(st)).signature_id())
    ok = len(ids) > 1
    return {"experiment": "watermark", "fork": "WM_VARIANT_SENSITIVITY",
            "pass": bool(ok), "result": {"distinct_signatures": len(ids),
                                          "space_size": variant_space_size()}}


def wm_detect_roundtrip_fork() -> Dict[str, Any]:
    """detect_variant() on a file obfuscated with a given store's variant
    recovers that exact variant."""
    st = CrossStore()
    st.add("project", ["lang:python"])
    variant = variant_from_fingerprint(fingerprint_store(st))
    plan = plan_obfuscation(_SAMPLE, variant=variant)
    detected = detect_variant(plan.obfuscated_source)
    ok = detected is not None and detected.signature_id() == variant.signature_id()
    return {"experiment": "watermark", "fork": "WM_DETECT_ROUNDTRIP",
            "pass": bool(ok),
            "result": {"expected": variant.signature_id(),
                       "detected": detected.signature_id() if detected else None}}


def wm_detect_silent_on_foreign_code_fork() -> Dict[str, Any]:
    """Ordinary, never-obfuscated Python must not be mistaken for a
    watermarked file -- detect_variant returns None rather than guessing."""
    plain = "def add(a, b):\n    return a + b\n"
    ok = detect_variant(plain) is None
    return {"experiment": "watermark", "fork": "WM_DETECT_SILENT_ON_FOREIGN_CODE",
            "pass": bool(ok), "result": {}}


def wm_registry_roundtrip_fork() -> Dict[str, Any]:
    """register_owner() + identify_candidates() finds the right owner, and
    the registry file on disk never contains the raw fingerprint (which
    would let anyone holding it recompute the AES key via derive_key())."""
    owner_store = CrossStore()
    owner_store.add("acme_corp", ["billing:module", "owner:acme"])

    with tempfile.TemporaryDirectory() as td:
        reg_path = Path(td) / "watermarks.json"
        register_owner(reg_path, "acme_corp", owner_store)

        variant = variant_from_fingerprint(fingerprint_store(owner_store))
        plan = plan_obfuscation(_SAMPLE, variant=variant)
        result = identify_candidates(reg_path, plan.obfuscated_source)

        raw_registry_text = reg_path.read_text()
        fp_hex = fingerprint_store(owner_store).hex()

    ok = (
        result["ok"]
        and "acme_corp" in result["candidates"]
        and fp_hex not in raw_registry_text  # never leak the fingerprint
    )
    return {"experiment": "watermark", "fork": "WM_REGISTRY_ROUNDTRIP",
            "pass": bool(ok), "result": {"candidates": result.get("candidates")}}


def all_watermark_forks() -> List[Dict[str, Any]]:
    return [
        wm_variant_determinism_fork(),
        wm_variant_sensitivity_fork(),
        wm_detect_roundtrip_fork(),
        wm_detect_silent_on_foreign_code_fork(),
        wm_registry_roundtrip_fork(),
    ]
