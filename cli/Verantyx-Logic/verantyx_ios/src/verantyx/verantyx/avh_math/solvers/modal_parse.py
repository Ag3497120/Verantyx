from __future__ import annotations

import re
from typing import List

_WS = re.compile(r"\s+")
_ATOM = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


class ModalParseError(ValueError):
    pass


def normalize_modal_surface(s: str) -> str:
    s = (s or "").strip()
    s = s.replace("□", "[]").replace("◇", "<>")
    s = re.sub(r"\bbox\b", "[]", s, flags=re.I)
    s = re.sub(r"\bdiamond\b", "<>", s, flags=re.I)
    s = s.replace("→", "->").replace("¬", "~")
    s = _WS.sub("", s)
    s = s.replace("[]", "[]")
    s = s.replace("<>", "<>")
    return s


def to_internal_modal(s: str) -> str:
    s = normalize_modal_surface(s)
    if not s:
        raise ModalParseError("empty")
    tokens = _tokenize(s)
    ast, pos = _parse_imp(tokens, 0)
    if pos != len(tokens):
        raise ModalParseError(f"unexpected token at {pos}: {tokens[pos]}")
    return _ast_to_prefix(ast)


def _tokenize(s: str) -> List[str]:
    out: List[str] = []
    i = 0
    while i < len(s):
        if s.startswith("->", i):
            out.append("->")
            i += 2
            continue
        if s.startswith("[]", i):
            out.append("[]")
            i += 2
            continue
        if s.startswith("<>", i):
            out.append("<>")
            i += 2
            continue
        c = s[i]
        if c in ("(", ")", "&", "|", "~"):
            out.append(c)
            i += 1
            continue
        j = i
        while j < len(s) and re.match(r"[A-Za-z0-9_]", s[j]):
            j += 1
        if j == i:
            raise ModalParseError(f"bad char: {s[i]}")
        out.append(s[i:j])
        i = j
    return out


def _parse_imp(toks: List[str], i: int):
    left, i = _parse_or(toks, i)
    if i < len(toks) and toks[i] == "->":
        i += 1
        right, i = _parse_imp(toks, i)
        return ("->", left, right), i
    return left, i


def _parse_or(toks: List[str], i: int):
    left, i = _parse_and(toks, i)
    while i < len(toks) and toks[i] == "|":
        i += 1
        right, i = _parse_and(toks, i)
        left = ("|", left, right)
    return left, i


def _parse_and(toks: List[str], i: int):
    left, i = _parse_unary(toks, i)
    while i < len(toks) and toks[i] == "&":
        i += 1
        right, i = _parse_unary(toks, i)
        left = ("&", left, right)
    return left, i


def _parse_unary(toks: List[str], i: int):
    if i >= len(toks):
        raise ModalParseError("unexpected end")
    if toks[i] in ("~", "[]", "<>"):
        op = toks[i]
        i += 1
        sub, i = _parse_unary(toks, i)
        return ("un", op, sub), i
    if toks[i] == "(":
        i += 1
        sub, i = _parse_imp(toks, i)
        if i >= len(toks) or toks[i] != ")":
            raise ModalParseError("missing ')'")
        i += 1
        return sub, i
    name = toks[i]
    i += 1
    if not _ATOM.match(name):
        raise ModalParseError(f"bad atom: {name}")
    return ("atom", name), i


def _ast_to_prefix(ast) -> str:
    if isinstance(ast, tuple) and ast[0] == "atom":
        return ast[1].lower()
    if isinstance(ast, tuple) and ast[0] == "un":
        op = ast[1]
        sub = _ast_to_prefix(ast[2])
        if op == "~":
            return f"not({sub})"
        if op == "[]":
            return f"box({sub})"
        if op == "<>":
            return f"dia({sub})"
        raise ModalParseError(f"unknown unary op: {op}")
    if isinstance(ast, tuple) and ast[0] in ("&", "|", "->"):
        op = ast[0]
        a = _ast_to_prefix(ast[1])
        b = _ast_to_prefix(ast[2])
        if op == "&":
            return f"and({a},{b})"
        if op == "|":
            return f"or({a},{b})"
        if op == "->":
            return f"imp({a},{b})"
    raise ModalParseError(f"bad ast: {ast}")
