# -*- coding: utf-8 -*-
"""Optional, provably-transparent memoization for the cloth solver.

Both ``garment_sew.sew_and_drape`` and ``garment_drape.solve`` are pure
functions of their explicit arguments **plus** a small, closed set of
module-level constants and helper functions that live in exactly two
files: ``garment_sew.py`` and ``garment_drape.py``. Neither function reads
randomness, wall-clock time, thread state, or any global outside those two
files (verified by reading both bodies: no unseeded ``random`` calls, no
``time``/``datetime`` reads, single-threaded Jacobi update).

**Default OFF.** Nothing is cached unless the environment variable
``PHOTOLOSET_SOLVER_MEMO`` is set to a truthy value. A plain
``python3 tests/run_checks.py`` — including the one this project's
regression gate runs — never sets it, so that verification exercises the
exact, unmemoized code path. ``tests/falsifiers.py`` turns it on only for
the subprocess copies of ``run_checks.py`` it spawns while sweeping
``WHOLE_SUITE`` mutations, where the profile measured the same handful of
fixtures (the reference coat, the composed cape-dress, the skirt) recomputed
under ~32 near-identical mutated trees in a row.

**Key = hash(format version, module + qualname, the full source bytes of
every file the function's output can depend on, repr of every argument).**

Hashing the *entire source text* of both solver files — not a hand-picked
list of "the constants that matter" — is what makes this sound under
mutation: whichever line a ``WHOLE_SUITE`` entry edits inside either file
(``STITCH_STIFFNESS_RATIO``, ``GRAVITY``, ``SEAM_TOLERANCE_CM``, the Jacobi
step itself, a helper's body...) changes those bytes, which changes the
digest, which misses the cache — the mutated code runs for real rather than
serving a pre-mutation answer. A cache keyed only on the explicit call
arguments would be blind to a ``GRAVITY`` edit (it is read from a module
global inside the function body, never passed in) and would silently serve
the last run's answer under a mutation meant to change it — exactly the
"a condition that cannot fail" defect this codebase spends its own docstrings
warning about. The one ``WHOLE_SUITE`` entry that mutates
``garment_drape.py`` ("gravity moves, and the coat moves with it") is the
concrete case this guards: without the source-hash term the cache would
mask that mutation and the check that is supposed to catch it would never
see the mutated behaviour.

Deliberately **not** part of the key: which file elsewhere in the tree was
mutated, which check is asking, or any notion of "this entry's expected
outcome". The key is derived only from bytes that can actually reach the
function's return value — nothing about the calling context is trusted.

Any failure anywhere in this module (unreadable source file, unpicklable
argument, a full disk) falls through to calling the wrapped function
directly. A caching bug must never be able to change what a check sees —
at worst it costs the speedup, never correctness.
"""
from __future__ import annotations

import functools
import hashlib
import os
import pickle
import tempfile
from pathlib import Path
from typing import Callable, Sequence

_FORMAT_VERSION = b"photoloset-solve-cache/v1"


def _enabled() -> bool:
    return os.environ.get("PHOTOLOSET_SOLVER_MEMO", "") not in (
        "", "0", "false", "False", "no", "off",
    )


def _cache_dir() -> Path:
    override = os.environ.get("PHOTOLOSET_SOLVER_CACHE_DIR")
    base = Path(override) if override else (
        Path(tempfile.gettempdir()) / "photoloset_solver_cache"
    )
    base.mkdir(parents=True, exist_ok=True)
    return base


def memoize_solver(*, source_files: Sequence[str]) -> Callable:
    """Decorator factory. ``source_files`` are absolute paths (typically
    each dependency module's own ``__file__``, resolved once at decoration
    time) whose *bytes, re-read at every call*, are folded into the cache
    key alongside the call's actual arguments.
    """
    paths = tuple(source_files)

    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if not _enabled():
                return fn(*args, **kwargs)
            try:
                h = hashlib.sha256()
                h.update(_FORMAT_VERSION)
                h.update(fn.__module__.encode())
                h.update(b"\0")
                h.update(fn.__qualname__.encode())
                for path in paths:
                    h.update(b"\0FILE\0")
                    h.update(os.fspath(path).encode("utf-8", "surrogatepass"))
                    h.update(b"\0BYTES\0")
                    h.update(Path(path).read_bytes())
                h.update(b"\0ARGS\0")
                h.update(repr(args).encode("utf-8", "surrogatepass"))
                h.update(b"\0KWARGS\0")
                h.update(repr(sorted(kwargs.items()))
                         .encode("utf-8", "surrogatepass"))
                key = h.hexdigest()
            except Exception:
                # A key we could not safely compute must not change what
                # the caller sees -- just skip the cache for this call.
                return fn(*args, **kwargs)

            cache_file = _cache_dir() / f"{key}.pkl"
            if cache_file.exists():
                try:
                    with cache_file.open("rb") as f:
                        return pickle.load(f)
                except Exception:
                    pass  # corrupt/partial entry: fall through, recompute

            result = fn(*args, **kwargs)

            try:
                tmp = cache_file.with_name(
                    f"{cache_file.name}.tmp{os.getpid()}")
                with tmp.open("wb") as f:
                    pickle.dump(result, f, protocol=pickle.HIGHEST_PROTOCOL)
                os.replace(tmp, cache_file)  # atomic on POSIX: no reader
                                              # can ever observe a partial
                                              # write, even under concurrent
                                              # writers racing the same key
            except Exception:
                pass  # caching is an optimisation; a write failure must
                      # never fail the call that produced a real answer
            return result
        wrapper.__wrapped_uncached__ = fn  # for tests that want to bypass
        return wrapper
    return deco
