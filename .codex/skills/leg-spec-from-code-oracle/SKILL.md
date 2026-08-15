---
name: leg-spec-from-code-oracle
description: Extract a complete, source-traceable legacy evidence specification for one Oracle Forms module from Forms XML/FMT/FMB/FMX, PLL/PLD, DDL, message catalogues, menus/object libraries, and screenshots. Use for fresh or incremental reverse engineering when the output must preserve every evidenced screen region, tab, field, operation, rule, message, database dependency, provenance locator, uncertainty, and source-supported detail without inventing target requirements, target architecture, target tests, POC assumptions, or implementation decisions.
---

# Oracle Forms Module Evidence Extraction

Produce a faithful evidence package for one selected Oracle Forms module. This is stage 1 of a two-stage legacy requirements workflow:

1. `leg-spec-from-code-oracle` extracts what the supplied legacy artifacts establish.
2. A separate curation skill converts that evidence into target UI, backend requirements, and target test cases.

The generated Markdown is controlled legacy evidence. It is not an approved requirement, a target design, a feasibility assessment, or authorization to generate code.

## Non-Negotiable Boundaries

1. Process exactly one tenant, one project, and one selected module.
2. Extract every relevant fact supported by readable source, including all canvases, windows, sections, tabs, grids, fields, buttons, triggers, program units, SQL, messages, CRUD paths, validation branches, database objects, constraints, dependencies, and unresolved calls.
3. Keep source facts separate from inference. Label confidence and preserve ambiguity as a gap or conflict.
4. Never turn missing evidence into evidence of absence.
5. Never infer a physical column from an item name alone.
6. Never treat binary Forms artifacts as readable behavior source.
7. Do not propose a target page, web interaction, API, database design, target requirement, target test, migration treatment, POC assumption, or production-readiness conclusion.
8. Do not discard an evidenced legacy behavior merely because it may be redesigned later.
9. Do not persist transient compiler JSON in the project repository during a normal extraction.
10. Preserve uploaded evidence and previous specifications unchanged unless the user explicitly asks to modify them.

## Identifier Economy

Use one human-facing global identifier for the module evidence package:

```text
MOD-<MODULE-ID>
```

Use qualified semantic local keys only where they materially improve navigation or later traceability:

```text
MOD-<MODULE-ID>#section.<slug>
MOD-<MODULE-ID>#tab.<slug>
MOD-<MODULE-ID>#grid.<slug>
MOD-<MODULE-ID>#operation.<slug>
MOD-<MODULE-ID>#rule.<slug>
```

Do not create human-facing IDs for every field, message, branch, SQL statement, source file, test scenario, or database column. Use natural legacy locators such as `BLOCK.ITEM`, trigger or routine names, database object names, message codes, and source file/line locators.

The compiler may retain deterministic `SRC-*`, `FACT-*`, `PATH-*`, and `GAP-*` keys inside transient validation evidence. Those are machine reconciliation keys, not governed requirement IDs and need not be shown as the primary identity of each document row.

## Project Scope

Resolve the project repository as:

```text
agentic-sdlc-data/tenants/<tenant>/projects/<project>/repo
```

Verify `project.yaml` exists and declares `objective_type: legacy_modernization`. Keep all generated artifacts inside the selected project repository and preserve uploads in place.

## Durable Output

Create one linked, lossless evidence package per module under a semantic feature folder:

```text
evidence/features/<feature-slug>/
  <module-id>-<screen-title>-specification.md
  <module-id>-operation-details.md
  <module-id>-decoded-source.md
  <module-id>-database-reference.md
```

Derive `<feature-slug>` from the business screen title, not from the action used to open the legacy form. Conservatively remove a leading action/navigation verb such as `maintain`, `retrieve`, `view`, or `manage` only when the remaining subject is unambiguous. For example, `Maintain Standard Contract` becomes `standard-contract`. Honor an explicit feature-folder override in run Notes. Keep the module ID in every filename to avoid collisions.

The master specification must implement all 22 numbered sections and Appendices A-J in `references/specification-template.md`. Child documents are controlled parts of the same evidence package, not optional supplements. Every child must declare the same module ID, module evidence ID, extraction run ID, and evidence fingerprint as the master and link back to it. The master must link to every child with relative Markdown links.

Package responsibilities:

- Master specification: human-reviewable legacy UI, fields, concise operation ledger, business rules, condition/message/effect associations, material persistence relationships, gaps, coverage, and traceability.
- Operation details: every complete normalized operation record, including calls, SQL, reads/writes, dependencies, messages, effects, source locators, and gaps.
- Decoded source: every trigger/program-unit inventory record and every exact full decoded source body with hash and locator.
- Database reference: every complete parsed relevant DDL object record, including all columns, constraints, defaults, dependencies, and locators.

Completeness is package-wide. Moving evidence to a child is allowed only when the master retains a useful summary and direct link and the guard proves the exhaustive record exists in the child. Never create an unlinked companion file.

The durable document must contain:

- the module identifier and extraction fingerprint;
- source inventory and parse/readability disposition;
- all visible regions, canvases, tabs, grids, controls, and hidden/helper items;
- every window, canvas, and tab-page definition rendered with its properties, not only aggregate counts;
- one natural `BLOCK.ITEM` locator for every Forms item;
- each source-supported Forms item mapping shown as `TABLE.COLUMN (PHYSICAL_DDL_TYPE)`;
- design-time and effective query/insert/update evidence kept distinct;
- operation behavior for query, insert, update, delete, validation, save/commit/rollback, and custom actions where present;
- decoded triggers, program units, calls, SQL, messages, property changes, navigation, and side effects, plus the exact full decoded unit source in a navigable appendix;
- referenced DDL, constraints, dependencies, sequences, synonyms, views, and database triggers where supplied;
- an inbound foreign-key matrix for every selected persistence object, including columns, referenced columns, `ON DELETE` behavior, and whether a decoded Forms delete path checks the dependency;
- an explicit gap when required audit columns exist but the supplied source does not establish whether Forms, a database trigger, or another runtime owner populates them;
- source locators, confidence, conflicts, coverage, and precise missing-source gaps;
- every plausible module screenshot as an Azure Wiki-compatible Markdown link.

Never emit `[truncated]`, `+N more`, or another lossy placeholder for source-backed durable evidence. Split high-cardinality evidence into rows or collapsible source sections instead.

Readability and deduplication rules:

- Section 6 contains one concise row per operation path. Do not serialize full normalized lists into a table cell; link each row to its complete operation record in the operation-detail child.
- Sections 12 (dependency/transaction rows), 14, 16, 19, and Appendices D/E keep concise curation or coverage summaries with per-path links. The operation-detail child owns their exhaustive technical collections so the master does not restate the same path several times.
- Section 12 uses `Applies during | Business condition | Message code | Message text | Effect | Association basis | Source`. Associate a message with a condition only when it occurs inside the active decoded `IF`/`ELSIF` branch in the same unit, or another equally explicit control-flow relation proves the binding. Preserve unbound messages explicitly. Never repeat a path-wide message or stop-effect collection for every branch.
- Section 15 contains curation-relevant persistence objects, keys, relationships, delete consequences, defaults, and audit ownership. Appendix F is a compact DDL package index. The database child owns the exhaustive DDL representation; Section 15 and Appendix F must not duplicate it.
- Appendix C is a compact inventory summary and link. The decoded-source child owns the exhaustive unit inventory and exact source bodies.
- A master table row longer than 4,000 characters in Section 6 or 5,000 characters in the Section 12 rule ledger is a validation failure, not a reason to truncate.

## Required References

Read before running or changing the workflow:

- `references/normalized-evidence-contract.md`
- `references/specialist-agent-contracts.md`
- `references/completeness-readiness-staleness-gates.md`
- `references/module-archetype-lenses.md`
- `references/oracle-analysis-rules.md`
- `references/specification-template.md`

## Input Model

Accept a complete source bundle or a supplemental upload. Folder names are case-insensitive. Recurse through every descendant.

```text
<input>/
  form/
  ddl/
  ui/
```

Classify files by extension, content, attached-library declarations, module naming, existing gaps, and the explicit module filter. Ignore unrelated modules except where a selected-module call or dependency makes the artifact relevant.

## Run Modes

- `fresh`: generate the complete evidence specification from the selected bundle. When prior specifications are supplied or auto-discovered, use all of them only as comparison oracles for source-supported legacy anchors.
- `refresh`: rerun the complete selected bundle and replace paired `oracle-evidence` regions in a marker-enabled evidence specification. Preserve human review notes outside generated regions, but never preserve target proposals as if they were extracted facts.
- `audit-only`: analyze coverage and falsification without writing a specification.

If an older specification contains target proposals, POC assumptions, target tests, or implementation decisions, exclude those concepts from the new evidence specification. Preserve only details independently supported by the current source bundle.

## Workflow

### 1. Resolve Scope

Resolve tenant, project, project repository, selected module, source paths, output path, and run mode. Refuse to overwrite an approved or baselined artifact. Never broaden the run to every module just because the bundle contains multiple modules.

### 2. Inventory And Fingerprint

Run the recursive inventory:

```powershell
python <skill-dir>\scripts\oracle_spec_inventory.py <input> --module <module-id> --output <temp-manifest>
```

Every supplied file must have a hash, role, module association, readability, and parse disposition. Repeatedly decode Forms XML text until stable. Record exact parse or acquisition gaps when extraction remains incomplete.

### 3. Compile The Evidence Candidate

Use a uniquely named operating-system temporary directory for validation evidence:

```powershell
python <skill-dir>\scripts\oracle_module_evidence.py <input> --module <module-id> --markdown-output <project-repo>\evidence\features\<feature-slug>\<candidate-spec> --validation-evidence-output <temp-dir>\evidence-model.json --extraction-mode fresh --self-check
```

Add `--comparison-spec <prior-spec>` when a specific older specification should be checked for source-supported legacy anchors. In fresh mode, when no explicit comparison is given, the compiler checks `previous_<output-name>.md`, the same-named flat historical specification when the new output is nested, and every adjacent `<output-stem>_v*.md` file it finds. For a nested feature package it also checks the parent `evidence/features/` folder so the current flat specification and older v0/v1 files remain continuity oracles. Use `--previous-spec <current-spec> --extraction-mode refresh` only for a marker-enabled current evidence draft.

The compiler must not stop merely because a companion library, called module, DDL object, message catalogue, or screenshot is absent. It must stop when the input cannot be read safely or the selected module cannot be associated.

### 4. Apply Independent Evidence Lenses

Apply these evidence-only lenses independently:

1. Forms UI, visual placement, and effective CRUD.
2. PL/SQL behavior, rules, messages, calls, and side effects.
3. DDL, dependency, constraint, and transaction behavior.

Reconcile supported findings by source locator. Preserve conflicts and unknowns. Specialists must not invent target treatment or edit the controlled specification directly.

### 5. Screenshot Discovery

Inspect every image under the input bundle. Score association using:

- exact or contained module ID;
- exact or similar Forms title;
- meaningful filename token overlap with the module title;
- proximity to selected-module source when relevant.

Attach every plausible match, not only the highest-scoring image. For each candidate record the association basis and confidence. Use a relative Azure Wiki-compatible image link from the specification to the preserved upload, URL-encoding spaces and other unsafe path characters:

```markdown
![GLASCT01 legacy screenshot](../../uploads/.../ui/GLASCT01%20screen.png)
```

Do not copy, rename, or delete the uploaded image merely to make the link convenient. A screenshot supports visible grouping, labels, and layout; it does not override Forms XML, PL/SQL, DDL, or runtime evidence.

### 6. Compare Without Contaminating Evidence

When comparing against an older specification:

1. Extract candidate legacy anchors such as `BLOCK.ITEM`, trigger/routine names, Forms properties, message codes, database objects, and source filenames.
2. Extract exact source statements and call expressions from prior source-excerpt sections as continuity candidates.
3. Retain each anchor or statement only when current evidence independently supports it.
4. Fail validation if a supported prior anchor or exact statement disappears from the new document.
5. Do not carry forward old `CHG-*`, `FR-*`, `FLD-*`, `BR-*`, `MSG-*`, `TC-*`, `OQ-*`, assumptions, target treatments, or POC decisions merely because they were present before.

### 7. Validate

Run:

```powershell
python <skill-dir>\scripts\oracle_module_evidence.py <input> --module <module-id> --markdown-output <project-repo>\evidence\features\<feature-slug>\<candidate-spec> --validation-evidence-output <temp-dir>\evidence-model.json --comparison-spec <prior-spec-if-used> --extraction-mode fresh --self-check
python <skill-dir>\scripts\oracle_spec_guard.py --evidence <temp-dir>\evidence-model.json --spec <candidate-spec> --output <temp-dir>\specification-validation.json
git diff --check -- <changed-paths>
```

Validation must fail for missing template sections or markers, a missing/broken/mismatched package child, any `[truncated]` marker, an omitted complete operation or DDL record, an omitted Forms item, missing typed DDL mapping, missing window/canvas/tab definition, incomplete inbound-FK coverage, absent exact decoded unit source, missing visible region/tab/grid membership, absent operation paths or material gaps, unaccounted supplied sources, oversized Section 6/12 rows, path-wide message repetition, a stale fingerprint, broken screenshot or child links, unsupported limiting claims, or loss of a current-source-supported comparison anchor or source statement.

Precisely registered open gaps do not make extraction fail. They make the evidence incomplete in the named dimensions.

## Controlled Evidence Rules

- Preserve uploads under `evidence/uploads/`.
- Keep the complete module evidence package under `evidence/features/<feature-slug>/`.
- Do not write extracted evidence into canonical `requirements/`, `architecture/`, or `tests/`.
- Do not mark evidence approved.
- Do not create commits, tags, pushes, releases, baselines, or approvals unless explicitly requested.
