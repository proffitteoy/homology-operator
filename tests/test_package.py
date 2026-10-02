import unittest
from importlib.metadata import version

import homology_operator


class PackageTests(unittest.TestCase):
    def test_installed_package_metadata_matches(self):
        self.assertEqual(version("homology-operator"), homology_operator.__version__)


if __name__ == "__main__":
    unittest.main()
