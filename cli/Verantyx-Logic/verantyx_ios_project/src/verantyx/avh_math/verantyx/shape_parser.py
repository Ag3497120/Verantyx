from __future__ import annotations

import re

from .shape_ast import Var, Not, And, Or, Imp, Box, Dia, Iff, Expr

TOKEN_RE = re.compile(r"\[\]|<>|<->|->|&|\||~|!|\(|\)|[A-Za-z][A-Za-z0-9_]*")


def tokenize(s: str) -> list[str]:
    s = (s or "").replace(" ", "")
    s = s.replace("□", "[]").replace("◇", "<>")
    s = re.sub(r"\bbox\b", "[]", s, flags=re.IGNORECASE)
    s = re.sub(r"\bdiamond\b", "<>", s, flags=re.IGNORECASE)
    return TOKEN_RE.findall(s)


class Parser:
    def __init__(self, tokens: list[str]) -> None:
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> str | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def eat(self, t: str | None = None) -> str:
        cur = self.peek()
        if t and cur != t:
            raise SyntaxError(f"Expected {t}, got {cur}")
        if cur is None:
            raise SyntaxError("Unexpected end of input")
        self.pos += 1
        return cur

    def parse(self) -> Expr:
        return self.parse_iff()

    def parse_iff(self) -> Expr:
        left = self.parse_imp()
        if self.peek() == "<->":
            self.eat("<->")
            right = self.parse_iff()
            return Iff(left, right)
        return left

    def parse_imp(self) -> Expr:
        left = self.parse_or()
        if self.peek() == "->":
            self.eat("->")
            right = self.parse_imp()
            return Imp(left, right)
        return left

    def parse_or(self) -> Expr:
        left = self.parse_and()
        while self.peek() == "|":
            self.eat("|")
            right = self.parse_and()
            left = Or(left, right)
        return left

    def parse_and(self) -> Expr:
        left = self.parse_unary()
        while self.peek() == "&":
            self.eat("&")
            right = self.parse_unary()
            left = And(left, right)
        return left

    def parse_unary(self) -> Expr:
        if self.peek() in ("~", "!"):
            self.eat()
            return Not(self.parse_unary())
        if self.peek() == "[]":
            self.eat("[]")
            return Box(self.parse_unary())
        if self.peek() == "<>":
            self.eat("<>")
            return Dia(self.parse_unary())
        if self.peek() == "(":
            self.eat("(")
            expr = self.parse()
            self.eat(")")
            return expr
        return Var(self.eat())


def parse_formula(s: str) -> Expr:
    tokens = tokenize(s)
    parser = Parser(tokens)
    expr = parser.parse()
    if parser.peek() is not None:
        raise SyntaxError("Unexpected token at end")
    return expr
