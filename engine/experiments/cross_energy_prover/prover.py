# -*- coding: utf-8 -*-
"""この実験の証明器は verantyx/prover.py へ昇格した(2026-08-20)。

ここは**別の写しではない**。`import prover` をパッケージ内の器官その
ものに解決する別名で、実験が `P._GROUND = ...` のようにモジュール属性を
差し替えたとき、差し替わるのは器官の側になる(写しを二つ持つと、測った
ものと出荷したものが乖離する — bidirectional_consensus の教訓)。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from verantyx import prover as _organ

sys.modules[__name__] = _organ
