#!/usr/bin/env python3
"""Adversarial tests for the Oracle specification validator."""

from __future__ import annotations

import unittest

from validate_specification import validate_documents


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    return "\n".join(
        ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
        + ["| " + " | ".join(row) + " |" for row in rows]
    )


def requirement_fixture() -> str:
    required_headings = [
        "Purpose And Authority", "Scope And Applicability", "Target Workflow", "Local Requirements",
        "Business Rules And Exceptions", "Origin And Target Differences", "Acceptance Criteria",
        "Assumptions Register", "Open Questions Register", "Evidence Coverage", "Change History",
    ]
    body = "\n\n".join(f"## {heading}\n\nComplete." for heading in required_headings)
    return f"""---
id: FEAT-GALA-001
artifact_type: feature
title: Example
status: draft-curated
taxonomy_path: Gala / Example
origin_type: legacy_transferred
change_intent: preserve
source_ids: [SRC-1]
candidate_ids: [CAND-1]
implementation_specification: architecture/target-to-be/example-implementation-spec.md
validation_status: validated
local_key_scheme: "FEAT-GALA-001#<local-key>"
last_updated: 2026-08-02
---

# Example

{body}
"""


def implementation_fixture(
    *,
    gap: bool = False,
    missing_action: bool = False,
    include_operation_decisions: bool = True,
    include_error_translations: bool = True,
    duplicate_operation_key: bool = False,
    unknown_operation_parent: bool = False,
) -> str:
    review = "reviewable_with_gaps" if gap else "review_ready"
    implementation = "not_implementation_ready" if gap else "implementation_ready"
    posture = "allowed_with_known_gaps" if gap else "allowed"
    mapping_object = "TBD" if gap else "GALA_HEADER.CODE"
    mapping_disposition = "TBD" if gap else "verified"
    mapping_gap = "gap.mapping-code" if gap else "none"
    action_key = "action.other" if missing_action else "action.save"

    sections: list[str] = []
    sections.append("## Purpose And Scope\n\nComplete.")
    sections.append("## Source Authority And Evidence\n\n" + markdown_table(
        ["Source", "Responsibility", "Locator/version", "Limitations"],
        [["Oracle evidence", "Behavior", "evidence/features/example/form.md", "None"]],
    ))
    sections.append("## Target UI Contract\n\n" + markdown_table(
        ["UI key", "Element kind", "Location/label", "Modes", "Visible/enabled rule",
         "Required/read-only/default", "Dependency/trigger and behavior", "Requirement reference",
         "Contract reference", "Gap key"],
        [
            ["ui.code", "field", "Main / Code", "add/edit", "visible and enabled", "required/write/none",
             "validated on blur and save", "FEAT-GALA-001#input.code", "ui.code", mapping_gap],
            ["ui.save", "button", "Main / Save", "add/edit", "enabled when dirty", "N/A",
             "submits current form", "FEAT-GALA-001#action.save", "action.save", "none"],
        ],
    ))
    sections.append("## UI-To-Data Mapping\n\n" + markdown_table(
        ["UI key", "Logical attribute", "Legacy block.item", "Legacy table.column/object",
         "Physical type/nullability", "Target data/API member and type", "Transform/default", "CRUD",
         "Evidence locator", "Confidence", "Disposition", "Gap key"],
        [["ui.code", "code", "HEADER.CODE", mapping_object, "VARCHAR2(20)/NOT NULL", "code:string",
          "trim/no default", "CRU", "evidence/features/example/form.md#code", "high",
          mapping_disposition, mapping_gap]],
    ))
    sections.append("## LOV Contracts\n\n" + markdown_table(
        ["UI key", "Display value", "Return value", "Source object/query", "Parameters/dependencies",
         "Filter/sort", "Inactive-value behavior", "Cache/refresh", "Evidence locator", "Confidence",
         "Disposition", "Gap key"],
        [["ui.code", "description", "code", "GALA_CODES", "none", "code ascending", "show existing only",
          "refresh per open", "evidence/features/example/form.md#lov", "high", "verified", "none"]],
    ))
    sections.append("## Validation And Business Rules\n\n" + markdown_table(
        ["Rule key", "Requirement reference", "Trigger/layer", "Inputs", "Ordered rule/sequence",
         "Exact outcome/error message", "Evidence locator", "Confidence", "Disposition", "Gap key"],
        [["validation.code", "FEAT-GALA-001#input.code", "save/client+server", "ui.code",
          "1 required; 2 exists", "CODE_REQUIRED: Code is required",
          "evidence/features/example/form.md#validate-code", "high", "verified", "none"]],
    ))
    if include_error_translations:
        sections.append("## Oracle Constraint And Error Translation\n\n" + markdown_table(
            ["Error mapping key", "Applies to action/control", "Oracle failure signature",
             "Database object/constraint semantics", "Legacy application code",
             "User-facing message/template", "Message parameters", "Match and precedence",
             "Structured API/UI outcome", "Transaction/editor behavior", "Evidence locator",
             "Confidence", "Disposition", "Gap key"],
            [
                ["error.constraint.header-uk1", "action.save; ui.code",
                 "ORA-00001; GALA_OWNER.GALA_HEADER_UK1; GALA_HEADER_UK1",
                 "GALA_HEADER(CODE) unique", "GLA-00001", "Code already exists.", "N/A",
                 "exact normalized constraint before generic ORA-00001",
                 "code=GLA-00001; message; constraint=GALA_HEADER_UK1; target=ui.code",
                 "rollback; retain editor and focus ui.code",
                 "evidence/features/example/form.md#error-handler; catalogue.md#GLA-00001",
                 "high", "verified", "none"],
                ["error.fallback.unknown-database", "all database actions", "unmapped Oracle/driver failure",
                 "no recognized in-scope constraint", "DATABASE_ERROR", "The database operation could not be completed.", "N/A",
                 "after every exact constraint and application-code mapping",
                 "code=DATABASE_ERROR; safe message; no target",
                 "rollback; retain active editor; log sanitized diagnostic",
                 "ADR-1#unknown-database-errors", "high", "verified", "none"],
            ],
        ))
    sections.append("## Search And Retrieval Contract\n\n" + markdown_table(
        ["Concern", "Required behavior", "Limits/defaults", "Errors/empty behavior", "Evidence/decision",
         "Disposition", "Gap key"],
        [["Operators", "exact code match", "limit 100", "show no-results state",
          "evidence/features/example/form.md#query", "verified", "none"]],
    ))
    sections.append("## Action And Transaction Contracts\n\n" + markdown_table(
        ["Action key", "UI keys/modes", "Visible/enabled and preconditions", "Authorization",
         "Ordered client/server validations", "Transaction and database operation sequence",
         "Final objects/procedures/functions", "Commit/rollback/partial failure", "Response/side effects",
         "Exact errors/messages", "Requirement references", "Evidence locator", "Confidence", "Disposition",
         "Gap key"],
        [[action_key, "ui.save; add/edit", "visible and enabled when dirty", "GALA_EDITOR",
          "1 validation.code; operation.save.persist-header", "single transaction: operation.save.persist-header", "GALA_HEADER",
          "commit on success; rollback all on error", "return row and show success",
          "CODE_REQUIRED: Code is required", "FEAT-GALA-001#action.save",
          "evidence/features/example/form.md#save", "high", "verified", "none"]],
    ))
    if include_operation_decisions:
        operation_parent = "action.missing" if unknown_operation_parent else action_key
        operation_rows = [[
            "operation.save.persist-header", operation_parent, "key-commit", "10", "DML", "ui.code bound as :code",
            "insert a new row or update the selected row", "INSERT/UPDATE GALA_HEADER using :code",
            "continue to commit on one affected row; stop on error", "N/A", "participates in form transaction",
            "evidence/features/example/form.md#save-persistence", "high", "verified", "none",
        ]]
        if duplicate_operation_key:
            operation_rows.append([
                "operation.save.persist-header", operation_parent, "key-commit", "20", "query", "saved row id",
                "reload saved row", "SELECT GALA_HEADER by id", "return refreshed row", "N/A", "none",
                "evidence/features/example/form.md#save-reload", "high", "verified", "none",
            ])
        sections.append("## Operation Decision Tables\n\n" + markdown_table(
            ["Operation row key", "Parent action/operation", "Phase/trigger", "Order",
             "Decision kind", "Condition and inputs/binds", "Detailed rule/check or call", "Physical operation/object",
             "Outcome and control flow", "Exact message/error", "Transaction effect", "Evidence locator",
             "Confidence", "Disposition", "Gap key"],
            operation_rows,
        ))
    crud_rows = []
    for operation in ["create", "retrieve", "update", "delete", "submit/save", "cancel/clear"]:
        crud_rows.append([
            operation, "yes", action_key, "validation.code", "defined transaction", "GALA_HEADER",
            "success or exact error", "evidence/features/example/form.md#" + operation.replace("/", "-"), "none",
        ])
    sections.append("## CRUD And Submit Completeness\n\n" + markdown_table(
        ["Operation", "Applicable", "Entry action keys", "Validations", "Transaction/database effect",
         "Final objects/procedures/functions", "Success/error outcome", "Evidence/decision", "Gap key"],
        crud_rows,
    ))
    sections.append("## Parent-Child Persistence\n\n" + markdown_table(
        ["Relationship", "Load behavior", "Save order", "Update/delete semantics",
         "Orphan/partial-failure behavior", "Evidence/decision", "Disposition", "Gap key"],
        [["header-lines", "load by header id", "header then lines", "restrict header delete with lines",
          "rollback all", "evidence/features/example/form.md#detail", "verified", "none"]],
    ))
    sections.append("## Tab And Population Logic\n\n" + markdown_table(
        ["Tab/section", "Initial population", "Refresh/lazy-load trigger", "Dependencies", "Dirty/stale behavior",
         "Failure behavior", "Evidence/decision", "Disposition", "Gap key"],
        [["Main", "load selected row", "refresh after save", "selected id", "preserve dirty form",
          "show load error", "mockup /example#main", "verified", "none"]],
    ))
    sections.append("## API Or Service Contracts\n\n" + markdown_table(
        ["Contract key", "Method/operation", "Request", "Response", "Validation/errors", "Authorization",
         "Idempotency/concurrency", "Requirement references", "Evidence/decision", "Disposition", "Gap key"],
        [["api.save", "POST /example", "code", "saved row", "CODE_REQUIRED/400", "GALA_EDITOR",
          "row version", "FEAT-GALA-001#action.save", "ADR-1", "verified", "none"]],
    ))
    sections.append("## Cross-Cutting Requirements\n\n" + markdown_table(
        ["Concern", "Implementation requirement", "Enforcement/failure behavior", "Evidence/decision",
         "Disposition", "Gap key"],
        [["Authorization", "require GALA_EDITOR", "return 403", "ADR-1", "verified", "none"]],
    ))
    sections.append("## Acceptance Scenarios\n\n" + markdown_table(
        ["Scenario key", "Requirement references", "Given", "When", "Then", "Failure/rollback evidence",
         "Disposition", "Gap key"],
        [["scenario.save", "FEAT-GALA-001#action.save", "valid form", "save", "row committed",
          "rollback assertion", "verified", "none"]],
    ))
    sections.append("## Coverage Matrix\n\n" + markdown_table(
        ["UI key", "Mockup location", "Oracle evidence", "Requirement reference", "Implementation sections",
         "Disposition", "Gap key/rationale"],
        [
            ["ui.code", "Main / Code", "evidence/features/example/form.md#code",
             "FEAT-GALA-001#input.code", "UI-To-Data Mapping", mapping_disposition, mapping_gap],
            ["ui.save", "Main / Save", "evidence/features/example/form.md#save",
             "FEAT-GALA-001#action.save", "Action And Transaction Contracts", "verified", "none"],
        ],
    ))
    readiness_table = markdown_table(
        ["Outcome", "Value", "Reason"],
        [["Review readiness", review, "derived"], ["Implementation readiness", implementation, "derived"],
         ["Code generation posture", posture, "derived"]],
    )
    gap_headers = ["Gap key", "Type", "Severity", "Statement", "Affected local keys",
                   "Likely generated-code/behavior impact", "Safe POC fallback", "Resolution needed", "Status"]
    gap_rows: list[list[str]] = []
    if gap:
        gap_rows.append(["gap.mapping-code", "gap", "high", "Physical column is not proven", "ui.code",
                         "Generated persistence may target the wrong column",
                         "disable persistence and use in-memory mock", "confirm column from Forms evidence",
                         "accepted-for-poc"])
    gap_table = "\n\n" + markdown_table(gap_headers, gap_rows)
    sections.append("## Implementation Readiness And Consolidated Gaps\n\n" + readiness_table + gap_table)
    sections.append("## Evidence And Confidence Summary\n\nComplete.")
    sections.append("## Change History\n\nComplete.")

    return f"""---
artifact_type: target_implementation_specification
title: Example Target Implementation Specification
status: draft
governed_package_id: FEAT-GALA-001
review_readiness: {review}
implementation_readiness: {implementation}
code_generation_posture: {posture}
source_ids: [SRC-1]
mockup_url: http://localhost/example
resolved_oracle_modules: [example]
last_updated: 2026-08-02
---

# Example

{"\n\n".join(sections)}
"""


class ValidatorTests(unittest.TestCase):
    def test_complete_specification_is_implementation_ready(self) -> None:
        result = validate_documents(
            requirement_fixture(), implementation_fixture(), require_operation_decisions=True,
            require_error_translations=True,
        )
        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual("implementation_ready", result["summary"]["implementation_readiness"])
        self.assertEqual("allowed", result["summary"]["code_generation_posture"])

    def test_registered_high_gap_allows_poc_but_fails_implementation_readiness(self) -> None:
        result = validate_documents(
            requirement_fixture(), implementation_fixture(gap=True), require_operation_decisions=True,
            require_error_translations=True,
        )
        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual("not_implementation_ready", result["summary"]["implementation_readiness"])
        self.assertEqual("allowed_with_known_gaps", result["summary"]["code_generation_posture"])
        self.assertTrue(any("wrong column" in warning for warning in result["warnings"]))

    def test_unregistered_tbd_is_rejected(self) -> None:
        text = implementation_fixture(gap=True).replace("gap.mapping-code", "none")
        result = validate_documents(requirement_fixture(), text, require_operation_decisions=True)
        self.assertFalse(result["valid"])
        self.assertTrue(any("no consolidated gap key" in error or "without a consolidated gap" in error
                            for error in result["errors"]))

    def test_missing_action_contract_is_rejected(self) -> None:
        result = validate_documents(
            requirement_fixture(), implementation_fixture(missing_action=True), require_operation_decisions=True
        )
        self.assertFalse(result["valid"])
        self.assertTrue(any("Interactive control has no Action contract" in error for error in result["errors"]))

    def test_missing_crud_operation_is_rejected(self) -> None:
        text = implementation_fixture().replace(
            "| delete | yes | action.save | validation.code | defined transaction | GALA_HEADER | success or exact error | evidence/features/example/form.md#delete | none |\n",
            "",
        )
        result = validate_documents(requirement_fixture(), text, require_operation_decisions=True)
        self.assertFalse(result["valid"])
        self.assertIn("CRUD And Submit Completeness missing operation: delete", result["errors"])

    def test_second_global_implementation_id_is_rejected(self) -> None:
        text = implementation_fixture().replace(
            "artifact_type: target_implementation_specification",
            "id: ARCH-TARGET-GALA-001\nartifact_type: target_implementation_specification",
        )
        result = validate_documents(requirement_fixture(), text, require_operation_decisions=True)
        self.assertFalse(result["valid"])
        self.assertTrue(any("must not create a second global ID" in error for error in result["errors"]))

    def test_legacy_spec_without_operation_table_is_backward_valid_with_warning(self) -> None:
        result = validate_documents(
            requirement_fixture(), implementation_fixture(include_operation_decisions=False)
        )
        self.assertTrue(result["valid"], result["errors"])
        self.assertTrue(any("rerun curation incrementally" in warning for warning in result["warnings"]))

    def test_current_curation_requires_operation_table(self) -> None:
        result = validate_documents(
            requirement_fixture(),
            implementation_fixture(include_operation_decisions=False),
            require_operation_decisions=True,
        )
        self.assertFalse(result["valid"])
        self.assertTrue(any("Operation Decision Tables" in error for error in result["errors"]))

    def test_legacy_spec_without_error_translation_is_backward_valid_with_warning(self) -> None:
        result = validate_documents(
            requirement_fixture(), implementation_fixture(include_error_translations=False)
        )
        self.assertTrue(result["valid"], result["errors"])
        self.assertTrue(any("constraint/application-message" in warning for warning in result["warnings"]))

    def test_current_curation_requires_error_translation(self) -> None:
        result = validate_documents(
            requirement_fixture(), implementation_fixture(include_error_translations=False),
            require_error_translations=True,
        )
        self.assertFalse(result["valid"])
        self.assertTrue(any("Oracle Constraint And Error Translation" in error
                            for error in result["errors"]))

    def test_known_application_code_without_message_or_gap_is_rejected(self) -> None:
        text = implementation_fixture().replace("Code already exists.", "TBD", 1)
        result = validate_documents(
            requirement_fixture(), text, require_error_translations=True
        )
        self.assertFalse(result["valid"])
        self.assertTrue(any("known application code" in error or "blank/TBD" in error
                            for error in result["errors"]))

    def test_error_translation_requires_one_unknown_fallback(self) -> None:
        text = implementation_fixture().replace("error.fallback.unknown-database", "error.fallback.other")
        result = validate_documents(
            requirement_fixture(), text, require_error_translations=True
        )
        self.assertFalse(result["valid"])
        self.assertTrue(any("exactly one error.fallback.unknown-database" in error
                            for error in result["errors"]))

    def test_duplicate_operation_row_key_is_rejected(self) -> None:
        result = validate_documents(
            requirement_fixture(),
            implementation_fixture(duplicate_operation_key=True),
            require_operation_decisions=True,
        )
        self.assertFalse(result["valid"])
        self.assertTrue(any("duplicate operation row key" in error.lower() for error in result["errors"]))

    def test_unknown_operation_parent_is_rejected(self) -> None:
        result = validate_documents(
            requirement_fixture(),
            implementation_fixture(unknown_operation_parent=True),
            require_operation_decisions=True,
        )
        self.assertFalse(result["valid"])
        self.assertTrue(any("unknown parent action/operation" in error for error in result["errors"]))

    def test_multiple_operation_tables_are_rejected(self) -> None:
        text = implementation_fixture()
        operation_body = text.split("## Operation Decision Tables\n\n", 1)[1].split(
            "\n\n## CRUD And Submit Completeness", 1
        )[0]
        text = text.replace(
            "\n\n## CRUD And Submit Completeness",
            f"\n\n{operation_body}\n\n## CRUD And Submit Completeness",
            1,
        )
        result = validate_documents(
            requirement_fixture(), text, require_operation_decisions=True
        )
        self.assertFalse(result["valid"])
        self.assertTrue(any("exactly one consolidated table" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
