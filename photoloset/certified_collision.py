# -*- coding: utf-8 -*-
"""Exact-predicate certificates for linear cloth collision candidates.

The fast path uses floating-point orientation with an explicit roundoff bound.
Ambiguous signs are retried with high-precision ``Decimal`` and finally exact
``Fraction`` arithmetic.  Continuous zero-thickness queries form the exact
coplanarity polynomial, bound its roots in Bernstein form, and certify only:

* separation when every root interval is excluded, or
* collision when an exact rational root also satisfies exact containment.

Finite-thickness overlap, identically coplanar motion, non-rational roots, and
complexity limits remain typed UNKNOWN.  This is conservative certification,
not exact symbolic CCD for every algebraic configuration.
"""
from __future__ import annotations

import copy
from decimal import Decimal, localcontext
from fractions import Fraction
import math
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


FVec = Tuple[Fraction, Fraction, Fraction]
ANSWER = "ANSWER"
INVALID_INPUT = "UNKNOWN_CERTIFIED_COLLISION_INVALID_INPUT"
COMPLEXITY = "UNKNOWN_CERTIFIED_COLLISION_COMPLEXITY_LIMIT"
COPLANAR_MOTION = "UNKNOWN_CERTIFIED_COLLISION_IDENTICALLY_COPLANAR"
ALGEBRAIC_ROOT = "UNKNOWN_CERTIFIED_COLLISION_ALGEBRAIC_ROOT"
FINITE_THICKNESS = "UNKNOWN_CERTIFIED_COLLISION_FINITE_THICKNESS"
DEGENERATE_AT_ROOT = "UNKNOWN_CERTIFIED_COLLISION_DEGENERATE_AT_ROOT"
_FLOAT_EPS = 2.220446049250313e-16


class _Invalid(ValueError):
    pass


class _Complexity(ValueError):
    pass


def capabilities() -> Dict[str, Any]:
    """Declare implemented proof mechanisms and intentional non-claims."""
    return {
        "verdict": ANSWER,
        "backend": "stdlib_decimal_fraction_cpu_reference",
        "features": {
            "adaptive_orientation_2d": True,
            "adaptive_orientation_3d": True,
            "decimal_fallback": True,
            "fraction_exact_fallback": True,
            "linear_trajectory_coplanarity_polynomial": True,
            "bernstein_root_exclusion": True,
            "exact_rational_root_contact": True,
            "vertex_triangle_certificate": True,
            "edge_edge_certificate": True,
            "explicit_proof_obligations": True,
            "exact_all_algebraic_roots": False,
            "certified_finite_thickness_distance": False,
            "curved_trajectory_ccd": False,
            "industrial_certification": False,
        },
        "numeric_interpretation": (
            "int, Decimal, and Fraction retain their exact value; float is "
            "certified for its exact IEEE-754 binary value via as_integer_ratio"
        ),
        "limits": [
            "exact collision is certified only at rational roots isolated by subdivision",
            "identically coplanar motion requires a separate planar swept solver",
            "finite thickness is certified only when swept AABBs prove separation",
            "Fraction bit-size and Bernstein subdivision are explicitly budgeted",
        ],
    }


def _unknown(code: str, reason: str, obligations: Sequence[Mapping[str, Any]],
             **extra: Any) -> Dict[str, Any]:
    return {"verdict": code, "reasons": [reason],
            "proof_obligations": list(obligations), **extra}


def _fraction(value: Any, name: str) -> Fraction:
    if isinstance(value, bool):
        raise _Invalid(f"{name} must be a finite real number")
    if isinstance(value, Fraction):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise _Invalid(f"{name} must be finite")
        return Fraction(value)
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise _Invalid(f"{name} must be finite")
        numerator, denominator = value.as_integer_ratio()
        return Fraction(numerator, denominator)
    raise _Invalid(f"{name} must be int, float, Decimal, or Fraction")


def _fvec(value: Any, name: str) -> FVec:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise _Invalid(f"{name} must contain three finite components")
    return tuple(_fraction(component, f"{name}[{axis}]")
                 for axis, component in enumerate(value))  # type: ignore[return-value]


def _point2(value: Any, name: str) -> Tuple[Fraction, Fraction]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise _Invalid(f"{name} must contain two finite components")
    return _fraction(value[0], f"{name}[0]"), _fraction(value[1], f"{name}[1]")


def _bits(values: Iterable[Fraction]) -> int:
    result = 0
    for value in values:
        result = max(result, abs(value.numerator).bit_length(),
                     value.denominator.bit_length())
    return result


def _check_bits(values: Iterable[Fraction], maximum: int) -> None:
    values = tuple(values)
    used = _bits(values)
    if used > maximum:
        raise _Complexity(f"exact rational representation requires {used} bits; limit is {maximum}")


def _decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, Fraction):
        return Decimal(value.numerator)/Decimal(value.denominator)
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal.from_float(value)
    raise _Invalid("orientation component has unsupported type")


def _sign(value: Any) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def _orient2_fraction(a: Tuple[Fraction, Fraction], b: Tuple[Fraction, Fraction],
                      c: Tuple[Fraction, Fraction]) -> Fraction:
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def _orient3_fraction(a: FVec, b: FVec, c: FVec, d: FVec) -> Fraction:
    ad = tuple(a[i]-d[i] for i in range(3))
    bd = tuple(b[i]-d[i] for i in range(3))
    cd = tuple(c[i]-d[i] for i in range(3))
    return (ad[0]*(bd[1]*cd[2]-bd[2]*cd[1])
            - ad[1]*(bd[0]*cd[2]-bd[2]*cd[0])
            + ad[2]*(bd[0]*cd[1]-bd[1]*cd[0]))


def orientation2d(a: Sequence[Any], b: Sequence[Any], c: Sequence[Any], *,
                  max_exact_bits: int = 16384) -> Dict[str, Any]:
    """Adaptive sign of the 2D orientation determinant."""
    obligations = [{"name": "orientation_sign", "status": "PENDING"}]
    try:
        if isinstance(max_exact_bits, bool) or not isinstance(max_exact_bits, int) or max_exact_bits < 1:
            raise _Invalid("max_exact_bits must be a positive integer")
        fa, fb, fc = (_point2(value, name) for value, name in
                      ((a, "a"), (b, "b"), (c, "c")))
        try:
            floats = [[float(component) for component in point] for point in (fa, fb, fc)]
            adx, ady = floats[1][0]-floats[0][0], floats[1][1]-floats[0][1]
            bdx, bdy = floats[2][0]-floats[0][0], floats[2][1]-floats[0][1]
            determinant = adx*bdy-ady*bdx
            error = 8.0*_FLOAT_EPS*(abs(adx*bdy)+abs(ady*bdx))
        except OverflowError:
            determinant, error = math.nan, math.inf
        if math.isfinite(determinant) and abs(determinant) > error:
            obligations[0] = {"name": "orientation_sign", "status": "PROVED",
                              "method": "float_error_bound"}
            return {"verdict": ANSWER, "sign": _sign(determinant),
                    "method": "FLOAT_FILTER", "determinant_estimate": determinant,
                    "absolute_error_bound": error, "proof_obligations": obligations}

        decimal_signs = []
        for precision in (80, 160):
            with localcontext() as context:
                context.prec = precision
                da, db, dc = ([ _decimal(component) for component in point]
                              for point in (fa, fb, fc))
                decimal_det = ((db[0]-da[0])*(dc[1]-da[1])
                               -(db[1]-da[1])*(dc[0]-da[0]))
                decimal_signs.append(_sign(decimal_det))
        _check_bits((*fa, *fb, *fc), max_exact_bits)
        exact = _orient2_fraction(fa, fb, fc)
        _check_bits((exact,), max_exact_bits)
        obligations[0] = {"name": "orientation_sign", "status": "PROVED",
                          "method": "Fraction exact determinant"}
        return {"verdict": ANSWER, "sign": _sign(exact),
                "method": "FRACTION_EXACT", "determinant": str(exact),
                "decimal_filter_signs": decimal_signs,
                "absolute_error_bound": "0", "proof_obligations": obligations}
    except _Complexity as error:
        return _unknown(COMPLEXITY, str(error), obligations)
    except _Invalid as error:
        return _unknown(INVALID_INPUT, str(error), obligations)


def orientation3d(a: Sequence[Any], b: Sequence[Any], c: Sequence[Any],
                  d: Sequence[Any], *, max_exact_bits: int = 16384) -> Dict[str, Any]:
    """Adaptive sign of the tetrahedral orientation determinant."""
    obligations = [{"name": "orientation_sign", "status": "PENDING"}]
    try:
        if isinstance(max_exact_bits, bool) or not isinstance(max_exact_bits, int) or max_exact_bits < 1:
            raise _Invalid("max_exact_bits must be a positive integer")
        fa, fb, fc, fd = (_fvec(value, name) for value, name in
                          ((a, "a"), (b, "b"), (c, "c"), (d, "d")))
        try:
            points = [[float(component) for component in point]
                      for point in (fa, fb, fc, fd)]
            ad = [points[0][i]-points[3][i] for i in range(3)]
            bd = [points[1][i]-points[3][i] for i in range(3)]
            cd = [points[2][i]-points[3][i] for i in range(3)]
            terms = (ad[0]*bd[1]*cd[2], -ad[0]*bd[2]*cd[1],
                     -ad[1]*bd[0]*cd[2], ad[1]*bd[2]*cd[0],
                     ad[2]*bd[0]*cd[1], -ad[2]*bd[1]*cd[0])
            determinant = sum(terms)
            error = 16.0*_FLOAT_EPS*sum(abs(term) for term in terms)
        except OverflowError:
            determinant, error = math.nan, math.inf
        if math.isfinite(determinant) and abs(determinant) > error:
            obligations[0] = {"name": "orientation_sign", "status": "PROVED",
                              "method": "float_error_bound"}
            return {"verdict": ANSWER, "sign": _sign(determinant),
                    "method": "FLOAT_FILTER", "determinant_estimate": determinant,
                    "absolute_error_bound": error, "proof_obligations": obligations}

        decimal_signs = []
        for precision in (80, 160):
            with localcontext() as context:
                context.prec = precision
                pa, pb, pc, pd = ([ _decimal(component) for component in point]
                                  for point in (fa, fb, fc, fd))
                da = [pa[i]-pd[i] for i in range(3)]
                db = [pb[i]-pd[i] for i in range(3)]
                dc = [pc[i]-pd[i] for i in range(3)]
                value = (da[0]*(db[1]*dc[2]-db[2]*dc[1])
                         - da[1]*(db[0]*dc[2]-db[2]*dc[0])
                         + da[2]*(db[0]*dc[1]-db[1]*dc[0]))
                decimal_signs.append(_sign(value))
        _check_bits((*fa, *fb, *fc, *fd), max_exact_bits)
        exact = _orient3_fraction(fa, fb, fc, fd)
        _check_bits((exact,), max_exact_bits)
        obligations[0] = {"name": "orientation_sign", "status": "PROVED",
                          "method": "Fraction exact determinant"}
        return {"verdict": ANSWER, "sign": _sign(exact),
                "method": "FRACTION_EXACT", "determinant": str(exact),
                "decimal_filter_signs": decimal_signs,
                "absolute_error_bound": "0", "proof_obligations": obligations}
    except _Complexity as error:
        return _unknown(COMPLEXITY, str(error), obligations)
    except _Invalid as error:
        return _unknown(INVALID_INPUT, str(error), obligations)


def _vsub(a: FVec, b: FVec) -> FVec:
    return tuple(a[i]-b[i] for i in range(3))  # type: ignore[return-value]


def _vlerp(a: FVec, b: FVec, t: Fraction) -> FVec:
    return tuple(a[i]+(b[i]-a[i])*t for i in range(3))  # type: ignore[return-value]


def _cross_exact(a: FVec, b: FVec) -> FVec:
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2],
            a[0]*b[1]-a[1]*b[0])


def _poly_add(a: Sequence[Fraction], b: Sequence[Fraction]) -> List[Fraction]:
    return [(a[i] if i < len(a) else Fraction(0))+
            (b[i] if i < len(b) else Fraction(0))
            for i in range(max(len(a), len(b)))]


def _poly_mul(a: Sequence[Fraction], b: Sequence[Fraction]) -> List[Fraction]:
    result = [Fraction(0)]*(len(a)+len(b)-1)
    for i, av in enumerate(a):
        for j, bv in enumerate(b):
            result[i+j] += av*bv
    return result


def _linear_vector(start: FVec, end: FVec) -> Tuple[List[Fraction], ...]:
    return tuple([[start[i], end[i]-start[i]] for i in range(3)])


def _coplanarity_polynomial(a0: FVec, a1: FVec, b0: FVec, b1: FVec,
                            c0: FVec, c1: FVec, d0: FVec, d1: FVec) -> List[Fraction]:
    a, b, c, d = (_linear_vector(x0, x1) for x0, x1 in
                  ((a0, a1), (b0, b1), (c0, c1), (d0, d1)))
    ad = tuple(_poly_add(a[i], [-value for value in d[i]]) for i in range(3))
    bd = tuple(_poly_add(b[i], [-value for value in d[i]]) for i in range(3))
    cd = tuple(_poly_add(c[i], [-value for value in d[i]]) for i in range(3))
    cross = (
        _poly_add(_poly_mul(bd[1], cd[2]), [-v for v in _poly_mul(bd[2], cd[1])]),
        _poly_add(_poly_mul(bd[2], cd[0]), [-v for v in _poly_mul(bd[0], cd[2])]),
        _poly_add(_poly_mul(bd[0], cd[1]), [-v for v in _poly_mul(bd[1], cd[0])]),
    )
    result = [Fraction(0)]
    for axis in range(3):
        result = _poly_add(result, _poly_mul(ad[axis], cross[axis]))
    result += [Fraction(0)]*(4-len(result))
    return result[:4]


def _bernstein(power: Sequence[Fraction]) -> Tuple[Fraction, ...]:
    c0, c1, c2, c3 = power
    return (c0, c0+c1/Fraction(3),
            c0+Fraction(2, 3)*c1+c2/Fraction(3), c0+c1+c2+c3)


def _split_bernstein(values: Tuple[Fraction, ...]) -> Tuple[
        Tuple[Fraction, ...], Tuple[Fraction, ...]]:
    a, b, c, d = values
    ab, bc, cd = (a+b)/2, (b+c)/2, (c+d)/2
    abc, bcd = (ab+bc)/2, (bc+cd)/2
    middle = (abc+bcd)/2
    return (a, ab, abc, middle), (middle, bcd, cd, d)


def _root_intervals(power: Sequence[Fraction], max_depth: int,
                    max_nodes: int, max_bits: int) -> Dict[str, Any]:
    bernstein = _bernstein(power)
    _check_bits((*power, *bernstein), max_bits)
    if all(value == 0 for value in bernstein):
        return {"kind": "IDENTICALLY_ZERO", "exact_roots": [], "unresolved": []}
    stack = [(Fraction(0), Fraction(1), bernstein, 0)]
    exact_roots = set()
    unresolved = []
    nodes = 0
    while stack:
        lo, hi, values, depth = stack.pop()
        nodes += 1
        if nodes > max_nodes:
            return {"kind": "COMPLEXITY", "exact_roots": sorted(exact_roots),
                    "unresolved": unresolved+[(lo, hi)], "nodes": nodes}
        signs = {_sign(value) for value in values if value != 0}
        if len(signs) <= 1:
            zeros = [i for i, value in enumerate(values) if value == 0]
            if not zeros:
                continue
            if zeros == [0]:
                exact_roots.add(lo)
                continue
            if zeros == [3]:
                exact_roots.add(hi)
                continue
        if depth >= max_depth:
            unresolved.append((lo, hi))
            continue
        left, right = _split_bernstein(values)
        middle = (lo+hi)/2
        _check_bits((*left, *right), max_bits)
        stack.append((middle, hi, right, depth+1))
        stack.append((lo, middle, left, depth+1))
    return {"kind": "ISOLATED", "exact_roots": sorted(exact_roots),
            "unresolved": sorted(set(unresolved)), "nodes": nodes}


def _project(point: FVec, drop_axis: int) -> Tuple[Fraction, Fraction]:
    return tuple(point[i] for i in range(3) if i != drop_axis)  # type: ignore[return-value]


def _dominant_axis(normal: FVec) -> Optional[int]:
    magnitudes = [abs(value) for value in normal]
    maximum = max(magnitudes)
    return None if maximum == 0 else magnitudes.index(maximum)


def _point_in_triangle(point: FVec, triangle: Tuple[FVec, FVec, FVec]) -> Optional[bool]:
    normal = _cross_exact(_vsub(triangle[1], triangle[0]),
                          _vsub(triangle[2], triangle[0]))
    axis = _dominant_axis(normal)
    if axis is None:
        return None
    p = _project(point, axis)
    a, b, c = (_project(vertex, axis) for vertex in triangle)
    signs = [_sign(_orient2_fraction(x, y, p)) for x, y in ((a, b), (b, c), (c, a))]
    nonzero = {sign for sign in signs if sign != 0}
    return len(nonzero) <= 1


def _on_segment(a: Tuple[Fraction, Fraction], b: Tuple[Fraction, Fraction],
                p: Tuple[Fraction, Fraction]) -> bool:
    return (_orient2_fraction(a, b, p) == 0 and
            min(a[0], b[0]) <= p[0] <= max(a[0], b[0]) and
            min(a[1], b[1]) <= p[1] <= max(a[1], b[1]))


def _segments_intersect(a: FVec, b: FVec, c: FVec, d: FVec) -> Optional[bool]:
    direction_a, direction_b = _vsub(b, a), _vsub(d, c)
    normal = _cross_exact(direction_a, direction_b)
    axis = _dominant_axis(normal)
    if axis is None:
        if direction_a == (0, 0, 0) or direction_b == (0, 0, 0):
            return None
        # Parallel lines intersect only if they are exactly collinear in 3D.
        if _cross_exact(_vsub(c, a), direction_a) != (0, 0, 0):
            return False
        coordinate = max(range(3), key=lambda i: abs(direction_a[i]))
        return (max(min(a[coordinate], b[coordinate]),
                    min(c[coordinate], d[coordinate])) <=
                min(max(a[coordinate], b[coordinate]),
                    max(c[coordinate], d[coordinate])))
    pa, pb, pc, pd = (_project(point, axis) for point in (a, b, c, d))
    o1, o2 = _orient2_fraction(pa, pb, pc), _orient2_fraction(pa, pb, pd)
    o3, o4 = _orient2_fraction(pc, pd, pa), _orient2_fraction(pc, pd, pb)
    if _sign(o1)*_sign(o2) < 0 and _sign(o3)*_sign(o4) < 0:
        return True
    return ((_on_segment(pa, pb, pc) if o1 == 0 else False) or
            (_on_segment(pa, pb, pd) if o2 == 0 else False) or
            (_on_segment(pc, pd, pa) if o3 == 0 else False) or
            (_on_segment(pc, pd, pb) if o4 == 0 else False))


def _swept_separated(first: Sequence[Tuple[FVec, FVec]],
                      second: Sequence[Tuple[FVec, FVec]], thickness: Fraction) -> bool:
    for axis in range(3):
        first_values = [point[axis] for path in first for point in path]
        second_values = [point[axis] for path in second for point in path]
        if max(first_values)+thickness < min(second_values) or \
                max(second_values)+thickness < min(first_values):
            return True
    return False


def _parse_trajectory(start: Any, end: Any, name: str) -> Tuple[FVec, FVec]:
    return _fvec(start, f"{name}_start"), _fvec(end, f"{name}_end")


def _certificate(power: Sequence[Fraction], exact_test: Any, *,
                 max_depth: int, max_nodes: int, max_exact_bits: int,
                 query_kind: str) -> Dict[str, Any]:
    obligations: List[Dict[str, Any]] = [
        {"name": "coplanarity_roots_complete", "status": "PENDING"},
        {"name": "primitive_containment_at_roots", "status": "PENDING"},
        {"name": "earliest_time", "status": "PENDING"},
    ]
    roots = _root_intervals(power, max_depth, max_nodes, max_exact_bits)
    if roots["kind"] == "IDENTICALLY_ZERO":
        obligations[0]["status"] = "UNRESOLVED"
        return _unknown(COPLANAR_MOTION,
            "coplanarity polynomial is identically zero; planar swept overlap is required",
            obligations, polynomial=[str(value) for value in power])
    if roots["kind"] == "COMPLEXITY":
        obligations[0]["status"] = "UNRESOLVED"
        return _unknown(COMPLEXITY, "Bernstein subdivision exceeded max_nodes",
            obligations, unresolved_brackets=[[str(a), str(b)] for a, b in roots["unresolved"]],
            nodes=roots["nodes"])
    exact_hits = []
    degenerate = []
    for root in roots["exact_roots"]:
        contained = exact_test(root)
        if contained is None:
            degenerate.append(root)
        elif contained:
            exact_hits.append(root)
    unresolved = roots["unresolved"]
    if degenerate:
        obligations[1]["status"] = "UNRESOLVED"
        return _unknown(DEGENERATE_AT_ROOT,
            "primitive degenerates at an exact coplanarity root",
            obligations, roots=[str(root) for root in degenerate])
    if exact_hits:
        earliest = min(exact_hits)
        earlier_unresolved = [interval for interval in unresolved if interval[0] < earliest]
        obligations[0]["status"] = "PROVED" if not unresolved else "PARTIAL"
        obligations[1] = {"name": "primitive_containment_at_roots", "status": "PROVED",
                          "method": "exact Fraction orientation"}
        obligations[2]["status"] = "PROVED" if not earlier_unresolved else "UNRESOLVED"
        return {"verdict": ANSWER, "hit": True, "kind": query_kind,
                "toi_exact": str(earliest), "toi_normalized": float(earliest),
                "toi_error_bound": "0", "earliest_certified": not earlier_unresolved,
                "proof_obligations": obligations,
                "unresolved_brackets": [[str(a), str(b)] for a, b in unresolved]}
    if unresolved:
        obligations[0]["status"] = "UNRESOLVED"
        obligations[1]["status"] = "UNRESOLVED"
        return _unknown(ALGEBRAIC_ROOT,
            "possible non-rational coplanarity roots remain bracketed",
            obligations, unresolved_brackets=[[str(a), str(b)] for a, b in unresolved],
            normalized_error_bound=str(max(b-a for a, b in unresolved)))
    obligations[0] = {"name": "coplanarity_roots_complete", "status": "PROVED",
                      "method": "exact Bernstein sign exclusion"}
    obligations[1] = {"name": "primitive_containment_at_roots", "status": "PROVED",
                      "method": "exact test at every rational root"}
    obligations[2] = {"name": "earliest_time", "status": "NOT_APPLICABLE"}
    return {"verdict": ANSWER, "hit": False, "kind": query_kind,
            "toi_exact": None, "toi_error_bound": "0",
            "proof_obligations": obligations,
            "separation_certificate": "no contained coplanarity root in [0,1]"}


def certify_vertex_triangle(vertex_start: Sequence[Any], vertex_end: Sequence[Any],
                            triangle_start: Sequence[Sequence[Any]],
                            triangle_end: Sequence[Sequence[Any]], *,
                            thickness_m: Any = 0, max_depth: int = 48,
                            max_nodes: int = 200000,
                            max_exact_bits: int = 16384) -> Dict[str, Any]:
    """Conservatively certify a linear vertex-triangle query."""
    initial_obligations = [{"name": "input_and_budget", "status": "PENDING"}]
    try:
        if len(triangle_start) != 3 or len(triangle_end) != 3:
            raise _Invalid("triangle trajectories require three vertices")
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 1
               for value in (max_depth, max_nodes, max_exact_bits)):
            raise _Invalid("max_depth, max_nodes, and max_exact_bits must be positive integers")
        vertex = _parse_trajectory(vertex_start, vertex_end, "vertex")
        triangle = tuple(_parse_trajectory(triangle_start[i], triangle_end[i],
                                           f"triangle[{i}]") for i in range(3))
        thickness = _fraction(thickness_m, "thickness_m")
        if thickness < 0:
            raise _Invalid("thickness_m must be >= 0")
        all_values = [value for path in (vertex, *triangle) for point in path for value in point]
        _check_bits((*all_values, thickness), max_exact_bits)
        if _swept_separated((vertex,), triangle, thickness):
            return {"verdict": ANSWER, "hit": False, "kind": "VERTEX_TRIANGLE",
                    "toi_exact": None, "toi_error_bound": "0",
                    "proof_obligations": [{"name": "swept_volume_separation",
                                            "status": "PROVED",
                                            "method": "exact rational AABB"}],
                    "separation_certificate": "swept AABBs are disjoint"}
        if thickness > 0:
            return _unknown(FINITE_THICKNESS,
                "overlapping swept AABBs do not certify finite-thickness distance",
                [{"name": "finite_thickness_distance_minimum", "status": "UNRESOLVED"}],
                thickness_m=str(thickness))
        power = _coplanarity_polynomial(
            triangle[0][0], triangle[0][1], triangle[1][0], triangle[1][1],
            triangle[2][0], triangle[2][1], vertex[0], vertex[1])

        def exact_test(time: Fraction) -> Optional[bool]:
            point = _vlerp(*vertex, time)
            tri = tuple(_vlerp(*path, time) for path in triangle)
            return _point_in_triangle(point, tri)  # type: ignore[arg-type]
        return _certificate(power, exact_test, max_depth=max_depth,
                            max_nodes=max_nodes, max_exact_bits=max_exact_bits,
                            query_kind="VERTEX_TRIANGLE")
    except _Complexity as error:
        return _unknown(COMPLEXITY, str(error), initial_obligations)
    except _Invalid as error:
        return _unknown(INVALID_INPUT, str(error), initial_obligations)


def certify_edge_edge(edge_a_start: Sequence[Sequence[Any]],
                      edge_a_end: Sequence[Sequence[Any]],
                      edge_b_start: Sequence[Sequence[Any]],
                      edge_b_end: Sequence[Sequence[Any]], *,
                      thickness_m: Any = 0, max_depth: int = 48,
                      max_nodes: int = 200000,
                      max_exact_bits: int = 16384) -> Dict[str, Any]:
    """Conservatively certify two linearly moving edges."""
    initial_obligations = [{"name": "input_and_budget", "status": "PENDING"}]
    try:
        if any(len(group) != 2 for group in
               (edge_a_start, edge_a_end, edge_b_start, edge_b_end)):
            raise _Invalid("each edge state must contain two vertices")
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 1
               for value in (max_depth, max_nodes, max_exact_bits)):
            raise _Invalid("max_depth, max_nodes, and max_exact_bits must be positive integers")
        edge_a = tuple(_parse_trajectory(edge_a_start[i], edge_a_end[i],
                                         f"edge_a[{i}]") for i in range(2))
        edge_b = tuple(_parse_trajectory(edge_b_start[i], edge_b_end[i],
                                         f"edge_b[{i}]") for i in range(2))
        thickness = _fraction(thickness_m, "thickness_m")
        if thickness < 0:
            raise _Invalid("thickness_m must be >= 0")
        all_values = [value for path in (*edge_a, *edge_b) for point in path for value in point]
        _check_bits((*all_values, thickness), max_exact_bits)
        if _swept_separated(edge_a, edge_b, thickness):
            return {"verdict": ANSWER, "hit": False, "kind": "EDGE_EDGE",
                    "toi_exact": None, "toi_error_bound": "0",
                    "proof_obligations": [{"name": "swept_volume_separation",
                                            "status": "PROVED",
                                            "method": "exact rational AABB"}],
                    "separation_certificate": "swept AABBs are disjoint"}
        if thickness > 0:
            return _unknown(FINITE_THICKNESS,
                "overlapping swept AABBs do not certify finite-thickness distance",
                [{"name": "finite_thickness_distance_minimum", "status": "UNRESOLVED"}],
                thickness_m=str(thickness))
        power = _coplanarity_polynomial(
            edge_a[0][0], edge_a[0][1], edge_a[1][0], edge_a[1][1],
            edge_b[0][0], edge_b[0][1], edge_b[1][0], edge_b[1][1])

        def exact_test(time: Fraction) -> Optional[bool]:
            a, b = (_vlerp(*path, time) for path in edge_a)
            c, d = (_vlerp(*path, time) for path in edge_b)
            return _segments_intersect(a, b, c, d)
        return _certificate(power, exact_test, max_depth=max_depth,
                            max_nodes=max_nodes, max_exact_bits=max_exact_bits,
                            query_kind="EDGE_EDGE")
    except _Complexity as error:
        return _unknown(COMPLEXITY, str(error), initial_obligations)
    except _Invalid as error:
        return _unknown(INVALID_INPUT, str(error), initial_obligations)


def solve(request: Mapping[str, Any]) -> Dict[str, Any]:
    """Certify a deterministic, id-addressed list of VT/EE queries."""
    snapshot = copy.deepcopy(request)
    try:
        if not isinstance(request, Mapping):
            raise _Invalid("request must be a mapping")
        queries = request.get("queries")
        if not isinstance(queries, (list, tuple)):
            raise _Invalid("queries must be a sequence")
        defaults = {
            "thickness_m": request.get("thickness_m", 0),
            "max_depth": request.get("max_depth", 48),
            "max_nodes": request.get("max_nodes", 200000),
            "max_exact_bits": request.get("max_exact_bits", 16384),
        }
        seen = set()
        results = []
        for index, query in enumerate(queries):
            if not isinstance(query, Mapping):
                raise _Invalid(f"queries[{index}] must be a mapping")
            identifier = query.get("id")
            if not isinstance(identifier, str) or not identifier:
                raise _Invalid(f"queries[{index}].id must be a non-empty string")
            if identifier in seen:
                raise _Invalid("query ids must be unique")
            seen.add(identifier)
            options = {key: query.get(key, value) for key, value in defaults.items()}
            kind = query.get("kind")
            if kind == "VERTEX_TRIANGLE":
                result = certify_vertex_triangle(
                    query.get("vertex_start"), query.get("vertex_end"),
                    query.get("triangle_start"), query.get("triangle_end"), **options)
            elif kind == "EDGE_EDGE":
                result = certify_edge_edge(
                    query.get("edge_a_start"), query.get("edge_a_end"),
                    query.get("edge_b_start"), query.get("edge_b_end"), **options)
            else:
                raise _Invalid(f"queries[{index}].kind is not supported")
            results.append({"id": identifier, **result})
        results.sort(key=lambda item: item["id"])
        unresolved = [result for result in results if result["verdict"] != ANSWER]
        return {"verdict": ANSWER if not unresolved else unresolved[0]["verdict"],
                "results": results, "all_certified": not unresolved,
                "backend": capabilities(), "immutable_input_snapshot": snapshot}
    except _Invalid as error:
        return _unknown(INVALID_INPUT, str(error),
                        [{"name": "request_schema", "status": "FAILED"}],
                        immutable_input_snapshot=snapshot, backend=capabilities())
