---
name: leg-curate-requirements-oracle
description: Curate an Oracle Forms modernization feature by reconciling extracted Oracle evidence, linked screenshots, a running target mockup, its Next.js implementation, existing canonical requirements, and accepted target architecture. Use when a target mockup must be converted or incrementally enriched into a review-ready feature requirement package plus an evidence-backed server-side implementation specification covering UI-to-data mappings, LOVs, validations, detailed decision rows for Delete, Add, Edit, and other operations, Oracle-constraint-to-application-message translations, transactions, tab dependencies, APIs, errors, security, and acceptance scenarios without inventing unsupported physical mappings.
---

# Curate Oracle Requirements And Implementation Specification

Create two linked, controlled artifacts for one target feature:

1. a canonical business-facing feature requirement package under `requirements/features/`;
2. a physical target implementation specification under `architecture/target-to-be/`.

Specialize the behavior of `../leg-curate-requirements/SKILL.md`. Follow the repository `AGENTS.md` and `CANONICAL_MODEL.md`. Keep requirement intent separate from tables, columns, procedures, endpoints, and transaction design.

## Inputs

| Input | Required | Default | Meaning |
| --- | --- | --- | --- |
| `Tenant` | No | `default` | Agentic SDLC tenant key. |
| `Project` | No | `gala` | Agentic SDLC project key. This specialized skill overrides the workspace-wide manual default. |
| `Project repo` | No | `auto` | Explicit project repository path or automatic resolution. |
| `feature_name` | Yes | None | Target feature slug, such as `standard-contract`. |
| `module_names` | Yes | None | One or more Oracle evidence module folder names, separated by commas. |
| `mockup_url` | Yes | None | Running URL for the target-state mockup. |
| `project_directory` | No | `C:\workspace\replatform\GALA\galanext` | Next.js project containing the mockup. |
| `overwrite` | No | `false` | Replacement mode for the matching module artifacts. Only an explicit `true` permits controlled replacement; every other run is incremental. |
| `Notes` | No | None | Run-specific scope, authority, decisions, restrictions, and output guidance. |

Stop and request any missing required input. When `Project` is omitted, state that this Oracle specialization defaults to `gala`. Split comma-separated module names, trim whitespace, remove empty values, and de-duplicate while preserving input order.

Accept `overwrite` only as `true` or `false`, case-insensitively. Treat an omitted value as `false`; request correction for any other value. Report the selected run mode before writing.

## Resolve Scope

Resolve exactly one project repository:

```text
agentic-sdlc-data/tenants/<tenant>/projects/<project>/repo
```

Verify the repository and `project.yaml` exist. Require `objective_type: legacy_modernization` unless Notes explicitly authorize a compatible legacy-modernization run. Read `TAXONOMY.md`, `ROLES.md`, existing requirements, review state, traceability, and applicable architecture before writing.

Resolve `project_directory` to an existing Next.js project. Treat the project repository as controlled evidence and the Next.js directory as read-only target implementation input. Never modify mockup application code in this workflow.

Resolve every requested module beneath:

```text
<project-repo>/evidence/features/<module-name>/
```

Treat this direct feature folder as the only normal module evidence root. Do not search or consume `evidence/features/oracle-modules/`; it contains extraction-run details rather than the curated module evidence for this workflow. Use it only when Notes explicitly opt in to a named artifact there.

Apply this matching order:

1. exact folder-name match;
2. case-insensitive normalized match, treating spaces, underscores, and hyphens as equivalent;
3. token-overlap and edit-similarity ranking;
4. automatic selection only when one candidate is clearly superior;
5. clarification when leading candidates are materially ambiguous;
6. explicit failure with available candidates when no credible match exists.

Report every requested-to-resolved mapping. Never omit an unresolved module silently.

## Read Required Sources

Read the relevant subset of these sources:

- `project.yaml`, `TAXONOMY.md`, `ROLES.md`, and existing canonical requirements;
- every relevant evidence file and linked image in each resolved feature folder;
- every `*-operation-details.md` or equivalent exhaustive operation-evidence artifact in each resolved feature folder, including the complete records for applicable operations rather than only summary links;
- Oracle DDL/metadata for every in-scope table constraint plus Forms `ON-ERROR`, constraint-checking, message-push, `RAISE_APPLICATION_ERROR`, and equivalent exception handlers;
- linked application message catalogues or lookup evidence that resolves legacy codes such as `GLA-*` to final user-facing text and substitution parameters;
- source inventories, candidate records, coverage reports, and open questions connected to the modules;
- applicable `architecture/decisions/` and `architecture/target-to-be/` artifacts;
- the running mockup, including all tabs, dialogs, grids, actions, errors, empty states, and navigation states;
- the mockup route, components, models, state, API calls, and validation code in `project_directory`;
- existing target backend and API conventions relevant to the feature.

Follow relative evidence links and inspect linked screenshots at readable resolution. Record unreadable files, broken links, inaccessible mockup states, and missing source exports as evidence gaps.

When an exhaustive operation-evidence artifact exists, treat each `## <operation type> - <entry point>` record and its declared calls, database reads, writes/effects, dependency checks, messages, stop effects, outcomes, side effects, and transaction behavior as the operation inventory. Use its record counts as reconciliation controls, follow its source locators into decoded source when predicate or bind detail is needed, and apply any semantic-review overlay that explicitly resolves an extraction ambiguity. Do not curate from the shorter operation summary alone.

## Apply Source Authority

Use sources according to responsibility:

1. explicit Notes and accepted architecture decisions govern target intent and approved replacement choices;
2. Oracle source evidence governs legacy tables, columns, triggers, program units, procedures, LOV queries, validations, database operations, and transaction order;
3. screenshots govern visible legacy fields, labels, sections, tabs, grids, control presentation, and relative organization;
4. the reviewed mockup runtime and its code are authoritative for the target UI surface: screens, controls, labels, layout, navigation, and represented UI states;
5. target application conventions govern implementation style only where architecture has not decided otherwise.

Where the mockup does not specify a control's detailed behavior, use Oracle evidence for the legacy behavior and make any target change explicit. Do not treat mock data, UI labels, TypeScript property names, or screenshot values as proof of physical database behavior. Do not state a table, column, data type, default, validation, procedure, endpoint, authorization rule, or transaction sequence as fact without Oracle evidence or an accepted decision.

Classify unsupported or conflicting claims as `TBD`, assumptions, open questions, review findings, or architecture open questions. Include evidence locator and confidence for every physical mapping.

## Build Inventories Before Drafting

Build a complete target UI inventory containing:

- search fields and operators;
- header and detail controls;
- tabs, sections, dialogs, and grids;
- every grid column and repeating child record;
- buttons, links, row actions, navigator controls, and form submissions;
- required, read-only, derived, defaulted, and dependent states;
- validation, error, loading, empty, confirmation, cancel, and success states;
- transitions among search, select, view, add, edit, save, delete, and related-detail states.

Build a corresponding Oracle inventory containing:

- modules, windows, canvases, blocks, and items;
- tables, views, columns, constraints, packages, procedures, and functions;
- LOVs, record groups, display values, return values, filters, and dependencies;
- triggers, events, program units, validations, defaults, calculations, and messages;
- every in-scope database constraint and application-raised failure, including the Oracle failure signature, legacy handler branch, mapped application message code, final message lookup, parameters, responsible control/action, matching precedence, and transaction consequence;
- query, insert, update, delete, commit, rollback, and navigation sequences;
- every evidenced operation entry point and its ordered triggers, program units, branch predicates, binds, messages, queries, DML, procedure/function calls, state changes, confirmations, stop/continue behavior, commit, rollback, and exception handling;
- confidence, source path, and source locator for each material conclusion.

Reconcile related modules into one feature model. Merge only proven duplicates. Preserve conflicting or module-specific behavior until evidence or a controlled decision resolves it.

Treat legacy error translation as a two-stage contract, not as an incidental exception string:

```text
Oracle constraint/error signature -> legacy application message code -> user-facing message/template
```

Inventory schema-qualified and unqualified constraint forms as one semantic mapping. Preserve exact application codes, message parameters, and handler precedence. A known first-stage mapping with an unavailable message-catalogue text is partial evidence: retain the code, mark the final text `TBD`, and link one consolidated gap rather than replacing it with a generic constraint message.

Create a coverage matrix for every target UI element using exactly one disposition:

- `verified`: directly supported by evidence or an accepted decision;
- `inferred`: supported by multiple consistent clues but not directly proven;
- `conflict`: sources disagree materially;
- `TBD`: required information is absent;
- `not-applicable`: intentionally has no backend behavior, with rationale.

Do not draft final artifacts while an inventory row lacks a disposition. A material `inferred`, `conflict`, or `TBD` row must also reference one entry in the consolidated implementation gap register.

## Preserve The Artifact Boundary

Put business purpose, target behavior, rules, outcomes, acceptance behavior, origin, and change intent in the feature requirement package. Use stable semantic local keys and canonical metadata.

Put physical mappings, APIs, service allocation, schemas, procedures, transaction design, persistence sequencing, concurrency, security implementation, observability, and performance design in the target implementation specification.

Reference requirement behavior from the implementation specification as:

```text
<PACKAGE-ID>#<local-key>
```

Use exactly one global governed package ID for the module: the feature requirement package ID. The implementation specification carries that value as `governed_package_id` and has no second global design ID. Controls, fields, rules, actions, scenarios, gaps, and other internal content use stable semantic local keys qualified as `<PACKAGE-ID>#<local-key>` only when referenced outside the package.

Do not duplicate the full physical design into requirements. Do not invent global IDs for every control, column, procedure, endpoint, acceptance criterion, gap, or scenario.

## Curate Detailed Operation Decisions

Retain the existing action contracts and CRUD completeness table as readable summaries. In addition, create one `Operation Decision Tables` section in the implementation specification. It contains the implementation-significant detail for all applicable operations in the feature, not only Delete.

Treat an operation as requiring detailed rows when its evidence contains one or more validations, branches, confirmations, warnings, database reads, DML statements, procedure/function calls, state transitions, transaction effects, navigation effects, or exception paths. Examples include Add, Edit, Save/Submit, Delete, Search, Clear/Cancel, LOV selection, child-row actions, tab actions, approvals, copies, calculations, and module-specific buttons or key triggers.

For each such operation:

1. Follow the operation from its UI or Forms entry point through all called triggers and program units.
2. Expand each material predicate, validation, warning, query, write, call, message, control-flow outcome, and transaction effect into an atomic ordered row and preserve its primary evidence classification when available, such as `hard_blocker` or `warning_confirmation`; otherwise use a concise decision kind such as query, DML, call, state-transition, or exception.
3. Capture exact inputs and binds, physical Oracle object or call, exact known message/code, continue/stop/confirm/retry behavior, and commit/rollback effect.
4. Preserve phase and execution order, including pre-query, post-query, when-button-pressed, pre-insert, pre-update, pre-delete, key-commit, on-error, and equivalent module-specific checkpoints.
5. Cross-reference the local operation-row keys from the applicable action, validation, CRUD, parent-child, API, and acceptance contracts.

Use stable local keys such as `operation.delete.precheck.child-exists` or `operation.save.insert.allocate-contract-id`. Prefer semantic suffixes; use `hard-01` or `warning-01` only when evidence supplies no stable semantic name. These are package-local keys, not new global IDs or trace records.

Do not replace evidenced detail with a count or narrative summary. If evidence states that an operation has 39 hard checks and 15 warnings, represent all 54 rows. When only 53 can be resolved, add the missing row as `TBD` with a consolidated gap key and identify the expected count mismatch. Preserve separately ordered rows even when they reference the same Oracle object or message.

For a genuinely simple operation, include one row describing its complete behavior. If the feature has no material operations, include one `not-applicable` row with evidence or decision rationale. Never fabricate Delete, Add, Edit, or other operations that neither the mockup nor controlled target scope contains.

## Curate Oracle Constraint And Error Translation

Create one local `Oracle Constraint And Error Translation` table in the implementation specification. Use stable semantic keys such as `error.constraint.scp-uk1`; these are package-local keys, not new global identifiers.

Cover every failure reachable from an in-scope query or mutation, including:

- primary-key, unique, check, foreign-key, not-null, trigger-raised, and application-raised failures;
- Forms error-handler branches that translate a database failure into an application code;
- the message-catalogue lookup that translates the application code into final text and substitution parameters;
- pre-DML validation that intentionally prevents the same failure, without treating it as a replacement for database-side enforcement;
- the responsible UI control, grid row, dialog, or action and the editor/focus behavior after failure;
- exact matching and precedence rules, including schema qualification, quoting/case normalization, SQL/driver metadata, and the unknown-error fallback;
- rollback/commit consequences and the structured API error returned to the client.

Reconcile three counts where the evidence permits: in-scope physical/application failure signatures, signatures with a legacy application-code mapping, and mappings with final message text. Represent every uncovered item as a `TBD` row or partial row with one consolidated gap key. Do not silently convert a known constraint into a generic error and do not invent message-catalogue text.

The table must be directly implementable as one centralized translator. It must distinguish at least `code`, user-safe `message`, normalized `constraint` when applicable, and responsible local `target`; retain diagnostic detail server-side without exposing unsafe SQL or bind values. Specify a safe unknown-error fallback, but never use it for a fully or partially known mapping when the known application code can be preserved.

Reference applicable `error.*` mapping keys from validation, action, operation-decision, API, and acceptance rows so the implementation path cannot lose the curated translation layer.

## Required Content

Use `references/specification-template.md` for exact artifact shapes and tables.

Ensure the feature requirement package covers:

- purpose, authority, actors, scope, prerequisites, and lifecycle;
- target search, view, add, edit, delete, and related-detail behavior;
- business rules, validations, outcomes, exceptions, and missing-configuration behavior;
- user-visible error behavior requiring known Oracle failures to retain their evidenced legacy application code and resolve to a safe, actionable message at the responsible control/action rather than exposing only a raw constraint name;
- origin and change intent for preserved, modified, reimagined, net-new, and retired behavior;
- semantic local requirements and testable acceptance criteria;
- assumptions, open questions, evidence coverage, and target differences.

Ensure the target implementation specification covers:

- one human-readable control contract for every field, grid column, button, link, row action, tab, dialog, navigator, submission, and material UI state shown by the mockup;
- for every control: mode, visibility, enabled/read-only state, requiredness, default, dependencies, triggers, validation/error references, requirement reference, and its data or action contract reference;
- one UI-to-data mapping row for every field and grid column;
- data type, nullability, default, read/write mode, transformation, source object, target contract, evidence locator, confidence, and disposition;
- complete LOV display/return contracts, query sources, dependencies, sorting, inactive-value handling, and caching expectations;
- client validation and authoritative server validation with exact outcomes;
- one exhaustive local Oracle constraint/error translation catalogue covering the database signature, legacy application code, final message/template and parameters, affected control/action, match precedence, API/UI outcome, transaction/editor behavior, evidence, and any gap;
- trigger timing, calculations, derived values, business rules, and exceptions;
- filtering, search operators, sorting, pagination, no-result behavior, and query limits;
- explicit create, retrieve, update, delete, search, clear, cancel, button, row-action, and form-submit coverage, including an applicability rationale when an operation does not exist;
- for every action: visibility/enabled conditions, preconditions, authorization, ordered client and server validations, exact known error messages, transaction boundary, ordered database operations, final tables/views/packages/procedures/functions, response, side effects, commit, rollback, and partial-failure behavior;
- one consolidated local operation decision table expanding every applicable operation into ordered atomic conditions, checks, reads, writes, calls, messages, control-flow outcomes, and transaction effects from the operation evidence;
- parent-child save order, cascading or restricted deletes, orphan behavior, and partial-failure handling;
- tab population, lazy loading, refresh, dependency, stale-data, and dirty-state behavior;
- API or service contracts, concurrency, idempotency, audit, security, observability, and performance;
- happy-path and failure acceptance scenarios;
- one consolidated register containing every risk, assumption, open question, conflict, blank/TBD contract cell, and implementation blocker, with severity, affected local keys, likely generated-code impact, safe POC fallback, resolution needed, and status.

Mention stored procedures or functions only when supported by source evidence or an accepted decision. Represent absent physical knowledge as `TBD`; do not fill gaps with plausible names.

## Incremental And Overwrite Reruns

Read the existing matching feature package, implementation specification, review records, trace links, indexes, change logs, and workflow state before drafting any change.

The default mode is `incremental` (`overwrite: false` or omitted):

- inventory the existing local keys and compare them with the newly inspected evidence and mockup;
- merge by stable semantic local key, adding new controls, mappings, rules, operation rows, scenarios, and gaps and enriching incomplete existing rows;
- merge Oracle error mappings by stable `error.*` key and normalized failure signature, enriching first-stage constraint-to-code mappings with message-catalogue text when later evidence supplies it;
- preserve existing supported content, human edits, resolved decisions, filenames, the governed package ID, review history, and baseline metadata;
- do not delete a row or downgrade a resolved decision merely because the current evidence subset does not repeat it;
- when new evidence conflicts with existing content, retain both facts, mark the affected contract `conflict`, and add or update one consolidated gap until a controlled decision resolves it;
- append one semantic change-history entry describing the incremental delta.

`overwrite: true` enables controlled replacement only for the exact matching feature package and implementation specification. In this mode, regenerate their evidence-derived bodies from the complete current source set while preserving the governed package ID, controlled path and filename where possible, provenance, governance metadata, and prior change history. It does not authorize deletion or replacement of unrelated artifacts. It also does not override reviewed, approved, baselined, retired, or locked content; replacing such content still requires explicit controlled migration instructions in Notes.

In either mode, never discard content produced by an earlier skill version without recording why it was superseded. After the merge or replacement, rerun complete coverage and validation against the resulting whole artifacts, not only the newly added rows.

## Readiness Outcomes

Derive and record both outcomes; do not use them as a hard stop for a controlled POC:

- `review_ready`: the package is structurally complete and has no unresolved material gaps;
- `reviewable_with_gaps`: the package is structurally complete and every unresolved point is consolidated for review;
- `not_review_ready`: the package is structurally incomplete or hides unresolved material content;
- `implementation_ready`: no unresolved implementation-impacting gaps remain;
- `implementation_ready_with_known_gaps`: only medium/low gaps remain and their likely code impact and POC fallback are explicit;
- `not_implementation_ready`: at least one unresolved `blocker` or `high` gap can materially omit or corrupt behavior, persistence, security, or transactions.

Code generation posture is `allowed` when implementation-ready and `allowed_with_known_gaps` otherwise. Never label code generation prohibited. For `allowed_with_known_gaps`, state that generated code is POC-only, enumerate likely omissions or defects, and require the implementer to carry the gap keys into its completion report.

Gap severity means:

- `blocker`: a safe or coherent behavior cannot be specified; generated code needs an explicit incomplete/stub path;
- `high`: generated code may implement wrong data, business, transaction, authorization, or destructive behavior;
- `medium`: generated code may omit an edge case, error path, dependency, or non-happy behavior;
- `low`: generated code may differ in minor UX, operational, or non-critical behavior.

An unresolved claim is acceptable only when it is explicit. Every material blank, `TBD`, `conflict`, or `inferred` contract row must reference a local gap key in the single consolidated register. Do not repeat separate open-question and risk registers in the implementation specification.

## Write Canonical Outputs

Determine the controlled taxonomy path from `TAXONOMY.md`, existing feature artifacts, and canonical indexes. Do not invent an ad hoc taxonomy folder. If the feature cannot be placed unambiguously, request clarification before creating canonical files.

Create or update idempotently:

```text
requirements/features/<controlled-taxonomy-path>/<feature_name>.md
architecture/target-to-be/<controlled-taxonomy-path>/<feature_name>-implementation-spec.md
review/findings.md                         # when material findings exist
review/open-decisions.md                   # when decisions are required
traceability/links.jsonl                   # minimal package-level links
traceability/gaps.md                       # when material gaps exist
requirements/index.yaml and index.md       # governed package only
requirements/requirements-change-log.*     # one semantic package change
work/current-workflow.md                   # run state and next action
```

Preserve existing stable IDs, filenames, human edits, review history, trace links, and baseline status. In incremental mode, update matching draft artifacts by semantic merge rather than duplicating or replacing them. In overwrite mode, replace only the matching eligible draft artifacts under the rules above. Never remove or rewrite reviewed, approved, baselined, retired, or locked content without explicit controlled migration instructions. Never mark an artifact approved or baselined.

## Workflow

1. Resolve tenant, project, repository, feature, modules, mockup URL, target project, and `overwrite`; report `incremental` or `overwrite` mode.
2. Read project governance, taxonomy, existing matching artifacts, Notes, and applicable architecture; inventory content that must be preserved.
3. Resolve all module folders and report fuzzy matches.
4. Inventory evidence files, source facts, and every linked screenshot.
5. Inspect every reachable mockup state and locate its implementing code.
6. Build the complete target UI and Oracle inventories.
7. Reconcile modules and create the disposition-based coverage matrix.
8. Trace every applicable operation and build the ordered local operation decision rows; reconcile any evidenced counts with the extracted row counts.
9. Trace every reachable Oracle constraint/application failure through its legacy application code and message-catalogue text; build the local error-translation rows and reconcile coverage counts.
10. Identify conflicts and material gaps before drafting; assign local gap keys and likely generated-code impacts.
11. Select or preserve the governed package ID and semantic local keys.
12. Incrementally merge or explicitly overwrite the feature requirement package according to the selected mode.
13. Incrementally merge or explicitly overwrite the linked implementation specification according to the selected mode.
14. Update only applicable review, traceability, index, change-log, and workflow records.
15. Derive review readiness, implementation readiness, and code-generation posture from the consolidated register.
16. Run deterministic and repository validation against the complete resulting artifacts.
17. Report coverage, mappings, operation-row and error-translation counts, readiness, gaps, changes, and the next workflow action.

## Validation

Resolve the skill directory first, then run its bundled validator:

```powershell
python <skill-directory>\scripts\validate_specification.py `
  --requirement <feature-requirement-path> `
  --implementation <implementation-specification-path> `
  --require-operation-decisions `
  --require-error-translations
```

Also run:

```powershell
git diff --check -- requirements architecture review traceability work
```

The validator distinguishes malformed or internally inconsistent specifications from declared evidence gaps. Structural errors fail validation. Properly registered unresolved gaps produce readiness findings and warnings but do not fail the command, so a controlled POC may continue with `allowed_with_known_gaps`.

Verify where applicable:

- front matter and index YAML parse;
- JSONL files parse one object per line;
- global IDs and local keys are unique;
- taxonomy, source, candidate, decision, requirement, and trace references resolve;
- local Markdown links resolve;
- every target UI element has a coverage disposition;
- every physical mapping has evidence, confidence, and disposition;
- every data control has a complete behavior and physical mapping contract or a linked consolidated gap;
- every action and CRUD operation has applicability, validation, transaction, database object, error, authorization, response, and rollback behavior or a linked consolidated gap;
- every applicable operation has ordered atomic operation-decision rows covering its evidenced predicates, validations, warnings, reads, writes, calls, messages, control flow, and transaction effects; stated check counts reconcile to represented rows or a linked gap;
- every reachable in-scope Oracle constraint/application failure has one error-translation row; known constraint-to-application-code and application-code-to-message stages are preserved separately, and every missing stage is linked to a consolidated gap;
- every verified error-translation row specifies deterministic matching/precedence, responsible target, structured API/UI outcome, transaction/editor behavior, and evidence; a generic fallback is not substituted for a known application code;
- every applicable LOV, tab, parent-child, API, security, and acceptance concern has a contract, or an explicit `not-applicable` rationale, or a linked consolidated gap;
- every implementation-impacting blank, `TBD`, `conflict`, and `inferred` value is represented once in the consolidated gap register;
- declared readiness and code-generation posture match the unresolved gap severities;
- no unsupported physical implementation claim is presented as verified;
- no mockup application code or unrelated project scope changed.

Continue correcting artifacts until all checks pass or a specific evidence or decision blocker remains.

## Completion Report

Report:

- selected tenant, project, repository, feature, mockup URL, and target project directory;
- run mode (`incremental` or explicit `overwrite`) and the existing artifacts preserved, enriched, or replaced;
- requested and resolved modules, including similarity matches;
- evidence files and screenshots inspected;
- UI inventory totals by fields, grids, columns, tabs, dialogs, and actions;
- coverage totals by `verified`, `inferred`, `conflict`, `TBD`, and `not-applicable`;
- physical mapping and CRUD/action coverage;
- operation decision-row totals by parent operation, phase, and decision kind, including any evidence-count mismatch;
- Oracle error-translation totals for failure signatures, application-code mappings, resolved message texts, and gap-linked partial mappings;
- requirement and implementation artifacts created or updated;
- review, traceability, index, and workflow records changed;
- preserved, modified, reimagined, net-new, and retired behavior counts;
- conflicts, assumptions, open questions, evidence gaps, and blockers;
- consolidated gap counts by severity, each gap's likely generated-code impact, and POC fallback;
- `review_readiness`, `implementation_readiness`, and `code_generation_posture`;
- validation commands and results;
- recommended next workflow action.

Do not create commits, tags, pushes, baselines, approvals, deployments, or application-code changes unless explicitly requested by a separate user instruction.
