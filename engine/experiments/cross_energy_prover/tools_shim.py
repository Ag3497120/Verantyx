# -*- coding: utf-8 -*-
"""tools/build_mathlib_statements.py の束縛スキャナを実験から使う薄い橋。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.build_mathlib_statements import split_header


def split_binders_and_type(header: str):
    return split_header(header.strip())
