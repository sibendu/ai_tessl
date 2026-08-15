#!/usr/bin/env python3
"""Regression tests for oracle_module_evidence.py.

The synthetic tests are self-contained.  The GLASCT01 golden test runs when the
repository evidence bundle is present and otherwise reports a normal unittest
skip, so the suite is portable outside this workspace.
"""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

import oracle_module_evidence as extractor
import oracle_spec_guard as specification_guard


SYNTHETIC_XML = """<?xml version="1.0" encoding="UTF-8"?>
<f:Module xmlns:f="http://xmlns.oracle.com/Forms">
  <f:FormModule f:Name="demo" f:Title="Demo" f:FirstNavigationBlockName="HDR">
    <f:AttachedLibrary f:Name="DEMOL" f:LibraryLocation="demol" f:LibrarySource="File" />
    <f:Window f:Name="DEMO_WINDOW" f:Title="Demo Window" f:PrimaryCanvas="MAIN" />
    <f:Canvas f:Name="MAIN" f:CanvasType="Content" f:Visible="true">
      <f:TabPage f:Name="DETAIL" f:Label="Detail" f:Visible="true" f:Enabled="true" />
    </f:Canvas>
    <f:Block f:Name="HDR" f:DatabaseBlock="true" f:QueryDataSourceName="DEMO_TABLE"
             f:DMLDataName="DEMO_TABLE" f:QueryAllowed="true" f:InsertAllowed="true"
             f:UpdateAllowed="true" f:DeleteAllowed="true">
      <f:Item f:Name="ID" f:DatabaseItem="true" f:ColumnName="ID" f:CanvasName="MAIN"
              f:QueryAllowed="true" f:InsertAllowed="true" f:UpdateAllowed="false" f:Required="true" />
      <f:Item f:Name="TITLE" f:DatabaseItem="true" f:ColumnName="TITLE" f:TabPageName="DETAIL"
              f:QueryAllowed="true" f:InsertAllowed="true" f:UpdateAllowed="true" />
      <f:Trigger f:Name="PRE-UPDATE" f:TriggerText="BEGIN&amp;#10; CHECK_EXTERNAL();&amp;#10;END;" />
    </f:Block>
  </f:FormModule>
</f:Module>
"""

DEMO_DDL = """
CREATE TABLE DEMO_TABLE (ID NUMBER, TITLE VARCHAR2(30));
ALTER TABLE DEMO_TABLE MODIFY (ID NOT NULL ENABLE);
COMMENT ON COLUMN DEMO_TABLE.ID IS 'Stable demo identifier';
CREATE TABLE DEPENDENCY_TABLE (ID NUMBER, DEMO_ID NUMBER,
  CONSTRAINT DEP_FK FOREIGN KEY (DEMO_ID) REFERENCES DEMO_TABLE(ID) ON DELETE CASCADE);
"""

DEMO_PLD = """
PROCEDURE CHECK_EXTERNAL IS
  L_COUNT NUMBER;
BEGIN
  SELECT COUNT(*) INTO L_COUNT FROM DEPENDENCY_TABLE;
  IF L_COUNT &gt; 0 THEN
    qms$forms_errors.push(QMS$FORMS_ERRORS.MSGGETTEXT(5,
      'Cannot delete &lt;p1&gt; while dependent &lt;p2&gt; exists', 'Demo', 'Dependency'), 'E', 'OFG', 5);
    qms$forms_errors.raise_failure;
  END IF;
END;
"""


def compile_model(root: Path, previous=None, supplemental: bool = False):
    evidence = extractor.build_evidence(root, "DEMO", previous, supplemental=supplemental)
    return extractor.build_contract_artifacts(evidence, previous)


class OracleModuleEvidenceTests(unittest.TestCase):
    def make_full_bundle(self, root: Path) -> None:
        (root / "demo_fmb.xml").write_text(SYNTHETIC_XML, encoding="utf-8")
        (root / "demo.sql").write_text(DEMO_DDL, encoding="utf-8")
        (root / "demol.pll").write_bytes(b"binary library placeholder")

    def test_fresh_run_auto_discovers_adjacent_previous_spec_as_comparison_oracle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            features = Path(temporary) / "features"
            features.mkdir()
            output = features / "glasct01-maintain-standard-contract-specification.md"
            previous = output.parent / f"previous_{output.name}"
            previous.write_text("# Historical oracle\n", encoding="utf-8")
            v0 = output.with_name(f"{output.stem}_v0.md")
            v1 = output.with_name(f"{output.stem}_v1.md")
            v0.write_text("# Historical v0 oracle\n", encoding="utf-8")
            v1.write_text("# Historical v1 oracle\n", encoding="utf-8")

            self.assertEqual(
                previous,
                extractor.resolve_comparison_spec(output, None, None, "fresh", False),
            )
            self.assertIsNone(
                extractor.resolve_comparison_spec(output, None, None, "fresh", True)
            )
            self.assertIsNone(
                extractor.resolve_comparison_spec(output, None, None, "refresh", False)
            )
            self.assertEqual(
                [previous, v0, v1],
                extractor.resolve_comparison_specs(output, None, None, "fresh", False),
            )

            nested = output.parent / "standard-contract" / output.name
            nested.parent.mkdir()
            output.write_text("# Historical current oracle\n", encoding="utf-8")
            self.assertEqual(
                [previous, output, v0, v1],
                extractor.resolve_comparison_specs(nested, None, None, "fresh", False),
            )

    def test_partial_bundle_is_best_effort_and_namespaced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_full_bundle(root)
            model = compile_model(root)
            module = model["modules"][0]
            self.assertEqual(1, len(module["blocks"]))
            self.assertEqual(2, sum(len(block["items"]) for block in module["blocks"]))
            trigger = module["triggers"][0]
            self.assertIn("\n", trigger["code"])
            self.assertNotIn("&#10;", trigger["code"])
            gaps = model["artifacts"]["gaps"]["records"]
            self.assertTrue(any(gap["gap_kind"] == "binary_only" and gap["subject"] == "DEMOL" for gap in gaps))
            table = next(obj for obj in model["ddl"]["catalog"] if obj["type"] == "table" and obj["name"] == "DEMO_TABLE")
            self.assertFalse(next(column for column in table["columns"] if column["name"] == "ID")["nullable"])
            self.assertEqual("Stable demo identifier", next(column for column in table["columns"] if column["name"] == "ID")["comment"])
            implicit = [path for path in model["artifacts"]["behavior_ledger"]["records"] if path["entry_point"]["scope"] == "forms_implicit_dml"]
            self.assertEqual({"insert", "update", "delete"}, {path["operation"] for path in implicit})
            self.assertTrue(all(path["database_writes"] == ["DEMO_TABLE"] for path in implicit))
            placements = model["artifacts"]["normalized_evidence"]["records"]
            title_placement = next(
                fact for fact in placements
                if fact["fact_kind"] == "item_visual_placement" and fact["subject"]["key"].endswith("/TITLE")
            )
            self.assertEqual("tab_page", title_placement["value"]["region_kind"])
            self.assertEqual("Detail", title_placement["value"]["tab_label"])
            coverage = model["artifacts"]["coverage"]["records"]
            self.assertEqual(2, next(row for row in coverage if row["dimension"] == "visible_item_region_placement")["denominator"])

    def test_markdown_cli_writes_linked_lossless_package(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            root.mkdir()
            self.make_full_bundle(root)
            package_dir = Path(temporary) / "evidence" / "features" / "demo"
            master = package_dir / "demo-specification.md"
            validation_evidence = Path(temporary) / "validation" / "evidence-model.json"
            result = extractor.main(
                [
                    str(root),
                    "--module",
                    "DEMO",
                    "--markdown-output",
                    str(master),
                    "--validation-evidence-output",
                    str(validation_evidence),
                    "--extraction-mode",
                    "fresh",
                    "--self-check",
                ]
            )
            self.assertEqual(0, result)
            expected = {
                "demo-specification.md",
                "demo-operation-details.md",
                "demo-decoded-source.md",
                "demo-database-reference.md",
            }
            self.assertEqual(expected, {path.name for path in package_dir.glob("*.md")})
            guard_result = specification_guard.run_guard(validation_evidence, master)
            self.assertEqual([], guard_result["errors"])
            repeated_payload = "X" * 600
            end_marker = '<!-- oracle-evidence:end key="business-rules" -->'
            broken = master.read_text(encoding="utf-8").replace(
                end_marker,
                f"| update | condition A | 1 | {repeated_payload} | source |\n"
                f"| update | condition B | 1 | {repeated_payload} | source |\n"
                + end_marker,
                1,
            )
            master.write_text(broken, encoding="utf-8")
            repeated_result = specification_guard.run_guard(validation_evidence, master)
            self.assertIn("SPEC_PATH_MESSAGE_SET_REPEATED", {issue["code"] for issue in repeated_result["errors"]})

    def test_all_plausible_screenshots_are_associated_and_linked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_full_bundle(root)
            ui = root / "ui"
            ui.mkdir()
            (ui / "DEMO overview.png").write_bytes(b"png")
            (ui / "Demo.jpg").write_bytes(b"jpg")
            (ui / "unrelated-screen.png").write_bytes(b"png")
            model = compile_model(root)
            screenshots = model["modules"][0]["runtime_screenshots"]
            self.assertEqual(
                {"ui/DEMO overview.png", "ui/Demo.jpg"},
                {record["path"] for record in screenshots},
            )
            self.assertTrue(all(record["association_score"] >= 0.55 for record in screenshots))
            fingerprint = extractor.semantic_state_hash(model)
            model["run"]["state_sha256"] = fingerprint
            model["run"]["evidence_sha256"] = fingerprint
            model["self_check"] = {"status": "passed", "errors": []}
            output = root / "evidence" / "demo-specification.md"
            specification = extractor.render_complete_markdown_specification(
                model,
                source_root=root,
                output_path=output,
            )
            self.assertIn("DEMO%20overview.png", specification)
            self.assertIn("Demo.jpg", specification)
            self.assertNotIn("![DEMO legacy screenshot](../ui/unrelated-screen.png)", specification)

    def test_required_audit_columns_without_population_owner_create_explicit_gap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "demo_fmb.xml").write_text(SYNTHETIC_XML, encoding="utf-8")
            (root / "demo.sql").write_text(
                DEMO_DDL.replace(
                    "ID NUMBER, TITLE VARCHAR2(30)",
                    "ID NUMBER, TITLE VARCHAR2(30), CREATED_BY VARCHAR2(30) NOT NULL, "
                    "CREATION_DATE DATE NOT NULL",
                ),
                encoding="utf-8",
            )
            model = compile_model(root)
            gap = next(
                gap
                for gap in model["artifacts"]["gaps"]["records"]
                if gap["subject"] == "Audit column population for DEMO_TABLE"
            )
            self.assertEqual("runtime_only", gap["gap_kind"])
            self.assertIn("CREATED_BY", gap["expected_artifact_or_behavior"])
            fingerprint = extractor.semantic_state_hash(model)
            model["run"]["state_sha256"] = fingerprint
            model["run"]["evidence_sha256"] = fingerprint
            specification = extractor.render_complete_markdown_specification(model)
            self.assertIn("Audit Column Population Evidence", specification)
            self.assertIn("Audit column population for DEMO_TABLE", specification)
            self.assertIn("no DDL default or explicit decoded assignment", specification)

    def test_button_navigation_becomes_a_reachable_custom_action_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            augmented_xml = SYNTHETIC_XML.replace(
                "    </f:Block>",
                """      <f:Item f:Name="OPEN_DETAILS_BUTTON" f:ItemType="Push Button" f:CanvasName="MAIN"
              f:DatabaseItem="false" f:Visible="true">
        <f:Trigger f:Name="WHEN-BUTTON-PRESSED"
                   f:TriggerText="BEGIN&amp;#10; OPEN_DETAILS;&amp;#10;END;" />
      </f:Item>
    </f:Block>""",
            ).replace(
                "  </f:FormModule>",
                """    <f:ProgramUnit f:Name="OPEN_DETAILS" f:ProgramUnitType="Procedure"
                   f:ProgramUnitText="PROCEDURE OPEN_DETAILS IS&amp;#10;BEGIN&amp;#10; COPY(:HDR.ID, 'PARAMETER.P_CTT_ID');&amp;#10; OPEN_FORM('detail01');&amp;#10;END;" />
  </f:FormModule>""",
            )
            (root / "demo_fmb.xml").write_text(augmented_xml, encoding="utf-8")
            (root / "demo.sql").write_text(DEMO_DDL, encoding="utf-8")
            model = compile_model(root)
            custom_path = next(
                path
                for path in model["artifacts"]["behavior_ledger"]["records"]
                if path["operation"] == "custom_action"
                and path["entry_point"]["symbol"] == "HDR.OPEN_DETAILS_BUTTON.WHEN-BUTTON-PRESSED"
            )
            self.assertIn("OPEN_DETAILS", {edge["to"] for edge in custom_path["call_chain"]})
            self.assertTrue(
                any(
                    effect.get("mechanism") == "OPEN_FORM" and effect.get("object") == "detail01"
                    for effect in custom_path["side_effects"]
                )
            )
            fingerprint = extractor.semantic_state_hash(model)
            model["run"]["state_sha256"] = fingerprint
            model["run"]["evidence_sha256"] = fingerprint
            model["self_check"] = {"status": "passed", "errors": []}
            specification = extractor.render_complete_markdown_specification(model)
            self.assertIn("OPEN_FORM detail01", specification)
            self.assertIn("PARAMETER.P_CTT_ID", specification)

    def test_complete_markdown_renderer_covers_template_paths_items_and_refresh_preservation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_full_bundle(root)
            model = compile_model(root)
            fingerprint = extractor.semantic_state_hash(model)
            model["run"]["state_sha256"] = fingerprint
            model["run"]["evidence_sha256"] = fingerprint
            model["self_check"] = {"status": "passed", "errors": []}
            comparison = """
            Prior source-backed anchors: `DEMO_TABLE`, `HDR.TITLE`.
            CHECK_EXTERNAL ( );
            Target-only identifier that must not become evidence: `FR-DEMO-001`.
            """
            package = extractor.render_evidence_markdown_package(
                model,
                extraction_mode="fresh",
                comparison_spec_text=comparison,
            )
            specification = package["demo-legacy-evidence-specification.md"]
            child_documents = {
                "operation_details": package["demo-operation-details.md"],
                "decoded_source": package["demo-decoded-source.md"],
                "database_reference": package["demo-database-reference.md"],
            }
            package_text = "\n".join(package.values())
            self.assertEqual(list(map(str, range(1, 23))), re.findall(r"^##\s+(\d+)\.", specification, re.M))
            self.assertEqual(list("ABCDEFGHIJ"), re.findall(r"^###\s+Appendix\s+([A-J])\.", specification, re.M))
            self.assertIn("### Tab: Detail", specification)
            self.assertIn("module_evidence_id: MOD-DEMO", specification)
            self.assertIn("MOD-DEMO#tab.detail", specification)
            self.assertIn("HDR.ID", specification)
            self.assertIn("HDR.TITLE", specification)
            self.assertIn("DEMO_WINDOW", specification)
            self.assertIn("DEMO_TABLE", specification)
            self.assertIn("DEMO_TABLE.ID (NUMBER)", specification)
            self.assertIn("DEMO_TABLE.TITLE (VARCHAR2(30))", specification)
            self.assertIn("| Local key | Region kind |", specification)
            self.assertIn("tab=DETAIL", specification)
            self.assertIn(
                "unknown (only design-time values are established; inherited/runtime behavior is gapped)",
                specification,
            )
            self.assertIn("ON DELETE CASCADE", specification)
            self.assertIn("### Header Delete: Database Consequences", specification)
            self.assertIn("Forms hard-blocker and warning routines are not a complete database-dependency inventory", specification)
            self.assertIn("DEP_FK", specification)
            self.assertIn("CHECK_EXTERNAL();", package_text)
            self.assertNotIn("[truncated]", package_text)
            self.assertNotRegex(package_text, r"\+\d+\s+more\b")
            self.assertNotIn("effective design_time_only", specification)
            for path in model["artifacts"]["behavior_ledger"]["records"]:
                self.assertIn(path["entry_point"]["symbol"], specification)
            self.assertNotRegex(specification, r"\b(?:FR|FLD|BR|MSG|TC|OQ)-DEMO-")
            self.assertEqual(
                [],
                extractor.validate_markdown_contract(
                    model,
                    specification,
                    comparison_spec_text=comparison,
                    package_documents=child_documents,
                ),
            )
            trigger_code = model["modules"][0]["triggers"][0]["code"].strip()
            without_exact_source = dict(child_documents)
            without_exact_source["decoded_source"] = without_exact_source["decoded_source"].replace(
                trigger_code, "SOURCE OMITTED", 1
            )
            self.assertTrue(
                any(
                    "Exact decoded source is absent" in error
                    for error in extractor.validate_markdown_contract(
                        model, specification, package_documents=without_exact_source
                    )
                )
            )
            without_typed_mapping = specification.replace(
                "DEMO_TABLE.ID (NUMBER)",
                "DEMO_TABLE.ID",
            )
            self.assertTrue(
                any(
                    "Typed physical mapping is absent" in error
                    for error in extractor.validate_markdown_contract(
                        model, without_typed_mapping, package_documents=child_documents
                    )
                )
            )
            self.assertTrue(
                any(
                    "truncation marker" in error
                    for error in extractor.validate_markdown_contract(
                        model,
                        specification + "\n[truncated]\n",
                        package_documents=child_documents,
                    )
                )
            )
            self.assertTrue(
                any(
                    "lossy '+N more' placeholder" in error
                    for error in extractor.validate_markdown_contract(
                        model,
                        specification + "\n+3 more\n",
                        package_documents=child_documents,
                    )
                )
            )

            authored = specification.replace(
                "## 4. Module Structure",
                "## 4. Module Structure\n\nHUMAN-REVIEW-NOTE: preserve this authored content.",
            )
            refreshed_candidate = extractor.render_complete_markdown_specification(
                model,
                extraction_mode="refresh",
                comparison_spec_text=authored,
            )
            refreshed = extractor.merge_evidence_regions(authored, refreshed_candidate)
            self.assertIn("HUMAN-REVIEW-NOTE: preserve this authored content.", refreshed)
            self.assertEqual(
                [],
                extractor.validate_markdown_contract(
                    model,
                    refreshed,
                    comparison_spec_text=authored,
                    package_documents=child_documents,
                ),
            )
            with self.assertRaisesRegex(ValueError, "lacks required evidence markers"):
                extractor.merge_evidence_regions(
                    '---\nmodule_id: "DEMO"\n---\n\n# Markerless historical specification\n',
                    refreshed_candidate,
                )

    def test_supplement_preserves_module_and_resolves_routine_and_library_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as full_temporary, tempfile.TemporaryDirectory() as supplement_temporary:
            full_root = Path(full_temporary)
            self.make_full_bundle(full_root)
            first = compile_model(full_root)
            supplement_root = Path(supplement_temporary)
            (supplement_root / "demol.pld").write_text(DEMO_PLD, encoding="utf-8")
            second = compile_model(supplement_root, first, supplemental=True)
            self.assertEqual(1, len(second["modules"][0]["blocks"]))
            self.assertIn("DEPENDENCY_TABLE", second["behavior_ledger"]["update"]["sql_references"][0]["object"])
            gaps = second["artifacts"]["gaps"]["records"]
            routine_gap = next(gap for gap in gaps if gap["gap_kind"] == "unresolved_call" and gap["subject"] == "CHECK_EXTERNAL")
            library_gap = next(gap for gap in gaps if gap["gap_kind"] == "binary_only" and gap["subject"] == "DEMOL")
            self.assertEqual("resolved", routine_gap["status"])
            self.assertEqual("resolved", library_gap["status"])
            third = compile_model(supplement_root, second, supplemental=True)
            third_gaps = third["artifacts"]["gaps"]["records"]
            self.assertEqual(
                "resolved",
                next(gap for gap in third_gaps if gap["gap_kind"] == "unresolved_call" and gap["subject"] == "CHECK_EXTERNAL")["status"],
            )
            self.assertEqual(
                "resolved",
                next(gap for gap in third_gaps if gap["gap_kind"] == "binary_only" and gap["subject"] == "DEMOL")["status"],
            )

    def test_compiler_transition_is_explicit_and_reparses(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_full_bundle(root)
            first = compile_model(root)
            first["extractor"]["version"] = "0.0.0-test"
            second = compile_model(root, first, supplemental=True)
            transition = second["incremental"]["compiler_transition"]
            self.assertTrue(transition["changed"])
            self.assertEqual("0.0.0-test", transition["previous_version"])
            self.assertEqual(extractor.EXTRACTOR_VERSION, transition["current_version"])
            synthetic = [
                row for row in second["artifacts"]["source_delta"]["records"]
                if row["change"] == "compiler_changed"
            ]
            self.assertEqual(1, len(synthetic))
            self.assertTrue(synthetic[0]["affected_fact_ids"])

    def test_identical_incremental_run_has_stable_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_full_bundle(root)
            (root / "demol.pld").write_text(DEMO_PLD, encoding="utf-8")
            first = compile_model(root)
            first_state = extractor.semantic_state_hash(first)
            first["run"]["state_sha256"] = first_state
            second = compile_model(root, first, supplemental=True)
            second_state = extractor.semantic_state_hash(second)
            self.assertEqual(first_state, second_state)
            self.assertFalse(second["incremental"]["change_set"]["added"])
            self.assertFalse(second["incremental"]["change_set"]["changed"])
            self.assertFalse(second["incremental"]["change_set"]["removed"])

    def test_real_glasct01_golden_when_bundle_is_available(self) -> None:
        workspace = Path(__file__).resolve().parents[4]
        bundle = workspace / "agentic-sdlc-data/tenants/default/projects/gala/repo/evidence/uploads/leg-spec-from-code-oracle/sourceBundle/extract"
        if not (bundle / "form/glasct01_fmb.xml").is_file():
            self.skipTest("GLASCT01 evidence bundle is not present")
        model = extractor.build_contract_artifacts(extractor.build_evidence(bundle, "GLASCT01"), None)
        errors = extractor.validate_evidence(model)
        self.assertEqual([], errors)
        module = model["modules"][0]
        self.assertEqual((6, 254, 481, 63), (
            len(module["blocks"]),
            sum(len(block["items"]) for block in module["blocks"]),
            len(module["triggers"]),
            sum(1 for unit in module["program_units"] if unit["scope"] == "form"),
        ))
        self.assertEqual({"FND_CURRENCIES_VL", "GLA_CTT_SEQ1", "QMS_MODULES"}, set(model["ddl"]["missing_objects"]))
        binary_gaps = [gap for gap in model["artifacts"]["gaps"]["records"] if gap["gap_kind"] == "binary_only" and gap["status"] != "resolved"]
        self.assertEqual(9, len(binary_gaps))
        self.assertEqual(9, len({gap["gap_id"] for gap in binary_gaps}))
        aggregate_gaps = model["gaps"]
        contract_gaps = model["artifacts"]["gaps"]["records"]
        self.assertEqual(62, len(aggregate_gaps))
        self.assertEqual(len(aggregate_gaps), len(contract_gaps))
        self.assertTrue(all(gap.get("evidence_impact") for gap in contract_gaps))
        self.assertTrue(all("poc_assumption" not in gap for gap in contract_gaps))
        ambiguous_subjects = {
            gap["subject"] for gap in contract_gaps
            if gap["gap_kind"] == "ambiguous_mapping" and gap["status"] != "resolved"
        }
        self.assertEqual(28, len(ambiguous_subjects))
        self.assertFalse(any(subject.split(".", 1)[0] in {"CG$CTRL", "CGNV$CG$WINDOW_1_1"} for subject in ambiguous_subjects))
        normalized_facts = model["artifacts"]["normalized_evidence"]["records"]
        self.assertEqual(len(normalized_facts), len({fact["fact_id"] for fact in normalized_facts}))
        self.assertTrue(any(fact["fact_kind"] == "database_comment" for fact in normalized_facts))
        tab_facts = [fact for fact in normalized_facts if fact["fact_kind"] == "tab"]
        self.assertEqual(
            {"Typification", "Duration", "Reporting", "Auditing", "Interest", "Finance", "Credit Rating", "Dunning", "Communication"},
            {fact["value"]["label"] for fact in tab_facts},
        )
        tabbed_visible = [
            fact for fact in normalized_facts
            if fact["fact_kind"] == "item_visual_placement"
            and fact["value"]["region_kind"] == "tab_page"
            and fact["value"]["visible"] is not False
        ]
        self.assertEqual(130, len(tabbed_visible))
        self.assertEqual(
            {"Typification": 50, "Duration": 12, "Reporting": 11, "Auditing": 5, "Interest": 5, "Finance": 25, "Credit Rating": 7, "Dunning": 7, "Communication": 8},
            {label: sum(fact["value"]["tab_label"] == label for fact in tabbed_visible) for label in {fact["value"]["tab_label"] for fact in tabbed_visible}},
        )
        aggregate_library_gaps = [
            gap for gap in aggregate_gaps
            if gap["kind"] in {"readable_module_library", "readable_attached_library"}
            and gap["status"] != "closed"
        ]
        self.assertEqual(9, len(aggregate_library_gaps))
        self.assertEqual(9, len({gap["subject"].upper() for gap in aggregate_library_gaps}))
        self.assertEqual(1, sum(1 for gap in aggregate_library_gaps if gap["subject"].upper() == "GLASCT01L"))
        module_gap = next(gap for gap in binary_gaps if gap["subject"] == "GLASCT01L")
        self.assertEqual(
            {"form/glasct01l.pll", "form/_glasct01l.pll"},
            {locator["relative_path"] for locator in module_gap["available_fallback_evidence"]},
        )
        self.assertEqual(
            {"commit_ownership", "rollback_and_failure_atomicity", "audit_column_population", "locking_and_lost_update_behavior", "retry_behavior"},
            set(module_gap["unresolved_facets"]),
        )
        controls = {block["id"]: block for block in module["blocks"]}
        for control_id in ("CGNV$CG$WINDOW_1_1", "CG$CTRL"):
            self.assertEqual("framework_control", controls[control_id]["block_role"])
            self.assertFalse(controls[control_id]["database_block"])
            self.assertFalse(any(controls[control_id]["effective_crud"].values()))
        self.assertEqual(
            {"ui/Maintain Standard Contract.jpeg", "ui/Maintain Standard Contract-1.jpeg"},
            {record["path"] for record in module["runtime_screenshots"]},
        )
        paths = model["artifacts"]["behavior_ledger"]["records"]
        custom_actions = [path for path in paths if path["operation"] == "custom_action"]
        navigation_effects = [
            effect
            for path in custom_actions
            for effect in path["side_effects"]
            if effect.get("effect") in {"open_or_transfer_form", "focus_item"}
        ]
        self.assertTrue(
            {"glascr01", "glacmd01", "glacsd01", "glascn01"}
            <= {
                effect["object"]
                for effect in navigation_effects
                if effect.get("effect") == "open_or_transfer_form"
            }
        )
        self.assertTrue(
            {"SCL.OGN_FUNLOC", "SPL.OGN_FUNLOC"}
            <= {
                effect["object"]
                for effect in navigation_effects
                if effect.get("effect") == "focus_item"
            }
        )
        open_form_paths = [
            path
            for path in custom_actions
            if any(
                effect.get("effect") == "open_or_transfer_form"
                and effect.get("object") in {"glascr01", "glacmd01", "glacsd01", "glascn01"}
                for effect in path["side_effects"]
            )
        ]
        self.assertTrue(all("68" in {str(message.get("code")) for message in path["messages"]} for path in open_form_paths))
        self.assertTrue(
            all(
                any(
                    "P_CTT_ID" in context or "P_CCT_ID" in context
                    for effect in path["side_effects"]
                    for context in effect.get("parameter_context", [])
                )
                for path in open_form_paths
            )
        )
        implicit = [path for path in paths if path["entry_point"]["scope"] == "forms_implicit_dml"]
        self.assertEqual(11, len(implicit))
        self.assertTrue(any(path["operation"] == "delete" and path["forms_blocks"] == ["SCL"] for path in implicit))
        self.assertTrue(any(path["operation"] == "delete" and path["forms_blocks"] == ["SPL"] for path in implicit))
        self.assertFalse(any(not effect.get("column") for path in paths for effect in path["field_effects"]))
        ctt_delete = next(path for path in paths if path["entry_point"]["symbol"] == "CTT.KEY-DELREC")
        self.assertEqual(39, sum(check["effect"] == "hard_blocker" for check in ctt_delete["dependency_checks"]))
        self.assertEqual(15, sum(check["database_cascade"] == "on_delete_cascade" for check in ctt_delete["dependency_checks"]))
        expected_validation_counts = {"CTT.PRE-INSERT": 173, "CTT.PRE-UPDATE": 153, "SCP.PRE-INSERT": 11, "SCP.PRE-UPDATE": 6, "SCL.PRE-INSERT": 1, "SCL.PRE-UPDATE": 1}
        for symbol, count in expected_validation_counts.items():
            path = next(record for record in paths if record["entry_point"]["symbol"] == symbol)
            self.assertEqual((count, count), (len(path["validations"]), len(path["validation_stop_branches"])))
        key_commit = next(path for path in paths if path["entry_point"]["symbol"] == "KEY-COMMIT")
        self.assertTrue({"KEY_COMMIT_BEFORE", "KEY_COMMIT_AFTER"} <= {edge["to"] for edge in key_commit["call_chain"]})
        source_inventory = model["artifacts"]["source_inventory"]["records"]
        screenshot = next(record for record in source_inventory if record["relative_path"] == "ui/Maintain Standard Contract.jpeg")
        self.assertEqual(["GLASCT01"], screenshot["module_association"])
        comment_files = {obj["source_path"] for obj in model["ddl"]["catalog"] if obj.get("comments")}
        self.assertEqual(136, len(comment_files))
        fingerprint = extractor.semantic_state_hash(model)
        model["run"]["state_sha256"] = fingerprint
        model["run"]["evidence_sha256"] = fingerprint
        model["self_check"] = {"status": "passed", "errors": []}
        previous_spec = bundle.parents[3] / "features/previous_glasct01-maintain-standard-contract-specification.md"
        comparison = previous_spec.read_text(encoding="utf-8") if previous_spec.is_file() else None
        package = extractor.render_evidence_markdown_package(
            model,
            extraction_mode="fresh",
            comparison_spec_text=comparison,
        )
        specification = package["glasct01-legacy-evidence-specification.md"]
        child_documents = {
            "operation_details": package["glasct01-operation-details.md"],
            "decoded_source": package["glasct01-decoded-source.md"],
            "database_reference": package["glasct01-database-reference.md"],
        }
        for anchor in (
            "CTT.WhereClause",
            "CTT.OrderByClause",
            "CG$DO_AUTO_QUERY",
            "CGRI$CHK_GLA_CONTRACTS",
            "CGRI$WRN_GLA_CONTRACTS",
            "KEY-COMMIT",
            "Typification",
            "Communication",
            "OPEN_FORM glascr01",
            "GO_ITEM SCL.OGN_FUNLOC",
        ):
            self.assertIn(anchor, specification)
        self.assertIn("MOD-GLASCT01#tab.typification", specification)
        self.assertIn("### Tab: Typification", specification)
        self.assertIn("SCP.CTT_ID", specification)
        self.assertIn("GLA_SCP_CTT_FK1", specification)
        self.assertIn("GLA_CONTRACTS; ON DELETE CASCADE", specification)
        self.assertIn("GLA_CONTRACTS; ON DELETE SET NULL", specification)
        self.assertNotIn("effective design_time_only", specification)
        self.assertIn("module_evidence_id: MOD-GLASCT01", specification)
        self.assertNotRegex(specification, r"\b(?:FR|FLD|BR|MSG|TC|OQ)-GLASCT01-")
        self.assertEqual(
            [],
            extractor.validate_markdown_contract(
                model,
                specification,
                comparison_spec_text=comparison,
                package_documents=child_documents,
            ),
        )
        with tempfile.TemporaryDirectory() as validation_temporary:
            validation_root = Path(validation_temporary)
            evidence_path = validation_root / "evidence.json"
            specification_path = validation_root / "glasct01-legacy-evidence-specification.md"
            screenshot_target = validation_root / "ui" / "Maintain Standard Contract.jpeg"
            screenshot_target.parent.mkdir()
            screenshot_target.write_bytes(b"test screenshot placeholder")
            (validation_root / "ui" / "Maintain Standard Contract-1.jpeg").write_bytes(
                b"test screenshot placeholder"
            )
            evidence_path.write_text(json.dumps(model), encoding="utf-8")
            specification_path.write_text(specification, encoding="utf-8")
            for filename, document in package.items():
                if filename != "glasct01-legacy-evidence-specification.md":
                    (validation_root / filename).write_text(document, encoding="utf-8")
            guard_result = specification_guard.run_guard(evidence_path, specification_path)
            self.assertEqual([], guard_result["errors"])
            self.assertEqual("pass_with_registered_gaps", guard_result["validation_status"])


if __name__ == "__main__":
    unittest.main()
