#!/usr/bin/env python3
"""Inventory Oracle Forms specification inputs and propose module associations."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable
import xml.etree.ElementTree as ET


FORM_EXTENSIONS = {
    ".fmb",
    ".fmx",
    ".fmt",
    ".xml",
    ".pll",
    ".pld",
    ".err",
    ".mmb",
    ".mmx",
    ".olb",
}
PRIMARY_EXTENSIONS = {".fmb", ".fmx", ".fmt", ".err"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
GENERIC_IMAGE_TOKENS = {
    "current",
    "existing",
    "legacy",
    "oracle",
    "forms",
    "form",
    "screen",
    "screenshot",
    "capture",
    "image",
    "gala",
    "ui",
}
FOLDER_ALIASES = {
    "form": ("form", "forms", "form_extraction"),
    "ddl": ("ddl", "ddls", "database"),
    "ui": ("ui", "screenshots", "images"),
}


@dataclass(frozen=True)
class DdlObject:
    name: str
    owner: str | None
    object_type: str
    path: Path


COMMON_ORACLE_OBJECTS = {
    "DUAL",
    "USER_OBJECTS",
    "USER_TABLES",
    "USER_TAB_COLUMNS",
    "USER_CONSTRAINTS",
    "USER_CONS_COLUMNS",
    "ALL_OBJECTS",
    "ALL_TABLES",
    "ALL_TAB_COLUMNS",
    "ALL_CONSTRAINTS",
    "ALL_CONS_COLUMNS",
    "DBA_OBJECTS",
    "DBA_TABLES",
    "DBA_TAB_COLUMNS",
    "CAT",
}


def local_name(value: str) -> str:
    if "}" in value:
        return value.rsplit("}", 1)[1]
    if ":" in value:
        return value.rsplit(":", 1)[1]
    return value


def attr_local(element: ET.Element, *names: str) -> str | None:
    wanted = {name.lower() for name in names}
    for key, value in element.attrib.items():
        if local_name(key).lower() in wanted and value:
            return decode_entities(value).strip()
    return None


def decode_entities(value: str, max_passes: int = 8) -> str:
    """Decode repeatedly escaped Forms XML text without looping forever."""
    decoded = value
    for _ in range(max_passes):
        next_value = html.unescape(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    return decoded.replace("&#10;", "\n").replace("&#13;", "\r").replace("&#xA;", "\n").replace("&#xD;", "\r")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def words(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) > 1 and token not in GENERIC_IMAGE_TOKENS
    }


def normalize_module_stem(path: Path) -> str:
    stem = path.stem.lower()
    for suffix in ("_fmb", "-fmb", "_form", "-form", "_module", "-module"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
    return re.sub(r"[^a-z0-9_$#]+", "", stem)


def relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def locate_folder(root: Path, canonical: str) -> tuple[Path | None, str | None]:
    children = {child.name.lower(): child for child in root.iterdir() if child.is_dir()}
    for alias in FOLDER_ALIASES[canonical]:
        if alias in children:
            warning = None if alias == canonical else f"Using '{alias}' as alias for '{canonical}'."
            return children[alias], warning
    return None, f"Missing '{canonical}' input folder."


def list_files(folder: Path | None, extensions: set[str]) -> list[Path]:
    if folder is None:
        return []
    return sorted(
        (path for path in folder.rglob("*") if path.is_file() and path.suffix.lower() in extensions),
        key=lambda item: str(item).lower(),
    )


def parse_form_xml(path: Path) -> dict[str, object]:
    result: dict[str, object] = {"path": path, "module": None, "title": None, "warnings": []}
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        result["warnings"] = [f"XML parse failed for {path.name}: {exc}"]
        return result

    candidates = [element for element in root.iter() if local_name(element.tag).lower() == "formmodule"]
    if not candidates and local_name(root.tag).lower() in {"module", "formmodule"}:
        candidates = [root]
    if not candidates:
        return result

    form = candidates[0]
    result["module"] = attr_local(form, "Name", "ModuleName") or attr_local(root, "Name", "ModuleName")
    result["title"] = attr_local(form, "Title", "ModuleTitle") or attr_local(root, "Title", "ModuleTitle")
    return result


def parse_ddl(path: Path) -> list[DdlObject]:
    text = read_text(path)
    create_replace = r"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:FORCE\s+)?(?:EDITIONABLE\s+|NONEDITIONABLE\s+)?"
    qualified_name = (
        r"(?:(?:\"?([A-Z][A-Z0-9_$#]*)\"?)\s*\.\s*)?"
        r"\"?([A-Z][A-Z0-9_$#]*)\"?"
    )
    object_patterns = [
        ("package body", rf"{create_replace}PACKAGE\s+BODY\s+{qualified_name}"),
        ("materialized view", rf"{create_replace}MATERIALIZED\s+VIEW\s+{qualified_name}"),
        ("table", rf"\bCREATE\s+(?:GLOBAL\s+TEMPORARY\s+)?TABLE\s+{qualified_name}"),
        ("view", rf"{create_replace}VIEW\s+{qualified_name}"),
        ("sequence", rf"{create_replace}SEQUENCE\s+{qualified_name}"),
        ("public synonym", rf"{create_replace}PUBLIC\s+SYNONYM\s+{qualified_name}"),
        ("synonym", rf"{create_replace}SYNONYM\s+{qualified_name}"),
        ("trigger", rf"{create_replace}TRIGGER\s+{qualified_name}"),
        ("index", rf"\bCREATE\s+(?:UNIQUE\s+|BITMAP\s+)?INDEX\s+{qualified_name}"),
        ("package", rf"{create_replace}PACKAGE\s+(?!BODY\b){qualified_name}"),
        ("procedure", rf"{create_replace}PROCEDURE\s+{qualified_name}"),
        ("function", rf"{create_replace}FUNCTION\s+{qualified_name}"),
    ]
    objects: list[DdlObject] = []
    seen: set[tuple[str, str | None, str]] = set()
    for object_type, expression in object_patterns:
        for match in re.finditer(expression, text, re.IGNORECASE):
            owner = match.group(1).upper() if match.group(1) else None
            name = match.group(2).upper()
            key = (name, owner, object_type)
            if key in seen:
                continue
            seen.add(key)
            objects.append(DdlObject(name=name, owner=owner, object_type=object_type, path=path))
    return objects


def strip_identifier(value: str) -> str:
    return value.replace('"', "").split(".")[-1].strip().upper()


def strip_plsql_comments_and_strings(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    text = re.sub(r"--[^\r\n]*", " ", text)
    text = re.sub(r"'(?:''|[^'])*'", "''", text)
    return text


def sql_statement_regions(text: str) -> list[str]:
    # Forms2XML may escape ProgramUnitText more than once. A single unescape
    # leaves entities such as ``&#10;`` whose semicolon is then mistaken for a
    # PL/SQL statement terminator, truncating SELECT ... FROM discovery.
    scrubbed = strip_plsql_comments_and_strings(decode_entities(text))
    regions: list[str] = []
    for match in re.finditer(r"\b(?:SELECT|INSERT|UPDATE|DELETE|MERGE)\b", scrubbed, re.IGNORECASE):
        start = match.start()
        semicolon = scrubbed.find(";", start)
        end = semicolon + 1 if semicolon != -1 and semicolon - start <= 4000 else min(len(scrubbed), start + 4000)
        regions.append(scrubbed[start:end])
    return regions


def extract_sql_object_references(text: str) -> set[str]:
    references: set[str] = set()
    object_name = r"(?:\"?[A-Z][A-Z0-9_$#]*\"?\s*\.\s*)?\"?[A-Z][A-Z0-9_$#]*\"?"
    sql_patterns = [
        rf"\b(?:FROM|JOIN|REFERENCES)\s+({object_name})",
        rf"\bINSERT\s+INTO\s+({object_name})",
        rf"\bUPDATE\s+({object_name})\s+SET\b",
        rf"\b(?:MERGE|DELETE)\s+INTO\s+({object_name})",
        rf"\bDELETE\s+FROM\s+({object_name})",
        rf"\bTABLE\s*\(\s*({object_name})",
    ]
    for region in sql_statement_regions(text):
        for expression in sql_patterns:
            for match in re.finditer(expression, region, re.IGNORECASE):
                references.add(strip_identifier(match.group(1)))
    for match in re.finditer(rf"\b({object_name})\s*\.\s*(?:NEXTVAL|CURRVAL)\b", decode_entities(text), re.IGNORECASE):
        references.add(strip_identifier(match.group(1)))
    return {name for name in references if name and name not in COMMON_ORACLE_OBJECTS}


def attached_libraries(text: str) -> set[str]:
    names = {
        match.group(1).lower()
        for match in re.finditer(r"\.ATTACH\s+LIBRARY\s+([A-Z0-9_$#]+)", text, re.IGNORECASE)
    }
    names.update(
        match.group(1).lower()
        for match in re.finditer(r"AttachedLibrary[^>]*\bName\s*=\s*[\"']([^\"']+)", text, re.IGNORECASE)
    )
    return names


def screenshot_score(module: str, title: str | None, image: Path) -> tuple[float, str]:
    image_text = image.stem.replace("_", " ").replace("-", " ")
    image_norm = normalized(image_text)
    module_norm = normalized(module)
    if module_norm and module_norm in image_norm:
        return 1.0, "filename contains the normalized module id"

    title = title or ""
    title_norm = normalized(title)
    if title_norm and (title_norm in image_norm or image_norm in title_norm):
        return 0.95, "filename closely contains the normalized screen title"

    image_words = words(image_text)
    title_words = words(title)
    overlap = len(image_words & title_words) / max(1, len(image_words | title_words))
    sequence = SequenceMatcher(None, title_norm, image_norm).ratio() if title_norm else 0.0
    score = round(max(overlap, sequence * 0.75), 4)
    return score, f"title token overlap={overlap:.2f}; normalized similarity={sequence:.2f}"


def discover_modules(form_files: list[Path]) -> tuple[dict[str, dict[str, object]], list[str]]:
    modules: dict[str, dict[str, object]] = {}
    warnings: list[str] = []
    xml_info: dict[Path, dict[str, object]] = {}

    for path in form_files:
        if path.suffix.lower() == ".xml":
            info = parse_form_xml(path)
            xml_info[path] = info
            warnings.extend(info["warnings"])  # type: ignore[arg-type]
            module_name = info.get("module")
            if module_name:
                key = normalized(str(module_name))
                modules.setdefault(key, {"module_id": str(module_name).lower(), "title": info.get("title")})

    for path in form_files:
        if path.suffix.lower() in PRIMARY_EXTENSIONS:
            key = normalized(normalize_module_stem(path))
            if key:
                modules.setdefault(key, {"module_id": normalize_module_stem(path), "title": None})

    for path, info in xml_info.items():
        module_name = info.get("module")
        if not module_name:
            continue
        key = normalized(str(module_name))
        if info.get("title"):
            modules[key]["title"] = info["title"]

    for key, module in modules.items():
        module_id = normalized(str(module["module_id"]))
        direct: list[Path] = []
        for path in form_files:
            stem = normalized(normalize_module_stem(path))
            if stem == module_id or stem == module_id + "l":
                direct.append(path)
                continue
            info = xml_info.get(path)
            if info and normalized(str(info.get("module") or "")) == key:
                direct.append(path)
        module["direct_files"] = sorted(set(direct), key=lambda item: str(item).lower())

    return modules, warnings


def resolve_libraries(module: dict[str, object], all_form_files: list[Path]) -> tuple[list[Path], list[str]]:
    by_stem: dict[str, list[Path]] = {}
    for path in all_form_files:
        by_stem.setdefault(normalized(path.stem), []).append(path)

    queue: list[str] = []
    for path in module["direct_files"]:  # type: ignore[index]
        if path.suffix.lower() in {".xml", ".pld", ".fmt", ".err"}:
            queue.extend(attached_libraries(read_text(path)))

    resolved: list[Path] = []
    unresolved: list[str] = []
    seen: set[str] = set()
    while queue:
        library = normalized(queue.pop(0))
        if not library or library in seen:
            continue
        seen.add(library)
        matches = by_stem.get(library, [])
        if not matches:
            unresolved.append(library)
            continue
        for path in matches:
            resolved.append(path)
            if path.suffix.lower() in {".pld", ".xml", ".fmt"}:
                queue.extend(attached_libraries(read_text(path)))
    return sorted(set(resolved), key=lambda item: str(item).lower()), sorted(set(unresolved))


def build_manifest(root: Path, module_filter: str | None = None) -> dict[str, object]:
    warnings: list[str] = []
    folders: dict[str, Path | None] = {}
    for canonical in ("form", "ddl", "ui"):
        folder, warning = locate_folder(root, canonical)
        folders[canonical] = folder
        if warning:
            warnings.append(warning)

    form_files = list_files(folders["form"], FORM_EXTENSIONS)
    ddl_files = list_files(folders["ddl"], {".sql"})
    image_files = list_files(folders["ui"], IMAGE_EXTENSIONS)
    modules, module_warnings = discover_modules(form_files)
    warnings.extend(module_warnings)

    ddl_objects = [item for path in ddl_files for item in parse_ddl(path)]
    ddl_by_name: dict[str, list[DdlObject]] = {}
    for item in ddl_objects:
        ddl_by_name.setdefault(item.name, []).append(item)
    ddl_type_counts: dict[str, int] = {}
    for item in ddl_objects:
        ddl_type_counts[item.object_type] = ddl_type_counts.get(item.object_type, 0) + 1

    selected_modules: list[dict[str, object]] = []
    requested = normalized(module_filter or "")
    for key, module in sorted(modules.items(), key=lambda pair: str(pair[1]["module_id"])):
        module_id = str(module["module_id"]).lower()
        if requested and requested not in {key, normalized(module_id)}:
            continue

        direct_files: list[Path] = module["direct_files"]  # type: ignore[assignment]
        shared_files, unresolved_libraries = resolve_libraries(module, form_files)
        library_groups: dict[str, list[Path]] = {}
        for library_path in shared_files:
            library_groups.setdefault(normalized(library_path.stem), []).append(library_path)
        library_source_status = []
        for library_name, library_paths in sorted(library_groups.items()):
            extensions = sorted({path.suffix.lower() for path in library_paths})
            readable_paths = [
                path for path in library_paths if path.suffix.lower() in {".pld", ".xml", ".fmt"}
            ]
            library_source_status.append(
                {
                    "name": library_name,
                    "status": "readable-source" if readable_paths else "binary-only",
                    "paths": [relative(path, root) for path in library_paths],
                    "extensions": extensions,
                }
            )
        searchable_paths = sorted(set(direct_files + shared_files), key=lambda item: str(item).lower())
        searchable_text = "\n".join(
            read_text(path)
            for path in searchable_paths
            if path.suffix.lower() in {".xml", ".pld", ".fmt", ".err"}
        )
        sql_reference_names = sorted(extract_sql_object_references(searchable_text))
        referenced_names = sorted(name for name in sql_reference_names if name in ddl_by_name)
        missing_ddl_objects = sorted(name for name in sql_reference_names if name not in ddl_by_name)
        matched_ddl = sorted(
            {item.path for name in referenced_names for item in ddl_by_name[name]}, key=lambda item: str(item).lower()
        )
        referenced_ddl_details = sorted(
            (
                {
                    "name": item.name,
                    "owner": item.owner,
                    "type": item.object_type,
                    "path": relative(item.path, root),
                }
                for name in referenced_names
                for item in ddl_by_name[name]
            ),
            key=lambda item: (str(item["name"]), str(item["type"]), str(item["path"])),
        )

        screenshot_candidates = []
        for image_path in image_files:
            score, rationale = screenshot_score(module_id, module.get("title"), image_path)  # type: ignore[arg-type]
            screenshot_candidates.append({"path": image_path, "score": score, "rationale": rationale})
        screenshot_candidates.sort(key=lambda item: (-item["score"], str(item["path"]).lower()))  # type: ignore[index]
        best = screenshot_candidates[0] if screenshot_candidates else None
        runner_up = screenshot_candidates[1] if len(screenshot_candidates) > 1 else None
        accepted = bool(
            best
            and (
                best["score"] >= 0.85
                or (best["score"] >= 0.45 and (not runner_up or best["score"] - runner_up["score"] >= 0.10))
            )
        )

        direct_exts = {path.suffix.lower() for path in direct_files}
        module_warnings_local = []
        if ".xml" not in direct_exts and ".fmt" not in direct_exts:
            module_warnings_local.append("No readable Forms XML or FMT was associated with the module.")
        if not any(path.suffix.lower() == ".pld" and normalized(path.stem) == normalized(module_id + "l") for path in direct_files):
            module_warnings_local.append("No module-specific companion PLD was associated with the module.")
        binary_only_libraries = [
            item["name"] for item in library_source_status if item["status"] == "binary-only"
        ]
        if binary_only_libraries:
            module_warnings_local.append(
                "Attached libraries have binary files but no readable PLD/XML/FMT source: "
                + ", ".join(binary_only_libraries)
                + "."
            )
        if not matched_ddl:
            module_warnings_local.append("No DDL object was directly matched from readable module source.")
        if missing_ddl_objects:
            shown = ", ".join(missing_ddl_objects[:20])
            suffix = "" if len(missing_ddl_objects) <= 20 else f", plus {len(missing_ddl_objects) - 20} more"
            module_warnings_local.append(
                f"Referenced SQL objects lack DDL after recursive ddl search: {shown}{suffix}."
            )
        if not accepted:
            module_warnings_local.append("No screenshot match met the automatic confidence threshold; visual review is required.")

        selected_modules.append(
            {
                "module_id": module_id,
                "title": module.get("title"),
                "form_files": [relative(path, root) for path in direct_files],
                "shared_library_files": [relative(path, root) for path in shared_files],
                "library_source_status": library_source_status,
                "unresolved_attached_libraries": unresolved_libraries,
                "referenced_sql_objects": sql_reference_names,
                "missing_ddl_objects": missing_ddl_objects,
                "referenced_ddl_objects": referenced_names,
                "referenced_ddl_details": referenced_ddl_details,
                "ddl_files": [relative(path, root) for path in matched_ddl],
                "screenshot_match": {
                    "selected": relative(best["path"], root) if accepted and best else None,
                    "score": best["score"] if best else None,
                    "rationale": best["rationale"] if best else None,
                    "requires_visual_confirmation": bool(best),
                    "candidates": [
                        {
                            "path": relative(item["path"], root),
                            "score": item["score"],
                            "rationale": item["rationale"],
                        }
                        for item in screenshot_candidates[:5]
                    ],
                },
                "warnings": module_warnings_local,
            }
        )

    assigned_ddl = {path for module in selected_modules for path in module["ddl_files"]}  # type: ignore[index]
    all_input_files = sorted(set(form_files + ddl_files + image_files), key=lambda item: str(item).lower())
    source_file_records = [
        {
            "path": relative(path, root),
            "extension": path.suffix.lower(),
            "size_bytes": path.stat().st_size,
            "sha256": sha256(path),
            "readability": "binary-only" if path.suffix.lower() in {".fmb", ".fmx", ".pll", ".olb", ".mmb", ".mmx"} else "readable",
        }
        for path in all_input_files
    ]
    input_manifest_sha256 = hashlib.sha256(
        json.dumps(source_file_records, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": 2,
        "input_root": str(root.resolve()),
        "input_manifest_sha256": input_manifest_sha256,
        "source_files": source_file_records,
        "folders": {name: relative(path, root) if path else None for name, path in folders.items()},
        "inventory": {
            "form_files": len(form_files),
            "ddl_files": len(ddl_files),
            "ddl_objects": len(ddl_objects),
            "ddl_object_type_counts": ddl_type_counts,
            "ui_files": len(image_files),
            "modules": len(selected_modules),
        },
        "ddl_objects": [
            {
                "name": item.name,
                "owner": item.owner,
                "type": item.object_type,
                "path": relative(item.path, root),
            }
            for item in sorted(ddl_objects, key=lambda value: (value.name, value.object_type, str(value.path).lower()))
        ],
        "modules": selected_modules,
        "unassigned_ddl_files": [relative(path, root) for path in ddl_files if relative(path, root) not in assigned_ddl],
        "warnings": warnings,
    }


def check_specs(manifest: dict[str, object], specs_dir: Path) -> list[str]:
    errors: list[str] = []
    if not specs_dir.exists():
        return [f"Specification directory does not exist: {specs_dir}"]
    markdown_files = list(specs_dir.glob("*.md"))
    for module in manifest["modules"]:  # type: ignore[index]
        module_id = str(module["module_id"]).lower()
        matches = [path for path in markdown_files if module_id in normalized(path.stem)]
        if len(matches) != 1:
            errors.append(f"Expected one specification for {module_id}; found {len(matches)}.")
            continue
        text = read_text(matches[0])
        if f'module_id: "{module_id.upper()}"' not in text and f'module_id: "{module_id}"' not in text:
            errors.append(f"Specification {matches[0].name} does not declare module_id {module_id}.")
        for link in re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', text, re.IGNORECASE):
            if re.match(r"^[a-z]+://", link, re.IGNORECASE):
                continue
            target = (matches[0].parent / link).resolve()
            if not target.exists():
                errors.append(f"Broken image link in {matches[0].name}: {link}")
    return errors


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Input root containing form, ddl, and ui folders")
    parser.add_argument("--output", type=Path, help="Write JSON manifest to this path; otherwise print to stdout")
    parser.add_argument("--module", help="Limit inventory to one module id")
    parser.add_argument("--check-specs", type=Path, help="Validate generated Markdown specifications in this folder")
    return parser.parse_args(list(argv))


def main(argv: Iterable[str] = ()) -> int:
    args = parse_args(argv or sys.argv[1:])
    root = args.input.resolve()
    if not root.is_dir():
        print(f"Input folder does not exist: {root}", file=sys.stderr)
        return 2

    manifest = build_manifest(root, args.module)
    rendered = json.dumps(manifest, indent=2, ensure_ascii=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(rendered, end="")

    if args.check_specs:
        errors = check_specs(manifest, args.check_specs.resolve())
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        if errors:
            return 1
        print(f"Validated specifications in {args.check_specs.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
