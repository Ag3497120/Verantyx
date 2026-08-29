import math
import unittest

from photoloset.modular_assembly import (
    ANSWER,
    UNKNOWN_NEEDS_SEWING_CORPUS,
    AssemblyInvariantError,
    GarmentPiece,
    Mesh,
    Port,
    PortRef,
    Seam,
    SecondSkinBoundary,
    assemble,
    assemble_layers,
    combine_top_skirt,
    combine_top_trouser,
    graph_report,
    plan_sewing,
    stretch_to_second_skin,
)


def piece(name, category="module", direction="neutral", size=2.0,
          stretch=(0.8, 1.3), layer=0):
    mesh = Mesh(
        ((0.0, 0.0, 0.0), (size, 0.0, 0.0),
         (size, size, 0.0), (0.0, size, 0.0)),
        ((0, 1, 2), (0, 2, 3)),
    )
    return GarmentPiece(
        name, mesh,
        (Port("waist", (0, 1, 2, 3), "waist", direction,
              stretch[0], stretch[1]),),
        category, layer,
    )


def known_seam(name, a, b, prerequisites=()):
    return Seam(
        name, PortRef(a, "waist"), PortRef(b, "waist"),
        construction_method="plain seam",
        construction_source="human-verified fixture",
        prerequisites=prerequisites,
    )


class ModularAssemblyTests(unittest.TestCase):
    def test_top_trouser_and_top_skirt_are_geometry_first(self):
        top = piece("top", "top", "lower")
        trouser = piece("trouser", "trouser", "upper")
        skirt = piece("skirt", "skirt", "upper")

        trousers = combine_top_trouser(top, trouser)
        skirts = combine_top_skirt(top, skirt)

        self.assertEqual([p.category for p in trousers.pieces], ["top", "trouser"])
        self.assertEqual([p.category for p in skirts.pieces], ["top", "skirt"])
        self.assertEqual(graph_report(trousers)["components"], 1)
        self.assertEqual(graph_report(skirts)["beta"], 0)

    def test_compatible_loops_can_merge_into_one_mesh(self):
        top = piece("top", "top", "lower")
        skirt = piece("skirt", "skirt", "upper")
        joined = combine_top_skirt(top, skirt, merge_compatible=True)

        self.assertIsNotNone(joined.merged_mesh)
        self.assertEqual(len(joined.merged_mesh.mesh.vertices), 4)
        self.assertTrue(any(len(sources) == 2
                            for sources in joined.merged_mesh.vertex_sources))

    def test_per_seam_merge_does_not_weld_unmarked_interfaces(self):
        a, b, c = piece("a"), piece("b"), piece("c")
        def with_two_ports(p):
            return GarmentPiece(
                p.name, p.mesh,
                (p.ports[0], Port("waist2", (0, 1, 2, 3), "waist")),
                p.category, p.layer,
            )
        a, b, c = map(with_two_ports, (a, b, c))
        assembly = assemble((a, b, c), (
            Seam("weld", PortRef("a", "waist"), PortRef("b", "waist"),
                 merge=True),
            Seam("sew", PortRef("b", "waist2"), PortRef("c", "waist")),
        ))

        self.assertIsNotNone(assembly.merged_mesh)
        self.assertEqual(len(assembly.merged_mesh.mesh.vertices), 8)
        sources = assembly.merged_mesh.vertex_sources
        self.assertTrue(any({name for name, _ in group} == {"a", "b"}
                            for group in sources))
        self.assertTrue(all(not ({name for name, _ in group} == {"b", "c"})
                            for group in sources))

    def test_second_skin_reports_required_stretch_and_limit(self):
        top = piece("top", "top", "lower", size=2.0, stretch=(0.9, 1.2))
        result = stretch_to_second_skin(top, "waist", SecondSkinBoundary("waist", 8.8))

        self.assertEqual(result["verdict"], ANSWER)
        self.assertAlmostEqual(result["rest_length"], 8.0)
        self.assertAlmostEqual(result["stretch_ratio"], 1.1)
        self.assertAlmostEqual(result["percent"], 10.0)
        self.assertTrue(result["within_declared_limits"])

        too_large = stretch_to_second_skin(
            top, "waist", SecondSkinBoundary("waist", 10.0))
        self.assertFalse(too_large["within_declared_limits"])

    def test_layers_remain_separate_without_an_explicit_attachment(self):
        inner = piece("inner", layer=99)
        outer = piece("outer", layer=99)
        result = assemble_layers(((inner,), (outer,)))

        self.assertEqual([p.layer for p in result.pieces], [0, 1])
        self.assertEqual(graph_report(result)["components"], 2)

        cross_layer = Seam(
            "tack", PortRef("inner", "waist"), PortRef("outer", "waist"),
            allow_cross_layer=True,
        )
        attached = assemble_layers(((inner,), (outer,)), (cross_layer,))
        self.assertEqual(graph_report(attached)["components"], 1)

    def test_unknown_sewing_knowledge_is_typed_and_not_guessed(self):
        top = piece("top", "top", "lower")
        skirt = piece("skirt", "skirt", "upper")
        result = plan_sewing(combine_top_skirt(top, skirt))

        self.assertEqual(result["verdict"], UNKNOWN_NEEDS_SEWING_CORPUS)
        self.assertEqual(result["missing_seams"], ["top+skirt:waist"])
        self.assertNotIn("operations", result)

    def test_known_dependencies_form_a_partial_order_and_beta_is_checked(self):
        a = piece("a")
        b = piece("b")
        c = piece("c")
        # Each module needs a distinct port for each incident seam.
        def with_two_ports(p):
            return GarmentPiece(
                p.name, p.mesh,
                (p.ports[0], Port("waist2", (0, 1, 2, 3), "waist")),
                p.category, p.layer,
            )
        a, b, c = map(with_two_ports, (a, b, c))
        seams = (
            known_seam("ab", "a", "b"),
            Seam("bc", PortRef("b", "waist2"), PortRef("c", "waist"),
                 construction_method="plain seam",
                 construction_source="human-verified fixture",
                 prerequisites=("ab",)),
            Seam("ca", PortRef("c", "waist2"), PortRef("a", "waist2"),
                 construction_method="plain seam",
                 construction_source="human-verified fixture",
                 prerequisites=("bc",)),
        )
        assembly = assemble((a, b, c), seams)
        report = graph_report(assembly)
        plan = plan_sewing(assembly)

        self.assertEqual(report["beta"], 1)
        self.assertEqual(plan["verdict"], ANSWER)
        self.assertEqual(plan["partial_order"], [("ab", "bc"), ("bc", "ca")])
        self.assertEqual([row["access"] for row in plan["operations"]],
                         ["FLAT", "FLAT", "IN_THE_ROUND"])
        self.assertTrue(plan["beta_check"])

    def test_graph_and_port_invariants_reject_invalid_assemblies(self):
        top = piece("top", "top", "lower")
        skirt = piece("skirt", "skirt", "upper")
        seam = Seam("waist", PortRef("top", "waist"), PortRef("skirt", "waist"))
        with self.assertRaisesRegex(AssemblyInvariantError, "DUPLICATE_PIECE"):
            assemble((top, top))
        with self.assertRaisesRegex(AssemblyInvariantError, "PORT_ALREADY_JOINED"):
            assemble((top, skirt), (seam, seam.__class__(
                "second", seam.a, seam.b)))
        with self.assertRaisesRegex(AssemblyInvariantError, "CYCLIC_SEAM_ORDER"):
            assemble((top, skirt), (Seam(
                "waist", seam.a, seam.b, prerequisites=("waist",)),))

        with self.assertRaisesRegex(AssemblyInvariantError, "PORT_NOT_MESH_LOOP"):
            GarmentPiece(
                "bad", top.mesh,
                (Port("bad", (0, 1, 3), "waist"),),
            )

    def test_incompatible_stretch_ranges_are_not_silently_forced(self):
        rigid_big = piece("big", direction="lower", size=2.0, stretch=(1.0, 1.0))
        rigid_small = piece("small", direction="upper", size=1.0, stretch=(1.0, 1.0))
        seam = Seam("join", PortRef("big", "waist"), PortRef("small", "waist"))
        with self.assertRaisesRegex(AssemblyInvariantError, "INCOMPATIBLE_INTERFACES"):
            assemble((rigid_big, rigid_small), (seam,))


if __name__ == "__main__":
    unittest.main()
