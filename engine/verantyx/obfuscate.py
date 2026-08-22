"""Reversible code obfuscation, keyed by a store's personal accumulated state.

Design covenant (see docs/DESIGN.md #obfuscation): the algorithm is public —
Kerckhoffs's principle — nothing here relies on the *process* being secret
or unusual-looking. What is secret is a KEY, derived from the owner's own
CrossStore state (facet counts, insertion order, adaptation history — the
path-dependent residue of exactly what that person poured, in what order).
Two people running the identical public code get different keys because
their stores differ, not because the algorithm differs.

That key derivation feeds a standard, vetted primitive (PBKDF2-HMAC-SHA256
→ AES-256-GCM via `cryptography`, not a home-grown cipher) — "don't roll
your own crypto" applies here as much as anywhere.

Pipeline:
  fingerprint_store(store)         → bytes  (deterministic, order-sensitive)
  derive_key(fingerprint, salt)    → 32-byte key (PBKDF2, stdlib only)
  obfuscate_python(path, key)      → renamed source + encrypted mapping
  deobfuscate_python(path, key)    → restores original names from mapping

Recovery: the derived key can be exported once and stored safely (password
manager, offline). Losing BOTH the original store state AND the exported
key means the mapping is permanently unrecoverable — this is the same
trade-off any personal-secret-derived key has, so back it up.
"""
from __future__ import annotations

import ast
import base64
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .cross_store import CrossStore

PBKDF2_ITERATIONS = 200_000
KEY_LEN = 32  # AES-256
_DEFAULT_SALT = b"verantyx-vera-obfuscate-v1"


# ---------------------------------------------------------------------------
# 1. store fingerprint — the personal, path-dependent secret material
# ---------------------------------------------------------------------------

def fingerprint_store(store: CrossStore) -> bytes:
    """Deterministic digest of THIS store's accumulated state.

    Order-sensitive on purpose: dict insertion order reflects the actual
    sequence of ``add()`` calls (i.e. real usage history), so two stores
    with identical final counts but different pour histories still differ
    here. Same store object (or the same store reloaded from its own save
    file) always yields the same fingerprint.
    """
    payload = json.dumps(
        {"crosses": store.crosses, "core_count": store.core_count},
        ensure_ascii=False,
        sort_keys=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).digest()


# ---------------------------------------------------------------------------
# 2. key derivation — standard KDF, no invented cryptography
# ---------------------------------------------------------------------------

def derive_key(fingerprint: bytes, *, salt: bytes = _DEFAULT_SALT) -> bytes:
    """PBKDF2-HMAC-SHA256 → 32-byte key. stdlib only (hashlib.pbkdf2_hmac)."""
    return hashlib.pbkdf2_hmac(
        "sha256", fingerprint, salt, PBKDF2_ITERATIONS, dklen=KEY_LEN
    )


def key_from_store(store: CrossStore, *, salt: bytes = _DEFAULT_SALT) -> bytes:
    return derive_key(fingerprint_store(store), salt=salt)


# ---------------------------------------------------------------------------
# 3. recovery key export/import — the actual portable secret once derived
# ---------------------------------------------------------------------------

def export_recovery_key(key: bytes, path: Path) -> Dict[str, Any]:
    """Save the derived key so the mapping stays decryptable even if the
    original store is later lost, corrupted, or migrated. Treat this file
    like a password: back it up somewhere the store itself doesn't live."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    b64 = base64.b64encode(key).decode("ascii")
    p.write_text(json.dumps({"recovery_key_b64": b64, "alg": "AES-256-GCM"}))
    os.chmod(p, 0o600)
    return {"ok": True, "path": str(p)}


def load_recovery_key(path: Path) -> bytes:
    d = json.loads(Path(path).read_text())
    return base64.b64decode(d["recovery_key_b64"])


# ---------------------------------------------------------------------------
# 4. AES-256-GCM — vetted primitive, not home-grown
# ---------------------------------------------------------------------------

def encrypt_mapping(mapping: Dict[str, Any], key: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    plaintext = json.dumps(mapping, ensure_ascii=False).encode("utf-8")
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return nonce + ciphertext  # nonce is not secret; prepend it


def decrypt_mapping(blob: bytes, key: bytes) -> Dict[str, Any]:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.exceptions import InvalidTag

    aesgcm = AESGCM(key)
    nonce, ciphertext = blob[:12], blob[12:]
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    except InvalidTag:
        raise ValueError(
            "wrong_key_or_corrupted_mapping: AES-GCM authentication failed "
            "(this is the point of using GCM — a wrong key never silently "
            "returns garbage, it refuses)"
        )
    return json.loads(plaintext.decode("utf-8"))


# ---------------------------------------------------------------------------
# 5. identifier renaming (the obfuscation transform itself — plain, public)
# ---------------------------------------------------------------------------

_RESERVED = set(dir(__builtins__)) | {
    "self", "cls", "__init__", "__name__", "__main__", "True", "False", "None",
}


class _Renamer(ast.NodeVisitor):
    """Collect renameable identifiers: function/class defs, assigned names,
    function parameters. Deterministic order of first appearance."""

    def __init__(self) -> None:
        self.order: List[str] = []
        self.seen: set = set()

    def _note(self, name: str) -> None:
        if name in _RESERVED or name.startswith("__") or name in self.seen:
            return
        self.seen.add(name)
        self.order.append(name)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._note(node.name)
        for a in node.args.args:
            self._note(a.arg)
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._note(node.name)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Store):
            self._note(node.id)
        self.generic_visit(node)


@dataclass(frozen=True)
class VariantSignature:
    """One point in a small, fixed space of equivalent naming schemes.

    Not a security boundary (see docs/OBFUSCATE_V2_PLAN.md — this raises
    the cost of running one static de-obfuscator across many distributed
    copies; it does not make any single copy harder to read once someone
    is looking at it). Its real job is watermarking: which point in this
    space a given obfuscated file uses is a durable, low-bandwidth signal
    that survives redistribution, usable to narrow down which store
    produced a leaked copy — see watermark.py.
    """

    prefix: str
    hex_len: int
    upper: bool
    sep: str

    def name_for(self, original: str, index: int) -> str:
        h = hashlib.sha256(f"{original}:{index}".encode()).hexdigest()[: self.hex_len]
        if self.upper:
            h = h.upper()
        return f"{self.prefix}{self.sep}{h}"

    def signature_id(self) -> str:
        return f"{self.prefix}|{self.hex_len}|{int(self.upper)}|{self.sep}"


# The default/legacy scheme — unchanged from before variants existed, so
# every pre-existing obfuscated file and fork keeps working byte-for-byte.
_DEFAULT_VARIANT = VariantSignature(prefix="_v", hex_len=8, upper=False, sep="")

# Each axis is independently derived from the fingerprint (different HMAC
# "context" per axis) so the combined space is the product of the axes,
# not just the size of one list. 8 * 3 * 2 * 2 = 96 points total — modest
# and deliberately not oversold: with N=96 equally-likely points, a
# birthday-bound collision between two *unrelated* owners' variants is
# expected once a registry holds roughly sqrt(96) ≈ 10 owners. A variant
# match is evidence to narrow a candidate list, never a standalone proof
# of identity — see watermark.py's `identify_candidates`.
_PREFIXES = ["_v", "_x", "_q", "_z", "_k", "_n", "_r", "_t"]
_HEX_LENS = [6, 8, 10]
_SEPS = ["", "_"]


def _axis_index(fingerprint: bytes, axis: str, n: int) -> int:
    h = hashlib.sha256(fingerprint + b":axis:" + axis.encode()).digest()
    return int.from_bytes(h[:4], "big") % n


def variant_space_size() -> int:
    return len(_PREFIXES) * len(_HEX_LENS) * 2 * len(_SEPS)


def variant_from_fingerprint(fingerprint: bytes) -> VariantSignature:
    """Deterministically pick a point in the naming-scheme space from a
    store fingerprint. Only derived integers (indices mod a small N) are
    computed here — never store or transmit the raw fingerprint itself as
    a "watermark," since `derive_key()` can turn a fingerprint back into
    the AES key. A `VariantSignature`/its `signature_id()` is safe to share
    (a registry, a support ticket, a legal record); the fingerprint is not.
    """
    return VariantSignature(
        prefix=_PREFIXES[_axis_index(fingerprint, "prefix", len(_PREFIXES))],
        hex_len=_HEX_LENS[_axis_index(fingerprint, "hexlen", len(_HEX_LENS))],
        upper=bool(_axis_index(fingerprint, "case", 2)),
        sep=_SEPS[_axis_index(fingerprint, "sep", len(_SEPS))],
    )


def _obfuscated_name(original: str, index: int, variant: VariantSignature = _DEFAULT_VARIANT) -> str:
    """Deterministic given (original, index, variant) — not reversible
    without the mapping (that's the point; reversibility comes from the
    stored map, not from the name itself being derivable)."""
    return variant.name_for(original, index)


@dataclass
class ObfuscationResult:
    mapping: Dict[str, str]          # original -> obfuscated
    reverse: Dict[str, str]          # obfuscated -> original
    obfuscated_source: str
    n_renamed: int


class _CollectSpans(ast.NodeVisitor):
    """Exact (lineno, col_start, col_end, replacement) for every REAL
    identifier occurrence in ``mapping`` — never touches string literals,
    comments, or docstrings, unlike a naive text-wide regex (which would
    also corrupt e.g. a dict key ``"price"`` that happens to share a name
    with a renamed variable ``price``, silently changing behavior)."""

    def __init__(self, mapping: Dict[str, str]):
        self.mapping = mapping
        self.spans: List[Tuple[int, int, int, str]] = []  # line, start, end, repl

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in self.mapping:
            self.spans.append(
                (node.lineno, node.col_offset, node.end_col_offset,
                 self.mapping[node.id])
            )
        self.generic_visit(node)

    def visit_arg(self, node: ast.arg) -> None:
        if node.arg in self.mapping:
            # node.end_col_offset spans the WHOLE "name: Annotation" when a
            # type annotation is present (verified empirically) — the bare
            # name is always exactly len(node.arg) chars from col_offset,
            # since annotations always start with ':' right after the name.
            end = node.col_offset + len(node.arg)
            self.spans.append(
                (node.lineno, node.col_offset, end, self.mapping[node.arg])
            )
        self.generic_visit(node)

    def _def_name_span(self, node, source_lines: List[str]) -> None:
        name = node.name
        if name not in self.mapping:
            return
        line = source_lines[node.lineno - 1]
        # "def "/"async def "/"class " precedes the name on this exact line
        idx = line.index(name, node.col_offset)
        self.spans.append((node.lineno, idx, idx + len(name), self.mapping[name]))

    def visit_with_source(self, tree: ast.AST, source_lines: List[str]) -> None:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self._def_name_span(node, source_lines)
        self.visit(tree)


def plan_obfuscation(source: str, variant: VariantSignature = _DEFAULT_VARIANT) -> ObfuscationResult:
    """Rename real identifiers only, via exact AST source positions —
    string literals, comments, and docstrings are never touched, so a
    coincidental name collision inside text can't silently change runtime
    behavior (e.g. a dict key string matching a renamed variable name).

    ``variant`` selects which point in the naming-scheme space to use
    (default: the original scheme, unchanged). Pass one derived by
    ``variant_from_fingerprint()`` to make this file's naming pattern a
    watermark tied to the owning store — see watermark.py."""
    tree = ast.parse(source)
    renamer = _Renamer()
    renamer.visit(tree)

    mapping: Dict[str, str] = {}
    for i, name in enumerate(renamer.order):
        mapping[name] = _obfuscated_name(name, i, variant)
    reverse = {v: k for k, v in mapping.items()}

    lines = source.splitlines(keepends=True)
    collector = _CollectSpans(mapping)
    collector.visit_with_source(tree, lines)

    by_line: Dict[int, List[Tuple[int, int, str]]] = {}
    for lineno, start, end, repl in collector.spans:
        by_line.setdefault(lineno, []).append((start, end, repl))
    for lineno, spans in by_line.items():
        spans.sort(key=lambda s: s[0], reverse=True)  # right-to-left
        line = lines[lineno - 1]
        for start, end, repl in spans:
            line = line[:start] + repl + line[end:]
        lines[lineno - 1] = line

    return ObfuscationResult(
        mapping=mapping, reverse=reverse, obfuscated_source="".join(lines),
        n_renamed=len(mapping),
    )


def restore_source(obfuscated_source: str, reverse: Dict[str, str]) -> str:
    """Restore via the SAME AST-positional technique, parsing the
    obfuscated source (which is syntactically valid Python — only names
    changed) so string literals containing an obfuscated-looking substring
    are never mistakenly touched."""
    tree = ast.parse(obfuscated_source)
    lines = obfuscated_source.splitlines(keepends=True)
    collector = _CollectSpans(reverse)
    collector.visit_with_source(tree, lines)

    by_line: Dict[int, List[Tuple[int, int, str]]] = {}
    for lineno, start, end, repl in collector.spans:
        by_line.setdefault(lineno, []).append((start, end, repl))
    for lineno, spans in by_line.items():
        spans.sort(key=lambda s: s[0], reverse=True)
        line = lines[lineno - 1]
        for start, end, repl in spans:
            line = line[:start] + repl + line[end:]
        lines[lineno - 1] = line
    return "".join(lines)


# ---------------------------------------------------------------------------
# 6. end-to-end: obfuscate a file, mapping encrypted with the store-derived key
# ---------------------------------------------------------------------------

def obfuscate_file(
    path: Path,
    store: CrossStore,
    *,
    out_path: Optional[Path] = None,
    map_path: Optional[Path] = None,
) -> Dict[str, Any]:
    source = Path(path).read_text()
    fingerprint = fingerprint_store(store)
    variant = variant_from_fingerprint(fingerprint)
    result = plan_obfuscation(source, variant=variant)
    key = derive_key(fingerprint)
    blob = encrypt_mapping({"reverse": result.reverse, "file": str(path)}, key)

    out_path = out_path or Path(path).with_suffix(Path(path).suffix + ".obf")
    map_path = map_path or Path(path).with_suffix(Path(path).suffix + ".obfmap")
    out_path.write_text(result.obfuscated_source)
    map_path.write_bytes(blob)
    return {
        "ok": True,
        "n_renamed": result.n_renamed,
        "obfuscated_file": str(out_path),
        "mapping_file": str(map_path),
        "variant_signature_id": variant.signature_id(),
        "note": "mapping is AES-256-GCM encrypted with a key derived from "
                "your store's state — back up the recovery key. The naming "
                "scheme used (variant_signature_id) is a watermark, not "
                "extra secrecy — see docs/WATERMARK.md",
    }


def deobfuscate_file(
    obf_path: Path,
    map_path: Path,
    *,
    store: Optional[CrossStore] = None,
    key: Optional[bytes] = None,
    out_path: Optional[Path] = None,
) -> Dict[str, Any]:
    if key is None:
        if store is None:
            return {"ok": False, "error": "need_store_or_key"}
        key = key_from_store(store)
    blob = Path(map_path).read_bytes()
    try:
        payload = decrypt_mapping(blob, key)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    obf_source = Path(obf_path).read_text()
    restored = restore_source(obf_source, payload["reverse"])
    out_path = out_path or Path(obf_path).with_suffix("").with_suffix(".restored.py")
    out_path.write_text(restored)
    return {"ok": True, "restored_file": str(out_path),
            "original_file": payload.get("file")}
