#!/usr/bin/env python3
"""Apply a hash-pinned patch only to explicit Oracle evidence-owned Markdown regions."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


START_RE = re.compile(r'(?m)^<!-- oracle-evidence:start key="([A-Za-z0-9_.:-]+)" -->\r?$')


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def marker_ranges(text: str) -> dict[str, tuple[int, int]]:
    ranges: dict[str, tuple[int, int]] = {}
    for match in START_RE.finditer(text):
        key = match.group(1)
        if key in ranges:
            raise ValueError(f"Duplicate evidence marker key: {key}")
        newline_end = text.find("\n", match.end())
        body_start = len(text) if newline_end < 0 else newline_end + 1
        end_re = re.compile(
            rf'(?m)^<!-- oracle-evidence:end key="{re.escape(key)}" -->\r?$'
        )
        end_match = end_re.search(text, body_start)
        if end_match is None:
            raise ValueError(f"Missing end marker for evidence region: {key}")
        ranges[key] = (body_start, end_match.start())
    return ranges


def load_patch(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Patch file must contain a JSON object.")
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported patch schema_version; expected 1.")
    expected = str(payload.get("expected_spec_sha256") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("expected_spec_sha256 must be a lowercase SHA-256 value.")
    patches = payload.get("patches")
    if not isinstance(patches, list) or not patches:
        raise ValueError("patches must be a non-empty list.")
    return payload


def apply_patch(text: str, payload: dict[str, Any]) -> tuple[str, list[str]]:
    ranges = marker_ranges(text)
    replacements: list[tuple[int, int, str, str]] = []
    seen: set[str] = set()
    for record in payload["patches"]:
        if not isinstance(record, dict):
            raise ValueError("Each patch must be an object.")
        key = str(record.get("key") or "").strip()
        content = record.get("content")
        if not key or key in seen:
            raise ValueError(f"Patch keys must be non-empty and unique: {key!r}")
        if key not in ranges:
            raise ValueError(f"Specification does not contain evidence marker: {key}")
        if not isinstance(content, str):
            raise ValueError(f"Patch content for {key} must be a string.")
        if "<!-- oracle-evidence:" in content:
            raise ValueError(f"Patch content for {key} may not contain evidence markers.")
        start, end = ranges[key]
        newline = "\r\n" if "\r\n" in text[max(0, start - 2) : start + 2] else "\n"
        normalized = content.replace("\r\n", "\n").replace("\r", "\n")
        normalized = normalized.rstrip("\n")
        replacement = normalized.replace("\n", newline) + newline
        replacements.append((start, end, replacement, key))
        seen.add(key)

    result = text
    for start, end, replacement, _ in sorted(replacements, reverse=True):
        result = result[:start] + replacement + result[end:]
    return result, [key for _, _, _, key in replacements]


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Patch only explicit evidence-owned regions of an Oracle specification."
    )
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--patch", required=True, type=Path)
    parser.add_argument("--output", type=Path, help="Defaults to replacing --spec atomically.")
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    original_bytes = args.spec.read_bytes()
    before_hash = sha256_bytes(original_bytes)
    payload = load_patch(args.patch)
    if before_hash != payload["expected_spec_sha256"]:
        raise ValueError(
            "Specification changed after the patch was prepared; refusing a stale incremental update."
        )

    original_text = original_bytes.decode("utf-8")
    updated_text, keys = apply_patch(original_text, payload)
    updated_bytes = updated_text.encode("utf-8")
    output = (args.output or args.spec).resolve()
    atomic_write(output, updated_bytes)

    report = {
        "schema_version": 1,
        "status": "passed",
        "spec": str(args.spec.resolve()),
        "output": str(output),
        "before_sha256": before_hash,
        "after_sha256": sha256_bytes(updated_bytes),
        "evidence_fingerprint": payload.get("evidence_fingerprint"),
        "source_delta_id": payload.get("source_delta_id"),
        "patched_keys": sorted(keys),
        "protected_content_policy": "all content outside explicit oracle-evidence markers preserved byte-for-byte",
    }
    if args.report:
        atomic_write(
            args.report.resolve(),
            (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
