# Normalized Oracle Module Evidence Contract

## Purpose

The compiler constructs a normalized evidence model in memory before rendering one linked legacy-evidence package. The model records what supplied artifacts establish, where each fact came from, what remains unknown, and how a later source update changes coverage.

The durable Markdown describes the legacy system only. It is not a target requirement, target design, architecture decision, target test suite, POC assumption, approval, or implementation-readiness statement.

## Durable And Transient Artifacts

The normal durable output is:

```text
evidence/features/<feature-slug>/
  <module>-<title>-specification.md
  <module>-operation-details.md
  <module>-decoded-source.md
  <module>-database-reference.md
```

Compiler JSON, specialist outputs, manifests, and guard results belong in a uniquely named operating-system temporary directory unless the user explicitly requests durable diagnostic evidence.

The master Markdown implements all 22 sections and Appendices A-J in `specification-template.md` and retains every paired `oracle-evidence` marker. Children carry exhaustive normalized operation records, exact decoded source, and complete DDL records. All four documents share module/run/fingerprint metadata and link within the package. Completeness is validated across the package; the master remains the human-review surface.

## Identifier Model

The human-facing governed identifier is:

```text
MOD-<MODULE-ID>
```

Semantic local keys are optional and limited to material groups:

```text
MOD-<MODULE-ID>#section.<slug>
MOD-<MODULE-ID>#tab.<slug>
MOD-<MODULE-ID>#grid.<slug>
MOD-<MODULE-ID>#operation.<slug>
MOD-<MODULE-ID>#rule.<slug>
```

Use natural Oracle locators for leaf evidence:

- field/control: `BLOCK.ITEM`;
- trigger/program unit: declared name and scope;
- database evidence: qualified object/column/constraint name;
- message: code or literal text plus source locator;
- source: repository-relative path and optional line/symbol locator.

Do not generate governed `FR`, `FLD`, `BR`, `MSG`, `TC`, or `OQ` IDs during evidence extraction.

The transient model may use deterministic machine keys such as `SRC-*`, `FACT-*`, `PATH-*`, and `GAP-*` for merging, deltas, and validation. These keys are not requirement IDs and are not the primary human identity of document rows.

## Evidence Principles

1. A fact requires a raw locator or an exact expected-reference locator for missing evidence.
2. Source facts, structural inference, behavioral inference, conflicts, and unknowns remain distinguishable.
3. Design-time, inherited, runtime-override, and effective CRUD remain separate.
4. Physical mappings require Forms mapping properties, SQL, or DDL support; item names alone are insufficient.
5. Binary artifacts are inventory evidence, not readable behavior evidence.
6. Absence in supplied source never proves runtime absence.
7. Screenshots supplement visible layout and labels; they do not override structural or executable source.
8. Legacy evidence never silently becomes a target requirement. That transition belongs to governed curation.

## Top-Level Shape

```json
{
  "schema_version": "oracle-module-evidence/1.x",
  "extractor": {},
  "run": {},
  "sources": [],
  "modules": [],
  "ddl": {},
  "artifacts": {
    "source_inventory": {"records": []},
    "normalized_evidence": {"records": []},
    "behavior_ledger": {"records": []},
    "coverage": {"records": []},
    "gaps": {"records": []},
    "source_delta": {"records": []}
  },
  "incremental": {},
  "self_check": {}
}
```

## Source Inventory

Each supplied or expected source record carries:

```json
{
  "source_id": "SRC-...",
  "relative_path": "form/glasct01_fmb.xml",
  "source_role": "forms_xml",
  "module_association": "GLASCT01",
  "media_type": "application/xml",
  "size_bytes": 123,
  "sha256": "...",
  "availability": "supplied|expected_missing|removed",
  "parse_status": "parsed|partial|binary_only|unparseable|not_applicable",
  "parse_warnings": []
}
```

Every supplied file must be accounted for. Recurse through all input descendants.

## Module Structure

A module record includes:

- module ID, title, source paths, and Forms properties;
- attached libraries and expected sources;
- runtime screenshot candidates with path, hash, association basis, numeric score, and confidence;
- windows, canvases, tab pages, blocks, relations, LOVs, and record groups;
- triggers and program units;
- item visual placement and CRUD evidence.

Every Forms item must have one `BLOCK.ITEM` locator and a visible-region placement status:

```json
{
  "block": "CTT",
  "item": "CTT_TITLE",
  "canvas": "MAIN",
  "tab_page": "DETAILS",
  "region_kind": "tab",
  "visible": true,
  "placement_status": "resolved"
}
```

Unknown placement becomes a precise gap; it is not silently assigned.

## Behavior Ledger

Create separate path records for each reachable or decoded operation entry point:

```json
{
  "path_id": "PATH-...",
  "operation": "query|insert|update|delete|validate|save|commit|rollback|custom",
  "entry_point": {"symbol": "KEY-COMMIT", "scope": "FORM"},
  "call_chain": [],
  "preconditions": [],
  "validations": [],
  "branches": [],
  "defaults_and_derivations": [],
  "database_reads": [],
  "database_writes": [],
  "database_effects": [],
  "messages": [],
  "dependency_checks": [],
  "side_effects": [],
  "transaction": {},
  "outcomes": [],
  "unresolved_calls": [],
  "locators": [],
  "confidence": "high|medium|low",
  "gap_ids": []
}
```

The human document groups paths under `MOD-<MODULE>#operation.<slug>` and identifies individual entries by their natural trigger/routine name, not by the transient path hash.

## Database Evidence

Capture relevant:

- tables, views, materialized views, synonyms, and sequences;
- columns, physical types, nullability, defaults, and keys;
- constraints, foreign-key targets, cascade behavior, indexes when material;
- database triggers, packages, procedures, and functions;
- view and synonym dependencies;
- object source paths and parse status.

DDL is authoritative for physical definitions when supplied. Forms and PL/SQL remain evidence of how those definitions are used.

## Screenshot Associations

Inventory every image. Create a module screenshot association when at least one conservative signal is present:

- exact filename/module ID;
- filename contains module ID;
- exact filename/Forms title;
- filename contains Forms title;
- meaningful title-token overlap above the configured threshold.

Store:

```json
{
  "path": "ui/GLASCT01 Maintain Standard Contract.png",
  "sha256": "...",
  "association_basis": "filename_contains_module_id, title_token_overlap_0.67",
  "association_score": 0.93,
  "association_confidence": "high",
  "matched_module_id": "GLASCT01",
  "matched_title": "Maintain Standard Contract"
}
```

Render all plausible candidates as relative, URL-encoded Markdown image links.

## Gap Contract

Machine gap records retain stable reconciliation IDs internally:

```json
{
  "gap_id": "GAP-...",
  "gap_kind": "source_missing|binary_only|unparseable|partial_parse|extraction_uncovered|conflicting_evidence|runtime_only|unresolved_call|missing_message_text|missing_ddl|ambiguous_mapping",
  "subject": "human-readable missing or uncertain subject",
  "status": "open|narrowed|resolved|reopened",
  "why_expected": "...",
  "expected_by_locators": [],
  "affected_operations": [],
  "affected_behavior": "...",
  "available_fallback_evidence": "...",
  "classification": "source_gap|extraction_gap|evidence_conflict|runtime_validation_gap",
  "recommended_action": "...",
  "resolution_evidence": [],
  "history": []
}
```

The human specification presents the subject, kind/status, impact, fallback evidence, and acquisition action. It need not expose the machine gap ID.

A gap resolves only when cited evidence establishes the subject. A design decision about future behavior does not resolve a legacy source gap.

## Coverage

Every material evidence dimension has:

```json
{
  "metric_id": "COV-...",
  "dimension": "items|visual_placement|effective_crud|operation_paths|ddl|messages|...",
  "denominator": 10,
  "numerator": 8,
  "exclusions": [],
  "unresolved_count": 2,
  "status": "complete|complete_with_registered_gaps|incomplete"
}
```

Completeness means every denominator member is extracted, explicitly excluded from that metric for a source-backed reason, or represented by a precise gap. It does not mean the legacy system is fully understood or the target is ready.

## Incremental Merge

1. Hash current sources and compare with prior transient evidence when supplied.
2. Reparse changed and dependency-affected sources.
3. Preserve unchanged normalized facts and machine keys.
4. Recompute dependent paths, coverage, and gaps.
5. Preserve gap history through `open`, `narrowed`, `resolved`, and `reopened`.
6. Refresh only paired evidence regions in a marker-enabled evidence draft.
7. Preserve human review notes outside generated regions unless they contradict current evidence; record contradictions as conflicts.
8. Never import target proposals, POC assumptions, or target tests from an older specification into the evidence model.

## Comparison Oracle

An older specification is a read-only semantic oracle. Candidate anchors include natural Oracle locators, Forms properties, routine names, database objects, message codes, and source filenames. Retain an anchor only when current evidence independently supports it. Target-only identifiers and prose are excluded.

## Self-Check

Fail compilation when:

- the selected module cannot be associated;
- a supplied source is unaccounted;
- a parsed item lacks a `BLOCK.ITEM` locator;
- an item is omitted from the Markdown;
- a path operation/entry is omitted;
- a complete normalized operation or DDL record is absent from its child;
- a package child is missing, unlinked, or has mismatched module/run/fingerprint metadata;
- a gap subject is omitted;
- a plausible screenshot is not linked;
- coverage arithmetic is invalid;
- a current-source-supported comparison anchor is lost;
- the document introduces target requirements, target tests, target design, POC readiness, or row-level requirement ID families.
- Section 6 or the Section 12 rule ledger contains an oversized table row caused by embedding exhaustive or path-wide collections.
