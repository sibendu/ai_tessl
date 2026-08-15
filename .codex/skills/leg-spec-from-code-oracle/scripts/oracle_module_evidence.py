#!/usr/bin/env python3
"""Compile deterministic, source-traceable evidence for one Oracle Forms module.

The compiler deliberately separates extraction from specification prose.  It
records what the supplied artifacts establish, what is unreadable or missing,
and which behavior slices must be revisited after an incremental source update.
It uses only the Python standard library so it can run in constrained workflow
runners as well as local development environments.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

from oracle_markdown_renderer import (
    merge_evidence_regions,
    render_evidence_markdown_package,
    render_markdown_specification as render_complete_markdown_specification,
    validate_markdown_contract,
)


SCHEMA_VERSION = "oracle-module-evidence/1.0"
EXTRACTOR_NAME = "oracle_module_evidence"
EXTRACTOR_VERSION = "1.7.0"
CANONICAL_SPEC_SECTIONS = [str(number) for number in range(1, 23)] + [f"Appendix {letter}" for letter in "ABCDEFGHIJ"]

FOLDER_ALIASES = {
    "form": ("form", "forms", "form_extraction"),
    "ddl": ("ddl",),
    "ui": ("ui", "screenshots", "images"),
}
FORM_EXTENSIONS = {
    ".xml", ".fmt", ".pld", ".err", ".fmb", ".fmx", ".pll", ".olb",
    ".mmb", ".mmx", ".sql", ".pls", ".pks", ".pkb", ".prc", ".fnc",
    ".trg", ".vw", ".txt",
}
TEXT_FORM_EXTENSIONS = {
    ".xml", ".fmt", ".pld", ".err", ".sql", ".pls", ".pks", ".pkb",
    ".prc", ".fnc", ".trg", ".vw", ".txt",
}
BINARY_FORM_EXTENSIONS = {".fmb", ".fmx", ".pll", ".olb", ".mmb", ".mmx"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}

SCREENSHOT_STOP_WORDS = {
    "form", "forms", "oracle", "screen", "screenshot", "image", "legacy", "page",
}


def screenshot_association(
    path: str,
    module_id: str,
    title: str,
) -> Optional[dict[str, Any]]:
    """Return a conservative, explainable association for a module screenshot."""
    stem = Path(path).stem

    def normalized(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()

    def tokens(value: str) -> set[str]:
        return {
            token
            for token in normalized(value).split()
            if len(token) > 1 and token not in SCREENSHOT_STOP_WORDS
        }

    stem_normalized = normalized(stem)
    module_normalized = normalized(module_id)
    title_normalized = normalized(title)
    stem_tokens = tokens(stem)
    title_tokens = tokens(title)
    bases: list[str] = []
    scores: list[float] = []

    if stem_normalized == module_normalized:
        bases.append("exact_filename_to_module_id")
        scores.append(1.0)
    elif module_normalized and module_normalized in stem_normalized.replace(" ", ""):
        bases.append("filename_contains_module_id")
        scores.append(0.93)
    if title_normalized and stem_normalized == title_normalized:
        bases.append("exact_filename_to_form_title")
        scores.append(0.99)
    elif title_normalized and (
        title_normalized in stem_normalized or stem_normalized in title_normalized
    ):
        bases.append("filename_contains_form_title")
        scores.append(0.86)
    if title_tokens and stem_tokens:
        overlap = len(title_tokens & stem_tokens) / len(title_tokens)
        if overlap >= 0.4:
            bases.append(f"title_token_overlap_{overlap:.2f}")
            scores.append(0.55 + (0.35 * overlap))

    if not scores or max(scores) < 0.55:
        return None
    score = max(scores)
    return {
        "association_basis": ", ".join(bases),
        "association_score": round(score, 3),
        "association_confidence": "high" if score >= 0.85 else "medium" if score >= 0.70 else "plausible",
        "matched_title": title or None,
        "matched_module_id": module_id,
    }

SQL_NAME = r'(?:"?[A-Z][A-Z0-9_$#]*"?\s*\.\s*)?"?[A-Z][A-Z0-9_$#]*"?'
COMMON_SQL_OBJECTS = {
    "DUAL", "SYS.DUAL", "SQLCODE", "SQLERRM", "ROWID", "ROWNUM", "SYSDATE",
    "USER", "TRUE", "FALSE", "NULL", "CAT",
}
CALL_EXCLUSIONS = {
    "IF", "ELSIF", "ELSE", "CASE", "LOOP", "FOR", "WHILE", "SELECT", "INSERT",
    "UPDATE", "DELETE", "MERGE", "VALUES", "INTO", "FROM", "WHERE", "EXISTS",
    "COUNT", "SUM", "MIN", "MAX", "AVG", "NVL", "NVL2", "DECODE", "TO_CHAR",
    "TO_DATE", "TO_NUMBER", "TRUNC", "ROUND", "SUBSTR", "INSTR", "UPPER", "LOWER",
    "REPLACE", "LTRIM", "RTRIM", "LENGTH", "CHR", "ASCII", "ABS", "MOD", "SIGN",
    "GREATEST", "LEAST", "COALESCE", "CAST", "OPEN", "CLOSE", "FETCH", "RETURN",
    "RAISE", "PRAGMA", "PROCEDURE", "FUNCTION", "PACKAGE", "BEGIN", "END",
    "ADD_MONTHS", "LAST_DAY", "LPAD", "RPAD", "TRANSLATE", "NUMBER", "VARCHAR2",
    "AND", "OR", "NOT", "IN", "EXCEPTION_INIT", "ID_NULL",
}
FORMS_BUILTINS = {
    "COMMIT_FORM", "CLEAR_FORM", "CLEAR_BLOCK", "CREATE_RECORD", "INSERT_RECORD", "DELETE_RECORD",
    "DO_KEY", "ENTER_QUERY", "EXECUTE_QUERY", "EXIT_FORM", "FIRST_RECORD", "GO_BLOCK",
    "GO_ITEM", "LAST_RECORD", "LIST_VALUES", "MESSAGE", "NEXT_BLOCK", "NEXT_ITEM",
    "NEXT_RECORD", "PREVIOUS_BLOCK", "PREVIOUS_ITEM", "PREVIOUS_RECORD", "QUERY_PARAMETER",
    "ROLLBACK", "SET_BLOCK_PROPERTY", "SET_FORM_PROPERTY", "SET_ITEM_PROPERTY",
    "SET_RECORD_PROPERTY", "SHOW_ALERT", "SYNCHRONIZE", "VALIDATE", "NAME_IN", "COPY",
    "FIND_BLOCK", "FIND_ITEM", "GET_ITEM_PROPERTY", "GET_BLOCK_PROPERTY", "EXECUTE_TRIGGER",
    "CALL_FORM", "OPEN_FORM", "NEW_FORM", "RUN_PRODUCT", "HOST",
    "ADD_GROUP_ROW", "ADD_PARAMETER", "CREATE_PARAMETER_LIST", "DESTROY_PARAMETER_LIST",
    "DEFAULT_VALUE", "ERASE", "FIND_COLUMN", "FIND_GROUP", "FIND_MENU_ITEM",
    "FIND_REPORT_OBJECT", "FIND_WINDOW", "GET_APPLICATION_PROPERTY", "GET_GROUP_CHAR_CELL",
    "GET_GROUP_ROW_COUNT", "GET_PARAMETER_LIST", "GET_VIEW_PROPERTY", "GET_WINDOW_PROPERTY",
    "GO_FORM", "ISSUE_ROLLBACK", "REPORT_OBJECT_STATUS", "RUN_REPORT_OBJECT",
    "SET_ALERT_BUTTON_PROPERTY", "SET_ALERT_PROPERTY", "SET_APPLICATION_PROPERTY",
    "SET_GROUP_CHAR_CELL", "SET_REPORT_OBJECT_PROPERTY", "SET_WINDOW_PROPERTY", "SHOW_WINDOW",
}

OPERATION_EVENTS = {
    "query": {"PRE-QUERY", "POST-QUERY", "KEY-EXEQRY", "KEY-ENTQRY", "KEY-CQUERY"},
    "create": {"PRE-INSERT", "ON-INSERT", "POST-INSERT", "WHEN-CREATE-RECORD"},
    "update": {"PRE-UPDATE", "ON-UPDATE", "POST-UPDATE"},
    "delete": {"PRE-DELETE", "ON-DELETE", "POST-DELETE", "KEY-DELREC"},
    "save": {"PRE-COMMIT", "ON-COMMIT", "POST-COMMIT", "KEY-COMMIT"},
    "validation": {"WHEN-VALIDATE-ITEM", "WHEN-VALIDATE-RECORD", "WHEN-VALIDATE-FORM"},
    "custom_action": {"WHEN-BUTTON-PRESSED"},
}
OPERATION_ROUTINE_HINTS = {
    "query": ("QRY", "QUERY", "POST_QUERY", "PRE_QUERY"),
    "create": ("INS", "INSERT", "CREATE"),
    "update": ("UPD", "UPDATE"),
    "delete": ("DEL", "DELETE", "CHK_", "WRN_"),
    "save": ("COMMIT", "SAVE"),
    "validation": ("VALID", "CHECK", "CHK_", "ERROR"),
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")


def stable_id(prefix: str, *parts: Any) -> str:
    canonical = "\x1f".join("" if part is None else str(part).strip() for part in parts)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16].upper()
    return f"{prefix}-{digest}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_text(path: Path) -> tuple[str, str]:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace"), "latin-1-replace"


def decode_entities(value: Any) -> Optional[str]:
    """Decode Forms2XML values until stable, including doubly escaped PL/SQL."""
    if value is None:
        return None
    current = str(value)
    for _ in range(12):
        decoded = html.unescape(current)
        if decoded == current:
            break
        current = decoded
    # Some exporters preserve numeric line entities even after html.unescape.
    current = re.sub(r"&#(?:10|x0*A);?", "\n", current, flags=re.IGNORECASE)
    current = re.sub(r"&#(?:13|x0*D);?", "\r", current, flags=re.IGNORECASE)
    return current


def local_name(name: str) -> str:
    return name.rsplit("}", 1)[-1] if "}" in name else name.split(":")[-1]


def attr_local(element: ET.Element, *names: str) -> Optional[str]:
    wanted = {name.lower() for name in names}
    for key, value in element.attrib.items():
        if local_name(key).lower() in wanted:
            return decode_entities(value)
    return None


def direct_children(element: ET.Element, name: str) -> list[ET.Element]:
    wanted = name.lower()
    return [child for child in list(element) if local_name(child.tag).lower() == wanted]


def descendants(element: ET.Element, name: str) -> list[ET.Element]:
    wanted = name.lower()
    return [child for child in element.iter() if local_name(child.tag).lower() == wanted]


def boolish(value: Any, default: Optional[bool] = None) -> Optional[bool]:
    if value is None or str(value).strip() == "":
        return default
    normalized = str(value).strip().lower()
    if normalized in {"true", "yes", "property_true", "property_on", "1"}:
        return True
    if normalized in {"false", "no", "property_false", "property_off", "0"}:
        return False
    return default


def integer(value: Any) -> Optional[int]:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def normalize_identifier(value: str) -> str:
    return re.sub(r"[^A-Z0-9_$#.]", "", value.replace('"', "").upper())


def unqualified(value: str) -> str:
    return normalize_identifier(value).split(".")[-1]


def normalize_module_stem(path: Path) -> str:
    stem = path.stem.lower().lstrip("_")
    for suffix in ("_fmb", "-fmb", "_form", "-form", "_module", "-module", "_fmt"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
    return re.sub(r"[^a-z0-9_$#]", "", stem)


def locate_folder(root: Path, canonical: str) -> tuple[Optional[Path], Optional[str]]:
    children = {child.name.lower(): child for child in root.iterdir() if child.is_dir()}
    for alias in FOLDER_ALIASES[canonical]:
        if alias in children:
            warning = None if alias == canonical else f"Using '{alias}' as alias for '{canonical}'."
            return children[alias], warning
    return None, f"Missing '{canonical}' input folder."


def list_files(folder: Optional[Path], extensions: set[str]) -> list[Path]:
    if folder is None:
        return []
    return sorted(
        (path for path in folder.rglob("*") if path.is_file() and path.suffix.lower() in extensions),
        key=lambda path: str(path).lower(),
    )


def file_state(path: Path, area: str) -> str:
    extension = path.suffix.lower()
    if area == "ui":
        return "binary_asset"
    if area == "form" and extension in BINARY_FORM_EXTENSIONS:
        return "binary_only"
    if extension == ".xml":
        return "structured_readable"
    return "readable_source"


def inventory_sources(root: Path, supplied_inputs: Optional[list[Path]] = None) -> tuple[dict[str, Optional[Path]], list[dict[str, Any]], list[str]]:
    folders: dict[str, Optional[Path]] = {}
    warnings: list[str] = []
    for canonical in ("form", "ddl", "ui"):
        folder, warning = locate_folder(root, canonical)
        folders[canonical] = folder
        if warning:
            warnings.append(warning)

    # Scan the entire supplied root as well as canonical folders.  Incremental
    # acquisition commonly supplies a single PLD or DDL at arbitrary depth.
    # Folder placement is useful evidence, but it is not a precondition.
    if supplied_inputs:
        candidate_set: set[Path] = set()
        for supplied in supplied_inputs:
            if supplied.is_file():
                candidate_set.add(supplied.resolve())
            elif supplied.is_dir():
                candidate_set.update(path.resolve() for path in supplied.rglob("*") if path.is_file())
        candidates = sorted(candidate_set, key=lambda path: str(path).lower())
    else:
        candidates = sorted((path for path in root.rglob("*") if path.is_file()), key=lambda path: str(path).lower())
    by_area: dict[str, list[Path]] = {"form": [], "ddl": [], "ui": []}
    for path in candidates:
        extension = path.suffix.lower()
        relative_parts = {part.lower() for part in path.relative_to(root).parts[:-1]}
        if extension in IMAGE_EXTENSIONS:
            by_area["ui"].append(path)
        elif extension == ".sql" and ("ddl" in relative_parts or folders["ddl"] is None):
            by_area["ddl"].append(path)
        elif extension in FORM_EXTENSIONS:
            by_area["form"].append(path)
    records: list[dict[str, Any]] = []
    for area, paths in by_area.items():
        for path in paths:
            stat = path.stat()
            records.append(
                {
                    "path": relative(path, root),
                    "area": area,
                    "extension": path.suffix.lower(),
                    "size": stat.st_size,
                    "sha256": sha256_file(path),
                    "state": file_state(path, area),
                }
            )
    records.sort(key=lambda item: item["path"].lower())
    return folders, records, warnings


def evidence_record(source_path: str, locator: str, claim: str, value: Any, confidence: str = "high") -> dict[str, Any]:
    return {
        "id": stable_id("EV", source_path, locator, claim),
        "source_path": source_path,
        "locator": locator,
        "claim": claim,
        "value": value,
        "confidence": confidence,
    }


def strip_comments(text: str) -> str:
    def preserve_lines(match: re.Match[str]) -> str:
        return "".join("\n" if char == "\n" else " " for char in match.group(0))

    text = re.sub(r"/\*.*?\*/", preserve_lines, text, flags=re.DOTALL)
    return re.sub(r"--[^\r\n]*", lambda match: " " * len(match.group(0)), text)


def extract_string_literals(text: str) -> list[dict[str, Any]]:
    literals: list[dict[str, Any]] = []
    for match in re.finditer(r"'(?:''|[^'])*'", text, flags=re.DOTALL):
        value = match.group(0)[1:-1].replace("''", "'")
        literals.append({"value": decode_entities(value) or "", "line": text.count("\n", 0, match.start()) + 1})
    return literals


def mask_string_literals(text: str) -> str:
    return re.sub(
        r"'(?:''|[^'])*'",
        lambda match: "".join("\n" if char == "\n" else " " for char in match.group(0)),
        text,
        flags=re.DOTALL,
    )


def sql_scan_regions(code: str) -> list[tuple[str, str, int]]:
    """Return decoded direct SQL and SQL-bearing literals with line offsets.

    Entity decoding happens before comment/string masking, so the semicolon in a
    residual ``&#10;`` can never terminate an SQL scan.
    """
    decoded = decode_entities(code) or ""
    clean = strip_comments(decoded)
    regions = [(mask_string_literals(clean), "direct", 0)]
    for literal in extract_string_literals(clean):
        value = literal["value"]
        if re.search(r"\b(SELECT|INSERT|UPDATE|DELETE|MERGE|CREATE)\b", value, re.IGNORECASE):
            regions.append((strip_comments(value), "embedded_literal", int(literal["line"]) - 1))
    return regions


def find_from_objects(text: str) -> Iterator[tuple[str, int]]:
    # Work statement by statement.  Requiring SELECT before FROM avoids treating
    # ordinary PL/SQL prose such as ``copy from record`` as an SQL reference.
    statement_start = 0
    for boundary in list(re.finditer(r";", text)) + [None]:
        statement_end = boundary.start() if boundary is not None else len(text)
        statement = text[statement_start:statement_end]
        if re.search(r"\bSELECT\b", statement, re.IGNORECASE):
            terminator = r"(?=\bWHERE\b|\bGROUP\s+BY\b|\bORDER\s+BY\b|\bCONNECT\s+BY\b|\bUNION\b|$)"
            for match in re.finditer(rf"\bFROM\b\s+(.+?){terminator}", statement, re.IGNORECASE | re.DOTALL):
                clause = match.group(1)
                if clause.lstrip().startswith("("):
                    continue
                offset = statement_start + match.start(1)
                cursor = 0
                for part in re.split(r",", clause):
                    name_match = re.match(rf"\s*({SQL_NAME})", part, re.IGNORECASE)
                    if name_match:
                        yield name_match.group(1), offset + cursor + name_match.start(1)
                    cursor += len(part) + 1
            for match in re.finditer(rf"\bJOIN\s+({SQL_NAME})", statement, re.IGNORECASE):
                yield match.group(1), statement_start + match.start(1)
        statement_start = statement_end + (1 if boundary is not None else 0)


def analyze_sql(code: str, source_path: str, locator: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, int]] = set()
    for region, source_kind, line_offset in sql_scan_regions(code):
        candidates: list[tuple[str, str, int]] = []
        for name, position in find_from_objects(region):
            candidates.append(("SELECT", name, position))
        patterns = [
            ("INSERT", rf"\bINSERT\s+INTO\s+({SQL_NAME})"),
            ("UPDATE", rf"\bUPDATE\s+({SQL_NAME})\s+SET\b"),
            ("DELETE", rf"\bDELETE\s+FROM\s+({SQL_NAME})"),
            ("MERGE", rf"\bMERGE\s+INTO\s+({SQL_NAME})"),
        ]
        for operation, expression in patterns:
            for match in re.finditer(expression, region, re.IGNORECASE):
                candidates.append((operation, match.group(1), match.start(1)))
        for match in re.finditer(rf"\b({SQL_NAME})\s*\.\s*(NEXTVAL|CURRVAL)\b", region, re.IGNORECASE):
            candidates.append((match.group(2).upper(), match.group(1), match.start(1)))

        for operation, raw_name, position in candidates:
            full_name = normalize_identifier(raw_name)
            name = unqualified(full_name)
            if not name or full_name in COMMON_SQL_OBJECTS or name in COMMON_SQL_OBJECTS:
                continue
            line = line_offset + region.count("\n", 0, position) + 1
            key = (operation, full_name, source_kind, line)
            if key in seen:
                continue
            seen.add(key)
            results.append(
                {
                    "id": stable_id("SQL", source_path, locator, operation, full_name, source_kind, line),
                    "operation": operation,
                    "access": "read" if operation in {"SELECT", "CURRVAL", "NEXTVAL"} else "write",
                    "object": name,
                    "qualified_object": full_name,
                    "source_kind": source_kind,
                    "source_path": source_path,
                    "locator": locator,
                    "code_line": line,
                }
            )
    return sorted(results, key=lambda item: (item["code_line"], item["operation"], item["qualified_object"]))


def analyze_calls(code: str) -> list[dict[str, Any]]:
    decoded = decode_entities(code) or ""
    clean = mask_string_literals(strip_comments(decoded))
    results: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    expression = re.compile(r"\b([A-Z][A-Z0-9_$#]*(?:\.[A-Z][A-Z0-9_$#]*){0,2})\s*\(", re.IGNORECASE)
    excluded = CALL_EXCLUSIONS | FORMS_BUILTINS
    for match in expression.finditer(clean):
        name = normalize_identifier(match.group(1))
        leaf = name.split(".")[-1]
        if name in excluded or leaf in excluded or leaf.startswith("C_") or leaf in {"ID", "NEXTVAL", "CURRVAL"}:
            continue
        line = clean.count("\n", 0, match.start()) + 1
        key = (name, line)
        if key not in seen:
            seen.add(key)
            results.append({"name": name, "code_line": line})
    # PL/SQL procedure calls may omit parentheses (for example
    # ``key_commit_before;``). Restrict this pass to standalone statements so
    # declarations, assignments, and prose are not promoted to call edges.
    standalone = re.compile(r"^\s*([A-Z][A-Z0-9_$#]*(?:\.[A-Z][A-Z0-9_$#]*){0,2})\s*;", re.IGNORECASE | re.MULTILINE)
    for match in standalone.finditer(clean):
        name = normalize_identifier(match.group(1))
        leaf = name.split(".")[-1]
        supported_hook = bool(
            re.fullmatch(r"KEY_[A-Z0-9_$#]+_(?:BEFORE|AFTER)", leaf)
            or re.fullmatch(r"ON_(?:INSERT|UPDATE|DELETE)", leaf)
            or leaf == "CG$CHK_PACKAGE_FAILURE"
        )
        if not supported_hook or name in excluded or leaf in excluded or leaf in CALL_EXCLUSIONS:
            continue
        line = clean.count("\n", 0, match.start()) + 1
        key = (name, line)
        if key not in seen:
            seen.add(key)
            results.append({"name": name, "code_line": line, "syntax": "standalone_procedure_call"})
    return results


def analyze_branches(code: str) -> list[dict[str, Any]]:
    decoded = decode_entities(code) or ""
    clean = strip_comments(decoded)
    branches = []
    for match in re.finditer(r"\b(IF|ELSIF)\s+(.+?)\s+THEN\b", clean, re.IGNORECASE | re.DOTALL):
        condition = re.sub(r"\s+", " ", match.group(2)).strip()
        branches.append({
            "branch_id": stable_id("BR", match.group(1).upper(), condition, clean.count("\n", 0, match.start()) + 1),
            "kind": match.group(1).lower(), "condition": condition,
            "code_line": clean.count("\n", 0, match.start()) + 1,
        })
    return branches


def analyze_forms_builtins(code: str) -> list[dict[str, Any]]:
    decoded = decode_entities(code) or ""
    clean = mask_string_literals(strip_comments(decoded))
    records = []
    for match in re.finditer(r"\b([A-Z][A-Z0-9_$#]*)\b\s*(?:\(|;)", clean, re.IGNORECASE):
        name = match.group(1).upper()
        if name not in FORMS_BUILTINS:
            continue
        records.append({"name": name, "code_line": clean.count("\n", 0, match.start()) + 1})
    return records


def analyze_navigation_actions(code: str) -> list[dict[str, Any]]:
    """Extract source-backed Forms navigation targets without masking literals."""
    decoded = decode_entities(code) or ""
    clean = strip_comments(decoded)
    records: list[dict[str, Any]] = []
    pattern = re.compile(
        r"\b(OPEN_FORM|CALL_FORM|NEW_FORM|GO_FORM|GO_ITEM)\s*\(\s*"
        r"(?:'((?:''|[^'])*)'|\"([^\"]*)\"|([^,\)\r\n]+))",
        re.IGNORECASE,
    )
    for match in pattern.finditer(clean):
        target = next(
            (
                value
                for value in (match.group(2), match.group(3), match.group(4))
                if value is not None
            ),
            "",
        )
        target = re.sub(r"\s+", " ", target.replace("''", "'")).strip()
        if match.group(1).upper() == "GO_ITEM":
            nested_literal = re.search(r"['\"]([^'\"]+)['\"]", target)
            if nested_literal:
                target = nested_literal.group(1)
        records.append(
            {
                "name": match.group(1).upper(),
                "target": target,
                "target_kind": "form" if match.group(1).upper() != "GO_ITEM" else "item",
                "code_line": clean.count("\n", 0, match.start()) + 1,
            }
        )
    return records


def analyze_messages(code: str, source_path: str, locator: str) -> list[dict[str, Any]]:
    decoded = decode_entities(code) or ""
    results: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()

    patterns = [
        (
            "catalog",
            re.compile(
                r"MSGGETTEXT\s*\(\s*(-?\d+)\s*,\s*'((?:''|[^'])*)'",
                re.IGNORECASE | re.DOTALL,
            ),
        ),
        (
            "raise_application_error",
            re.compile(r"RAISE_APPLICATION_ERROR\s*\(\s*(-?\d+)\s*,\s*'((?:''|[^'])*)'", re.IGNORECASE | re.DOTALL),
        ),
        (
            "forms_message",
            re.compile(r"\bMESSAGE\s*\(\s*'((?:''|[^'])*)'", re.IGNORECASE | re.DOTALL),
        ),
    ]
    for kind, pattern in patterns:
        for match in pattern.finditer(decoded):
            if kind == "forms_message":
                code_value, text_value = None, match.group(1).replace("''", "'")
            else:
                code_value, text_value = match.group(1), match.group(2).replace("''", "'")
            line = decoded.count("\n", 0, match.start()) + 1
            key = (kind, code_value, text_value, line)
            if key in seen:
                continue
            seen.add(key)
            results.append(
                {
                    "id": stable_id("MSG", source_path, locator, kind, code_value, text_value, line),
                    "kind": kind,
                    "code": code_value,
                    "text": text_value,
                    "source_path": source_path,
                    "locator": locator,
                    "code_line": line,
                    "text_available": bool(text_value),
                    "severity": None,
                    "domain": None,
                }
            )
            if kind == "catalog":
                statement_end = decoded.find(";", match.end())
                tail = decoded[match.end(): statement_end if statement_end >= 0 else min(len(decoded), match.end() + 500)]
                push_metadata = re.search(r"\)\s*,\s*'([A-Z])'\s*,\s*'([A-Z0-9_$#]+)'\s*,\s*(-?\d+)", tail, re.IGNORECASE)
                if push_metadata:
                    results[-1]["severity"] = push_metadata.group(1).upper()
                    results[-1]["domain"] = push_metadata.group(2).upper()
    for push in re.finditer(r"\bQMS\$FORMS_ERRORS\.PUSH\s*\(", decoded, re.IGNORECASE):
        opening = decoded.find("(", push.start())
        closing = matching_parenthesis(decoded, opening)
        if closing is None:
            continue
        invocation = decoded[push.start():closing + 1]
        if re.search(r"\bMSGGETTEXT\s*\(", invocation, re.IGNORECASE):
            continue
        line = decoded.count("\n", 0, push.start()) + 1
        literals = extract_string_literals(invocation)
        text_value = literals[0]["value"] if literals else None
        key = ("forms_error_push", None, text_value, line)
        if key in seen:
            continue
        seen.add(key)
        results.append({
            "id": stable_id("MSG", source_path, locator, "forms_error_push", line),
            "kind": "forms_error_push", "code": None, "text": text_value,
            "source_path": source_path, "locator": locator, "code_line": line,
            "text_available": bool(text_value), "severity": None, "domain": None,
        })
    results.sort(key=lambda record: (record.get("code_line", 0), record["id"]))
    return results


def analyze_property_overrides(code: str, source_path: str, locator: str) -> list[dict[str, Any]]:
    decoded = decode_entities(code) or ""
    results: list[dict[str, Any]] = []
    expression = re.compile(
        r"\bSET_(ITEM|BLOCK)_PROPERTY\s*\(\s*([^,]+?)\s*,\s*([A-Z0-9_$#]+)\s*,\s*([A-Z0-9_$#'\".]+)",
        re.IGNORECASE,
    )
    for match in expression.finditer(strip_comments(decoded)):
        line = decoded.count("\n", 0, match.start()) + 1
        target = match.group(2).strip().strip("'\"").upper()
        prop = match.group(3).upper()
        value = match.group(4).strip().strip("'\"").upper()
        results.append(
            {
                "id": stable_id("OVR", source_path, locator, match.group(1), target, prop, value, line),
                "target_type": match.group(1).lower(),
                "target": target,
                "property": prop,
                "value": value,
                "source_path": source_path,
                "locator": locator,
                "code_line": line,
            }
        )
    return results


def code_unit(kind: str, name: str, scope: str, source_path: str, locator: str, code: str,
              block_id: Optional[str] = None, item_id: Optional[str] = None) -> dict[str, Any]:
    decoded = decode_entities(code) or ""
    calls = [call for call in analyze_calls(decoded) if call["name"].split(".")[-1] != name.upper()]
    return {
        "id": stable_id("UNIT", source_path, locator, kind, name),
        "kind": kind,
        "name": name.upper(),
        "scope": scope,
        "block_id": block_id,
        "item_id": item_id,
        "source_path": source_path,
        "locator": locator,
        "code": decoded,
        "code_sha256": hashlib.sha256(decoded.encode("utf-8")).hexdigest(),
        "calls": calls,
        "sql_references": analyze_sql(decoded, source_path, locator),
        "messages": analyze_messages(decoded, source_path, locator),
        "branches": analyze_branches(decoded),
        "forms_builtins": analyze_forms_builtins(decoded),
        "navigation_actions": analyze_navigation_actions(decoded),
        "property_overrides": analyze_property_overrides(decoded, source_path, locator),
    }


def parse_form_xml(path: Path, root: Path) -> dict[str, Any]:
    source_path = relative(path, root)
    try:
        document = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        return {"source_path": source_path, "parse_error": str(exc), "module_id": None}

    modules = descendants(document, "FormModule")
    if local_name(document.tag).lower() == "formmodule":
        modules.insert(0, document)
    if not modules:
        return {"source_path": source_path, "parse_error": "No FormModule element found.", "module_id": None}
    form = modules[0]
    module_id = (attr_local(form, "Name", "ModuleName") or path.stem).lower()
    form_locator = f"FormModule[{module_id.upper()}]"
    extracted: dict[str, Any] = {
        "source_path": source_path,
        "module_id": module_id,
        "title": attr_local(form, "Title", "ModuleTitle"),
        "properties": {
            "menu_module": attr_local(form, "MenuModule"),
            "first_navigation_block": attr_local(form, "FirstNavigationBlockName"),
            "validation_unit": attr_local(form, "ValidationUnit"),
            "isolation_mode": attr_local(form, "IsolationMode"),
            "savepoint_mode": boolish(attr_local(form, "SavepointMode")),
        },
        "attached_libraries": [],
        "expected_sources": [],
        "runtime_screenshots": [],
        "windows": [],
        "canvases": [],
        "tab_pages": [],
        "blocks": [],
        "relations": [],
        "lovs": [],
        "record_groups": [],
        "triggers": [],
        "program_units": [],
        "evidence": [],
    }
    extracted["evidence"].append(evidence_record(source_path, form_locator, "module_identity", module_id))
    menu_module = extracted["properties"].get("menu_module")
    if menu_module:
        extracted["expected_sources"].append(
            {
                "kind": "menu_module",
                "name": menu_module,
                "normalized_stem": normalize_module_stem(Path(menu_module)),
                "source_path": source_path,
                "locators": [f"{form_locator}/@MenuModule"],
            }
        )

    for element in direct_children(form, "AttachedLibrary"):
        name = attr_local(element, "Name")
        if not name:
            continue
        locator = f"{form_locator}/AttachedLibrary[{name.upper()}]"
        record = {
            "name": name.upper(),
            "location": attr_local(element, "LibraryLocation"),
            "source_type": attr_local(element, "LibrarySource"),
            "evidence_id": stable_id("EV", source_path, locator, "attached_library"),
        }
        extracted["attached_libraries"].append(record)
        extracted["evidence"].append(evidence_record(source_path, locator, "attached_library", record))

    for element in direct_children(form, "Window"):
        name = attr_local(element, "Name")
        if name:
            extracted["windows"].append(
                {
                    "id": name,
                    "title": attr_local(element, "Title"),
                    "primary_canvas": attr_local(element, "PrimaryCanvas"),
                    "visible": boolish(attr_local(element, "Visible")),
                }
            )

    for element in direct_children(form, "Canvas"):
        name = attr_local(element, "Name")
        if not name:
            continue
        canvas = {
            "id": name,
            "window": attr_local(element, "WindowName"),
            "type": attr_local(element, "CanvasType"),
            "visible": boolish(attr_local(element, "Visible")),
        }
        extracted["canvases"].append(canvas)
        for page in direct_children(element, "TabPage"):
            page_name = attr_local(page, "Name")
            if page_name:
                extracted["tab_pages"].append(
                    {
                        "id": page_name,
                        "canvas": name,
                        "label": attr_local(page, "Label"),
                        "visible": boolish(attr_local(page, "Visible")),
                        "enabled": boolish(attr_local(page, "Enabled")),
                    }
                )

    for block in direct_children(form, "Block"):
        block_name = attr_local(block, "Name")
        if not block_name:
            continue
        locator = f"{form_locator}/Block[{block_name}]"
        query_source = attr_local(block, "QueryDataSourceName")
        dml_source = attr_local(block, "DMLDataName")
        declared_database_block = boolish(attr_local(block, "DatabaseBlock"), bool(query_source or dml_source))
        persistence_applicable = bool(query_source or dml_source)
        design_crud = {
            "query": boolish(attr_local(block, "QueryAllowed"), bool(query_source)),
            "create": boolish(attr_local(block, "InsertAllowed")),
            "update": boolish(attr_local(block, "UpdateAllowed")),
            "delete": boolish(attr_local(block, "DeleteAllowed")),
        }
        block_record: dict[str, Any] = {
            "id": block_name,
            "database_block": persistence_applicable,
            "declared_database_block": declared_database_block,
            "persistence_applicable": persistence_applicable,
            "block_role": "database_persistence" if persistence_applicable else ("framework_control" if block_name.upper().startswith(("CG$", "CGNV$", "QMS$")) else "control"),
            "query_data_source": query_source,
            "query_data_source_type": attr_local(block, "QueryDataSourceType"),
            "dml_data_name": dml_source,
            "dml_data_type": attr_local(block, "DMLDataType"),
            "where_clause": attr_local(block, "WhereClause", "DefaultWhere"),
            "order_by": attr_local(block, "OrderByClause"),
            "records_displayed": integer(attr_local(block, "RecordsDisplayCount")),
            "design_crud": design_crud,
            "effective_crud": dict(design_crud),
            "effective_crud_status": "design_time_only",
            "parent_filename": attr_local(block, "ParentFilename"),
            "items": [],
            "evidence_id": stable_id("EV", source_path, locator, "block_design"),
        }
        extracted["evidence"].append(evidence_record(source_path, locator, "block_design", {k: v for k, v in block_record.items() if k != "items"}))

        for item in direct_children(block, "Item"):
            item_name = attr_local(item, "Name")
            if not item_name:
                continue
            item_locator = f"{locator}/Item[{item_name}]"
            column = attr_local(item, "ColumnName", "BaseTableColumnName")
            database_item = boolish(attr_local(item, "DatabaseItem"), bool(column))
            item_design = {
                "query": boolish(attr_local(item, "QueryAllowed")),
                "create": boolish(attr_local(item, "InsertAllowed")),
                "update": boolish(attr_local(item, "UpdateAllowed")),
            }
            item_record = {
                "id": f"{block_name}.{item_name}",
                "name": item_name,
                "prompt": attr_local(item, "Prompt", "Label"),
                "hint": attr_local(item, "Hint", "Tooltip"),
                "item_type": attr_local(item, "ItemType"),
                "data_type": attr_local(item, "DataType"),
                "maximum_length": integer(attr_local(item, "MaximumLength")),
                "format_mask": attr_local(item, "FormatMask"),
                "canvas": attr_local(item, "CanvasName"),
                "tab_page": attr_local(item, "TabPageName"),
                "visible": boolish(attr_local(item, "Visible"), True),
                "enabled": boolish(attr_local(item, "Enabled"), True),
                "required": boolish(attr_local(item, "Required")),
                "database_item": database_item,
                "database_column": column,
                "mapping_status": "explicit" if column else ("database_item_without_column" if database_item else "non_database_item"),
                "lov": attr_local(item, "LovName", "LOVName"),
                "initial_value": attr_local(item, "InitialValue", "InitializeValue"),
                "parent_filename": attr_local(item, "ParentFilename"),
                "design_crud": item_design,
                "effective_crud": dict(item_design),
                "effective_crud_status": "design_time_only",
                "evidence_id": stable_id("EV", source_path, item_locator, "item_design"),
            }
            block_record["items"].append(item_record)
            extracted["evidence"].append(evidence_record(source_path, item_locator, "item_design", item_record))
            for trigger in direct_children(item, "Trigger"):
                name = attr_local(trigger, "Name")
                if name:
                    trigger_locator = f"{item_locator}/Trigger[{name}]"
                    extracted["triggers"].append(
                        code_unit("trigger", name, "item", source_path, trigger_locator, attr_local(trigger, "TriggerText") or "", block_name, item_record["id"])
                    )

        extracted["blocks"].append(block_record)
        for trigger in direct_children(block, "Trigger"):
            name = attr_local(trigger, "Name")
            if name:
                trigger_locator = f"{locator}/Trigger[{name}]"
                extracted["triggers"].append(
                    code_unit("trigger", name, "block", source_path, trigger_locator, attr_local(trigger, "TriggerText") or "", block_name)
                )

        parent_references: list[tuple[str, str]] = []
        if block_record.get("parent_filename"):
            parent_references.append((block_record["parent_filename"], locator))
        parent_references.extend(
            (item["parent_filename"], f"{locator}/Item[{item['name']}]/@ParentFilename")
            for item in block_record["items"]
            if item.get("parent_filename")
        )
        for parent_filename, parent_locator in parent_references:
            existing = next(
                (record for record in extracted["expected_sources"] if record["kind"] == "object_library" and record["name"].lower() == parent_filename.lower()),
                None,
            )
            if existing:
                existing["locators"].append(parent_locator)
            else:
                extracted["expected_sources"].append(
                    {
                        "kind": "object_library",
                        "name": parent_filename,
                        "normalized_stem": normalize_module_stem(Path(parent_filename)),
                        "source_path": source_path,
                        "locators": [parent_locator],
                    }
                )

    for relation in direct_children(form, "Relation"):
        name = attr_local(relation, "Name")
        if name:
            extracted["relations"].append(
                {
                    "id": name,
                    "master_block": attr_local(relation, "MasterBlock"),
                    "detail_block": attr_local(relation, "DetailBlock"),
                    "join_condition": attr_local(relation, "JoinCondition"),
                    "delete_record": attr_local(relation, "DeleteRecord"),
                    "prevent_masterless_operations": boolish(attr_local(relation, "PreventMasterlessOperations")),
                    "auto_query": boolish(attr_local(relation, "AutoQuery")),
                }
            )

    for group in direct_children(form, "RecordGroup"):
        name = attr_local(group, "Name")
        if name:
            query = attr_local(group, "RecordGroupQuery", "QueryText") or ""
            locator = f"{form_locator}/RecordGroup[{name}]"
            extracted["record_groups"].append(
                {
                    "id": name,
                    "type": attr_local(group, "RecordGroupType"),
                    "query": query,
                    "sql_references": analyze_sql(query, source_path, locator),
                }
            )

    for lov in direct_children(form, "LOV"):
        name = attr_local(lov, "Name")
        if name:
            returns = []
            for mapping in descendants(lov, "LOVColumnMapping"):
                returns.append(
                    {
                        "column": attr_local(mapping, "Name", "ColumnName"),
                        "return_item": attr_local(mapping, "ReturnItem"),
                        "display_width": integer(attr_local(mapping, "DisplayWidth")),
                    }
                )
            extracted["lovs"].append(
                {
                    "id": name,
                    "title": attr_local(lov, "Title"),
                    "record_group": attr_local(lov, "RecordGroupName"),
                    "return_mappings": returns,
                }
            )

    for trigger in direct_children(form, "Trigger"):
        name = attr_local(trigger, "Name")
        if name:
            locator = f"{form_locator}/Trigger[{name}]"
            extracted["triggers"].append(code_unit("trigger", name, "form", source_path, locator, attr_local(trigger, "TriggerText") or ""))

    for unit in direct_children(form, "ProgramUnit"):
        name = attr_local(unit, "Name")
        if name:
            locator = f"{form_locator}/ProgramUnit[{name}]"
            record = code_unit("program_unit", name, "form", source_path, locator, attr_local(unit, "ProgramUnitText") or "")
            record["program_unit_type"] = attr_local(unit, "ProgramUnitType")
            extracted["program_units"].append(record)
    for expected in extracted["expected_sources"]:
        expected["locators"] = sorted(set(expected["locators"]))
    return extracted


def parse_pld_units(path: Path, root: Path) -> dict[str, Any]:
    source_path = relative(path, root)
    text, encoding = read_text(path)
    decoded = decode_entities(text) or ""
    units: list[dict[str, Any]] = []
    attached = sorted(
        {match.group(1).upper() for match in re.finditer(r"^\s*\.ATTACH\s+LIBRARY\s+([A-Z0-9_$#]+)", decoded, re.IGNORECASE | re.MULTILINE)}
    )
    expression = re.compile(
        r"^\s*(PROCEDURE|FUNCTION|PACKAGE(?:\s+BODY|\s+SPECIFICATION|\s+SPEC)?)\s+([A-Z0-9_$#]+)",
        re.IGNORECASE | re.MULTILINE,
    )
    # Match declarations in a comment-masked twin so change-history prose such
    # as "procedure X added" never becomes an executable code unit. Offsets are
    # preserved by strip_comments and can safely slice the decoded source.
    matches = list(expression.finditer(strip_comments(decoded)))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(decoded)
        name = match.group(2).upper()
        locator = f"TextUnit[{name}]@line:{decoded.count(chr(10), 0, match.start()) + 1}"
        unit = code_unit("program_unit", name, "library", source_path, locator, decoded[match.start():end])
        unit["program_unit_type"] = match.group(1).upper()
        units.append(unit)
    return {"source_path": source_path, "encoding": encoding, "attached_libraries": attached, "program_units": units}


def split_top_level(value: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    in_string = False
    index = 0
    while index < len(value):
        char = value[index]
        if char == "'":
            if in_string and index + 1 < len(value) and value[index + 1] == "'":
                index += 2
                continue
            in_string = not in_string
        elif not in_string:
            if char == "(":
                depth += 1
            elif char == ")":
                depth = max(0, depth - 1)
            elif char == "," and depth == 0:
                parts.append(value[start:index].strip())
                start = index + 1
        index += 1
    tail = value[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def matching_parenthesis(text: str, opening: int) -> Optional[int]:
    depth = 0
    in_string = False
    index = opening
    while index < len(text):
        char = text[index]
        if char == "'":
            if in_string and index + 1 < len(text) and text[index + 1] == "'":
                index += 2
                continue
            in_string = not in_string
        elif not in_string:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return index
        index += 1
    return None


def parse_constraint(definition: str, table_name: str) -> Optional[dict[str, Any]]:
    text = definition.strip()
    constraint_name = None
    named = re.match(rf"CONSTRAINT\s+({SQL_NAME})\s+(.+)$", text, re.IGNORECASE | re.DOTALL)
    if named:
        constraint_name = unqualified(named.group(1))
        text = named.group(2).strip()
    patterns = [
        ("primary_key", r"PRIMARY\s+KEY\s*\(([^)]*)\)"),
        ("unique", r"UNIQUE\s*\(([^)]*)\)"),
        ("foreign_key", r"FOREIGN\s+KEY\s*\(([^)]*)\)\s+REFERENCES\s+(" + SQL_NAME + r")\s*\(([^)]*)\)(.*)"),
        ("check", r"CHECK\s*\((.*)\)"),
    ]
    for kind, expression in patterns:
        match = re.search(expression, text, re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        record: dict[str, Any] = {
            "name": constraint_name,
            "type": kind,
            "table": table_name,
            "definition": text,
        }
        if kind in {"primary_key", "unique"}:
            record["columns"] = [unqualified(part) for part in split_top_level(match.group(1))]
        elif kind == "foreign_key":
            record["columns"] = [unqualified(part) for part in split_top_level(match.group(1))]
            record["references_object"] = unqualified(match.group(2))
            record["references_columns"] = [unqualified(part) for part in split_top_level(match.group(3))]
            record["on_delete"] = "cascade" if re.search(r"ON\s+DELETE\s+CASCADE", match.group(4), re.IGNORECASE) else None
        else:
            record["expression"] = match.group(1).strip()
        return record
    return None


def parse_table_columns(body: str, table_name: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    columns: list[dict[str, Any]] = []
    constraints: list[dict[str, Any]] = []
    for definition in split_top_level(body):
        if re.match(r"^(CONSTRAINT|PRIMARY\s+KEY|UNIQUE|FOREIGN\s+KEY|CHECK)\b", definition, re.IGNORECASE):
            constraint = parse_constraint(definition, table_name)
            if constraint:
                constraints.append(constraint)
            continue
        match = re.match(rf"\s*({SQL_NAME})\s+([A-Z][A-Z0-9_]*(?:\s*\([^)]*\))?(?:\s+WITH\s+TIME\s+ZONE)?)\s*(.*)$", definition, re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        name = unqualified(match.group(1))
        data_type = re.sub(r"\s+", " ", match.group(2).strip()).upper()
        tail = match.group(3).strip()
        default_match = re.search(r"\bDEFAULT\s+(.+?)(?=\s+NOT\s+NULL|\s+CONSTRAINT\b|\s+PRIMARY\s+KEY|\s+REFERENCES\b|$)", tail, re.IGNORECASE | re.DOTALL)
        column = {
            "name": name,
            "data_type": data_type,
            "nullable": not bool(re.search(r"\bNOT\s+NULL\b", tail, re.IGNORECASE)),
            "default": default_match.group(1).strip() if default_match else None,
        }
        columns.append(column)
        if re.search(r"\bPRIMARY\s+KEY\b", tail, re.IGNORECASE):
            constraints.append({"name": None, "type": "primary_key", "table": table_name, "columns": [name], "definition": tail})
        reference = re.search(rf"\bREFERENCES\s+({SQL_NAME})\s*\(([^)]*)\)", tail, re.IGNORECASE)
        if reference:
            constraints.append(
                {
                    "name": None,
                    "type": "foreign_key",
                    "table": table_name,
                    "columns": [name],
                    "references_object": unqualified(reference.group(1)),
                    "references_columns": [unqualified(part) for part in split_top_level(reference.group(2))],
                    "on_delete": "cascade" if re.search(r"ON\s+DELETE\s+CASCADE", tail, re.IGNORECASE) else None,
                    "definition": tail,
                }
            )
    return columns, constraints


def parse_ddl_file(path: Path, root: Path) -> list[dict[str, Any]]:
    source_path = relative(path, root)
    text, encoding = read_text(path)
    decoded = decode_entities(text) or ""
    create_prefix = r"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:FORCE\s+)?(?:EDITIONABLE\s+|NONEDITIONABLE\s+)?"
    patterns = [
        ("table", re.compile(rf"\bCREATE\s+(?:GLOBAL\s+TEMPORARY\s+)?TABLE\s+({SQL_NAME})", re.IGNORECASE)),
        ("materialized_view", re.compile(rf"{create_prefix}MATERIALIZED\s+VIEW\s+({SQL_NAME})", re.IGNORECASE)),
        ("view", re.compile(rf"{create_prefix}VIEW\s+({SQL_NAME})", re.IGNORECASE)),
        ("sequence", re.compile(rf"{create_prefix}SEQUENCE\s+({SQL_NAME})", re.IGNORECASE)),
        ("public_synonym", re.compile(rf"{create_prefix}PUBLIC\s+SYNONYM\s+({SQL_NAME})", re.IGNORECASE)),
        ("synonym", re.compile(rf"{create_prefix}(?!PUBLIC\s+)SYNONYM\s+({SQL_NAME})", re.IGNORECASE)),
        ("trigger", re.compile(rf"{create_prefix}TRIGGER\s+({SQL_NAME})", re.IGNORECASE)),
        ("index", re.compile(rf"\bCREATE\s+(?:UNIQUE\s+|BITMAP\s+)?INDEX\s+({SQL_NAME})", re.IGNORECASE)),
        ("package_body", re.compile(rf"{create_prefix}PACKAGE\s+BODY\s+({SQL_NAME})", re.IGNORECASE)),
        ("package", re.compile(rf"{create_prefix}PACKAGE\s+(?!BODY\b)({SQL_NAME})", re.IGNORECASE)),
        ("procedure", re.compile(rf"{create_prefix}PROCEDURE\s+({SQL_NAME})", re.IGNORECASE)),
        ("function", re.compile(rf"{create_prefix}FUNCTION\s+({SQL_NAME})", re.IGNORECASE)),
    ]
    found: list[tuple[int, str, re.Match[str]]] = []
    for kind, expression in patterns:
        found.extend((match.start(), kind, match) for match in expression.finditer(decoded))
    found.sort(key=lambda value: value[0])
    objects: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int]] = set()
    for index, (start, kind, match) in enumerate(found):
        full_name = normalize_identifier(match.group(1))
        name = unqualified(full_name)
        key = (kind, full_name, start)
        if key in seen:
            continue
        seen.add(key)
        end = found[index + 1][0] if index + 1 < len(found) else len(decoded)
        statement = decoded[start:end]
        line = decoded.count("\n", 0, start) + 1
        record: dict[str, Any] = {
            "id": stable_id("DDL", source_path, kind, full_name, line),
            "name": name,
            "qualified_name": full_name,
            "owner": full_name.rsplit(".", 1)[0] if "." in full_name else None,
            "type": kind,
            "source_path": source_path,
            "source_line": line,
            "source_sha256": hashlib.sha256(statement.encode("utf-8")).hexdigest(),
            "encoding": encoding,
            "columns": [],
            "constraints": [],
            "dependencies": [],
            "comments": [],
        }
        if kind == "table":
            opening = decoded.find("(", match.end())
            closing = matching_parenthesis(decoded, opening) if opening >= 0 else None
            if closing is not None and closing <= end:
                record["columns"], record["constraints"] = parse_table_columns(decoded[opening + 1:closing], name)
        elif kind in {"view", "materialized_view"}:
            record["dependencies"] = sorted({item["object"] for item in analyze_sql(statement, source_path, f"DDL[{name}]") if item["object"] != name})
        elif kind in {"synonym", "public_synonym"}:
            target = re.search(rf"\bFOR\s+({SQL_NAME})", statement, re.IGNORECASE)
            if target:
                record["synonym_target"] = normalize_identifier(target.group(1))
                record["dependencies"] = [unqualified(target.group(1))]
        elif kind == "trigger":
            target = re.search(rf"\bON\s+({SQL_NAME})", statement, re.IGNORECASE)
            if target:
                record["trigger_table"] = unqualified(target.group(1))
                record["dependencies"].append(record["trigger_table"])
            record["trigger_events"] = sorted({match.group(1).upper() for match in re.finditer(r"\b(INSERT|UPDATE|DELETE)\b", statement, re.IGNORECASE)})
            record["dependencies"] = sorted(set(record["dependencies"]) | {item["object"] for item in analyze_sql(statement, source_path, f"DDL[{name}]") if item["object"] != name})
        elif kind == "index":
            target = re.search(rf"\bON\s+({SQL_NAME})\s*\(([^)]*)\)", statement, re.IGNORECASE | re.DOTALL)
            if target:
                record["index_table"] = unqualified(target.group(1))
                record["index_columns"] = [unqualified(part.split()[0]) for part in split_top_level(target.group(2))]
                record["dependencies"] = [record["index_table"]]
            record["unique"] = bool(re.search(r"\bCREATE\s+UNIQUE\s+INDEX\b", statement, re.IGNORECASE))
        elif kind == "sequence":
            options = {}
            for label, expression in {
                "start_with": r"\bSTART\s+WITH\s+(-?\d+)",
                "increment_by": r"\bINCREMENT\s+BY\s+(-?\d+)",
                "minvalue": r"\bMINVALUE\s+(-?\d+)",
                "maxvalue": r"\bMAXVALUE\s+(-?\d+)",
                "cache": r"\bCACHE\s+(\d+)",
            }.items():
                option = re.search(expression, statement, re.IGNORECASE)
                options[label] = integer(option.group(1)) if option else None
            options["cycle"] = bool(re.search(r"\bCYCLE\b", statement, re.IGNORECASE) and not re.search(r"\bNOCYCLE\b", statement, re.IGNORECASE))
            record["sequence_options"] = options
        objects.append(record)

    # ALTER TABLE constraints are material and often live after CREATE TABLE.
    for match in re.finditer(rf"\bALTER\s+TABLE\s+({SQL_NAME})\s+ADD\s+(.+?);", decoded, re.IGNORECASE | re.DOTALL):
        table_name = unqualified(match.group(1))
        constraint = parse_constraint(match.group(2), table_name)
        if not constraint:
            continue
        target = next((item for item in objects if item["type"] == "table" and item["name"] == table_name), None)
        if target is None:
            target = {
                "id": stable_id("DDL", source_path, "table_alter", table_name),
                "name": table_name,
                "qualified_name": normalize_identifier(match.group(1)),
                "owner": None,
                "type": "table_alter",
                "source_path": source_path,
                "source_line": decoded.count("\n", 0, match.start()) + 1,
                "source_sha256": hashlib.sha256(match.group(0).encode("utf-8")).hexdigest(),
                "encoding": encoding,
                "columns": [],
                "constraints": [],
                "dependencies": [],
                "comments": [],
            }
            objects.append(target)
        target["constraints"].append(constraint)
    for match in re.finditer(rf"\bALTER\s+TABLE\s+({SQL_NAME})\s+MODIFY\s*\((.+?)\)\s*;", decoded, re.IGNORECASE | re.DOTALL):
        table_name = unqualified(match.group(1))
        target = next((item for item in objects if item["type"] == "table" and item["name"] == table_name), None)
        if target is None:
            target = {
                "id": stable_id("DDL", source_path, "table_alter", table_name), "name": table_name,
                "qualified_name": normalize_identifier(match.group(1)), "owner": None, "type": "table_alter",
                "source_path": source_path, "source_line": decoded.count("\n", 0, match.start()) + 1,
                "source_sha256": hashlib.sha256(match.group(0).encode("utf-8")).hexdigest(), "encoding": encoding,
                "columns": [], "constraints": [], "dependencies": [],
                "comments": [],
            }
            objects.append(target)
        for definition in split_top_level(match.group(2)):
            column_match = re.match(rf"\s*({SQL_NAME})\s+(.+)$", definition, re.IGNORECASE | re.DOTALL)
            if not column_match:
                continue
            column_name = unqualified(column_match.group(1))
            tail = column_match.group(2)
            nullable: Optional[bool] = None
            if re.search(r"\bNOT\s+NULL\b", tail, re.IGNORECASE):
                nullable = False
            elif re.search(r"(?:^|\s)NULL(?:\s|$)", tail, re.IGNORECASE):
                nullable = True
            column = next((item for item in target.get("columns", []) if item["name"] == column_name), None)
            if column is None:
                column = {"name": column_name, "data_type": None, "nullable": nullable, "default": None, "alter_only": True}
                target["columns"].append(column)
            elif nullable is not None:
                column["nullable"] = nullable
            if nullable is False:
                target["constraints"].append(
                    {
                        "name": None, "type": "not_null", "table": table_name, "columns": [column_name],
                        "definition": definition, "source": "ALTER TABLE MODIFY",
                    }
                )
    comment_identifier = r'"?[A-Z][A-Z0-9_$#]*"?'
    comment_target = rf'{comment_identifier}(?:\s*\.\s*{comment_identifier}){{0,2}}'
    for match in re.finditer(
        rf"\bCOMMENT\s+ON\s+(TABLE|COLUMN)\s+({comment_target})\s+IS\s+'((?:''|[^'])*)'\s*;",
        decoded, re.IGNORECASE | re.DOTALL,
    ):
        target_type = match.group(1).lower()
        parts = normalize_identifier(match.group(2)).split(".")
        column_name = parts[-1] if target_type == "column" else None
        table_name = parts[-2] if target_type == "column" and len(parts) >= 2 else parts[-1]
        target = next(
            (item for item in objects if item.get("name") == table_name and item.get("type") in {"table", "table_alter", "view", "materialized_view"}),
            None,
        )
        if target is None:
            continue
        comment = {
            "target_type": target_type,
            "table": table_name,
            "column": column_name,
            "text": match.group(3).replace("''", "'"),
            "source_line": decoded.count("\n", 0, match.start()) + 1,
        }
        target.setdefault("comments", []).append(comment)
        if column_name:
            column = next((record for record in target.get("columns", []) if record.get("name") == column_name), None)
            if column is not None:
                column["comment"] = comment["text"]
        else:
            target["comment"] = comment["text"]
    return objects


def parse_message_sources(paths: list[Path], root: Path) -> dict[str, str]:
    catalog: dict[str, str] = {}
    for path in paths:
        if path.suffix.lower() not in {".err", ".txt", ".sql", ".pld", ".xml"}:
            continue
        try:
            text, _ = read_text(path)
        except OSError:
            continue
        decoded = decode_entities(text) or ""
        for match in re.finditer(r"MSGGETTEXT\s*\(\s*(-?\d+)\s*,\s*'((?:''|[^'])*)'", decoded, re.IGNORECASE | re.DOTALL):
            catalog.setdefault(match.group(1), match.group(2).replace("''", "'"))
        for match in re.finditer(r"^\s*(?:[A-Z][A-Z0-9_$#]*[-.:])?(-?\d+)\s*[=:|]\s*(.+?)\s*$", decoded, re.MULTILINE):
            catalog.setdefault(match.group(1), match.group(2).strip())
    return catalog


def merge_form_extractions(extractions: list[dict[str, Any]], module_id: str) -> dict[str, Any]:
    selected = [item for item in extractions if str(item.get("module_id") or "").lower() == module_id.lower()]
    module: dict[str, Any] = {
        "module_id": module_id.lower(),
        "title": None,
        "source_paths": [],
        "properties": {},
        "attached_libraries": [],
        "expected_sources": [],
        "runtime_screenshots": [],
        "windows": [],
        "canvases": [],
        "tab_pages": [],
        "blocks": [],
        "relations": [],
        "lovs": [],
        "record_groups": [],
        "triggers": [],
        "program_units": [],
        "evidence": [],
    }
    keyed_collections = {
        "attached_libraries": "name",
        "expected_sources": "name",
        "runtime_screenshots": "path",
        "windows": "id",
        "canvases": "id",
        "tab_pages": "id",
        "blocks": "id",
        "relations": "id",
        "lovs": "id",
        "record_groups": "id",
        "triggers": "id",
        "program_units": "id",
        "evidence": "id",
    }
    for item in selected:
        module["source_paths"].append(item["source_path"])
        if item.get("title"):
            module["title"] = item["title"]
        module["properties"].update(item.get("properties", {}))
        for collection, key in keyed_collections.items():
            existing = {record[key] for record in module[collection]}
            module[collection].extend(record for record in item.get(collection, []) if record[key] not in existing)
    return module


def attach_library_units(module: dict[str, Any], library_extractions: list[dict[str, Any]]) -> None:
    existing = {unit["id"] for unit in module["program_units"]}
    for extraction in library_extractions:
        for unit in extraction.get("program_units", []):
            if unit["id"] not in existing:
                module["program_units"].append(unit)
                existing.add(unit["id"])


def all_code_units(module: dict[str, Any]) -> list[dict[str, Any]]:
    return list(module.get("triggers", [])) + list(module.get("program_units", []))


def resolve_effective_crud(module: dict[str, Any], relevant_unit_ids: Optional[set[str]] = None) -> list[dict[str, Any]]:
    overrides = [override for unit in all_code_units(module) if relevant_unit_ids is None or unit["id"] in relevant_unit_ids for override in unit.get("property_overrides", [])]
    for block in module.get("blocks", []):
        if block.get("persistence_applicable") is False or block.get("block_role") != "database_persistence":
            block["effective_crud"] = {operation: False for operation in ("query", "create", "update", "delete")}
            block["effective_crud_status"] = "not_applicable_to_persistence"
        else:
            block["effective_crud"] = dict(block.get("design_crud", {}))
            block["effective_crud_status"] = "design_time_only"
        block.pop("runtime_overrides", None)
        block.pop("runtime_override_ids", None)
        for item in block.get("items", []):
            item["effective_crud"] = dict(item.get("design_crud", {}))
            item["effective_crud_status"] = "design_time_only"
            item.pop("runtime_overrides", None)
            item.pop("runtime_override_ids", None)
    blocks = {block["id"].upper(): block for block in module.get("blocks", [])}
    items = {item["id"].upper(): item for block in module.get("blocks", []) for item in block.get("items", [])}
    property_map = {"QUERY_ALLOWED": "query", "INSERT_ALLOWED": "create", "UPDATE_ALLOWED": "update", "DELETE_ALLOWED": "delete"}
    for override in overrides:
        crud_key = property_map.get(override["property"])
        if not crud_key:
            continue
        value = boolish(override["value"])
        if value is None:
            continue
        target = override["target"].upper()
        candidates = blocks if override["target_type"] == "block" else items
        record = candidates.get(target)
        if record:
            if override["target_type"] == "block" and record.get("block_role") != "database_persistence":
                override["resolution"] = "non_persistence_control_target"
                continue
            # Static extraction establishes that runtime code can override the
            # property, not that every execution takes that branch. Preserve
            # the conditional provenance instead of flattening it to a bool.
            record["effective_crud"][crud_key] = "conditional"
            record["effective_crud_status"] = "conditional_runtime_override"
            record.setdefault("runtime_overrides", []).append(
                {
                    "override_id": override["id"],
                    "operation": crud_key,
                    "value": value,
                    "source_path": override["source_path"],
                    "locator": override["locator"],
                    "code_line": override["code_line"],
                    "condition": "Condition requires PL/SQL control-flow review",
                }
            )
        else:
            override["resolution"] = "dynamic_or_unresolved_target"
    for block in module.get("blocks", []):
        for item in block.get("items", []):
            item["inherited_crud"] = {}
            for operation in ("query", "create", "update"):
                block_value = block.get("effective_crud", {}).get(operation)
                item_value = item.get("effective_crud", {}).get(operation)
                item["inherited_crud"][operation] = block_value
                if block_value is False:
                    item["effective_crud"][operation] = False
                    if item_value is not False:
                        item["effective_crud_status"] = "restricted_by_block"
                elif block_value == "conditional" or item_value == "conditional":
                    item["effective_crud"][operation] = "conditional"
                    item["effective_crud_status"] = "conditional_runtime_override"
    return overrides


def operation_for_unit(unit: dict[str, Any]) -> set[str]:
    operations: set[str] = set()
    event = unit["name"].upper()
    for operation, events in OPERATION_EVENTS.items():
        if event in events:
            operations.add(operation)
    sql_ops = {item["operation"] for item in unit.get("sql_references", [])}
    if "SELECT" in sql_ops or "EXECUTE_QUERY" in unit.get("code", "").upper():
        operations.add("query")
    if "INSERT" in sql_ops:
        operations.add("create")
    if "UPDATE" in sql_ops:
        operations.add("update")
    if "DELETE" in sql_ops:
        operations.add("delete")
    upper_code = unit.get("code", "").upper()
    if "COMMIT_FORM" in upper_code or re.search(r"DO_KEY\s*\(\s*'COMMIT_FORM'", upper_code):
        operations.add("save")
    if unit["kind"] == "program_unit" and (unit.get("messages") or "RAISE_FAILURE" in upper_code):
        operations.add("validation")
    for operation, hints in OPERATION_ROUTINE_HINTS.items():
        if unit["kind"] == "program_unit" and any(hint in event for hint in hints):
            operations.add(operation)
    return operations


def build_behavior_ledger(module: dict[str, Any]) -> dict[str, Any]:
    units = all_code_units(module)
    units_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    # Routine calls resolve to program units. Trigger names such as KEY-DELREC
    # repeat across blocks and are never interchangeable call-graph nodes.
    for unit in module.get("program_units", []):
        units_by_name[unit["name"].upper()].append(unit)

    ledgers: dict[str, Any] = {}
    for operation in OPERATION_EVENTS:
        # Program units are reachable implementation, not user/runtime entry
        # points merely because their name contains DEL/UPD or their body has
        # SQL. Entry points start at Forms triggers and follow calls from there.
        entry_units = [unit for unit in units if unit["kind"] == "trigger" and operation in operation_for_unit(unit)]
        entry_paths = []
        aggregate_reachable: dict[str, dict[str, Any]] = {}
        aggregate_sql: dict[str, dict[str, Any]] = {}
        aggregate_messages: dict[str, dict[str, Any]] = {}
        aggregate_overrides: dict[str, dict[str, Any]] = {}
        aggregate_unresolved: set[str] = set()
        for entry_unit in entry_units:
            queue = deque([entry_unit])
            reachable: dict[str, dict[str, Any]] = {entry_unit["id"]: entry_unit}
            unresolved: set[str] = set()
            call_edges: list[dict[str, Any]] = []
            while queue:
                current = queue.popleft()
                current_calls = list(current.get("calls", []))
                known_call_keys = {
                    (str(call.get("name") or "").upper(), int(call.get("code_line") or 0))
                    for call in current_calls
                }
                # Generated Forms triggers often invoke a local action unit as
                # a standalone statement without parentheses. Resolve any such
                # statement when its name is an actual selected-module program
                # unit; this avoids broad prose/declaration false positives
                # while preserving explicit button-action reachability.
                clean_current = mask_string_literals(strip_comments(current.get("code", "")))
                for match in re.finditer(
                    r"^\s*([A-Z][A-Z0-9_$#]*(?:\.[A-Z][A-Z0-9_$#]*){0,2})\s*;",
                    clean_current,
                    re.IGNORECASE | re.MULTILINE,
                ):
                    name = normalize_identifier(match.group(1))
                    leaf = name.split(".")[-1]
                    if not (units_by_name.get(name) or units_by_name.get(leaf)):
                        continue
                    line = clean_current.count("\n", 0, match.start()) + 1
                    if (name, line) not in known_call_keys:
                        current_calls.append(
                            {
                                "name": name,
                                "code_line": line,
                                "syntax": "resolved_local_standalone_call",
                            }
                        )
                        known_call_keys.add((name, line))
                for call in current_calls:
                    name = call["name"].upper()
                    leaf = name.split(".")[-1]
                    targets = units_by_name.get(name, []) or units_by_name.get(leaf, [])
                    targets = [target for target in targets if target["id"] != current["id"]]
                    if targets:
                        for target in targets:
                            edge = {"from_unit_id": current["id"], "from": current["name"], "to_unit_id": target["id"], "to": target["name"], "call_line": call.get("code_line")}
                            if edge not in call_edges:
                                call_edges.append(edge)
                            if target["id"] not in reachable:
                                reachable[target["id"]] = target
                                queue.append(target)
                    elif name not in FORMS_BUILTINS and leaf not in FORMS_BUILTINS:
                        unresolved.add(name)
            reachable_units = sorted(reachable.values(), key=lambda item: (item["source_path"], item["locator"]))
            sql_refs = {item["id"]: item for unit in reachable_units for item in unit.get("sql_references", [])}
            messages = {item["id"]: item for unit in reachable_units for item in unit.get("messages", [])}
            overrides = {item["id"]: item for unit in reachable_units for item in unit.get("property_overrides", [])}
            branches = [
                {**branch, "unit_id": unit["id"], "unit_name": unit["name"], "source_path": unit["source_path"], "locator": unit["locator"]}
                for unit in reachable_units for branch in unit.get("branches", [])
            ]
            forms_builtins = [
                {**builtin, "unit_id": unit["id"], "unit_name": unit["name"], "source_path": unit["source_path"], "locator": unit["locator"]}
                for unit in reachable_units for builtin in unit.get("forms_builtins", [])
            ]
            navigation_actions = [
                {
                    **action,
                    "unit_id": unit["id"],
                    "unit_name": unit["name"],
                    "source_path": unit["source_path"],
                    "locator": unit["locator"],
                }
                for unit in reachable_units
                for action in unit.get("navigation_actions", [])
            ]
            entry_paths.append(
                {
                    "entry_unit_id": entry_unit["id"],
                    "reachable_routine_ids": sorted(reachable),
                    "call_edges": call_edges,
                    "sql_references": sorted(sql_refs.values(), key=lambda item: item["id"]),
                    "messages": sorted(messages.values(), key=lambda item: item["id"]),
                    "property_overrides": sorted(overrides.values(), key=lambda item: item["id"]),
                    "branches": branches,
                    "forms_builtins": forms_builtins,
                    "navigation_actions": navigation_actions,
                    "unresolved_calls": sorted(unresolved),
                }
            )
            aggregate_reachable.update(reachable)
            aggregate_sql.update(sql_refs)
            aggregate_messages.update(messages)
            aggregate_overrides.update(overrides)
            aggregate_unresolved.update(unresolved)
        ledgers[operation] = {
            "id": stable_id("BEH", module["module_id"], operation),
            "operation": operation,
            "status": "evidence_found" if entry_units else "no_readable_entry_point_found",
            "entry_point_ids": sorted({unit["id"] for unit in entry_units}),
            "entry_points": [
                {
                    "unit_id": unit["id"],
                    "name": unit["name"],
                    "scope": unit["scope"],
                    "block_id": unit.get("block_id"),
                    "item_id": unit.get("item_id"),
                    "source_path": unit["source_path"],
                    "locator": unit["locator"],
                }
                for unit in sorted(entry_units, key=lambda item: (item["source_path"], item["locator"]))
            ],
            "entry_paths": entry_paths,
            "reachable_routine_ids": sorted(aggregate_reachable),
            "sql_references": sorted(aggregate_sql.values(), key=lambda item: item["id"]),
            "messages": sorted(aggregate_messages.values(), key=lambda item: item["id"]),
            "property_overrides": sorted(aggregate_overrides.values(), key=lambda item: item["id"]),
            "unresolved_calls": sorted(aggregate_unresolved),
            "confidence": "high" if entry_units and not aggregate_unresolved else ("medium" if entry_units else "low"),
        }
    return ledgers


def file_map(files: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {item.get("identity_path", item["path"]): item for item in files}


def canonicalize_supplied_paths(files: list[dict[str, Any]], previous: Optional[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Match relocated supplemental files by content and source role.

    ``path`` remains the physical path under the supplied root for reading;
    ``identity_path`` is the stable prior path used by deltas and evidence IDs.
    """
    previous_files = (previous or {}).get("sources", {}).get("files", [])
    previous_by_path = {record["path"]: record for record in previous_files}
    previous_by_content: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for record in previous_files:
        previous_by_content[(record.get("area", ""), record.get("extension", ""), record.get("sha256", ""))].append(record["path"])
    aliases: dict[str, str] = {}
    normalized: list[dict[str, Any]] = []
    for original in files:
        record = dict(original)
        physical = record["path"]
        identity = physical
        if physical not in previous_by_path:
            matches = previous_by_content.get((record["area"], record["extension"], record["sha256"]), [])
            if len(matches) == 1:
                identity = matches[0]
        record["identity_path"] = identity
        aliases[physical] = identity
        normalized.append(record)
    return normalized, aliases


def remap_source_paths(value: Any, aliases: dict[str, str]) -> Any:
    if isinstance(value, dict):
        for key, item in list(value.items()):
            if key in {"source_path", "sourcePath"} and isinstance(item, str):
                value[key] = aliases.get(item, item)
            else:
                remap_source_paths(item, aliases)
    elif isinstance(value, list):
        for item in value:
            remap_source_paths(item, aliases)
    return value


def load_previous(path: Optional[Path]) -> Optional[dict[str, Any]]:
    if path is not None and path.is_dir():
        path = path / "evidence-model.json"
    if path is None or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read previous evidence {path}: {exc}") from exc


def compare_files(current: list[dict[str, Any]], previous: Optional[dict[str, Any]], supplemental: bool = False) -> dict[str, list[str]]:
    current_map = file_map(current)
    previous_map = file_map((previous or {}).get("sources", {}).get("files", []))
    added = sorted(set(current_map) - set(previous_map))
    removed = [] if supplemental else sorted(set(previous_map) - set(current_map))
    changed = sorted(path for path in set(current_map) & set(previous_map) if current_map[path]["sha256"] != previous_map[path]["sha256"])
    unchanged = sorted(path for path in set(current_map) & set(previous_map) if current_map[path]["sha256"] == previous_map[path]["sha256"])
    return {"added": added, "changed": changed, "removed": removed, "unchanged": unchanged}


def relevant_form_paths(files: list[dict[str, Any]], module_id: str, attached: set[str]) -> set[str]:
    module_norm = re.sub(r"[^a-z0-9_$#]", "", module_id.lower())
    library_norms = {re.sub(r"[^a-z0-9_$#]", "", name.lower()) for name in attached}
    selected: set[str] = set()
    for record in files:
        if record["area"] != "form":
            continue
        identity_path = record.get("identity_path", record["path"])
        stem = normalize_module_stem(Path(identity_path))
        if stem in {module_norm, module_norm + "l"} or stem in library_norms:
            selected.add(identity_path)
    return selected


def ddl_catalog_incremental(root: Path, ddl_paths: list[Path], changes: dict[str, list[str]], previous: Optional[dict[str, Any]], supplemental: bool = False,
                            path_aliases: Optional[dict[str, str]] = None, compiler_changed: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    aliases = path_aliases or {}
    supplied_paths = {aliases.get(relative(path, root), relative(path, root)) for path in ddl_paths}
    reusable = set() if compiler_changed else set(changes["unchanged"])
    if supplemental and not compiler_changed:
        reusable.update(
            record.get("source_path")
            for record in (previous or {}).get("ddl", {}).get("catalog", [])
            if record.get("source_path") not in supplied_paths
        )
    previous_catalog = (previous or {}).get("ddl", {}).get("catalog", [])
    reused_records = [record for record in previous_catalog if record.get("source_path") in reusable]
    parsed_paths = [path for path in ddl_paths if aliases.get(relative(path, root), relative(path, root)) not in reusable]
    parsed_records = [record for path in parsed_paths for record in parse_ddl_file(path, root)]
    remap_source_paths(parsed_records, aliases)
    catalog = reused_records + parsed_records
    catalog.sort(key=lambda item: (item["name"], item["type"], item["source_path"], item["source_line"]))
    return catalog, {
        "reused_ddl_files": sorted({record["source_path"] for record in reused_records}),
        "parsed_ddl_files": sorted(aliases.get(relative(path, root), relative(path, root)) for path in parsed_paths),
    }


def source_gap(kind: str, subject: str, status_reason: str, operations: list[str], impact: str, source_status: str = "missing") -> dict[str, Any]:
    key = f"{kind}:{subject.upper()}"
    identifier = stable_id("GAP", key)
    return {
        "id": identifier,
        "gap_id": identifier,
        "key": key,
        "kind": kind,
        "subject": subject,
        "status": "open",
        "source_status": source_status,
        "reason": status_reason,
        "affected_operations": sorted(set(operations)),
        "impact": impact,
    }


def deduplicate_semantic_gaps(gaps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge legacy aggregate gaps that represent one semantic expectation."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    library_kinds = {"readable_module_library", "readable_attached_library"}
    for original in gaps:
        gap = dict(original)
        semantic_key = (
            f"readable_library:{str(gap.get('subject', '')).upper()}"
            if gap.get("kind") in library_kinds
            else str(gap.get("key") or f"{gap.get('kind')}:{str(gap.get('subject', '')).upper()}")
        )
        groups[semantic_key].append(gap)

    merged: list[dict[str, Any]] = []
    for semantic_key, records in sorted(groups.items()):
        preferred = next((record for record in records if record.get("kind") == "readable_module_library"), records[0])
        combined = dict(preferred)
        combined["key"] = semantic_key
        combined["id"] = stable_id("GAP", semantic_key)
        combined["gap_id"] = combined["id"]
        combined["affected_operations"] = sorted({operation for record in records for operation in record.get("affected_operations", [])})
        if len(records) > 1:
            combined["reason"] = "The semantically unique attached/module library has no readable PLD or equivalent source."
            combined["impact"] = "Runtime defaulting, navigation, CRUD overrides, validation, and reachable library behavior may be incomplete."
            combined["merged_legacy_gap_kinds"] = sorted({record.get("kind") for record in records})
        # Preserve the strongest active lifecycle state when older aggregate
        # outputs contained one open and one resolved duplicate.
        status_priority = {"reopened": 4, "open": 3, "narrowed": 2, "closed": 1, "resolved": 1}
        combined["status"] = max(records, key=lambda record: status_priority.get(record.get("status"), 0)).get("status", "open")
        merged.append(combined)
    return merged


def reconcile_gaps(current_open: list[dict[str, Any]], previous: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
    current_open = deduplicate_semantic_gaps(current_open)
    previous_semantic = deduplicate_semantic_gaps((previous or {}).get("gaps", []))
    previous_gaps = {gap["key"]: gap for gap in previous_semantic}
    current_by_key = {gap["key"]: gap for gap in current_open}
    reconciled: list[dict[str, Any]] = []
    now = utc_now()
    for key, gap in sorted(current_by_key.items()):
        old = previous_gaps.get(key)
        if old:
            gap["first_seen"] = old.get("first_seen", old.get("last_seen", now))
            gap["last_seen"] = now
            if old.get("status") == "closed":
                gap["status"] = "reopened"
                gap["reopened_at"] = now
            elif old.get("reason") != gap.get("reason") or old.get("affected_operations") != gap.get("affected_operations"):
                gap["status"] = "narrowed"
                gap["previous_reason"] = old.get("reason")
            else:
                gap["status"] = old.get("status") if old.get("status") in {"open", "narrowed", "reopened"} else "open"
        else:
            gap["first_seen"] = now
            gap["last_seen"] = now
        reconciled.append(gap)
    for key, old in sorted(previous_gaps.items()):
        if key in current_by_key:
            continue
        if old.get("status") == "closed":
            # Resolved gaps are durable history. A supplemental run must not
            # erase them merely because they no longer appear in current-open
            # detection.
            reconciled.append(dict(old))
            continue
        closed = dict(old)
        closed["status"] = "closed"
        closed["closed_at"] = now
        closed["resolution"] = "The current source set no longer exhibits this gap; review the change set for the resolving artifact."
        reconciled.append(closed)
    return reconciled


def impact_analysis(changes: dict[str, list[str]], current_catalog: list[dict[str, Any]], previous: Optional[dict[str, Any]], module: dict[str, Any], behavior: dict[str, Any]) -> dict[str, Any]:
    changed_paths = set(changes["added"] + changes["changed"] + changes["removed"])
    current_objects = {record["name"] for record in current_catalog if record["source_path"] in changed_paths}
    previous_objects = {
        record["name"]
        for record in (previous or {}).get("ddl", {}).get("catalog", [])
        if record.get("source_path") in changed_paths
    }
    db_objects = sorted(current_objects | previous_objects)
    impacted_operations = sorted(
        operation
        for operation, ledger in behavior.items()
        if {item["object"] for item in ledger.get("sql_references", [])} & set(db_objects)
    )
    module_source_paths = set(module.get("source_paths", [])) | {unit.get("source_path") for unit in all_code_units(module)}
    form_changed = bool(changed_paths & module_source_paths) or any(path.lower().startswith(("form/", "forms/", "form_extraction/")) for path in changed_paths)
    if form_changed:
        impacted_operations = sorted(behavior)
    changed_routines = sorted(
        {
            unit["name"]
            for unit in all_code_units(module)
            if unit["source_path"] in changed_paths
        }
    )
    if changed_routines:
        changed_unit_ids = {unit["id"] for unit in all_code_units(module) if unit["name"] in changed_routines}
        impacted_operations = sorted(
            set(impacted_operations)
            | {
                operation
                for operation, ledger in behavior.items()
                if changed_unit_ids & set(ledger.get("reachable_routine_ids", []))
            }
        )
    stale_sections = []
    if form_changed:
        stale_sections.extend([
            "Section 3 - Legacy Screen Overview",
            "Section 6 - Functional Requirements",
            "Section 7 - Page Layout and Components",
            "Section 8 - Field and Control Specification",
            "Section 11 - Actions and Buttons",
            "Section 12 - Business Rules and Validation",
            "Section 19 - Test and Acceptance Scenarios",
            "Appendix B - Legacy Item Inventory And Coverage",
            "Appendix C - Trigger And Program Unit Inventory",
            "Appendix D - Forms-To-Target Event Mapping",
            "Appendix I - Extraction Coverage And Missing Source Register",
            "Appendix J - Incremental Extraction History",
        ])
    if db_objects:
        stale_sections.extend([
            "Section 8 - Field and Control Specification",
            "Section 12 - Business Rules and Validation",
            "Section 15 - Data Model and Database Mapping",
            "Section 16 - Data Retrieval and Processing Logic",
            "Section 17 - Error and Message Catalogue",
            "Section 19 - Test and Acceptance Scenarios",
            "Appendix F - Database DDL Inventory",
            "Appendix G - Reference SQL And Technical Notes",
            "Appendix I - Extraction Coverage And Missing Source Register",
            "Appendix J - Incremental Extraction History",
        ])
    if any(path.lower().startswith(("ui/", "screenshots/", "images/")) for path in changed_paths):
        stale_sections.append("Section 3 - Legacy Screen Overview")
    return {
        "modules": [module["module_id"]] if changed_paths else [],
        "blocks": sorted(block["id"] for block in module.get("blocks", [])) if form_changed else [],
        "routines": changed_routines,
        "database_objects": db_objects,
        "behavior_slices": impacted_operations,
        "stale_section_hints": sorted(set(stale_sections)),
    }


def percentage(numerator: int, denominator: int) -> Optional[float]:
    return round(100.0 * numerator / denominator, 2) if denominator else None


def build_evidence(root: Path, module_filter: str, previous: Optional[dict[str, Any]] = None,
                   supplemental: bool = False, supplied_inputs: Optional[list[Path]] = None) -> dict[str, Any]:
    folders, supplied_files, warnings = inventory_sources(root, supplied_inputs)
    supplied_files, path_aliases = canonicalize_supplied_paths(supplied_files, previous if supplemental else None)
    changes = compare_files(supplied_files, previous, supplemental=supplemental)
    previous_files = (previous or {}).get("sources", {}).get("files", [])
    if supplemental:
        effective_by_path = {record["path"]: record for record in previous_files}
        for record in supplied_files:
            public_record = dict(record)
            public_record["path"] = record["identity_path"]
            public_record.pop("identity_path", None)
            effective_by_path[public_record["path"]] = public_record
        files = sorted(effective_by_path.values(), key=lambda record: record["path"].lower())
    else:
        files = [dict(record, path=record.get("identity_path", record["path"])) for record in supplied_files]
        for record in files:
            record.pop("identity_path", None)
    previous_extractor_version = str((previous or {}).get("extractor", {}).get("version") or "")
    compiler_changed = bool(previous and previous_extractor_version != EXTRACTOR_VERSION)
    # A compiler semantic change must reparse every still-available effective
    # source. Reusing prior parsed structures across extractor versions would
    # make an unchanged-source delta falsely imply unchanged semantics.
    parse_file_records = files if compiler_changed else supplied_files
    form_paths = [root / record["path"] for record in parse_file_records if record["area"] == "form" and (root / record["path"]).is_file()]
    ddl_paths = [root / record["path"] for record in parse_file_records if record["area"] == "ddl" and (root / record["path"]).is_file()]

    # Parse module XML headers first to resolve attached libraries exactly.
    xml_paths = [path for path in form_paths if path.suffix.lower() == ".xml"]
    header_extractions = [parse_form_xml(path, root) for path in xml_paths]
    remap_source_paths(header_extractions, path_aliases)
    selected_headers = [item for item in header_extractions if str(item.get("module_id") or "").lower() == module_filter.lower()]
    previous_module = next(
        (item for item in (previous or {}).get("modules", []) if item.get("module_id", "").lower() == module_filter.lower()),
        None,
    )
    attached = {library["name"] for item in selected_headers for library in item.get("attached_libraries", [])}
    if previous_module:
        attached.update(library["name"] for library in previous_module.get("attached_libraries", []))
    relevant_paths = relevant_form_paths(files, module_filter, attached)
    relevant_supplied_paths = relevant_form_paths(supplied_files, module_filter, attached)

    relevant_changed = bool(set(changes["added"] + changes["changed"] + changes["removed"]) & relevant_paths)
    # A supplemental bundle without the module XML enriches the previous model;
    # its absence never erases previously established blocks or behavior.
    can_reuse_module = bool(previous_module and not compiler_changed and (not selected_headers or not relevant_changed))
    if can_reuse_module:
        module = json.loads(json.dumps(previous_module))
        form_parse_mode = "reused_previous_module_for_supplement" if supplemental else "reused_unchanged_module_extraction"
    else:
        module = merge_form_extractions(header_extractions, module_filter)
        form_parse_mode = "parsed_all_relevant_form_sources" if previous else "parsed_first_run"

    # Associate every plausible screenshot using explainable filename/module/title
    # evidence.  Pixels remain a human-review source; filename association does
    # not override Forms, PL/SQL, or DDL evidence.
    title = str(module.get("title") or "").strip()
    screenshot_records: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for record in files:
        if record.get("area") != "ui":
            continue
        association = screenshot_association(str(record["path"]), module_filter, title)
        if association:
            screenshot_records.append((record, association))
    screenshot_records.sort(
        key=lambda pair: (-float(pair[1]["association_score"]), str(pair[0]["path"]).casefold())
    )
    for record, _ in screenshot_records:
        relevant_paths.add(record["path"])
    module["runtime_screenshots"] = [
        {
            "path": record["path"],
            "sha256": record["sha256"],
            **association,
        }
        for record, association in screenshot_records
    ]

    library_extractions = [
        parse_pld_units(path, root)
        for path in form_paths
        if path_aliases.get(relative(path, root), relative(path, root)) in relevant_supplied_paths and path.suffix.lower() in {".pld", ".fmt", ".sql", ".pls", ".pks", ".pkb", ".prc", ".fnc", ".trg", ".vw", ".txt"}
    ]
    remap_source_paths(library_extractions, path_aliases)
    supplied_library_paths = {item["source_path"] for item in library_extractions}
    if supplied_library_paths:
        module["program_units"] = [unit for unit in module.get("program_units", []) if unit.get("source_path") not in supplied_library_paths]
    attach_library_units(module, library_extractions)

    behavior = build_behavior_ledger(module)
    module_source_paths = set(module.get("source_paths", []))
    relevant_unit_ids = {
        unit["id"]
        for unit in all_code_units(module)
        if unit.get("source_path") in module_source_paths
    } | {
        unit_id
        for ledger in behavior.values()
        for unit_id in ledger.get("reachable_routine_ids", [])
    }
    overrides = resolve_effective_crud(module, relevant_unit_ids)
    ddl_catalog, ddl_incremental = ddl_catalog_incremental(
        root, ddl_paths, changes, previous, supplemental=supplemental,
        path_aliases=path_aliases, compiler_changed=compiler_changed,
    )
    ddl_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in ddl_catalog:
        ddl_by_name[record["name"]].append(record)

    sql_references = {
        ref["id"]: ref
        for unit in all_code_units(module)
        if unit["id"] in relevant_unit_ids
        for ref in unit.get("sql_references", [])
    }
    # QMS_MODULES is the framework module registry used by the attached GALA
    # application library. Preserve it as an inferred module-runtime dependency
    # even when the only readable SQL locator is outside a recognized CRUD path;
    # do not similarly pull the report-specific QMS_MDE_PARAMS dependency.
    for unit in all_code_units(module):
        for ref in unit.get("sql_references", []):
            if ref["object"] == "QMS_MODULES":
                inferred = dict(ref)
                inferred["module_relevance"] = "framework_runtime_inferred"
                sql_references[inferred["id"]] = inferred
    for group in module.get("record_groups", []):
        for ref in group.get("sql_references", []):
            sql_references[ref["id"]] = ref
    referenced_names = sorted({ref["object"] for ref in sql_references.values()})
    missing_ddl = sorted(name for name in referenced_names if name not in ddl_by_name)

    message_catalog = dict((previous or {}).get("logic", {}).get("message_catalog", {})) if supplemental else {}
    message_catalog.update(parse_message_sources([path for path in form_paths if path_aliases.get(relative(path, root), relative(path, root)) in relevant_supplied_paths], root))
    messages = {message["id"]: message for unit in all_code_units(module) if unit["id"] in relevant_unit_ids for message in unit.get("messages", [])}
    for message in messages.values():
        if not message.get("text") and message.get("code") in message_catalog:
            message["text"] = message_catalog[message["code"]]
            message["text_available"] = True

    gaps: list[dict[str, Any]] = []
    selected_file_records = [record for record in files if record["path"] in relevant_paths]
    readable_xml = [record for record in selected_file_records if record["extension"] == ".xml" and record["state"] == "structured_readable"]
    if not selected_headers and not previous_module:
        gaps.append(source_gap("module_source", module_filter, "No readable Forms XML for the requested module was found.", list(OPERATION_EVENTS), "All UI, CRUD, validation, and transaction claims are incomplete."))

    module_library = module_filter.lower() + "l"
    module_library_files = [record for record in files if record["area"] == "form" and normalize_module_stem(Path(record["path"])) == module_library]
    readable_module_library = [record for record in module_library_files if record["state"] == "readable_source"]
    if not readable_module_library:
        source_status = "binary_only" if module_library_files else "missing"
        reason = "The module-specific library is present only as a binary artifact." if module_library_files else "The module-specific library was not supplied."
        gaps.append(source_gap("readable_module_library", module_library.upper(), reason, list(OPERATION_EVENTS), "Runtime defaulting, navigation, CRUD overrides, and validation may be incomplete.", source_status))

    file_stems: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in files:
        if record["area"] == "form":
            file_stems[normalize_module_stem(Path(record["path"]))].append(record)
    for library in sorted(attached):
        matches = file_stems.get(library.lower(), [])
        readable = [record for record in matches if record["state"] in {"readable_source", "structured_readable"}]
        if not readable:
            source_status = "binary_only" if matches else "missing"
            gaps.append(source_gap("readable_attached_library", library, f"Attached library {library} has no readable PLD or equivalent source.", list(OPERATION_EVENTS), "Calls into this library cannot be fully traced.", source_status))

    for expected in module.get("expected_sources", []):
        matches = file_stems.get(expected.get("normalized_stem", ""), [])
        readable = [record for record in matches if record["state"] in {"readable_source", "structured_readable"}]
        if readable:
            continue
        kind = expected.get("kind")
        subject = str(expected.get("name") or "").upper()
        if kind == "menu_module":
            operations = ["delete", "save", "query", "validation"]
            reason = f"The Forms XML declares menu module {subject}, but no readable menu source was supplied."
            impact_text = "Menu-triggered save, delete, navigation, and custom entry points remain incomplete."
            expected_path = f"form/{str(expected.get('name')).lower()}.mmb-or-readable-export"
            role = "forms_menu"
        else:
            operations = list(OPERATION_EVENTS)
            reason = f"The Forms XML declares parent object library {subject}, but no readable object-library source was supplied."
            impact_text = "Inherited properties and standard trigger behavior cannot be independently verified."
            expected_path = f"form/{str(expected.get('name')).lower()}-or-readable-export"
            role = "object_library"
        gap = source_gap("expected_source", subject, reason, operations, impact_text, "binary_only" if matches else "missing")
        gap["expected_path"] = expected_path
        gap["expected_source_role"] = role
        gap["expected_by"] = [
            {"source_path": expected["source_path"], "locator": locator, "symbol": subject}
            for locator in expected.get("locators", [])
        ]
        gaps.append(gap)

    # SCL and SPL are delete-enabled persistence blocks, but their generic
    # user entry point is outside the readable module. Preserve applicability
    # as an implicit path and uncertainty as one exact gap.
    unresolved_delete_blocks = [
        block["id"] for block in module.get("blocks", [])
        if block.get("block_role") == "database_persistence"
        and block.get("effective_crud", {}).get("delete") is True
        and not any(unit.get("block_id") == block["id"] and unit.get("name") == "KEY-DELREC" for unit in module.get("triggers", []))
    ]
    if unresolved_delete_blocks:
        subject = "Generic delete entry point for " + " and ".join(unresolved_delete_blocks)
        gap = source_gap(
            "implicit_forms_entry_point", subject,
            f"Delete is enabled for {', '.join(unresolved_delete_blocks)}, but no block-local readable KEY-DELREC entry point exists.",
            ["delete"], "The physical delete is applicable, while menu/framework routing and its full outcome remain unresolved.",
            "not_found_in_readable_source",
        )
        source = module.get("source_paths", [None])[0]
        gap["expected_by"] = [
            {"source_path": source, "locator": f"FormModule/Block[@Name='{block_id}']/@DeleteAllowed", "symbol": block_id}
            for block_id in unresolved_delete_blocks if source
        ]
        gaps.append(gap)

    pre_dml_validation_units = [
        unit for unit in module.get("triggers", [])
        if unit.get("name") in {"PRE-INSERT", "PRE-UPDATE"}
        and re.search(r"\b(?:QMS\$FORMS_ERRORS\.)?RAISE_FAILURE\b", unit.get("code", ""), re.IGNORECASE)
    ]
    if pre_dml_validation_units:
        gap = source_gap(
            "validation_branch_mapping", "Pre-DML validation predicate-to-message mapping",
            "Readable pre-insert/pre-update messages and stop calls are normalized, but nested predicates are not yet deterministically associated with each message/stop branch.",
            ["create", "update"],
            "Code generation must preserve the recorded branch cardinality and raw trigger locators, and obtain predicate-level review before claiming rule completeness.",
            "readable_source_partially_normalized",
        )
        gap["expected_by"] = [
            {"source_path": unit["source_path"], "locator": unit["locator"], "symbol": f"{unit.get('block_id')}.{unit['name']}"}
            for unit in pre_dml_validation_units
        ]
        gaps.append(gap)

    for name in missing_ddl:
        operations = [operation for operation, ledger in behavior.items() if name in {ref["object"] for ref in ledger.get("sql_references", [])}]
        gaps.append(source_gap("missing_ddl", name, f"Referenced database object {name} has no matched recursive DDL artifact.", operations, "Object shape, constraints, cascades, or view derivation remain unresolved."))

    for block in module.get("blocks", []):
        if block.get("block_role") != "database_persistence":
            continue
        for item in block.get("items", []):
            if item.get("database_item") and item.get("mapping_status") == "database_item_without_column":
                gaps.append(
                    source_gap(
                        "ambiguous_mapping", item["id"],
                        f"Database item {item['id']} has no explicit physical ColumnName mapping in readable Forms XML.",
                        [operation for operation in ("query", "create", "update") if item.get("effective_crud", {}).get(operation) is not False],
                        "Do not infer a physical column from the item name; validate generated SQL, triggers, or business intent.",
                        "not_established",
                    )
                )
    audit_column_names = {
        "CREATED_BY",
        "CREATION_DATE",
        "LAST_UPDATED_BY",
        "LAST_UPDATE_DATE",
        "LAST_UPDATE_LOGIN",
    }
    decoded_unit_source = "\n".join(
        str(unit.get("code") or "") for unit in all_code_units(module)
    ).upper()
    for table_name in sorted(
        {
            unqualified(block.get("dml_data_name") or block.get("query_data_source"))
            for block in module.get("blocks", [])
            if block.get("block_role") == "database_persistence"
            and (block.get("dml_data_name") or block.get("query_data_source"))
        }
    ):
        table_records = [
            record
            for record in ddl_by_name.get(table_name, [])
            if record.get("type") in {"table", "view", "materialized_view"}
        ]
        table_record = max(table_records, key=lambda record: len(record.get("columns", [])), default=None)
        if not table_record:
            continue
        relevant_audit_columns = [
            column
            for column in table_record.get("columns", [])
            if str(column.get("name") or "").upper() in audit_column_names
            and column.get("nullable") is False
        ]
        if not relevant_audit_columns:
            continue
        unresolved_columns = []
        for column in relevant_audit_columns:
            column_name = str(column.get("name") or "").upper()
            if column.get("default") not in (None, ""):
                continue
            explicit_assignment = bool(
                re.search(
                    rf"(?:\b{re.escape(table_name)}\s*\.\s*{re.escape(column_name)}\b|"
                    rf":\s*[A-Z0-9_$#]+\s*\.\s*{re.escape(column_name)}\s*:=)",
                    decoded_unit_source,
                    re.IGNORECASE,
                )
            )
            trigger_evidence = any(
                record.get("type") == "trigger"
                and table_name in json.dumps(record, ensure_ascii=True).upper()
                and column_name in json.dumps(record, ensure_ascii=True).upper()
                for record in ddl_catalog
            )
            if not explicit_assignment and not trigger_evidence:
                unresolved_columns.append(column_name)
        if unresolved_columns:
            gap = source_gap(
                "audit_column_population",
                f"Audit column population for {table_name}",
                f"Required audit columns {', '.join(unresolved_columns)} have no DDL default, "
                "decoded Forms/PLSQL assignment, or supplied database-trigger evidence that establishes "
                "their population owner.",
                ["create", "update"],
                "Insert/update behavior may depend on an unsupplied Forms library, database trigger, "
                "or runtime framework. Preserve the required columns but do not invent their owner.",
                "not_established",
            )
            gap["expected_by"] = [
                {
                    "source_path": table_record["source_path"],
                    "locator": f"DDL/{table_record['type']}[@Name='{table_record['qualified_name']}']",
                    "symbol": table_name,
                }
            ]
            gaps.append(gap)
    for message in messages.values():
        if not message.get("text_available"):
            subject = str(message.get("code") or message["id"])
            operations = [operation for operation, ledger in behavior.items() if message["id"] in {candidate["id"] for candidate in ledger.get("messages", [])}]
            gaps.append(source_gap("missing_message_text", subject, f"Message {subject} is reachable but its user-facing text is unavailable.", operations, "The target must retain the code and use placeholder text until the catalogue is supplied.", "missing"))

    unresolved_calls = sorted({call for ledger in behavior.values() for call in ledger.get("unresolved_calls", [])})
    readable_unit_names = {unit["name"] for unit in all_code_units(module)}
    for call in unresolved_calls:
        # Framework and package-qualified calls remain explicit gaps, but one gap per routine is stable and reviewable.
        ddl_matches = ddl_by_name.get(call.split(".")[-1], [])
        non_callable_ddl = ddl_matches and all(item.get("type") not in {"package", "package_body", "procedure", "function"} for item in ddl_matches)
        if call.split(".")[-1] not in readable_unit_names and not non_callable_ddl:
            operations = [operation for operation, ledger in behavior.items() if call in ledger.get("unresolved_calls", [])]
            gaps.append(source_gap("unresolved_routine", call, f"Reachable routine {call} has no readable definition in the selected source set.", operations, "Observable legacy behavior may be incomplete until readable source or runtime evidence is supplied.", "missing_or_external"))

    for operation, ledger in behavior.items():
        if ledger["status"] == "no_readable_entry_point_found":
            gaps.append(source_gap("operation_entry_point", operation, f"No readable {operation} entry point was found; this is not proof that the operation is absent.", [operation], "The specification must avoid negative or completeness claims for this operation.", "not_found_in_readable_source"))

    gaps = reconcile_gaps(gaps, previous)
    for gap in gaps:
        if gap.get("subject", "").upper() == module_filter.upper() + "L" and gap.get("kind") in {"readable_module_library", "readable_attached_library"}:
            gap["unresolved_facets"] = [
                "commit_ownership", "rollback_and_failure_atomicity", "audit_column_population",
                "locking_and_lost_update_behavior", "retry_behavior",
            ]
    open_gaps = [gap for gap in gaps if gap["status"] != "closed"]

    declared_database_blocks = [block for block in module.get("blocks", []) if block.get("database_block")]
    database_blocks = [block for block in module.get("blocks", []) if block.get("block_role") == "database_persistence"]
    control_blocks = [block for block in module.get("blocks", []) if block.get("block_role") != "database_persistence"]
    database_items = [item for block in database_blocks for item in block.get("items", []) if item.get("database_item")]
    disposed_items = [item for item in database_items if all(item.get("design_crud", {}).get(key) is not None for key in ("query", "create", "update"))]
    matched_references = [name for name in referenced_names if name in ddl_by_name]
    coverage = {
        "source_files": {
            "total": len(files),
            "by_area": dict(sorted(Counter(record["area"] for record in files).items())),
            "by_state": dict(sorted(Counter(record["state"] for record in files).items())),
            "selected_module_files": len(selected_file_records),
            "readable_module_xml": len(readable_xml),
        },
        "forms": {
            "all_blocks": len(module.get("blocks", [])),
            "declared_database_blocks": len(declared_database_blocks),
            "database_blocks": len(database_blocks),
            "control_or_framework_blocks": len(control_blocks),
            "database_blocks_with_crud_disposition": sum(1 for block in database_blocks if all(block.get("design_crud", {}).get(key) is not None for key in ("query", "create", "update", "delete"))),
            "database_items": len(database_items),
            "database_items_with_crud_disposition": len(disposed_items),
            "item_crud_coverage_percent": percentage(len(disposed_items), len(database_items)),
            "triggers": len(module.get("triggers", [])),
            "program_units": len(module.get("program_units", [])),
            "runtime_property_overrides": len(overrides),
        },
        "database": {
            "ddl_files": len(ddl_paths),
            "ddl_objects": len(ddl_catalog),
            "referenced_objects": len(referenced_names),
            "matched_referenced_objects": len(matched_references),
            "missing_referenced_objects": len(missing_ddl),
            "referenced_ddl_coverage_percent": percentage(len(matched_references), len(referenced_names)),
        },
        "behavior": {
            "operation_slices": len(behavior),
            "operation_slices_with_entry_points": sum(1 for ledger in behavior.values() if ledger["entry_point_ids"]),
            "unresolved_reachable_calls": len(unresolved_calls),
            "messages": len(messages),
        },
        "gaps": {
            "open": len(open_gaps),
            "closed": sum(1 for gap in gaps if gap["status"] == "closed"),
            "by_kind": dict(sorted(Counter(gap["kind"] for gap in open_gaps).items())),
        },
    }

    impact = impact_analysis(changes, ddl_catalog, previous, module, behavior)
    previous_run = (previous or {}).get("run", {})
    previous_path_hash = previous_run.get("run_sha256")
    result = {
        "schema_version": SCHEMA_VERSION,
        "extractor": {
            "name": EXTRACTOR_NAME,
            "version": EXTRACTOR_VERSION,
            "deterministic_ids": True,
            "entity_decode": "repeat_until_stable",
        },
        "run": {
            "generated_at": utc_now(),
            "input_root": str(root.resolve()),
            "module_filter": module_filter.lower(),
            "previous_evidence_sha256": previous_path_hash,
            "previous_run_id": previous_run.get("run_id"),
            "previous_run_sha256": previous_run.get("run_sha256"),
            "previous_state_sha256": previous_run.get("state_sha256") or previous_run.get("evidence_sha256"),
            "previous_extractor_version": previous_extractor_version or None,
        },
        "sources": {
            "folders": {name: relative(path, root) if path else None for name, path in folders.items()},
            "files": files,
            "warnings": warnings,
            "selected_module_paths": sorted(relevant_paths),
            "missing_or_unreadable": [
                {
                    "gap_id": gap["id"],
                    "kind": gap["kind"],
                    "subject": gap["subject"],
                    "source_status": gap["source_status"],
                    "impact": gap["impact"],
                }
                for gap in open_gaps
                if gap["kind"] in {"module_source", "readable_module_library", "readable_attached_library", "missing_ddl"}
            ],
        },
        "modules": [module],
        "logic": {
            "call_graph": [
                {"from_unit_id": unit["id"], "from_name": unit["name"], "calls": unit.get("calls", [])}
                for unit in all_code_units(module)
                if unit.get("calls")
            ],
            "messages": sorted(messages.values(), key=lambda item: item["id"]),
            "message_catalog": message_catalog,
            "property_overrides": sorted(overrides, key=lambda item: item["id"]),
            "sql_references": sorted(sql_references.values(), key=lambda item: item["id"]),
            "unresolved_calls": unresolved_calls,
        },
        "behavior_ledger": behavior,
        "ddl": {
            "catalog": ddl_catalog,
            "referenced_objects": [
                {"name": name, "ddl_found": name in ddl_by_name, "ddl_record_ids": [record["id"] for record in ddl_by_name.get(name, [])]}
                for name in referenced_names
            ],
            "missing_objects": missing_ddl,
            "object_type_counts": dict(sorted(Counter(record["type"] for record in ddl_catalog).items())),
        },
        "gaps": gaps,
        "coverage": coverage,
        "incremental": {
            "mode": "incremental_supplement" if supplemental and previous else ("incremental_snapshot" if previous else "first_run"),
            "compiler_transition": {
                "changed": compiler_changed,
                "previous_version": previous_extractor_version or None,
                "current_version": EXTRACTOR_VERSION,
                "analysis": "full_reparse_of_available_effective_sources" if compiler_changed else "same_compiler_semantics",
            },
            "change_set": changes,
            "reuse": {"module": form_parse_mode, **ddl_incremental},
            "impacted": impact,
        },
    }
    return result


def contract_digest(value: str, length: int = 12) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length].upper()


def source_id(module_id: str, relative_path: str) -> str:
    return f"SRC-{module_id.upper()}-{contract_digest(relative_path.replace(chr(92), '/').lower())}"


def fact_id(module_id: str, fact_kind: str, semantic_key: str) -> str:
    return f"FACT-{module_id.upper()}-{fact_kind.upper()}-{contract_digest(semantic_key.upper())}"


def path_id(module_id: str, operation: str, entry_point: str) -> str:
    return f"PATH-{module_id.upper()}-{operation.upper()}-{contract_digest(entry_point.upper())}"


def contract_gap_id(module_id: str, gap_kind: str, subject: str) -> str:
    return f"GAP-{module_id.upper()}-{gap_kind.upper()}-{contract_digest(subject.upper())}"


def source_role(record: dict[str, Any]) -> str:
    if record["area"] == "ddl":
        return "ddl"
    if record["area"] == "ui":
        return "screenshot"
    return {
        ".xml": "forms_xml",
        ".fmt": "fmt",
        ".fmb": "fmb",
        ".fmx": "fmx",
        ".pld": "pld",
        ".pll": "pll",
        ".err": "err",
        ".mmb": "menu",
        ".mmx": "menu",
        ".olb": "object_library",
    }.get(record["extension"], "other")


def media_type(record: dict[str, Any]) -> str:
    if record["area"] == "ui":
        return {
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp",
            ".tif": "image/tiff", ".tiff": "image/tiff",
        }.get(record["extension"], "application/octet-stream")
    if record["extension"] == ".xml":
        return "application/xml"
    if record["state"] == "binary_only":
        return "application/octet-stream"
    return "text/plain"


def artifact_envelope(module_id: str, run_id: str, generated_at: str, input_hash: str, records: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    envelope = {
        "schema_version": "1.0",
        "extractor_version": EXTRACTOR_VERSION,
        "module_id": module_id.upper(),
        "run_id": run_id,
        "generated_at": generated_at,
        "input_manifest_sha256": input_hash,
        "records": records,
    }
    envelope.update(extra)
    return envelope


def raw_locator(module_id: str, source_path_value: str, locator: str, symbol: Optional[str] = None,
                excerpt: Optional[str] = None, content_hash: Optional[str] = None) -> dict[str, Any]:
    suffix = Path(source_path_value).suffix.lower()
    return {
        "source_id": source_id(module_id, source_path_value),
        "relative_path": source_path_value,
        "locator_kind": "xml_object" if suffix == ".xml" else (
            "ddl_object" if suffix == ".sql" and source_path_value.lower().startswith("ddl/") else (
                "file" if suffix in BINARY_FORM_EXTENSIONS or suffix in IMAGE_EXTENSIONS else "plsql_symbol"
            )
        ),
        "locator": locator,
        "symbol": symbol,
        "line_start": None,
        "line_end": None,
        "content_sha256": content_hash,
        "excerpt": excerpt[:240] if excerpt else None,
    }


def crud_value(record: dict[str, Any], operation: str, unresolved_runtime: bool) -> dict[str, Any]:
    design = record.get("design_crud", {}).get(operation)
    effective_value = record.get("effective_crud", {}).get(operation)
    overrides = [
        {
            "condition": override.get("condition"),
            "value": override.get("value"),
            "entry_point": override.get("locator"),
            "locators": [],
        }
        for override in record.get("runtime_overrides", [])
        if override.get("operation") == operation
    ]
    effective: Any = effective_value if effective_value is not None else "unknown"
    if overrides:
        effective = "conditional"
    return {
        "design_time": design,
        "inherited": record.get("inherited_crud", {}).get(operation),
        "runtime_overrides": overrides,
        "effective": effective,
        "unresolved_runtime_override": unresolved_runtime,
    }


def make_fact(module_id: str, kind: str, semantic_key: str, subject_kind: str, subject_key: str,
              predicate: str, value: Any, locators: list[dict[str, Any]], evidence_type: str = "explicit",
              confidence: str = "high", derivation: Optional[str] = None, status: str = "verified") -> dict[str, Any]:
    value_type = "object" if isinstance(value, dict) else "array" if isinstance(value, list) else "boolean" if isinstance(value, bool) else "number" if isinstance(value, (int, float)) else "null" if value is None else "string"
    return {
        "fact_id": fact_id(module_id, kind, semantic_key),
        "fact_kind": kind,
        "subject": {"kind": subject_kind, "key": subject_key},
        "predicate": predicate,
        "value": value,
        "value_type": value_type,
        "evidence_type": evidence_type,
        "confidence": confidence,
        "derivation": derivation,
        "locators": locators,
        "scope": "legacy_as_is",
        "status": status,
        "invalidated_by": [],
        "related_gap_ids": [],
    }


def normalized_facts(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    module = evidence["modules"][0]
    module_id = module["module_id"].upper()
    facts: list[dict[str, Any]] = []
    module_source = module.get("source_paths", [None])[0]
    module_locator = raw_locator(module_id, module_source, f"FormModule[@Name='{module_id}']", module_id, module.get("title")) if module_source else []
    facts.append(make_fact(module_id, "module_identity", module_id, "forms_module", module_id, "title", module.get("title"), [module_locator] if module_locator else [], confidence="high" if module_source else "unresolved", status="verified" if module_source else "unknown"))

    for screenshot in module.get("runtime_screenshots", []):
        locator = raw_locator(module_id, screenshot["path"], "full-image/title-match", module.get("title"), module.get("title"), screenshot.get("sha256"))
        facts.append(
            make_fact(
                module_id, "runtime_screenshot", screenshot["path"], "ui_screenshot", screenshot["path"],
                "module_association", screenshot, [locator], evidence_type="derived", confidence="high",
                derivation="The screenshot filename exactly matches the Forms module title.",
            )
        )

    for library in module.get("attached_libraries", []):
        locator = raw_locator(module_id, module_source, f"FormModule/AttachedLibrary[@Name='{library['name']}']", library["name"]) if module_source else None
        facts.append(make_fact(module_id, "attachment", library["name"], "attached_library", f"{module_id}/{library['name']}", "attached", library, [locator] if locator else []))
    for collection, kind, subject_kind in (
        ("windows", "window", "forms_window"), ("canvases", "canvas", "forms_canvas"), ("tab_pages", "tab", "forms_tab"),
        ("relations", "relation", "forms_relation"), ("lovs", "lov", "forms_lov"), ("record_groups", "record_group", "forms_record_group"),
    ):
        for record in module.get(collection, []):
            locator = raw_locator(module_id, module_source, f"FormModule/{subject_kind}[{record['id']}]", record["id"]) if module_source else None
            facts.append(make_fact(module_id, kind, record["id"], subject_kind, f"{module_id}/{record['id']}", "definition", record, [locator] if locator else []))

    tab_labels = {page["id"]: page.get("label") or page["id"] for page in module.get("tab_pages", [])}
    unresolved_runtime = any(
        gap.get("status") != "closed" and gap.get("kind") in {"readable_module_library", "readable_attached_library"}
        for gap in evidence.get("gaps", [])
    )
    for block in module.get("blocks", []):
        block_key = f"{module_id}/{block['id']}"
        locator = raw_locator(module_id, module_source, f"FormModule/Block[@Name='{block['id']}']", block["id"]) if module_source else None
        profile = {operation: crud_value(block, operation, unresolved_runtime) for operation in ("query", "create", "update", "delete")}
        facts.append(make_fact(module_id, "block_crud", block_key, "forms_block", block_key, "crud_profile", profile, [locator] if locator else [], confidence="medium" if unresolved_runtime else "high"))
        facts.append(make_fact(module_id, "block_database_mapping", block_key, "forms_block", block_key, "database_sources", {"query": block.get("query_data_source"), "dml": block.get("dml_data_name"), "persistence_applicable": block.get("block_role") == "database_persistence", "mapping_evidence": "explicit" if block.get("block_role") == "database_persistence" else "not_applicable"}, [locator] if locator else []))
        for item in block.get("items", []):
            item_key = f"{block_key}/{item['name']}"
            item_locator = raw_locator(module_id, module_source, f"FormModule/Block[@Name='{block['id']}']/Item[@Name='{item['name']}']", item["id"]) if module_source else None
            tab_page = item.get("tab_page")
            canvas = item.get("canvas")
            region_kind = "tab_page" if tab_page else "canvas" if canvas else "unassigned"
            region_id = tab_page or canvas or "UNASSIGNED"
            rendered = bool(tab_page or canvas) and item.get("visible") is not False
            placement = {
                "block": block["id"], "item": item["name"], "canvas": canvas,
                "tab_page": tab_page, "tab_label": tab_labels.get(tab_page) if tab_page else None,
                "region_kind": region_kind, "region_id": region_id,
                "presentation_shape": "technical_support" if not rendered else ("grid_column" if (block.get("records_displayed") or 0) > 1 else "field"),
                "visible": item.get("visible"), "rendered": rendered, "prompt": item.get("prompt"), "item_type": item.get("item_type"),
            }
            facts.append(make_fact(module_id, "item_visual_placement", item_key, "forms_item", item_key, "visual_placement", placement, [item_locator] if item_locator else [], confidence="high" if item_locator else "unresolved", status="verified" if item_locator else "unknown"))
            item_profile = {operation: crud_value(item, operation, unresolved_runtime) for operation in ("query", "create", "update")}
            facts.append(make_fact(module_id, "item_crud", item_key, "forms_item", item_key, "crud_profile", item_profile, [item_locator] if item_locator else [], confidence="medium" if unresolved_runtime else "high"))
            persistence_applicable = block.get("block_role") == "database_persistence" and bool(item.get("database_item"))
            mapping_type = "explicit" if persistence_applicable and item.get("mapping_status") == "explicit" else "unknown" if persistence_applicable else "not_applicable"
            mapping_confidence = "high" if mapping_type == "explicit" else "unresolved"
            facts.append(make_fact(module_id, "item_column_mapping", item_key, "forms_item", item_key, "physical_column", {"database_item": item.get("database_item"), "column": item.get("database_column"), "mapping_status": item.get("mapping_status"), "persistence_applicable": persistence_applicable}, [item_locator] if item_locator else [], evidence_type=mapping_type, confidence=mapping_confidence if persistence_applicable else "high", status="verified" if mapping_type in {"explicit", "not_applicable"} or not item.get("database_item") else "unknown"))

    def aggregate_effective(values: list[Any]) -> Any:
        known = [value for value in values if value is not None]
        if not known:
            return "unknown"
        if "conditional" in known or len(set(str(value) for value in known)) > 1:
            return "conditional"
        return known[0]

    module_profile = {}
    for operation in ("query", "create", "update", "delete"):
        design_values = [block.get("design_crud", {}).get(operation) for block in module.get("blocks", []) if block.get("database_block")]
        effective_values = [block.get("effective_crud", {}).get(operation) for block in module.get("blocks", []) if block.get("database_block")]
        module_profile[operation] = {
            "design_time": aggregate_effective(design_values), "inherited": None, "runtime_overrides": [],
            "effective": aggregate_effective(effective_values), "unresolved_runtime_override": unresolved_runtime,
        }
    facts.append(make_fact(module_id, "module_crud", module_id, "forms_module", module_id, "crud_profile", module_profile, [], evidence_type="derived", confidence="medium", derivation="Aggregate of database-block CRUD facts."))

    region_items: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for block in module.get("blocks", []):
        for item in block.get("items", []):
            region = item.get("tab_page") or item.get("canvas") or "UNASSIGNED"
            region_items[region].append((block, item))
    for region, pairs in sorted(region_items.items()):
        profile = {}
        for operation in ("query", "create", "update"):
            profile[operation] = {
                "design_time": aggregate_effective([item.get("design_crud", {}).get(operation) for _, item in pairs]),
                "inherited": None, "runtime_overrides": [],
                "effective": aggregate_effective([item.get("effective_crud", {}).get(operation) for _, item in pairs]),
                "unresolved_runtime_override": unresolved_runtime,
            }
        facts.append(make_fact(module_id, "region_crud", region, "forms_region", f"{module_id}/{region}", "crud_profile", profile, [], evidence_type="derived", confidence="medium", derivation="Aggregate of independently mapped item CRUD facts; block names do not define visual regions."))

    for block in module.get("blocks", []):
        table = block.get("dml_data_name") or block.get("query_data_source")
        if not table:
            continue
        for item in block.get("items", []):
            column = item.get("database_column")
            if not column:
                continue
            key = f"{unqualified(table)}/{unqualified(column)}"
            profile = {operation: crud_value(item, operation, unresolved_runtime) for operation in ("query", "create", "update")}
            profile["delete"] = crud_value(block, "delete", unresolved_runtime)
            facts.append(make_fact(module_id, "physical_column_crud", key, "database_column", key, "crud_profile", profile, [], evidence_type="derived", confidence="medium", derivation=f"Derived from explicit item mapping {item['id']} and block {block['id']} CRUD facts."))

    for unit in all_code_units(module):
        kind = "trigger" if unit["kind"] == "trigger" else "program_unit"
        # Unit names can be overloaded or repeated in generated PLD sources.
        # The parser's stable unit ID includes the defining source occurrence
        # and is therefore the correct semantic identity boundary.
        semantic_key = unit["id"]
        subject_key = f"{unit['source_path']}/{unit['scope']}/{unit.get('block_id') or ''}/{unit.get('item_id') or ''}/{unit['name']}/{unit['id']}"
        locator = raw_locator(module_id, unit["source_path"], unit["locator"], unit["name"], unit["code"][:240], unit["code_sha256"])
        value = {
            "name": unit["name"], "scope": unit["scope"], "block_id": unit.get("block_id"),
            "item_id": unit.get("item_id"), "decoded_source": unit["code"], "code_sha256": unit["code_sha256"],
        }
        facts.append(make_fact(module_id, kind, semantic_key, kind, f"{module_id}/{subject_key}", "decoded_definition", value, [locator]))
        for call_name in sorted({call["name"] for call in unit.get("calls", [])}):
            call_key = f"{semantic_key}->{call_name}"
            facts.append(make_fact(module_id, "call_edge", call_key, kind, f"{module_id}/{subject_key}", "calls", call_name, [locator]))

    for obj in evidence.get("ddl", {}).get("catalog", []):
        key = f"{obj['type']}/{obj['qualified_name']}"
        locator = raw_locator(module_id, obj["source_path"], f"DDL/{obj['type']}[@Name='{obj['qualified_name']}']", obj["qualified_name"], f"{obj['type']} {obj['qualified_name']}", obj["source_sha256"])
        facts.append(make_fact(module_id, "database_object", key, "database_object", obj["qualified_name"], "definition", obj, [locator]))
        for comment in obj.get("comments", []):
            target = comment.get("column") or comment.get("table") or obj["qualified_name"]
            comment_key = f"{obj['qualified_name']}/{comment.get('target_type')}/{target}"
            comment_locator = raw_locator(
                module_id, obj["source_path"], f"DDL/COMMENT[{comment.get('source_line')}]",
                str(target), comment.get("text"), obj["source_sha256"],
            )
            comment_locator["line_start"] = comment.get("source_line")
            comment_locator["line_end"] = comment.get("source_line")
            facts.append(make_fact(
                module_id, "database_comment", comment_key, "database_object", obj["qualified_name"],
                "comment", comment, [comment_locator],
            ))
    return facts


def build_behavior_paths(evidence: dict[str, Any], gap_records: Optional[list[dict[str, Any]]] = None) -> list[dict[str, Any]]:
    module = evidence["modules"][0]
    module_id = module["module_id"].upper()
    units = {unit["id"]: unit for unit in all_code_units(module)}
    operation_names = {"create": "insert", "validation": "validate"}
    paths: list[dict[str, Any]] = []
    item_map = {item["id"]: item for block in module.get("blocks", []) for item in block.get("items", [])}
    tab_labels = {page["id"]: page.get("label") or page["id"] for page in module.get("tab_pages", [])}
    blocks_by_id = {block["id"]: block for block in module.get("blocks", [])}
    cascade_edges = {
        (obj.get("name"), constraint.get("references_object"))
        for obj in evidence.get("ddl", {}).get("catalog", [])
        for constraint in obj.get("constraints", [])
        if constraint.get("type") == "foreign_key" and constraint.get("on_delete") == "cascade"
    }
    for internal_operation, ledger in evidence.get("behavior_ledger", {}).items():
        operation = operation_names.get(internal_operation, internal_operation)
        for entry in ledger.get("entry_points", []):
            unit = units.get(entry["unit_id"])
            if not unit:
                continue
            entry_detail = next((detail for detail in ledger.get("entry_paths", []) if detail.get("entry_unit_id") == entry["unit_id"]), {})
            symbol = ".".join(value for value in (entry.get("item_id") or entry.get("block_id"), entry["name"]) if value)
            locator = raw_locator(module_id, unit["source_path"], unit["locator"], symbol, unit["code"][:240], unit["code_sha256"])
            reachable_units = [units[unit_id] for unit_id in entry_detail.get("reachable_routine_ids", [entry["unit_id"]]) if unit_id in units]
            call_chain = []
            for edge in entry_detail.get("call_edges", []):
                source_unit = units.get(edge["from_unit_id"])
                if source_unit:
                    call_chain.append({"from": edge["from"], "to": edge["to"], "locators": [raw_locator(module_id, source_unit["source_path"], source_unit["locator"], source_unit["name"])]})
            for unresolved in entry_detail.get("unresolved_calls", []):
                caller = next(
                    (candidate for candidate in reachable_units if unresolved in {call["name"] for call in candidate.get("calls", [])}),
                    unit,
                )
                call_chain.append({
                    "from": caller["name"], "to": unresolved, "resolution": "unresolved",
                    "locators": [raw_locator(module_id, caller["source_path"], caller["locator"], caller["name"])],
                })
            path_sql = entry_detail.get("sql_references", [])
            path_messages = entry_detail.get("messages", [])
            reads = sorted({ref["object"] for ref in path_sql if ref["access"] == "read"})
            writes = sorted({ref["object"] for ref in path_sql if ref["access"] == "write"})
            forms_blocks = sorted({candidate.get("block_id") for candidate in reachable_units if candidate.get("block_id")} | ({entry.get("block_id")} if entry.get("block_id") else set()))
            code_block_refs = {
                block_id for block_id in blocks_by_id
                if re.search(rf"\b{re.escape(block_id)}\s*\.", unit.get("code", ""), re.IGNORECASE)
            }
            forms_blocks = sorted(set(forms_blocks) | code_block_refs)
            if internal_operation in {"create", "update", "delete"}:
                writes = sorted(
                    set(writes)
                    | {
                        unqualified(block["dml_data_name"])
                        for block_id in forms_blocks
                        for block in [blocks_by_id.get(block_id)]
                        if block and block.get("block_role") == "database_persistence"
                        and block.get("dml_data_name")
                        and block.get("effective_crud", {}).get(internal_operation) in {True, "conditional"}
                    }
                )
            scopes: set[str] = set()
            field_effects = []
            ui_field_effects = []
            crud_operation = internal_operation if internal_operation in {"query", "create", "update"} else None
            for block in module.get("blocks", []):
                if forms_blocks and block["id"] not in forms_blocks:
                    continue
                for item in block.get("items", []):
                    if item.get("tab_page"):
                        scopes.add(tab_labels.get(item["tab_page"], item["tab_page"]))
                    elif item.get("canvas"):
                        scopes.add(item["canvas"])
                    if crud_operation and item.get("effective_crud", {}).get(crud_operation) is True:
                        if item.get("mapping_status") == "explicit" and item.get("database_column"):
                            field_effects.append({"item": item["id"], "column": item["database_column"], "effect": crud_operation})
                        else:
                            ui_field_effects.append({"item": item["id"], "effect": crud_operation, "physical_mapping": "unresolved"})
            dependency_checks = []
            if internal_operation == "delete":
                delete_target = next(
                    (unqualified(blocks_by_id[block_id]["dml_data_name"]) for block_id in forms_blocks if block_id in blocks_by_id and blocks_by_id[block_id].get("dml_data_name")),
                    None,
                )
                for candidate in reachable_units:
                    effect = "hard_blocker" if "CHK" in candidate["name"] else "warning_confirmation" if "WRN" in candidate["name"] else "unresolved"
                    for reference in candidate.get("sql_references", []):
                        if reference["access"] == "read":
                            # A hard blocker prevents the database delete, so
                            # an otherwise-declared cascade is not an observed
                            # effect of that path. Cascade is material on the
                            # second-confirmation warning branch only.
                            cascade = effect == "warning_confirmation" and bool(delete_target) and (reference["object"], delete_target) in cascade_edges
                            dependency_checks.append({
                                "object": reference["object"], "effect": effect, "routine": candidate["name"],
                                "locator": reference["locator"], "message_code": "5" if effect == "hard_blocker" else "22" if effect == "warning_confirmation" else None,
                                "stop_effect": "raise_failure" if effect == "hard_blocker" else None,
                                "confirmation": "second_delete_action" if effect == "warning_confirmation" else None,
                                "database_cascade": "on_delete_cascade" if cascade else None,
                                "enforcement": "application_and_database_cascade" if cascade else "application_check",
                            })
                dependency_checks = list({
                    (check["object"], check["effect"], check["routine"]): check
                    for check in dependency_checks
                }.values())
                dependency_checks.sort(key=lambda check: (check["effect"], check["object"], check["routine"]))
            message_codes = {str(message.get("code")) for message in path_messages if message.get("code") is not None}
            outcomes = []
            stop_effects = []
            validation_stop_branches = []
            for candidate in reachable_units:
                failure_count = len(re.findall(r"\b(?:QMS\$FORMS_ERRORS\.)?RAISE_FAILURE\b", candidate.get("code", ""), re.IGNORECASE))
                candidate_messages = candidate.get("messages", [])
                for ordinal in range(failure_count):
                    message = candidate_messages[ordinal] if ordinal < len(candidate_messages) else None
                    validation_stop_branches.append({
                        "branch_id": stable_id("VSTOP", candidate["id"], ordinal + 1),
                        "unit": candidate["name"], "ordinal": ordinal + 1,
                        "message_id": message.get("id") if message else None,
                        "message_code": message.get("code") if message else None,
                        "message_line": message.get("code_line") if message else None,
                        "stop_effect": "raise_failure", "result": "abort_operation",
                        "predicate_mapping": "source_control_flow_not_yet_associated",
                    })
            if "5" in message_codes:
                outcomes.append({"result": "delete_aborted", "condition": "dependent record exists", "message_code": "5"})
                stop_effects.append({"effect": "raise_failure", "result": "abort_operation", "message_code": "5"})
            if "22" in message_codes:
                outcomes.append({"result": "first_delete_attempt_stopped", "condition": "warning dependency exists", "message_code": "22", "state_effect": "user_warned_on_delete"})
                outcomes.append({"result": "record_marked_for_delete", "condition": "user invokes delete again after warning", "message_code": "22", "physical_delete_timing": "deferred_until_forms_posting"})
                stop_effects.append({"effect": "form_trigger_failure", "result": "abort_first_delete_attempt", "message_code": "22"})
            builtin_names = {record.get("name") for record in entry_detail.get("forms_builtins", [])}
            navigation_actions = entry_detail.get("navigation_actions", [])
            navigation_parameter_context = sorted(
                {
                    re.sub(r"\s+", " ", line).strip()
                    for candidate in reachable_units
                    for line in candidate.get("code", "").splitlines()
                    if re.search(
                        r"\b(?:PARAMETER|GLOBAL)\s*\.|\bP_[A-Z0-9_$#]+\b|CG\$STARTUP_MODE",
                        line,
                        re.IGNORECASE,
                    )
                }
            )[:16]
            if internal_operation == "create" and "INSERT_RECORD" in builtin_names:
                outcomes.append({
                    "result": "implicit_forms_insert", "condition": "non-custom ON-INSERT branch",
                    "mechanism": "INSERT_RECORD", "transaction_completion": "unknown",
                })
            if internal_operation == "create" and "ON_INSERT" in entry_detail.get("unresolved_calls", []):
                outcomes.append({
                    "result": "custom_insert_branch_unresolved", "condition": "CTT.SCT_PGP_ID is not null",
                    "routine": "ON_INSERT", "transaction_completion": "unknown",
                })
            for action in navigation_actions:
                outcomes.append(
                    {
                        "result": "focus_item" if action.get("name") == "GO_ITEM" else "open_or_transfer_form",
                        "mechanism": action.get("name"),
                        "target": action.get("target"),
                        "parameter_context": navigation_parameter_context,
                        "source_path": action.get("source_path"),
                        "locator": action.get("locator"),
                        "code_line": action.get("code_line"),
                    }
                )
            database_effects = [
                {"object": reference["object"], "access": reference["access"], "operation": reference["operation"], "source_path": reference["source_path"], "locator": reference["locator"]}
                for reference in path_sql
            ]
            explicit_sql_writes = {reference["object"] for reference in path_sql if reference["access"] == "write"}
            database_effects.extend(
                {
                    "object": name, "access": "write", "operation": operation.upper(),
                    "source_path": unit["source_path"], "locator": unit["locator"], "mechanism": "implicit_oracle_forms_dml",
                }
                for name in writes if name not in explicit_sql_writes
            )
            path_record = {
                "path_id": path_id(module_id, operation, symbol),
                "operation": operation,
                "entry_point": {"scope": entry["scope"], "symbol": symbol, "locators": [locator]},
                "reachability": "reachable",
                "call_chain": call_chain,
                "calls": call_chain,
                "user_scope": sorted(scopes),
                "forms_blocks": forms_blocks,
                "database_reads": reads,
                "database_writes": writes,
                "field_effects": field_effects,
                "ui_field_effects": ui_field_effects,
                "preconditions": ([{"kind": "block_where_clause", "value": block.get("where_clause")} for block in module.get("blocks", []) if block["id"] in forms_blocks and block.get("where_clause")] if internal_operation == "query" else []),
                "validations": [{"message_id": message["id"], "code": message.get("code"), "text": message.get("text"), "severity": message.get("severity")} for message in path_messages],
                "branches": entry_detail.get("branches", []),
                "forms_builtins": entry_detail.get("forms_builtins", []),
                "validation_stop_branches": validation_stop_branches,
                "defaults_and_derivations": [],
                "messages": path_messages,
                "dependency_checks": dependency_checks,
                "database_effects": database_effects,
                "side_effects": (
                    [{"object": name, "effect": "database_write"} for name in writes]
                    + [
                        {
                            "object": action.get("target"),
                            "effect": "focus_item" if action.get("name") == "GO_ITEM" else "open_or_transfer_form",
                            "mechanism": action.get("name"),
                            "parameter_context": navigation_parameter_context,
                            "source_path": action.get("source_path"),
                            "locator": action.get("locator"),
                            "code_line": action.get("code_line"),
                        }
                        for action in navigation_actions
                    ]
                ),
                "transaction": {"boundary": "unknown", "commit_owner": "unknown", "rollback_behavior": "unknown", "concurrency_behavior": "unknown", "dml_timing": "deferred_until_forms_posting" if internal_operation == "delete" else "forms_managed"},
                "outcomes": outcomes,
                "stop_effects": stop_effects,
                "unresolved_calls": entry_detail.get("unresolved_calls", []),
                "locators": [locator],
                "confidence": "high" if not entry_detail.get("unresolved_calls") else "medium",
                "gap_ids": [],
            }
            paths.append(path_record)
    # Oracle Forms performs base-table DML from block mappings even when no
    # block-local SQL trigger exists. Emit one durable path per applicable
    # persistence block and write operation so SCL/SPL delete cannot vanish.
    for block in module.get("blocks", []):
        if block.get("block_role") != "database_persistence" or not block.get("dml_data_name"):
            continue
        for internal_operation, operation in (("create", "insert"), ("update", "update"), ("delete", "delete")):
            if block.get("effective_crud", {}).get(internal_operation) not in {True, "conditional"}:
                continue
            symbol = f"{block['id']}.IMPLICIT_FORMS_{operation.upper()}"
            source = module.get("source_paths", [""])[0]
            locator = raw_locator(module_id, source, f"FormModule/Block[@Name='{block['id']}']/@DMLDataName", block["id"], block["dml_data_name"])
            physical_fields = [
                {"item": item["id"], "column": item["database_column"], "effect": internal_operation}
                for item in block.get("items", [])
                if internal_operation != "delete" and item.get("effective_crud", {}).get(internal_operation) is True
                and item.get("mapping_status") == "explicit" and item.get("database_column")
            ]
            ui_fields = [
                {"item": item["id"], "effect": internal_operation, "physical_mapping": "unresolved"}
                for item in block.get("items", [])
                if internal_operation != "delete" and item.get("effective_crud", {}).get(internal_operation) is True
                and item.get("mapping_status") != "explicit"
            ]
            table = unqualified(block["dml_data_name"])
            paths.append({
                "path_id": path_id(module_id, operation, symbol), "operation": operation,
                "entry_point": {"scope": "forms_implicit_dml", "symbol": symbol, "locators": [locator]},
                "reachability": "implicit_forms_runtime", "call_chain": [], "calls": [],
                "user_scope": sorted({tab_labels.get(item.get("tab_page"), item.get("tab_page")) if item.get("tab_page") else item.get("canvas") for item in block.get("items", []) if item.get("tab_page") or item.get("canvas")}),
                "forms_blocks": [block["id"]], "database_reads": [], "database_writes": [table],
                "field_effects": physical_fields, "ui_field_effects": ui_fields,
                "preconditions": [], "validations": [], "branches": [], "forms_builtins": [], "validation_stop_branches": [], "defaults_and_derivations": [], "messages": [],
                "dependency_checks": [],
                "database_effects": [{"object": table, "access": "write", "operation": operation.upper(), "source_path": source, "locator": locator["locator"], "mechanism": "implicit_oracle_forms_dml"}],
                "side_effects": [{"object": table, "effect": "database_write", "mechanism": "implicit_oracle_forms_dml"}],
                "transaction": {"boundary": "unknown", "commit_owner": "unknown", "rollback_behavior": "unknown", "concurrency_behavior": "unknown", "dml_timing": "deferred_until_forms_posting" if internal_operation == "delete" else "forms_managed"},
                "outcomes": [], "stop_effects": [], "unresolved_calls": [], "locators": [locator],
                "confidence": "high", "gap_ids": [],
            })
    if gap_records:
        by_operation: dict[str, list[str]] = defaultdict(list)
        for gap in gap_records:
            for operation in gap.get("affected_operations", []):
                by_operation[operation_names.get(operation, operation)].append(gap["gap_id"])
        for record in paths:
            record["gap_ids"] = sorted(set(by_operation.get(record["operation"], [])))
    return sorted(paths, key=lambda item: item["path_id"])


def contract_gaps(evidence: dict[str, Any], previous: Optional[dict[str, Any]], run_id: str,
                  behavior_paths: list[dict[str, Any]]) -> list[dict[str, Any]]:
    module_id = evidence["modules"][0]["module_id"].upper()
    previous_records = {
        (record.get("gap_kind"), record.get("subject")): record
        for record in (previous or {}).get("artifacts", {}).get("gaps", {}).get("records", [])
    }
    kind_map = {
        "module_source": "source_missing", "readable_module_library": "binary_only",
        "readable_attached_library": "binary_only", "missing_ddl": "missing_ddl",
        "unresolved_routine": "unresolved_call", "operation_entry_point": "extraction_uncovered",
        "expected_source": "source_missing", "implicit_forms_entry_point": "unresolved_call",
        "validation_branch_mapping": "extraction_uncovered",
        "ambiguous_mapping": "ambiguous_mapping", "missing_message_text": "missing_message_text",
        "audit_column_population": "runtime_only",
    }
    status_map = {"closed": "resolved", "open": "open", "narrowed": "narrowed", "reopened": "reopened"}
    paths_by_operation: dict[str, list[str]] = defaultdict(list)
    for record in behavior_paths:
        paths_by_operation[record["operation"]].append(record["path_id"])
    operation_names = {"create": "insert", "validation": "validate"}
    records: list[dict[str, Any]] = []
    for gap in evidence.get("gaps", []):
        gap_kind = kind_map.get(gap["kind"], "extraction_uncovered")
        subject = str(gap["subject"])
        old = previous_records.get((gap_kind, subject))
        status = status_map.get(gap.get("status"), "open")
        gap_identifier = contract_gap_id(module_id, gap_kind, subject)
        history = list((old or {}).get("history", []))
        if old and old.get("status") != status:
            history.append({"run_id": run_id, "from": old.get("status"), "to": status, "reason": gap.get("reason")})
        affected_operations = [operation_names.get(operation, operation) for operation in gap.get("affected_operations", [])]
        expected_by_locators = []
        fallback_locators = []
        if gap.get("expected_by"):
            expected_by_locators = [
                raw_locator(module_id, record["source_path"], record["locator"], record.get("symbol") or subject)
                for record in gap.get("expected_by", [])
            ]
        elif gap["kind"] == "missing_ddl":
            expected_by_locators = [raw_locator(module_id, ref["source_path"], ref["locator"], subject) for ref in evidence.get("logic", {}).get("sql_references", []) if ref["object"] == subject]
        elif gap["kind"] == "unresolved_routine":
            for unit in all_code_units(evidence["modules"][0]):
                if subject in {call["name"] for call in unit.get("calls", [])}:
                    expected_by_locators.append(raw_locator(module_id, unit["source_path"], unit["locator"], unit["name"]))
        elif gap["kind"] in {"readable_module_library", "readable_attached_library"}:
            for library in evidence["modules"][0].get("attached_libraries", []):
                if library["name"].upper() == subject.upper() and evidence["modules"][0].get("source_paths"):
                    source = evidence["modules"][0]["source_paths"][0]
                    expected_by_locators.append(raw_locator(module_id, source, f"FormModule/AttachedLibrary[@Name='{subject}']", subject))
            for source_record in evidence.get("sources", {}).get("files", []):
                if (
                    source_record.get("area") == "form"
                    and source_record.get("state") == "binary_only"
                    and normalize_module_stem(Path(source_record["path"])) == subject.lower()
                ):
                    fallback_locators.append(
                        raw_locator(
                            module_id,
                            source_record["path"],
                            f"File[{source_record['path']}]",
                            subject,
                            f"Binary-only {source_record.get('extension')} source",
                            source_record.get("sha256"),
                        )
                    )
        classification = "source_gap" if gap_kind in {"source_missing", "binary_only", "missing_ddl", "unresolved_call", "missing_message_text"} else "extraction_gap"
        recommended = {
            "binary_only": f"Export or decompile {subject} to readable source and rerun affected slices.",
            "source_missing": f"Supply readable source for {subject} and rerun extraction.",
            "missing_ddl": f"Supply recursive DDL for {subject} and rerun database and affected behavior slices.",
            "unresolved_call": f"Supply the readable definition for {subject}, or validate its observable behavior at runtime.",
            "extraction_uncovered": f"Inspect or observe the {subject} behavior; absence in readable source is not proof of absence.",
            "ambiguous_mapping": f"Supply explicit mapping evidence for {subject}; do not infer a column from the item name.",
            "missing_message_text": f"Supply the message catalogue entry for {subject}; preserve the code/literal as incomplete evidence until then.",
            "runtime_only": f"Supply the runtime owner or database-trigger evidence for {subject}, or validate it through an observed insert/update trace.",
        }[gap_kind]
        resolution_evidence = list((old or {}).get("resolution_evidence", [])) if status == "resolved" else []
        resolution_id = f"RES-{module_id}-{gap_kind.upper()}-{contract_digest(subject.upper())}"
        if status == "resolved" and not resolution_evidence:
            if gap_kind == "ambiguous_mapping" and "." in subject:
                block_id, item_name = subject.split(".", 1)
                block = next((candidate for candidate in evidence["modules"][0].get("blocks", []) if candidate.get("id") == block_id), None)
                item = next((candidate for candidate in (block or {}).get("items", []) if candidate.get("name") == item_name), None)
                source = (evidence["modules"][0].get("source_paths") or [None])[0]
                if block and item and source:
                    resolution_evidence.append({
                        "decision_id": resolution_id,
                        "resolution_kind": "extractor_reclassification",
                        "extractor_version": EXTRACTOR_VERSION,
                        "reason": "The containing block is explicitly classified as non-persistent framework control; physical column mapping is not applicable.",
                        "locator": raw_locator(module_id, source, f"FormModule/Block[@Name='{block_id}']/Item[@Name='{item_name}']", subject),
                    })
            if gap_kind == "missing_ddl":
                matched = next((obj for obj in evidence.get("ddl", {}).get("catalog", []) if obj.get("name") == subject), None)
                if matched:
                    resolution_evidence.append({
                        "decision_id": resolution_id,
                        "resolution_kind": "source_supplied",
                        "locator": raw_locator(module_id, matched["source_path"], f"DDL/{matched['type']}[@Name='{matched['qualified_name']}']", matched["qualified_name"], content_hash=matched.get("source_sha256")),
                    })
            if not resolution_evidence:
                resolution_evidence.append({
                    "decision_id": resolution_id,
                    "resolution_kind": "evidence_reconciliation",
                    "extractor_version": EXTRACTOR_VERSION,
                    "reason": gap.get("resolution") or "The current normalized evidence no longer exhibits this gap.",
                })
        records.append(
            {
                "gap_id": gap_identifier,
                "gap_kind": gap_kind,
                "subject": subject,
                "expected_artifact_or_behavior": gap.get("reason"),
                "status": status,
                "first_seen_run_id": (old or {}).get("first_seen_run_id", run_id),
                "last_changed_run_id": run_id if not old or old.get("status") != status else (old or {}).get("last_changed_run_id", run_id),
                "why_expected": gap.get("reason"),
                "expected_by_locators": expected_by_locators,
                "affected_operations": sorted(set(affected_operations)),
                "affected_behavior": gap.get("impact") or "The unavailable evidence may affect shared or non-CRUD module behavior.",
                "affected_fact_ids": [],
                "affected_path_ids": sorted({path for operation in affected_operations for path in paths_by_operation.get(operation, [])}),
                "available_fallback_evidence": fallback_locators,
                "classification": classification,
                "evidence_impact": "none_resolved" if status == "resolved" else "material" if gap_kind in {"source_missing", "binary_only", "unresolved_call"} else "bounded_unknown",
                "recommended_action": recommended,
                "resolution_evidence": resolution_evidence,
                "history": history,
                "unresolved_facets": gap.get("unresolved_facets", []),
                "expected_path": gap.get("expected_path"),
                "expected_source_role": gap.get("expected_source_role"),
            }
        )
    # A module companion can also appear in AttachedLibrary declarations. Both
    # expectations describe one semantic missing readable library, not two
    # gaps. Merge them by stable contract ID and retain every binary locator.
    merged: dict[str, dict[str, Any]] = {}
    for record in records:
        identifier = record["gap_id"]
        if identifier not in merged:
            merged[identifier] = record
            continue
        existing = merged[identifier]
        for field in ("expected_by_locators", "available_fallback_evidence", "resolution_evidence", "history"):
            combined = existing.get(field, []) + record.get(field, [])
            unique: dict[str, Any] = {}
            for item in combined:
                unique[json.dumps(item, sort_keys=True, ensure_ascii=True)] = item
            existing[field] = list(unique.values())
        for field in ("affected_operations", "affected_fact_ids", "affected_path_ids"):
            existing[field] = sorted(set(existing.get(field, [])) | set(record.get(field, [])))
        if record.get("expected_artifact_or_behavior") and record.get("gap_kind") == "binary_only":
            existing["expected_artifact_or_behavior"] = "Readable source for the semantically unique attached/module library."
            existing["why_expected"] = "The library is attached and/or follows the module companion naming convention; all supplied copies are binary-only."
    return sorted(merged.values(), key=lambda item: item["gap_id"])


def contract_source_inventory(evidence: dict[str, Any], previous: Optional[dict[str, Any]], run_id: str,
                              gap_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    module_id = evidence["modules"][0]["module_id"].upper()
    selected = set(evidence.get("sources", {}).get("selected_module_paths", []))
    previous_records = {record.get("relative_path"): record for record in (previous or {}).get("artifacts", {}).get("source_inventory", {}).get("records", [])}
    records: list[dict[str, Any]] = []
    for record in evidence.get("sources", {}).get("files", []):
        path = record["path"]
        role = source_role(record)
        availability = "binary_only" if record["state"] == "binary_only" else "readable"
        parse_status = "not_parseable" if availability == "binary_only" or role == "screenshot" else (
            "parsed" if role in {"forms_xml", "pld", "fmt", "ddl"} and (path in selected or role == "ddl") else "not_attempted"
        )
        old = previous_records.get(path, {})
        records.append(
            {
                "source_id": source_id(module_id, path),
                "relative_path": path,
                "source_role": role,
                "module_association": [module_id] if path in selected else [],
                "media_type": media_type(record),
                "size_bytes": record["size"],
                "sha256": record["sha256"],
                "availability": availability,
                "parse_status": parse_status,
                "parse_warnings": [],
                "expected_by": [],
                "first_seen_run_id": old.get("first_seen_run_id", run_id),
                "last_seen_run_id": run_id,
            }
        )
    for gap in gap_records:
        if gap["status"] == "resolved" or gap["gap_kind"] not in {"source_missing", "binary_only", "missing_ddl"}:
            continue
        subject = gap["subject"]
        if gap.get("expected_path"):
            path = gap["expected_path"]
            role = gap.get("expected_source_role") or "other"
        elif gap["gap_kind"] == "missing_ddl":
            path = f"ddl/**/{subject}.sql"
            role = "ddl"
        elif subject.upper().endswith("L"):
            path = f"form/{subject.lower()}.pld"
            role = "pld"
        else:
            path = f"expected/{subject}"
            role = "other"
        if any(record["relative_path"] == path for record in records):
            continue
        old = previous_records.get(path, {})
        records.append(
            {
                "source_id": source_id(module_id, path), "relative_path": path, "source_role": role,
                "module_association": [module_id], "media_type": "text/plain", "size_bytes": 0, "sha256": None,
                "availability": "binary_only" if gap["gap_kind"] == "binary_only" else "missing",
                "parse_status": "not_parseable" if gap["gap_kind"] == "binary_only" else "not_attempted",
                "parse_warnings": [], "expected_by": gap["expected_by_locators"],
                "first_seen_run_id": old.get("first_seen_run_id", run_id), "last_seen_run_id": run_id,
            }
        )
    return sorted(records, key=lambda item: item["relative_path"].lower())


def contract_source_delta(current_inventory: list[dict[str, Any]], previous: Optional[dict[str, Any]],
                          facts: list[dict[str, Any]], paths: list[dict[str, Any]], gaps: list[dict[str, Any]],
                          affected_sections: list[str], compiler_transition: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    previous_inventory = (previous or {}).get("artifacts", {}).get("source_inventory", {}).get("records", [])
    current_by_path = {record["relative_path"]: record for record in current_inventory}
    previous_by_path = {record["relative_path"]: record for record in previous_inventory}
    added = set(current_by_path) - set(previous_by_path)
    removed = set(previous_by_path) - set(current_by_path)
    relocated: dict[str, str] = {}
    for old_path in sorted(removed):
        old = previous_by_path[old_path]
        if not old.get("sha256"):
            continue
        new_path = next((path for path in sorted(added) if current_by_path[path].get("sha256") == old.get("sha256") and current_by_path[path].get("source_role") == old.get("source_role")), None)
        if new_path:
            relocated[old_path] = new_path
            added.remove(new_path)
    records: list[dict[str, Any]] = []
    fact_paths = defaultdict(list)
    for fact in facts:
        for locator in fact.get("locators", []):
            fact_paths[locator.get("relative_path")].append(fact["fact_id"])
    behavior_paths = defaultdict(list)
    for path in paths:
        for locator in path.get("locators", []):
            behavior_paths[locator.get("relative_path")].append(path["path_id"])
    all_paths = sorted(set(current_by_path) | set(previous_by_path))
    handled_new = set(relocated.values())
    for source_path_value in all_paths:
        if source_path_value in handled_new:
            continue
        current = current_by_path.get(source_path_value)
        old = previous_by_path.get(source_path_value)
        if source_path_value in relocated:
            current = current_by_path[relocated[source_path_value]]
            change = "relocated"
            source_key = f"{source_path_value}->{relocated[source_path_value]}"
        elif old is None:
            change, source_key = "added", source_path_value
        elif current is None:
            change, source_key = "removed", source_path_value
        elif old.get("sha256") != current.get("sha256") or old.get("availability") != current.get("availability"):
            change, source_key = "changed", source_path_value
        else:
            change, source_key = "unchanged", source_path_value
        semantic_path = (current or old or {}).get("relative_path")
        affected_fact_ids = sorted(set(fact_paths.get(semantic_path, []))) if change != "unchanged" else []
        affected_path_ids = sorted(set(behavior_paths.get(semantic_path, []))) if change != "unchanged" else []
        affected_operations = {path["operation"] for path in paths if path["path_id"] in affected_path_ids}
        affected_gap_ids = sorted({gap["gap_id"] for gap in gaps if set(gap.get("affected_operations", [])) & affected_operations})
        records.append(
            {
                "source_key": source_key, "change": change,
                "previous_sha256": old.get("sha256") if old else None,
                "current_sha256": current.get("sha256") if current else None,
                "previous_source_id": old.get("source_id") if old else None,
                "current_source_id": current.get("source_id") if current else None,
                "affected_semantic_keys": [], "affected_fact_ids": affected_fact_ids,
                "affected_path_ids": affected_path_ids, "affected_gap_ids": affected_gap_ids,
                "affected_spec_sections": affected_sections if change != "unchanged" else [],
                "analysis_scope": "affected_slice" if change != "unchanged" else "none",
            }
        )
    transition = compiler_transition or {}
    if transition.get("changed"):
        records.append(
            {
                "source_key": "__extractor_semantics__",
                "change": "compiler_changed",
                "previous_sha256": None,
                "current_sha256": None,
                "previous_source_id": None,
                "current_source_id": None,
                "previous_extractor_version": transition.get("previous_version"),
                "current_extractor_version": transition.get("current_version"),
                "affected_semantic_keys": ["all_normalized_evidence"],
                "affected_fact_ids": sorted(fact["fact_id"] for fact in facts),
                "affected_path_ids": sorted(path["path_id"] for path in paths),
                "affected_gap_ids": sorted(gap["gap_id"] for gap in gaps),
                "affected_spec_sections": CANONICAL_SPEC_SECTIONS,
                "analysis_scope": transition.get("analysis") or "full_reparse_required",
            }
        )
    return records


def coverage_records(evidence: dict[str, Any], inventory: list[dict[str, Any]], facts: list[dict[str, Any]],
                     paths: list[dict[str, Any]], gaps: list[dict[str, Any]], stale_sections: list[str]) -> list[dict[str, Any]]:
    module_id = evidence["modules"][0]["module_id"].upper()
    blocks = [fact for fact in facts if fact["fact_kind"] == "block_crud"]
    items = [fact for fact in facts if fact["fact_kind"] == "item_crud"]
    tab_pages = [fact for fact in facts if fact["fact_kind"] == "tab"]
    visible_placements = [
        fact for fact in facts
        if fact["fact_kind"] == "item_visual_placement" and fact["value"].get("rendered")
    ]
    placed_visible_items = [fact for fact in visible_placements if fact["value"].get("region_kind") != "unassigned"]
    mappings = [
        fact for fact in facts
        if fact["fact_kind"] == "item_column_mapping" and fact["value"].get("persistence_applicable")
    ]
    resolved_mappings = [fact for fact in mappings if fact["value"].get("mapping_status") == "explicit"]
    call_facts = [fact for fact in facts if fact["fact_kind"] == "call_edge"]
    unresolved_calls = evidence.get("logic", {}).get("unresolved_calls", [])
    db_refs = evidence.get("ddl", {}).get("referenced_objects", [])
    matched_db = [record for record in db_refs if record["ddl_found"]]
    messages = evidence.get("logic", {}).get("messages", [])
    resolved_messages = [message for message in messages if message.get("text_available")]

    active_gaps = [gap for gap in gaps if gap["status"] != "resolved"]
    gap_ids_by_kind: dict[str, list[str]] = defaultdict(list)
    for gap in active_gaps:
        gap_ids_by_kind[gap["gap_kind"]].append(gap["gap_id"])

    def metric(dimension: str, denominator: int, numerator: int, unresolved: int, record_ids: list[str], status: str = "measured", exclusions: Optional[list[str]] = None,
               unresolved_record_ids: Optional[list[str]] = None) -> dict[str, Any]:
        return {
            "metric_id": f"COV-{module_id}-{dimension.upper().replace('_', '-')}", "dimension": dimension,
            "denominator": denominator, "numerator": numerator, "exclusions": exclusions or [],
            "unresolved_count": unresolved, "record_ids": record_ids,
            "unresolved_record_ids": sorted(set(unresolved_record_ids or [])), "status": "not_applicable" if denominator == 0 else status,
        }

    return [
        metric("source_classification", len(inventory), len(inventory), 0, [record["source_id"] for record in inventory]),
        metric("block_crud_disposition", len(blocks), len(blocks), 0, [record["fact_id"] for record in blocks]),
        metric("item_crud_disposition", len(items), len(items), 0, [record["fact_id"] for record in items]),
        metric("tab_page_disposition", len(tab_pages), len(tab_pages), 0, [record["fact_id"] for record in tab_pages]),
        metric("visible_item_region_placement", len(visible_placements), len(placed_visible_items), len(visible_placements) - len(placed_visible_items), [record["fact_id"] for record in visible_placements], unresolved_record_ids=[record["fact_id"] for record in visible_placements if record["value"].get("region_kind") == "unassigned"]),
        metric("database_item_physical_mapping", len(mappings), len(resolved_mappings), len(mappings) - len(resolved_mappings), [record["fact_id"] for record in mappings], unresolved_record_ids=gap_ids_by_kind["ambiguous_mapping"]),
        metric("entry_point_behavior_paths", len(paths), len(paths), 0, [record["path_id"] for record in paths]),
        metric("reachable_call_resolution", len(call_facts), max(0, len(call_facts) - len(unresolved_calls)), len(unresolved_calls), [record["fact_id"] for record in call_facts], unresolved_record_ids=gap_ids_by_kind["unresolved_call"] + gap_ids_by_kind["binary_only"]),
        metric("database_reference_ddl", len(db_refs), len(matched_db), len(db_refs) - len(matched_db), [record["name"] for record in db_refs], unresolved_record_ids=gap_ids_by_kind["missing_ddl"]),
        metric("validation_message_text", len(messages), len(resolved_messages), len(messages) - len(resolved_messages), [record["id"] for record in messages], unresolved_record_ids=gap_ids_by_kind["missing_message_text"]),
        metric("fact_to_specification", len(facts), 0, 0, [], status="not_assessed_pre_specification", exclusions=[record["fact_id"] for record in facts]),
        metric("stale_specification_sections", len(stale_sections), 0, len(stale_sections), stale_sections, status="stale" if stale_sections else "current"),
        metric("open_gaps", len(gaps), sum(1 for gap in gaps if gap["status"] == "resolved"), sum(1 for gap in gaps if gap["status"] != "resolved"), [gap["gap_id"] for gap in gaps], unresolved_record_ids=[gap["gap_id"] for gap in active_gaps]),
    ]


def build_contract_artifacts(evidence: dict[str, Any], previous: Optional[dict[str, Any]]) -> dict[str, Any]:
    module_id = evidence["modules"][0]["module_id"].upper()
    generated_at = evidence["run"]["generated_at"]
    run_id = re.sub(r"[^0-9TZ]", "", generated_at.replace("+00:00", "Z"))
    manifest_rows = [(record["path"], record["sha256"]) for record in evidence.get("sources", {}).get("files", [])]
    input_hash = hashlib.sha256(json.dumps(manifest_rows, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()
    facts = normalized_facts(evidence)
    preliminary_paths = build_behavior_paths(evidence)
    gaps = contract_gaps(evidence, previous, run_id, preliminary_paths)
    paths = build_behavior_paths(evidence, gaps)
    inventory = contract_source_inventory(evidence, previous, run_id, gaps)
    affected_sections = evidence.get("incremental", {}).get("impacted", {}).get("stale_section_hints", []) if previous else []
    delta = contract_source_delta(
        inventory, previous, facts, paths, gaps, affected_sections,
        evidence.get("incremental", {}).get("compiler_transition"),
    )
    coverage = coverage_records(evidence, inventory, facts, paths, gaps, affected_sections)
    artifacts = {
        "source_inventory": artifact_envelope(module_id, run_id, generated_at, input_hash, inventory),
        "source_delta": artifact_envelope(module_id, run_id, generated_at, input_hash, delta, affected_spec_sections=affected_sections),
        "normalized_evidence": artifact_envelope(module_id, run_id, generated_at, input_hash, facts),
        "behavior_ledger": artifact_envelope(module_id, run_id, generated_at, input_hash, paths),
        "coverage": artifact_envelope(module_id, run_id, generated_at, input_hash, coverage, stale_fact_ids=[], stale_path_ids=[], stale_gap_ids=[], affected_spec_sections=affected_sections),
        "gaps": artifact_envelope(module_id, run_id, generated_at, input_hash, gaps),
    }
    evidence["run"]["run_id"] = run_id
    evidence["run"]["input_manifest_sha256"] = input_hash
    evidence["incremental"]["affected_spec_sections"] = affected_sections
    evidence["artifacts"] = artifacts
    return evidence


def validate_evidence(evidence: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if evidence.get("schema_version") != SCHEMA_VERSION:
        errors.append("Unexpected evidence schema version.")
    modules = evidence.get("modules", [])
    if len(modules) != 1:
        errors.append(f"Expected exactly one selected module; found {len(modules)}.")
    files = evidence.get("sources", {}).get("files", [])
    if any(not re.fullmatch(r"[0-9a-f]{64}", record.get("sha256", "")) for record in files):
        errors.append("Every source file must have a SHA-256 digest.")
    ids: list[str] = []
    if modules:
        module = modules[0]
        ids.extend(record["id"] for record in module.get("evidence", []))
        ids.extend(unit["id"] for unit in all_code_units(module))
        ids.extend(item["id"] for unit in all_code_units(module) for item in unit.get("sql_references", []))
        for unit in all_code_units(module):
            if "&#10;" in unit.get("code", "") or "&#xA;" in unit.get("code", ""):
                errors.append(f"Residual encoded newline in decoded code unit {unit['id']}.")
        if module.get("module_id", "").lower() == "glasct01" and any(Path(path).name.lower() == "glasct01_fmb.xml" for path in module.get("source_paths", [])):
            observed = {
                "blocks": len(module.get("blocks", [])),
                "items": sum(len(block.get("items", [])) for block in module.get("blocks", [])),
                "triggers": sum(1 for unit in module.get("triggers", []) if unit.get("source_path", "").lower().endswith("glasct01_fmb.xml")),
                "program_units": sum(1 for unit in module.get("program_units", []) if unit.get("scope") == "form" and unit.get("source_path", "").lower().endswith("glasct01_fmb.xml")),
            }
            expected = {"blocks": 6, "items": 254, "triggers": 481, "program_units": 63}
            if observed != expected:
                errors.append(f"GLASCT01 namespace regression: expected {expected}, observed {observed}.")
            entry_counts = {operation: len(ledger.get("entry_point_ids", [])) for operation, ledger in evidence.get("behavior_ledger", {}).items()}
            expected_entries = {
                "query": 13,
                "create": 11,
                "update": 4,
                "delete": 3,
                "save": 1,
                "validation": 11,
                "custom_action": 32,
            }
            if entry_counts != expected_entries:
                errors.append(f"GLASCT01 entry-point regression: expected {expected_entries}, observed {entry_counts}.")
            spl = next((block for block in module.get("blocks", []) if block["id"] == "SPL"), None)
            ogn = next((item for item in (spl or {}).get("items", []) if item["name"] == "OGN_FUNLOC2"), None)
            if not spl or spl.get("effective_crud", {}).get("update") is not False or not ogn or ogn.get("effective_crud", {}).get("update") is not False:
                errors.append("GLASCT01 inherited CRUD regression: SPL and SPL.OGN_FUNLOC2 must be effectively non-updateable.")
            for control_id in ("CGNV$CG$WINDOW_1_1", "CG$CTRL"):
                control = next((block for block in module.get("blocks", []) if block["id"] == control_id), None)
                if not control or control.get("block_role") != "framework_control" or control.get("database_block") is not False or any(control.get("effective_crud", {}).values()):
                    errors.append(f"GLASCT01 control-block regression: {control_id} must be non-persistent with no effective CRUD.")
            screenshots = module.get("runtime_screenshots", [])
            expected_screenshots = {
                "ui/Maintain Standard Contract.jpeg",
                "ui/Maintain Standard Contract-1.jpeg",
            }
            if {record.get("path") for record in screenshots} != expected_screenshots:
                errors.append(f"GLASCT01 screenshot-association regression: observed {[record.get('path') for record in screenshots]}.")
            behavior_paths = evidence.get("artifacts", {}).get("behavior_ledger", {}).get("records", [])
            contract_gap_records = evidence.get("artifacts", {}).get("gaps", {}).get("records", [])
            binary_gaps = [gap for gap in contract_gap_records if gap.get("gap_kind") == "binary_only" and gap.get("status") != "resolved"]
            if len(binary_gaps) != 9 or len({gap["gap_id"] for gap in binary_gaps}) != 9:
                errors.append(f"GLASCT01 binary-library gap regression: expected 9 unique semantic gaps, observed {len(binary_gaps)} records/{len({gap['gap_id'] for gap in binary_gaps})} IDs.")
            aggregate_library_gaps = [
                gap for gap in evidence.get("gaps", [])
                if gap.get("kind") in {"readable_module_library", "readable_attached_library"}
                and gap.get("status") != "closed"
            ]
            aggregate_library_subjects = {str(gap.get("subject", "")).upper() for gap in aggregate_library_gaps}
            if len(aggregate_library_gaps) != 9 or len(aggregate_library_subjects) != 9:
                errors.append(
                    "GLASCT01 aggregate library-gap regression: expected 9 unique semantic gaps, "
                    f"observed {len(aggregate_library_gaps)} records/{len(aggregate_library_subjects)} subjects."
                )
            module_library_gap = next((gap for gap in binary_gaps if gap.get("subject") == "GLASCT01L"), None)
            module_binary_paths = {locator.get("relative_path") for locator in (module_library_gap or {}).get("available_fallback_evidence", [])}
            expected_binary_paths = {"form/glasct01l.pll", "form/_glasct01l.pll"}
            if not module_library_gap or not expected_binary_paths <= module_binary_paths:
                errors.append(f"GLASCT01 binary-library locator regression: expected both PLL copies, observed {sorted(path for path in module_binary_paths if path)}.")
            expected_source_subjects = {
                gap.get("subject") for gap in contract_gap_records
                if gap.get("gap_kind") == "source_missing" and gap.get("status") != "resolved"
            }
            if not {"GLA_MENU", "QMSOLB65.OLB"} <= expected_source_subjects:
                errors.append(f"GLASCT01 expected-source regression: observed {sorted(subject for subject in expected_source_subjects if subject)}.")
            implicit_paths = [path for path in behavior_paths if path.get("entry_point", {}).get("scope") == "forms_implicit_dml"]
            expected_implicit = {
                ("CTT", "insert", "GLA_CONTRACTS"), ("CTT", "update", "GLA_CONTRACTS"), ("CTT", "delete", "GLA_CONTRACTS"),
                ("SCP", "insert", "GLA_STD_CONTRACT_PRODUCTS"), ("SCP", "update", "GLA_STD_CONTRACT_PRODUCTS"), ("SCP", "delete", "GLA_STD_CONTRACT_PRODUCTS"),
                ("SCL", "insert", "GLA_STD_CONTRACT_LICENSORS"), ("SCL", "update", "GLA_STD_CONTRACT_LICENSORS"), ("SCL", "delete", "GLA_STD_CONTRACT_LICENSORS"),
                ("SPL", "insert", "GLA_STD_CONTRACT_PLANTS"), ("SPL", "delete", "GLA_STD_CONTRACT_PLANTS"),
            }
            observed_implicit = {
                (path["forms_blocks"][0], path["operation"], path["database_writes"][0])
                for path in implicit_paths if len(path.get("forms_blocks", [])) == 1 and len(path.get("database_writes", [])) == 1
            }
            if observed_implicit != expected_implicit:
                errors.append(f"GLASCT01 implicit Forms DML regression: expected {sorted(expected_implicit)}, observed {sorted(observed_implicit)}.")
            if any(not effect.get("column") for path in behavior_paths for effect in path.get("field_effects", [])):
                errors.append("GLASCT01 field-effect regression: blank ColumnName controls appeared as physical field effects.")
            ctt_delete = next((path for path in behavior_paths if path["operation"] == "delete" and path["entry_point"]["symbol"] == "CTT.KEY-DELREC"), None)
            scp_delete = next((path for path in behavior_paths if path["operation"] == "delete" and path["entry_point"]["symbol"] == "SCP.KEY-DELREC"), None)
            for label, path, expected_routines, forbidden_routines in (
                ("CTT", ctt_delete, {"CGRI$CHK_GLA_CONTRACTS", "CGRI$WRN_GLA_CONTRACTS"}, {"CGRI$CHK_GLA_STD_CONTRACT_PROD", "CGRI$WRN_GLA_STD_CONTRACT_PROD"}),
                ("SCP", scp_delete, {"CGRI$CHK_GLA_STD_CONTRACT_PROD", "CGRI$WRN_GLA_STD_CONTRACT_PROD"}, {"CGRI$CHK_GLA_CONTRACTS", "CGRI$WRN_GLA_CONTRACTS"}),
            ):
                if not path:
                    errors.append(f"GLASCT01 delete regression: missing {label}.KEY-DELREC path.")
                    continue
                callees = {edge["to"] for edge in path.get("call_chain", [])}
                codes = {str(message.get("code")) for message in path.get("messages", []) if message.get("code") is not None}
                if not expected_routines <= callees or callees & forbidden_routines:
                    errors.append(f"GLASCT01 delete call-chain regression for {label}: observed {sorted(callees)}.")
                if not {"5", "22"} <= codes:
                    errors.append(f"GLASCT01 delete message regression for {label}: expected OFG 5 and 22, observed {sorted(codes)}.")
                effects = {check.get("effect") for check in path.get("dependency_checks", [])}
                if not {"hard_blocker", "warning_confirmation"} <= effects:
                    errors.append(f"GLASCT01 delete dependency regression for {label}: observed effects {sorted(effects)}.")
            if ctt_delete:
                ctt_hard = [check for check in ctt_delete.get("dependency_checks", []) if check.get("effect") == "hard_blocker"]
                ctt_warning = [check for check in ctt_delete.get("dependency_checks", []) if check.get("effect") == "warning_confirmation"]
                if len(ctt_hard) != 39 or any(check.get("message_code") != "5" or check.get("stop_effect") != "raise_failure" for check in ctt_hard):
                    errors.append(f"GLASCT01 contract-delete blocker regression: observed {len(ctt_hard)} hard blockers.")
                if len(ctt_warning) != 15 or any(check.get("message_code") != "22" or check.get("confirmation") != "second_delete_action" or check.get("database_cascade") != "on_delete_cascade" for check in ctt_warning):
                    errors.append(f"GLASCT01 contract-delete warning/cascade regression: observed {len(ctt_warning)} warning dependencies.")
                if ctt_delete.get("database_writes") != ["GLA_CONTRACTS"] or not any(effect.get("effect") == "form_trigger_failure" and effect.get("result") == "abort_first_delete_attempt" for effect in ctt_delete.get("stop_effects", [])):
                    errors.append("GLASCT01 staged contract-delete regression: implicit write or first-attempt stop is missing.")
            if scp_delete:
                scp_by_object = {check.get("object"): check for check in scp_delete.get("dependency_checks", [])}
                expected_scp = {"GLA_STD_CONTRACT_PRODUCTS", "GLA_DISCOUNTING_SCHEMES", "GLA_STD_CONTRACT_REMUNERATIONS"}
                if set(scp_by_object) != expected_scp or any(scp_by_object[name].get("effect") != "hard_blocker" for name in expected_scp - {"GLA_STD_CONTRACT_REMUNERATIONS"}) or scp_by_object.get("GLA_STD_CONTRACT_REMUNERATIONS", {}).get("database_cascade") != "on_delete_cascade":
                    errors.append(f"GLASCT01 product-delete dependency regression: observed {sorted(scp_by_object)}.")
            pre_delete = next((path for path in behavior_paths if path["operation"] == "delete" and path["entry_point"]["symbol"] == "CTT.PRE-DELETE"), None)
            if not pre_delete or len([check for check in pre_delete.get("dependency_checks", []) if check.get("effect") == "hard_blocker"]) != 39:
                errors.append("GLASCT01 PRE-DELETE regression: 39 repeated hard dependency checks were not preserved.")
            expected_validation_counts = {
                "CTT.PRE-INSERT": 173, "CTT.PRE-UPDATE": 153,
                "SCP.PRE-INSERT": 11, "SCP.PRE-UPDATE": 6,
                "SCL.PRE-INSERT": 1, "SCL.PRE-UPDATE": 1,
            }
            for symbol, expected_count in expected_validation_counts.items():
                path = next((record for record in behavior_paths if record.get("entry_point", {}).get("symbol") == symbol), None)
                if not path or len(path.get("validations", [])) != expected_count or len(path.get("validation_stop_branches", [])) != expected_count:
                    errors.append(f"GLASCT01 validation-branch regression for {symbol}: expected {expected_count} message/stop branches.")
            key_commit = next((path for path in behavior_paths if path["operation"] == "save" and path["entry_point"]["symbol"] == "KEY-COMMIT"), None)
            key_commit_calls = {edge.get("to") for edge in (key_commit or {}).get("call_chain", [])}
            if not {"KEY_COMMIT_BEFORE", "KEY_COMMIT_AFTER"} <= key_commit_calls or any((key_commit or {}).get("transaction", {}).get(field) != "unknown" for field in ("boundary", "commit_owner", "rollback_behavior", "concurrency_behavior")):
                errors.append(f"GLASCT01 KEY-COMMIT regression: observed calls {sorted(call for call in key_commit_calls if call)}.")
            on_insert = next((path for path in behavior_paths if path["operation"] == "insert" and path["entry_point"]["symbol"] == "ON-INSERT"), None)
            on_insert_calls = {edge.get("to") for edge in (on_insert or {}).get("call_chain", [])}
            on_insert_builtins = {record.get("name") for record in (on_insert or {}).get("forms_builtins", [])}
            if not on_insert or on_insert.get("database_writes") != ["GLA_CONTRACTS"] or not {"ON_INSERT", "CG$CHK_PACKAGE_FAILURE"} <= on_insert_calls or "INSERT_RECORD" not in on_insert_builtins or not on_insert.get("branches"):
                errors.append("GLASCT01 ON-INSERT branch/call/write regression.")
            qms_gap = next((gap for gap in contract_gap_records if gap.get("gap_kind") == "missing_ddl" and gap.get("subject") == "QMS_MODULES"), None)
            if not qms_gap or qms_gap.get("affected_operations") or qms_gap.get("affected_path_ids"):
                errors.append("GLASCT01 QMS_MODULES reachability regression: shared-unreachable DDL must not enter CRUD paths.")
            ddl_file_count = sum(1 for record in evidence.get("sources", {}).get("files", []) if record.get("area") == "ddl")
            if ddl_file_count >= 470:
                active_aggregate_gaps = [gap for gap in evidence.get("gaps", []) if gap.get("status") != "closed"]
                active_contract_gaps = [gap for gap in contract_gap_records if gap.get("status") != "resolved"]
                if len(active_aggregate_gaps) != 62 or len(active_contract_gaps) != 62:
                    errors.append(
                        "GLASCT01 full-bundle gap regression: expected 62 active aggregate and contract gaps, including explicit audit-population ownership gaps, "
                        f"observed {len(active_aggregate_gaps)} aggregate/{len(active_contract_gaps)} contract."
                    )
                ambiguous_subjects = {
                    gap.get("subject") for gap in contract_gap_records
                    if gap.get("gap_kind") == "ambiguous_mapping" and gap.get("status") != "resolved"
                }
                if len(ambiguous_subjects) != 28 or any(subject and subject.split(".", 1)[0] in {"CG$CTRL", "CGNV$CG$WINDOW_1_1"} for subject in ambiguous_subjects):
                    errors.append(f"GLASCT01 physical-mapping gap regression: observed {len(ambiguous_subjects)} persistence gaps, including controls={sorted(subject for subject in ambiguous_subjects if subject and subject.split('.', 1)[0] in {'CG$CTRL', 'CGNV$CG$WINDOW_1_1'})}.")
                expected_missing = {"FND_CURRENCIES_VL", "GLA_CTT_SEQ1", "QMS_MODULES"}
                observed_missing = set(evidence.get("ddl", {}).get("missing_objects", []))
                if observed_missing != expected_missing:
                    errors.append(f"GLASCT01 reachable DDL regression: expected {sorted(expected_missing)}, observed {sorted(observed_missing)}.")
                contracts = next((obj for obj in evidence.get("ddl", {}).get("catalog", []) if obj.get("type") == "table" and obj.get("name") == "GLA_CONTRACTS"), None)
                required = {"CTT_ID", "CTT_TYPE", "CTT_TITLE", "CREATED_BY", "CREATION_DATE", "LAST_UPDATED_BY", "LAST_UPDATE_DATE"}
                not_null = {column["name"] for column in (contracts or {}).get("columns", []) if column.get("nullable") is False}
                if not required <= not_null:
                    errors.append(f"GLASCT01 ALTER MODIFY regression: missing NOT NULL columns {sorted(required - not_null)}.")
                comment_files = {obj.get("source_path") for obj in evidence.get("ddl", {}).get("catalog", []) if obj.get("comments")}
                ctt_id = next((column for column in (contracts or {}).get("columns", []) if column.get("name") == "CTT_ID"), None)
                if len(comment_files) != 136 or (ctt_id or {}).get("comment") != "The artificial identifier for a contract":
                    errors.append(f"GLASCT01 DDL-comment regression: observed {len(comment_files)} comment files and CTT_ID={(ctt_id or {}).get('comment')!r}.")
    ids.extend(record["id"] for record in evidence.get("ddl", {}).get("catalog", []))
    gap_ids = [record["id"] for record in evidence.get("gaps", [])]
    if len(gap_ids) != len(set(gap_ids)):
        errors.append("Gap IDs are not unique.")
    # Evidence IDs may legitimately repeat in merged output references; unit and DDL IDs may not.
    unit_ddl_ids = [unit["id"] for module in modules for unit in all_code_units(module)] + [record["id"] for record in evidence.get("ddl", {}).get("catalog", [])]
    if len(unit_ddl_ids) != len(set(unit_ddl_ids)):
        errors.append("Code-unit or DDL IDs are not unique.")
    expected_slices = set(OPERATION_EVENTS)
    if set(evidence.get("behavior_ledger", {})) != expected_slices:
        errors.append("Behavior ledger does not contain every required operation slice.")
    artifacts = evidence.get("artifacts", {})
    expected_artifacts = {"source_inventory", "source_delta", "normalized_evidence", "behavior_ledger", "coverage", "gaps"}
    if artifacts and set(artifacts) != expected_artifacts:
        errors.append("Normalized contract artifact set is incomplete.")
    contract_gap_ids = [gap["gap_id"] for gap in artifacts.get("gaps", {}).get("records", [])]
    if len(contract_gap_ids) != len(set(contract_gap_ids)):
        errors.append("Contract gap IDs are not unique by semantic gap identity.")
    contract_gap_records = artifacts.get("gaps", {}).get("records", [])
    fact_ids = [record.get("fact_id") for record in artifacts.get("normalized_evidence", {}).get("records", [])]
    if artifacts and (not all(fact_ids) or len(fact_ids) != len(set(fact_ids))):
        errors.append(
            "Normalized fact IDs are not unique: "
            f"{len(fact_ids)} records/{len(set(identifier for identifier in fact_ids if identifier))} unique IDs."
        )
    if artifacts and len(evidence.get("gaps", [])) != len(contract_gap_records):
        errors.append(
            "Aggregate and contract gap registers disagree on semantic gap count: "
            f"{len(evidence.get('gaps', []))} aggregate/{len(contract_gap_records)} contract."
        )
    aggregate_active = sum(1 for gap in evidence.get("gaps", []) if gap.get("status") != "closed")
    contract_active = sum(1 for gap in contract_gap_records if gap.get("status") != "resolved")
    if artifacts and aggregate_active != contract_active:
        errors.append(
            "Aggregate and contract gap registers disagree on active gap count: "
            f"{aggregate_active} aggregate/{contract_active} contract."
        )
    return errors


def semantic_state_hash(evidence: dict[str, Any]) -> str:
    volatile = {
        "generated_at", "run_id", "first_seen", "last_seen", "first_seen_run_id", "last_seen_run_id",
        "last_changed_run_id", "closed_at", "reopened_at", "history", "previous_evidence_sha256",
        "evidence_sha256", "state_sha256", "run_sha256", "previous_run_id", "previous_run_sha256",
        "previous_state_sha256", "previous_extractor_version",
    }

    def clean(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: clean(item) for key, item in sorted(value.items()) if key not in volatile}
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    payload = {
        "schema_version": evidence.get("schema_version"),
        "extractor": evidence.get("extractor"),
        "sources": [{key: record.get(key) for key in ("path", "area", "extension", "size", "sha256", "state")} for record in evidence.get("sources", {}).get("files", [])],
        "modules": evidence.get("modules", []),
        "logic": evidence.get("logic", {}),
        "behavior_ledger": evidence.get("behavior_ledger", {}),
        "ddl": evidence.get("ddl", {}),
        "gaps": evidence.get("artifacts", {}).get("gaps", {}).get("records", []),
        "normalized_facts": evidence.get("artifacts", {}).get("normalized_evidence", {}).get("records", []),
        "behavior_paths": evidence.get("artifacts", {}).get("behavior_ledger", {}).get("records", []),
    }
    return hashlib.sha256(json.dumps(clean(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


def markdown_cell(value: Any) -> str:
    """Return a compact, safe Markdown table cell."""
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(item) for item in value if item not in (None, ""))
    return " ".join(str(value).replace("|", "\\|").replace("\n", " ").split()) or "—"


def crud_cell(crud: dict[str, Any]) -> str:
    labels = (("query", "Q"), ("create", "C"), ("update", "U"), ("delete", "D"))
    return "/".join(label for key, label in labels if crud.get(key)) or "—"


def render_markdown_specification(evidence: dict[str, Any]) -> str:
    """Compatibility entry point for callers that imported the old renderer."""
    return render_complete_markdown_specification(evidence)


def _retired_narrow_markdown_renderer(evidence: dict[str, Any]) -> str:
    """Render the entire durable extraction surface into one reviewable Markdown file.

    JSON remains an in-memory compiler representation only in this mode.  The
    Markdown deliberately includes field-level visual placement, coverage, and
    gaps so a reviewer does not need companion machine artifacts.
    """
    module = evidence["modules"][0]
    run = evidence["run"]
    module_id = module["module_id"].upper()
    tab_labels = {page.get("id"): page.get("label") or page.get("id") for page in module.get("tab_pages", [])}
    database_objects = {}
    for fact in evidence.get("artifacts", {}).get("normalized_evidence", {}).get("records", []):
        if fact.get("fact_kind") != "database_object" or not isinstance(fact.get("value"), dict):
            continue
        value = fact["value"]
        for name in (value.get("name"), value.get("qualified_name")):
            if name:
                key = str(name).upper().split(".")[-1]
                existing = database_objects.get(key)
                if not existing or (not existing.get("columns") and value.get("columns")):
                    database_objects[key] = value
    lines = [
        "---",
        f"module_id: {module_id}",
        f"extraction_run_id: {run.get('run_id', 'TBD')}",
        f"evidence_fingerprint: {run.get('evidence_sha256', 'TBD')}",
        "artifact_kind: legacy_extraction_specification",
        "review_status: draft",
        "---",
        "",
        f"# {module.get('title') or module_id} — Legacy Extraction Specification",
        "",
        "This is the complete durable output of the extraction. It describes supplied legacy evidence, not approved target requirements.",
        "",
        "## 1. Extraction Scope",
        "",
        f"- Module: `{module_id}`",
        f"- Source files considered: {len(evidence.get('sources', {}).get('files', []))}",
        f"- Compiler: `{evidence.get('extractor', {}).get('version', 'TBD')}`",
        f"- Self-check: {evidence.get('self_check', {}).get('status', 'not run')}",
        "",
        "## 2. Screen and Field Inventory",
        "",
        "Each visible control is listed in its actual visual region. `Q/C/U/D` denotes explicit Forms design-time query/create/update/delete properties; effective runtime status is stated separately and remains unknown where inherited, library, or menu evidence is unavailable.",
        "",
    ]

    def item_row(block: dict[str, Any], item: dict[str, Any]) -> str:
        mapping = f"{block['id']}.{item['name']}"
        physical = item.get("database_column") or "Not explicitly mapped"
        table_name = str(block.get("dml_data_name") or "").upper().split(".")[-1]
        ddl = database_objects.get(table_name, {})
        column = next((record for record in ddl.get("columns", []) if str(record.get("name", "")).upper() == str(item.get("database_column", "")).upper()), None)
        if column:
            physical = f"{table_name}.{item['database_column']} ({column.get('datatype') or column.get('data_type') or 'DDL type not parsed'})"
        detail = item.get("hint") or item.get("prompt") or "No business description in supplied source"
        control = f"{item.get('item_type') or 'Unknown'} / {item.get('data_type') or 'Unknown'}"
        if item.get("maximum_length"):
            control += f" ({item['maximum_length']})"
        lookup_default = "; ".join(filter(None, [
            f"LOV: {item['lov']}" if item.get("lov") else "",
            f"Default: {item['initial_value']}" if item.get("initial_value") else "",
        ]))
        required = "Required" if item.get("required") else "Optional"
        effective = item.get("effective_crud_status")
        effective_display = effective if effective in {"true", "false", "conditional", "unknown"} else "unknown (runtime/inherited source gap)"
        return "| " + " | ".join(markdown_cell(value) for value in (
            item.get("prompt") or item["name"], detail, mapping, physical, control,
            required, f"Design: {crud_cell(item.get('design_crud', {}))}; Effective: {effective_display}", lookup_default,
            f"Evidence: {item.get('evidence_id', 'TBD')}",
        )) + " |"

    header = "| Field | Description | Legacy mapping | Physical mapping | Control / data | Required | CRUD | Lookup / default | Evidence / logic |"
    divider = "|---|---|---|---|---|---|---|---|---|"
    visible_by_tab: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    visible_by_canvas: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    grids: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    helpers: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for block in module.get("blocks", []):
        for item in block.get("items", []):
            if item.get("tab_page") and item.get("visible"):
                visible_by_tab.setdefault(item["tab_page"], []).append((block, item))
            elif item.get("canvas") and item.get("visible"):
                bucket = grids if block.get("records_displayed", 1) > 1 else visible_by_canvas
                bucket.setdefault(block["id"] if bucket is grids else item["canvas"], []).append((block, item))
            else:
                helpers.append((block, item))
    for tab_id, pairs in visible_by_tab.items():
        lines.extend([f"### Tab: {tab_labels.get(tab_id, tab_id)}", "", header, divider])
        lines.extend(item_row(block, item) for block, item in pairs)
        lines.append("")
    for canvas, pairs in visible_by_canvas.items():
        lines.extend([f"### Section: {canvas}", "", header, divider])
        lines.extend(item_row(block, item) for block, item in pairs)
        lines.append("")
    for block_id, pairs in grids.items():
        grid_block = pairs[0][0]
        lines.extend([
            f"### Grid: {block_id}", "",
            f"Canvas: `{pairs[0][1].get('canvas') or 'unknown'}`; rows displayed: {markdown_cell(grid_block.get('records_displayed'))}; row CRUD — Design: {crud_cell(grid_block.get('design_crud', {}))}; Effective: unknown (runtime/inherited source gap).",
            "", header, divider,
        ])
        lines.extend(item_row(block, item) for block, item in pairs)
        lines.append("")
    if helpers:
        lines.extend(["### Supporting Technical Fields", "", header, divider])
        lines.extend(item_row(block, item) for block, item in helpers)
        lines.append("")

    lines.extend(["## 3. Direct Persistence and DDL Evidence", "", "Only direct Forms DML blocks are listed here. DDL is authoritative for physical types and constraints; Forms control types remain UI evidence.", "", "| Forms block | DML object | DDL source | Keys and constraints | Dependencies / limitations |", "|---|---|---|---|---|"])
    for block in module.get("blocks", []):
        if block.get("block_role") != "database_persistence" or not block.get("dml_data_name"):
            continue
        table = str(block["dml_data_name"]).upper().split(".")[-1]
        ddl = database_objects.get(table)
        if not ddl:
            lines.append(f"| {markdown_cell(block['id'])} | {markdown_cell(table)} | Not supplied | Not established | Open DDL gap |")
            continue
        constraints = ddl.get("constraints", [])
        constraint_text = "; ".join(str(record.get("name") or record.get("type") or "constraint") for record in constraints[:12]) or "No constraints parsed"
        if len(constraints) > 12:
            constraint_text += f"; +{len(constraints) - 12} more"
        foreign_keys = [constraint for constraint in constraints if constraint.get("type") == "foreign_key"]
        dependencies = "; ".join(
            f"{constraint.get('name')} -> {constraint.get('references_object')}" + (f" (on delete {constraint.get('on_delete')})" if constraint.get('on_delete') else "")
            for constraint in foreign_keys[:12]
        ) or "No foreign-key dependency parsed"
        if len(foreign_keys) > 12:
            dependencies += f"; +{len(foreign_keys) - 12} more"
        lines.append("| " + " | ".join(markdown_cell(value) for value in (block["id"], table, ddl.get("source_path"), constraint_text, dependencies)) + " |")
    inbound_contract_fks = []
    for object_name, ddl in database_objects.items():
        for constraint in ddl.get("constraints", []):
            if constraint.get("type") == "foreign_key" and str(constraint.get("references_object", "")).upper() == "GLA_CONTRACTS":
                inbound_contract_fks.append((object_name, constraint))
    if inbound_contract_fks:
        lines.extend(["", "### Header Delete: Database Consequences", "", "The Forms hard-blocker/warning routines are not a complete database-dependency inventory. The following supplied DDL foreign keys reference `GLA_CONTRACTS`; reconcile their effects with the Forms routines before treating header deletion as complete.", "", "| Referencing object | Constraint | Columns | On delete |", "|---|---|---|---|"])
        for object_name, constraint in sorted(inbound_contract_fks, key=lambda row: (row[0], str(row[1].get("name")))):
            definition = str(constraint.get("definition") or "").upper()
            on_delete = constraint.get("on_delete") or ("set null" if "ON DELETE SET NULL" in definition else "not stated / non-cascade")
            lines.append("| " + " | ".join(markdown_cell(value) for value in (object_name, constraint.get("name"), ", ".join(constraint.get("columns", [])), on_delete)) + " |")
    lines.append("")

    def path_summary(path: dict[str, Any]) -> str:
        parts = []
        writes = path.get("database_writes", [])
        reads = path.get("database_reads", [])
        if reads:
            parts.append("reads " + ", ".join(reads))
        if writes:
            parts.append("writes " + ", ".join(writes))
        messages = path.get("messages", [])
        codes = sorted({str(message.get("code") or message.get("text")) for message in messages if message.get("code") is not None or message.get("text")})
        if codes:
            parts.append("message codes " + ", ".join(codes))
        branches = path.get("branches", [])
        if branches:
            parts.append(f"{len(branches)} decoded branch(es)")
        validation_stops = path.get("validation_stop_branches", [])
        if validation_stops:
            parts.append(f"{len(validation_stops)} validation failure branch(es)")
        for outcome in path.get("outcomes", []):
            result = outcome.get("result")
            condition = outcome.get("condition")
            if result:
                parts.append(f"outcome {result}" + (f" when {condition}" if condition else ""))
        checks = path.get("dependency_checks", [])
        if checks:
            effects = sorted({str(check.get("effect")) for check in checks if check.get("effect")})
            parts.append("dependency checks: " + ", ".join(effects))
        unresolved = path.get("unresolved_calls", [])
        if unresolved:
            parts.append("unresolved calls: " + ", ".join(sorted(set(unresolved))))
        if not parts:
            parts.append("reachable entry point recorded; no additional outcome is established by supplied readable source")
        return "; ".join(parts)

    lines.extend(["## 4. Operation and Logic Evidence", ""])
    paths = evidence.get("artifacts", {}).get("behavior_ledger", {}).get("records", [])
    if paths:
        lines.extend(["| Path ID | Operation | Entry point | Outcome / evidence |", "|---|---|---|---|"])
        for path in paths:
            lines.append("| " + " | ".join(markdown_cell(value) for value in (path.get("path_id"), path.get("operation"), path.get("entry_point"), path_summary(path))) + " |")
    else:
        lines.append("No executable behavior paths were established from the supplied readable source.")
    lines.extend(["", "### Validation Predicates and Message Evidence", "", "Rows preserve explicit source conditions and message codes. A predicate-to-message pairing is not inferred where source control flow does not establish it.", "", "| Path | Predicate / branch | Source locator |", "|---|---|---|"])
    branch_rows = []
    for path in paths:
        for branch in path.get("branches", []):
            branch_rows.append((path.get("path_id"), branch.get("condition") or branch.get("kind"), branch.get("locator") or branch.get("source_path")))
    if branch_rows:
        lines.extend("| " + " | ".join(markdown_cell(value) for value in row) + " |" for row in branch_rows)
    else:
        lines.append("| — | No source branch predicates were decoded | — |")
    lines.extend(["", "| Path | Message code / text | Severity | Source locator |", "|---|---|---|---|"])
    message_rows = []
    for path in paths:
        for message in path.get("messages", []):
            message_rows.append((path.get("path_id"), message.get("code") or message.get("text") or "unresolved", message.get("severity") or "not established", message.get("locator") or message.get("source_path")))
    rendered_message_keys = {(str(row[1]), str(row[3])) for row in message_rows}
    for unit in module.get("program_units", []):
        for message in unit.get("messages", []):
            code = message.get("code") or message.get("text") or "unresolved"
            locator = message.get("locator") or unit.get("locator") or unit.get("source_path")
            key = (str(code), str(locator))
            if key not in rendered_message_keys:
                message_rows.append((f"Program unit: {unit.get('name')}", code, message.get("severity") or "not established", locator))
                rendered_message_keys.add(key)
    if message_rows:
        lines.extend("| " + " | ".join(markdown_cell(value) for value in row) + " |" for row in message_rows)
    else:
        lines.append("| — | No message evidence was decoded | — | — |")
    lines.extend(["", "## 5. Extraction Coverage", "", "| Metric | Numerator | Denominator | Unresolved | Status |", "|---|---:|---:|---:|---|"])
    for record in evidence.get("artifacts", {}).get("coverage", {}).get("records", []):
        lines.append("| " + " | ".join(markdown_cell(record.get(key)) for key in ("metric_id", "numerator", "denominator", "unresolved_count", "status")) + " |")
    lines.extend(["", "## 6. Missing-Source and Extraction Gaps", "", "| Gap ID | Subject | Status | Impact / recommended action |", "|---|---|---|---|"])
    gaps = evidence.get("artifacts", {}).get("gaps", {}).get("records", [])
    if gaps:
        for gap in gaps:
            impact = gap.get("affected_behavior") or gap.get("recommended_action") or gap.get("expected_artifact_or_behavior")
            lines.append("| " + " | ".join(markdown_cell(value) for value in (gap.get("gap_id"), gap.get("subject"), gap.get("status"), impact)) + " |")
    else:
        lines.append("| — | No gaps recorded | — | — |")
    lines.extend(["", "## 7. Source Summary", "", "| Source role | Files |", "|---|---:|"])
    roles: dict[str, int] = {}
    for source in evidence.get("sources", {}).get("files", []):
        roles[source.get("role") or source.get("area") or "unclassified"] = roles.get(source.get("role") or source.get("area") or "unclassified", 0) + 1
    lines.extend(f"| {markdown_cell(role)} | {count} |" for role, count in sorted(roles.items()))
    lines.extend(["", "## 8. Review Notes", "", "- Validate open gaps before treating any affected behavior as production-parity evidence.", "- Human target decisions must be recorded separately in canonical requirements and architecture artifacts.", ""])
    return "\n".join(lines)


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="*", type=Path, help="One or more source roots, directories, or exact files")
    parser.add_argument("--input-manifest", type=Path, help="JSON list of exact paths, or an object with root/input_root and paths")
    parser.add_argument("--module", required=True, help="Logical Oracle Forms module id")
    output_group = parser.add_mutually_exclusive_group(required=True)
    output_group.add_argument(
        "--markdown-output",
        type=Path,
        help="Write a master specification at this path plus linked operation, decoded-source, and database child Markdown files",
    )
    output_group.add_argument("--output", type=Path, help="Write the aggregate JSON evidence model to this file")
    output_group.add_argument("--output-dir", type=Path, help="Write the normalized run artifacts and aggregate evidence-model.json to this directory")
    parser.add_argument(
        "--comparison-spec",
        type=Path,
        help="Read-only prior specification used as a semantic coverage oracle on a fresh run",
    )
    parser.add_argument(
        "--no-auto-comparison",
        action="store_true",
        help="Do not auto-use an adjacent previous_<output-filename> specification as a fresh-run comparison oracle",
    )
    parser.add_argument(
        "--previous-spec",
        type=Path,
        help="Marker-enabled current draft whose evidence regions are refreshed while authored content is preserved",
    )
    parser.add_argument(
        "--extraction-mode",
        choices=("fresh", "refresh"),
        help="Markdown generation mode; defaults to refresh with --previous-spec and fresh otherwise",
    )
    parser.add_argument(
        "--validation-evidence-output",
        type=Path,
        help="Optional transient aggregate evidence file for the specification guard; valid only with --markdown-output",
    )
    parser.add_argument("--previous-evidence", type=Path, help="Prior compiler output for incremental reconciliation")
    parser.add_argument("--incremental", action="store_true", help="Use --previous-evidence, or the existing --output file, when available")
    parser.add_argument("--full-refresh", action="store_true", help="Treat the input as a complete snapshot; absent prior files are removals")
    parser.add_argument("--self-check", action="store_true", help="Run structural and regression checks before writing output")
    return parser.parse_args(list(argv))


def resolve_comparison_spec(
    markdown_output: Optional[Path],
    comparison_spec: Optional[Path],
    previous_spec: Optional[Path],
    extraction_mode: str,
    no_auto_comparison: bool,
) -> Optional[Path]:
    """Resolve the read-only semantic oracle without weakening refresh semantics."""
    paths = resolve_comparison_specs(
        markdown_output,
        comparison_spec,
        previous_spec,
        extraction_mode,
        no_auto_comparison,
    )
    return paths[0] if paths else None


def resolve_comparison_specs(
    markdown_output: Optional[Path],
    comparison_spec: Optional[Path],
    previous_spec: Optional[Path],
    extraction_mode: str,
    no_auto_comparison: bool,
) -> list[Path]:
    """Return every applicable prior evidence oracle in deterministic order."""
    explicit = comparison_spec or previous_spec
    if explicit:
        return [explicit]
    if (
        not markdown_output
        or extraction_mode != "fresh"
        or no_auto_comparison
    ):
        return []
    candidates: list[Path] = []
    search_directories = [markdown_output.parent]
    # Feature packages are nested below evidence/features/<feature-slug>. Keep
    # discovering historical flat specifications in evidence/features so a
    # packaging improvement cannot weaken comparison continuity.
    if markdown_output.parent.parent.name.casefold() == "features":
        search_directories.append(markdown_output.parent.parent)
    for directory in search_directories:
        adjacent_previous = directory / f"previous_{markdown_output.name}"
        if adjacent_previous.is_file():
            candidates.append(adjacent_previous)
        same_name_historical = directory / markdown_output.name
        if (
            same_name_historical.is_file()
            and same_name_historical.resolve() != markdown_output.resolve()
        ):
            candidates.append(same_name_historical)
        candidates.extend(
            sorted(
                (
                    path
                    for path in directory.glob(f"{markdown_output.stem}_v*.md")
                    if path.resolve() != markdown_output.resolve()
                ),
                key=lambda path: path.name.casefold(),
            )
        )
    unique: dict[str, Path] = {}
    for path in candidates:
        unique.setdefault(str(path.resolve()).casefold(), path)
    return list(unique.values())


def main(argv: Iterable[str] = ()) -> int:
    args = parse_args(argv or sys.argv[1:])
    if (args.comparison_spec or args.previous_spec) and not args.markdown_output:
        print("--comparison-spec and --previous-spec apply only with --markdown-output.", file=sys.stderr)
        return 2
    if args.validation_evidence_output and not args.markdown_output:
        print("--validation-evidence-output applies only with --markdown-output.", file=sys.stderr)
        return 2
    if args.no_auto_comparison and not args.markdown_output:
        print("--no-auto-comparison applies only with --markdown-output.", file=sys.stderr)
        return 2
    if args.previous_spec and not args.previous_spec.is_file():
        print(f"Previous specification does not exist: {args.previous_spec}", file=sys.stderr)
        return 2
    if args.comparison_spec and not args.comparison_spec.is_file():
        print(f"Comparison specification does not exist: {args.comparison_spec}", file=sys.stderr)
        return 2
    extraction_mode = args.extraction_mode or ("refresh" if args.previous_spec else "fresh")
    if extraction_mode == "refresh" and not args.previous_spec:
        print("Refresh mode requires --previous-spec so authored content can be preserved safely.", file=sys.stderr)
        return 2
    comparison_paths = resolve_comparison_specs(
        args.markdown_output,
        args.comparison_spec,
        args.previous_spec,
        extraction_mode,
        args.no_auto_comparison,
    )
    manifest_inputs: list[Path] = []
    if args.input_manifest:
        try:
            manifest_data = json.loads(args.input_manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Cannot read input manifest {args.input_manifest}: {exc}", file=sys.stderr)
            return 2
        if isinstance(manifest_data, list):
            manifest_paths = manifest_data
            manifest_base = args.input_manifest.resolve().parent
        elif isinstance(manifest_data, dict) and isinstance(manifest_data.get("paths"), list):
            manifest_paths = manifest_data["paths"]
            root_hint = manifest_data.get("root") or manifest_data.get("input_root")
            manifest_base = Path(root_hint).resolve() if root_hint else args.input_manifest.resolve().parent
        else:
            print("Input manifest must be a JSON path list or an object containing a paths list.", file=sys.stderr)
            return 2
        for value in manifest_paths:
            candidate = Path(str(value))
            manifest_inputs.append(candidate.resolve() if candidate.is_absolute() else (manifest_base / candidate).resolve())
    supplied_inputs = [path.resolve() for path in args.inputs] + manifest_inputs
    if not supplied_inputs:
        print("At least one positional input or --input-manifest path is required.", file=sys.stderr)
        return 2
    missing_inputs = [path for path in supplied_inputs if not path.exists()]
    if missing_inputs:
        print("Input path(s) do not exist: " + ", ".join(str(path) for path in missing_inputs), file=sys.stderr)
        return 2
    if len(supplied_inputs) == 1 and supplied_inputs[0].is_dir():
        root = supplied_inputs[0]
        explicit_inputs: Optional[list[Path]] = None
    else:
        roots = [str(path if path.is_dir() else path.parent) for path in supplied_inputs]
        root = Path(os.path.commonpath(roots)).resolve()
        explicit_inputs = supplied_inputs

    previous_path = args.previous_evidence
    if args.incremental and previous_path is None:
        if args.output and args.output.is_file():
            previous_path = args.output
        elif args.output_dir and (args.output_dir / "evidence-model.json").is_file():
            previous_path = args.output_dir / "evidence-model.json"
        elif args.markdown_output:
            print("Markdown-only mode does not persist a prior JSON model; rerun the complete selected source bundle.", file=sys.stderr)
            return 2
    try:
        previous = load_previous(previous_path)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.previous_evidence and previous is None:
        print(f"Previous evidence file does not exist: {args.previous_evidence}", file=sys.stderr)
        return 2

    supplemental = bool(previous and not args.full_refresh)
    evidence = build_evidence(root, args.module, previous, supplemental=supplemental, supplied_inputs=explicit_inputs)
    evidence["run"]["supplied_inputs"] = [relative(path, root) for path in supplied_inputs]
    evidence = build_contract_artifacts(evidence, previous)
    state_sha256 = semantic_state_hash(evidence)
    evidence["run"]["state_sha256"] = state_sha256
    evidence["run"]["evidence_sha256"] = state_sha256  # Backward-compatible alias for state identity.
    evidence["run"]["run_sha256"] = hashlib.sha256(
        json.dumps(evidence, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    errors = validate_evidence(evidence)
    no_source_changes = previous and not any(evidence["incremental"]["change_set"][key] for key in ("added", "changed", "removed"))
    previous_state = (previous or {}).get("run", {}).get("state_sha256") or (previous or {}).get("run", {}).get("evidence_sha256")
    compiler_changed = bool(evidence.get("incremental", {}).get("compiler_transition", {}).get("changed"))
    if no_source_changes and not compiler_changed and previous_state and previous_state != state_sha256:
        errors.append(f"Idempotence regression: unchanged source state changed from {previous_state} to {state_sha256}.")
    evidence["self_check"] = {"status": "passed" if not errors else "failed", "errors": errors}
    if args.self_check and errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    rendered = json.dumps(evidence, indent=2, ensure_ascii=True) + "\n"
    if args.markdown_output:
        try:
            comparison_text = (
                "\n\n".join(
                    f"<!-- comparison-source: {path.name} -->\n"
                    + path.read_text(encoding="utf-8-sig")
                    for path in comparison_paths
                )
                if comparison_paths
                else None
            )
            specification_package = render_evidence_markdown_package(
                evidence,
                extraction_mode=extraction_mode,
                comparison_spec_text=comparison_text,
                source_root=root,
                output_path=args.markdown_output,
            )
            specification = specification_package[args.markdown_output.name]
            child_documents = {
                "operation_details": specification_package[f"{args.module.lower()}-operation-details.md"],
                "decoded_source": specification_package[f"{args.module.lower()}-decoded-source.md"],
                "database_reference": specification_package[f"{args.module.lower()}-database-reference.md"],
            }
            if args.previous_spec:
                previous_specification = args.previous_spec.read_text(encoding="utf-8-sig")
                specification = merge_evidence_regions(previous_specification, specification)
                specification_package[args.markdown_output.name] = specification
            markdown_errors = validate_markdown_contract(
                evidence,
                specification,
                comparison_spec_text=comparison_text,
                package_documents=child_documents,
            )
        except (OSError, UnicodeError, ValueError) as exc:
            print(f"Markdown generation failed: {exc}", file=sys.stderr)
            return 1
        if markdown_errors:
            for error in markdown_errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 1
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        for filename, document in specification_package.items():
            (args.markdown_output.parent / filename).write_text(document, encoding="utf-8")
        if args.validation_evidence_output:
            args.validation_evidence_output.parent.mkdir(parents=True, exist_ok=True)
            args.validation_evidence_output.write_text(rendered, encoding="utf-8")
        output_label = args.markdown_output
        if comparison_paths:
            print("Comparison oracle(s): " + ", ".join(str(path) for path in comparison_paths))
    elif args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        output_label = args.output
    else:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        top_specialists = args.output_dir / "specialist-findings"
        top_specialists.mkdir(exist_ok=True)
        artifact_names = {
            "source_inventory": "source-inventory.json",
            "source_delta": "source-delta.json",
            "normalized_evidence": "normalized-evidence.json",
            "behavior_ledger": "behavior-ledger.json",
            "coverage": "coverage.json",
            "gaps": "gaps.json",
        }
        for key, filename in artifact_names.items():
            (args.output_dir / filename).write_text(json.dumps(evidence["artifacts"][key], indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        (args.output_dir / "evidence-model.json").write_text(rendered, encoding="utf-8")
        pending_status = {
            "schema_version": "1.0", "module_id": evidence["modules"][0]["module_id"].upper(),
            "run_id": evidence["run"]["run_id"], "status": "pending",
            "findings": [], "note": "No specialist or independent-audit findings have been supplied for this run.",
        }
        (top_specialists / "status.json").write_text(json.dumps(pending_status, indent=2) + "\n", encoding="utf-8")
        run_dir = args.output_dir / "runs" / evidence["run"]["run_id"]
        run_dir.mkdir(parents=True, exist_ok=True)
        run_specialists = run_dir / "specialist-findings"
        run_specialists.mkdir(exist_ok=True)
        for key, filename in artifact_names.items():
            (run_dir / filename).write_text(json.dumps(evidence["artifacts"][key], indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        (run_dir / "evidence-model.json").write_text(rendered, encoding="utf-8")
        change_set = artifact_envelope(
            evidence["modules"][0]["module_id"], evidence["run"]["run_id"], evidence["run"]["generated_at"],
            evidence["run"]["input_manifest_sha256"],
            [{
                "change_set": evidence["incremental"]["change_set"],
                "impacted": evidence["incremental"]["impacted"],
                "affected_spec_sections": evidence["incremental"].get("affected_spec_sections", []),
                "state_sha256": evidence["run"]["state_sha256"],
                "run_sha256": evidence["run"]["run_sha256"],
            }],
        )
        (run_dir / "change-set.json").write_text(json.dumps(change_set, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        (run_specialists / "status.json").write_text(json.dumps(pending_status, indent=2) + "\n", encoding="utf-8")
        (run_dir / "audit-status.json").write_text(json.dumps({**pending_status, "note": "Independent audit has not run; readiness must remain conditional."}, indent=2) + "\n", encoding="utf-8")
        output_label = args.output_dir
    coverage = evidence["coverage"]
    contract_open_gaps = sum(
        1
        for gap in evidence.get("artifacts", {}).get("gaps", {}).get("records", [])
        if gap.get("status") != "resolved"
    )
    if args.markdown_output:
        print(f"Wrote linked Markdown evidence package ({len(specification_package)} files): {output_label.parent}")
    else:
        print(f"Wrote {output_label}")
    print(
        "Module {module}: {blocks} database blocks, {items} database items, "
        "{units} code units, {refs} referenced DB objects ({missing} missing DDL), {gaps} open gaps.".format(
            module=args.module.lower(),
            blocks=coverage["forms"]["database_blocks"],
            items=coverage["forms"]["database_items"],
            units=coverage["forms"]["triggers"] + coverage["forms"]["program_units"],
            refs=coverage["database"]["referenced_objects"],
            missing=coverage["database"]["missing_referenced_objects"],
            gaps=contract_open_gaps,
        )
    )
    if errors:
        print(f"Self-check recorded {len(errors)} issue(s); rerun with --self-check to fail the command.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
