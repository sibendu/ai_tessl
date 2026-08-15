import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import oracle_spec_guard as guard  # noqa: E402


MODULE = "GLASCT01"
FP_A = "a" * 64
FP_B = "b" * 64
GAP_ID = "GAP-GLASCT01-SOURCE_MISSING-GLASCT01L"


def coverage_records(*, zero_forms=False, unresolved_gap=None):
    block_total = 0 if zero_forms else 1
    item_total = 0 if zero_forms else 1
    rows = [
        metric("COV-SOURCE", "source_classification", 2, 2),
        metric("COV-BLOCK", "block_crud", block_total, block_total),
        metric("COV-ITEM", "item_crud", item_total, item_total),
        metric("COV-PATH", "operation_paths", 1, 1),
        metric("COV-DDL", "database_references", 1, 1),
        metric("COV-AUDIT", "independent_audit", 1, 1),
        metric("COV-SPEC", "specification_coverage", 1, 1),
    ]
    if unresolved_gap:
        rows.append(
            {
                "metric_id": "COV-CALL",
                "dimension": "call_reachability",
                "denominator": 1,
                "numerator": 0,
                "exclusions": 0,
                "unresolved_count": 1,
                "record_ids": [unresolved_gap],
                "status": "pass_with_assumptions",
            }
        )
    return rows


def metric(metric_id, dimension, denominator, numerator):
    return {
        "metric_id": metric_id,
        "dimension": dimension,
        "denominator": denominator,
        "numerator": numerator,
        "exclusions": 0,
        "unresolved_count": denominator - numerator,
        "record_ids": [],
        "status": "pass" if denominator == numerator else "pass_with_assumptions",
    }


def gap(status="open"):
    value = {
        "gap_id": GAP_ID,
        "gap_kind": "source_missing",
        "subject": "GLASCT01L.PLD",
        "expected_artifact_or_behavior": "Readable module library",
        "status": status,
        "first_seen_run_id": "run-1",
        "last_changed_run_id": "run-2" if status == "resolved" else "run-1",
        "why_expected": "Attached binary library",
        "affected_operations": ["update", "delete"],
        "affected_fact_ids": [],
        "affected_path_ids": [],
        "classification": "source_gap",
        "poc_impact": "bounded_by_proposed_assumption",
        "production_impact": "blocking",
        "assumption_or_decision_id": "ASM-GLASCT01-SOURCE_MISSING-GLASCT01L",
        "poc_assumption": {
            "assumption_id": "ASM-GLASCT01-SOURCE_MISSING-GLASCT01L",
            "status": "proposed_for_poc_validation",
            "bounded_scope": {"operations": ["update", "delete"], "scope_kind": "operation_paths"},
            "assumed_target_behavior": "Fail closed when unavailable behavior could make a write unsafe.",
            "approval_state": "not_business_validated",
        },
        "resolution_evidence": [],
        "history": [],
    }
    if status == "resolved":
        value["resolution_evidence"] = [{"source_id": "SRC-GLASCT01-PLD"}]
        value["history"] = [{"from": "open", "to": "resolved", "run_id": "run-2"}]
    return value


def evidence(fingerprint=FP_A, *, gaps=None, zero_forms=False, delta=None):
    gaps = [] if gaps is None else gaps
    artifacts = {
        "source_inventory": {
            "records": [
                {
                    "source_id": "SRC-GLASCT01-FORM",
                    "source_role": "forms_xml",
                    "availability": "readable",
                    "parse_status": "parsed",
                },
                {
                    "source_id": "SRC-GLASCT01-DDL",
                    "source_role": "ddl",
                    "availability": "readable",
                    "parse_status": "parsed",
                },
            ]
        },
        "normalized_evidence": {
            "records": []
            if zero_forms
            else [
                {"fact_id": "FACT-GLASCT01-BLOCK_CRUD-CTT", "fact_kind": "block_crud"},
                {"fact_id": "FACT-GLASCT01-ITEM_CRUD-TITLE", "fact_kind": "item_crud"},
                {"fact_id": "FACT-GLASCT01-DATABASE_OBJECT-CTT", "fact_kind": "database_object"},
            ]
        },
        "behavior_ledger": {"records": [{"path_id": "PATH-GLASCT01-UPDATE-CTT"}]},
        "coverage": {
            "records": coverage_records(
                zero_forms=zero_forms,
                unresolved_gap=GAP_ID if gaps and gaps[0]["status"] != "resolved" else None,
            )
        },
        "gaps": {"records": gaps},
    }
    if delta is not None:
        artifacts["source_delta"] = delta
    return {
        "schema_version": "1.0",
        "extractor_version": "test-1",
        "module_id": MODULE,
        "run_id": "run-2" if fingerprint == FP_B else "run-1",
        "generated_at": "2026-07-22T00:00:00Z",
        "input_manifest_sha256": fingerprint,
        "artifacts": artifacts,
    }


def specification(fingerprint=FP_A, *, gap_ids=(), body=""):
    visible_gaps = "\n".join(f"| {gap_id} | source_missing | open |" for gap_id in gap_ids)
    return f"""---
module_id: "{MODULE}"
evidence_fingerprint: "{fingerprint}"
---

# Maintain Standard Contract

## 1. Document Control

Evidence-backed draft.

## 6. Functional Requirements

{body or 'The page shall preserve the evidenced update behavior.'}

## 22. Appendices

### Appendix I. Extraction Coverage And Missing Source Register

#### Coverage Summary

| Coverage dimension | Total | Classified/resolved | Open/unknown |
| --- | --- | --- | --- |
| Source | 2 | 2 | 0 |

#### Missing Source And Evidence Gaps

| Gap ID | Gap type | Lifecycle status |
| --- | --- | --- |
{visible_gaps or '| None | None | resolved |'}

### Appendix J. Incremental Extraction History

| Run ID | Evidence fingerprint | Validation result |
| --- | --- | --- |
| run-1 | {fingerprint} | pending |
"""


class OracleSpecGuardTests(unittest.TestCase):
    def write_fixture(self, root, name, value):
        path = Path(root) / name
        if isinstance(value, str):
            path.write_text(value, encoding="utf-8")
        else:
            path.write_text(json.dumps(value, indent=2), encoding="utf-8")
        return path

    def test_precisely_registered_open_gap_does_not_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            evidence_path = self.write_fixture(temp, "evidence.json", evidence(gaps=[gap()]))
            spec_path = self.write_fixture(temp, "spec.md", specification(gap_ids=[GAP_ID]))
            result = guard.run_guard(evidence_path, spec_path)
            self.assertEqual([], result["errors"])
            self.assertEqual("pass_with_registered_gaps", result["validation_status"])
            call_gate = next(
                row for row in result["readiness_gate_results"] if row["gate_id"] == "GATE-CALL-REACHABILITY"
            )
            self.assertEqual("pass_with_registered_gaps", call_gate["status"])

    def test_ready_poc_requires_accepted_bounded_assumption_trace(self):
        with tempfile.TemporaryDirectory() as temp:
            evidence_path = self.write_fixture(temp, "evidence.json", evidence(gaps=[gap()]))
            spec_text = specification(gap_ids=[GAP_ID]).replace(
                f'evidence_fingerprint: "{FP_A}"',
                f'evidence_fingerprint: "{FP_A}"\npoc_forward_engineering_readiness: "ready-with-explicit-assumptions"',
            )
            spec_path = self.write_fixture(temp, "spec.md", spec_text)
            result = guard.run_guard(evidence_path, spec_path)
            self.assertIn("POC_ASSUMPTION_UNGOVERNED", {row["code"] for row in result["errors"]})

    def test_accepts_compiler_aggregate_metadata_shape(self):
        with tempfile.TemporaryDirectory() as temp:
            model = evidence()
            model["schema_version"] = "oracle-module-evidence/1.0"
            model["extractor"] = {"version": model.pop("extractor_version"), "schema": "1.0"}
            model["modules"] = [{"module_id": model.pop("module_id")}]
            model["run"] = {
                "run_id": model.pop("run_id"),
                "generated_at": model.pop("generated_at"),
                "input_manifest_sha256": model.pop("input_manifest_sha256"),
                "evidence_sha256": FP_B,
            }
            evidence_path = self.write_fixture(temp, "evidence-model.json", model)
            spec_path = self.write_fixture(temp, "spec.md", specification(FP_B))
            result = guard.run_guard(evidence_path, spec_path)
            metadata_codes = {
                row["code"]
                for row in result["errors"]
                if row["code"].startswith("EVIDENCE_METADATA")
                or row["code"].startswith("EVIDENCE_SCHEMA")
                or row["code"].startswith("EVIDENCE_MODULE")
                or row["code"].startswith("EVIDENCE_FINGERPRINT")
            }
            self.assertEqual(set(), metadata_codes)
            self.assertEqual(FP_B, result["evidence_fingerprint"])

    def test_gap_closure_preserves_stable_id_and_history(self):
        with tempfile.TemporaryDirectory() as temp:
            previous_path = self.write_fixture(temp, "previous.json", evidence(FP_A, gaps=[gap("open")]))
            current_path = self.write_fixture(temp, "current.json", evidence(FP_B, gaps=[gap("resolved")]))
            spec_path = self.write_fixture(temp, "spec.md", specification(FP_B, gap_ids=[GAP_ID]))
            result = guard.run_guard(current_path, spec_path, previous_evidence=previous_path)
            self.assertFalse(any(row["code"].startswith("GAP_") for row in result["errors"]))
            self.assertEqual(1, result["gap_summary"]["resolved"])

    def test_lost_gap_history_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            previous_path = self.write_fixture(temp, "previous.json", evidence(FP_A, gaps=[gap("open")]))
            current_path = self.write_fixture(temp, "current.json", evidence(FP_A, gaps=[]))
            spec_path = self.write_fixture(temp, "spec.md", specification(FP_A, gap_ids=[GAP_ID]))
            result = guard.run_guard(current_path, spec_path, previous_evidence=previous_path)
            self.assertIn("GAP_HISTORY_LOST", {row["code"] for row in result["errors"]})

    def test_stale_fingerprint_uses_delta_section_impact(self):
        delta = {
            "records": [
                {
                    "source_key": "form/glasct01_fmb.xml",
                    "change": "changed",
                    "affected_fact_ids": ["FACT-GLASCT01-ITEM_CRUD-TITLE"],
                    "affected_path_ids": [],
                    "affected_gap_ids": [],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as temp:
            evidence_path = self.write_fixture(temp, "evidence.json", evidence(FP_B, delta=delta))
            spec_path = self.write_fixture(temp, "spec.md", specification(FP_A))
            result = guard.run_guard(evidence_path, spec_path)
            self.assertIn("SPEC_STALE_FINGERPRINT", {row["code"] for row in result["errors"]})
            stale = {row["section_key"] for row in result["stale_sections"]}
            self.assertTrue({"3", "6", "8", "Appendix B", "Appendix J"}.issubset(stale))
            self.assertIn("1", result["preserved_sections"])

    def test_missing_appendices_and_unsupported_claims_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            weak = evidence(gaps=[gap()])
            weak["artifacts"]["coverage"]["records"] = []
            evidence_path = self.write_fixture(temp, "evidence.json", weak)
            spec_path = self.write_fixture(
                temp,
                "spec.md",
                f'---\nmodule_id: "{MODULE}"\nevidence_fingerprint: "{FP_A}"\n---\n\n## 6. Functional Requirements\n\nOnly the header is editable.\n',
            )
            result = guard.run_guard(evidence_path, spec_path)
            codes = {row["code"] for row in result["errors"]}
            self.assertIn("APPENDIX_I_MISSING", codes)
            self.assertIn("APPENDIX_J_MISSING", codes)
            self.assertIn("UNSUPPORTED_LIMITING_CLAIM", codes)

    def test_exact_on_delete_ddl_clause_is_not_an_unsupported_limiting_claim(self):
        with tempfile.TemporaryDirectory() as temp:
            weak = evidence()
            weak["artifacts"]["coverage"]["records"] = []
            evidence_path = self.write_fixture(temp, "evidence.json", weak)
            spec_path = self.write_fixture(
                temp,
                "spec.md",
                specification(body="GLA_SCP_CTT_FK1 references GLA_CONTRACTS; ON DELETE CASCADE."),
            )
            result = guard.run_guard(evidence_path, spec_path)
            self.assertNotIn(
                "UNSUPPORTED_LIMITING_CLAIM",
                {row["code"] for row in result["errors"]},
            )

    def test_generated_specification_requires_complete_template_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            evidence_path = self.write_fixture(temp, "evidence.json", evidence())
            incomplete = specification().replace(
                f'module_id: "{MODULE}"',
                f'module_id: "{MODULE}"\nartifact_kind: "legacy_evidence_specification"\nmodule_evidence_id: "MOD-{MODULE}"',
            )
            spec_path = self.write_fixture(temp, "spec.md", incomplete)
            result = guard.run_guard(evidence_path, spec_path)
            codes = {row["code"] for row in result["errors"]}
            self.assertIn("SPECIFICATION_CONTRACT_INCOMPLETE", codes)
            self.assertIn("SPECIFICATION_MARKER_CONTRACT_INCOMPLETE", codes)

    def test_full_inventory_and_zero_count_parser_regression_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            evidence_path = self.write_fixture(temp, "evidence.json", evidence(zero_forms=True))
            spec_path = self.write_fixture(
                temp,
                "spec.md",
                specification(body="### Full Legacy Item Inventory\n\nThe full inventory is below."),
            )
            result = guard.run_guard(evidence_path, spec_path)
            codes = {row["code"] for row in result["errors"]}
            self.assertIn("ZERO_COUNT_FORMS_BLOCKS", codes)
            self.assertIn("ZERO_COUNT_FORMS_ITEMS", codes)
            self.assertIn("MISLEADING_FULL_INVENTORY", codes)

    def test_full_inventory_row_count_must_reconcile(self):
        with tempfile.TemporaryDirectory() as temp:
            evidence_path = self.write_fixture(temp, "evidence.json", evidence())
            spec_text = specification().replace(
                "## 22. Appendices",
                "### Appendix B. Full Legacy Item Inventory\n\n"
                "| Evidence ID | Block.item |\n"
                "| --- | --- |\n"
                "| FACT-1 | CTT.TITLE |\n"
                "| FACT-2 | CTT.REMARK |\n\n"
                "## 22. Appendices",
            )
            spec_path = self.write_fixture(temp, "spec.md", spec_text)
            result = guard.run_guard(evidence_path, spec_path)
            self.assertIn("FULL_INVENTORY_ROW_MISMATCH", {row["code"] for row in result["errors"]})

    def test_tabbed_visible_items_require_a_tab_table_and_membership(self):
        with tempfile.TemporaryDirectory() as temp:
            model = evidence()
            model["artifacts"]["normalized_evidence"]["records"].extend([
                {"fact_id": "FACT-GLASCT01-TAB-DETAIL", "fact_kind": "tab", "subject": {"key": "GLASCT01/DETAIL"}, "value": {"id": "DETAIL", "label": "Detail"}},
                {"fact_id": "FACT-GLASCT01-PLACEMENT-TITLE", "fact_kind": "item_visual_placement", "value": {"block": "CTT", "item": "TITLE", "tab_page": "DETAIL", "tab_label": "Detail", "region_kind": "tab_page", "presentation_shape": "field", "visible": True}},
            ])
            evidence_path = self.write_fixture(temp, "evidence.json", model)
            complete = specification().replace(
                "## 22. Appendices",
                "## 8. Field and Control Specification\n\n### Tab: Detail\n\n| Legacy mapping | Description |\n| --- | --- |\n| `CTT.TITLE` | Contract title |\n\n## 22. Appendices",
            )
            complete_path = self.write_fixture(temp, "complete.md", complete)
            self.assertFalse(any(row["code"].startswith("VISUAL_REGION") for row in guard.run_guard(evidence_path, complete_path)["errors"]))
            incomplete_path = self.write_fixture(temp, "incomplete.md", specification())
            codes = {row["code"] for row in guard.run_guard(evidence_path, incomplete_path)["errors"]}
            self.assertIn("FIELD_SPECIFICATION_SECTION_MISSING", codes)

    def test_optional_markers_must_still_be_balanced_when_present(self):
        with tempfile.TemporaryDirectory() as temp:
            evidence_path = self.write_fixture(temp, "evidence.json", evidence())
            spec_text = specification().replace(
                'evidence_fingerprint: "',
                'extraction_mode: "initial"\nevidence_fingerprint: "',
            ).replace(
                "# Maintain Standard Contract",
                "# Maintain Standard Contract\n\n"
                "<!-- Required keys when applicable: extraction-coverage, missing-sources, incremental-history. -->\n"
                '<!-- oracle-evidence:start key="extraction-coverage" -->\n'
                "content\n",
            )
            spec_path = self.write_fixture(temp, "spec.md", spec_text)
            result = guard.run_guard(evidence_path, spec_path)
            codes = {row["code"] for row in result["errors"]}
            self.assertIn("EVIDENCE_MARKER_UNBALANCED", codes)
            self.assertNotIn("EVIDENCE_MARKER_MISSING", codes)

    def test_broken_local_evidence_link_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            evidence_path = self.write_fixture(temp, "evidence.json", evidence())
            spec_path = self.write_fixture(
                temp,
                "spec.md",
                specification().replace(
                    "# Maintain Standard Contract",
                    "# Maintain Standard Contract\n\n[Evidence](./missing/evidence-model.json)",
                ),
            )
            result = guard.run_guard(evidence_path, spec_path)
            self.assertIn("SPEC_LOCAL_LINK_BROKEN", {row["code"] for row in result["errors"]})

    def test_cli_writes_output_and_returns_zero_for_registered_gap(self):
        with tempfile.TemporaryDirectory() as temp:
            evidence_path = self.write_fixture(temp, "evidence.json", evidence(gaps=[gap()]))
            spec_path = self.write_fixture(temp, "spec.md", specification(gap_ids=[GAP_ID]))
            output_path = Path(temp) / "result.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "oracle_spec_guard.py"),
                    "--evidence",
                    str(evidence_path),
                    "--spec",
                    str(spec_path),
                    "--output",
                    str(output_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
            self.assertTrue(output_path.is_file())
            self.assertEqual("pass_with_registered_gaps", json.loads(completed.stdout)["validation_status"])


if __name__ == "__main__":
    unittest.main()
