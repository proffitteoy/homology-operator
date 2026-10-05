import unittest
from importlib.metadata import version

import homology_operator


class PackageTests(unittest.TestCase):
    def test_installed_package_metadata_matches(self):
        self.assertEqual(version("homology-operator"), homology_operator.__version__)

    def test_new_results_report_installed_version(self):
        api = homology_operator
        window = api.ChainWindow(
            k=0,
            A=api.Matrix.zero(0, 1),
            D=api.Matrix.zero(1, 0),
            basis_previous=(),
            basis_current=("v",),
            basis_next=(),
            weights=(1,),
        )
        op = api.HomologyOperator(
            window, api.solve_projection(api.ProjectionProblem(window))
        )
        record = op.to_result()
        installed_version = version("homology-operator")
        self.assertEqual(record.provenance["backend_version"], installed_version)
        self.assertEqual(record.provenance["solver_version"], installed_version)
        restored = api.OperatorResult.from_json(record.to_json())
        self.assertEqual(restored.provenance, record.provenance)

    def test_public_exports_are_available(self):
        for name in homology_operator.__all__:
            with self.subTest(name=name):
                self.assertIsNotNone(getattr(homology_operator, name))


if __name__ == "__main__":
    unittest.main()
