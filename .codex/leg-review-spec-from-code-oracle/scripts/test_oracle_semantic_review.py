from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path

import oracle_semantic_review as review


FINGERPRINT = "a" * 64


class OracleSemanticReviewTests(unittest.TestCase):
    def make_package(self, root: Path) -> Path:
        repo = root / "repo"
        feature = repo / "evidence" / "features" / "demo-feature"
        feature.mkdir(parents=True)
        (repo / "project.yaml").write_text(
            "schema_version: 1\nobjective_type: legacy_modernization\n", encoding="utf-8"
        )
        master = feature / "demo1-demo-specification.md"
        master.write_text(
            f"""---
artifact_kind: legacy_evidence_specification
module_id: DEMO1
module_evidence_id: MOD-DEMO1
evidence_fingerprint: {FINGERPRINT}
operation_details: demo1-operation-details.md
decoded_source: demo1-decoded-source.md
database_reference: demo1-database-reference.md
---

# Demo - Legacy Evidence Specification

![demo](shot.png)

<!-- oracle-evidence:start key=\"missing-sources\" -->
| Subject | Gap kind / status |
| --- | --- |
| CALLER | runtime_context / open |
<!-- oracle-evidence:end key=\"missing-sources\" -->

<!-- oracle-evidence:start key=\"technical-notes\" -->
| Source-supported prior anchor | Current support |
| --- | --- |
| DEMO | Current evidence |
<!-- oracle-evidence:end key=\"technical-notes\" -->
""",
            encoding="utf-8",
        )
        common = f"""artifact_kind: legacy_evidence_reference
module_id: DEMO1
module_evidence_id: MOD-DEMO1
evidence_fingerprint: {FINGERPRINT}
parent_specification: {master.name}
"""
        (feature / "demo1-operation-details.md").write_text(
            f"---\n{common}reference_kind: operation_details\n---\n\n"
            "~~~json\n"
            + json.dumps(
                {
                    "path_id": "PATH-DEMO1-QUERY-1",
                    "operation": "query",
                    "entry_point": {"symbol": "DEMO.PRE-QUERY"},
                    "unresolved_calls": ["MISSING_CALL"],
                    "transaction": {"boundary": "unknown"},
                },
                indent=2,
            )
            + "\n~~~\n",
            encoding="utf-8",
        )
        (feature / "demo1-decoded-source.md").write_text(
            f"---\n{common}reference_kind: decoded_source\n---\n\n"
            + f"Decoded source SHA-256: `{'b' * 64}`\n",
            encoding="utf-8",
        )
        (feature / "demo1-database-reference.md").write_text(
            f"---\n{common}reference_kind: database_reference\n---\n\n"
            "~~~json\n"
            + json.dumps({"name": "DEMO_TABLE", "type": "table"}, indent=2)
            + "\n~~~\n",
            encoding="utf-8",
        )
        (feature / "shot.png").write_bytes(b"not-a-real-image")
        return master

    def test_prepare_scaffold_and_validate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            master = self.make_package(Path(temporary))
            context = review.resolve_package(master)
            self.assertEqual(context["metrics"]["operation_paths"], 1)
            self.assertEqual(context["metrics"]["decoded_units"], 1)
            self.assertEqual(context["metrics"]["database_objects"], 1)
            self.assertEqual(context["metrics"]["screenshots"], 1)
            self.assertTrue(context["expected_review_path"].endswith("demo1-semantic-review.md"))

            context_path = Path(temporary) / "context.json"
            review.write_json(context_path, context)
            output = Path(context["expected_review_path"])
            review.command_scaffold(argparse.Namespace(context=str(context_path), output=str(output)))
            result = review.validate_review(master, output, context_path)
            self.assertEqual(result["status"], "pass", result["errors"])
            self.assertTrue(result["extraction_unchanged"])

    def test_validation_detects_changed_extraction_child(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            master = self.make_package(Path(temporary))
            context = review.resolve_package(master)
            context_path = Path(temporary) / "context.json"
            review.write_json(context_path, context)
            output = Path(context["expected_review_path"])
            review.command_scaffold(argparse.Namespace(context=str(context_path), output=str(output)))
            operation_child = master.parent / "demo1-operation-details.md"
            operation_child.write_text(operation_child.read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8")
            result = review.validate_review(master, output, context_path)
            self.assertEqual(result["status"], "fail")
            self.assertTrue(any("changed" in error.lower() for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
