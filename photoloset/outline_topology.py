"""Deterministic topology repair for pixel boundaries and polygon outlines.

The repair deliberately refuses ambiguous graph topology.  In particular, two
loops which merely touch at a pixel corner are not silently spliced into a
figure eight: their shared vertex has two possible successors and is reported
as ``UNKNOWN_BRANCH_AMBIGUITY``.

Only the Python standard library is used.  Successful outlines use Cartesian
counter-clockwise winding and omit a repeated closing point.
"""

from __future__ import annotations

from collections import defaultdict
import math
from typing import Any, Dict, Iterable, List, Sequence, Tuple


Point = Tuple[float, float]
Edge = Tuple[Point, Point]

ANSWER = "ANSWER"
BAD_INPUT = "UNKNOWN_BAD_OUTLINE_INPUT"
EMPTY = "UNKNOWN_EMPTY_OUTLINE"
BRANCH_AMBIGUITY = "UNKNOWN_BRANCH_AMBIGUITY"
OPEN_BOUNDARY = "UNKNOWN_OPEN_BOUNDARY"
DEGENERATE = "UNKNOWN_DEGENERATE_OUTLINE"
SELF_INTERSECTS = "UNKNOWN_OUTLINE_SELF_INTERSECTS"

_ALGORITHM = "outline-topology-v1"
_EPSILON = 1.0e-12


def _provenance(input_kind: str, input_count: int, **extra: Any) -> Dict[str, Any]:
    value: Dict[str, Any] = {
        "algorithm": _ALGORITHM,
        "input_kind": input_kind,
        "input_count": input_count,
        "winding_convention": "counter_clockwise_cartesian",
        "closing_point_repeated": False,
    }
    value.update(extra)
    return value


def _unknown(code: str, why: str, provenance: Dict[str, Any]) -> Dict[str, Any]:
    return {"verdict": code, "why": why, "provenance": provenance}


def _point(value: Any) -> Point:
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or isinstance(value[0], bool) or isinstance(value[1], bool)):
        raise ValueError("a point must contain exactly two numbers")
    x, y = float(value[0]), float(value[1])
    if not math.isfinite(x) or not math.isfinite(y):
        raise ValueError("point coordinates must be finite")
    return (x, y)


def _edge(value: Any) -> Edge:
    if not isinstance(value, (list, tuple)):
        raise ValueError("an edge must be a pair of points")
    if len(value) == 4:
        return _point(value[:2]), _point(value[2:])
    if len(value) == 2:
        return _point(value[0]), _point(value[1])
    raise ValueError("an edge must be ((x1, y1), (x2, y2)) or four numbers")


def _area(points: Sequence[Point]) -> float:
    return 0.5 * sum(
        a[0] * b[1] - b[0] * a[1]
        for a, b in zip(points, points[1:] + points[:1])
    )


def _collapse_duplicates(points: Sequence[Point]) -> Tuple[List[Point], int]:
    out: List[Point] = []
    removed = 0
    for point in points:
        if out and point == out[-1]:
            removed += 1
        else:
            out.append(point)
    if len(out) > 1 and out[0] == out[-1]:
        out.pop()
        removed += 1
    return out, removed


def _cross(a: Point, b: Point, c: Point) -> float:
    return ((b[0] - a[0]) * (c[1] - b[1])
            - (b[1] - a[1]) * (c[0] - b[0]))


def _remove_collinear(points: Sequence[Point]) -> Tuple[List[Point], int]:
    """Remove collinear middle points, including zero-width A-B-A spikes."""
    out = list(points)
    removed = 0
    changed = True
    while changed and len(out) >= 3:
        changed = False
        for index in range(len(out)):
            before = out[index - 1]
            current = out[index]
            after = out[(index + 1) % len(out)]
            if abs(_cross(before, current, after)) <= _EPSILON:
                del out[index]
                removed += 1
                out, duplicate_count = _collapse_duplicates(out)
                removed += duplicate_count
                changed = True
                break
    return out, removed


def _orientation(a: Point, b: Point, c: Point) -> int:
    value = ((b[0] - a[0]) * (c[1] - a[1])
             - (b[1] - a[1]) * (c[0] - a[0]))
    if value > _EPSILON:
        return 1
    if value < -_EPSILON:
        return -1
    return 0


def _on_segment(a: Point, b: Point, p: Point) -> bool:
    return (min(a[0], b[0]) - _EPSILON <= p[0]
            <= max(a[0], b[0]) + _EPSILON
            and min(a[1], b[1]) - _EPSILON <= p[1]
            <= max(a[1], b[1]) + _EPSILON
            and _orientation(a, b, p) == 0)


def _segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    o1 = _orientation(a, b, c)
    o2 = _orientation(a, b, d)
    o3 = _orientation(c, d, a)
    o4 = _orientation(c, d, b)
    if o1 != o2 and o3 != o4:
        return True
    return ((o1 == 0 and _on_segment(a, b, c))
            or (o2 == 0 and _on_segment(a, b, d))
            or (o3 == 0 and _on_segment(c, d, a))
            or (o4 == 0 and _on_segment(c, d, b)))


def _first_self_intersection(points: Sequence[Point]) -> Tuple[int, int] | None:
    count = len(points)
    for first in range(count):
        a, b = points[first], points[(first + 1) % count]
        for second in range(first + 1, count):
            # Consecutive edges share their intended polygon vertex.
            if second == first + 1 or (first == 0 and second == count - 1):
                continue
            c, d = points[second], points[(second + 1) % count]
            if _segments_intersect(a, b, c, d):
                return first, second
    return None


def _canonical_ccw(points: Sequence[Point]) -> Tuple[List[Point], bool]:
    out = list(points)
    reversed_winding = _area(out) < 0.0
    if reversed_winding:
        out.reverse()
    # Fixing the first point makes output independent of edge order and of the
    # arbitrary first point supplied for a polygon.
    rotations = [out[index:] + out[:index] for index in range(len(out))]
    return min(rotations), reversed_winding


def _repair_loops(loops: Sequence[Sequence[Point]], input_kind: str,
                  input_count: int) -> Dict[str, Any]:
    cleaned: List[List[Point]] = []
    duplicate_count = 0
    collinear_count = 0
    base = _provenance(input_kind, input_count, loop_count=len(loops))

    for loop_index, loop in enumerate(loops):
        current, removed_duplicates = _collapse_duplicates(loop)
        current, removed_collinear = _remove_collinear(current)
        duplicate_count += removed_duplicates
        collinear_count += removed_collinear
        if len(current) < 3:
            return _unknown(
                DEGENERATE,
                "a boundary loop has fewer than three non-collinear points",
                dict(base, failed_loop=loop_index,
                     consecutive_duplicates_removed=duplicate_count,
                     collinear_points_removed=collinear_count),
            )
        crossing = _first_self_intersection(current)
        if crossing is not None:
            return _unknown(
                SELF_INTERSECTS,
                "a boundary loop contains intersecting non-adjacent edges",
                dict(base, failed_loop=loop_index,
                     intersecting_edge_indices=list(crossing),
                     consecutive_duplicates_removed=duplicate_count,
                     collinear_points_removed=collinear_count),
            )
        if abs(_area(current)) <= _EPSILON:
            return _unknown(
                DEGENERATE,
                "a boundary loop has zero enclosed area",
                dict(base, failed_loop=loop_index,
                     consecutive_duplicates_removed=duplicate_count,
                     collinear_points_removed=collinear_count),
            )
        cleaned.append(current)

    if not cleaned:
        return _unknown(EMPTY, "no boundary loop was supplied", base)

    # Absolute area selects the enclosing exterior over any interior holes.
    # Canonical point sequences provide a stable tie break for equal areas.
    normalized = [_canonical_ccw(loop)[0] for loop in cleaned]
    selected_index = min(
        range(len(cleaned)),
        key=lambda i: (-abs(_area(cleaned[i])), normalized[i]),
    )
    selected, reversed_winding = _canonical_ccw(cleaned[selected_index])
    provenance = dict(
        base,
        selected_loop=selected_index,
        selected_absolute_area=abs(_area(selected)),
        discarded_loop_count=len(cleaned) - 1,
        consecutive_duplicates_removed=duplicate_count,
        collinear_points_removed=collinear_count,
        winding_reversed=reversed_winding,
        canonical_start=list(selected[0]),
    )
    return {
        "verdict": ANSWER,
        "outline": [[x, y] for x, y in selected],
        "provenance": provenance,
    }


def repair_edges(edges: Iterable[Any]) -> Dict[str, Any]:
    """Repair unordered directed boundary edges into one exterior outline."""
    try:
        raw = list(edges)
    except TypeError:
        return _unknown(BAD_INPUT, "edges must be iterable",
                        _provenance("directed_edges", 0))
    if not raw:
        return _unknown(EMPTY, "no directed edges were supplied",
                        _provenance("directed_edges", 0, loop_count=0))
    try:
        parsed = [_edge(value) for value in raw]
    except (TypeError, ValueError, OverflowError) as error:
        return _unknown(BAD_INPUT, str(error),
                        _provenance("directed_edges", len(raw)))

    outgoing: Dict[Point, List[Point]] = defaultdict(list)
    incoming: Dict[Point, List[Point]] = defaultdict(list)
    for start, end in parsed:
        if start == end:
            return _unknown(DEGENERATE, "a directed edge has zero length",
                            _provenance("directed_edges", len(parsed)))
        outgoing[start].append(end)
        incoming[end].append(start)

    vertices = sorted(set(outgoing) | set(incoming))
    ambiguous = [point for point in vertices
                 if len(outgoing[point]) > 1 or len(incoming[point]) > 1]
    if ambiguous:
        return _unknown(
            BRANCH_AMBIGUITY,
            "a boundary vertex has more than one predecessor or successor",
            _provenance("directed_edges", len(parsed),
                        ambiguous_vertices=[list(point) for point in ambiguous]),
        )
    open_vertices = [point for point in vertices
                     if len(outgoing[point]) != 1 or len(incoming[point]) != 1]
    if open_vertices:
        return _unknown(
            OPEN_BOUNDARY,
            "directed boundary edges do not form closed loops",
            _provenance("directed_edges", len(parsed),
                        open_vertices=[list(point) for point in open_vertices]),
        )

    successor = {point: targets[0] for point, targets in outgoing.items()}
    unused = set(vertices)
    loops: List[List[Point]] = []
    while unused:
        start = min(unused)
        loop: List[Point] = []
        current = start
        while current not in loop:
            loop.append(current)
            unused.discard(current)
            current = successor[current]
        if current != start:
            # The degree checks make this unreachable for a valid finite graph,
            # but keep the refusal typed if malformed mappings ever reach here.
            return _unknown(OPEN_BOUNDARY, "an edge walk did not close at its start",
                            _provenance("directed_edges", len(parsed)))
        loops.append(loop)
    return _repair_loops(loops, "directed_edges", len(parsed))


def repair_polygon(points: Iterable[Any]) -> Dict[str, Any]:
    """Repair one ordered polygon point sequence."""
    try:
        raw = list(points)
    except TypeError:
        return _unknown(BAD_INPUT, "points must be iterable",
                        _provenance("polygon_points", 0))
    if not raw:
        return _unknown(EMPTY, "no polygon points were supplied",
                        _provenance("polygon_points", 0, loop_count=0))
    try:
        parsed = [_point(value) for value in raw]
    except (TypeError, ValueError, OverflowError) as error:
        return _unknown(BAD_INPUT, str(error),
                        _provenance("polygon_points", len(raw)))
    return _repair_loops([parsed], "polygon_points", len(parsed))


def repair_outline(boundary: Iterable[Any], kind: str | None = None) -> Dict[str, Any]:
    """Repair ``boundary`` after explicit or structural input-kind selection.

    ``kind`` may be ``"edges"`` or ``"polygon"``.  With no kind, values shaped
    as pairs of points (or flat four-number records) are directed edges; values
    shaped as individual coordinate pairs are polygon points.
    """
    try:
        values = list(boundary)
    except TypeError:
        return _unknown(BAD_INPUT, "boundary must be iterable",
                        _provenance("unknown", 0))
    if kind == "edges":
        return repair_edges(values)
    if kind == "polygon":
        return repair_polygon(values)
    if kind is not None:
        return _unknown(BAD_INPUT, "kind must be 'edges' or 'polygon'",
                        _provenance("unknown", len(values)))
    if not values:
        return _unknown(EMPTY, "no boundary data were supplied",
                        _provenance("unknown", 0, loop_count=0))

    first = values[0]
    looks_like_edge = (
        isinstance(first, (list, tuple))
        and (len(first) == 4
             or (len(first) == 2
                 and isinstance(first[0], (list, tuple))
                 and isinstance(first[1], (list, tuple))))
    )
    return repair_edges(values) if looks_like_edge else repair_polygon(values)


__all__ = [
    "ANSWER", "BAD_INPUT", "BRANCH_AMBIGUITY", "DEGENERATE", "EMPTY",
    "OPEN_BOUNDARY", "SELF_INTERSECTS", "repair_edges", "repair_outline",
    "repair_polygon",
]
