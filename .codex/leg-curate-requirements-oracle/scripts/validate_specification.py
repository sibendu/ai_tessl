#!/usr/bin/env python3
"""Validate paired Oracle module specifications and derive readiness outcomes."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


ALLOWED_DISPOSITIONS = {"verified", "inferred", "conflict", "tbd", "not-applicable"}
ALLOWED_CONFIDENCE = {"high", "medium", "low"}
ALLOWED_GAP_TYPES = {
    "gap", "open-question", "conflict", "assumption", "risk", "implementation-blocker"
}
ALLOWED_SEVERITIES = {"blocker", "high", "medium", "low"}
ALLOWED_GAP_STATUSES = {"open", "accepted-for-poc", "resolved"}
UNRESOLVED_DISPOSITIONS = {"inferred", "conflict", "tbd"}
UNRESOLVED_GAP_STATUSES = {"open", "accepted-for-poc"}
INCOMPLETE_VALUES = {"", "tbd", "unknown", "not-known", "?"}
OPERATION_DECISION_HEADING = "Operation Decision Tables"
ERROR_TRANSLATION_HEADING = "Oracle Constraint And Error Translation"

REQUIREMENT_METADATA = {
    "id", "artifact_type", "title", "status", "taxonomy_path", "origin_type",
    "change_intent", "source_ids", "candidate_ids", "implementation_specification",
    "validation_status", "local_key_scheme", "last_updated",
}
IMPLEMENTATION_METADATA = {
    "artifact_type", "title", "status", "governed_package_id", "review_readiness",
    "implementation_readiness", "code_generation_posture", "source_ids", "mockup_url",
    "resolved_oracle_modules", "last_updated",
}
REQUIREMENT_HEADINGS = {
    "Purpose And Authority", "Scope And Applicability", "Target Workflow", "Local Requirements",
    "Business Rules And Exceptions", "Origin And Target Differences", "Acceptance Criteria",
    "Assumptions Register", "Open Questions Register", "Evidence Coverage", "Change History",
}
IMPLEMENTATION_HEADINGS = {
    "Purpose And Scope", "Source Authority And Evidence", "Target UI Contract",
    "UI-To-Data Mapping", "LOV Contracts", "Validation And Business Rules",
    "Search And Retrieval Contract", "Action And Transaction Contracts",
    "CRUD And Submit Completeness", "Parent-Child Persistence", "Tab And Population Logic",
    "API Or Service Contracts", "Cross-Cutting Requirements", "Acceptance Scenarios",
    "Coverage Matrix", "Implementation Readiness And Consolidated Gaps",
    "Evidence And Confidence Summary", "Change History",
}

TABLE_HEADERS = {
    "Target UI Contract": {
        "ui key", "element kind", "location/label", "modes", "visible/enabled rule",
        "required/read-only/default", "dependency/trigger and behavior", "requirement reference",
        "contract reference", "gap key",
    },
    "UI-To-Data Mapping": {
        "ui key", "logical attribute", "legacy block.item", "legacy table.column/object",
        "physical type/nullability", "target data/api member and type", "transform/default", "crud",
        "evidence locator", "confidence", "disposition", "gap key",
    },
    "LOV Contracts": {
        "ui key", "display value", "return value", "source object/query", "parameters/dependencies",
        "filter/sort", "inactive-value behavior", "cache/refresh", "evidence locator", "confidence",
        "disposition", "gap key",
    },
    "Validation And Business Rules": {
        "rule key", "requirement reference", "trigger/layer", "inputs", "ordered rule/sequence",
        "exact outcome/error message", "evidence locator", "confidence", "disposition", "gap key",
    },
    ERROR_TRANSLATION_HEADING: {
        "error mapping key", "applies to action/control", "oracle failure signature",
        "database object/constraint semantics", "legacy application code",
        "user-facing message/template", "message parameters", "match and precedence",
        "structured api/ui outcome", "transaction/editor behavior", "evidence locator",
        "confidence", "disposition", "gap key",
    },
    "Search And Retrieval Contract": {
        "concern", "required behavior", "limits/defaults", "errors/empty behavior",
        "evidence/decision", "disposition", "gap key",
    },
    "Action And Transaction Contracts": {
        "action key", "ui keys/modes", "visible/enabled and preconditions", "authorization",
        "ordered client/server validations", "transaction and database operation sequence",
        "final objects/procedures/functions", "commit/rollback/partial failure", "response/side effects",
        "exact errors/messages", "requirement references", "evidence locator", "confidence",
        "disposition", "gap key",
    },
    OPERATION_DECISION_HEADING: {
        "operation row key", "parent action/operation", "phase/trigger", "order",
        "decision kind", "condition and inputs/binds", "detailed rule/check or call", "physical operation/object",
        "outcome and control flow", "exact message/error", "transaction effect", "evidence locator",
        "confidence", "disposition", "gap key",
    },
    "CRUD And Submit Completeness": {
        "operation", "applicable", "entry action keys", "validations", "transaction/database effect",
        "final objects/procedures/functions", "success/error outcome", "evidence/decision", "gap key",
    },
    "Parent-Child Persistence": {
        "relationship", "load behavior", "save order", "update/delete semantics",
        "orphan/partial-failure behavior", "evidence/decision", "disposition", "gap key",
    },
    "Tab And Population Logic": {
        "tab/section", "initial population", "refresh/lazy-load trigger", "dependencies",
        "dirty/stale behavior", "failure behavior", "evidence/decision", "disposition", "gap key",
    },
    "API Or Service Contracts": {
        "contract key", "method/operation", "request", "response", "validation/errors", "authorization",
        "idempotency/concurrency", "requirement references", "evidence/decision", "disposition", "gap key",
    },
    "Cross-Cutting Requirements": {
        "concern", "implementation requirement", "enforcement/failure behavior", "evidence/decision",
        "disposition", "gap key",
    },
    "Acceptance Scenarios": {
        "scenario key", "requirement references", "given", "when", "then",
        "failure/rollback evidence", "disposition", "gap key",
    },
    "Coverage Matrix": {
        "ui key", "mockup location", "oracle evidence", "requirement reference",
        "implementation sections", "disposition", "gap key/rationale",
    },
}

ROW_REQUIRED = {
    heading: set(headers) - {"gap key"} for heading, headers in TABLE_HEADERS.items()
}
ROW_REQUIRED["Coverage Matrix"].discard("gap key/rationale")
ROW_REQUIRED["Coverage Matrix"].add("gap key/rationale")

KEY_COLUMNS = {
    "Target UI Contract": "ui key", "UI-To-Data Mapping": "ui key",
    "Validation And Business Rules": "rule key", "Action And Transaction Contracts": "action key",
    OPERATION_DECISION_HEADING: "operation row key",
    ERROR_TRANSLATION_HEADING: "error mapping key",
    "CRUD And Submit Completeness": "operation", "API Or Service Contracts": "contract key",
    "Acceptance Scenarios": "scenario key", "Coverage Matrix": "ui key",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requirement", required=True, type=Path)
    parser.add_argument("--implementation", required=True, type=Path)
    parser.add_argument(
        "--require-operation-decisions",
        action="store_true",
        help="Require the generalized Operation Decision Tables section used by current curation runs",
    )
    parser.add_argument(
        "--require-error-translations",
        action="store_true",
        help="Require the Oracle constraint/application-message translation catalogue used by current curation runs",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args()


def normalize(value: str) -> str:
    return value.strip().strip("`\"'").lower().replace("_", "-").replace(" ", "-")


def incomplete(value: str) -> bool:
    return normalize(value) in INCOMPLETE_VALUES


def front_matter(text: str) -> dict[str, str]:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, flags=re.DOTALL)
    if not match:
        return {}
    result: dict[str, str] = {}
    for key, value in re.findall(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*([^\n]*)$", match.group(1), re.MULTILINE):
        result[key] = value.strip().strip("\"'")
    return result


def headings(text: str) -> set[str]:
    return set(re.findall(r"^##\s+(.+?)\s*$", text, flags=re.MULTILINE))


def section_text(text: str, heading: str) -> str:
    match = re.search(
        rf"^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s+|\Z)", text,
        flags=re.MULTILINE | re.DOTALL,
    )
    return match.group(1) if match else ""


def split_row(line: str) -> list[str]:
    return [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]


def section_tables(text: str, heading: str) -> list[list[dict[str, str]]]:
    lines = section_text(text, heading).splitlines()
    tables: list[list[dict[str, str]]] = []
    index = 0
    while index < len(lines) - 1:
        if not lines[index].strip().startswith("|") or not re.match(r"^\s*\|?[\s:|-]+\|?\s*$", lines[index + 1]):
            index += 1
            continue
        headers = [value.lower() for value in split_row(lines[index])]
        index += 2
        rows: list[dict[str, str]] = []
        while index < len(lines) and lines[index].strip().startswith("|"):
            cells = split_row(lines[index])
            if len(cells) == len(headers):
                rows.append(dict(zip(headers, cells)))
            index += 1
        tables.append(rows)
    return tables


def section_table_headers(text: str, heading: str) -> list[set[str]]:
    lines = section_text(text, heading).splitlines()
    result: list[set[str]] = []
    for index in range(len(lines) - 1):
        if lines[index].strip().startswith("|") and re.match(r"^\s*\|?[\s:|-]+\|?\s*$", lines[index + 1]):
            result.append({value.lower() for value in split_row(lines[index])})
    return result


def first_table(text: str, heading: str) -> list[dict[str, str]]:
    tables = section_tables(text, heading)
    return tables[0] if tables else []


def table_headers(text: str, heading: str) -> set[str]:
    section = section_text(text, heading)
    lines = section.splitlines()
    for index in range(len(lines) - 1):
        if lines[index].strip().startswith("|") and re.match(r"^\s*\|?[\s:|-]+\|?\s*$", lines[index + 1]):
            return {value.lower() for value in split_row(lines[index])}
    return set()


def gap_references(value: str) -> set[str]:
    return {match.lower() for match in re.findall(r"\bgap\.[a-z0-9][a-z0-9._-]*\b", value, re.IGNORECASE)}


def operation_references(value: str) -> set[str]:
    return {
        match.lower()
        for match in re.findall(r"\boperation\.[a-z0-9][a-z0-9._-]*\b", value, re.IGNORECASE)
    }


def validate_documents(
    requirement: str,
    implementation: str,
    *,
    require_operation_decisions: bool = False,
    require_error_translations: bool = False,
) -> dict:
    errors: list[str] = []
    warnings: list[str] = []

    requirement_meta = front_matter(requirement)
    implementation_meta = front_matter(implementation)
    if not requirement_meta:
        errors.append("Requirement file has no valid YAML-style front matter")
    if not implementation_meta:
        errors.append("Implementation file has no valid YAML-style front matter")
    for key in sorted(REQUIREMENT_METADATA - requirement_meta.keys()):
        errors.append(f"Requirement metadata missing: {key}")
    for key in sorted(IMPLEMENTATION_METADATA - implementation_meta.keys()):
        errors.append(f"Implementation metadata missing: {key}")
    if "id" in implementation_meta:
        errors.append("Implementation specification must not create a second global ID; use governed_package_id")

    for heading in sorted(REQUIREMENT_HEADINGS - headings(requirement)):
        errors.append(f"Requirement section missing: {heading}")
    for heading in sorted(IMPLEMENTATION_HEADINGS - headings(implementation)):
        errors.append(f"Implementation section missing: {heading}")
    operation_section_present = OPERATION_DECISION_HEADING in headings(implementation)
    if not operation_section_present:
        message = (
            "Implementation section missing: Operation Decision Tables; "
            "rerun curation incrementally to add detailed operation evidence"
        )
        if require_operation_decisions:
            errors.append(message)
        else:
            warnings.append(message)
    error_translation_section_present = ERROR_TRANSLATION_HEADING in headings(implementation)
    if not error_translation_section_present:
        message = (
            f"Implementation section missing: {ERROR_TRANSLATION_HEADING}; "
            "rerun curation incrementally to add Oracle constraint/application-message mappings"
        )
        if require_error_translations:
            errors.append(message)
        else:
            warnings.append(message)

    package_id = requirement_meta.get("id", "")
    governed_package_id = implementation_meta.get("governed_package_id", "")
    if package_id and governed_package_id and package_id != governed_package_id:
        errors.append("Implementation governed_package_id does not match requirement id")

    readiness_tables = section_tables(implementation, "Implementation Readiness And Consolidated Gaps")
    readiness_headers = section_table_headers(implementation, "Implementation Readiness And Consolidated Gaps")
    if len(readiness_tables) < 2:
        errors.append("Implementation readiness section must contain its outcome table and consolidated gap table")
    elif readiness_headers[0] != {"outcome", "value", "reason"}:
        errors.append("Implementation readiness outcome table has invalid columns")
    expected_gap_headers = {
        "gap key", "type", "severity", "statement", "affected local keys",
        "likely generated-code/behavior impact", "safe poc fallback", "resolution needed", "status",
    }
    if len(readiness_headers) >= 2 and readiness_headers[1] != expected_gap_headers:
        errors.append("Consolidated gap table has invalid columns")
    outcome_rows = readiness_tables[0] if readiness_tables else []
    gap_rows = readiness_tables[1] if len(readiness_tables) > 1 else []
    gaps: dict[str, dict[str, str]] = {}
    for index, row in enumerate(gap_rows, start=1):
        gap_key = normalize(row.get("gap key", ""))
        gap_type = normalize(row.get("type", ""))
        severity = normalize(row.get("severity", ""))
        status = normalize(row.get("status", ""))
        if not gap_key.startswith("gap."):
            errors.append(f"Consolidated gap row {index} has invalid local gap key")
            continue
        if gap_key in gaps:
            errors.append(f"Duplicate consolidated gap key: {gap_key}")
        gaps[gap_key] = row
        if gap_type not in ALLOWED_GAP_TYPES:
            errors.append(f"{gap_key} has invalid type: {gap_type or '<blank>'}")
        if severity not in ALLOWED_SEVERITIES:
            errors.append(f"{gap_key} has invalid severity: {severity or '<blank>'}")
        if status not in ALLOWED_GAP_STATUSES:
            errors.append(f"{gap_key} has invalid status: {status or '<blank>'}")
        for column in ("statement", "affected local keys", "likely generated-code/behavior impact",
                       "safe poc fallback", "resolution needed"):
            if incomplete(row.get(column, "")):
                errors.append(f"{gap_key} has blank/TBD {column}")

    unresolved_gaps = {
        key: row for key, row in gaps.items()
        if normalize(row.get("status", "")) in UNRESOLVED_GAP_STATUSES
    }
    referenced_gaps: set[str] = set()
    tables: dict[str, list[dict[str, str]]] = {}

    for heading, required_headers in TABLE_HEADERS.items():
        if heading == OPERATION_DECISION_HEADING and not operation_section_present:
            tables[heading] = []
            continue
        if heading == ERROR_TRANSLATION_HEADING and not error_translation_section_present:
            tables[heading] = []
            continue
        if heading == OPERATION_DECISION_HEADING:
            operation_tables = section_tables(implementation, heading)
            if len(operation_tables) != 1:
                errors.append(
                    f"{OPERATION_DECISION_HEADING} must contain exactly one consolidated table; "
                    f"found {len(operation_tables)}"
                )
        if heading == ERROR_TRANSLATION_HEADING:
            error_translation_tables = section_tables(implementation, heading)
            if len(error_translation_tables) != 1:
                errors.append(
                    f"{ERROR_TRANSLATION_HEADING} must contain exactly one consolidated table; "
                    f"found {len(error_translation_tables)}"
                )
        actual_headers = table_headers(implementation, heading)
        missing_headers = required_headers - actual_headers
        if missing_headers:
            errors.append(f"{heading} missing columns: {', '.join(sorted(missing_headers))}")
        rows = first_table(implementation, heading)
        tables[heading] = rows
        if not rows:
            errors.append(f"{heading} has no rows; add an explicit not-applicable or TBD row linked to a gap")
            continue

        disposition_column = "disposition" if "disposition" in required_headers else None
        for index, row in enumerate(rows, start=1):
            disposition = normalize(row.get(disposition_column, "")) if disposition_column else ""
            gap_cell = row.get("gap key/rationale", row.get("gap key", ""))
            refs = gap_references(gap_cell)
            referenced_gaps.update(refs)
            missing_values = [column for column in ROW_REQUIRED[heading] if incomplete(row.get(column, ""))]

            if disposition_column and disposition not in ALLOWED_DISPOSITIONS:
                errors.append(f"{heading} row {index} has invalid disposition: {disposition or '<blank>'}")
            if "confidence" in required_headers and normalize(row.get("confidence", "")) not in ALLOWED_CONFIDENCE:
                errors.append(f"{heading} row {index} has invalid confidence")
            if disposition == "verified" and missing_values:
                errors.append(f"{heading} row {index} is verified with blank/TBD cells: {', '.join(sorted(missing_values))}")
            if disposition == "verified":
                evidence = row.get(
                    "evidence locator",
                    row.get(
                        "evidence/decision",
                        row.get("oracle evidence", row.get("failure/rollback evidence", "")),
                    ),
                )
                if incomplete(evidence) or normalize(evidence) == "none":
                    errors.append(f"{heading} row {index} is verified without evidence")
            if disposition in UNRESOLVED_DISPOSITIONS and not refs:
                errors.append(f"{heading} row {index} is {disposition} but has no consolidated gap key")
            if missing_values and disposition != "not-applicable" and not refs:
                errors.append(f"{heading} row {index} has blank/TBD cells without a consolidated gap key")
            if disposition == "not-applicable":
                rationale = row.get("evidence/decision", row.get("evidence locator", row.get("gap key/rationale", "")))
                if incomplete(rationale) or normalize(rationale) in {"none", "not-applicable", "n/a"}:
                    errors.append(f"{heading} row {index} is not-applicable without rationale/evidence")
            for ref in refs:
                if ref not in gaps:
                    errors.append(f"{heading} row {index} references missing consolidated gap: {ref}")
                elif ref not in unresolved_gaps and (missing_values or disposition in UNRESOLVED_DISPOSITIONS):
                    errors.append(f"{heading} row {index} is unresolved but references resolved gap: {ref}")

    for heading, key_column in KEY_COLUMNS.items():
        seen: set[str] = set()
        for index, row in enumerate(tables.get(heading, []), start=1):
            key = normalize(row.get(key_column, ""))
            if incomplete(key):
                errors.append(f"{heading} row {index} has no {key_column}")
            elif key in seen:
                errors.append(f"{heading} contains duplicate {key_column}: {key}")
            seen.add(key)

    ui_rows = tables.get("Target UI Contract", [])
    ui_keys = {normalize(row.get("ui key", "")) for row in ui_rows if not incomplete(row.get("ui key", ""))}
    mapping_keys = {normalize(row.get("ui key", "")) for row in tables.get("UI-To-Data Mapping", [])}
    action_keys = {normalize(row.get("action key", "")) for row in tables.get("Action And Transaction Contracts", [])}
    coverage_keys = {normalize(row.get("ui key", "")) for row in tables.get("Coverage Matrix", [])}
    for key in sorted(ui_keys - coverage_keys):
        errors.append(f"Target UI key has no coverage row: {key}")
    for key in sorted(coverage_keys - ui_keys):
        errors.append(f"Coverage key is absent from Target UI Contract: {key}")

    data_kinds = {"field", "grid-column"}
    action_kinds = {"button", "link", "row-action", "navigator", "form-submit", "action"}
    for row in ui_rows:
        ui_key = normalize(row.get("ui key", ""))
        kind = normalize(row.get("element kind", ""))
        contract_ref = normalize(row.get("contract reference", ""))
        refs = gap_references(row.get("gap key", ""))
        if kind in data_kinds and ui_key not in mapping_keys and not refs:
            errors.append(f"Data control has no UI-To-Data Mapping or gap: {ui_key}")
        if kind in action_kinds and contract_ref not in action_keys and not refs:
            errors.append(f"Interactive control has no Action contract or gap: {ui_key}")

    required_operations = {"create", "retrieve", "update", "delete", "submit/save", "cancel/clear"}
    crud_rows = tables.get("CRUD And Submit Completeness", [])
    operation_names = {normalize(row.get("operation", "")) for row in crud_rows}
    for operation in sorted(required_operations - operation_names):
        errors.append(f"CRUD And Submit Completeness missing operation: {operation}")
    for index, row in enumerate(crud_rows, start=1):
        applicable = normalize(row.get("applicable", ""))
        refs = gap_references(row.get("gap key", ""))
        if applicable not in {"yes", "no"}:
            errors.append(f"CRUD And Submit Completeness row {index} has invalid applicable value")
        if applicable == "yes":
            material = ("entry action keys", "validations", "transaction/database effect",
                        "final objects/procedures/functions", "success/error outcome", "evidence/decision")
            if any(incomplete(row.get(column, "")) for column in material) and not refs:
                errors.append(f"CRUD And Submit Completeness row {index} is incomplete without a gap")
        if applicable == "no" and incomplete(row.get("evidence/decision", "")):
            errors.append(f"CRUD And Submit Completeness row {index} is not applicable without rationale")

    operation_rows = tables.get(OPERATION_DECISION_HEADING, [])
    allowed_operation_parents = action_keys | operation_names
    parent_to_operation_keys: dict[str, set[str]] = {}
    phase_orders: set[tuple[str, str, str]] = set()
    for index, row in enumerate(operation_rows, start=1):
        disposition = normalize(row.get("disposition", ""))
        parent = normalize(row.get("parent action/operation", ""))
        operation_key = normalize(row.get("operation row key", ""))
        phase = normalize(row.get("phase/trigger", ""))
        order = normalize(row.get("order", ""))
        if not operation_key.startswith("operation."):
            errors.append(
                f"{OPERATION_DECISION_HEADING} row {index} has invalid local operation row key"
            )
        if disposition != "not-applicable" and parent not in allowed_operation_parents:
            errors.append(
                f"{OPERATION_DECISION_HEADING} row {index} has unknown parent action/operation: "
                f"{parent or '<blank>'}"
            )
        if disposition != "not-applicable" and not re.fullmatch(r"[1-9][0-9]*", order):
            errors.append(f"{OPERATION_DECISION_HEADING} row {index} order must be a positive integer")
        order_key = (parent, phase, order)
        if disposition != "not-applicable" and order_key in phase_orders:
            errors.append(
                f"{OPERATION_DECISION_HEADING} contains duplicate order {order} "
                f"for {parent} in {phase}"
            )
        phase_orders.add(order_key)
        if parent and operation_key:
            parent_to_operation_keys.setdefault(parent, set()).add(operation_key)

    action_rows_by_key = {
        normalize(row.get("action key", "")): row
        for row in tables.get("Action And Transaction Contracts", [])
    }
    for parent, keys in sorted(parent_to_operation_keys.items()):
        if parent not in action_rows_by_key:
            continue
        action_refs = operation_references(" ".join(action_rows_by_key[parent].values()))
        if not (keys & action_refs):
            errors.append(
                f"Action contract {parent} does not reference its detailed operation row keys"
            )

    error_translation_rows = tables.get(ERROR_TRANSLATION_HEADING, [])
    fallback_rows = 0
    for index, row in enumerate(error_translation_rows, start=1):
        mapping_key = normalize(row.get("error mapping key", ""))
        disposition = normalize(row.get("disposition", ""))
        refs = gap_references(row.get("gap key", ""))
        if not mapping_key.startswith("error."):
            errors.append(f"{ERROR_TRANSLATION_HEADING} row {index} has invalid local error mapping key")
        if mapping_key == "error.fallback.unknown-database":
            fallback_rows += 1
        if disposition == "verified":
            for column in (
                "legacy application code", "user-facing message/template", "match and precedence",
                "structured api/ui outcome", "transaction/editor behavior",
            ):
                if incomplete(row.get(column, "")):
                    errors.append(
                        f"{ERROR_TRANSLATION_HEADING} row {index} is verified with incomplete {column}"
                    )
        known_code = not incomplete(row.get("legacy application code", ""))
        missing_message = incomplete(row.get("user-facing message/template", ""))
        if known_code and missing_message and not refs:
            errors.append(
                f"{ERROR_TRANSLATION_HEADING} row {index} has a known application code but "
                "no final message or consolidated gap"
            )
    if error_translation_section_present and fallback_rows != 1:
        errors.append(
            f"{ERROR_TRANSLATION_HEADING} must contain exactly one "
            f"error.fallback.unknown-database row; found {fallback_rows}"
        )

    for gap_key in sorted(unresolved_gaps.keys() - referenced_gaps):
        errors.append(f"Unresolved consolidated gap is not referenced by an affected contract row: {gap_key}")

    severities = [normalize(row.get("severity", "")) for row in unresolved_gaps.values()]
    if any(value in {"blocker", "high"} for value in severities):
        implementation_readiness = "not_implementation_ready"
    elif unresolved_gaps:
        implementation_readiness = "implementation_ready_with_known_gaps"
    else:
        implementation_readiness = "implementation_ready"
    review_readiness = "not_review_ready" if errors else ("reviewable_with_gaps" if unresolved_gaps else "review_ready")
    code_generation_posture = "allowed" if implementation_readiness == "implementation_ready" else "allowed_with_known_gaps"

    declared = {
        "review_readiness": normalize(implementation_meta.get("review_readiness", "")),
        "implementation_readiness": normalize(implementation_meta.get("implementation_readiness", "")),
        "code_generation_posture": normalize(implementation_meta.get("code_generation_posture", "")),
    }
    derived_normalized = {
        "review_readiness": normalize(review_readiness),
        "implementation_readiness": normalize(implementation_readiness),
        "code_generation_posture": normalize(code_generation_posture),
    }
    for key, value in derived_normalized.items():
        if declared[key] != value:
            errors.append(f"Declared {key} is {declared[key] or '<blank>'}; derived value is {value}")

    displayed_outcomes = {
        normalize(row.get("outcome", "")): normalize(row.get("value", "")) for row in outcome_rows
    }
    displayed_expected = {
        "review-readiness": derived_normalized["review_readiness"],
        "implementation-readiness": derived_normalized["implementation_readiness"],
        "code-generation-posture": derived_normalized["code_generation_posture"],
    }
    for outcome, value in displayed_expected.items():
        if displayed_outcomes.get(outcome) != value:
            errors.append(
                f"Displayed {outcome} is {displayed_outcomes.get(outcome, '<missing>')}; derived value is {value}"
            )

    for key, row in unresolved_gaps.items():
        impact = row.get("likely generated-code/behavior impact", "")
        warnings.append(f"{key} ({normalize(row.get('severity', ''))}) may affect generated code: {impact}")

    severity_counts = {severity: severities.count(severity) for severity in sorted(ALLOWED_SEVERITIES)}
    result = {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "package_id": package_id,
            "target_ui_rows": len(ui_rows),
            "mapping_rows": len(tables.get("UI-To-Data Mapping", [])),
            "action_rows": len(tables.get("Action And Transaction Contracts", [])),
            "operation_decision_rows": len(operation_rows),
            "error_translation_rows": len(error_translation_rows),
            "gap_counts": severity_counts,
            "review_readiness": review_readiness,
            "implementation_readiness": implementation_readiness,
            "code_generation_posture": code_generation_posture,
        },
    }
    return result


def emit(result: dict, json_output: bool) -> int:
    if json_output:
        print(json.dumps(result, indent=2))
    else:
        print("VALID" if result["valid"] else "INVALID")
        for error in result["errors"]:
            print(f"ERROR: {error}")
        for warning in result["warnings"]:
            print(f"WARNING: {warning}")
        print(json.dumps(result["summary"], indent=2))
    return 0 if result["valid"] else 1


def main() -> int:
    args = parse_args()
    errors: list[str] = []
    requirement = ""
    implementation = ""
    for path, label in ((args.requirement, "Requirement"), (args.implementation, "Implementation")):
        if not path.is_file():
            errors.append(f"Missing {label.lower()} file: {path}")
        elif label == "Requirement":
            requirement = path.read_text(encoding="utf-8")
        else:
            implementation = path.read_text(encoding="utf-8")
    if errors:
        return emit({"valid": False, "errors": errors, "warnings": [], "summary": {}}, args.json_output)
    return emit(
        validate_documents(
            requirement,
            implementation,
            require_operation_decisions=args.require_operation_decisions,
            require_error_translations=args.require_error_translations,
        ),
        args.json_output,
    )


if __name__ == "__main__":
    sys.exit(main())
