#!/usr/bin/env python3
"""Render and validate the complete Oracle module Markdown specification.

The evidence compiler owns source parsing and normalization.  This module owns
the human-reviewable output contract.  Keeping those responsibilities separate
prevents a richer evidence model from silently producing a poorer document.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import quote


TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "references" / "specification-template.md"
CANONICAL_SECTIONS = [str(number) for number in range(1, 23)]
CANONICAL_APPENDICES = list("ABCDEFGHIJ")
MARKER_RE = re.compile(
    r'<!--\s*oracle-evidence:start\s+key="(?P<key>[A-Za-z0-9_.:-]+)"\s*-->'
    r'(?P<body>.*?)'
    r'<!--\s*oracle-evidence:end\s+key="(?P=key)"\s*-->',
    re.S,
)
CODE_SPAN_RE = re.compile(r"`([^`\r\n]{1,180})`")
FRONTMATTER_RE = re.compile(r"\A---\r?\n(?P<body>.*?)\r?\n---\r?\n", re.S)


def markdown_cell(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, Mapping):
        value = "; ".join(f"{key}={item}" for key, item in value.items())
    elif isinstance(value, (list, tuple, set)):
        value = ", ".join(str(item) for item in value if item not in (None, ""))
    return " ".join(str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ").split()) or "—"


def markdown_code(value: Any) -> str:
    text = markdown_cell(value)
    return text if text == "—" else f"`{text.replace('`', '')}`"


def stable_spec_id(prefix: str, module_id: str, *semantic_parts: Any) -> str:
    semantic = "|".join(str(part or "").strip().upper() for part in semantic_parts)
    digest = hashlib.sha256(semantic.encode("utf-8")).hexdigest()[:10].upper()
    return f"{prefix}-{module_id}-{digest}"


def marker(key: str, body: Sequence[str]) -> list[str]:
    return [
        f'<!-- oracle-evidence:start key="{key}" -->',
        *body,
        f'<!-- oracle-evidence:end key="{key}" -->',
    ]


def row(values: Iterable[Any]) -> str:
    return "| " + " | ".join(markdown_cell(value) for value in values) + " |"


def code_row(values: Iterable[Any]) -> str:
    return "| " + " | ".join(markdown_code(value) for value in values) + " |"


def count_summary(value: Any) -> str:
    if not isinstance(value, Mapping) or not value:
        return "None recorded"
    parts = []
    for key, item in value.items():
        if isinstance(item, Mapping):
            count = sum(len(child) if isinstance(child, (list, tuple, set, Mapping)) else 1 for child in item.values())
        elif isinstance(item, (list, tuple, set, Mapping)):
            count = len(item)
        else:
            count = 1 if item not in (None, "", False) else 0
        parts.append(f"{key}={count}")
    return ", ".join(parts)


def evidence_reference_summary(value: Any, limit: int = 8) -> str:
    if not value:
        return "None recorded"
    records = value if isinstance(value, (list, tuple, set)) else [value]
    rendered = []
    for record in records:
        if isinstance(record, Mapping):
            rendered.append(
                str(
                    record.get("source_id")
                    or record.get("relative_path")
                    or record.get("source_path")
                    or record.get("symbol")
                    or record.get("locator")
                    or record.get("id")
                    or "structured evidence"
                )
            )
        else:
            rendered.append(str(record))
    compact = rendered[:limit]
    if len(rendered) > limit:
        compact.append(f"+{len(rendered) - limit} more")
    return ", ".join(compact)


def crud_cell(crud: Mapping[str, Any] | None) -> str:
    crud = crud or {}
    labels = (("query", "Q"), ("create", "I"), ("update", "U"), ("delete", "D"))
    return "/".join(label for key, label in labels if crud.get(key)) or "—"


def explicit_crud_cell(
    crud: Mapping[str, Any] | None,
    operations: Sequence[tuple[str, str]] = (("query", "Q"), ("create", "I"), ("update", "U")),
) -> str:
    """Render every design-time CRUD dimension, including explicit false values."""
    crud = crud or {}
    return "/".join(
        f"{label}={'Y' if crud.get(key) is True else 'N' if crud.get(key) is False else '?'}"
        for key, label in operations
    )


def effective_crud_cell(record: Mapping[str, Any]) -> str:
    """Keep effective runtime CRUD unknown when only design-time evidence exists."""
    status = str(record.get("effective_crud_status") or "unknown")
    if status == "design_time_only":
        return "unknown (only design-time values are established; inherited/runtime behavior is gapped)"
    if status == "restricted_by_block":
        return "unknown overall (design-time block restriction recorded; inherited/runtime behavior is gapped)"
    if status in {"true", "false", "conditional", "unknown"}:
        return status
    return f"unknown (unrecognized evidence-model status: {status})"


def locator_text(record: Mapping[str, Any]) -> str:
    locators = record.get("locators") or record.get("raw_locators") or []
    values = []
    for locator in locators[:4]:
        if isinstance(locator, Mapping):
            values.append(
                str(
                    locator.get("symbol")
                    or locator.get("locator")
                    or locator.get("relative_path")
                    or locator.get("source_path")
                    or ""
                )
            )
        elif locator:
            values.append(str(locator))
    return "; ".join(value for value in values if value) or "No structural locator recorded"


def entry_symbol(path: Mapping[str, Any]) -> str:
    entry = path.get("entry_point") or {}
    if isinstance(entry, Mapping):
        return str(entry.get("symbol") or entry.get("scope") or path.get("path_id") or "Unknown")
    return str(entry or path.get("path_id") or "Unknown")


def path_summary(path: Mapping[str, Any]) -> str:
    parts: list[str] = []
    if path.get("database_reads"):
        parts.append("reads " + ", ".join(path["database_reads"]))
    if path.get("database_writes"):
        parts.append("writes " + ", ".join(path["database_writes"]))
    if path.get("call_chain"):
        callees = sorted(
            {
                str(call.get("to"))
                for call in path["call_chain"]
                if isinstance(call, Mapping) and call.get("to")
            }
        )
        if callees:
            parts.append("calls " + ", ".join(callees))
    if path.get("branches"):
        parts.append(f"{len(path['branches'])} branch(es)")
    if path.get("validations"):
        parts.append(f"{len(path['validations'])} validation/message outcome(s)")
    if path.get("dependency_checks"):
        effects = sorted(
            {
                str(check.get("effect"))
                for check in path["dependency_checks"]
                if isinstance(check, Mapping) and check.get("effect")
            }
        )
        parts.append("dependency effects " + ", ".join(effects or ["recorded"]))
    navigation = sorted(
        {
            f"{effect.get('mechanism')} {effect.get('object')}"
            for effect in path.get("side_effects", [])
            if isinstance(effect, Mapping)
            and effect.get("effect") in {"focus_item", "open_or_transfer_form"}
            and effect.get("object")
        }
    )
    if navigation:
        parts.append("navigation " + ", ".join(navigation))
        parameter_context = sorted(
            {
                str(context)
                for effect in path.get("side_effects", [])
                if isinstance(effect, Mapping)
                and effect.get("effect") in {"focus_item", "open_or_transfer_form"}
                for context in effect.get("parameter_context", [])
                if context
            }
        )
        if parameter_context:
            parts.append(
                "navigation parameter context "
                + "; ".join(parameter_context)
            )
    if path.get("unresolved_calls"):
        parts.append("unresolved calls " + ", ".join(sorted(set(path["unresolved_calls"]))))
    transaction = path.get("transaction") or {}
    if isinstance(transaction, Mapping):
        unknowns = [
            key
            for key in ("boundary", "commit_owner", "rollback_behavior", "concurrency_behavior")
            if str(transaction.get(key) or "unknown").lower() == "unknown"
        ]
        if unknowns:
            parts.append("transaction unknown: " + ", ".join(unknowns))
    return "; ".join(parts) or "Reachable entry point; no further business outcome established by readable source"


def _database_objects(evidence: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    priorities = {"table": 5, "view": 4, "materialized_view": 4, "sequence": 3, "synonym": 2, "public_synonym": 1}
    module = evidence["modules"][0]
    relevant_names = {
        str(record.get("name") or "").upper().split(".")[-1]
        for record in evidence.get("ddl", {}).get("referenced_objects", [])
        if record.get("name")
    }
    relevant_names.update(
        str(block.get(key) or "").upper().split(".")[-1]
        for block in module.get("blocks", [])
        for key in ("query_data_source", "dml_data_name")
        if block.get(key)
    )
    catalog = [record for record in evidence.get("ddl", {}).get("catalog", []) if isinstance(record, Mapping)]
    # Add one-hop DDL dependants that can materially affect reads or destructive
    # behavior, without dumping the entire recursively supplied enterprise DDL
    # corpus into a single-module specification.
    inbound_dependency_targets = {
        str(block.get("dml_data_name") or "").upper().split(".")[-1]
        for block in module.get("blocks", [])
        if block.get("dml_data_name")
    }
    for record in catalog:
        name = str(record.get("name") or record.get("qualified_name") or "").upper().split(".")[-1]
        dependencies = {
            str(dependency or "").upper().split(".")[-1]
            for dependency in record.get("dependencies", [])
        }
        constraint_targets = {
            str(constraint.get("references_object") or "").upper().split(".")[-1]
            for constraint in record.get("constraints", [])
            if isinstance(constraint, Mapping) and constraint.get("references_object")
        }
        if (dependencies | constraint_targets) & inbound_dependency_targets:
            relevant_names.add(name)
    for record in catalog:
        name = str(record.get("name") or record.get("qualified_name") or "").upper().split(".")[-1]
        if not name or name not in relevant_names:
            continue
        current = result.get(name)
        candidate_priority = priorities.get(str(record.get("type") or "").lower(), 0)
        current_priority = priorities.get(str((current or {}).get("type") or "").lower(), -1)
        if current is None or candidate_priority > current_priority or (
            not current.get("columns") and record.get("columns")
        ):
            result[name] = record
    return result


def _all_units(module: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [
        record
        for key in ("triggers", "program_units")
        for record in module.get(key, [])
        if isinstance(record, Mapping)
    ]


def _all_items(module: Mapping[str, Any]) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    return [
        (block, item)
        for block in module.get("blocks", [])
        if isinstance(block, Mapping)
        for item in block.get("items", [])
        if isinstance(item, Mapping)
    ]


def _message_records(module: Mapping[str, Any], paths: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    messages: dict[tuple[str, str], dict[str, Any]] = {}

    def add_message(
        code: str,
        text: str,
        condition: str,
        severity: Any,
        status: str,
        locator: Any,
    ) -> None:
        key = (code, text)
        record = messages.setdefault(
            key,
            {
                "code": code,
                "text": text,
                "severity": set(),
                "conditions": set(),
                "statuses": set(),
                "locators": set(),
            },
        )
        record["severity"].add(str(severity or "not established"))
        record["conditions"].add(condition)
        record["statuses"].add(status)
        if locator:
            record["locators"].add(str(locator))

    for path in paths:
        for message in path.get("messages", []):
            if not isinstance(message, Mapping):
                continue
            code = str(message.get("code") or message.get("text") or "unresolved")
            text = str(message.get("text") or code)
            add_message(
                code,
                text,
                entry_symbol(path),
                message.get("severity"),
                "reachable",
                message.get("locator") or locator_text(path),
            )
    for unit in _all_units(module):
        for message in unit.get("messages", []):
            if not isinstance(message, Mapping):
                continue
            code = str(message.get("code") or message.get("text") or "unresolved")
            text = str(message.get("text") or code)
            condition = str(unit.get("name") or unit.get("id") or "program unit")
            add_message(
                code,
                text,
                condition,
                message.get("severity"),
                "decoded; path reachability may require review",
                message.get("locator") or unit.get("locator") or unit.get("source_path"),
            )
    result = []
    for key in sorted(messages):
        record = messages[key]
        conditions = sorted(record.pop("conditions"))
        locators = sorted(record.pop("locators"))
        statuses = sorted(record.pop("statuses"))
        severities = sorted(record.pop("severity"))
        result.append(
            {
                **record,
                "severity": ", ".join(severities),
                "condition": ", ".join(conditions),
                "status": ", ".join(statuses),
                "locator": "; ".join(locators),
            }
        )
    return result


def _operation_paths(evidence: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    records = evidence.get("artifacts", {}).get("behavior_ledger", {}).get("records", [])
    return sorted(
        (record for record in records if isinstance(record, Mapping)),
        key=lambda record: (str(record.get("operation")), entry_symbol(record), str(record.get("path_id"))),
    )


def _normalize_executable_statement(value: Any) -> str:
    """Normalize layout outside PL/SQL string literals without changing literal content."""
    text = str(value or "").replace("\\|", "|").strip()
    normalized: list[str] = []
    in_literal = False
    index = 0
    while index < len(text):
        char = text[index]
        if char == "'":
            normalized.append(char)
            if in_literal and index + 1 < len(text) and text[index + 1] == "'":
                normalized.append("'")
                index += 2
                continue
            in_literal = not in_literal
        elif char.isspace() and not in_literal:
            pass
        else:
            normalized.append(char.upper() if not in_literal else char)
        index += 1
    return "".join(normalized)


def _supported_comparison_anchors(
    evidence: Mapping[str, Any], comparison_spec_text: str | None
) -> list[dict[str, str]]:
    if not comparison_spec_text:
        return []
    blob = json.dumps(evidence, sort_keys=True, ensure_ascii=False).upper()
    normalized_blob = " ".join(
        blob.replace("\\N", " ").replace("\\R", " ").replace("\\T", " ").split()
    )
    normalized_evidence_lines: set[str] = set()

    def collect_evidence_lines(value: Any) -> None:
        if isinstance(value, str):
            for line in value.splitlines() or [value]:
                normalized = _normalize_executable_statement(line)
                if normalized:
                    normalized_evidence_lines.add(normalized)
        elif isinstance(value, Mapping):
            for child in value.values():
                collect_evidence_lines(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                collect_evidence_lines(child)

    collect_evidence_lines(evidence)
    module = evidence["modules"][0]
    blocks = {str(block.get("id") or "").upper(): block for block in module.get("blocks", [])}
    excluded_id_prefixes = (
        "CHG-",
        "FR-",
        "FLD-",
        "BR-",
        "MSG-",
        "TC-",
        "OQ-",
        "ASM-",
        "DEC-",
        "ACT-",
        "DEP-",
        "LOV-",
        "FLT-",
    )
    result: dict[str, dict[str, str]] = {}
    candidates: list[tuple[str, bool]] = [
        (raw, False) for raw in CODE_SPAN_RE.findall(comparison_spec_text)
    ]
    source_statement_pattern = re.compile(
        r"\b(?:SELECT|INSERT|UPDATE|DELETE|MERGE|OPEN_FORM|CALL_FORM|NEW_FORM|"
        r"GO_ITEM|COPY|NAME_IN|SET_ITEM_PROPERTY|SET_BLOCK_PROPERTY|"
        r"[A-Z][A-Z0-9_$#]*\s*\([^)]*\))",
        re.I,
    )
    for raw_line in comparison_spec_text.splitlines():
        line = raw_line.strip()
        if (
            8 <= len(line) <= 240
            and not line.startswith(("#", "|", "-", "<!--", "```", "~~~"))
            and source_statement_pattern.search(line)
        ):
            candidates.append((line, True))
    for raw, source_statement in candidates:
        anchor = " ".join(raw.split()).strip()
        upper = anchor.upper()
        if (
            not anchor
            or anchor.startswith(("./", "../"))
            or upper.startswith(excluded_id_prefixes)
            or len(anchor) > (240 if source_statement else 120)
            or (
                not source_statement
                and (
                    not re.fullmatch(r"[A-Za-z0-9_$#./:*-]+", anchor)
                    or not re.search(r"[A-Z_$]", upper)
                )
            )
        ):
            continue
        supported = upper in blob or upper in normalized_blob
        if source_statement:
            normalized_anchor = _normalize_executable_statement(anchor)
            supported = any(normalized_anchor in line for line in normalized_evidence_lines)
        support = "Current normalized evidence"
        property_match = re.fullmatch(r"([A-Za-z0-9_$#]+)\.(WhereClause|OrderByClause)", anchor, re.I)
        if property_match:
            block = blocks.get(property_match.group(1).upper())
            property_key = "where_clause" if property_match.group(2).lower() == "whereclause" else "order_by"
            supported = bool(block and block.get(property_key))
            support = f"Forms block property {property_match.group(1).upper()}.{property_match.group(2)}"
        if supported:
            if source_statement:
                support = "Exact source-supported statement in current normalized evidence"
            result.setdefault(
                upper,
                {
                    "anchor": anchor,
                    "support": support,
                    "match_kind": "source_statement" if source_statement else "anchor",
                },
            )
    return [result[key] for key in sorted(result)]


def _template_contract() -> tuple[list[str], list[str]]:
    text = TEMPLATE_PATH.read_text(encoding="utf-8")
    sections = re.findall(r"^##\s+(\d+)\.", text, re.M)
    markers = re.findall(r'oracle-evidence:start\s+key="([^"]+)"', text)
    return sections, markers


def _frontmatter_value(text: str, key: str) -> str | None:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None
    value_match = re.search(rf"^{re.escape(key)}:\s*[\"']?([^\"'\r\n]+)", match.group("body"), re.M)
    return value_match.group(1).strip() if value_match else None


def _replace_frontmatter_values(previous: str, generated: str, keys: Sequence[str]) -> str:
    previous_match = FRONTMATTER_RE.match(previous)
    generated_match = FRONTMATTER_RE.match(generated)
    if not previous_match or not generated_match:
        raise ValueError("Refresh requires valid YAML front matter in both the existing and generated specifications.")
    previous_body = previous_match.group("body")
    generated_body = generated_match.group("body")
    for key in keys:
        generated_value = re.search(rf"^{re.escape(key)}:\s*(.+)$", generated_body, re.M)
        if not generated_value:
            continue
        replacement = f"{key}: {generated_value.group(1)}"
        if re.search(rf"^{re.escape(key)}:", previous_body, re.M):
            previous_body = re.sub(rf"^{re.escape(key)}:\s*.+$", replacement, previous_body, flags=re.M)
        else:
            previous_body += "\n" + replacement
    return previous[: previous_match.start("body")] + previous_body + previous[previous_match.end("body") :]


def merge_evidence_regions(previous: str, generated: str) -> str:
    previous_regions = {match.group("key"): match.group(0) for match in MARKER_RE.finditer(previous)}
    generated_matches = {match.group("key"): match for match in MARKER_RE.finditer(generated)}
    required = set(_template_contract()[1])
    missing = sorted(required - set(previous_regions))
    if missing:
        raise ValueError(
            "Refresh cannot safely preserve authored content because the existing specification lacks "
            f"required evidence markers: {', '.join(missing)}. Run fresh with --comparison-spec instead."
        )
    merged = previous
    for key in sorted(required):
        replacement = generated_matches[key].group(0)
        if key == "incremental-history":
            old_body = MARKER_RE.search(previous_regions[key]).group("body")
            new_body = generated_matches[key].group("body")
            old_rows = [
                line
                for line in old_body.splitlines()
                if line.startswith("|")
                and "Run ID" not in line
                and not re.fullmatch(r"\|[\s:|-]+\|", line)
            ]
            new_lines = new_body.splitlines()
            existing = {line.split("|")[1].strip() for line in old_rows}
            insertion = next(
                (index + 1 for index, line in enumerate(new_lines) if re.fullmatch(r"\|[\s:|-]+\|", line)),
                len(new_lines),
            )
            current_rows = [
                line
                for line in new_lines
                if line.startswith("|")
                and "Run ID" not in line
                and not re.fullmatch(r"\|[\s:|-]+\|", line)
            ]
            preserved = [line for line in old_rows if line.split("|")[1].strip() not in {row.split("|")[1].strip() for row in current_rows}]
            new_lines[insertion:insertion] = preserved
            replacement = marker(key, new_lines)
            replacement = "\n".join(replacement)
        merged = merged.replace(previous_regions[key], replacement)
    return _replace_frontmatter_values(
        merged,
        generated,
        (
            "evidence_fingerprint",
            "extraction_run_id",
            "extraction_mode",
            "legacy_evidence_status",
            "comparison_oracle_sha256",
        ),
    )


def validate_markdown_contract(
    evidence: Mapping[str, Any],
    specification: str,
    *,
    comparison_spec_text: str | None = None,
) -> list[str]:
    errors: list[str] = []
    specification_upper = specification.upper()
    template_sections, template_markers = _template_contract()
    if template_sections != CANONICAL_SECTIONS:
        errors.append(f"Template section contract changed unexpectedly: {template_sections}.")
    section_ids = re.findall(r"^##\s+(\d+)\.", specification, re.M)
    missing_sections = [section for section in CANONICAL_SECTIONS if section not in section_ids]
    if missing_sections:
        errors.append("Rendered specification is missing canonical sections: " + ", ".join(missing_sections) + ".")
    appendix_ids = re.findall(r"^###\s+Appendix\s+([A-J])\.", specification, re.M)
    missing_appendices = [appendix for appendix in CANONICAL_APPENDICES if appendix not in appendix_ids]
    if missing_appendices:
        errors.append("Rendered specification is missing appendices: " + ", ".join(missing_appendices) + ".")
    marker_matches = list(MARKER_RE.finditer(specification))
    marker_keys = [match.group("key") for match in marker_matches]
    for key in template_markers:
        if marker_keys.count(key) != 1:
            errors.append(f"Rendered specification requires exactly one balanced marker region for {key}.")
    module = evidence["modules"][0]
    module_id = str(module["module_id"]).upper()
    objects = _database_objects(evidence)
    if _frontmatter_value(specification, "module_id") != module_id:
        errors.append("Rendered specification module_id does not match the selected evidence module.")
    fingerprint = str(evidence.get("run", {}).get("evidence_sha256") or "")
    if _frontmatter_value(specification, "evidence_fingerprint") != fingerprint:
        errors.append("Rendered specification evidence_fingerprint does not match the evidence model.")
    for path in _operation_paths(evidence):
        if str(path.get("path_id")) not in specification:
            errors.append(f"Behavior path {path.get('path_id')} is absent from the rendered specification.")
    for gap in evidence.get("artifacts", {}).get("gaps", {}).get("records", []):
        if str(gap.get("gap_id")) not in specification:
            errors.append(f"Gap {gap.get('gap_id')} is absent from the rendered specification.")
    for source in evidence.get("artifacts", {}).get("source_inventory", {}).get("records", []):
        if str(source.get("source_id")) not in specification:
            errors.append(f"Source {source.get('source_id')} is absent from the rendered specification.")
    for block, item in _all_items(module):
        mapping = f"{block.get('id')}.{item.get('name')}"
        if mapping not in specification:
            errors.append(f"Forms item {mapping} is absent from the rendered specification.")
    for prefix in ("FR", "FLD", "BR", "MSG", "TC", "OQ"):
        applicable = {
            "FR": bool(_operation_paths(evidence)),
            "FLD": bool(_all_items(module)),
            "BR": any(path.get("branches") or path.get("dependency_checks") for path in _operation_paths(evidence)),
            "MSG": bool(_message_records(module, _operation_paths(evidence))),
            "TC": bool(_operation_paths(evidence)),
            "OQ": bool(evidence.get("artifacts", {}).get("gaps", {}).get("records", [])),
        }[prefix]
        if applicable and not re.search(rf"\b{prefix}-{re.escape(module_id)}-[A-F0-9]{{10}}\b", specification):
            errors.append(f"Rendered specification lacks stable {prefix} records.")
    for record in _supported_comparison_anchors(evidence, comparison_spec_text):
        if record["anchor"].upper() not in specification_upper:
            errors.append(f"Source-supported comparison anchor was lost: {record['anchor']}.")
    return errors


def render_markdown_specification(
    evidence: Mapping[str, Any],
    *,
    extraction_mode: str = "fresh",
    comparison_spec_text: str | None = None,
) -> str:
    """Render all canonical sections and appendices from normalized evidence."""
    module = evidence["modules"][0]
    run = evidence["run"]
    module_id = str(module["module_id"]).upper()
    title = str(module.get("title") or module_id)
    paths = _operation_paths(evidence)
    gaps = list(evidence.get("artifacts", {}).get("gaps", {}).get("records", []))
    coverage = list(evidence.get("artifacts", {}).get("coverage", {}).get("records", []))
    sources = list(evidence.get("artifacts", {}).get("source_inventory", {}).get("records", []))
    objects = _database_objects(evidence)
    units = _all_units(module)
    items = _all_items(module)
    messages = _message_records(module, paths)
    comparison_anchors = _supported_comparison_anchors(evidence, comparison_spec_text)
    comparison_hash = (
        hashlib.sha256(comparison_spec_text.encode("utf-8")).hexdigest()
        if comparison_spec_text
        else "not-supplied"
    )
    generated_date = str(run.get("generated_at") or datetime.now(timezone.utc).isoformat()).split("T")[0]
    open_gaps = [gap for gap in gaps if str(gap.get("status") or "").lower() != "resolved"]
    evidence_status = "complete-against-supplied-readable-evidence" if not open_gaps else "partial-with-registered-gaps"

    lines = [
        "---",
        f'specification_id: "MOD-{module_id}"',
        f'module_id: "{module_id}"',
        f'legacy_title: "{title.replace(chr(34), chr(39))}"',
        f'target_title: "{title.replace(chr(34), chr(39))}"',
        'specification_version: "0.1"',
        'status: "draft"',
        'artifact_kind: "legacy_extraction_specification"',
        'legacy_platform: "Oracle Forms"',
        'target_platform: "Next.js full-stack web application (proposal; not approved)"',
        'business_owner: "TBD"',
        'reviewers: "TBD"',
        f'evidence_fingerprint: "{run.get("evidence_sha256", "TBD")}"',
        f'extraction_run_id: "{run.get("run_id", "TBD")}"',
        f'extraction_mode: "{extraction_mode}"',
        f'legacy_evidence_status: "{evidence_status}"',
        'poc_forward_engineering_readiness: "not-assessed"',
        f'comparison_oracle_sha256: "{comparison_hash}"',
        "---",
        "",
        f"# {title}",
        "",
        "This draft separates source-backed legacy evidence from proposed target treatment. "
        "Target statements require governed curation and review before they become canonical requirements.",
        "",
        "## 1. Document Control",
        "",
        "| Field | Value |",
        "| --- | --- |",
        row(("Specification ID", f"MOD-{module_id}")),
        row(("Oracle Forms module", module_id)),
        row(("Legacy screen title", title)),
        row(("Target page title", title)),
        row(("Status", "Draft extracted specification")),
        row(("Evidence fingerprint", run.get("evidence_sha256"))),
        row(("Extraction run", f"{run.get('run_id')} ({extraction_mode})")),
        row(("Legacy evidence status", evidence_status)),
        row(("Comparison oracle", comparison_hash)),
        row(("POC forward-engineering readiness", "Not assessed")),
        "",
        "### Revision History",
        "",
        "| Version | Date | Change | Author |",
        "| --- | --- | --- | --- |",
        row(("0.1", generated_date, f"{extraction_mode.title()} code-derived specification", "Generated draft")),
        "",
        "## 2. Executive Summary",
        "",
        f"`{module_id}` is an Oracle Forms module titled “{title}”. The supplied readable evidence contains "
        f"{len(module.get('blocks', []))} blocks, {len(items)} items, {len(paths)} reachable behavior paths, "
        f"and {len(objects)} supplied DDL object definitions associated with the module.",
        "",
        f"The extraction is {evidence_status.replace('-', ' ')}. {len(open_gaps)} unresolved gap(s) remain and "
        "are listed in Appendix I. Proposed web behavior below is a reviewable translation of the evidence, "
        "not an approved target requirement.",
        "",
        "### Capability Summary",
        "",
    ]
    capability_rows = ["| Capability | Legacy | Proposed target treatment |", "| --- | --- | --- |"]
    for operation in ("query", "insert", "update", "delete", "save", "validate"):
        operation_paths = [path for path in paths if path.get("operation") == operation]
        capability_rows.append(
            row(
                (
                    operation.title(),
                    f"{len(operation_paths)} reachable path(s): "
                    + ", ".join(entry_symbol(path) for path in operation_paths[:8])
                    + (f"; +{len(operation_paths) - 8} more" if len(operation_paths) > 8 else ""),
                    "Preserve evidenced business outcomes in server-only processing; unresolved behavior remains gapped.",
                )
            )
        )
    lines.extend(marker("executive-capabilities", capability_rows))

    lines.extend(["", "## 3. Legacy Screen Overview", "", "### Current GALA UI", ""])
    screenshots = module.get("runtime_screenshots", [])
    if screenshots:
        lines.append(
            "A runtime screenshot candidate was associated with this module: "
            + ", ".join(markdown_code(record.get("path")) for record in screenshots)
            + ". Copy and visually confirm it before embedding it as authoritative layout evidence."
        )
    else:
        lines.append("No runtime screenshot was confidently matched. See Appendix A for source and gap details.")
    lines.extend(["", "### Legacy Interaction Summary", ""])
    interaction_body = [
        "The module exposes the following source-backed query and persistence behavior. "
        "Framework or binary-library effects remain bounded by the registered gaps."
    ]
    for block in module.get("blocks", []):
        if block.get("where_clause"):
            interaction_body.extend(
                [
                    "",
                    f"#### `{block['id']}.WhereClause`",
                    "",
                    "```sql",
                    str(block["where_clause"]).strip(),
                    "```",
                ]
            )
        if block.get("order_by"):
            interaction_body.extend(
                [
                    "",
                    f"#### `{block['id']}.OrderByClause`",
                    "",
                    "```sql",
                    str(block["order_by"]).strip(),
                    "```",
                ]
            )
    interaction_body.extend(
        [
            "",
            "| Operation | Entry point | Observable outcome | Evidence path |",
            "| --- | --- | --- | --- |",
            *[
                row((path.get("operation"), entry_symbol(path), path_summary(path), path.get("path_id")))
                for path in paths
            ],
        ]
    )
    lines.extend(marker("legacy-screen", interaction_body))
    lines.extend(["", "### Legacy Regions", ""])
    region_rows = ["| Region | Forms source | Purpose | Visible content | Legacy behavior |", "| --- | --- | --- | --- | --- |"]
    region_items: dict[str, list[str]] = defaultdict(list)
    for block, item in items:
        if item.get("visible"):
            region = item.get("tab_page") or item.get("canvas") or "Unassigned visible region"
            region_items[str(region)].append(f"{block['id']}.{item['name']}")
    tab_labels = {page.get("id"): page.get("label") or page.get("id") for page in module.get("tab_pages", [])}
    tab_canvases = {page.get("id"): page.get("canvas") for page in module.get("tab_pages", [])}
    for region, mappings in sorted(region_items.items()):
        label = tab_labels.get(region, region)
        region_rows.append(
            row(
                (
                    label,
                    region,
                    "Visible Oracle Forms region",
                    f"{len(mappings)} control(s)",
                    "Controls and CRUD are detailed in Sections 8 and 11.",
                )
            )
        )
    lines.extend(marker("legacy-regions", region_rows))

    lines.extend(
        [
            "",
            "## 4. Target Experience Overview",
            "",
            "Proposed treatment: provide one full-stack page that preserves the evidenced business outcomes, "
            "uses server-only Oracle access, and presents the discovered regions as accessible page sections, "
            "tabs, or grids. This proposal is pending target-requirements curation.",
            "",
            "### Target Page States",
            "",
            "| State | Entry condition | Display and allowed actions |",
            "| --- | --- | --- |",
            row(("Initial", "Page opens", "Show explicit search or load behavior after query-scope review.")),
            row(("Loading", "A server operation is running", "Prevent duplicate submissions and retain context.")),
            row(("Results/editing", "Data returned or a record is selected", "Expose only evidence-supported actions.")),
            row(("No results", "Query returns no rows", "Show an empty result without treating it as an error.")),
            row(("Validation/error", "A rule or operation fails", "Show safe message text and preserve unsaved input.")),
            "",
            "## 5. Module-Specific Behavior Change Register",
            "",
            "| Change ID | Capability | Legacy behavior | Proposed target behavior | Classification | Impact | Rationale | Approval status |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for capability, legacy, target in (
        ("Query", "Forms query properties and triggers", "Explicit server-side search preserving predicates and ordering"),
        ("Save", "Forms-managed validation and commit hooks", "Explicit save with bounded transaction behavior"),
        ("Navigation", "Canvases, tabs, buttons, and framework navigation", "Accessible sections, tabs, grids, and explicit actions"),
    ):
        lines.append(
            row(
                (
                    stable_spec_id("CHG", module_id, capability),
                    capability,
                    legacy,
                    target,
                    "reimagined presentation; preserve business outcomes",
                    "Requires business and UX review",
                    "Replace Oracle Forms interaction mechanics without silently dropping behavior",
                    "Proposed—not approved",
                )
            )
        )

    lines.extend(["", "## 6. Functional Requirements", ""])
    requirement_rows = [
        "| Requirement ID | Proposed requirement | Legacy evidence | Target treatment | Change ID |",
        "| --- | --- | --- | --- | --- |",
    ]
    fr_by_path: dict[str, str] = {}
    for path in paths:
        identifier = stable_spec_id("FR", module_id, path.get("operation"), entry_symbol(path))
        fr_by_path[str(path.get("path_id"))] = identifier
        requirement_rows.append(
            row(
                (
                    identifier,
                    f"The target shall preserve the source-backed {path.get('operation')} outcome of "
                    f"{entry_symbol(path)} and fail closed where an unresolved source could make the operation unsafe.",
                    f"{path.get('path_id')}; {locator_text(path)}; {path_summary(path)}",
                    "Server-only processing; proposed pending curation",
                    stable_spec_id(
                        "CHG",
                        module_id,
                        "Save" if path.get("operation") in {"insert", "update", "delete", "save", "validate"} else "Query",
                    ),
                )
            )
        )
    lines.extend(marker("functional-requirements", requirement_rows))

    lines.extend(
        [
            "",
            "## 7. Page Layout and Components",
            "",
            "| Region | Purpose | Proposed component | Source data/state | Responsive behavior |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for region, mappings in sorted(region_items.items()):
        lines.append(
            row(
                (
                    tab_labels.get(region, region),
                    f"Present {len(mappings)} evidenced control(s)",
                    "Section, tab panel, or data grid after UX review",
                    ", ".join(mappings[:12]) + (f"; +{len(mappings)-12} more" if len(mappings) > 12 else ""),
                    "Preserve labels, grouping, keyboard access, and validation association",
                )
            )
        )

    lines.extend(["", "## 8. Field and Control Specification", ""])
    field_body: list[str] = [
        "Legacy effective CRUD remains distinct from proposed target treatment. Every Forms item is also "
        "accounted for in Appendix B.",
        "",
    ]
    grouped: dict[tuple[str, str], list[tuple[Mapping[str, Any], Mapping[str, Any]]]] = defaultdict(list)
    technical: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    for block, item in items:
        if item.get("visible") and item.get("tab_page"):
            grouped[("Tab", str(item["tab_page"]))].append((block, item))
        elif item.get("visible") and item.get("canvas") and int(block.get("records_displayed") or 1) > 1:
            grouped[("Grid", str(block["id"]))].append((block, item))
        elif item.get("visible"):
            grouped[("Section", str(item.get("canvas") or "Unassigned"))].append((block, item))
        else:
            technical.append((block, item))
    field_header = (
        "| Field key | Display label | Description | Legacy mapping | Visual region | Database mapping | Data/control | "
        "Required and legacy effective Q/I/U | Lookup/default | Rules and logic | Target treatment | Evidence/gaps |"
    )
    field_divider = "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"
    for (kind, region), pairs in sorted(grouped.items(), key=lambda value: (value[0][0], value[0][1])):
        label = tab_labels.get(region, region) if kind == "Tab" else region
        field_body.extend([f"### {kind}: {label}", ""])
        if kind == "Grid":
            block = pairs[0][0]
            table_name = str(block.get("dml_data_name") or "").upper().split(".")[-1]
            ddl = objects.get(table_name, {})
            primary_key = next(
                (
                    constraint
                    for constraint in ddl.get("constraints", [])
                    if str(constraint.get("type") or "").lower() == "primary_key"
                ),
                None,
            )
            row_identity = (
                f"{primary_key.get('name') or 'primary key'} ({', '.join(primary_key.get('columns') or [])})"
                if primary_key
                else "Not established; see physical-mapping gaps"
            )
            grid_canvases = sorted({str(item.get("canvas") or "Unassigned") for _, item in pairs})
            field_body.extend(
                [
                    f"- Canvas: {', '.join(grid_canvases)}",
                    f"- DML target: {table_name or 'Not explicitly mapped'}",
                    f"- Rows displayed: {block.get('records_displayed') or 'Not established'}",
                    f"- Row identity: {row_identity}",
                    f"- Design row CRUD: {explicit_crud_cell(block.get('design_crud'), (('query', 'Q'), ('create', 'I'), ('update', 'U'), ('delete', 'D')))}",
                    f"- Effective row CRUD: {effective_crud_cell(block)}",
                    "- Row actions and validation: see Sections 11 and 12 and the operation-specific behavior paths.",
                    "",
                ]
            )
        field_body.extend([field_header, field_divider])
        for block, item in pairs:
            table_name = str(block.get("dml_data_name") or "").upper().split(".")[-1]
            column = item.get("database_column")
            physical = f"{table_name}.{column}" if table_name and column else "Not explicitly mapped"
            ddl = objects.get(table_name, {})
            ddl_column = next(
                (
                    record
                    for record in ddl.get("columns", [])
                    if str(record.get("name") or "").upper() == str(column or "").upper()
                ),
                None,
            )
            if ddl_column:
                physical += f" ({ddl_column.get('datatype') or ddl_column.get('data_type') or 'type unparsed'})"
            rules = []
            if block.get("where_clause"):
                rules.append(f"{block['id']}.WhereClause")
            if block.get("order_by"):
                rules.append(f"{block['id']}.OrderByClause")
            tab_page = str(item.get("tab_page") or "")
            canvas = str(item.get("canvas") or tab_canvases.get(tab_page) or "Unassigned")
            visual_region = f"canvas {canvas}"
            if tab_page:
                tab_label = tab_labels.get(tab_page, item.get("tab_page_label") or "label unresolved")
                visual_region += f"; tab {tab_page} ({tab_label})"
            elif canvas == "Unassigned":
                visual_region += "; no source canvas/tab assignment"
            field_body.append(
                row(
                    (
                        stable_spec_id("FLD", module_id, block.get("id"), item.get("name")),
                        item.get("prompt") or item.get("name"),
                        item.get("hint") or item.get("prompt") or "No business description in supplied source",
                        f"{block.get('id')}.{item.get('name')}",
                        visual_region,
                        physical,
                        f"{item.get('item_type') or 'Unknown'} / {item.get('data_type') or 'Unknown'}"
                        + (f" ({item.get('maximum_length')})" if item.get("maximum_length") else ""),
                        f"{'Required' if item.get('required') else 'Optional'}; "
                        f"design {explicit_crud_cell(item.get('design_crud'))}; "
                        f"effective {effective_crud_cell(item)}",
                        "; ".join(
                            value
                            for value in (
                                f"LOV {item.get('lov')}" if item.get("lov") else "",
                                f"default {item.get('initial_value')}" if item.get("initial_value") else "",
                            )
                            if value
                        )
                        or "—",
                        "; ".join(rules) or "See behavior-path and rule sections",
                        "Proposed equivalent control; editability requires target review",
                        item.get("evidence_id"),
                    )
                )
            )
        field_body.append("")
    field_body.extend(
        [
            "### Hidden And Technical Fields",
            "",
            "| Field key | Legacy item/column | Purpose | Legacy effective behavior | Needed in target | Treatment | Evidence/confidence |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for block, item in technical:
        technical_tab_page = str(item.get("tab_page") or "")
        technical_region = (
            f"canvas {item.get('canvas') or tab_canvases.get(technical_tab_page) or 'Unassigned'}"
        )
        if item.get("tab_page"):
            tab_page = str(item.get("tab_page"))
            technical_region += (
                f"; tab {tab_page} "
                f"({tab_labels.get(tab_page, item.get('tab_page_label') or 'label unresolved')})"
            )
        field_body.append(
            row(
                (
                    stable_spec_id("FLD", module_id, block.get("id"), item.get("name")),
                    f"{block.get('id')}.{item.get('name')} ({technical_region})",
                    item.get("hint") or item.get("prompt") or "Hidden/helper or visually unplaced item",
                    f"design {explicit_crud_cell(item.get('design_crud'))}; "
                    f"effective {effective_crud_cell(item)}",
                    "Only when a business effect is established",
                    "Keep server-side or exclude with explicit rationale",
                    item.get("evidence_id"),
                )
            )
        )
    lines.extend(marker("field-inventory", field_body))

    query_blocks = [block for block in module.get("blocks", []) if block.get("where_clause") or block.get("order_by")]
    lines.extend(
        [
            "",
            "## 9. Search Specification",
            "",
            "Search controls are proposals; the authoritative legacy retrieval predicates and ordering are preserved below.",
            "",
            "| Filter ID | Label | Source field/property | Control | Operator | Default | Normalization | Rationale | Review status |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for block in query_blocks:
        lines.append(
            row(
                (
                    stable_spec_id("FLT", module_id, block.get("id"), "query-scope"),
                    f"{block.get('id')} query scope",
                    f"{block.get('id')}.WhereClause",
                    "Explicit search criteria derived during curation",
                    "Preserve legacy predicate semantics",
                    "No implicit target default approved",
                    "Parameterized server-side evaluation",
                    "Retain legacy data scope without reproducing QBE syntax",
                    "Proposed",
                )
            )
        )
    lines.extend(
        [
            "",
            "## 10. Results and Selection Behavior",
            "",
            "| Block/grid | Source | Row identity | Default order | Selection/detail effect | Target review point |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for block in module.get("blocks", []):
        if block.get("database_block") or int(block.get("records_displayed") or 1) > 1:
            lines.append(
                row(
                    (
                        block.get("id"),
                        block.get("query_data_source") or block.get("dml_data_name") or "Control block",
                        "Use supplied PK/UK DDL where resolved; otherwise open mapping gap",
                        block.get("order_by") or "No explicit Forms order",
                        f"{block.get('records_displayed') or 1} record(s) displayed",
                        "Pagination, null display, refresh, and selection persistence require target review",
                    )
                )
            )

    lines.extend(["", "## 11. Actions and Buttons", ""])
    action_rows = [
        "| Action ID | Action | Availability | Legacy trigger/routine | Proposed target behavior | Server processing | Confirmation | Outcome/evidence |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for path in paths:
        action_rows.append(
            row(
                (
                    stable_spec_id("ACT", module_id, path.get("path_id")),
                    str(path.get("operation") or "action").title(),
                    path.get("reachability") or "reachable",
                    entry_symbol(path),
                    "Preserve source-backed outcome; resolve listed gaps before production parity",
                    ", ".join(path.get("database_writes") or path.get("database_reads") or ["No direct database effect established"]),
                    "Required when warning/confirmation paths are present"
                    if any(
                        check.get("effect") == "warning_confirmation"
                        for check in path.get("dependency_checks", [])
                        if isinstance(check, Mapping)
                    )
                    else "No confirmation established",
                    f"{path.get('path_id')}: {path_summary(path)}",
                )
            )
        )
    lines.extend(marker("actions", action_rows))

    lines.extend(["", "## 12. Business Rules and Validation", ""])
    rule_rows = [
        "| Rule ID | Trigger/condition | Rule/effect | Legacy behavior | Proposed target behavior | Enforcement | Error/message | Evidence path |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for path in paths:
        grouped_branches: dict[str, int] = defaultdict(int)
        for branch in path.get("branches", []):
            grouped_branches[str(branch.get("condition") or branch.get("kind") or "Unresolved branch")] += 1
        path_message_values = sorted(
            {
                str(message.get("code") or message.get("text"))
                for message in path.get("messages", [])
                if isinstance(message, Mapping) and (message.get("code") or message.get("text"))
            }
        )
        path_messages = ", ".join(path_message_values[:12])
        if len(path_message_values) > 12:
            path_messages += f"; +{len(path_message_values) - 12} more message outcome(s)"
        if not path_messages:
            path_messages = "Message outcome not established by this decoded path; review associated gaps"
        for condition, occurrence_count in sorted(grouped_branches.items()):
            rule_rows.append(
                row(
                    (
                        stable_spec_id("BR", module_id, path.get("path_id"), condition),
                        condition,
                        f"Preserve the decoded branch outcome in {entry_symbol(path)}",
                        f"{occurrence_count} occurrence(s) in the source-backed path",
                        "Equivalent server validation or processing branch; proposed pending curation",
                        "Server",
                        path_messages,
                        path.get("path_id"),
                    )
                )
            )
    if len(rule_rows) == 2:
        rule_rows.append(row(("—", "No decoded branch", "No source-backed module rule identified", "—", "No target rule proposed", "—", "—", "—")))
    lines.extend(marker("business-rules", rule_rows))
    lines.extend(["", "### Delete/Save Dependency Matrix", ""])
    dependency_rows = [
        "| Dependency ID | Operation | Legacy entry point/routine | Dependency object | DDL found | Legacy effect | Proposed target treatment | Message/error | Open gap |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for path in paths:
        for check in path.get("dependency_checks", []):
            object_name = str(check.get("object") or "Unresolved")
            path_gap_ids = list(path.get("gap_ids", []))
            path_gap_summary = ", ".join(path_gap_ids[:5])
            if len(path_gap_ids) > 5:
                path_gap_summary += f"; +{len(path_gap_ids) - 5} more gap(s)"
            dependency_rows.append(
                row(
                    (
                        stable_spec_id("DEP", module_id, path.get("path_id"), object_name, check.get("effect")),
                        path.get("operation"),
                        entry_symbol(path),
                        object_name,
                        "Yes" if object_name.upper().split(".")[-1] in objects else "No—see gap register",
                        check.get("effect") or "unresolved",
                        "Reproduce blocker/warning/cascade semantics server-side after review",
                        check.get("message_code") or check.get("message") or "Not established",
                        path_gap_summary or "—",
                    )
                )
            )
    if len(dependency_rows) == 2:
        dependency_rows.append(row(("—", "—", "—", "—", "—", "No reachable dependency check", "Not applicable", "—", "—")))
    lines.extend(marker("delete-save-dependencies", dependency_rows))

    lines.extend(["", "## 13. LOV and Lookup Specification", ""])
    lookup_rows = [
        "| Lookup ID | Field/action | Legacy LOV/record group/query | Search/display columns | Return values | Dependencies | Proposed target control | Empty/error behavior |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    record_groups = {str(record.get("id")): record for record in module.get("record_groups", [])}
    for lov in module.get("lovs", []):
        record_group = record_groups.get(str(lov.get("record_group"))) or {}
        returns = lov.get("return_mappings", [])
        lookup_rows.append(
            row(
                (
                    stable_spec_id("LOV", module_id, lov.get("id")),
                    lov.get("title") or lov.get("id"),
                    f"{lov.get('id')} / {lov.get('record_group')}; {record_group.get('query') or 'query not supplied'}",
                    ", ".join(str(mapping.get("column")) for mapping in returns if mapping.get("column")),
                    ", ".join(str(mapping.get("return_item")) for mapping in returns if mapping.get("return_item")),
                    ", ".join(
                        reference.get("object")
                        for reference in record_group.get("sql_references", [])
                        if reference.get("object")
                    ),
                    "Searchable combobox/dialog proposal",
                    "Preserve no-match and unresolved-message behavior",
                )
            )
        )
    if len(lookup_rows) == 2:
        lookup_rows.append(row(("—", "—", "No module-specific LOV found", "—", "—", "—", "Not applicable", "—")))
    lines.extend(marker("lookups", lookup_rows))

    lines.extend(["", "## 14. Workflow and State Model", ""])
    state_rows = [
        "| State/transition | Entry or trigger | Allowed action | Validation/guards | Side effects | Proposed target treatment |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for path in paths:
        state_rows.append(
            row(
                (
                    path.get("operation"),
                    entry_symbol(path),
                    path.get("reachability"),
                    f"{len(path.get('branches', []))} branch(es); {len(path.get('validations', []))} validation outcome(s)",
                    ", ".join(
                        str(effect.get("object") or effect.get("effect"))
                        for effect in path.get("side_effects", [])
                        if isinstance(effect, Mapping)
                    )
                    or "A side effect is not established by this decoded path; review associated gaps",
                    "Preserve observable outcome; do not infer additional workflow state",
                )
            )
        )
    lines.extend(marker("legacy-state-model", state_rows))

    lines.extend(["", "## 15. Data Model and Database Mapping", "", "### Object Usage", ""])
    object_rows = [
        "| Database object | Owner/synonym | Type | Operation | Module usage | Proposed target treatment | Evidence |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    read_objects = {name for path in paths for name in path.get("database_reads", [])}
    write_objects = {name for path in paths for name in path.get("database_writes", [])}
    for name, ddl in sorted(objects.items()):
        operations = []
        if name in read_objects:
            operations.append("read")
        if name in write_objects:
            operations.append("write")
        object_rows.append(
            row(
                (
                    name,
                    ddl.get("owner") or ddl.get("synonym_target") or "Owner unresolved",
                    ddl.get("type"),
                    ", ".join(operations) or "DDL dependency/reference",
                    "; ".join(path.get("path_id") for path in paths if name in path.get("database_reads", []) + path.get("database_writes", []))
                    or "Supplied recursive DDL",
                    "Use server-only Oracle access; preserve constraints and side effects",
                    ddl.get("source_path"),
                )
            )
        )
    lines.extend(marker("database-objects", object_rows))
    lines.extend(["", "### Keys, Relationships, And Constraints", ""])
    constraint_rows = [
        "| Object | Constraint/index | Columns | References/rule | Module relevance |",
        "| --- | --- | --- | --- | --- |",
    ]
    direct_constraint_objects = {
        str(block.get(key) or "").upper().split(".")[-1]
        for block in module.get("blocks", [])
        for key in ("query_data_source", "dml_data_name")
        if block.get(key)
    }
    for name, ddl in sorted(objects.items()):
        relevant_constraints = [
            constraint
            for constraint in ddl.get("constraints", [])
            if name in direct_constraint_objects
            or str(constraint.get("references_object") or "").upper().split(".")[-1] in direct_constraint_objects
        ]
        for constraint in relevant_constraints:
            definition = str(constraint.get("definition") or "")
            delete_action = constraint.get("on_delete")
            if not delete_action:
                delete_match = re.search(r"\bON\s+DELETE\s+(CASCADE|SET\s+NULL)\b", definition, re.I)
                delete_action = delete_match.group(1).lower().replace(" ", "_") if delete_match else None
            reference_rule = constraint.get("references_object") or definition or constraint.get("type")
            if constraint.get("references_object") and delete_action:
                reference_rule = (
                    f"{constraint.get('references_object')}; "
                    f"ON DELETE {str(delete_action).replace('_', ' ').upper()}"
                )
            constraint_rows.append(
                row(
                    (
                        name,
                        constraint.get("name") or constraint.get("type"),
                        constraint.get("columns"),
                        reference_rule,
                        (
                            f"Supplied DDL clause: ON DELETE {str(delete_action).replace('_', ' ').upper()}; "
                            "Forms checks/warnings and unresolved runtime behavior remain separate"
                            if delete_action
                            else "Database-enforced behavior; reconcile with application checks"
                        ),
                    )
                )
            )
    if len(constraint_rows) == 2:
        constraint_rows.append(row(("—", "No parsed constraint", "—", "—", "See DDL gaps")))
    lines.extend(marker("database-constraints", constraint_rows))
    lines.extend(["", "### Defaults, Audit, And Triggers", ""])
    defaults_body = [
        "| Object.column | Default/nullability | Audit/comment evidence | Source |",
        "| --- | --- | --- | --- |",
    ]
    for name, ddl in sorted(objects.items()):
        if name not in direct_constraint_objects:
            continue
        comments = {comment.get("column"): comment.get("text") for comment in ddl.get("comments", []) if isinstance(comment, Mapping)}
        for column in ddl.get("columns", []):
            if column.get("default") is not None or column.get("nullable") is False or comments.get(column.get("name")):
                defaults_body.append(
                    row(
                        (
                            f"{name}.{column.get('name')}",
                            f"default={column.get('default') or 'none'}; nullable={column.get('nullable')}",
                            comments.get(column.get("name")) or "No column comment",
                            ddl.get("source_path"),
                        )
                    )
                )
    if len(defaults_body) == 2:
        defaults_body.append(row(("—", "No default/nullability evidence parsed", "—", "—")))
    lines.extend(marker("database-defaults", defaults_body))

    lines.extend(["", "## 16. Data Retrieval and Processing Logic", ""])
    processing_body = [
        "Database access must run in server-only code. The following paths are the source-backed processing authority; "
        "unknown transaction or library behavior remains an explicit gap.",
        "",
        "| Path | Operation | Entry point | Inputs/scope | Reads | Writes | Branches/messages | Transaction | Outcome/gaps |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for path in paths:
        transaction = path.get("transaction") or {}
        gap_ids = list(path.get("gap_ids", []))
        gap_summary = ", ".join(gap_ids[:8])
        if len(gap_ids) > 8:
            gap_summary += f"; +{len(gap_ids) - 8} more gap(s)"
        processing_body.append(
            row(
                (
                    path.get("path_id"),
                    path.get("operation"),
                    entry_symbol(path),
                    path.get("user_scope") or path.get("forms_blocks") or "No user scope established",
                    path.get("database_reads"),
                    path.get("database_writes"),
                    f"{len(path.get('branches', []))} branch(es); {len(path.get('messages', []))} message(s)",
                    transaction,
                    path_summary(path) + (f"; gaps {gap_summary}" if gap_ids else ""),
                )
            )
        )
    lines.extend([""] + marker("retrieval-processing", processing_body))

    lines.extend(["", "## 17. Error and Message Catalogue", ""])
    message_rows = [
        "| Message ID | Legacy code/condition | Legacy message | Proposed target condition | Proposed display | Reachability/status | Evidence |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for message in messages:
        message_rows.append(
            row(
                (
                    stable_spec_id("MSG", module_id, message["code"], message["text"], message["condition"]),
                    f"{message['code']} / {message['condition']}",
                    message["text"],
                    "Equivalent source-backed validation or operation failure",
                    "Safe inline, summary, warning, or blocking error after UX review",
                    message["status"],
                    message["locator"],
                )
            )
        )
    if len(message_rows) == 2:
        message_rows.append(row(("—", "—", "Message evidence was not decoded from supplied readable source", "—", "—", "—", "—")))
    lines.extend(marker("messages", message_rows))

    lines.extend(
        [
            "",
            "## 18. Module-Specific Non-Functional Requirements",
            "",
            "No module-specific NFR is approved from source extraction alone. Application-wide security, accessibility, "
            "performance, observability, and deployment standards apply after requirements and architecture curation.",
            "",
            "## 19. Test and Acceptance Scenarios",
            "",
        ]
    )
    test_rows = [
        "| Test ID | Scenario | Preconditions | Steps | Expected result | Requirement/rule links |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for path in paths:
        test_rows.append(
            row(
                (
                    stable_spec_id("TC", module_id, path.get("path_id")),
                    f"{str(path.get('operation')).title()} through {entry_symbol(path)}",
                    "Synthetic fixture satisfies the source-backed preconditions; unresolved dependencies are isolated",
                    f"Invoke the proposed target equivalent of {entry_symbol(path)} and exercise success plus decoded branch/message outcomes",
                    f"Observable reads, writes, validation, warnings, and stop effects match {path.get('path_id')}; unresolved behavior fails closed",
                    fr_by_path.get(str(path.get("path_id"))),
                )
            )
        )
    lines.extend(marker("evidence-derived-tests", test_rows))

    lines.extend(["", "## 20. Traceability Matrix", ""])
    trace_rows = [
        "| Requirement/rule | Legacy evidence | Database evidence | Change | Processing/component | Tests |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for path in paths:
        trace_rows.append(
            row(
                (
                    fr_by_path.get(str(path.get("path_id"))),
                    f"{path.get('path_id')}; {locator_text(path)}",
                    ", ".join(path.get("database_reads", []) + path.get("database_writes", []))
                    or "Direct database object not established by this decoded path",
                    stable_spec_id(
                        "CHG",
                        module_id,
                        "Save" if path.get("operation") in {"insert", "update", "delete", "save", "validate"} else "Query",
                    ),
                    "Server-only operation handler plus page state",
                    stable_spec_id("TC", module_id, path.get("path_id")),
                )
            )
        )
    lines.extend(marker("traceability", trace_rows))

    lines.extend(
        [
            "",
            "## 21. Assumptions, Decisions, And Open Questions",
            "",
            "### Assumptions",
            "",
            "| ID | Assumption | Impact if false | Owner | Status |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for gap in gaps:
        assumption = gap.get("poc_assumption") or {}
        if assumption:
            lines.append(
                row(
                    (
                        assumption.get("assumption_id") or gap.get("assumption_or_decision_id"),
                        assumption.get("assumed_target_behavior"),
                        gap.get("affected_behavior") or gap.get("production_impact"),
                        assumption.get("validation_owner") or "Business and legacy SME",
                        assumption.get("status") or "proposed",
                    )
                )
            )
    lines.extend(
        [
            "",
            "### Decisions",
            "",
            "| ID | Decision | Rationale | Source/approver | Status |",
            "| --- | --- | --- | --- | --- |",
            row(("—", "No target decision is created by extraction.", "Legacy facts require governed curation.", "TBD", "Open")),
            "",
            "### Open Questions",
            "",
            "| ID | Question | Why it matters | Needed evidence/owner | Blocking level | Status |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for gap in gaps:
        lines.append(
            row(
                (
                    stable_spec_id("OQ", module_id, gap.get("gap_id")),
                    f"How should {gap.get('subject')} be resolved or deliberately dispositioned?",
                    gap.get("affected_behavior") or gap.get("expected_artifact_or_behavior"),
                    gap.get("recommended_action") or "Acquire the expected source or obtain an explicit target decision",
                    gap.get("production_impact") or "Review required",
                    gap.get("status"),
                )
            )
        )

    lines.extend(["", "## 22. Appendices", "", "### Appendix A. Source Evidence And Confidence", ""])
    source_rows = [
        "| Source ID | Source file | SHA-256 | Type/readability | Module role | Facts supported | Confidence/limitations | First/last run |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for source in sources:
        source_rows.append(
            row(
                (
                    source.get("source_id"),
                    source.get("relative_path"),
                    source.get("sha256"),
                    f"{source.get('source_role')} / {source.get('availability')} / {source.get('parse_status')}",
                    source.get("module_association"),
                    evidence_reference_summary(source.get("expected_by"))
                    if source.get("expected_by")
                    else "See normalized facts and behavior paths",
                    source.get("parse_warnings") or "No parser warning",
                    f"{source.get('first_seen_run_id')} / {source.get('last_seen_run_id')}",
                )
            )
        )
    lines.extend(marker("source-evidence", source_rows))

    lines.extend(["", "### Appendix B. Legacy Item Inventory And Coverage", ""])
    item_rows = [
        f"Source item count: {len(items)}. Every item below is represented exactly once.",
        "",
        "| Evidence ID | Block.item | Region/tab | Prompt | Item type | Visible | Database item | Column | Effective query/insert/update | Format/length | Target disposition | Confidence/gap |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for block, item in items:
        item_tab_page = str(item.get("tab_page") or "")
        item_canvas = str(item.get("canvas") or tab_canvases.get(item_tab_page) or "Unassigned")
        item_region = f"canvas {item_canvas}"
        if item_tab_page:
            item_region += (
                f"; tab {item_tab_page} "
                f"({tab_labels.get(item_tab_page, item.get('tab_page_label') or 'label unresolved')})"
            )
        elif item_canvas == "Unassigned":
            item_region += "; supporting technical field/no source assignment"
        item_rows.append(
            row(
                (
                    item.get("evidence_id"),
                    f"{block.get('id')}.{item.get('name')}",
                    item_region,
                    item.get("prompt"),
                    item.get("item_type"),
                    item.get("visible"),
                    item.get("database_item"),
                    item.get("database_column"),
                    f"design {explicit_crud_cell(item.get('design_crud'))}; "
                    f"effective {effective_crud_cell(item)}",
                    f"{item.get('format_mask') or '—'} / {item.get('maximum_length') or '—'}",
                    "Visible target control proposal" if item.get("visible") else "Technical/supporting; include only if behavior requires",
                    item.get("mapping_status") or "See gaps",
                )
            )
        )
    lines.extend(marker("item-coverage", item_rows))

    lines.extend(["", "### Appendix C. Trigger And Program Unit Inventory", ""])
    unit_rows = [
        "| Evidence/unit ID | Scope/object | Event or unit | Purpose | Calls/SQL | Business relevance | Target disposition | Source |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for unit in units:
        calls = sorted({str(call.get("to")) for call in unit.get("calls", []) if isinstance(call, Mapping) and call.get("to")})
        sql_objects = sorted({str(ref.get("object")) for ref in unit.get("sql_references", []) if isinstance(ref, Mapping) and ref.get("object")})
        unit_rows.append(
            row(
                (
                    unit.get("id"),
                    unit.get("scope"),
                    unit.get("name"),
                    f"{len(unit.get('branches', []))} branch(es); {len(unit.get('messages', []))} message(s)",
                    "; ".join(calls + sql_objects) or "No decoded call/SQL",
                    "Material when reachable from a behavior path; otherwise inventory evidence",
                    "Map observable outcome or retain as framework/unresolved evidence",
                    f"{unit.get('source_path')}#{unit.get('locator')}",
                )
            )
        )
    lines.extend(marker("code-units", unit_rows))

    lines.extend(["", "### Appendix D. Forms-To-Target Event Mapping", ""])
    event_rows = [
        "| Legacy event/mechanic | Observable outcome | Proposed target equivalent | Preserved/changed/excluded | Change ID/rationale | Evidence path |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for path in paths:
        event_rows.append(
            row(
                (
                    entry_symbol(path),
                    path_summary(path),
                    f"Server-side {path.get('operation')} handler plus accessible UI action/state",
                    "Preserve business outcome; replace Forms mechanic",
                    stable_spec_id(
                        "CHG",
                        module_id,
                        "Save" if path.get("operation") in {"insert", "update", "delete", "save", "validate"} else "Query",
                    ),
                    path.get("path_id"),
                )
            )
        )
    lines.extend(marker("event-mapping", event_rows))

    lines.extend(["", "### Appendix E. Excluded Framework Behavior", ""])
    framework_lines = [
        "Generic Oracle Forms, QMS, and OFG mechanics are not promoted to module-specific target behavior unless "
        "a reachable path establishes an observable business outcome.",
        "",
        "| Symbol | Treatment | Affected paths/gaps |",
        "| --- | --- | --- |",
    ]
    unresolved: dict[str, set[str]] = defaultdict(set)
    for path in paths:
        for symbol in path.get("unresolved_calls", []):
            unresolved[str(symbol)].add(str(path.get("path_id")))
    for symbol, affected in sorted(unresolved.items()):
        framework_lines.append(row((symbol, "Unresolved; do not assume no business effect", sorted(affected))))
    if len(framework_lines) == 4:
        framework_lines.append(row(("—", "No unresolved framework call recorded", "—")))
    lines.extend(marker("framework-exclusions", framework_lines))

    lines.extend(["", "### Appendix F. Database DDL Inventory", ""])
    ddl_rows = [
        "| DDL file | Object | Object type | Columns | Constraints | Dependencies | Comments | Completeness |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name, ddl in sorted(objects.items()):
        ddl_rows.append(
            row(
                (
                    ddl.get("source_path"),
                    ddl.get("qualified_name") or name,
                    ddl.get("type"),
                    len(ddl.get("columns", [])),
                    len(ddl.get("constraints", [])),
                    ddl.get("dependencies"),
                    len(ddl.get("comments", [])),
                    "Parsed supplied DDL; absence of related objects remains gapped",
                )
            )
        )
    lines.extend(marker("ddl-inventory", ddl_rows))

    lines.extend(["", "### Appendix G. Reference SQL And Technical Notes", ""])
    technical_lines = [
        "#### Prior-specification semantic coverage",
        "",
        "When a comparison specification is supplied, only anchors also supported by the current normalized evidence "
        "are carried into this table. Target-only IDs or unsupported claims are not treated as legacy facts.",
        "",
        "| Prior source-backed anchor | Current support/disposition |",
        "| --- | --- |",
    ]
    if comparison_anchors:
        technical_lines.extend(row((record["anchor"], record["support"])) for record in comparison_anchors)
    else:
        technical_lines.append(row(("No comparison oracle supplied or no source-supported anchors found", "Not applicable")))
    technical_lines.extend(["", "#### Query properties", ""])
    for block in query_blocks:
        technical_lines.extend(
            [
                f"- `{block.get('id')}.WhereClause`: {markdown_cell(block.get('where_clause'))}",
                f"- `{block.get('id')}.OrderByClause`: {markdown_cell(block.get('order_by'))}",
            ]
        )
    lines.extend(marker("technical-notes", technical_lines))

    lines.extend(
        [
            "",
            "### Appendix H. Glossary",
            "",
            "| Term | Meaning |",
            "| --- | --- |",
            row(("Forms block", "Oracle Forms data/control grouping; not necessarily a visual region")),
            row(("Effective CRUD", "Design-time CRUD reconciled with known inherited/runtime overrides")),
            row(("Comparison oracle", "Prior specification used non-mutatively to detect loss of source-backed semantic anchors")),
            row(("Registered gap", "Known missing, unreadable, conflicting, or unresolved evidence with explicit impact")),
            "",
            "### Appendix I. Extraction Coverage And Missing Source Register",
            "",
            "#### Coverage Summary",
            "",
        ]
    )
    coverage_rows = [
        "| Coverage dimension | Total | Classified/resolved | Open/unknown | Excluded | Status | Evidence model reference |",
        "| --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for metric in coverage:
        coverage_rows.append(
            row(
                (
                    metric.get("dimension") or metric.get("metric_id"),
                    metric.get("denominator"),
                    metric.get("numerator"),
                    metric.get("unresolved_count"),
                    metric.get("exclusions"),
                    metric.get("status"),
                    f"{metric.get('metric_id')}: {len(metric.get('record_ids', []))} measured record(s); "
                    f"unresolved={evidence_reference_summary(metric.get('unresolved_record_ids'), limit=60)}",
                )
            )
        )
    lines.extend(marker("extraction-coverage", coverage_rows))
    lines.extend(["", "#### Missing Source And Evidence Gaps", ""])
    gap_rows = [
        "| Gap ID | Gap type | Expected artifact/module/library/object/symbol | Discovery evidence | Readability/status | Behavior/operation affected | Current fallback evidence | Confidence impact | POC impact | Production-parity impact | Acquisition/validation action | Lifecycle status | Opened/resolved run |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for gap in gaps:
        gap_rows.append(
            row(
                (
                    gap.get("gap_id"),
                    gap.get("gap_kind"),
                    gap.get("subject") or gap.get("expected_artifact_or_behavior"),
                    gap.get("why_expected") or evidence_reference_summary(gap.get("expected_by_locators")),
                    gap.get("source_status") or gap.get("status"),
                    gap.get("affected_behavior") or gap.get("affected_operations"),
                    evidence_reference_summary(gap.get("available_fallback_evidence"))
                    if gap.get("available_fallback_evidence")
                    else "Fallback evidence not available",
                    gap.get("confidence_impact") or "Unresolved",
                    gap.get("poc_impact"),
                    gap.get("production_impact"),
                    gap.get("recommended_action"),
                    gap.get("status"),
                    f"{gap.get('first_seen_run_id')} / {gap.get('last_changed_run_id')}",
                )
            )
        )
    if len(gap_rows) == 2:
        gap_rows.append(row(("—", "None", "No open gap", "—", "resolved", "—", "—", "—", "none", "none", "—", "resolved", run.get("run_id"))))
    lines.extend(marker("missing-sources", gap_rows))

    lines.extend(["", "### Appendix J. Incremental Extraction History", ""])
    history_rows = [
        "| Run ID | Date | Mode | Added/changed/removed sources | Affected evidence slices/spec sections | Gaps opened/narrowed/resolved/reopened | Evidence fingerprint | Validation result |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        row(
            (
                run.get("run_id"),
                generated_date,
                extraction_mode,
                count_summary(evidence.get("incremental", {}).get("change_set"))
                if evidence.get("incremental", {}).get("change_set")
                else "Fresh complete selected bundle",
                count_summary(evidence.get("incremental", {}).get("impacted"))
                if evidence.get("incremental", {}).get("impacted")
                else "All generated evidence regions",
                f"{len(open_gaps)} active / {len(gaps) - len(open_gaps)} resolved",
                run.get("evidence_sha256"),
                evidence.get("self_check", {}).get("status") or "pending rendered-document validation",
            )
        ),
    ]
    lines.extend(marker("incremental-history", history_rows))
    lines.append("")
    specification = "\n".join(lines)
    errors = validate_markdown_contract(
        evidence,
        specification,
        comparison_spec_text=comparison_spec_text,
    )
    if errors:
        raise ValueError("Rendered Markdown contract failed:\n- " + "\n- ".join(errors))
    return specification


# Evidence-only rendering contract (v1.5).
#
# The earlier renderer deliberately remains above so historical generated files
# can still be understood while the workflow transitions.  The public names at
# the end of this module point to the evidence-only contract below.


def _semantic_slug(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(value or "").casefold()).strip("-")
    return text or "unnamed"


def _local_key(module_id: str, kind: str, value: Any) -> str:
    return f"MOD-{module_id}#{kind}.{_semantic_slug(value)}"


def _json_summary(value: Any, limit: int | None = None) -> str:
    """Render durable normalized evidence without silently discarding detail."""
    if value in (None, "", [], {}):
        return "—"
    if isinstance(value, Mapping):
        machine_key = re.compile(
            r"^(?:id|source_id|fact_id|path_id|gap_id|evidence_id|branch_id|message_id|unit_id|metric_id)$|"
            r"(?:_ids|_id)$",
            re.I,
        )
        text = "; ".join(
            f"{key}={_json_summary(item)}"
            for key, item in value.items()
            if not machine_key.search(str(key))
        )
    elif isinstance(value, (list, tuple, set)):
        text = "; ".join(_json_summary(item) for item in value)
    else:
        text = " ".join(str(value).replace("\r", " ").replace("\n", " ").split())
    if limit is None or len(text) <= limit:
        return text
    return text[: limit - 12] + "… [truncated]"


def _object_name(value: Any) -> str:
    return str(value or "").upper().split(".")[-1]


def _physical_column(
    objects: Mapping[str, Mapping[str, Any]],
    table_name: Any,
    column_name: Any,
) -> Mapping[str, Any] | None:
    table = objects.get(_object_name(table_name))
    if not table:
        return None
    wanted = _object_name(column_name)
    return next(
        (
            column
            for column in table.get("columns", [])
            if isinstance(column, Mapping) and _object_name(column.get("name")) == wanted
        ),
        None,
    )


def _physical_mapping_text(
    objects: Mapping[str, Mapping[str, Any]],
    table_name: Any,
    column_name: Any,
) -> str:
    table = _object_name(table_name)
    column = _object_name(column_name)
    if not table or not column:
        return "not applicable"
    ddl_column = _physical_column(objects, table, column)
    if not ddl_column:
        return f"{table}.{column} (DDL definition not resolved)"
    data_type = ddl_column.get("data_type") or ddl_column.get("datatype") or "DDL type not parsed"
    return f"{table}.{column} ({data_type})"


def _on_delete_effect(constraint: Mapping[str, Any]) -> str:
    explicit = str(constraint.get("on_delete") or "").replace("_", " ").strip()
    if explicit:
        return explicit.upper()
    match = re.search(
        r"\bON\s+DELETE\s+(CASCADE|SET\s+NULL)\b",
        str(constraint.get("definition") or ""),
        re.I,
    )
    return match.group(1).upper() if match else "NOT STATED / RESTRICTIVE"


def _reverse_foreign_keys(
    objects: Mapping[str, Mapping[str, Any]],
    target_names: Iterable[Any],
) -> list[tuple[str, Mapping[str, Any]]]:
    targets = {_object_name(name) for name in target_names if name}
    records: list[tuple[str, Mapping[str, Any]]] = []
    for object_name, record in objects.items():
        for constraint in record.get("constraints", []):
            if (
                isinstance(constraint, Mapping)
                and str(constraint.get("type") or "").lower() == "foreign_key"
                and _object_name(constraint.get("references_object")) in targets
            ):
                records.append((object_name, constraint))
    return sorted(
        records,
        key=lambda pair: (
            _object_name(pair[1].get("references_object")),
            pair[0],
            str(pair[1].get("name") or ""),
        ),
    )


def _unit_source_blocks(units: Sequence[Mapping[str, Any]]) -> list[str]:
    """Render exact decoded source while keeping the long appendix navigable."""
    rendered: list[str] = []
    for unit in units:
        code = (
            str(unit.get("code") or "")
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .strip()
        )
        if not code:
            continue
        name = str(unit.get("name") or unit.get("id") or "unnamed unit")
        scope = str(unit.get("scope") or unit.get("kind") or "unknown scope")
        locator = str(unit.get("locator") or unit.get("source_path") or "source locator unavailable")
        digest = str(unit.get("code_sha256") or hashlib.sha256(code.encode("utf-8")).hexdigest())
        fence = "~~~"
        while fence in code:
            fence += "~"
        rendered.extend(
            [
                "<details>",
                f"<summary><code>{markdown_cell(name)}</code> — {markdown_cell(scope)}</summary>",
                "",
                f"Source locator: `{markdown_cell(locator)}`  ",
                f"Decoded source SHA-256: `{markdown_cell(digest)}`",
                "",
                f"{fence}sql",
                code,
                fence,
                "",
                "</details>",
                "",
            ]
        )
    return rendered


def _package_names(module_id: str, output_path: Path | None) -> dict[str, str]:
    master = output_path.name if output_path else f"{module_id.lower()}-legacy-evidence-specification.md"
    prefix = module_id.lower()
    return {
        "master": master,
        "operation_details": f"{prefix}-operation-details.md",
        "decoded_source": f"{prefix}-decoded-source.md",
        "database_reference": f"{prefix}-database-reference.md",
    }


def _reference_frontmatter(
    evidence: Mapping[str, Any],
    *,
    reference_kind: str,
    parent_name: str,
) -> list[str]:
    module = evidence["modules"][0]
    run = evidence["run"]
    module_id = str(module["module_id"]).upper()
    return [
        "---",
        "artifact_kind: legacy_evidence_reference",
        f"reference_kind: {reference_kind}",
        f"module_id: {module_id}",
        f"module_evidence_id: MOD-{module_id}",
        f"evidence_fingerprint: {run.get('evidence_sha256')}",
        f"extraction_run_id: {run.get('run_id')}",
        f"parent_specification: {parent_name}",
        "---",
        "",
    ]


def _compact_count(value: Any, label: str) -> str:
    if value in (None, "", [], {}):
        return f"0 {label}"
    if isinstance(value, Mapping):
        return f"{len(value)} {label}"
    if isinstance(value, (list, tuple, set)):
        return f"{len(value)} {label}"
    return f"1 {label}"


def _operation_effect_summary(path: Mapping[str, Any]) -> str:
    effects: list[str] = []
    reads = path.get("database_reads") or []
    writes = path.get("database_writes") or path.get("database_effects") or []
    dependencies = path.get("dependency_checks") or []
    if reads:
        effects.append(_compact_count(reads, "database read(s)"))
    if writes:
        effects.append(_compact_count(writes, "database write/effect(s)"))
    if dependencies:
        effects.append(_compact_count(dependencies, "dependency check(s)"))
    if path.get("transaction"):
        effects.append("transaction behavior present")
    return "; ".join(effects) or "Database effect not established"


def _operation_outcome_summary(path: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for key, label in (
        ("messages", "message(s)"),
        ("stop_effects", "stop effect(s)"),
        ("outcomes", "outcome(s)"),
        ("side_effects", "side effect(s)"),
    ):
        value = path.get(key)
        if value:
            parts.append(_compact_count(value, label))
    return "; ".join(parts) or "Explicit message or outcome not established"


def _operation_anchor(path: Mapping[str, Any]) -> str:
    return "operation-" + _semantic_slug(
        f"{path.get('operation')}-{entry_symbol(path)}-{path.get('path_id') or ''}"
    )


def _render_operation_reference(
    evidence: Mapping[str, Any],
    paths: Sequence[Mapping[str, Any]],
    names: Mapping[str, str],
) -> str:
    module = evidence["modules"][0]
    module_id = str(module["module_id"]).upper()
    lines = _reference_frontmatter(
        evidence,
        reference_kind="operation_details",
        parent_name=names["master"],
    )
    lines.extend(
        [
            f"# {module_id} - Exhaustive Operation Evidence",
            "",
            f"This child document preserves the complete normalized detail for all {len(paths)} operation paths. "
            f"Return to the [master specification]({names['master']}).",
            "",
        ]
    )
    for path in paths:
        operation = str(path.get("operation") or "unknown")
        entry = entry_symbol(path)
        lines.extend(
            [
                f"## {operation} - {entry}",
                f'<a id="{_operation_anchor(path)}"></a>',
                "",
                "| Attribute | Evidence |",
                "| --- | --- |",
                row(("Operation", operation)),
                row(("Entry point", entry)),
                row(("Source", locator_text(path))),
                row(("Confidence", path.get("confidence") or "unknown")),
                row(("Preconditions", _compact_count(path.get("preconditions"), "record(s)"))),
                row(("Call chain", _compact_count(path.get("call_chain") or path.get("calls"), "call record(s)"))),
                row(("Database reads", _compact_count(path.get("database_reads"), "read record(s)"))),
                row(("Database writes/effects", _compact_count(path.get("database_writes") or path.get("database_effects"), "write/effect record(s)"))),
                row(("Dependency checks", _compact_count(path.get("dependency_checks"), "check(s)"))),
                row(("Messages", _compact_count(path.get("messages"), "message(s)"))),
                row(("Stop effects", _compact_count(path.get("stop_effects"), "stop effect(s)"))),
                row(("Outcomes / side effects", _compact_count(path.get("outcomes") or path.get("side_effects"), "record(s)"))),
                row(("Gap IDs", _json_summary(path.get("gap_ids")))),
                "",
                "<details>",
                "<summary>Complete normalized operation record</summary>",
                "",
                "~~~json",
                json.dumps(path, indent=2, ensure_ascii=False),
                "~~~",
                "",
                "</details>",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _render_decoded_source_reference(
    evidence: Mapping[str, Any],
    units: Sequence[Mapping[str, Any]],
    names: Mapping[str, str],
) -> str:
    module_id = str(evidence["modules"][0]["module_id"]).upper()
    lines = _reference_frontmatter(
        evidence,
        reference_kind="decoded_source",
        parent_name=names["master"],
    )
    lines.extend(
        [
            f"# {module_id} - Decoded Trigger And Program Unit Source",
            "",
            f"This child document preserves all {len(units)} decoded unit records and every exact source body. "
            f"Return to the [master specification]({names['master']}).",
            "",
            "| Scope / unit | Kind | Calls | SQL / messages / effects | Source locator |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for unit in units:
        lines.append(
            row(
                (
                    unit.get("name") or unit.get("id"),
                    unit.get("kind") or unit.get("type"),
                    _json_summary(unit.get("calls")),
                    _json_summary(
                        {
                            "reads": unit.get("database_reads"),
                            "writes": unit.get("database_writes"),
                            "messages": unit.get("messages"),
                            "builtins": unit.get("forms_builtins"),
                        }
                    ),
                    unit.get("locator") or unit.get("source_path"),
                )
            )
        )
    if not units:
        lines.append(row(("None decoded", "-", "-", "-", "-")))
    lines.extend(["", "## Exact Decoded Source", "", *_unit_source_blocks(units)])
    return "\n".join(lines).rstrip() + "\n"


def _render_database_reference(
    evidence: Mapping[str, Any],
    objects: Mapping[str, Mapping[str, Any]],
    names: Mapping[str, str],
) -> str:
    module_id = str(evidence["modules"][0]["module_id"]).upper()
    lines = _reference_frontmatter(
        evidence,
        reference_kind="database_reference",
        parent_name=names["master"],
    )
    lines.extend(
        [
            f"# {module_id} - Exhaustive Database Reference",
            "",
            f"This child document preserves complete parsed DDL evidence for {len(objects)} relevant objects. "
            f"Return to the [master specification]({names['master']}).",
            "",
        ]
    )
    for name, record in sorted(objects.items()):
        lines.extend(
            [
                f"## {name}",
                "",
                "| Attribute | Evidence |",
                "| --- | --- |",
                row(("Object type", record.get("type"))),
                row(("Source", record.get("source_path") or record.get("relative_path"))),
                row(("Columns", _compact_count(record.get("columns"), "column record(s)"))),
                row(("Constraints", _compact_count(record.get("constraints"), "constraint record(s)"))),
                row(("Dependencies", _compact_count(record.get("dependencies"), "dependency record(s)"))),
                "",
                "<details>",
                "<summary>Complete normalized DDL record</summary>",
                "",
                "~~~json",
                json.dumps(record, indent=2, ensure_ascii=False),
                "~~~",
                "",
                "</details>",
                "",
            ]
        )
    if not objects:
        lines.append("No relevant DDL object was resolved from the supplied source.")
    return "\n".join(lines).rstrip() + "\n"


def _rule_message_bindings(
    path: Mapping[str, Any],
    units: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Associate messages to the active decoded IF/ELSIF branch in the same unit."""
    branches = [record for record in path.get("branches", []) if isinstance(record, Mapping)]
    messages = [record for record in path.get("messages", []) if isinstance(record, Mapping)]
    assignments: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    assigned_messages: set[str] = set()
    units_by_locator = {
        str(unit.get("locator") or ""): unit
        for unit in units
        if unit.get("locator") and unit.get("code")
    }
    for locator in sorted({str(branch.get("locator") or "") for branch in branches if branch.get("locator")}):
        unit = units_by_locator.get(locator)
        if not unit:
            continue
        unit_branches = [branch for branch in branches if str(branch.get("locator") or "") == locator]
        unit_messages = [message for message in messages if str(message.get("locator") or "") == locator]
        branches_by_line: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
        messages_by_line: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
        for branch in unit_branches:
            if isinstance(branch.get("code_line"), int):
                branches_by_line[int(branch["code_line"])].append(branch)
        for message in unit_messages:
            if isinstance(message.get("code_line"), int):
                messages_by_line[int(message["code_line"])].append(message)
        active_branches: list[str | None] = []
        for line_number, source_line in enumerate(str(unit.get("code") or "").splitlines(), start=1):
            normalized_line = re.sub(r"--.*$", "", source_line).upper()
            if re.search(r"\bEND\s+IF\b", normalized_line) and active_branches:
                active_branches.pop()
            line_branches = branches_by_line.get(line_number, [])
            elsif_branches = [branch for branch in line_branches if str(branch.get("kind") or "").lower() == "elsif"]
            if elsif_branches:
                if active_branches:
                    active_branches[-1] = str(elsif_branches[-1].get("branch_id") or id(elsif_branches[-1]))
            elif re.search(r"(?<!ELS)\bELSE\b", normalized_line) and active_branches:
                active_branches[-1] = None
            for branch in line_branches:
                if str(branch.get("kind") or "").lower() == "if":
                    active_branches.append(str(branch.get("branch_id") or id(branch)))
            for message in messages_by_line.get(line_number, []):
                if not active_branches or active_branches[-1] is None:
                    continue
                branch_key = str(active_branches[-1])
                assignments[branch_key].append(message)
                assigned_messages.add(str(message.get("id") or message.get("message_id") or id(message)))

    stop_by_code: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for stop in path.get("stop_effects", []):
        if isinstance(stop, Mapping) and stop.get("message_code") not in (None, ""):
            stop_by_code[str(stop.get("message_code"))].append(stop)

    records: list[dict[str, Any]] = []
    for branch in branches:
        branch_key = str(branch.get("branch_id") or id(branch))
        bound = assignments.get(branch_key, [])
        effects = [effect for message in bound for effect in stop_by_code.get(str(message.get("code") or ""), [])]
        records.append(
            {
                "operation": path.get("operation") or "unknown",
                "entry": entry_symbol(path),
                "condition": branch.get("condition") or branch.get("kind") or "Condition not decoded",
                "messages": bound,
                "effects": effects,
                "source": f"{branch.get('source_path') or ''} :: {branch.get('locator') or ''} line {branch.get('code_line') or '?'}",
                "association": "active decoded IF/ELSIF branch in the same unit" if bound else "message association not established",
            }
        )
    for message in messages:
        message_key = str(message.get("id") or message.get("message_id") or id(message))
        if message_key in assigned_messages:
            continue
        records.append(
            {
                "operation": path.get("operation") or "unknown",
                "entry": entry_symbol(path),
                "condition": "Condition association not established",
                "messages": [message],
                "effects": stop_by_code.get(str(message.get("code") or ""), []),
                "source": f"{message.get('source_path') or ''} :: {message.get('locator') or ''} line {message.get('code_line') or '?'}",
                "association": "unbound message preserved",
            }
        )
    validation_codes = {
        str(message.get("code") or "")
        for message in messages
        if message.get("code") not in (None, "")
    }
    for validation in path.get("validations", []):
        if not isinstance(validation, Mapping) or str(validation.get("code") or "") in validation_codes:
            continue
        records.append(
            {
                "operation": path.get("operation") or "unknown",
                "entry": entry_symbol(path),
                "condition": "Validation condition not structurally associated",
                "messages": [validation],
                "effects": stop_by_code.get(str(validation.get("code") or ""), []),
                "source": locator_text(path),
                "association": "validation preserved without inferred condition",
            }
        )
    return records


def _screenshot_markdown(
    screenshot: Mapping[str, Any],
    module_id: str,
    *,
    source_root: Path | None,
    output_path: Path | None,
) -> str:
    raw = str(screenshot.get("path") or "")
    link = raw.replace("\\", "/")
    if source_root is not None and output_path is not None and raw:
        absolute = (source_root / Path(raw)).resolve()
        link = os.path.relpath(absolute, output_path.resolve().parent).replace("\\", "/")
    link = quote(link, safe="/._-~")
    return f"![{module_id} legacy screenshot]({link})"


def _field_group(block: Mapping[str, Any], item: Mapping[str, Any]) -> tuple[str, str]:
    if item.get("tab_page"):
        return "tab", str(item["tab_page"])
    if int(block.get("records_displayed") or 0) > 1:
        return "grid", str(block.get("id") or "records")
    return "section", str(item.get("canvas") or block.get("id") or "unplaced")


def validate_evidence_markdown_contract(
    evidence: Mapping[str, Any],
    specification: str,
    *,
    comparison_spec_text: str | None = None,
    package_documents: Mapping[str, str] | None = None,
) -> list[str]:
    """Validate exhaustive evidence coverage without requiring row-level IDs."""
    errors: list[str] = []
    package_documents = dict(package_documents or {})
    package_text = "\n".join([specification, *package_documents.values()])
    template_sections, template_markers = _template_contract()
    section_ids = re.findall(r"^##\s+(\d+)\.", specification, re.M)
    missing_sections = [section for section in CANONICAL_SECTIONS if section not in section_ids]
    if template_sections != CANONICAL_SECTIONS:
        errors.append(f"Template section contract changed unexpectedly: {template_sections}.")
    if missing_sections:
        errors.append("Rendered specification is missing canonical sections: " + ", ".join(missing_sections) + ".")
    appendix_ids = re.findall(r"^###\s+Appendix\s+([A-J])\.", specification, re.M)
    missing_appendices = [appendix for appendix in CANONICAL_APPENDICES if appendix not in appendix_ids]
    if missing_appendices:
        errors.append("Rendered specification is missing appendices: " + ", ".join(missing_appendices) + ".")
    marker_keys = [match.group("key") for match in MARKER_RE.finditer(specification)]
    for key in template_markers:
        if marker_keys.count(key) != 1:
            errors.append(f"Rendered specification requires exactly one balanced marker region for {key}.")
    if "[truncated]" in package_text.casefold():
        errors.append(
            "Rendered specification contains a truncation marker; durable evidence must be rendered losslessly."
        )
    if re.search(r"\+\d+\s+more\b", package_text, re.I):
        errors.append(
            "Rendered specification contains a lossy '+N more' placeholder; render every durable evidence member."
        )

    module = evidence["modules"][0]
    module_id = str(module["module_id"]).upper()
    objects = _database_objects(evidence)
    if _frontmatter_value(specification, "artifact_kind") != "legacy_evidence_specification":
        errors.append("Rendered specification must declare artifact_kind: legacy_evidence_specification.")
    if _frontmatter_value(specification, "module_id") != module_id:
        errors.append("Rendered specification module_id does not match the selected evidence module.")
    if _frontmatter_value(specification, "module_evidence_id") != f"MOD-{module_id}":
        errors.append("Rendered specification has an invalid module_evidence_id.")
    fingerprint = str(evidence.get("run", {}).get("evidence_sha256") or "")
    if _frontmatter_value(specification, "evidence_fingerprint") != fingerprint:
        errors.append("Rendered specification evidence_fingerprint does not match the evidence model.")

    for block, item in _all_items(module):
        locator = f"{block.get('id')}.{item.get('name')}"
        if locator not in specification:
            errors.append(f"Forms item {locator} is absent from the rendered specification.")
        if item.get("database_column"):
            table_name = block.get("dml_data_name") or block.get("query_data_source")
            ddl_column = _physical_column(objects, table_name, item.get("database_column"))
            if ddl_column:
                typed_mapping = _physical_mapping_text(
                    objects,
                    table_name,
                    item.get("database_column"),
                )
                if typed_mapping not in specification:
                    errors.append(
                        f"Typed physical mapping is absent for {locator}: {typed_mapping}."
                    )
    for collection, label in (
        ("windows", "Forms window"),
        ("canvases", "Forms canvas"),
        ("tab_pages", "Forms tab page"),
    ):
        for record in module.get(collection, []):
            identifier = str(record.get("id") or "")
            if identifier and identifier not in specification:
                errors.append(f"{label} {identifier} is absent from the rendered specification.")
    persistence_objects = {
        _object_name(block.get("dml_data_name") or block.get("query_data_source"))
        for block in module.get("blocks", [])
        if block.get("block_role") == "database_persistence"
    }
    for referencing_object, constraint in _reverse_foreign_keys(
        objects,
        persistence_objects,
    ):
        expected_tokens = (
            referencing_object,
            str(constraint.get("name") or constraint.get("type") or ""),
            _object_name(constraint.get("references_object")),
            _on_delete_effect(constraint),
        )
        missing_tokens = [token for token in expected_tokens if token and token not in package_text]
        if missing_tokens:
            errors.append(
                "Inbound foreign-key evidence is incomplete for "
                f"{referencing_object}/{constraint.get('name') or constraint.get('type')}: "
                + ", ".join(missing_tokens)
                + "."
            )
    rendered_source_blocks = {
        match.group("hash").lower(): match.group("code")
        for match in re.finditer(
            r"Decoded source SHA-256:\s*`(?P<hash>[0-9a-fA-F]{64})`"
            r".*?\n(?P<fence>~{3,})sql\r?\n(?P<code>.*?)\r?\n(?P=fence)",
            package_text,
            re.S,
        )
    }
    for unit in _all_units(module):
        code = (
            str(unit.get("code") or "")
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .strip()
        )
        digest = str(unit.get("code_sha256") or hashlib.sha256(code.encode("utf-8")).hexdigest()).lower()
        rendered_code = rendered_source_blocks.get(digest)
        if code and rendered_code != code:
            errors.append(
                "Exact decoded source is absent for "
                f"{unit.get('name') or unit.get('id')} at "
                f"{unit.get('locator') or unit.get('source_path')}."
            )
    for path in _operation_paths(evidence):
        operation = str(path.get("operation") or "unknown")
        entry = entry_symbol(path)
        if operation not in package_text or entry not in package_text:
            errors.append(f"Behavior entry {operation}/{entry} is absent from the rendered specification.")
    for gap in evidence.get("artifacts", {}).get("gaps", {}).get("records", []):
        subject = str(gap.get("subject") or gap.get("expected_artifact_or_behavior") or "")
        if subject and subject not in package_text:
            errors.append(f"Gap subject is absent from the rendered specification: {subject}.")
    for source in evidence.get("artifacts", {}).get("source_inventory", {}).get("records", []):
        relative_path = str(source.get("relative_path") or "")
        if relative_path and relative_path not in package_text:
            errors.append(f"Source path {relative_path} is absent from the rendered specification.")
    for screenshot in module.get("runtime_screenshots", []):
        path = str(screenshot.get("path") or "")
        encoded_name = quote(Path(path).name, safe="._-~")
        if path and encoded_name not in specification:
            errors.append(f"Screenshot {path} is not linked from the rendered specification.")

    prohibited_patterns = {
        "target requirement IDs": r"\b(?:CHG|FR|FLD|BR|MSG|TC|OQ)-" + re.escape(module_id) + r"-[A-F0-9]{10}\b",
        "target design section": r"^##\s+\d+\.\s+Target\b",
        "POC readiness": r"\bpoc_forward_engineering_readiness\b",
    }
    for label, pattern in prohibited_patterns.items():
        if re.search(pattern, specification, re.I | re.M):
            errors.append(f"Rendered evidence specification contains prohibited {label}.")
    normalized_package_lines = {
        _normalize_executable_statement(line)
        for line in package_text.splitlines()
        if line.strip()
    }
    for record in _supported_comparison_anchors(evidence, comparison_spec_text):
        if record.get("match_kind") == "source_statement":
            normalized_anchor = _normalize_executable_statement(record["anchor"])
            present = any(normalized_anchor in line for line in normalized_package_lines)
        else:
            present = record["anchor"].upper() in package_text.upper()
        if not present:
            errors.append(f"Source-supported comparison anchor was lost: {record['anchor']}.")
    if package_documents:
        expected_kinds = {
            "operation_details": "operation_details",
            "decoded_source": "decoded_source",
            "database_reference": "database_reference",
        }
        for key, expected_kind in expected_kinds.items():
            text = package_documents.get(key, "")
            if not text:
                errors.append(f"Evidence package is missing required child document: {key}.")
                continue
            if _frontmatter_value(text, "artifact_kind") != "legacy_evidence_reference":
                errors.append(f"Evidence child {key} has an invalid artifact_kind.")
            if _frontmatter_value(text, "reference_kind") != expected_kind:
                errors.append(f"Evidence child {key} has an invalid reference_kind.")
            if _frontmatter_value(text, "module_id") != module_id:
                errors.append(f"Evidence child {key} does not match module {module_id}.")
            if _frontmatter_value(text, "evidence_fingerprint") != fingerprint:
                errors.append(f"Evidence child {key} does not match the package fingerprint.")
        operation_reference = package_documents.get("operation_details", "")
        for path in _operation_paths(evidence):
            serialized = json.dumps(path, indent=2, ensure_ascii=False)
            if serialized not in operation_reference:
                errors.append(
                    f"Complete normalized operation record is absent for {path.get('operation')}/{entry_symbol(path)}."
                )
        database_reference = package_documents.get("database_reference", "")
        for object_name, record in sorted(objects.items()):
            serialized = json.dumps(record, indent=2, ensure_ascii=False)
            if serialized not in database_reference:
                errors.append(f"Complete normalized DDL record is absent for {object_name}.")
        section_six_match = re.search(r"^## 6\..*?(?=^## 7\.)", specification, re.M | re.S)
        if section_six_match and any(
            len(line) > 4000
            for line in section_six_match.group(0).splitlines()
            if line.startswith("|")
        ):
            errors.append("Section 6 contains an oversized table row; exhaustive detail belongs in the operation child.")
        rule_match = re.search(
            r'<!--\s*oracle-evidence:start\s+key="business-rules"\s*-->(.*?)'
            r'<!--\s*oracle-evidence:end\s+key="business-rules"\s*-->',
            specification,
            re.S,
        )
        if rule_match and any(
            len(line) > 5000 for line in rule_match.group(1).splitlines() if line.startswith("|")
        ):
            errors.append("Section 12 contains an oversized business-rule row.")
        repeated_payloads: dict[str, int] = defaultdict(int)
        if rule_match:
            for line in rule_match.group(1).splitlines():
                if not line.startswith("|"):
                    continue
                cells = [cell.strip() for cell in re.split(r"(?<!\\)\|", line.strip("|"))]
                if len(cells) >= 5 and len(cells[3]) > 500:
                    repeated_payloads[cells[3]] += 1
        if any(count > 1 for count in repeated_payloads.values()):
            errors.append("Section 12 repeats a long path-wide message/outcome payload across rule rows.")
    return errors


def render_evidence_markdown_package(
    evidence: Mapping[str, Any],
    *,
    extraction_mode: str = "fresh",
    comparison_spec_text: str | None = None,
    source_root: Path | None = None,
    output_path: Path | None = None,
) -> dict[str, str]:
    """Render a lossless, linked legacy-evidence Markdown package."""
    module = evidence["modules"][0]
    run = evidence["run"]
    module_id = str(module["module_id"]).upper()
    module_evidence_id = f"MOD-{module_id}"
    title = str(module.get("title") or module_id)
    paths = _operation_paths(evidence)
    gaps = list(evidence.get("artifacts", {}).get("gaps", {}).get("records", []))
    coverage = list(evidence.get("artifacts", {}).get("coverage", {}).get("records", []))
    sources = list(evidence.get("artifacts", {}).get("source_inventory", {}).get("records", []))
    objects = _database_objects(evidence)
    units = _all_units(module)
    items = _all_items(module)
    messages = _message_records(module, paths)
    screenshots = list(module.get("runtime_screenshots", []))
    package_names = _package_names(module_id, output_path)
    generated_date = str(run.get("generated_at") or datetime.now(timezone.utc).isoformat()).split("T")[0]
    comparison_hash = (
        hashlib.sha256(comparison_spec_text.encode("utf-8")).hexdigest()
        if comparison_spec_text
        else "not-supplied"
    )
    open_gaps = [gap for gap in gaps if str(gap.get("status") or "").lower() != "resolved"]

    lines = [
        "---",
        "artifact_kind: legacy_evidence_specification",
        f"module_id: {module_id}",
        f"module_evidence_id: {module_evidence_id}",
        f"evidence_fingerprint: {run.get('evidence_sha256')}",
        f"extraction_run_id: {run.get('run_id')}",
        f"extraction_mode: {extraction_mode}",
        f"legacy_evidence_status: {'extracted_with_open_gaps' if open_gaps else 'extracted_no_open_gaps'}",
        f"comparison_oracle_sha256: {comparison_hash}",
        f"operation_details: {package_names['operation_details']}",
        f"decoded_source: {package_names['decoded_source']}",
        f"database_reference: {package_names['database_reference']}",
        "---",
        "",
        f"# {title} — Legacy Evidence Specification",
        "",
        "> Evidence boundary: this document records legacy behavior established by the supplied artifacts. "
        "It does not define target requirements, target design, target tests, POC assumptions, or implementation feasibility.",
        "",
        "## 1. Document Control",
        "",
        "| Attribute | Value |",
        "| --- | --- |",
        row(("Module evidence ID", module_evidence_id)),
        row(("Oracle Forms module", module_id)),
        row(("Forms title", title)),
        row(("Extraction run", run.get("run_id"))),
        row(("Extraction date", generated_date)),
        row(("Extractor", f"{evidence.get('extractor', {}).get('name')} {evidence.get('extractor', {}).get('version')}")),
        row(("Evidence fingerprint", run.get("evidence_sha256"))),
        row(("Mode", extraction_mode)),
        row(("Comparison oracle", comparison_hash)),
        row(("Operation detail reference", f"[{package_names['operation_details']}]({package_names['operation_details']})")),
        row(("Decoded source reference", f"[{package_names['decoded_source']}]({package_names['decoded_source']})")),
        row(("Database reference", f"[{package_names['database_reference']}]({package_names['database_reference']})")),
        "",
        "## 2. Evidence Summary",
        "",
    ]
    capability_rows = [
        "| Evidence area | Extracted | Notes |",
        "| --- | --- | --- |",
        row(("Sources", len(sources), f"{sum(str(s.get('parse_status')).lower() == 'parsed' for s in sources)} parsed")),
        row(("Screen blocks", len(module.get("blocks", [])), f"{len(items)} Forms items")),
        row(("Operations", len(paths), ", ".join(sorted({str(p.get('operation')) for p in paths})) or "None")),
        row(("Code units", len(units), f"{len(module.get('triggers', []))} triggers; {len(module.get('program_units', []))} program units")),
        row(("Database objects", len(objects), ", ".join(sorted(objects)) or "None resolved")),
        row(("Messages", len(messages), "Reachable and decoded messages")),
        row(("Screenshots", len(screenshots), "All plausible module matches are linked")),
        row(("Open evidence gaps", len(open_gaps), "Precise missing or unreadable evidence remains visible")),
    ]
    lines.extend(marker("executive-capabilities", capability_rows))

    lines.extend(["", "## 3. Legacy Screen Overview", ""])
    screen_body = [
        f"The selected module is `{module_id}` with Forms title **{title}**.",
        "",
        "| Structure | Count / evidence |",
        "| --- | --- |",
        row(("Windows", len(module.get("windows", [])))),
        row(("Canvases", len(module.get("canvases", [])))),
        row(("Tab pages", len(module.get("tab_pages", [])))),
        row(("Blocks", len(module.get("blocks", [])))),
        row(("Relations", len(module.get("relations", [])))),
    ]
    if screenshots:
        screen_body.extend(["", "### Plausibly Associated Runtime Screenshots", ""])
        for screenshot in screenshots:
            screen_body.extend(
                [
                    _screenshot_markdown(
                        screenshot,
                        module_id,
                        source_root=source_root,
                        output_path=output_path,
                    ),
                    "",
                    f"Association: {markdown_cell(screenshot.get('association_basis'))}; "
                    f"confidence: {markdown_cell(screenshot.get('association_confidence'))}; "
                    f"source: `{markdown_cell(screenshot.get('path'))}`.",
                    "",
                ]
            )
    else:
        screen_body.append("No plausibly associated screenshot was found in the supplied bundle.")
    lines.extend(marker("legacy-screen", screen_body))

    tab_labels = {
        str(tab.get("id") or ""): str(tab.get("label") or tab.get("id") or "")
        for tab in module.get("tab_pages", [])
        if isinstance(tab, Mapping)
    }
    groups: dict[tuple[str, str], list[tuple[Mapping[str, Any], Mapping[str, Any]]]] = defaultdict(list)
    for block, item in items:
        kind, name = _field_group(block, item)
        groups[(kind, tab_labels.get(name, name) if kind == "tab" else name)].append((block, item))
    region_rows = [
        "| Local key | Region kind | Legacy name | Item count |",
        "| --- | --- | --- | --- |",
    ]
    for (kind, name), group_items in sorted(groups.items()):
        region_rows.append(row((_local_key(module_id, kind, name), kind, name, len(group_items))))
    if len(region_rows) == 2:
        region_rows.append(row(("—", "none", "No item placement evidence", 0)))
    lines.extend([""] + marker("legacy-regions", region_rows))

    lines.extend(["", "## 4. Module Structure", ""])
    lines.extend(
        [
            "| Component | Legacy identifier | Important properties |",
            "| --- | --- | --- |",
            *[
                row(("Window", window.get("id"), _json_summary(window)))
                for window in module.get("windows", [])
            ],
            *[
                row(("Canvas", canvas.get("id"), _json_summary(canvas)))
                for canvas in module.get("canvases", [])
            ],
            *[
                row(
                    (
                        "Tab page",
                        tab_page.get("id"),
                        _json_summary(tab_page),
                    )
                )
                for tab_page in module.get("tab_pages", [])
            ],
            *[
                row(
                    (
                        "Block",
                        block.get("id"),
                        f"role={block.get('block_role')}; source={block.get('query_data_source')}; "
                        f"DML={block.get('dml_data_name')}; records displayed={block.get('records_displayed')}",
                    )
                )
                for block in module.get("blocks", [])
            ],
            *[
                row(("Attached library", library.get("name"), _json_summary(library)))
                for library in module.get("attached_libraries", [])
            ],
            *[
                row(("Relation", relation.get("name") or relation.get("id"), _json_summary(relation)))
                for relation in module.get("relations", [])
            ],
        ]
    )

    lines.extend(["", "## 5. Legacy Capability Inventory", ""])
    for operation in sorted({str(path.get("operation") or "unknown") for path in paths}):
        op_paths = [path for path in paths if str(path.get("operation") or "unknown") == operation]
        lines.extend(
            [
                f"### `{_local_key(module_id, 'operation', operation)}`",
                "",
                f"{len(op_paths)} reachable or decoded behavior path(s) provide evidence for **{operation}**.",
                "",
            ]
        )
    if not paths:
        lines.append("No operation paths were established by readable source.")

    lines.extend(["", "## 6. Operation Behavior Ledger", ""])
    operation_rows = [
        "The master ledger is intentionally concise. Every normalized call, SQL record, dependency, message, "
        f"effect, and outcome is retained in [{package_names['operation_details']}]({package_names['operation_details']}).",
        "",
        "| Operation | Entry point | Trigger / precondition summary | Business and data effect | Messages / outcomes | Confidence / gaps | Detail |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for path in paths:
        operation = str(path.get("operation") or "unknown")
        operation_rows.append(
            row(
                (
                    operation,
                    entry_symbol(path),
                    _compact_count(path.get("preconditions"), "precondition(s)"),
                    _operation_effect_summary(path),
                    _operation_outcome_summary(path),
                    f"{path.get('confidence') or 'unknown'}; gaps={len(path.get('gap_ids', []))}",
                    f"[full path]({package_names['operation_details']}#{_operation_anchor(path)})",
                )
            )
        )
    if len(operation_rows) == 4:
        operation_rows.append(row(("—", "No operation paths extracted", "—", "—", "—", "—", "unknown")))
    lines.extend(marker("functional-requirements", operation_rows))

    lines.extend(["", "## 7. Screen Layout And Regions", ""])
    lines.extend(region_rows)
    lines.extend(["", "## 8. Field And Control Evidence", ""])
    field_body: list[str] = []
    for (kind, name), group_items in sorted(groups.items()):
        field_body.extend(
            [
                f"### {kind.title()}: {name}",
                "",
                f"Local key: `{_local_key(module_id, kind, name)}`",
                "",
                "| Legacy field/control | Label | Forms type | Physical DDL mapping and type | Required / visible / enabled | Design-time Q/I/U | Effective CRUD evidence | Lookup / default | Rules and source notes |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for block, item in sorted(group_items, key=lambda pair: (str(pair[0].get("id")), str(pair[1].get("name")))):
            field_body.append(
                row(
                    (
                        f"{block.get('id')}.{item.get('name')}",
                        item.get("prompt") or item.get("hint"),
                        f"{item.get('item_type')}/{item.get('data_type')}; len={item.get('maximum_length')}; format={item.get('format_mask')}",
                        _physical_mapping_text(
                            objects,
                            block.get("dml_data_name") or block.get("query_data_source"),
                            item.get("database_column"),
                        )
                        if item.get("database_column")
                        else item.get("mapping_status"),
                        f"required={item.get('required')}; visible={item.get('visible')}; enabled={item.get('enabled')}",
                        explicit_crud_cell(item.get("design_crud")),
                        effective_crud_cell(item),
                        f"LOV={item.get('lov')}; default={item.get('initial_value')}",
                        f"canvas={item.get('canvas')}; tab={item.get('tab_page')}; source={item.get('parent_filename')}",
                    )
                )
            )
        field_body.append("")
    if not field_body:
        field_body.append("No Forms items were established.")
    lines.extend(marker("field-inventory", field_body))

    lines.extend(["", "## 9. Query And Retrieval Evidence", ""])
    lines.extend(
        [
            "| Block | Query source | Where clause | Order by | Design/effective query evidence |",
            "| --- | --- | --- | --- | --- |",
            *[
                row(
                    (
                        block.get("id"),
                        block.get("query_data_source"),
                        f"{block.get('id')}.WhereClause = {block.get('where_clause') or 'not set'}",
                        f"{block.get('id')}.OrderByClause = {block.get('order_by') or 'not set'}",
                        f"{explicit_crud_cell(block.get('design_crud'), (('query', 'Q'),))}; {effective_crud_cell(block)}",
                    )
                )
                for block in module.get("blocks", [])
            ],
        ]
    )

    lines.extend(["", "## 10. Record Selection And Master-Detail Evidence", ""])
    relation_rows = [
        "| Relation / block | Evidence |",
        "| --- | --- |",
        *[
            row((relation.get("name") or relation.get("id"), _json_summary(relation)))
            for relation in module.get("relations", [])
        ],
    ]
    if len(relation_rows) == 2:
        relation_rows.append(row(("None established", "No relation record was extracted.")))
    lines.extend(relation_rows)

    lines.extend(["", "## 11. Actions And Buttons", ""])
    action_rows = [
        "| Action control / entry | Operation group | Trigger or unit | Observable legacy behavior | Source |",
        "| --- | --- | --- | --- | --- |",
    ]
    button_locators = {
        f"{block.get('id')}.{item.get('name')}"
        for block, item in items
        if "BUTTON" in str(item.get("item_type") or "").upper()
    }
    for locator in sorted(button_locators):
        action_rows.append(row((locator, "custom action", locator, "Button/control is declared in Forms", "Forms item metadata")))
    for path in paths:
        if path.get("forms_builtins") or path.get("side_effects") or str(path.get("operation")) == "custom":
            action_rows.append(
                row(
                    (
                        entry_symbol(path),
                        path.get("operation") or "custom",
                        entry_symbol(path),
                        path_summary(path),
                        locator_text(path),
                    )
                )
            )
    if len(action_rows) == 2:
        action_rows.append(row(("None established", "—", "—", "No action evidence extracted", "—")))
    lines.extend(marker("actions", action_rows))

    lines.extend(["", "## 12. Business Rules And Validation", ""])
    rule_operations = sorted(
        {
            str(path.get("operation") or "unknown")
            for path in paths
            if path.get("branches") or path.get("validations")
        }
    )
    rule_rows = [
        "Rule groups: "
        + (
            ", ".join(f"`{_local_key(module_id, 'rule', operation)}`" for operation in rule_operations)
            if rule_operations
            else "none established"
        ),
        "",
        "Messages are associated with conditions only when they occur inside the active decoded IF/ELSIF branch in the same unit. "
        "An unbound message is preserved explicitly; it is never repeated across every rule in its operation path.",
        "",
        "| Applies during | Business condition | Message code | Message text | Effect | Association basis | Source |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    rule_data_count = 0
    for path in paths:
        for rule_record in _rule_message_bindings(path, units):
            bound_messages = rule_record.get("messages") or []
            message_codes = sorted(
                {str(message.get("code")) for message in bound_messages if message.get("code") not in (None, "")}
            )
            message_texts = sorted(
                {str(message.get("text")) for message in bound_messages if message.get("text") not in (None, "")}
            )
            rule_rows.append(
                row(
                    (
                        f"{rule_record.get('operation')} / {rule_record.get('entry')}",
                        rule_record.get("condition"),
                        ", ".join(message_codes) or "-",
                        "; ".join(message_texts) or "-",
                        _json_summary(rule_record.get("effects")) if rule_record.get("effects") else "Stop-effect association not established",
                        rule_record.get("association"),
                        rule_record.get("source"),
                    )
                )
            )
            rule_data_count += 1
    if not rule_data_count:
        rule_rows.append(row(("-", "No explicit branch/validation record extracted", "-", "-", "-", "-", "-")))
    lines.extend(marker("business-rules", rule_rows))
    dependency_rows = [
        "| Operation group | Entry point | Dependency / transaction summary | Complete detail |",
        "| --- | --- | --- | --- |",
    ]
    for path in paths:
        if path.get("dependency_checks") or path.get("transaction") or path.get("stop_effects"):
            dependency_rows.append(
                row(
                    (
                        path.get("operation") or "unknown",
                        entry_symbol(path),
                        "; ".join(
                            (
                                _compact_count(path.get("dependency_checks"), "dependency check(s)"),
                                "transaction evidence present" if path.get("transaction") else "transaction evidence not established",
                                _compact_count(path.get("stop_effects"), "stop effect(s)"),
                            )
                        ),
                        f"[full path]({package_names['operation_details']}#{_operation_anchor(path)})",
                    )
                )
            )
    persistence_objects = {
        _object_name(block.get("dml_data_name") or block.get("query_data_source"))
        for block in module.get("blocks", [])
        if block.get("block_role") == "database_persistence"
    }
    inbound_foreign_keys = _reverse_foreign_keys(objects, persistence_objects)
    if inbound_foreign_keys:
        delete_checks: dict[str, list[str]] = defaultdict(list)
        for path in paths:
            if str(path.get("operation") or "").lower() != "delete":
                continue
            for check in path.get("dependency_checks", []):
                if not isinstance(check, Mapping):
                    continue
                delete_checks[_object_name(check.get("object"))].append(
                    f"{entry_symbol(path)}: {check.get('effect') or 'effect unresolved'} "
                    f"via {check.get('routine') or 'routine unresolved'}"
                )
        dependency_rows.extend(
            [
                "",
                "### Header Delete: Database Consequences",
                "",
                "Forms hard-blocker and warning routines are not a complete database-dependency inventory. "
                "The table below is independently derived from every supplied inbound foreign key to a "
                "selected-module persistence object. Reconcile both evidence sets before treating delete "
                "behavior as complete.",
                "",
                "| Referenced object | Referencing object | Constraint | Foreign-key columns → referenced columns | On delete | Forms delete-path coverage |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for referencing_object, constraint in inbound_foreign_keys:
            target = _object_name(constraint.get("references_object"))
            coverage_text = "; ".join(sorted(set(delete_checks.get(referencing_object, []))))
            dependency_rows.append(
                row(
                    (
                        target,
                        referencing_object,
                        constraint.get("name") or constraint.get("type"),
                        f"{', '.join(map(str, constraint.get('columns') or []))} → "
                        f"{', '.join(map(str, constraint.get('references_columns') or []))}",
                        _on_delete_effect(constraint),
                        coverage_text or "Not established in decoded Forms delete paths",
                    )
                )
            )
    if len(dependency_rows) == 2:
        dependency_rows.append(row(("—", "None", "No dependency or transaction detail established.")))
    lines.extend([""] + marker("delete-save-dependencies", dependency_rows))

    lines.extend(["", "## 13. LOV And Lookup Evidence", ""])
    lookup_rows = [
        "| LOV / record group | Query or source | Return/default mapping and properties |",
        "| --- | --- | --- |",
    ]
    for lov in module.get("lovs", []):
        lookup_rows.append(row((lov.get("name") or lov.get("id"), lov.get("record_group"), _json_summary(lov))))
    for group in module.get("record_groups", []):
        lookup_rows.append(row((group.get("name") or group.get("id"), group.get("query"), _json_summary(group))))
    if len(lookup_rows) == 2:
        lookup_rows.append(row(("None established", "—", "No LOV/record-group metadata extracted.")))
    lines.extend(marker("lookups", lookup_rows))

    lines.extend(["", "## 14. Workflow And State Evidence", ""])
    state_rows = [
        "| Operation / entry | Runtime property, navigation, or state summary | Complete detail |",
        "| --- | --- | --- |",
    ]
    for path in paths:
        state = path.get("field_effects") or path.get("ui_field_effects") or path.get("side_effects")
        if state:
            state_rows.append(
                row(
                    (
                        f"{path.get('operation')} / {entry_symbol(path)}",
                        _compact_count(state, "state/property effect record(s)"),
                        f"[full path]({package_names['operation_details']}#{_operation_anchor(path)})",
                    )
                )
            )
    if len(state_rows) == 2:
        state_rows.append(row(("None established", "Runtime state/property transition not extracted.", "-")))
    lines.extend(marker("legacy-state-model", state_rows))

    lines.extend(["", "## 15. Data Model And Database Mapping", ""])
    object_rows = [
        "This section keeps curation-relevant persistence, relationship, default, and audit evidence. "
        f"Every parsed column, constraint, dependency, and complete normalized DDL record is retained in "
        f"[{package_names['database_reference']}]({package_names['database_reference']}).",
        "",
        "| Database object | Type | Module relevance | Parsed detail | Source |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name, record in sorted(objects.items()):
        used_by = sorted(
            {
                str(path.get("operation") or "unknown")
                for path in paths
                if name in _json_summary(
                    {
                        "reads": path.get("database_reads"),
                        "writes": path.get("database_writes"),
                        "dependencies": path.get("dependency_checks"),
                    }
                ).upper()
            }
        )
        object_rows.append(
            row(
                (
                    name,
                    record.get("type"),
                    ", ".join(used_by) or "DDL/supporting object",
                    f"{len(record.get('columns', []))} column(s); {len(record.get('constraints', []))} constraint(s); "
                    f"{len(record.get('dependencies', []))} dependency record(s)",
                    record.get("source_path") or record.get("relative_path"),
                )
            )
        )
    if len(object_rows) == 4:
        object_rows.append(row(("None resolved", "-", "-", "Referenced DDL was not resolved from supplied source.", "-")))
    lines.extend(marker("database-objects", object_rows))
    constraint_rows = [
        "| Object | Constraint / dependency | Evidence |",
        "| --- | --- | --- |",
    ]
    for name, record in sorted(objects.items()):
        for constraint in record.get("constraints", []):
            if (
                name not in persistence_objects
                and _object_name(constraint.get("references_object")) not in persistence_objects
            ):
                continue
            referential_effect = ""
            if constraint.get("references_object"):
                referential_effect = str(constraint.get("references_object"))
                on_delete = str(constraint.get("on_delete") or "")
                if not on_delete:
                    clause = re.search(
                        r"\bON\s+DELETE\s+(CASCADE|SET\s+NULL)\b",
                        str(constraint.get("definition") or ""),
                        re.I,
                    )
                    on_delete = clause.group(1) if clause else ""
                if on_delete:
                    referential_effect += f"; ON DELETE {on_delete.replace('_', ' ').upper()}"
            constraint_rows.append(
                row(
                    (
                        name,
                        constraint.get("name") or constraint.get("type"),
                        "; ".join(part for part in (referential_effect, _json_summary(constraint)) if part),
                    )
                )
            )
    if len(constraint_rows) == 2:
        constraint_rows.append(row(("None established", "—", "No relevant constraint metadata extracted.")))
    lines.extend([""] + marker("database-constraints", constraint_rows))
    default_rows = [
        "| Legacy locator | Default evidence |",
        "| --- | --- |",
        *[
            row((f"{block.get('id')}.{item.get('name')}", item.get("initial_value")))
            for block, item in items
            if item.get("initial_value") not in (None, "")
        ],
    ]
    if len(default_rows) == 2:
        default_rows.append(row(("None established", "No Forms default value extracted.")))
    audit_column_names = {
        "CREATED_BY",
        "CREATION_DATE",
        "LAST_UPDATED_BY",
        "LAST_UPDATE_DATE",
        "LAST_UPDATE_LOGIN",
    }
    persistence_names = {
        _object_name(block.get("dml_data_name") or block.get("query_data_source"))
        for block in module.get("blocks", [])
        if block.get("block_role") == "database_persistence"
    }
    audit_rows = [
        "",
        "### Audit Column Population Evidence",
        "",
        "| Persistence object | Audit column | Required / default | Population mechanism established by supplied source |",
        "| --- | --- | --- | --- |",
    ]
    audit_count = 0
    unit_source_upper = "\n".join(str(unit.get("code") or "") for unit in units).upper()
    for object_name in sorted(persistence_names):
        record = objects.get(object_name)
        if not record:
            continue
        for column in record.get("columns", []):
            if not isinstance(column, Mapping) or _object_name(column.get("name")) not in audit_column_names:
                continue
            column_name = _object_name(column.get("name"))
            default = column.get("default")
            explicit_assignment = bool(
                re.search(
                    rf"(?:\b{re.escape(object_name)}\s*\.\s*{re.escape(column_name)}\b|"
                    rf":\s*[A-Z0-9_$#]+\s*\.\s*{re.escape(column_name)}\s*:=)",
                    unit_source_upper,
                    re.I,
                )
            )
            if default not in (None, ""):
                mechanism = f"DDL default: {default}"
            elif explicit_assignment:
                mechanism = (
                    "Explicit assignment/reference found in decoded Forms or PL/SQL source; inspect "
                    f"[{package_names['decoded_source']}]({package_names['decoded_source']}) for ownership"
                )
            else:
                mechanism = (
                    "Not established — no DDL default or explicit decoded assignment proves whether "
                    "Forms, a database trigger, or another runtime owner populates this column"
                )
            audit_rows.append(
                row(
                    (
                        object_name,
                        column_name,
                        f"required={column.get('nullable') is False}; default={default or 'none'}",
                        mechanism,
                    )
                )
            )
            audit_count += 1
    if audit_count:
        default_rows.extend(audit_rows)
    lines.extend([""] + marker("database-defaults", default_rows))

    lines.extend(["", "## 16. Data Retrieval And Processing Logic", ""])
    processing_rows = [
        "| Operation / entry | Calls | Reads | Writes | Derivations / side effects | Complete detail |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for path in paths:
        processing_rows.append(
            row(
                (
                    f"{path.get('operation')} / {entry_symbol(path)}",
                    _compact_count(path.get("call_chain") or path.get("calls"), "call record(s)"),
                    _compact_count(path.get("database_reads"), "read record(s)"),
                    _compact_count(path.get("database_writes"), "write record(s)"),
                    _compact_count(path.get("defaults_and_derivations") or path.get("side_effects"), "effect record(s)"),
                    f"[full path]({package_names['operation_details']}#{_operation_anchor(path)})",
                )
            )
        )
    if len(processing_rows) == 2:
        processing_rows.append(row(("None established", "-", "-", "-", "-", "-")))
    lines.extend(marker("retrieval-processing", processing_rows))

    lines.extend(["", "## 17. Error And Message Catalogue", ""])
    message_rows = [
        "| Code / text | Condition / entry | Severity | Reachability | Source locator |",
        "| --- | --- | --- | --- | --- |",
    ]
    for message in messages:
        message_rows.append(
            row(
                (
                    f"{message.get('code')}: {message.get('text')}",
                    message.get("condition"),
                    message.get("severity"),
                    message.get("status"),
                    message.get("locator"),
                )
            )
        )
    if len(message_rows) == 2:
        message_rows.append(row(("None established", "—", "—", "—", "—")))
    lines.extend(marker("messages", message_rows))

    lines.extend(["", "## 18. Evidenced Operational Characteristics", ""])
    lines.extend(
        [
            "| Entry point | Transaction / locking / external boundary evidence |",
            "| --- | --- |",
            *[
                row(
                    (
                        entry_symbol(path),
                        _json_summary(
                            {
                                "transaction": path.get("transaction"),
                                "external_or_side_effects": path.get("side_effects"),
                                "unresolved_calls": path.get("unresolved_calls"),
                            }
                        ),
                    )
                )
                for path in paths
                if path.get("transaction") or path.get("side_effects") or path.get("unresolved_calls")
            ],
        ]
    )

    lines.extend(["", "## 19. Behavior Coverage Scenarios", ""])
    scenario_rows = [
        "| Operation group | Entry condition summary | Action / event | Observed legacy outcome summary | Evidence status | Complete detail |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for path in paths:
        scenario_rows.append(
            row(
                (
                    path.get("operation") or "unknown",
                    _compact_count(path.get("preconditions"), "precondition(s)"),
                    entry_symbol(path),
                    "; ".join((_operation_effect_summary(path), _operation_outcome_summary(path))),
                    f"{path.get('confidence') or 'unknown'}; gaps={len(path.get('gap_ids', []))}",
                    f"[full path]({package_names['operation_details']}#{_operation_anchor(path)})",
                )
            )
        )
    if len(scenario_rows) == 2:
        scenario_rows.append(row(("-", "-", "No path", "Behavior scenario not extracted", "unknown", "-")))
    lines.extend(marker("evidence-derived-tests", scenario_rows))

    lines.extend(["", "## 20. Evidence Traceability", ""])
    trace_rows = [
        "| Governed/local reference | Legacy locator or subject | Source support | Evidence limitation |",
        "| --- | --- | --- | --- |",
        row((module_evidence_id, module_id, ", ".join(module.get("source_paths", [])), f"{len(open_gaps)} open gaps")),
    ]
    for (kind, name), group_items in sorted(groups.items()):
        trace_rows.append(
            row(
                (
                    _local_key(module_id, kind, name),
                    ", ".join(f"{block.get('id')}.{item.get('name')}" for block, item in group_items),
                    ", ".join(sorted({str(item.get("parent_filename") or "") for _, item in group_items if item.get("parent_filename")})),
                    "See field rows and Appendix I",
                )
            )
        )
    for operation in sorted({str(path.get("operation") or "unknown") for path in paths}):
        op_paths = [path for path in paths if str(path.get("operation") or "unknown") == operation]
        trace_rows.append(
            row(
                (
                    _local_key(module_id, "operation", operation),
                    ", ".join(entry_symbol(path) for path in op_paths),
                    "; ".join(locator_text(path) for path in op_paths),
                    f"{sum(len(path.get('gap_ids', [])) for path in op_paths)} path gap references",
                )
            )
        )
    lines.extend(marker("traceability", trace_rows))

    lines.extend(["", "## 21. Conflicts, Unknowns, And Open Evidence Questions", ""])
    if open_gaps:
        lines.extend(
            [
                "| Subject | Gap kind | Affected behavior | Recommended evidence action |",
                "| --- | --- | --- | --- |",
                *[
                    row(
                        (
                            gap.get("subject") or gap.get("expected_artifact_or_behavior"),
                            gap.get("gap_kind"),
                            gap.get("affected_behavior") or gap.get("affected_operations"),
                            gap.get("recommended_action"),
                        )
                    )
                    for gap in open_gaps
                ],
            ]
        )
    else:
        lines.append("No open evidence gap is registered. This is not a claim of runtime or target completeness.")

    lines.extend(["", "## 22. Appendices", "", "### Appendix A. Source And Screenshot Inventory", ""])
    source_rows = [
        "| Source path | Role / module association | Availability / parse status | SHA-256 | Warnings |",
        "| --- | --- | --- | --- | --- |",
    ]
    for source in sources:
        source_rows.append(
            row(
                (
                    source.get("relative_path"),
                    f"{source.get('source_role')}; {source.get('module_association')}",
                    f"{source.get('availability')}; {source.get('parse_status')}",
                    source.get("sha256"),
                    source.get("parse_warnings"),
                )
            )
        )
    if screenshots:
        source_rows.extend(["", "#### Screenshot links", ""])
        for screenshot in screenshots:
            source_rows.extend(
                [
                    _screenshot_markdown(
                        screenshot,
                        module_id,
                        source_root=source_root,
                        output_path=output_path,
                    ),
                    "",
                    f"`{screenshot.get('path')}` — {screenshot.get('association_basis')} "
                    f"(confidence {screenshot.get('association_confidence') or 'not scored'}).",
                    "",
                ]
            )
    lines.extend(marker("source-evidence", source_rows))

    lines.extend(["", "### Appendix B. Item Evidence Inventory", ""])
    item_rows = [
        "| Block.item | Region local key | Type/properties | Physical mapping | CRUD evidence | Source |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for block, item in items:
        kind, name = _field_group(block, item)
        if kind == "tab":
            name = tab_labels.get(name, name)
        item_rows.append(
            row(
                (
                    f"{block.get('id')}.{item.get('name')}",
                    f"{kind}: {name}",
                    _json_summary(
                        {
                            "prompt": item.get("prompt"),
                            "type": item.get("item_type"),
                            "data_type": item.get("data_type"),
                            "length": item.get("maximum_length"),
                            "format": item.get("format_mask"),
                            "visible": item.get("visible"),
                            "enabled": item.get("enabled"),
                            "required": item.get("required"),
                        }
                    ),
                    _physical_mapping_text(
                        objects,
                        block.get("dml_data_name") or block.get("query_data_source"),
                        item.get("database_column"),
                    )
                    if item.get("database_column")
                    else item.get("mapping_status"),
                    f"design={explicit_crud_cell(item.get('design_crud'))}; effective={effective_crud_cell(item)}",
                    item.get("parent_filename"),
                )
            )
        )
    lines.extend(marker("item-coverage", item_rows))

    lines.extend(["", "### Appendix C. Trigger And Program Unit Inventory", ""])
    unit_rows = [
        f"The complete inventory and exact decoded source for all {len(units)} trigger/program-unit records is "
        f"preserved in [{package_names['decoded_source']}]({package_names['decoded_source']}).",
        "",
        "| Unit category | Count | Complete reference |",
        "| --- | --- | --- |",
    ]
    unit_kind_counts = defaultdict(int)
    for unit in units:
        unit_kind_counts[str(unit.get("kind") or unit.get("type") or "unknown")] += 1
    for unit_kind, count in sorted(unit_kind_counts.items()):
        unit_rows.append(row((unit_kind, count, f"[{package_names['decoded_source']}]({package_names['decoded_source']})")))
    if not unit_kind_counts:
        unit_rows.append(row(("None decoded", 0, f"[{package_names['decoded_source']}]({package_names['decoded_source']})")))
    lines.extend(marker("code-units", unit_rows))

    lines.extend(["", "### Appendix D. Legacy Event And Outcome Mapping", ""])
    event_rows = [
        "| Event / entry | Operation | Call / data-effect summary | Message / outcome summary | Source | Complete detail |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for path in paths:
        event_rows.append(
            row(
                (
                    entry_symbol(path),
                    path.get("operation"),
                    "; ".join(
                        (
                            _compact_count(path.get("call_chain"), "call record(s)"),
                            _operation_effect_summary(path),
                        )
                    ),
                    _operation_outcome_summary(path),
                    locator_text(path),
                    f"[full path]({package_names['operation_details']}#{_operation_anchor(path)})",
                )
            )
        )
    lines.extend(marker("event-mapping", event_rows))

    lines.extend(["", "### Appendix E. Framework And External Boundary Evidence", ""])
    framework_lines = [
        "| Boundary | Evidence | Limitation |",
        "| --- | --- | --- |",
        row(("Attached libraries", _json_summary(module.get("attached_libraries")), "Unreadable or missing library source remains a gap.")),
        row((
            "Called modules and external effects",
            f"{sum(len(path.get('side_effects') or []) for path in paths)} side-effect record(s) across {len(paths)} path(s); "
            f"see [{package_names['operation_details']}]({package_names['operation_details']})",
            "Only decoded calls and parameters are established.",
        )),
        row((
            "Unresolved calls",
            f"{sum(len(path.get('unresolved_calls') or []) for path in paths)} unresolved-call record(s); "
            f"see [{package_names['operation_details']}]({package_names['operation_details']})",
            "Behavior is not inferred beyond readable source.",
        )),
    ]
    lines.extend(marker("framework-exclusions", framework_lines))

    lines.extend(["", "### Appendix F. DDL Inventory", ""])
    ddl_rows = [
        "Appendix F is the package index for exhaustive DDL evidence; it does not duplicate Section 15. "
        f"Complete parsed records are in [{package_names['database_reference']}]({package_names['database_reference']}).",
        "",
        "| Object type | Object count | Column count | Constraint count | Complete reference |",
        "| --- | --- | --- | --- | --- |",
    ]
    ddl_type_groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in objects.values():
        ddl_type_groups[str(record.get("type") or "unknown")].append(record)
    for object_type, records in sorted(ddl_type_groups.items()):
        ddl_rows.append(
            row(
                (
                    object_type,
                    len(records),
                    sum(len(record.get("columns", [])) for record in records),
                    sum(len(record.get("constraints", [])) for record in records),
                    f"[{package_names['database_reference']}]({package_names['database_reference']})",
                )
            )
        )
    if not ddl_type_groups:
        ddl_rows.append(row(("None resolved", 0, 0, 0, f"[{package_names['database_reference']}]({package_names['database_reference']})")))
    lines.extend(marker("ddl-inventory", ddl_rows))

    lines.extend(["", "### Appendix G. Technical Evidence Notes", ""])
    comparison_anchors = _supported_comparison_anchors(evidence, comparison_spec_text)
    technical_lines = [
        "Source precedence: readable Forms structure and PL/SQL establish legacy behavior; supplied DDL establishes physical database definitions. "
        "Screenshots supplement visible layout only.",
        "",
        "| Source-supported prior anchor | Current support |",
        "| --- | --- |",
        *[row((record["anchor"], record["support"])) for record in comparison_anchors],
    ]
    if not comparison_anchors:
        technical_lines.append(row(("None", "No comparison oracle supplied or no supported anchor required carry-forward.")))
    lines.extend(marker("technical-notes", technical_lines))

    lines.extend(
        [
            "",
            "### Appendix H. Glossary",
            "",
            "| Term | Meaning in this evidence package |",
            "| --- | --- |",
            row(("Forms item", "A control identified by natural `BLOCK.ITEM` locator.")),
            row(("Effective CRUD", "Runtime behavior established after known block/item restrictions and decoded property changes; unknown when source is incomplete.")),
            row(("Evidence gap", "A precise missing, unreadable, conflicting, or unresolved source dimension.")),
            row(("Coverage scenario", "A legacy entry-condition-action-outcome slice used to check extraction coverage; not a target test case.")),
            "",
            "### Appendix I. Extraction Coverage And Missing Sources",
            "",
            "#### Coverage Summary",
            "",
        ]
    )
    coverage_rows = [
        "| Dimension | Accounted / denominator | Unresolved | Status | Notes |",
        "| --- | --- | --- | --- | --- |",
    ]
    for record in coverage:
        coverage_rows.append(
            row(
                (
                    record.get("dimension"),
                    f"{record.get('numerator')}/{record.get('denominator')}",
                    record.get("unresolved_count"),
                    record.get("status"),
                    f"{len(record.get('exclusions') or [])} exclusion/reference record(s)"
                    if record.get("exclusions")
                    else "—",
                )
            )
        )
    lines.extend(marker("extraction-coverage", coverage_rows))
    gap_rows = [
        "| Subject | Gap kind / status | Why expected | Affected behavior | Fallback evidence | Confidence impact | Acquisition or validation action |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for gap in gaps:
        gap_rows.append(
            row(
                (
                    gap.get("subject") or gap.get("expected_artifact_or_behavior"),
                    f"{gap.get('gap_kind')} / {gap.get('status')}",
                    gap.get("why_expected"),
                    gap.get("affected_behavior") or gap.get("affected_operations"),
                    _json_summary(gap.get("available_fallback_evidence")),
                    gap.get("classification"),
                    gap.get("recommended_action"),
                )
            )
        )
    if len(gap_rows) == 2:
        gap_rows.append(row(("None", "No open gap", "—", "—", "—", "—", "—")))
    lines.extend(["", "#### Evidence Gaps And Missing Sources", ""] + marker("missing-sources", gap_rows))

    lines.extend(["", "### Appendix J. Extraction History", ""])
    history_rows = [
        "| Run ID | Date | Mode | Source delta | Changed evidence dimensions | Open/resolved gaps | Evidence fingerprint |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        row(
            (
                run.get("run_id"),
                generated_date,
                extraction_mode,
                count_summary(evidence.get("incremental", {}).get("change_set"))
                if evidence.get("incremental", {}).get("change_set")
                else "Fresh selected bundle",
                count_summary(evidence.get("incremental", {}).get("impacted"))
                if evidence.get("incremental", {}).get("impacted")
                else "All evidence dimensions",
                f"{len(open_gaps)} open / {len(gaps) - len(open_gaps)} resolved",
                run.get("evidence_sha256"),
            )
        ),
    ]
    lines.extend(marker("incremental-history", history_rows))
    lines.append("")
    specification = "\n".join(lines)
    package_documents = {
        "operation_details": _render_operation_reference(evidence, paths, package_names),
        "decoded_source": _render_decoded_source_reference(evidence, units, package_names),
        "database_reference": _render_database_reference(evidence, objects, package_names),
    }
    errors = validate_evidence_markdown_contract(
        evidence,
        specification,
        comparison_spec_text=comparison_spec_text,
        package_documents=package_documents,
    )
    if errors:
        raise ValueError("Rendered Markdown contract failed:\n- " + "\n- ".join(errors))
    return {
        package_names["master"]: specification,
        package_names["operation_details"]: package_documents["operation_details"],
        package_names["decoded_source"]: package_documents["decoded_source"],
        package_names["database_reference"]: package_documents["database_reference"],
    }


def render_evidence_markdown_specification(
    evidence: Mapping[str, Any],
    *,
    extraction_mode: str = "fresh",
    comparison_spec_text: str | None = None,
    source_root: Path | None = None,
    output_path: Path | None = None,
) -> str:
    """Backward-compatible API returning only the package master document."""
    package = render_evidence_markdown_package(
        evidence,
        extraction_mode=extraction_mode,
        comparison_spec_text=comparison_spec_text,
        source_root=source_root,
        output_path=output_path,
    )
    master_name = _package_names(str(evidence["modules"][0]["module_id"]).upper(), output_path)["master"]
    return package[master_name]


# Public API used by the evidence compiler.
validate_markdown_contract = validate_evidence_markdown_contract
render_markdown_specification = render_evidence_markdown_specification
