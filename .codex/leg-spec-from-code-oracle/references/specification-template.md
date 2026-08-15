# Oracle Module Legacy Evidence Specification Template

This template is an executable output contract. It describes legacy evidence only. It must not contain target requirements, target UI design, target architecture, target tests, migration treatment, POC assumptions, or feasibility/readiness conclusions.

Use one package ID, `MOD-<MODULE-ID>`. Use semantic local keys only for material sections, tabs, grids, operations, and rules. Identify fields by their natural `BLOCK.ITEM` locator.

---
artifact_kind: legacy_evidence_specification
module_id: MODULE
module_evidence_id: MOD-MODULE
evidence_fingerprint: SHA256
extraction_run_id: RUN
extraction_mode: fresh
legacy_evidence_status: extracted_with_open_gaps
comparison_oracle_sha256: not-supplied
operation_details: MODULE-operation-details.md
decoded_source: MODULE-decoded-source.md
database_reference: MODULE-database-reference.md
---

# <Module title> — Legacy Evidence Specification

## 1. Document Control

Module scope, run identity, source fingerprint, extraction mode, and evidence boundary.

## 2. Evidence Summary

<!-- oracle-evidence:start key="executive-capabilities" -->
Source-backed capability and coverage summary.
<!-- oracle-evidence:end key="executive-capabilities" -->

## 3. Legacy Screen Overview

<!-- oracle-evidence:start key="legacy-screen" -->
Windows, canvases, interaction pattern, and screenshot links.
<!-- oracle-evidence:end key="legacy-screen" -->

<!-- oracle-evidence:start key="legacy-regions" -->
Visible regions, tabs, grids, and section keys.
<!-- oracle-evidence:end key="legacy-regions" -->

## 4. Module Structure

Every block, relation, canvas, window, tab page, attached library, menu, and called module with its extracted properties. Counts alone are not sufficient.

## 5. Legacy Capability Inventory

Source-backed module capabilities grouped by operation and screen region.

## 6. Operation Behavior Ledger

<!-- oracle-evidence:start key="functional-requirements" -->
One concise row per query, insert, update, delete, validation, save/commit/rollback, or custom-action path. Summarize triggers/preconditions, business/data effects, messages/outcomes, confidence, and gaps; link each row to the complete normalized record in the operation-detail child. Do not place exhaustive normalized collections in master table cells. These are legacy behavior records, not target requirements.
<!-- oracle-evidence:end key="functional-requirements" -->

## 7. Screen Layout And Regions

Canvas, tab, section, and grid structure with semantic local keys.

## 8. Field And Control Evidence

<!-- oracle-evidence:start key="field-inventory" -->
One subsection per visible section, tab, or grid, plus hidden/helper items. Every Forms item appears once or is explicitly cross-referenced. Each resolved item mapping includes the authoritative physical DDL type as `TABLE.COLUMN (TYPE)`.
<!-- oracle-evidence:end key="field-inventory" -->

## 9. Query And Retrieval Evidence

Query data sources, clauses, ordering, criteria behavior, LOVs, and relevant SQL.

## 10. Record Selection And Master-Detail Evidence

Row identity, relations, coordination, selection effects, and detail navigation.

## 11. Actions And Buttons

<!-- oracle-evidence:start key="actions" -->
Buttons, key triggers, custom commands, navigation, and observable outcomes.
<!-- oracle-evidence:end key="actions" -->

## 12. Business Rules And Validation

<!-- oracle-evidence:start key="business-rules" -->
Source-backed conditions, branches, validation, calculations, and outcomes. Use the columns `Applies during | Business condition | Message code | Message text | Effect | Association basis | Source`. Bind a message to a condition only when it occurs inside the active decoded `IF`/`ELSIF` branch in the same unit or another explicit control-flow relation proves it; preserve unbound messages explicitly and never repeat a path-wide message set for every rule.
<!-- oracle-evidence:end key="business-rules" -->

<!-- oracle-evidence:start key="delete-save-dependencies" -->
Delete, save, commit, rollback, dependency, and transaction evidence. Include a complete inbound foreign-key matrix for each selected persistence object and distinguish it from the narrower set of dependencies checked by Forms routines.
<!-- oracle-evidence:end key="delete-save-dependencies" -->

## 13. LOV And Lookup Evidence

<!-- oracle-evidence:start key="lookups" -->
LOV, record-group, lookup query, return mapping, validation, and default evidence.
<!-- oracle-evidence:end key="lookups" -->

## 14. Workflow And State Evidence

<!-- oracle-evidence:start key="legacy-state-model" -->
Legacy mode/state transitions and runtime property changes.
<!-- oracle-evidence:end key="legacy-state-model" -->

## 15. Data Model And Database Mapping

<!-- oracle-evidence:start key="database-objects" -->
Referenced database objects and item-to-column mappings.
<!-- oracle-evidence:end key="database-objects" -->

<!-- oracle-evidence:start key="database-constraints" -->
Constraints, keys, cascades, and dependency evidence.
<!-- oracle-evidence:end key="database-constraints" -->

<!-- oracle-evidence:start key="database-defaults" -->
Database and Forms defaults, plus required audit-column population ownership. If ownership is not established by a DDL default, decoded assignment, or supplied database trigger, render an explicit evidence gap.
<!-- oracle-evidence:end key="database-defaults" -->

## 16. Data Retrieval And Processing Logic

<!-- oracle-evidence:start key="retrieval-processing" -->
SQL, call chains, calculation logic, processing order, and side effects.
<!-- oracle-evidence:end key="retrieval-processing" -->

## 17. Error And Message Catalogue

<!-- oracle-evidence:start key="messages" -->
Message codes/text, conditions, severity where known, and source locators.
<!-- oracle-evidence:end key="messages" -->

## 18. Evidenced Operational Characteristics

Only characteristics established by supplied source, such as locking, commit ownership, external calls, file or host interaction, and security-sensitive behavior. Unknown runtime qualities remain unknown.

## 19. Behavior Coverage Scenarios

<!-- oracle-evidence:start key="evidence-derived-tests" -->
Observed entry-condition-action-outcome slices used to check extraction coverage. These are not target application test cases.
<!-- oracle-evidence:end key="evidence-derived-tests" -->

## 20. Evidence Traceability

<!-- oracle-evidence:start key="traceability" -->
Mapping from module/group local keys and natural legacy locators to source evidence and gaps.
<!-- oracle-evidence:end key="traceability" -->

## 21. Conflicts, Unknowns, And Open Evidence Questions

Conflicting evidence, unresolved calls, unreadable sources, missing artifacts, and questions that require more evidence or human clarification.

## 22. Appendices

### Appendix A. Source And Screenshot Inventory

<!-- oracle-evidence:start key="source-evidence" -->
All relevant source files and every plausibly associated screenshot, including link, association basis, confidence, hash, readability, and parse disposition.
<!-- oracle-evidence:end key="source-evidence" -->

### Appendix B. Item Evidence Inventory

<!-- oracle-evidence:start key="item-coverage" -->
Every Forms item with natural `BLOCK.ITEM` locator, region/tab/grid placement, properties, mapping, and evidence status.
<!-- oracle-evidence:end key="item-coverage" -->

### Appendix C. Trigger And Program Unit Inventory

<!-- oracle-evidence:start key="code-units" -->
Compact inventory summary and link to the decoded-source child. The child preserves every decoded trigger and program unit, including source, scope, calls, SQL, messages, parse status, exact full decoded source, and source hash. Exact call arguments and sequence SQL must remain visible package-wide.
<!-- oracle-evidence:end key="code-units" -->

### Appendix D. Legacy Event And Outcome Mapping

<!-- oracle-evidence:start key="event-mapping" -->
Legacy event, entry point, call chain, database effects, messages, navigation, and observable outcome.
<!-- oracle-evidence:end key="event-mapping" -->

### Appendix E. Framework And External Boundary Evidence

<!-- oracle-evidence:start key="framework-exclusions" -->
Framework calls, attached libraries, menus, called modules, host/file/report interactions, unresolved boundaries, and exact evidence limits.
<!-- oracle-evidence:end key="framework-exclusions" -->

### Appendix F. DDL Inventory

<!-- oracle-evidence:start key="ddl-inventory" -->
Compact DDL package index and link to the database-reference child. Section 15 retains material persistence, relationship, delete, default, and audit evidence; the child preserves relevant tables, views, sequences, synonyms, packages, triggers, constraints, every column with physical type/default/nullability, dependencies, and source locators. Do not duplicate the exhaustive DDL representation in both Section 15 and Appendix F, and do not use truncation placeholders.
<!-- oracle-evidence:end key="ddl-inventory" -->

### Appendix G. Technical Evidence Notes

<!-- oracle-evidence:start key="technical-notes" -->
Source-supported comparison anchors, SQL notes, precedence decisions, conflicts, and technical extraction notes.
<!-- oracle-evidence:end key="technical-notes" -->

### Appendix H. Glossary

Legacy terms, Forms terminology, abbreviations, and domain labels present in source.

### Appendix I. Extraction Coverage And Missing Sources

<!-- oracle-evidence:start key="extraction-coverage" -->
Coverage denominators, accounted/extracted/unknown counts, and status by evidence dimension.
<!-- oracle-evidence:end key="extraction-coverage" -->

<!-- oracle-evidence:start key="missing-sources" -->
Precise gaps with affected behavior, current fallback evidence, confidence impact, and acquisition/validation action.
<!-- oracle-evidence:end key="missing-sources" -->

### Appendix J. Extraction History

<!-- oracle-evidence:start key="incremental-history" -->
Run fingerprint, compiler version, mode, source delta, comparison oracle, and changed evidence dimensions.
<!-- oracle-evidence:end key="incremental-history" -->
