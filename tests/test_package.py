import unittest
from importlib.metadata import version

import homology_operator


class PackageTests(unittest.TestCase):
    def test_installed_package_metadata_matches(self):
        self.assertEqual(version("homology-operator"), homology_operator.__version__)

    def test_public_exports_are_available(self):
        for name in homology_operator.__all__:
            with self.subTest(name=name):
                self.assertIsNotNone(getattr(homology_operator, name))


if __name__ == "__main__":
    unittest.main()
