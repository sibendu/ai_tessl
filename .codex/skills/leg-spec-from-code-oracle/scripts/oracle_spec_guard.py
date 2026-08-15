#!/usr/bin/env python3
"""Validate an Oracle Forms evidence model against its generated specification.

The guard is deliberately dependency-free.  It accepts either the aggregate
``evidence-model.json`` produced by the Oracle evidence compiler or a run
directory containing the contract artifacts documented by the skill.

Open, precisely registered source gaps are evidence, not validator failures.
Structural/schema errors, unaccounted coverage, stale specifications, lost gap
history, and claims that exceed the available coverage are failures.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import unquote


TOOL_VERSION = "1.6.0"
SUPPORTED_SCHEMA_MAJORS = {1, 2}
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
GAP_ID_RE = re.compile(r"^GAP-[A-Z0-9][A-Z0-9_-]*-[A-Z0-9][A-Z0-9_-]*$")

ARTIFACT_ALIASES = {
    "source_inventory": ("source_inventory", "source-inventory", "sources"),
    "normalized_evidence": (
        "normalized_evidence",
        "normalized-evidence",
        "facts",
    ),
    "behavior_ledger": ("behavior_ledger", "behavior-ledger", "paths"),
    "coverage": ("coverage",),
    "gaps": ("gaps", "gap_register", "gap-register"),
    "source_delta": ("source_delta", "source-delta", "delta"),
}

ARTIFACT_FILENAMES = {
    "source_inventory": "source-inventory.json",
    "normalized_evidence": "normalized-evidence.json",
    "behavior_ledger": "behavior-ledger.json",
    "coverage": "coverage.json",
    "gaps": "gaps.json",
    "source_delta": "source-delta.json",
}

CANONICAL_SECTIONS = [str(i) for i in range(1, 23)] + [
    f"Appendix {letter}" for letter in "ABCDEFGHIJ"
]

SECTION_IMPACT = {
    "source": {"2", "3", "Appendix A", "Appendix I", "Appendix J"},
    "item": {"3", "6", "8", "Appendix B"},
    "block": {"3", "6", "7", "8", "Appendix B"},
    "mapping": {"8", "15", "Appendix B", "Appendix F"},
    "behavior": {
        "6",
        "11",
        "12",
        "14",
        "16",
        "17",
        "19",
        "20",
        "Appendix C",
        "Appendix D",
        "Appendix G",
    },
    "ddl": {"8", "12", "15", "16", "Appendix F", "Appendix G"},
    "message": {"6", "12", "17", "19", "20", "Appendix C"},
    "gap": {"2", "21", "Appendix I", "Appendix J"},
    "audit": {"2", "20", "21", "Appendix I", "Appendix J"},
}

SECTION_MARKERS = {
    "2": {"executive-capabilities"},
    "3": {"legacy-screen", "legacy-regions"},
    "6": {"functional-requirements"},
    "8": {"field-inventory"},
    "11": {"actions"},
    "12": {"business-rules", "delete-save-dependencies"},
    "13": {"lookups"},
    "14": {"legacy-state-model"},
    "15": {"database-objects", "database-constraints", "database-defaults"},
    "16": {"retrieval-processing"},
    "17": {"messages"},
    "19": {"evidence-derived-tests"},
    "20": {"traceability"},
    "Appendix A": {"source-evidence"},
    "Appendix B": {"item-coverage"},
    "Appendix C": {"code-units"},
    "Appendix D": {"event-mapping"},
    "Appendix E": {"framework-exclusions"},
    "Appendix F": {"ddl-inventory"},
    "Appendix G": {"technical-notes"},
    "Appendix I": {"extraction-coverage", "missing-sources"},
    "Appendix J": {"incremental-history"},
}

MANDATORY_INCREMENTAL_MARKERS = {"extraction-coverage", "missing-sources", "incremental-history"}
MARKER_START_RE = re.compile(r'^<!--\s*oracle-evidence:start\s+key="([A-Za-z0-9_.:-]+)"\s*-->\s*$', re.M)
MARKER_END_RE = re.compile(r'^<!--\s*oracle-evidence:end\s+key="([A-Za-z0-9_.:-]+)"\s*-->\s*$', re.M)

GATE_DIMENSION_ALIASES = {
    "GATE-SOURCE-CLASSIFICATION": ("source_classification", "sources", "source_files"),
    "GATE-SOURCE-INTEGRITY": ("source_integrity", "source_files"),
    "GATE-FORMS-STRUCTURE": ("forms_structure", "blocks", "items", "regions"),
    "GATE-EFFECTIVE-CRUD": ("effective_crud", "block_crud", "item_crud"),
    "GATE-PHYSICAL-MAPPING": ("physical_mapping", "item_column_mapping", "mappings"),
    "GATE-ENTRY-POINTS": ("entry_points", "persistence_entry_points"),
    "GATE-CALL-REACHABILITY": ("call_reachability", "reachable_calls", "unresolved_calls"),
    "GATE-OPERATION-PATHS": ("operation_paths", "behavior_paths", "behavior"),
    "GATE-DATABASE-REFERENCES": (
        "database_references",
        "ddl",
        "ddl_definitions",
        "database_objects",
    ),
    "GATE-RULES-MESSAGES": ("rules_messages", "messages", "validations"),
    "GATE-TRANSACTION-BEHAVIOR": ("transaction_behavior", "transactions"),
    "GATE-SPECIFICATION-COVERAGE": ("specification_coverage", "spec_coverage"),
    "GATE-INDEPENDENT-AUDIT": ("independent_audit", "audit"),
}

LIMITING_CLAIMS = (
    (
        "EDIT_SCOPE",
        re.compile(
            r"\b(?:header\s+only|only\s+(?:the\s+)?header\b|"
            r"only\s+.{0,80}\b(?:editable|edited|updated)|"
            r"(?:updates?|edits?)\s+only\s+)",
            re.I,
        ),
        ("sources", "blocks", "items", "behavior", "audit"),
    ),
    (
        "SINGLE_WRITE_TARGET",
        re.compile(r"\b(?:only\s+(?:one|a\s+single)\s+table|updates?\s+only\s+(?:the\s+)?[A-Z0-9_$#]+)", re.I),
        ("sources", "behavior", "ddl", "audit"),
    ),
    (
        "NO_VALIDATION_OR_EFFECT",
        re.compile(r"\bno\s+(?:validation|message|side[ -]?effect|dependency|additional\s+update|custom\s+logic)s?\b", re.I),
        ("sources", "behavior", "audit"),
    ),
    (
        "ABSOLUTE_DELETE",
        re.compile(r"\bdelete\s+(?:is\s+)?(?:always\s+)?(?:blocked|cascades?)\b|\balways\s+cascades?\b", re.I),
        ("sources", "behavior", "ddl", "audit"),
    ),
    (
        "ATOMICITY",
        re.compile(r"\b(?:is|are|remains?)\s+atomic\b|\balways\s+rolls?\s+back\b", re.I),
        ("sources", "behavior", "audit"),
    ),
    (
        "NEVER_EDITABLE",
        re.compile(
            r"\bnever\s+(?:editable|updated|inserted|deleted)\b|"
            r"\b(?:field|item|block|screen|module|record)s?\b.{0,60}\bread[ -]?only\b|"
            r"\bread[ -]?only\b.{0,60}\b(?:field|item|block|screen|module|record)s?\b",
            re.I,
        ),
        ("sources", "blocks", "items", "behavior", "audit"),
    ),
    (
        "FRAMEWORK_NO_EFFECT",
        re.compile(r"\bframework\b.{0,100}\bno\s+module-specific\s+(?:business\s+)?effect\b", re.I),
        ("sources", "behavior", "audit"),
    ),
)


@dataclass
class EvidenceBundle:
    root: Path
    aggregate: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, dict[str, Any]] = field(default_factory=dict)
    documents: list[tuple[str, dict[str, Any], Path]] = field(default_factory=list)
    audit: dict[str, Any] = field(default_factory=dict)
    load_errors: list[dict[str, Any]] = field(default_factory=list)

    def component(self, name: str) -> Any:
        if name in self.artifacts:
            return self.artifacts[name]
        for alias in ARTIFACT_ALIASES[name]:
            value = _mapping_get(self.aggregate, alias)
            if value is not None:
                return value
        artifacts = self.aggregate.get("artifacts")
        if isinstance(artifacts, Mapping):
            for alias in ARTIFACT_ALIASES[name]:
                value = _mapping_get(artifacts, alias)
                if value is not None:
                    return value
        return {}

    def records(self, name: str) -> list[dict[str, Any]]:
        return _records(self.component(name))


def _mapping_get(mapping: Any, key: str) -> Any:
    if not isinstance(mapping, Mapping):
        return None
    normalized = key.lower().replace("-", "_")
    for candidate, value in mapping.items():
        if str(candidate).lower().replace("-", "_") == normalized:
            return value
    return None


def _records(component: Any) -> list[dict[str, Any]]:
    if isinstance(component, list):
        return [row for row in component if isinstance(row, dict)]
    if not isinstance(component, Mapping):
        return []
    records = component.get("records")
    if isinstance(records, list):
        return [row for row in records if isinstance(row, dict)]
    for key in ("items", "facts", "paths", "gaps", "sources", "entries"):
        rows = component.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _read_json(path: Path, errors: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(_issue("EVIDENCE_JSON_PARSE", f"Cannot parse {path}: {exc}"))
        return {}
    if not isinstance(value, dict):
        errors.append(_issue("EVIDENCE_JSON_SHAPE", f"{path} must contain a JSON object."))
        return {}
    return value


def _select_run_directory(root: Path) -> Path:
    if any((root / filename).is_file() for filename in ARTIFACT_FILENAMES.values()):
        return root
    candidates = list(root.rglob("evidence-model.json"))
    if not candidates:
        candidates = list(root.rglob("normalized-evidence.json"))
    if not candidates:
        return root

    def rank(path: Path) -> tuple[str, float]:
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            generated = str(data.get("generated_at") or data.get("run", {}).get("generated_at") or "")
        except Exception:
            generated = ""
        return generated, path.stat().st_mtime

    return max(candidates, key=rank).parent


def load_evidence(path_value: str | Path) -> EvidenceBundle:
    path = Path(path_value).resolve()
    bundle = EvidenceBundle(root=path if path.is_dir() else path.parent)
    if not path.exists():
        bundle.load_errors.append(_issue("EVIDENCE_NOT_FOUND", f"Evidence path does not exist: {path}"))
        return bundle

    if path.is_file():
        data = _read_json(path, bundle.load_errors)
        bundle.aggregate = data
        bundle.documents.append((path.name, data, path))
        _load_embedded_artifacts(bundle, data, path.parent)
        return bundle

    run_dir = _select_run_directory(path)
    aggregate_path = run_dir / "evidence-model.json"
    if aggregate_path.is_file():
        bundle.aggregate = _read_json(aggregate_path, bundle.load_errors)
        bundle.documents.append((aggregate_path.name, bundle.aggregate, aggregate_path))
        _load_embedded_artifacts(bundle, bundle.aggregate, run_dir)

    for name, filename in ARTIFACT_FILENAMES.items():
        artifact_path = run_dir / filename
        if artifact_path.is_file():
            data = _read_json(artifact_path, bundle.load_errors)
            bundle.artifacts[name] = data
            bundle.documents.append((name, data, artifact_path))

    run_id = str(_metadata(bundle.aggregate).get("run_id") or "")
    audit_candidates = [run_dir / "audit-status.json"]
    if run_id:
        audit_candidates.append(path / "runs" / run_id / "audit-status.json")
    for audit_path in audit_candidates:
        if audit_path.is_file():
            bundle.audit = _read_json(audit_path, bundle.load_errors)
            break

    if not bundle.aggregate and not bundle.artifacts:
        bundle.load_errors.append(
            _issue(
                "EVIDENCE_ARTIFACTS_MISSING",
                f"No evidence-model.json or contract artifacts found under {path}.",
            )
        )
    return bundle


def _load_embedded_artifacts(bundle: EvidenceBundle, aggregate: dict[str, Any], base: Path) -> None:
    artifacts = aggregate.get("artifacts")
    if not isinstance(artifacts, Mapping):
        return
    for name, aliases in ARTIFACT_ALIASES.items():
        value = None
        for alias in aliases:
            value = _mapping_get(artifacts, alias)
            if value is not None:
                break
        if isinstance(value, Mapping):
            bundle.artifacts[name] = dict(value)
            if any(
                key in value
                for key in (
                    "schema_version",
                    "extractor_version",
                    "module_id",
                    "run_id",
                    "generated_at",
                    "input_manifest_sha256",
                )
            ):
                bundle.documents.append((name, dict(value), base / f"<{name}>"))
        elif isinstance(value, list):
            bundle.artifacts[name] = {"records": value}
        elif isinstance(value, str):
            candidate = (base / value).resolve()
            if candidate.is_file():
                data = _read_json(candidate, bundle.load_errors)
                bundle.artifacts[name] = data
                bundle.documents.append((name, data, candidate))


def _issue(
    code: str,
    message: str,
    *,
    record_ids: Iterable[str] = (),
    sections: Iterable[str] = (),
    line: int | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "code": code,
        "message": message,
        "record_ids": sorted({str(item) for item in record_ids if item}),
        "sections": sorted({str(item) for item in sections if item}, key=_section_sort_key),
    }
    if line is not None:
        value["line"] = line
    return value


def _section_sort_key(value: str) -> tuple[int, str]:
    if value.isdigit():
        return int(value), ""
    match = re.match(r"Appendix\s+([A-Z])", value, re.I)
    return (100 + ord(match.group(1).upper()) - ord("A"), value) if match else (999, value)


def _metadata(document: Mapping[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for holder_key in ("metadata", "run"):
        holder = document.get(holder_key)
        if isinstance(holder, Mapping):
            metadata.update(holder)
    extractor = document.get("extractor")
    if isinstance(extractor, Mapping):
        metadata.setdefault("extractor_version", extractor.get("version"))
        metadata.setdefault("schema_version", extractor.get("schema"))
    modules = document.get("modules")
    if isinstance(modules, list) and len(modules) == 1 and isinstance(modules[0], Mapping):
        metadata.setdefault("module_id", modules[0].get("module_id"))
    for key in (
        "schema_version",
        "extractor_version",
        "module_id",
        "run_id",
        "generated_at",
        "input_manifest_sha256",
        "evidence_fingerprint",
        "evidence_sha256",
    ):
        if document.get(key) is not None:
            metadata[key] = document[key]
    return metadata


def _fingerprints(bundle: EvidenceBundle) -> tuple[set[str], set[str]]:
    evidence: set[str] = set()
    manifests: set[str] = set()
    documents = bundle.documents or [("aggregate", bundle.aggregate, bundle.root)]
    for _, document, _ in documents:
        metadata = _metadata(document)
        for key in ("evidence_fingerprint", "evidence_sha256"):
            value = metadata.get(key)
            if isinstance(value, str) and value:
                evidence.add(value.lower())
        value = metadata.get("input_manifest_sha256")
        if isinstance(value, str) and value:
            manifests.add(value.lower())
    return evidence, manifests


def _module_ids(bundle: EvidenceBundle) -> set[str]:
    result: set[str] = set()
    documents = bundle.documents or [("aggregate", bundle.aggregate, bundle.root)]
    for _, document, _ in documents:
        value = _metadata(document).get("module_id")
        if isinstance(value, str) and value.strip():
            result.add(value.strip().upper())
    return result


def _validate_metadata(bundle: EvidenceBundle, errors: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> None:
    errors.extend(bundle.load_errors)
    for name, document, path in bundle.documents:
        metadata = _metadata(document)
        for key in ("schema_version", "extractor_version", "module_id", "run_id", "generated_at"):
            if metadata.get(key) in (None, ""):
                errors.append(_issue("EVIDENCE_METADATA_MISSING", f"{path} is missing {key}."))
        schema = str(metadata.get("schema_version") or "")
        try:
            version_part = schema.rsplit("/", 1)[-1]
            major = int(version_part.split(".", 1)[0])
        except ValueError:
            major = -1
        if schema and major not in SUPPORTED_SCHEMA_MAJORS:
            errors.append(_issue("EVIDENCE_SCHEMA_UNSUPPORTED", f"{path} uses unsupported schema {schema}."))
        fingerprint = metadata.get("input_manifest_sha256")
        if not isinstance(fingerprint, str) or not SHA256_RE.fullmatch(fingerprint):
            errors.append(
                _issue(
                    "EVIDENCE_FINGERPRINT_INVALID",
                    f"{path} is missing a valid input_manifest_sha256.",
                )
            )
        if name != "evidence-model.json" and "records" not in document:
            warnings.append(
                _issue(
                    "ARTIFACT_RECORDS_MISSING",
                    f"Contract artifact {path} has no records array.",
                )
            )

    module_ids = _module_ids(bundle)
    if len(module_ids) > 1:
        errors.append(
            _issue(
                "EVIDENCE_MODULE_CONFLICT",
                f"Evidence artifacts disagree on module_id: {', '.join(sorted(module_ids))}.",
            )
        )
    evidence_fps, manifest_fps = _fingerprints(bundle)
    if len(manifest_fps) > 1:
        errors.append(
            _issue(
                "EVIDENCE_MANIFEST_CONFLICT",
                "Evidence artifacts carry different input manifest fingerprints.",
            )
        )
    if len(evidence_fps) > 1:
        errors.append(
            _issue(
                "EVIDENCE_FINGERPRINT_CONFLICT",
                "Evidence artifacts carry different evidence fingerprints.",
            )
        )


def _parse_frontmatter(text: str) -> dict[str, str]:
    lines = text.lstrip("\ufeff").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    result: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*?)\s*$", line)
        if match:
            result[match.group(1)] = match.group(2).strip().strip("\"'")
    return result


def _section_text(text: str, appendix: str) -> str:
    pattern = re.compile(rf"^###\s+Appendix\s+{re.escape(appendix)}\b.*$", re.I | re.M)
    match = pattern.search(text)
    if not match:
        return ""
    next_heading = re.compile(r"^###\s+Appendix\s+[A-Z]\b.*$", re.I | re.M).search(text, match.end())
    end = next_heading.start() if next_heading else len(text)
    return text[match.start() : end]


def _spec_sections(text: str) -> set[str]:
    result: set[str] = set()
    for match in re.finditer(r"^##\s+(\d+)\.", text, re.M):
        result.add(match.group(1))
    for match in re.finditer(r"^###\s+Appendix\s+([A-Z])\b", text, re.I | re.M):
        result.add(f"Appendix {match.group(1).upper()}")
    return result


def _load_spec_package(
    spec_path: Path,
    master_text: str,
    errors: list[dict[str, Any]],
) -> dict[str, tuple[Path, str]]:
    """Load generated child references declared by the master front matter."""
    result: dict[str, tuple[Path, str]] = {"master": (spec_path, master_text)}
    frontmatter = _parse_frontmatter(master_text)
    for key in ("operation_details", "decoded_source", "database_reference"):
        value = str(frontmatter.get(key) or "").strip()
        if not value:
            if str(frontmatter.get("artifact_kind") or "").lower() == "legacy_evidence_specification":
                errors.append(_issue("SPEC_PACKAGE_CHILD_UNDECLARED", f"Master specification does not declare {key}."))
            continue
        child_path = (spec_path.parent / unquote(value)).resolve()
        try:
            child_text = child_path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            errors.append(_issue("SPEC_PACKAGE_CHILD_READ_FAILED", f"Cannot read {key} child {child_path}: {exc}"))
            continue
        result[key] = (child_path, child_text)
    return result


def _numbered_section_text(text: str, section: str) -> str:
    match = re.search(rf"^##\s+{re.escape(section)}\..*$", text, re.M)
    if not match:
        return ""
    following = re.search(r"^##\s+\d+\..*$", text[match.end() :], re.M)
    end = match.end() + following.start() if following else len(text)
    return text[match.start() : end]


def _validate_spec_package(
    package: Mapping[str, tuple[Path, str]],
    master_frontmatter: Mapping[str, str],
    errors: list[dict[str, Any]],
) -> None:
    module_id = str(master_frontmatter.get("module_id") or "").upper()
    fingerprint = str(master_frontmatter.get("evidence_fingerprint") or "").lower()
    run_id = str(master_frontmatter.get("extraction_run_id") or "")
    expected = {
        "operation_details": "operation_details",
        "decoded_source": "decoded_source",
        "database_reference": "database_reference",
    }
    for key, reference_kind in expected.items():
        child = package.get(key)
        if not child:
            continue
        child_path, child_text = child
        metadata = _parse_frontmatter(child_text)
        mismatches: list[str] = []
        if metadata.get("artifact_kind") != "legacy_evidence_reference":
            mismatches.append("artifact_kind")
        if metadata.get("reference_kind") != reference_kind:
            mismatches.append("reference_kind")
        if str(metadata.get("module_id") or "").upper() != module_id:
            mismatches.append("module_id")
        if str(metadata.get("evidence_fingerprint") or "").lower() != fingerprint:
            mismatches.append("evidence_fingerprint")
        if str(metadata.get("extraction_run_id") or "") != run_id:
            mismatches.append("extraction_run_id")
        if mismatches:
            errors.append(
                _issue(
                    "SPEC_PACKAGE_CHILD_METADATA_MISMATCH",
                    f"Child {child_path.name} does not match master package metadata: {', '.join(mismatches)}.",
                )
            )

    master_text = package.get("master", (Path(), ""))[1]
    section_six = _numbered_section_text(master_text, "6")
    business_rule_match = re.search(
        r'<!--\s*oracle-evidence:start\s+key="business-rules"\s*-->(.*?)'
        r'<!--\s*oracle-evidence:end\s+key="business-rules"\s*-->',
        master_text,
        re.S,
    )
    section_twelve = business_rule_match.group(1) if business_rule_match else _numbered_section_text(master_text, "12")
    oversized_six = [len(line) for line in section_six.splitlines() if line.startswith("|") and len(line) > 4000]
    if oversized_six:
        errors.append(
            _issue(
                "SPEC_OPERATION_LEDGER_UNREADABLE",
                "Section 6 contains an oversized table row; move exhaustive path evidence to the operation-detail child.",
            )
        )
    oversized_rules = [len(line) for line in section_twelve.splitlines() if line.startswith("|") and len(line) > 5000]
    if oversized_rules:
        errors.append(
            _issue(
                "SPEC_BUSINESS_RULE_ROW_UNREADABLE",
                "Section 12 contains an oversized rule row, usually caused by repeating a path-wide message set.",
            )
        )
    repeated_rule_payloads: dict[str, int] = defaultdict(int)
    for line in section_twelve.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in re.split(r"(?<!\\)\|", line.strip("|"))]
        if len(cells) < 5:
            continue
        message_or_outcome = cells[3]
        if len(message_or_outcome) > 500:
            repeated_rule_payloads[message_or_outcome] += 1
    if any(count > 1 for count in repeated_rule_payloads.values()):
        errors.append(
            _issue(
                "SPEC_PATH_MESSAGE_SET_REPEATED",
                "Section 12 repeats a long path-wide message/outcome payload across multiple rule rows.",
            )
        )
    if section_twelve and "Message code" not in section_twelve:
        errors.append(
            _issue(
                "SPEC_BUSINESS_RULE_MESSAGE_ASSOCIATION_MISSING",
                "Section 12 must expose business condition, message code/text, effect, and association basis.",
            )
        )


def _validate_complete_specification_contract(
    bundle: EvidenceBundle,
    spec_text: str,
    frontmatter: Mapping[str, str],
    errors: list[dict[str, Any]],
    package_text: str | None = None,
) -> None:
    """Enforce the evidence-only output contract for specifications generated by this skill.

    Historical and hand-authored specifications without ``artifact_kind`` keep
    the guard's backward-compatible checks.  New generated specifications opt
    into the strict contract and cannot pass with a field-complete but
    behavior-incomplete document.
    """
    if str(frontmatter.get("artifact_kind") or "").lower() != "legacy_evidence_specification":
        return

    sections = _spec_sections(spec_text)
    missing_sections = sorted(set(CANONICAL_SECTIONS) - sections, key=_section_sort_key)
    if missing_sections:
        errors.append(
            _issue(
                "SPECIFICATION_CONTRACT_INCOMPLETE",
                "Generated extraction specification is missing canonical sections: "
                + ", ".join(missing_sections),
                sections=missing_sections,
            )
        )

    required_markers = set().union(*SECTION_MARKERS.values())
    starts = MARKER_START_RE.findall(spec_text)
    ends = MARKER_END_RE.findall(spec_text)
    missing_markers = sorted(
        key for key in required_markers if starts.count(key) != 1 or ends.count(key) != 1
    )
    if missing_markers:
        errors.append(
            _issue(
                "SPECIFICATION_MARKER_CONTRACT_INCOMPLETE",
                "Generated extraction specification lacks exactly one balanced region for: "
                + ", ".join(missing_markers),
            )
        )
    package_text = package_text or spec_text
    if "[truncated]" in package_text.casefold():
        errors.append(
            _issue(
                "SPECIFICATION_EVIDENCE_TRUNCATED",
                "Generated specification contains a truncation marker; the durable evidence surface must be lossless.",
            )
        )
    if re.search(r"\+\d+\s+more\b", package_text, re.I):
        errors.append(
            _issue(
                "SPECIFICATION_EVIDENCE_SUMMARIZED_LOSSILY",
                "Generated specification contains a lossy '+N more' placeholder.",
            )
        )

    missing_decoded_sources: list[str] = []
    modules = bundle.aggregate.get("modules", [])
    selected_units = [
        unit
        for module in modules
        if isinstance(module, Mapping)
        for collection in ("triggers", "program_units")
        for unit in module.get(collection, [])
        if isinstance(unit, Mapping)
    ]
    rendered_source_blocks = {
        match.group("hash").lower(): match.group("code").replace("\r\n", "\n").replace("\r", "\n")
        for match in re.finditer(
            r"Decoded source SHA-256:\s*`(?P<hash>[0-9a-fA-F]{64})`"
            r".*?\n(?P<fence>~{3,})sql\r?\n(?P<code>.*?)\r?\n(?P=fence)",
            package_text,
            re.S,
        )
    }
    for unit in selected_units:
        decoded_source = (
            str(unit.get("code") or "")
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .strip()
        )
        digest = str(unit.get("code_sha256") or "").lower()
        rendered_code = rendered_source_blocks.get(digest) if digest else None
        if decoded_source and rendered_code != decoded_source:
            missing_decoded_sources.append(
                str(unit.get("id") or unit.get("name") or unit.get("locator") or "decoded source")
            )
    if missing_decoded_sources:
        errors.append(
            _issue(
                "SPECIFICATION_DECODED_SOURCE_MISSING",
                "Generated specification omits exact decoded trigger or program-unit source.",
                record_ids=sorted(missing_decoded_sources),
            )
        )

    missing_records: list[str] = []
    for record in bundle.records("source_inventory"):
        locator = str(record.get("relative_path") or record.get("path") or "")
        if locator and locator not in package_text:
            missing_records.append(locator)
    for record in bundle.records("behavior_ledger"):
        entry = record.get("entry_point") or {}
        entry_symbol = (
            str(entry.get("symbol") or entry.get("scope") or "")
            if isinstance(entry, Mapping)
            else str(entry)
        )
        operation = str(record.get("operation") or "")
        if entry_symbol and (entry_symbol not in package_text or operation not in package_text):
            missing_records.append(f"{operation}/{entry_symbol}")
    for record in bundle.records("gaps"):
        subject = str(record.get("subject") or record.get("expected_artifact_or_behavior") or "")
        if subject and subject not in package_text:
            missing_records.append(subject)
    if missing_records:
        errors.append(
            _issue(
                "SPECIFICATION_MATERIAL_RECORDS_MISSING",
                "Generated specification omits source paths, behavior entries, or gap subjects.",
                record_ids=sorted(missing_records),
            )
        )
    module_id = next(iter(_module_ids(bundle)), str(frontmatter.get("module_id") or "UNKNOWN").upper())
    if str(frontmatter.get("module_evidence_id") or "") != f"MOD-{module_id}":
        errors.append(
            _issue(
                "SPECIFICATION_MODULE_ID_INVALID",
                f"Generated specification must use the single governed package ID MOD-{module_id}.",
            )
        )


def _stable_id(record: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _gap_precise(gap: Mapping[str, Any]) -> tuple[bool, list[str]]:
    missing: list[str] = []
    gap_id = _stable_id(gap, "gap_id", "id")
    if not GAP_ID_RE.fullmatch(gap_id):
        missing.append("stable gap_id")
    for key in ("gap_kind", "status", "classification"):
        if not gap.get(key):
            missing.append(key)
    if not (gap.get("subject") or gap.get("expected_artifact_or_behavior")):
        missing.append("subject/expected_artifact_or_behavior")
    if not (
        gap.get("affected_operations") or gap.get("affected_fact_ids") or gap.get("affected_path_ids")
        or gap.get("affected_behavior")
    ):
        missing.append("affected behavior references")
    return not missing, missing


def _validate_gaps(
    current: EvidenceBundle,
    previous: EvidenceBundle | None,
    appendix_i: str,
    errors: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    current_gaps = {
        _stable_id(row, "gap_id", "id"): row
        for row in current.records("gaps")
        if _stable_id(row, "gap_id", "id")
    }
    precise_ids: set[str] = set()
    for gap_id, gap in current_gaps.items():
        precise, missing = _gap_precise(gap)
        if not precise:
            errors.append(
                _issue(
                    "GAP_IMPRECISE",
                    f"{gap_id} is not precise; missing {', '.join(missing)}.",
                    record_ids=[gap_id],
                    sections=["Appendix I"],
                )
            )
        else:
            precise_ids.add(gap_id)
        gap_subject = str(gap.get("subject") or gap.get("expected_artifact_or_behavior") or "")
        if gap_id not in appendix_i and (not gap_subject or gap_subject not in appendix_i):
            errors.append(
                _issue(
                    "GAP_NOT_VISIBLE",
                    f"{gap_id} and its human-readable subject are absent from Appendix I.",
                    record_ids=[gap_id],
                    sections=["Appendix I"],
                )
            )
        status = str(gap.get("status") or "").lower()
        resolution = gap.get("resolution_evidence")
        resolution_rows = resolution if isinstance(resolution, list) else [resolution] if resolution else []
        has_resolution_locator = bool(gap.get("assumption_or_decision_id")) or any(
            isinstance(row, Mapping)
            and any(row.get(key) for key in ("source_id", "locator", "decision_id", "runtime_observation_id"))
            for row in resolution_rows
        )
        if status == "resolved" and not has_resolution_locator:
            errors.append(
                _issue(
                    "GAP_RESOLUTION_UNSUPPORTED",
                    f"{gap_id} is resolved without source/locator/runtime/decision resolution evidence.",
                    record_ids=[gap_id],
                    sections=["Appendix I", "Appendix J"],
                )
            )
        elif status in {"open", "narrowed", "reopened"} and precise:
            warnings.append(
                _issue(
                    "OPEN_REGISTERED_GAP",
                    f"{gap_id} remains {status}; this is conditional readiness, not an extraction validation failure.",
                    record_ids=[gap_id],
                    sections=["Appendix I"],
                )
            )

    if previous is not None:
        previous_gaps = {
            _stable_id(row, "gap_id", "id"): row
            for row in previous.records("gaps")
            if _stable_id(row, "gap_id", "id")
        }
        for gap_id, old in previous_gaps.items():
            if gap_id not in current_gaps:
                errors.append(
                    _issue(
                        "GAP_HISTORY_LOST",
                        f"Previously registered {gap_id} is missing from current evidence; resolved gaps must be retained.",
                        record_ids=[gap_id],
                        sections=["Appendix I", "Appendix J"],
                    )
                )
                continue
            new = current_gaps[gap_id]
            for key in ("gap_kind", "subject"):
                if old.get(key) and new.get(key) and old.get(key) != new.get(key):
                    errors.append(
                        _issue(
                            "GAP_IDENTITY_CHANGED",
                            f"{gap_id} changed semantic identity field {key}.",
                            record_ids=[gap_id],
                        )
                    )
            if str(old.get("status")).lower() == "resolved" and str(new.get("status")).lower() == "open":
                errors.append(
                    _issue(
                        "GAP_REOPEN_STATUS_INVALID",
                        f"{gap_id} must use status reopened when prior resolution is invalidated.",
                        record_ids=[gap_id],
                    )
                )
    return current_gaps, precise_ids


def _int_value(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, list):
        return len(value)
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _coverage_records(component: Any) -> list[dict[str, Any]]:
    records = _records(component)
    if records:
        return records
    found: list[dict[str, Any]] = []

    def walk(value: Any, path: list[str]) -> None:
        if not isinstance(value, Mapping):
            return
        if any(key in value for key in ("denominator", "total")) and any(
            key in value for key in ("numerator", "classified", "resolved", "covered")
        ):
            row = dict(value)
            row.setdefault("dimension", ".".join(path))
            found.append(row)
            return
        for key, child in value.items():
            if key not in {"metadata", "run", "extractor"}:
                walk(child, path + [str(key)])

    walk(component, [])
    return found


def _normalize_metric(row: Mapping[str, Any]) -> dict[str, Any]:
    dimension = str(row.get("dimension") or row.get("metric_id") or row.get("name") or "unknown").lower()
    dimension = re.sub(r"[^a-z0-9]+", "_", dimension).strip("_")
    denominator = _int_value(row.get("denominator", row.get("total", 0)))
    numerator = _int_value(
        row.get("numerator", row.get("classified", row.get("resolved", row.get("covered", 0))))
    )
    exclusions = _int_value(row.get("exclusions", row.get("excluded_count", 0)))
    unresolved = _int_value(row.get("unresolved_count", row.get("open_unknown", row.get("unresolved", 0))))
    record_ids = [str(value) for value in row.get("record_ids", []) if value]
    unresolved_ids = [str(value) for value in row.get("unresolved_record_ids", []) if value]
    if not unresolved_ids and unresolved:
        unresolved_ids = [value for value in record_ids if value.startswith("GAP-")]
    return {
        "metric_id": str(row.get("metric_id") or dimension).upper(),
        "dimension": dimension,
        "denominator": denominator,
        "numerator": numerator,
        "exclusions": exclusions,
        "unresolved_count": unresolved,
        "record_ids": record_ids,
        "unresolved_record_ids": unresolved_ids,
        "declared_status": str(row.get("status") or "").lower(),
    }


def _dimension_matches(dimension: str, aliases: Sequence[str]) -> bool:
    normalized = dimension.lower()
    return any(alias == normalized or alias in normalized for alias in aliases)


def _validate_coverage(
    bundle: EvidenceBundle,
    gaps: Mapping[str, Mapping[str, Any]],
    precise_gap_ids: set[str],
    errors: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    metrics = [_normalize_metric(row) for row in _coverage_records(bundle.component("coverage"))]
    if bundle.audit:
        audit_status = str(bundle.audit.get("status") or "pending").lower()
        audit_passed = audit_status in {"pass", "passed", "pass_with_registered_gaps", "pass_with_assumptions"}
        metrics.append(
            _normalize_metric(
                {
                    "metric_id": "COV-INDEPENDENT-AUDIT",
                    "dimension": "independent_audit",
                    "denominator": 1,
                    "numerator": 1 if audit_passed else 0,
                    "unresolved_count": 0 if audit_passed else 1,
                    "record_ids": [str(bundle.audit.get("run_id") or "audit-status")],
                    "unresolved_record_ids": [
                        str(finding.get("finding_id") or finding.get("id"))
                        for finding in bundle.audit.get("findings", [])
                        if str(finding.get("severity") or "").lower() in {"blocking", "error", "high"}
                    ] or (["AUDIT-PENDING"] if not audit_passed else []),
                    "status": "measured" if audit_passed else "fail",
                }
            )
        )

    def associated_gap_ids(metric: Mapping[str, Any]) -> set[str]:
        unresolved_records = {str(value).upper() for value in metric["unresolved_record_ids"]}
        result = {gap_id for gap_id in unresolved_records if gap_id in precise_gap_ids}
        for gap_id, gap in gaps.items():
            if gap_id not in precise_gap_ids:
                continue
            affected = {
                str(value).upper()
                for key in ("affected_fact_ids", "affected_path_ids")
                for value in (gap.get(key) or [])
            }
            subject = str(gap.get("subject") or "").upper()
            if unresolved_records & affected or (subject and subject in unresolved_records):
                result.add(gap_id)
        return result

    for metric in metrics:
        reason_ids = metric["record_ids"]
        if min(
            metric["denominator"],
            metric["numerator"],
            metric["exclusions"],
            metric["unresolved_count"],
        ) < 0:
            errors.append(_issue("COVERAGE_COUNT_INVALID", f"{metric['metric_id']} has a negative count.", record_ids=reason_ids))
            continue
        if metric["numerator"] > metric["denominator"] or metric["unresolved_count"] > metric["denominator"]:
            errors.append(_issue("COVERAGE_COUNT_INVALID", f"{metric['metric_id']} counts exceed its denominator.", record_ids=reason_ids))
        accounted_without_exclusions = metric["numerator"] + metric["unresolved_count"]
        accounted_with_exclusions = accounted_without_exclusions + metric["exclusions"]
        if metric["denominator"] and metric["denominator"] not in {
            accounted_without_exclusions,
            accounted_with_exclusions,
        }:
            errors.append(
                _issue(
                    "COVERAGE_RECONCILIATION_FAILED",
                    f"{metric['metric_id']} does not reconcile: denominator={metric['denominator']}, "
                    f"numerator={metric['numerator']}, exclusions={metric['exclusions']}, "
                    f"unresolved={metric['unresolved_count']}.",
                    record_ids=reason_ids,
                )
            )
        if metric["unresolved_count"]:
            resolved_by_gaps = associated_gap_ids(metric)
            if len(resolved_by_gaps) < metric["unresolved_count"]:
                errors.append(
                    _issue(
                        "COVERAGE_UNACCOUNTED",
                        f"{metric['metric_id']} has unresolved records without precise gap IDs.",
                        record_ids=metric["unresolved_record_ids"],
                    )
                )
        if metric["declared_status"] in {"not_evaluated", "not_evaluated_pre_specification"}:
            errors.append(
                _issue(
                    "SPECIFICATION_COVERAGE_NOT_EVALUATED",
                    f"{metric['metric_id']} is still marked {metric['declared_status']}.",
                    record_ids=metric["record_ids"],
                    sections=["20", "Appendix I"],
                )
            )

    gates: list[dict[str, Any]] = []
    for gate_id, aliases in GATE_DIMENSION_ALIASES.items():
        matched = [metric for metric in metrics if _dimension_matches(metric["dimension"], aliases)]
        if not matched:
            gates.append(
                {
                    "gate_id": gate_id,
                    "level": "evidence",
                    "status": "not_applicable",
                    "numerator": 0,
                    "denominator": 0,
                    "record_ids": [],
                    "blocking_gap_ids": [],
                    "reason": "No corresponding coverage metric was emitted.",
                }
            )
            continue
        denominator = sum(metric["denominator"] for metric in matched)
        numerator = sum(metric["numerator"] for metric in matched)
        unresolved = sum(metric["unresolved_count"] for metric in matched)
        record_ids = sorted({item for metric in matched for item in metric["record_ids"]})
        unresolved_ids = sorted({item for metric in matched for item in metric["unresolved_record_ids"]})
        accounted_gap_ids = sorted({gap_id for metric in matched for gap_id in associated_gap_ids(metric)})
        unaccounted = unresolved and len(accounted_gap_ids) < unresolved
        declared_fail = any(
            metric["declared_status"] in {"fail", "not_evaluated", "not_evaluated_pre_specification"}
            for metric in matched
        )
        reconciled = all(
            metric["denominator"]
            in {
                metric["numerator"] + metric["unresolved_count"],
                metric["numerator"] + metric["exclusions"] + metric["unresolved_count"],
            }
            for metric in matched
            if metric["denominator"]
        )
        if denominator == 0:
            status = "not_applicable"
            reason = "The emitted metric has a zero denominator."
        elif declared_fail or unaccounted or not reconciled:
            status = "fail"
            reason = "Coverage is failed, unaccounted, or arithmetically inconsistent."
        elif unresolved:
            status = "pass_with_registered_gaps"
            reason = "All unresolved records are accounted for by precise evidence gaps."
        else:
            status = "pass"
            reason = "All records are dispositioned."
        gates.append(
            {
                "gate_id": gate_id,
                "level": "evidence",
                "status": status,
                "numerator": numerator,
                "denominator": denominator,
                "record_ids": record_ids,
                "blocking_gap_ids": unresolved_ids if status == "fail" else [],
                "reason": reason,
            }
        )

    _detect_zero_count_regressions(bundle, metrics, errors, warnings)
    return metrics, gates


def _detect_zero_count_regressions(
    bundle: EvidenceBundle,
    metrics: Sequence[Mapping[str, Any]],
    errors: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    sources = bundle.records("source_inventory")
    facts = bundle.records("normalized_evidence")
    paths = bundle.records("behavior_ledger")
    fact_kinds = [str(row.get("fact_kind") or row.get("kind") or "").lower() for row in facts]

    readable_forms = any(
        str(row.get("source_role") or "").lower() in {"forms_xml", "fmt"}
        and str(row.get("availability") or "").lower() in {"readable", "partial"}
        and str(row.get("parse_status") or "").lower() in {"parsed", "partially_parsed"}
        for row in sources
    )
    readable_ddl = any(
        str(row.get("source_role") or "").lower() == "ddl"
        and str(row.get("availability") or "").lower() == "readable"
        and str(row.get("parse_status") or "").lower() == "parsed"
        for row in sources
    )
    block_facts = sum(kind in {"block", "block_crud", "forms_block"} for kind in fact_kinds)
    item_facts = sum(kind in {"item", "item_crud", "forms_item"} for kind in fact_kinds)
    ddl_facts = sum(kind in {"database_object", "ddl_object", "table", "view", "sequence"} for kind in fact_kinds)

    def max_denominator(aliases: Sequence[str]) -> int | None:
        matches = [metric["denominator"] for metric in metrics if _dimension_matches(str(metric["dimension"]), aliases)]
        return max(matches) if matches else None

    required_metrics = {
        "source": (bool(sources), ("source_classification", "source_files")),
        "block": (bool(block_facts), ("block", "forms_structure")),
        "item": (bool(item_facts), ("item", "effective_crud")),
        "behavior": (bool(paths), ("behavior", "operation_paths", "entry_point")),
        "DDL": (bool(ddl_facts or readable_ddl), ("ddl", "database_reference", "database_object")),
    }
    for label, (applicable, aliases) in required_metrics.items():
        if applicable and not any(_dimension_matches(str(metric["dimension"]), aliases) for metric in metrics):
            errors.append(
                _issue(
                    "COVERAGE_METRIC_MISSING",
                    f"{label} evidence exists but no corresponding coverage metric was emitted.",
                )
            )

    if readable_forms and block_facts == 0:
        errors.append(
            _issue(
                "ZERO_COUNT_FORMS_BLOCKS",
                "Readable parsed Forms XML/FMT produced zero block facts; possible namespace/parser regression.",
            )
        )
    if readable_forms and item_facts == 0:
        errors.append(
            _issue(
                "ZERO_COUNT_FORMS_ITEMS",
                "Readable parsed Forms XML/FMT produced zero item facts; possible namespace/parser regression.",
            )
        )
    if readable_forms and max_denominator(("blocks", "block_crud", "forms_structure")) == 0:
        errors.append(_issue("ZERO_COUNT_BLOCK_COVERAGE", "Forms block coverage denominator is zero despite readable Forms source."))
    if readable_forms and max_denominator(("items", "item_crud", "forms_structure")) == 0:
        errors.append(_issue("ZERO_COUNT_ITEM_COVERAGE", "Forms item coverage denominator is zero despite readable Forms source."))
    if readable_ddl and ddl_facts == 0:
        errors.append(
            _issue(
                "ZERO_COUNT_DDL_OBJECTS",
                "Readable parsed DDL produced zero database-object facts; possible DDL parser regression.",
            )
        )
    if any(kind in {"trigger", "program_unit", "call_edge"} for kind in fact_kinds) and not paths:
        warnings.append(
            _issue(
                "ZERO_COUNT_BEHAVIOR_PATHS",
                "Executable Forms facts exist but the behavior ledger contains zero paths; verify reachability disposition.",
            )
        )


def _metric_category(metric: Mapping[str, Any]) -> set[str]:
    dimension = str(metric.get("dimension") or "")
    result: set[str] = set()
    aliases = {
        "sources": ("source",),
        "blocks": ("block", "forms_structure"),
        "items": ("item", "physical_mapping", "effective_crud"),
        "behavior": ("behavior", "operation", "entry_point", "call", "transaction", "message", "validation"),
        "ddl": ("ddl", "database_reference", "database_object"),
        "audit": ("audit",),
    }
    for category, names in aliases.items():
        if _dimension_matches(dimension, names):
            result.add(category)
    return result


def _coverage_supports_claim(
    required: Sequence[str], metrics: Sequence[Mapping[str, Any]], gaps: Mapping[str, Mapping[str, Any]]
) -> tuple[bool, list[str]]:
    missing: list[str] = []
    for category in required:
        matched = [metric for metric in metrics if category in _metric_category(metric)]
        if not matched or any(metric["denominator"] == 0 or metric["unresolved_count"] for metric in matched):
            missing.append(category)
    open_gap_ids = [
        gap_id
        for gap_id, gap in gaps.items()
        if str(gap.get("status") or "").lower() in {"open", "narrowed", "reopened"}
        and str(gap.get("classification") or "").lower()
        in {"source_gap", "extraction_gap", "evidence_conflict", "runtime_validation_gap"}
    ]
    if open_gap_ids and any(category in required for category in ("sources", "behavior", "ddl")):
        missing.append("open behavior-affecting gaps")
    return not missing, sorted(set(missing))


def _validate_spec_claims(
    spec_text: str,
    metrics: Sequence[Mapping[str, Any]],
    gaps: Mapping[str, Mapping[str, Any]],
    errors: list[dict[str, Any]],
) -> None:
    full_inventory = re.compile(r"\bfull\b.{0,40}\binventor(?:y|ies)\b|\binventor(?:y|ies)\b.{0,40}\bfull\b", re.I)
    appendix_b = _section_text(spec_text, "B")
    item_denominators = [
        metric["denominator"]
        for metric in metrics
        if "item_crud" in str(metric.get("dimension") or "")
        or str(metric.get("dimension") or "") in {"items", "item_inventory"}
    ]

    def inventory_row_count() -> int:
        count = 0
        for row in appendix_b.splitlines():
            if not row.strip().startswith("|"):
                continue
            cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
            if not cells or all(re.fullmatch(r":?-{3,}:?", cell or "---") for cell in cells):
                continue
            first = cells[0].lower()
            if first in {"evidence id", "field id", "block.item", "legacy item/column"}:
                continue
            count += 1
        return count

    in_code_fence = False
    fence_character = ""
    fence_length = 0
    for line_number, line in enumerate(spec_text.splitlines(), 1):
        stripped = line.strip()
        fence_match = re.match(r"^(`{3,}|~{3,})", stripped)
        if fence_match:
            marker = fence_match.group(1)
            if not in_code_fence:
                in_code_fence = True
                fence_character = marker[0]
                fence_length = len(marker)
            elif marker[0] == fence_character and len(marker) >= fence_length:
                in_code_fence = False
                fence_character = ""
                fence_length = 0
            continue
        if in_code_fence or not stripped:
            continue
        if full_inventory.search(stripped):
            supported, missing = _coverage_supports_claim(("items",), metrics, gaps)
            if not supported:
                errors.append(
                    _issue(
                        "MISLEADING_FULL_INVENTORY",
                        f"Line {line_number} claims a full inventory without reconciled item coverage ({', '.join(missing)}).",
                        sections=["Appendix B"],
                        line=line_number,
                    )
                )
            elif item_denominators and appendix_b:
                expected = max(item_denominators)
                actual = inventory_row_count()
                if actual != expected:
                    errors.append(
                        _issue(
                            "FULL_INVENTORY_ROW_MISMATCH",
                            f"Appendix B claims a full inventory but has {actual} data rows; evidence item denominator is {expected}.",
                            sections=["Appendix B"],
                            line=line_number,
                        )
                    )
        for claim_code, pattern, required in LIMITING_CLAIMS:
            if not pattern.search(stripped):
                continue
            if claim_code == "ABSOLUTE_DELETE" and re.search(
                r"\bON\s+DELETE\s+(?:CASCADE|SET\s+NULL)\b",
                stripped,
                re.I,
            ):
                # An exact FK clause is positive DDL evidence about that
                # constraint, not a module-wide claim that every delete always
                # cascades or is blocked.
                continue
            bounded = bool(
                re.search(r"\b(?:design-time|supplied\s+readable|within\s+the\s+supplied|no\s+additional\s+.+\s+was\s+found)\b", stripped, re.I)
                and re.search(r"GAP-[A-Z0-9_-]+", stripped)
            )
            supported, missing = _coverage_supports_claim(required, metrics, gaps)
            if not supported and not bounded:
                errors.append(
                    _issue(
                        "UNSUPPORTED_LIMITING_CLAIM",
                        f"Line {line_number} contains unsupported {claim_code.lower().replace('_', ' ')} certainty; "
                        f"coverage is missing or unresolved for {', '.join(missing)}.",
                        line=line_number,
                    )
                )


def _validate_visual_region_specification(
    spec_text: str, facts: Sequence[Mapping[str, Any]], errors: list[dict[str, Any]]
) -> None:
    """Require rendered field/grid tables to reconcile to extracted visible regions.

    Older evidence models do not contain item_visual_placement facts, so this
    rule activates only for models produced by the region-aware compiler.
    """
    placements = [
        fact for fact in facts
        if str(fact.get("fact_kind") or "") == "item_visual_placement"
        and isinstance(fact.get("value"), Mapping)
        and fact["value"].get("rendered", fact["value"].get("visible") is not False)
    ]
    if not placements:
        return

    tab_labels = {
        str(fact.get("value", {}).get("id") or fact.get("subject", {}).get("key") or ""): str(fact.get("value", {}).get("label") or "")
        for fact in facts if str(fact.get("fact_kind") or "") == "tab"
    }
    section_match = re.search(r"^##\s+8(?:\.|\s).*$", spec_text, re.I | re.M)
    if not section_match:
        errors.append(_issue("FIELD_SPECIFICATION_SECTION_MISSING", "Specification lacks Section 8 for visible-region field coverage.", sections=["8"]))
        return
    next_section = re.search(r"^##\s+9(?:\.|\s).*$", spec_text[section_match.end():], re.I | re.M)
    section = spec_text[section_match.end(): section_match.end() + next_section.start()] if next_section else spec_text[section_match.end():]

    def heading_body(heading: str) -> str | None:
        match = re.search(rf"^###\s+{re.escape(heading)}\s*$", section, re.I | re.M)
        if not match:
            return None
        following = re.search(r"^#{2,3}\s+", section[match.end():], re.M)
        return section[match.end(): match.end() + following.start()] if following else section[match.end():]

    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for fact in placements:
        value = fact["value"]
        if value.get("presentation_shape") == "grid_column":
            key = ("Grid", str(value.get("block") or "UNKNOWN"))
        elif value.get("region_kind") == "tab_page":
            label = str(value.get("tab_label") or tab_labels.get(str(value.get("tab_page") or "")) or value.get("tab_page") or "UNKNOWN")
            key = ("Tab", label)
        else:
            key = ("Section", str(value.get("region_id") or "UNASSIGNED"))
        groups.setdefault(key, []).append(fact)

    for (kind, name), group in sorted(groups.items()):
        heading = f"{kind}: {name}"
        body = heading_body(heading)
        ids = [fact["fact_id"] for fact in group]
        if body is None:
            errors.append(_issue("VISUAL_REGION_SECTION_MISSING", f"Section 8 is missing the required heading '{heading}'.", record_ids=ids, sections=["8"]))
            continue
        if not re.search(r"^\s*\|.+\|\s*$", body, re.M):
            errors.append(_issue("VISUAL_REGION_TABLE_MISSING", f"'{heading}' has no Markdown field/column table.", record_ids=ids, sections=["8"]))
            continue
        missing = [
            f"{fact['value'].get('block')}.{fact['value'].get('item')}"
            for fact in group
            if f"{fact['value'].get('block')}.{fact['value'].get('item')}" not in body
        ]
        if missing:
            errors.append(_issue("VISUAL_REGION_ITEM_UNACCOUNTED", f"'{heading}' does not account for: {', '.join(missing)}.", record_ids=ids, sections=["8"]))


def _validate_poc_assumption_trace(
    spec_text: str,
    frontmatter: Mapping[str, str],
    gaps: Mapping[str, Mapping[str, Any]],
    errors: list[dict[str, Any]],
) -> None:
    readiness = str(frontmatter.get("poc_forward_engineering_readiness") or "").lower()
    if "ready" not in readiness:
        return
    for gap_id, gap in gaps.items():
        if str(gap.get("status") or "").lower() not in {"open", "narrowed", "reopened"}:
            continue
        assumption = gap.get("poc_assumption")
        missing: list[str] = []
        if not isinstance(assumption, Mapping):
            missing.append("poc_assumption")
            assumption = {}
        status = str(assumption.get("status") or "")
        if not status.startswith("accepted_for_current_poc"):
            missing.append("POC acceptance status")
        for key in (
            "assumption_id", "bounded_scope", "assumed_target_behavior", "acceptance_decision_id",
            "business_validation_state", "validation_owner", "acceptance_test_ids",
            "destructive_containment", "production_use",
        ):
            if not assumption.get(key):
                missing.append(key)
        if missing:
            errors.append(
                _issue(
                    "POC_ASSUMPTION_UNGOVERNED",
                    f"{gap_id} cannot support POC readiness; missing {', '.join(missing)}.",
                    record_ids=[gap_id, str(assumption.get("assumption_id") or "")],
                    sections=["19", "21", "Appendix I"],
                )
            )
            continue
        decision_id = str(assumption["acceptance_decision_id"])
        test_ids = [str(value) for value in assumption.get("acceptance_test_ids", []) if value]
        missing_spec_ids = [identifier for identifier in [decision_id, *test_ids] if identifier not in spec_text]
        if missing_spec_ids:
            errors.append(
                _issue(
                    "POC_ASSUMPTION_TRACE_MISSING",
                    f"{gap_id} references POC decision/tests absent from the specification: {', '.join(missing_spec_ids)}.",
                    record_ids=[gap_id, *missing_spec_ids],
                    sections=["19", "21", "Appendix I"],
                )
            )


def _normalize_section(value: Any) -> str | None:
    if isinstance(value, Mapping):
        value = value.get("section_key") or value.get("section")
    if value is None:
        return None
    text = str(value).strip()
    number = re.match(r"^(?:Section\s+)?(\d+)\b", text, re.I)
    if number:
        return number.group(1)
    appendix = re.match(r"^(?:###\s+)?Appendix\s+([A-J])\b", text, re.I)
    if appendix:
        return f"Appendix {appendix.group(1).upper()}"
    return text if text in CANONICAL_SECTIONS else None


def _classify_reason(value: str) -> str:
    upper = value.upper()
    if upper.startswith("PATH-") or any(word in upper for word in ("TRIGGER", "ROUTINE", "CALL", "TRANSACTION", "OPERATION")):
        return "behavior"
    if upper.startswith("GAP-"):
        return "gap"
    if "ITEM_CRUD" in upper or "/ITEM" in upper:
        return "item"
    if "BLOCK_CRUD" in upper or "/BLOCK" in upper:
        return "block"
    if any(word in upper for word in ("DDL", "DATABASE_OBJECT", "TABLE", "VIEW", "SEQUENCE", "CONSTRAINT")):
        return "ddl"
    if any(word in upper for word in ("MAPPING", "COLUMN")):
        return "mapping"
    if "MESSAGE" in upper or "VALIDATION" in upper:
        return "message"
    if upper.startswith("SRC-") or "SOURCE" in upper:
        return "source"
    if "AUDIT" in upper:
        return "audit"
    return "source"


def _delta_component(bundle: EvidenceBundle, explicit_path: str | Path | None) -> Any:
    if explicit_path:
        errors: list[dict[str, Any]] = []
        data = _read_json(Path(explicit_path).resolve(), errors)
        if errors:
            return {"_load_errors": errors, "records": []}
        return data
    return bundle.component("source_delta")


def _extract_human_conflicts(bundle: EvidenceBundle, delta: Any) -> list[dict[str, Any]]:
    values: list[Any] = []
    for holder in (bundle.aggregate, delta):
        if isinstance(holder, Mapping):
            direct = holder.get("human_decision_conflicts")
            if isinstance(direct, list):
                values.extend(direct)
            conflicts = holder.get("conflicts")
            if isinstance(conflicts, list):
                values.extend(
                    item
                    for item in conflicts
                    if isinstance(item, Mapping)
                    and str(item.get("classification") or item.get("conflict_kind") or "").lower()
                    in {"target_decision", "human_decision", "human_decision_conflict"}
                )
    result: list[dict[str, Any]] = []
    for index, value in enumerate(values):
        if isinstance(value, str):
            result.append({"conflict_id": f"HUMAN-CONFLICT-{index + 1:03d}", "description": value, "status": "open"})
        elif isinstance(value, Mapping):
            result.append(dict(value))
    return result


def _section_impact(
    current: EvidenceBundle,
    previous: EvidenceBundle | None,
    delta: Any,
    stale: bool,
    spec_sections: set[str],
    errors: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    human_conflicts = _extract_human_conflicts(current, delta)
    for conflict in human_conflicts:
        status = str(conflict.get("status") or "open").lower()
        if status not in {"resolved", "accepted"}:
            record_id = _stable_id(conflict, "conflict_id", "id")
            errors.append(
                _issue(
                    "HUMAN_DECISION_CONFLICT",
                    "Incremental evidence conflicts with a preserved human decision.",
                    record_ids=[record_id],
                )
            )

    if not stale:
        return [], sorted(spec_sections or set(CANONICAL_SECTIONS), key=_section_sort_key), human_conflicts

    impact: dict[str, set[str]] = {}
    delta_records = _records(delta)
    if isinstance(delta, Mapping):
        for raw in delta.get("affected_spec_sections", []):
            section = _normalize_section(raw)
            if section:
                reason_ids: list[str] = []
                if isinstance(raw, Mapping):
                    reason_ids = [str(item) for item in raw.get("reason_record_ids", [])]
                impact.setdefault(section, set()).update(reason_ids or ["SOURCE-DELTA"])

    incomplete_records: list[str] = []
    for index, record in enumerate(delta_records):
        change = str(record.get("change") or "changed").lower()
        if change == "unchanged":
            continue
        record_id = _stable_id(record, "delta_id", "source_id", "source_key") or f"DELTA-{index + 1}"
        explicit_sections = record.get("affected_spec_sections") or record.get("affected_section_keys") or []
        reason_ids = [
            str(item)
            for key in ("affected_fact_ids", "affected_path_ids", "affected_gap_ids", "affected_semantic_keys")
            for item in (record.get(key) or [])
        ]
        if explicit_sections:
            for raw in explicit_sections:
                section = _normalize_section(raw)
                if section:
                    impact.setdefault(section, set()).update(reason_ids or [record_id])
        elif reason_ids:
            for reason in reason_ids:
                category = _classify_reason(reason)
                for section in SECTION_IMPACT[category]:
                    impact.setdefault(section, set()).add(reason)
            for section in SECTION_IMPACT["source"]:
                impact.setdefault(section, set()).add(record_id)
        else:
            incomplete_records.append(record_id)

    if not delta_records and previous is not None:
        old_records: dict[str, tuple[str, Mapping[str, Any]]] = {}
        new_records: dict[str, tuple[str, Mapping[str, Any]]] = {}
        for component, id_keys in (
            ("normalized_evidence", ("fact_id", "id")),
            ("behavior_ledger", ("path_id", "id")),
            ("gaps", ("gap_id", "id")),
        ):
            for row in previous.records(component):
                record_id = _stable_id(row, *id_keys)
                if record_id:
                    old_records[record_id] = (component, row)
            for row in current.records(component):
                record_id = _stable_id(row, *id_keys)
                if record_id:
                    new_records[record_id] = (component, row)
        for record_id in sorted(set(old_records) | set(new_records)):
            if old_records.get(record_id) != new_records.get(record_id):
                category = _classify_reason(record_id)
                for section in SECTION_IMPACT[category]:
                    impact.setdefault(section, set()).add(record_id)

    if incomplete_records or not impact:
        errors.append(
            _issue(
                "SECTION_IMPACT_INCOMPLETE",
                "The evidence fingerprint changed but the affected specification section boundary is incomplete.",
                record_ids=incomplete_records,
            )
        )
        if not impact:
            for section in CANONICAL_SECTIONS:
                impact.setdefault(section, set()).add("UNBOUNDED-SOURCE-DELTA")

    stale_sections = [
        {
            "section_key": section,
            "reason_record_ids": sorted(reason_ids),
            "patch_required": True,
        }
        for section, reason_ids in sorted(impact.items(), key=lambda pair: _section_sort_key(pair[0]))
    ]
    known_sections = spec_sections or set(CANONICAL_SECTIONS)
    preserved = sorted(known_sections - set(impact), key=_section_sort_key)
    return stale_sections, preserved, human_conflicts


def _validate_appendices(spec_text: str, errors: list[dict[str, Any]]) -> tuple[str, str]:
    appendix_i = _section_text(spec_text, "I")
    appendix_j = _section_text(spec_text, "J")
    if not appendix_i:
        errors.append(_issue("APPENDIX_I_MISSING", "Mandatory Appendix I is missing.", sections=["Appendix I"]))
    else:
        if not re.search(r"Coverage\s+Summary", appendix_i, re.I):
            errors.append(_issue("APPENDIX_I_COVERAGE_MISSING", "Appendix I lacks its Coverage Summary.", sections=["Appendix I"]))
        if not re.search(r"(?:Missing\s+Source|Evidence\s+Gaps?)", appendix_i, re.I):
            errors.append(_issue("APPENDIX_I_GAPS_MISSING", "Appendix I lacks the missing-source/evidence-gap register.", sections=["Appendix I"]))
    if not appendix_j:
        errors.append(_issue("APPENDIX_J_MISSING", "Mandatory Appendix J is missing.", sections=["Appendix J"]))
    else:
        if not re.search(r"Run\s+ID", appendix_j, re.I) or not re.search(r"Evidence\s+fingerprint", appendix_j, re.I):
            errors.append(_issue("APPENDIX_J_HISTORY_INCOMPLETE", "Appendix J lacks run ID or evidence fingerprint history columns.", sections=["Appendix J"]))
    return appendix_i, appendix_j


def _validate_markers(
    spec_text: str,
    frontmatter: Mapping[str, str],
    stale_sections: Sequence[Mapping[str, Any]],
    errors: list[dict[str, Any]],
) -> None:
    starts = MARKER_START_RE.findall(spec_text)
    ends = MARKER_END_RE.findall(spec_text)
    start_set, end_set = set(starts), set(ends)
    for key in sorted(start_set | end_set):
        start_count, end_count = starts.count(key), ends.count(key)
        if start_count != 1 or end_count != 1:
            errors.append(
                _issue(
                    "EVIDENCE_MARKER_UNBALANCED",
                    f"Evidence marker {key!r} has {start_count} starts and {end_count} ends; exactly one pair is required.",
                )
            )
            continue
        start_match = re.search(
            rf'^<!--\s*oracle-evidence:start\s+key="{re.escape(key)}"\s*-->\s*$', spec_text, re.M
        )
        end_match = re.search(
            rf'^<!--\s*oracle-evidence:end\s+key="{re.escape(key)}"\s*-->\s*$', spec_text, re.M
        )
        if start_match and end_match and end_match.start() < start_match.end():
            errors.append(_issue("EVIDENCE_MARKER_ORDER", f"Evidence marker {key!r} ends before it starts."))

    # Markers are optional in the lightweight one-time migration workflow.
    # Enforce impacted-region boundaries only when a specification opted in by
    # including at least one marker pair.
    if not start_set:
        return

    for stale in stale_sections:
        section = str(stale.get("section_key") or "")
        expected = SECTION_MARKERS.get(section, set())
        if expected and not expected.issubset(start_set):
            missing = sorted(expected - start_set)
            errors.append(
                _issue(
                    "IMPACTED_MARKER_MISSING",
                    f"Affected {section} cannot be safely patched because marker(s) {', '.join(missing)} are absent.",
                    record_ids=stale.get("reason_record_ids", []),
                    sections=[section],
                )
            )


def _validate_local_links(
    spec_path: Path,
    spec_text: str,
    frontmatter: Mapping[str, str],
    errors: list[dict[str, Any]],
) -> None:
    candidates: list[tuple[str, str]] = []
    for match in re.finditer(r"!?\[[^\]]*\]\((?:<([^>]+)>|([^\s\)]+))(?:\s+['\"][^\)]*['\"])?\)", spec_text):
        candidates.append((match.group(1) or match.group(2), "Markdown link"))
    for match in re.finditer(r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"']", spec_text, re.I):
        candidates.append((match.group(1), "image"))
    for key in ("legacy_ui_screenshot", "source_manifest", "evidence_model"):
        value = frontmatter.get(key)
        if value:
            candidates.append((value, key))

    seen: set[str] = set()
    for raw, kind in candidates:
        target = raw.strip()
        if target in seen:
            continue
        seen.add(target)
        if not target or any(char in target for char in "<>"):
            continue
        if re.match(r"^(?:https?|mailto|data):", target, re.I) or target.startswith("#"):
            continue
        target = unquote(target.split("#", 1)[0])
        target = re.sub(r":\d+$", "", target)
        candidate = Path(target)
        resolved = candidate if candidate.is_absolute() else (spec_path.parent / candidate).resolve()
        if not resolved.exists():
            errors.append(
                _issue(
                    "SPEC_LOCAL_LINK_BROKEN",
                    f"{kind} target does not exist: {raw}",
                )
            )


def _canonical_sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def run_guard(
    evidence: str | Path,
    spec: str | Path,
    *,
    previous_evidence: str | Path | None = None,
    source_delta: str | Path | None = None,
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    current = load_evidence(evidence)
    previous = load_evidence(previous_evidence) if previous_evidence else None
    _validate_metadata(current, errors, warnings)
    if previous is not None:
        _validate_metadata(previous, errors, warnings)

    spec_path = Path(spec).resolve()
    try:
        spec_text = spec_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        errors.append(_issue("SPEC_READ_FAILED", f"Cannot read {spec_path}: {exc}"))
        spec_text = ""
    frontmatter = _parse_frontmatter(spec_text)
    spec_package = _load_spec_package(spec_path, spec_text, errors)
    package_text = "\n".join(text for _, text in spec_package.values())
    _validate_complete_specification_contract(current, spec_text, frontmatter, errors, package_text)
    _validate_spec_package(spec_package, frontmatter, errors)
    appendix_i, _ = _validate_appendices(spec_text, errors)
    current_modules = _module_ids(current)
    module_id = next(iter(current_modules), str(frontmatter.get("module_id") or "UNKNOWN").upper())
    spec_module = str(frontmatter.get("module_id") or "").upper()
    if not spec_module:
        errors.append(_issue("SPEC_MODULE_MISSING", "Specification front matter is missing module_id."))
    elif current_modules and spec_module not in current_modules:
        errors.append(
            _issue(
                "SPEC_MODULE_MISMATCH",
                f"Specification module {spec_module} does not match evidence module {module_id}.",
            )
        )

    current_evidence_fps, current_manifest_fps = _fingerprints(current)
    current_fingerprints = current_evidence_fps | current_manifest_fps
    spec_fingerprint = str(frontmatter.get("evidence_fingerprint") or "").lower()
    if not SHA256_RE.fullmatch(spec_fingerprint):
        errors.append(_issue("SPEC_FINGERPRINT_INVALID", "Specification front matter lacks a valid evidence_fingerprint."))
    stale = bool(current_fingerprints and spec_fingerprint not in current_fingerprints)
    if stale:
        errors.append(
            _issue(
                "SPEC_STALE_FINGERPRINT",
                "Specification evidence_fingerprint does not match the current evidence run.",
                sections=["1", "Appendix J"],
            )
        )

    previous_fingerprints: set[str] = set()
    if previous is not None:
        previous_fingerprints = set().union(*_fingerprints(previous))
    delta = _delta_component(current, source_delta)
    if isinstance(delta, Mapping) and delta.get("_load_errors"):
        errors.extend(delta["_load_errors"])
    if previous is not None and current_fingerprints != previous_fingerprints and not _records(delta) and not (
        isinstance(delta, Mapping) and delta.get("affected_spec_sections")
    ):
        warnings.append(
            _issue(
                "SOURCE_DELTA_NOT_SUPPLIED",
                "Evidence fingerprint changed without source-delta records; record comparison will be used where possible.",
            )
        )

    current_gaps, precise_gap_ids = _validate_gaps(current, previous, appendix_i, errors, warnings)
    metrics, gates = _validate_coverage(current, current_gaps, precise_gap_ids, errors, warnings)
    _validate_spec_claims(spec_text, metrics, current_gaps, errors)
    _validate_visual_region_specification(spec_text, current.records("normalized_evidence"), errors)
    _validate_poc_assumption_trace(spec_text, frontmatter, current_gaps, errors)

    spec_sections = _spec_sections(spec_text)
    stale_sections, preserved_sections, human_conflicts = _section_impact(
        current, previous, delta, stale, spec_sections, errors
    )
    _validate_markers(spec_text, frontmatter, stale_sections, errors)
    for _, (document_path, document_text) in spec_package.items():
        _validate_local_links(document_path, document_text, _parse_frontmatter(document_text), errors)

    failing_gate_ids = [gate["gate_id"] for gate in gates if gate["status"] == "fail"]
    for gate_id in failing_gate_ids:
        if not any(issue["code"] == "READINESS_GATE_FAILED" and gate_id in issue["record_ids"] for issue in errors):
            errors.append(
                _issue(
                    "READINESS_GATE_FAILED",
                    f"{gate_id} failed.",
                    record_ids=[gate_id],
                )
            )

    errors = _deduplicate_issues(errors)
    warnings = _deduplicate_issues(warnings)
    reason_record_ids = sorted(
        {
            record_id
            for issue in errors + warnings
            for record_id in issue.get("record_ids", [])
        }
        | {
            record_id
            for section in stale_sections
            for record_id in section.get("reason_record_ids", [])
        }
    )
    result = {
        "schema_version": "1.0",
        "guard_version": TOOL_VERSION,
        "module_id": module_id,
        "evidence_path": str(Path(evidence).resolve()),
        "spec_path": str(spec_path),
        "evidence_fingerprint": (
            sorted(current_evidence_fps)[0]
            if current_evidence_fps
            else sorted(current_manifest_fps)[0]
            if current_manifest_fps
            else None
        ),
        "spec_evidence_fingerprint": spec_fingerprint or None,
        "validation_status": "fail" if errors else "pass_with_registered_gaps" if any(
            str(gap.get("status") or "").lower() in {"open", "narrowed", "reopened"}
            for gap in current_gaps.values()
        ) else "pass",
        "errors": errors,
        "warnings": warnings,
        "readiness_gate_results": gates,
        "stale_sections": stale_sections,
        "preserved_sections": preserved_sections,
        "reason_record_ids": reason_record_ids,
        "human_decision_conflicts": human_conflicts,
        "coverage_summary": metrics,
        "gap_summary": {
            "total": len(current_gaps),
            "precisely_registered": len(precise_gap_ids),
            "open": sum(
                str(gap.get("status") or "").lower() in {"open", "narrowed", "reopened"}
                for gap in current_gaps.values()
            ),
            "resolved": sum(str(gap.get("status") or "").lower() == "resolved" for gap in current_gaps.values()),
        },
    }
    result["result_sha256"] = _canonical_sha({key: value for key, value in result.items() if key != "result_sha256"})
    return result


def _deduplicate_issues(issues: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for issue in issues:
        key = json.dumps(issue, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            seen.add(key)
            result.append(issue)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate normalized Oracle Forms evidence and its Markdown specification."
    )
    parser.add_argument(
        "--evidence",
        required=True,
        help="Current evidence-model.json or module/run evidence directory.",
    )
    parser.add_argument("--spec", required=True, help="Markdown specification to validate.")
    parser.add_argument(
        "--previous-evidence",
        help="Optional prior evidence-model.json or module/run evidence directory.",
    )
    parser.add_argument(
        "--source-delta",
        help="Optional source-delta.json. Defaults to the current evidence artifact when present.",
    )
    parser.add_argument("--output", help="Optional JSON output path; JSON is always written to stdout.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_guard(
        args.evidence,
        args.spec,
        previous_evidence=args.previous_evidence,
        source_delta=args.source_delta,
    )
    serialized = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
