import unittest
from fractions import Fraction

from homology_operator.algebra import Matrix
from homology_operator.chain import ChainWindow, InvalidInput


class ChainWindowTests(unittest.TestCase):
    def window(self, **changes):
        data = dict(
            k=1,
            A=Matrix.from_rows(((1, 1, 0),)),
            D=Matrix.from_rows(((1,), (1,), (0,))),
            basis_previous=("v",),
            basis_current=("e0", "e1", "e2"),
            basis_next=("f",),
            weights=(1, Fraction(3, 2), 2),
        )
        data.update(changes)
        return ChainWindow(**data)

    def test_shape_order_and_exact_weights(self):
        window = self.window()
        self.assertEqual((window.m, window.n, window.p), (1, 3, 1))
        self.assertEqual(window.basis_current, ("e0", "e1", "e2"))
        self.assertEqual(window.weights, (Fraction(1), Fraction(3, 2), Fraction(2)))
        self.assertEqual(window, ChainWindow.from_dict(window.to_dict()))

    def test_empty_spaces_and_h0(self):
        empty = ChainWindow(0, Matrix.zero(0, 0), Matrix.zero(0, 0), (), (), (), ())
        self.assertEqual(ChainWindow.from_dict(empty.to_dict()).A.ncols, 0)
        h0 = ChainWindow(
            0,
            Matrix.zero(0, 2),
            Matrix.from_rows(((1,), (1,))),
            (),
            ("v0", "v1"),
            ("edge",),
            (1, 1),
            "unit",
        )
        decoded = ChainWindow.from_dict(h0.to_dict())
        self.assertEqual((decoded.A.nrows, decoded.A.ncols), (0, 2))
        self.assertEqual(decoded.basis_current, ("v0", "v1"))

    def test_invalid_chain_and_dimensions(self):
        cases = (
            {"k": -1},
            {"k": True},
            {"D": Matrix.zero(2, 1)},
            {"D": Matrix.from_rows(((1,), (0,), (0,)))},
            {"basis_current": ("e0", "e0", "e2")},
            {"basis_previous": ()},
            {"basis_next": ("",)},
        )
        for change in cases:
            with self.subTest(change=change), self.assertRaises(InvalidInput):
                self.window(**change)

    def test_invalid_weights_and_arithmetic(self):
        for weights in (
            (1, 2),
            (1, 0, 2),
            (1, -1, 2),
            (1, True, 2),
            (1, 1.5, 2),
            (1, float("inf"), 2),
            (1, float("nan"), 2),
        ):
            with self.subTest(weights=weights), self.assertRaises(InvalidInput):
                self.window(weights=weights)
        floating = self.window(weights=(1, 1.5, 2), arithmetic="FloatingPoint")
        self.assertEqual(floating.weights, (1.0, 1.5, 2.0))
        self.assertEqual(floating, ChainWindow.from_dict(floating.to_dict()))
        for weights in ((1, 0, 2), (1, float("inf"), 2), (1, float("nan"), 2)):
            with self.assertRaises(InvalidInput):
                self.window(weights=weights, arithmetic="FloatingPoint")
        with self.assertRaises(InvalidInput):
            self.window(arithmetic="ExactInteger")

    def test_geometry_semantics_and_metadata_are_explicit(self):
        metadata = {"source": {"path": "mesh.json"}, "coordinates": [0, 1]}
        window = self.window(
            weight_semantics="euclidean_area", unit="m^2", source_metadata=metadata
        )
        metadata["source"]["path"] = "changed"
        self.assertEqual(window.source_metadata["source"]["path"], "mesh.json")
        with self.assertRaises(TypeError):
            window.source_metadata["source"]["path"] = "changed"
        self.assertEqual(window.to_dict()["source_metadata"]["coordinates"], [0, 1])
        for changes in (
            {"weight_semantics": "length"},
            {"unit": ""},
            {"source_metadata": {"nan": float("nan")}},
        ):
            with self.assertRaises(InvalidInput):
                self.window(**changes)

    def test_deserialization_revalidates_inputs(self):
        data = self.window().to_dict()
        data["D"]["rows"][1][0] = 0
        with self.assertRaises(InvalidInput):
            ChainWindow.from_dict(data)
        data = self.window().to_dict()
        data["weights"][0]["denominator"] = 0
        with self.assertRaises(InvalidInput):
            ChainWindow.from_dict(data)
        data = self.window().to_dict()
        data["A"]["rows"][0][0] = 2
        with self.assertRaises(InvalidInput):
            ChainWindow.from_dict(data)


if __name__ == "__main__":
    unittest.main()
