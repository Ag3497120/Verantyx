"""Forks for store-keyed reversible obfuscation.

Verifies the actual security-relevant properties, not just plumbing:
same store → same key (determinism), different store content/order →
different key (per-person uniqueness), wrong key refuses loudly (AES-GCM
auth failure) rather than returning silent garbage, and the exported
recovery key alone (without the original store) is sufficient to decrypt.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List

from .cross_store import CrossStore
from .obfuscate import (
    decrypt_mapping,
    deobfuscate_file,
    derive_key,
    encrypt_mapping,
    export_recovery_key,
    fingerprint_store,
    key_from_store,
    load_recovery_key,
    obfuscate_file,
    plan_obfuscation,
    restore_source,
)

_SAMPLE = '''
def calculate_total(price, tax_rate):
    subtotal = price * tax_rate
    return subtotal + price


class OrderProcessor:
    def process(self, price):
        result = calculate_total(price, 1.21)
        return result
'''


def obf_rename_roundtrip_fork() -> Dict[str, Any]:
    """Rename → restore recovers byte-identical source; renaming is real
    (functions/classes/params/locals), not a no-op."""
    plan = plan_obfuscation(_SAMPLE)
    restored = restore_source(plan.obfuscated_source, plan.reverse)
    ok = (
        plan.n_renamed >= 4  # calculate_total, price, tax_rate, subtotal, ...
        and "calculate_total" not in plan.obfuscated_source
        and "OrderProcessor" not in plan.obfuscated_source
        and restored.strip() == _SAMPLE.strip()
    )
    return {"experiment": "obfuscate", "fork": "OBF_RENAME_ROUNDTRIP",
            "pass": bool(ok), "result": {"n_renamed": plan.n_renamed}}


def obf_key_determinism_fork() -> Dict[str, Any]:
    """Same store state → same key, every time (reproducible for the owner)."""
    st = CrossStore()
    st.add("apple", ["fruit", "sweet"])
    st.add("banana", ["fruit", "yellow"])
    k1 = key_from_store(st)
    k2 = key_from_store(st)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "s.json"
        st.save(p)
        st2 = CrossStore.load(p)
        k3 = key_from_store(st2)
    ok = k1 == k2 == k3 and len(k1) == 32
    return {"experiment": "obfuscate", "fork": "OBF_KEY_DETERMINISM",
            "pass": bool(ok), "result": {"key_len": len(k1)}}


def obf_key_uniqueness_fork() -> Dict[str, Any]:
    """Different personal data (or different pour ORDER) → different key —
    this is the actual security property: your accumulated state is the
    secret, not the (public) algorithm."""
    a = CrossStore()
    a.add("apple", ["fruit", "sweet"])
    a.add("banana", ["fruit", "yellow"])

    b = CrossStore()
    b.add("banana", ["fruit", "yellow"])  # same facts, different ORDER
    b.add("apple", ["fruit", "sweet"])

    c = CrossStore()
    c.add("apple", ["fruit", "sweet"])  # different content entirely

    ka, kb, kc = key_from_store(a), key_from_store(b), key_from_store(c)
    ok = ka != kb and ka != kc and kb != kc
    return {"experiment": "obfuscate", "fork": "OBF_KEY_UNIQUENESS",
            "pass": bool(ok), "result": {"order_sensitive": ka != kb}}


def obf_wrong_key_refuses_fork() -> Dict[str, Any]:
    """AES-GCM auth failure on wrong key → explicit typed error, never
    silently-wrong plaintext (this is why GCM, not a bare stream cipher)."""
    st = CrossStore()
    st.add("apple", ["fruit"])
    key = key_from_store(st)
    blob = encrypt_mapping({"reverse": {"_vabc": "secret_fn"}}, key)

    ok_roundtrip = decrypt_mapping(blob, key)["reverse"]["_vabc"] == "secret_fn"

    wrong_key = derive_key(b"totally-different-fingerprint")
    threw = False
    try:
        decrypt_mapping(blob, wrong_key)
    except ValueError as e:
        threw = "wrong_key_or_corrupted_mapping" in str(e)

    ok = ok_roundtrip and threw
    return {"experiment": "obfuscate", "fork": "OBF_WRONG_KEY_REFUSES",
            "pass": bool(ok), "result": {"refused": threw}}


def obf_end_to_end_file_fork() -> Dict[str, Any]:
    """Full pipeline on a real file: obfuscate with the owner's store,
    restore using (a) the same store and (b) an exported recovery key
    alone — the key, once exported, is a portable secret independent of
    the original store surviving."""
    st = CrossStore()
    st.add("project", ["lang:python", "owner:me"])

    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "billing.py"
        src.write_text(_SAMPLE)

        rep = obfuscate_file(src, st)
        obf_path = Path(rep["obfuscated_file"])
        map_path = Path(rep["mapping_file"])

        restored_via_store = deobfuscate_file(obf_path, map_path, store=st)

        key_path = Path(td) / "recovery.key"
        export_recovery_key(key_from_store(st), key_path)
        recovered_key = load_recovery_key(key_path)
        restored_via_key = deobfuscate_file(
            obf_path, map_path, key=recovered_key,
            out_path=Path(td) / "via_key.py",
        )

        ok = (
            rep["ok"]
            and restored_via_store["ok"]
            and Path(restored_via_store["restored_file"]).read_text().strip()
            == _SAMPLE.strip()
            and restored_via_key["ok"]
            and Path(restored_via_key["restored_file"]).read_text().strip()
            == _SAMPLE.strip()
        )
    return {"experiment": "obfuscate", "fork": "OBF_END_TO_END_FILE",
            "pass": bool(ok), "result": {"n_renamed": rep.get("n_renamed")}}


_COLLISION_SAMPLE = '''
def calculate_total(price):
    """This talks about price in a sentence, not as code."""
    lookup = {"price": price, "note": "the price field"}
    return lookup["price"]
'''


def obf_string_literals_untouched_fork() -> Dict[str, Any]:
    """Regression: a variable named ``price`` must not corrupt the STRING
    "price" used as a dict key / docstring prose, even though a naive
    whole-text-regex approach would rename both identically. AST-positional
    replacement only touches real ast.Name/arg/def occurrences."""
    import ast as _ast

    plan = plan_obfuscation(_COLLISION_SAMPLE)
    restored = restore_source(plan.obfuscated_source, plan.reverse)
    names_left = {
        n.id for n in _ast.walk(_ast.parse(plan.obfuscated_source))
        if isinstance(n, _ast.Name)
    }
    ok = (
        '"price"' in plan.obfuscated_source        # dict-key string survives
        and "price in a sentence" in plan.obfuscated_source  # docstring prose survives
        and "price" not in names_left               # the real variable IS renamed
        and restored.strip() == _COLLISION_SAMPLE.strip()
    )
    return {"experiment": "obfuscate", "fork": "OBF_STRING_LITERALS_UNTOUCHED",
            "pass": bool(ok),
            "result": {"obfuscated": plan.obfuscated_source}}


def _run(fn) -> Dict[str, Any]:
    """Run one fork, turning a missing optional extra into a named SKIP.

    Catching the ImportError is deliberate rather than keeping a list of
    "the forks that need cryptography": the dependency is also reached
    INDIRECTLY — obfuscate_file encrypts its own sidecar — so a hand-kept
    list goes stale the moment a fork gains a new call, and goes stale
    silently, which is the failure mode a suite can least afford.

    A skipped fork carries pass=False and a `skipped` reason. The runner
    keeps it out of the pass count instead of scoring it, because a check
    that never executed is neither a pass nor a failure and pretending
    otherwise misreports coverage on exactly the installs that have least.
    """
    try:
        return fn()
    except ModuleNotFoundError as exc:
        if exc.name != "cryptography":
            raise
        return {"experiment": "obfuscate",
                "fork": fn.__name__[:-len("_fork")].upper(),
                "pass": False, "skipped": "cryptography_not_installed",
                "result": {"install": 'python3 -m pip install "verantyx-vera[obfuscate] @ git+https://github.com/Ag3497120/Verantyx-Vera-alpha"'}}


def all_obfuscate_forks() -> List[Dict[str, Any]]:
    return [_run(fn) for fn in (
        obf_rename_roundtrip_fork,
        obf_key_determinism_fork,
        obf_key_uniqueness_fork,
        obf_wrong_key_refuses_fork,
        obf_string_literals_untouched_fork,
        obf_end_to_end_file_fork,
    )]
