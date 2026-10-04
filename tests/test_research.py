"""Research evidence must retain its identities and never be overwritten."""

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from reproduce_research import audit_registry, prepare_output  # noqa: E402


class ResearchEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        (self.root / "benchmarks").mkdir()
        (self.root / "benchmarks/result.json").write_bytes(b'{"value": 1}\n')
        (self.root / "report.md").write_text("Frozen evidence\n", encoding="utf-8")
        self.catalog = {
            "schema_version": 1,
            "groups": [{"id": "sample", "report": "report.md", "entrypoints": []}],
            "artifacts": [
                {
                    "path": "benchmarks/result.json",
                    "group": "sample",
                    "hash_mode": "lf",
                    "sha256": sha256(b'{"value": 1}\n').hexdigest(),
                    "size": 13,
                }
            ],
        }

    def test_portable_text_hash_and_byte_exact_archive(self):
        path = self.root / "benchmarks/result.json"
        path.write_bytes(b'{"value": 1}\r\n')
        self.assertEqual(audit_registry(self.root, self.catalog)["artifacts"], 1)
        catalog = deepcopy(self.catalog)
        catalog["artifacts"][0]["hash_mode"] = "bytes"
        with self.assertRaisesRegex(ValueError, "artifact changed"):
            audit_registry(self.root, catalog)

    def test_mutated_missing_and_uncatalogued_evidence_rejected(self):
        path = self.root / "benchmarks/result.json"
        path.write_bytes(b'{"value": 2}\n')
        with self.assertRaisesRegex(ValueError, "artifact changed"):
            audit_registry(self.root, self.catalog)
        path.unlink()
        with self.assertRaises(FileNotFoundError):
            audit_registry(self.root, self.catalog)
        path.write_bytes(b'{"value": 1}\n')
        (self.root / "benchmarks/extra.json").write_bytes(b"{}")
        with self.assertRaisesRegex(ValueError, "uncatalogued"):
            audit_registry(self.root, self.catalog)

    def test_duplicate_and_escaping_paths_rejected(self):
        catalog = deepcopy(self.catalog)
        catalog["artifacts"] *= 2
        with self.assertRaisesRegex(ValueError, "duplicate artifact"):
            audit_registry(self.root, catalog)
        catalog = deepcopy(self.catalog)
        catalog["artifacts"][0]["path"] = "../outside.json"
        with self.assertRaisesRegex(ValueError, "invalid repository path"):
            audit_registry(self.root, catalog)

    def test_output_preserves_evidence_and_existing_results(self):
        before = (self.root / "benchmarks/result.json").read_bytes()
        for name in ("benchmarks", "research/s4-s5", "src", ".git"):
            with self.assertRaisesRegex(ValueError, "frozen evidence"):
                prepare_output(self.root, self.root / name / "new-output")
        with self.assertRaisesRegex(ValueError, "frozen evidence"):
            prepare_output(self.root, self.root)
        output = prepare_output(self.root, self.root / ".task-artifacts/run")
        (output / "sentinel").write_bytes(b"keep")
        with self.assertRaises(FileExistsError):
            prepare_output(self.root, output)
        self.assertEqual((output / "sentinel").read_bytes(), b"keep")
        self.assertEqual((self.root / "benchmarks/result.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
