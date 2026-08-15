#!/usr/bin/env python3
"""Prepare, scaffold, and validate an Oracle evidence semantic review overlay."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote


VERSION = "1.0.0"
CHILD_KEYS = ("operation_details", "decoded_source", "database_reference")
ALLOWED_TYPES = {
    "ambiguity",
    "apparent_conflict",
    "cross_fact_dependency",
    "runtime_context_gap",
    "under_specified_behavior",
    "evidence_quality",
    "extraction_defect",
}
ALLOWED_SEVERITIES = {"high", "medium", "low"}
ALLOWED_STATUSES = {
    "resolved_automatically",
    "proposed_for_human_review",
    "blocked_by_missing_evidence",
    "accepted_as_legacy_behavior",
    "superseded",
    "stale",
}
ALLOWED_REVIEW_STATUSES = {
    "in_progress",
    "reviewed",
    "reviewed_with_open_findings",
    "stale",
}
REQUIRED_SECTIONS = (
    "1. Review Control",
    "2. Review Scope And Method",
    "3. Semantic Findings Register",
    "4. Finding Details",
    "5. Automatically Reconciled Interpretations",
    "6. Human Review Queue",
    "7. Missing Runtime Context",
    "8. Review Coverage And Limitations",
    "9. Downstream Handoff",
    "10. Review History",
)
REQUIRED_FINDING_HEADINGS = (
    "Facts In Relationship Or Tension",
    "Source References",
    "Analysis",
    "Proposed Resolution",
    "Applied Interpretation",
    "Human Review Needed",
    "Downstream Evidence Impact",
)


class ReviewError(RuntimeError):
    pass


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ReviewError(f"Cannot read UTF-8 Markdown file {path}: {exc}") from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        raise ReviewError("Markdown file is missing YAML frontmatter.")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ReviewError("Markdown frontmatter is not terminated.")
    result: dict[str, str] = {}
    for raw in text[4:end].splitlines():
        if not raw.strip() or raw.lstrip().startswith("#") or ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def find_project_repo(path: Path) -> Path:
    current = path.resolve().parent
    for candidate in (current, *current.parents):
        if (candidate / "project.yaml").is_file():
            return candidate
    raise ReviewError(f"Cannot find project.yaml above {path}.")


def ensure_within(path: Path, root: Path, label: str) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ReviewError(f"{label} escapes the selected project repository: {path}") from exc


def extract_json_fences(text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for match in re.findall(r"~~~json\s*\n(.*?)\n~~~", text, re.I | re.S):
        try:
            value = json.loads(match)
        except json.JSONDecodeError as exc:
            raise ReviewError(f"Invalid JSON evidence block: {exc}") from exc
        if isinstance(value, dict):
            records.append(value)
    return records


def marker_body(text: str, key: str) -> str:
    start_token = f'<!-- oracle-evidence:start key="{key}" -->'
    end_token = f'<!-- oracle-evidence:end key="{key}" -->'
    start = text.find(start_token)
    end = text.find(end_token, start + len(start_token)) if start >= 0 else -1
    return text[start + len(start_token) : end] if start >= 0 and end >= 0 else ""


def markdown_data_rows(text: str) -> list[list[str]]:
    result: list[list[str]] = []
    for line in text.splitlines():
        if not line.startswith("| ") or re.match(r"^\|\s*-", line):
            continue
        result.append([cell.strip() for cell in line.strip("|").split("|")])
    return result


def package_hash(files: Iterable[dict[str, Any]]) -> str:
    payload = "\n".join(
        f"{record['name']}\0{record['sha256']}" for record in sorted(files, key=lambda item: item["name"])
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def resolve_package(spec_path: Path) -> dict[str, Any]:
    spec_path = spec_path.resolve()
    if not spec_path.is_file():
        raise ReviewError(f"Master specification does not exist: {spec_path}")
    repo = find_project_repo(spec_path)
    ensure_within(spec_path, repo, "Master specification")
    expected_root = (repo / "evidence" / "features").resolve()
    ensure_within(spec_path, expected_root, "Master specification")

    project_text = read_text(repo / "project.yaml")
    if not re.search(r"^objective_type:\s*[\"']?legacy_modernization[\"']?\s*$", project_text, re.M):
        raise ReviewError("project.yaml must declare objective_type: legacy_modernization.")

    master_text = read_text(spec_path)
    master_fm = parse_frontmatter(master_text)
    if master_fm.get("artifact_kind") != "legacy_evidence_specification":
        raise ReviewError("Input is not a legacy_evidence_specification master.")
    module_id = master_fm.get("module_id", "").upper()
    evidence_id = master_fm.get("module_evidence_id", "")
    fingerprint = master_fm.get("evidence_fingerprint", "")
    if not module_id or evidence_id != f"MOD-{module_id}" or not re.fullmatch(r"[0-9a-fA-F]{64}", fingerprint):
        raise ReviewError("Master module identity or evidence fingerprint is invalid.")

    package_paths = {"master": spec_path}
    package_texts = {"master": master_text}
    for key in CHILD_KEYS:
        filename = master_fm.get(key, "")
        if not filename or Path(filename).name != filename:
            raise ReviewError(f"Master has an invalid or missing {key} link.")
        child = (spec_path.parent / filename).resolve()
        if child.parent != spec_path.parent or not child.is_file():
            raise ReviewError(f"Required child is missing or outside the feature package: {child}")
        child_text = read_text(child)
        child_fm = parse_frontmatter(child_text)
        expected_kind = key
        mismatches = []
        for field, expected in (
            ("artifact_kind", "legacy_evidence_reference"),
            ("reference_kind", expected_kind),
            ("module_id", module_id),
            ("module_evidence_id", evidence_id),
            ("evidence_fingerprint", fingerprint),
            ("parent_specification", spec_path.name),
        ):
            if child_fm.get(field, "").upper() != expected.upper():
                mismatches.append(field)
        if mismatches:
            raise ReviewError(f"Child {child.name} mismatches master metadata: {', '.join(mismatches)}")
        package_paths[key] = child
        package_texts[key] = child_text

    file_records = [
        {
            "role": role,
            "name": path.name,
            "path": str(path),
            "size": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for role, path in package_paths.items()
    ]
    operation_records = extract_json_fences(package_texts["operation_details"])
    database_records = extract_json_fences(package_texts["database_reference"])
    decoded_hashes = re.findall(
        r"Decoded source SHA-256:\s*`([0-9a-fA-F]{64})`", package_texts["decoded_source"]
    )
    operation_counts = Counter(str(record.get("operation") or "unknown") for record in operation_records)
    unresolved_calls = sorted(
        {
            str(call)
            for record in operation_records
            for call in record.get("unresolved_calls", [])
            if call
        }
    )
    transaction_unknown_paths = 0
    for record in operation_records:
        transaction = record.get("transaction") or {}
        if isinstance(transaction, dict) and any(
            str(transaction.get(key) or "unknown").lower() == "unknown"
            for key in ("boundary", "commit_owner", "rollback_behavior", "concurrency_behavior")
        ):
            transaction_unknown_paths += 1

    screenshot_links = sorted(set(re.findall(r"!\[[^\]]*\]\(([^)]+)\)", master_text)))
    gaps = markdown_data_rows(marker_body(master_text, "missing-sources"))
    if gaps and gaps[0] and gaps[0][0] == "Subject":
        gaps = gaps[1:]
    markers = re.findall(r'oracle-evidence:start key="([^"]+)"', master_text)
    comparison_body = marker_body(master_text, "technical-notes")
    comparison_rows = [
        row
        for row in markdown_data_rows(comparison_body)
        if row and row[0] != "Source-supported prior anchor"
    ]
    title_match = re.search(r"^#\s+(.+?)(?:\s+[—-]\s+Legacy Evidence Specification)?\s*$", master_text, re.M)
    feature_slug = spec_path.parent.name
    review_path = spec_path.parent / f"{module_id.lower()}-semantic-review.md"

    return {
        "schema_version": "1.0",
        "generator": "oracle_semantic_review",
        "generator_version": VERSION,
        "project_repo": str(repo),
        "feature_slug": feature_slug,
        "module_id": module_id,
        "module_evidence_id": evidence_id,
        "module_title": title_match.group(1).strip() if title_match else module_id,
        "evidence_fingerprint": fingerprint.lower(),
        "master_specification": str(spec_path),
        "expected_review_path": str(review_path),
        "package_files": file_records,
        "package_sha256": package_hash(file_records),
        "child_names": {key: package_paths[key].name for key in CHILD_KEYS},
        "metrics": {
            "operation_paths": len(operation_records),
            "operations_by_type": dict(sorted(operation_counts.items())),
            "decoded_units": len(decoded_hashes),
            "unique_decoded_source_hashes": len({value.lower() for value in decoded_hashes}),
            "database_objects": len(database_records),
            "controlled_sections": len(markers),
            "screenshots": len(screenshot_links),
            "open_extraction_gaps": len(gaps),
            "comparison_anchors": len(comparison_rows),
            "unresolved_call_names": len(unresolved_calls),
            "transaction_unknown_paths": transaction_unknown_paths,
            "explicit_branch_message_bindings": master_text.count(
                "active decoded IF/ELSIF branch in the same unit"
            ),
        },
        "review_focus": {
            "unresolved_calls": unresolved_calls,
            "gap_kinds": dict(sorted(Counter(row[1].split("/")[0].strip() for row in gaps if len(row) > 1).items())),
        },
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def command_prepare(args: argparse.Namespace) -> int:
    context = resolve_package(Path(args.spec))
    write_json(Path(args.output), context)
    print(json.dumps({
        "status": "prepared",
        "module_id": context["module_id"],
        "feature_slug": context["feature_slug"],
        "package_sha256": context["package_sha256"],
        "expected_review_path": context["expected_review_path"],
        "metrics": context["metrics"],
    }, indent=2))
    return 0


def load_context(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewError(f"Cannot read review context {path}: {exc}") from exc
    if value.get("generator") != "oracle_semantic_review":
        raise ReviewError("Context was not produced by oracle_semantic_review.")
    return value


def command_scaffold(args: argparse.Namespace) -> int:
    context = load_context(Path(args.context))
    output = Path(args.output).resolve()
    expected = Path(context["expected_review_path"]).resolve()
    if output != expected:
        raise ReviewError(f"Review must be colocated at {expected}, not {output}.")
    if output.exists():
        raise ReviewError(f"Review already exists; reconcile it instead of overwriting: {output}")
    template = read_text(Path(__file__).resolve().parent.parent / "references" / "semantic-review-template.md")
    metrics = context["metrics"]
    replacements = {
        "MODULE_ID": context["module_id"],
        "MODULE_EVIDENCE_ID": context["module_evidence_id"],
        "EVIDENCE_FINGERPRINT": context["evidence_fingerprint"],
        "PACKAGE_SHA256": context["package_sha256"],
        "PARENT_SPECIFICATION": Path(context["master_specification"]).name,
        "OPERATION_DETAILS": context["child_names"]["operation_details"],
        "DECODED_SOURCE": context["child_names"]["decoded_source"],
        "DATABASE_REFERENCE": context["child_names"]["database_reference"],
        "REVIEWED_AT": date.today().isoformat(),
        "OPERATION_COUNT": str(metrics["operation_paths"]),
        "DECODED_UNIT_COUNT": str(metrics["decoded_units"]),
        "DATABASE_OBJECT_COUNT": str(metrics["database_objects"]),
        "CONTROLLED_SECTION_COUNT": str(metrics["controlled_sections"]),
        "SCREENSHOT_COUNT": str(metrics["screenshots"]),
        "OPEN_GAP_COUNT": str(metrics["open_extraction_gaps"]),
    }
    for key, value in replacements.items():
        template = template.replace("{{" + key + "}}", value)
    unresolved = re.findall(r"{{[A-Z0-9_]+}}", template)
    if unresolved:
        raise ReviewError(f"Template has unresolved placeholders: {', '.join(sorted(set(unresolved)))}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(template, encoding="utf-8")
    print(json.dumps({"status": "scaffolded", "review": str(output)}, indent=2))
    return 0


def field_value(block: str, field: str) -> str:
    match = re.search(rf"^{re.escape(field)}:\s*([^\n]+)\s*$", block, re.M)
    return match.group(1).strip() if match else ""


def section_content(block: str, heading: str) -> str:
    match = re.search(
        rf"^####\s+{re.escape(heading)}\s*$\n(.*?)(?=^####\s+|^###\s+|^##\s+|\Z)",
        block,
        re.M | re.S,
    )
    return match.group(1).strip() if match else ""


def strip_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def finding_blocks(text: str, module_id: str) -> list[tuple[str, str]]:
    clean = strip_comments(text)
    pattern = re.compile(
        rf"^###\s+`?(MOD-{re.escape(module_id)}#review\.[a-z0-9][a-z0-9.-]*)`?\s*$\n(.*?)(?=^###\s+|^##\s+|\Z)",
        re.M | re.S,
    )
    return [(match.group(1), match.group(2)) for match in pattern.finditer(clean)]


def validate_links(review_path: Path, text: str, repo: Path) -> list[str]:
    errors: list[str] = []
    for target in re.findall(r"!?(?:\[[^\]]*\])\(([^)]+)\)", strip_comments(text)):
        target = target.strip().strip("<>")
        if not target or target.startswith(("#", "http://", "https://", "mailto:")):
            continue
        raw_path = unquote(target.split("#", 1)[0])
        if not raw_path:
            continue
        candidate = (review_path.parent / raw_path).resolve()
        try:
            candidate.relative_to(repo.resolve())
        except ValueError:
            errors.append(f"Local link escapes project repository: {target}")
            continue
        if not candidate.exists():
            errors.append(f"Broken local link: {target}")
    return errors


def validate_review(spec: Path, review: Path, context_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    context = load_context(context_path)
    current = resolve_package(spec)
    if Path(context["master_specification"]).resolve() != spec.resolve():
        errors.append("Context belongs to another master specification.")
    if context["package_sha256"] != current["package_sha256"]:
        errors.append("Extraction package changed after review preparation.")
    for previous in context.get("package_files", []):
        present = next((item for item in current["package_files"] if item["role"] == previous["role"]), None)
        if not present or present["sha256"] != previous["sha256"]:
            errors.append(f"Extraction package file changed: {previous['name']}")

    expected_review = Path(current["expected_review_path"]).resolve()
    if review.resolve() != expected_review:
        errors.append(f"Review must be colocated at {expected_review}.")
    if not review.is_file():
        errors.append(f"Review does not exist: {review}")
        return {"status": "fail", "errors": errors, "warnings": warnings}

    review_text = read_text(review)
    try:
        fm = parse_frontmatter(review_text)
    except ReviewError as exc:
        errors.append(str(exc))
        fm = {}
    expected_fields = {
        "artifact_kind": "legacy_evidence_semantic_review",
        "authority": "review_overlay_not_extracted_fact",
        "module_id": current["module_id"],
        "module_evidence_id": current["module_evidence_id"],
        "evidence_fingerprint": current["evidence_fingerprint"],
        "reviewed_package_sha256": current["package_sha256"],
        "parent_specification": Path(current["master_specification"]).name,
    }
    for key, expected in expected_fields.items():
        if fm.get(key, "").lower() != expected.lower():
            errors.append(f"Review frontmatter {key} must be {expected!r}.")
    if fm.get("review_status") not in ALLOWED_REVIEW_STATUSES:
        errors.append(f"Unsupported review_status: {fm.get('review_status')!r}.")
    if fm.get("review_status") in {"reviewed", "reviewed_with_open_findings"} and "review pending" in review_text.lower():
        errors.append("Completed review still contains review-pending placeholders.")

    for heading in REQUIRED_SECTIONS:
        if not re.search(rf"^##\s+{re.escape(heading)}\s*$", review_text, re.M):
            errors.append(f"Missing required section: {heading}")

    findings = finding_blocks(review_text, current["module_id"])
    keys = [key for key, _ in findings]
    for key, count in Counter(keys).items():
        if count > 1:
            errors.append(f"Duplicate semantic review key: {key}")
    finding_summary: list[dict[str, str]] = []
    for key, block in findings:
        finding_type = field_value(block, "Type")
        severity = field_value(block, "Severity")
        status = field_value(block, "Status")
        confidence = field_value(block, "Confidence")
        if finding_type not in ALLOWED_TYPES:
            errors.append(f"{key} has unsupported Type: {finding_type!r}.")
        if severity not in ALLOWED_SEVERITIES:
            errors.append(f"{key} has unsupported Severity: {severity!r}.")
        if status not in ALLOWED_STATUSES:
            errors.append(f"{key} has unsupported Status: {status!r}.")
        if confidence not in {"high", "medium", "low"}:
            errors.append(f"{key} has unsupported Confidence: {confidence!r}.")
        for heading in REQUIRED_FINDING_HEADINGS:
            content = section_content(block, heading)
            if not content or content.upper() == "TBD":
                errors.append(f"{key} is missing substantive {heading} content.")
        sources = section_content(block, "Source References")
        if not re.search(r"\[[^\]]+\]\([^)]+\)", sources):
            errors.append(f"{key} requires at least one Markdown source link.")
        if status == "resolved_automatically":
            applied = section_content(block, "Applied Interpretation")
            human = section_content(block, "Human Review Needed")
            if applied.lower() in {"not applied", "none", "tbd"}:
                errors.append(f"{key} is automatically resolved but has no applied interpretation.")
            if human.lower() not in {"none", "none."}:
                warnings.append(f"{key} is automatically resolved but still requests human review.")
        finding_summary.append({"key": key, "type": finding_type, "severity": severity, "status": status})

    register_body_match = re.search(
        r"^##\s+3\. Semantic Findings Register\s*$\n(.*?)(?=^##\s+4\.)",
        review_text,
        re.M | re.S,
    )
    register_body = register_body_match.group(1) if register_body_match else ""
    for key in keys:
        if key not in register_body:
            errors.append(f"Finding detail is missing from the register: {key}")

    repo = Path(current["project_repo"])
    errors.extend(validate_links(review, review_text, repo))
    if re.search(r"^review_status:\s*(?:approved|baselined)\s*$", review_text, re.M | re.I):
        errors.append("Semantic evidence review cannot claim approval or baseline status.")
    if re.search(r"^##\s+.*Target (?:Requirements|Design|Tests?)", review_text, re.M | re.I):
        errors.append("Semantic evidence review contains a prohibited target-artifact section.")

    counts = {
        "total": len(finding_summary),
        "by_type": dict(sorted(Counter(item["type"] for item in finding_summary).items())),
        "by_severity": dict(sorted(Counter(item["severity"] for item in finding_summary).items())),
        "by_status": dict(sorted(Counter(item["status"] for item in finding_summary).items())),
    }
    return {
        "schema_version": "1.0",
        "validator_version": VERSION,
        "status": "pass" if not errors else "fail",
        "module_id": current["module_id"],
        "feature_slug": current["feature_slug"],
        "package_sha256": current["package_sha256"],
        "extraction_unchanged": context["package_sha256"] == current["package_sha256"],
        "review": str(review.resolve()),
        "finding_counts": counts,
        "errors": errors,
        "warnings": warnings,
    }


def command_validate(args: argparse.Namespace) -> int:
    result = validate_review(Path(args.spec), Path(args.review), Path(args.context))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "pass" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare", help="Verify and fingerprint an extracted evidence package.")
    prepare.add_argument("--spec", required=True, help="Path to the package master specification.")
    prepare.add_argument("--output", required=True, help="Path for the temporary review context JSON.")
    prepare.set_defaults(func=command_prepare)
    scaffold = subparsers.add_parser("scaffold", help="Create a new colocated semantic review scaffold.")
    scaffold.add_argument("--context", required=True, help="Prepared context JSON.")
    scaffold.add_argument("--output", required=True, help="Expected semantic-review Markdown path.")
    scaffold.set_defaults(func=command_scaffold)
    validate = subparsers.add_parser("validate", help="Validate review structure and package immutability.")
    validate.add_argument("--spec", required=True, help="Path to the package master specification.")
    validate.add_argument("--review", required=True, help="Path to the semantic review Markdown file.")
    validate.add_argument("--context", required=True, help="Prepared context JSON.")
    validate.set_defaults(func=command_validate)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except ReviewError as exc:
        print(json.dumps({"status": "fail", "errors": [str(exc)]}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
