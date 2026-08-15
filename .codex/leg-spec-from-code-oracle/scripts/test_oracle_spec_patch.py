from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("oracle_spec_patch.py")


class OracleSpecPatchTests(unittest.TestCase):
    def test_patches_only_marked_region(self) -> None:
        original = (
            "# Spec\n\n"
            "Human decision: preserve me.\n\n"
            '<!-- oracle-evidence:start key="field-rows" -->\n'
            "old evidence\n"
            '<!-- oracle-evidence:end key="field-rows" -->\n\n'
            "Reviewer note: preserve me too.\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec = root / "spec.md"
            patch = root / "patch.json"
            report = root / "report.json"
            spec.write_text(original, encoding="utf-8", newline="\n")
            patch.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "expected_spec_sha256": hashlib.sha256(
                            original.encode("utf-8")
                        ).hexdigest(),
                        "evidence_fingerprint": "abc",
                        "patches": [{"key": "field-rows", "content": "new evidence"}],
                    }
                ),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--spec",
                    str(spec),
                    "--patch",
                    str(patch),
                    "--report",
                    str(report),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            updated = spec.read_text(encoding="utf-8")
            self.assertIn("Human decision: preserve me.", updated)
            self.assertIn("Reviewer note: preserve me too.", updated)
            self.assertIn("new evidence", updated)
            self.assertNotIn("old evidence", updated)
            self.assertEqual(json.loads(report.read_text())["patched_keys"], ["field-rows"])

    def test_rejects_stale_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec = root / "spec.md"
            patch = root / "patch.json"
            spec.write_text(
                '<!-- oracle-evidence:start key="x" -->\na\n'
                '<!-- oracle-evidence:end key="x" -->\n',
                encoding="utf-8",
            )
            patch.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "expected_spec_sha256": "0" * 64,
                        "patches": [{"key": "x", "content": "b"}],
                    }
                ),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "--spec", str(spec), "--patch", str(patch)],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("stale incremental update", completed.stderr)


if __name__ == "__main__":
    unittest.main()
