import unittest

from photoloset.outline_topology import (
    BRANCH_AMBIGUITY,
    SELF_INTERSECTS,
    repair_edges,
    repair_outline,
    repair_polygon,
)


def edges(points):
    return list(zip(points, points[1:] + points[:1]))


def signed_area(points):
    return 0.5 * sum(
        a[0] * b[1] - b[0] * a[1]
        for a, b in zip(points, points[1:] + points[:1])
    )


class OutlineTopologyTests(unittest.TestCase):
    def test_diagonal_touch_figure_eight_rejects_branch_ambiguity(self):
        upper_left = [(0, 0), (2, 0), (2, 2), (0, 2)]
        lower_right = [(2, 2), (4, 2), (4, 4), (2, 4)]
        result = repair_edges(list(reversed(edges(upper_left) + edges(lower_right))))

        self.assertEqual(BRANCH_AMBIGUITY, result["verdict"])
        self.assertEqual([[2.0, 2.0]],
                         result["provenance"]["ambiguous_vertices"])

    def test_hole_is_discarded_in_favour_of_largest_exterior(self):
        exterior = [(0, 0), (8, 0), (8, 7), (0, 7)]
        hole_clockwise = [(2, 2), (2, 4), (5, 4), (5, 2)]
        unordered = edges(hole_clockwise)[2:] + edges(exterior)[1:] \
            + edges(hole_clockwise)[:2] + edges(exterior)[:1]

        result = repair_outline(unordered)

        self.assertEqual("ANSWER", result["verdict"])
        self.assertEqual([[0.0, 0.0], [8.0, 0.0], [8.0, 7.0], [0.0, 7.0]],
                         result["outline"])
        self.assertEqual(2, result["provenance"]["loop_count"])
        self.assertEqual(1, result["provenance"]["discarded_loop_count"])
        self.assertEqual(56.0, result["provenance"]["selected_absolute_area"])

    def test_reversed_winding_is_normalized_and_start_is_canonical(self):
        clockwise_with_shifted_start = [(4, 3), (4, 0), (0, 0), (0, 3)]

        result = repair_polygon(clockwise_with_shifted_start)

        self.assertEqual("ANSWER", result["verdict"])
        self.assertGreater(signed_area(result["outline"]), 0)
        self.assertEqual([0.0, 0.0], result["outline"][0])
        self.assertTrue(result["provenance"]["winding_reversed"])

    def test_duplicate_points_and_collinear_spike_are_removed(self):
        noisy = [
            (0, 0), (0, 0), (2, 0), (4, 0),
            (4, 4), (3, 4), (4, 4), (0, 4), (0, 0),
        ]

        result = repair_outline(noisy, kind="polygon")

        self.assertEqual("ANSWER", result["verdict"])
        self.assertEqual([[0.0, 0.0], [4.0, 0.0], [4.0, 4.0], [0.0, 4.0]],
                         result["outline"])
        self.assertGreaterEqual(
            result["provenance"]["consecutive_duplicates_removed"], 2)
        self.assertGreaterEqual(result["provenance"]["collinear_points_removed"], 2)

    def test_simple_dress_like_outline_is_repaired_deterministically(self):
        dress = [
            (3, 0), (5, 0), (5, 2), (7, 8), (8, 12),
            (0, 12), (1, 8), (3, 2),
        ]
        unordered = edges(dress)
        unordered = unordered[4:] + unordered[:4]

        first = repair_edges(unordered)
        second = repair_edges(list(reversed(unordered)))

        self.assertEqual("ANSWER", first["verdict"])
        self.assertEqual(first["outline"], second["outline"])
        self.assertEqual([0.0, 12.0], first["outline"][0])
        self.assertGreater(signed_area(first["outline"]), 0)
        self.assertEqual("outline-topology-v1",
                         first["provenance"]["algorithm"])

    def test_bow_tie_polygon_reports_typed_self_intersection(self):
        result = repair_polygon([(0, 0), (4, 4), (0, 4), (4, 0)])

        self.assertEqual(SELF_INTERSECTS, result["verdict"])
        self.assertEqual([0, 2],
                         result["provenance"]["intersecting_edge_indices"])


if __name__ == "__main__":
    unittest.main()
