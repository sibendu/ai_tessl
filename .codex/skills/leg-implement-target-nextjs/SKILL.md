---
name: leg-implement-target-nextjs
description: Implement or incrementally complete a legacy-modernization module in a target Next.js application from a canonical curated feature requirement package and its linked target implementation specification. Use when a reviewed mockup supplies the approved visual UI while curated requirements supply every backend, Oracle, validation, operation, persistence, transaction, error, and security behavior; supports POC generation with explicit known gaps without silently inventing missing behavior.
---

# Implement Target Next.js

## Purpose

Generate a working Next.js module with the smallest practical amount of manual correction. Preserve the approved mockup experience, implement the curated backend contract, verify every in-scope control and operation, and leave one consolidated record of anything that remains incomplete.

This is a downstream implementation skill. It consumes curated requirements; it does not reinterpret raw legacy evidence or change requirements to match convenient code.

## Required inputs

Accept the canonical invocation fields:

```text
Tenant: <tenant-key>
Project: <project-key>
Project repo: <auto-or-path>
feature_name: <feature-key>
module_names: <comma-separated-module-keys>
mockup_url: <running-approved-mockup-url>
project_directory: <target-Next.js-project-path>
mode: implement | assess | continue | static-validate
overwrite: false
Notes: <scope, exclusions, environment facts, and accepted POC gaps>
```

Required for implementation are `feature_name`, `module_names`, `mockup_url`, and `project_directory`. Default `mode` to `implement` and `overwrite` to `false`.

Every run targets exactly one tenant and project. When manual use omits them, use `Tenant: default` and `Project: gala`, state the fallback, and continue only after verifying the resolved repository. Resolve `Project repo: auto` as:

```text
agentic-sdlc-data/tenants/<tenant>/projects/<project>/repo
```

Refuse to guess between multiple feature packages or target implementation specifications. A single package may cover multiple `module_names` when the curated package says so.

## Authority contract

Read [references/authority-and-conformance.md](references/authority-and-conformance.md) before modifying target code. Apply its source precedence and safe-fallback rules throughout the run.

The following split is mandatory:

1. **Mockup authority is visual and client-presentational only.** Use the running mockup and the component that actually serves `mockup_url` for layout, labels, controls, tabs, grids, dialogs, interaction shape, responsive behavior, and styling.
2. **The curated package is behavioral authority.** Use the canonical feature requirement and linked target implementation specification for field semantics, identifiers, types, defaults, LOV values, validations, business rules, action decisions, APIs, Oracle objects, SQL predicates and binds, sequences, persistence order, transactions, errors, authorization, concurrency, and audit behavior.
3. **Existing target code is an implementation baseline, not a requirement source.** Reuse conformant code and revise nonconformant code. Do not let current code override the curated contract.
4. **Raw evidence is provenance, not ordinary implementation input.** Do not reopen Oracle source, operation evidence, screenshots, or extraction-run records to resolve an ambiguity. Record the gap and use the documented fallback. Send missing facts back through curation.

When sources conflict, keep the approved mockup's visual shape and implement the curated backend behavior. Never use mock values, display labels, sample IDs, sample defaults, or in-memory fixtures as persisted business data.

## Modes

- `assess`: inspect and produce the implementation disposition and plan; do not edit target code.
- `implement`: perform an incremental implementation, then verify it.
- `continue`: resume a previous implementation using its ownership manifest and current diff.
- `static-validate`: inspect implemented code against the package without changing it or requiring a running database.

`overwrite: true` is valid only with `mode: implement`. It permits controlled reconstruction of files owned solely by this feature. It does not authorize replacement of unrelated code, shared infrastructure, human changes, environment configuration, canonical requirements, or database objects. Resolve exact ownership before replacing anything.

## Workflow

### 1. Resolve scope and operating rules

1. Read the workspace `AGENTS.md`, `CANONICAL_MODEL.md`, and project `project.yaml`.
2. Read project `TAXONOMY.md` and `ROLES.md` when present.
3. Verify the project repository and `project_directory` exist.
4. Identify local target instructions such as `AGENTS.md`, package-manager configuration, lint/typecheck/test/build commands, architecture conventions, and database access patterns.
5. Inspect Git status. Preserve unrelated and user-authored changes.
6. Translate `Notes` into explicit in-scope, excluded, deferred, and environment-known items. Notes may narrow POC scope but may not silently override curated behavior.

Do not install packages, change framework versions, create database objects, run migrations, deploy, commit, or push unless required by the existing project workflow or explicitly authorized.

### 2. Resolve the canonical implementation contract

Locate exactly one feature package under:

```text
requirements/features/<controlled-taxonomy-path>/<feature_name>.md
```

Follow its link to exactly one specification under `architecture/target-to-be/`. Confirm both carry the same single `governed_package_id`. Internal controls, mappings, operations, gaps, and scenarios remain local keys; do not create new global IDs for them.

Read the complete feature package and complete linked implementation specification. Also read only directly relevant canonical architecture decisions, acceptance tests, review readiness, and consolidated gaps.

Before implementation, run the curation validator when available:

```powershell
python .agent\skills\leg-curate-requirements-oracle\scripts\validate_specification.py `
  --requirement <feature-package> `
  --implementation <implementation-specification> `
  --require-operation-decisions `
  --require-error-translations `
  --json
```

Use `--require-operation-decisions` whenever any operation contract exists. A failing validator is an implementation finding. It blocks only the affected behavior unless it makes safe target ownership or data mutation impossible.

### 3. Resolve the live mockup implementation

Open `mockup_url` and inspect every route state, tab, field, grid, LOV, dialog, message, and in-scope action. Trace the target route and import graph to the component actually rendering that URL. Do not trust a component path merely because it is mentioned in an older artifact.

Reuse or extend the live mockup component when practical. Preserve its presentation and client interaction design. Remove production dependencies on sample data and mock mutation paths as backend integration is introduced.

If the live URL is unavailable, `static-validate` may continue using route/component source. `implement` may continue only when the approved visual structure can be resolved without guessing; record runtime visual verification as pending.

### 4. Build the implementation disposition

Create one working matrix keyed by the governed package and stable local keys. Cover every in-scope:

- control, field, grid column, tab, LOV, dialog, and displayed message;
- every `error.*` Oracle constraint/application-message translation and the unknown-error fallback;
- Search, Add, Edit, Delete, Save, Clear, Cancel, navigation, selection, paging, and other declared operation;
- API, DTO mapping, query, mutation, procedure/function invocation, validation, transaction consequence, authorization check, and acceptance scenario.

Follow `error.*` references from validation, action, operation, API, and acceptance rows back to the single translation catalogue. Treat an unreferenced known mapping or a referenced missing mapping as an implementation coverage defect.

For every writable field and grid column, include the complete value path:

```text
UI label/value -> request DTO -> normalized bind -> Oracle stored value -> allowed physical domain/check constraint
```

Do not mark a mapping `READY_IMPLEMENT` merely because the target column is known. Every selectable/defaultable UI value must terminate in a stored value permitted by the curated column domain, nullability, and check constraints. If the physical domain is known but the display-label mapping is not, use `READY_WITH_POC_FALLBACK` only when the consolidated gap register supplies that exact mapping fallback; otherwise use `READY_EXPLICIT_INCOMPLETE` or `BLOCKED`. Never assume that Yes/No means `Y/N`; Oracle domains such as `A/I`, `P/I`, `0/1`, or nullable codes remain authoritative.

Assign exactly one disposition:

- `READY_IMPLEMENT`: the curated contract is complete enough to implement and verify.
- `READY_WITH_POC_FALLBACK`: a gap exists, but the specification or consolidated gap register defines a safe executable POC fallback.
- `READY_EXPLICIT_INCOMPLETE`: visible behavior can remain disabled, read-only, blank, or explicitly unavailable without corrupting data.
- `EXCLUDED_SCOPE`: Notes or the curated package explicitly exclude it.
- `BLOCKED`: no safe implementation or explicit-incomplete state exists, or destructive target ownership is ambiguous.

`not_implementation_ready` does not by itself stop a POC. Continue when the package allows code generation with known gaps and every affected item has a safe disposition. Never downgrade production readiness or conceal a blocker merely to continue.

### 5. Design the narrow target implementation

Fit the existing project architecture. Prefer one module boundary with the smallest cohesive set of route, presentation, API/service, repository/database, schema, and test files.

Create one explicit boundary mapping between UI state and backend contracts:

```text
approved UI field/local key
  -> request DTO property
  -> domain/service value
  -> Oracle key, column, bind, or procedure parameter
```

Keep UI names close to approved mockup field names when that improves readability, but do not contort backend contracts to eliminate a clear adapter. The adapter must:

- convert display labels to Oracle keys/codes;
- prove every emitted code, default, blank, and null is allowed by the curated physical domain and check constraints;
- submit identifiers required for referential integrity;
- omit mock defaults and presentation-only values;
- keep audit fields server-owned;
- distinguish omitted, null, blank, unchanged, and cleared values as specified;
- preserve untouched legacy values instead of normalizing or defaulting them during an unrelated edit;
- map backend validation and constraint failures to the correct editor, control, or action.

For Edit, prefer a sparse mutation contract based on the loaded baseline and explicit dirty state. Send only changed parent fields and explicitly changed child collections. A child-only Add/Edit/Remove/Reorder must not rewrite unrelated parent columns, audit-owned values, or other child collections. If the target API intentionally uses full replacement, require complete domain validation for every resubmitted value and an explicit curated replacement contract; do not infer full replacement from convenient form serialization.

Never accept client-supplied table names, column names, SQL fragments, unrestricted sort expressions, audit identities, or authorization decisions.

Create one centralized server-side error translator from the specification's `Oracle Constraint And Error Translation` table. Do not distribute constraint-name special cases across repositories, routes, or components. The translator must:

- normalize schema-qualified/unqualified and quoted/case variants without weakening exact constraint matching;
- prefer an exact constraint/application mapping over a generic ORA-class fallback;
- preserve the curated legacy application code even when final catalogue text remains gap-linked;
- return the curated safe message and responsible local target while retaining diagnostic constraint/code data;
- keep unsafe SQL, binds, stack traces, and driver details server-side;
- apply the specified transaction rollback and editor-retention/focus behavior;
- use the curated unknown-error fallback only when no more specific row matches.

Use one compact structured error boundary, normally `code`, `message`, optional normalized `constraint`, and optional local `target`. Add fields only when the curated contract requires them. Do not manufacture legacy message text for a known code whose catalogue entry is unresolved.

### 6. Implement controls and read behavior

For each control contract, implement its type, label, requiredness, editability, visibility, default, allowed values, LOV query/return value, dependencies, clear/reset behavior, normalization, validation timing, error location, and backend mapping.

Implement search, filters, paging, selection, detail loading, tab loading, parent-child grids, empty states, and errors from the specification. Do not derive product or entity identity from display text. A selected LOV must retain and send the specified key even when the UI displays a label.

### 7. Implement every operation decision table

Treat each operation's local decision table as executable control flow. This applies to Delete, Add, Edit, Save, copy, approve, launch, and any other discovered operation.

For every row, preserve:

- ordering and stop/continue behavior;
- condition, database predicate, binds, and dependent Oracle objects;
- hard-block versus warning-confirmation semantics;
- exact or mapped message and its display location;
- first-request and confirmed-request behavior;
- mutation/procedure/function call and returned values;
- parent-child, cascade, and restrict consequences;
- commit, rollback, retry, concurrency, and exception behavior.

Do not collapse multiple checks into a generic validation when ordering, message selection, database reads, or confirmation behavior would change. Do not explicitly delete children governed by an authoritative database cascade. Do not treat a bare client confirmation flag as sufficient when the specification requires a server-verifiable proof or recheck.

### 8. Implement persistence and errors

Use only specified tables, views, sequences, packages, procedures, functions, predicates, and binds. Generate keys and populate foreign keys in the documented order. Keep a multi-step logical save/delete in the required transaction boundary.

Apply mutation scope deliberately:

- track the loaded baseline or equivalent dirty-field state for Edit;
- distinguish parent changes from each child-collection change;
- omit unchanged values from PATCH-like updates;
- do not issue a parent `UPDATE` for a child-only mutation;
- do not replace or delete an unchanged child collection merely because it was omitted from the request;
- preserve the specification's distinction between omitted, null, blank, unchanged, and explicitly cleared values.

Before executing a write, verify each bound value against every curated physical domain and check constraint for its target column. Do this at the final stored-value boundary, after label/key/code conversion—not only against the UI option list. Unknown nonblank values fail closed. Missing label-to-code mappings remain gaps and must not be solved by a generic Yes/No helper.

The server must not report success before commit. On failure, roll back as specified, retain usable editor state, surface a safe actionable error, and preserve the authoritative Oracle message/code when the contract requires it. Never silently accept an unsupported field or silently discard a requested mutation.

Map known Oracle constraints to the responsible local control/action and an actionable curated message when that mapping exists. Retain the Oracle constraint/code for diagnosis. A generic constraint message is acceptable only under the documented error-mapping gap fallback; it does not replace control-level validation for known constraints.

Implement every curated `error.*` mapping, including mappings known only through raw-database failure handling rather than pre-DML validation. Pre-DML checks improve usability but do not replace database enforcement or the translator. If the specification preserves a known constraint-to-application-code mapping while its final catalogue text is `TBD`, return that known code with only the explicit gap fallback text; never degrade it to `Database constraint violated: <name>` alone.

Where database connectivity is unavailable, isolate the database boundary so static and unit verification can proceed. Do not introduce a fake success path into production code. Clearly mark database integration verification as pending.

### 9. Test and verify

Derive implementation tests from the feature package, implementation tables, and canonical acceptance artifacts. Do not invent behavior in tests. At minimum verify:

- every field and control mapping, including required/blank/null/default cases;
- every UI option and adapter default produces a stored value permitted by the target column's curated domain/check constraints;
- unknown nonblank labels/codes fail closed while untouched legacy values survive unrelated edits;
- LOV label/key handling and dependent-control resets;
- Add/Edit persistence, generated keys, and parent-child relationships;
- parent-only, child-only, and combined mutations issue only the intended DML; specifically assert that a child-only Add/Edit/Remove/Reorder performs no unrelated parent update;
- omitting a child collection preserves it, while explicitly submitting an empty changed collection applies the specified remove-all behavior;
- every operation decision branch, with check order, blocking messages, warnings, confirmation, and final mutation;
- rollback and backend-error propagation into the active editor/dialog;
- known database constraints are attributed to the responsible control/action and keep the editor open;
- every curated error-translation row matches schema-qualified and unqualified driver forms, returns the specified application code/message/target, and applies its rollback/editor behavior;
- the generic unknown-error path is used only for unmapped failures, does not leak SQL/binds/stacks, and never shadows an exact constraint mapping;
- search/filter/paging/selection/tab state and no-results behavior;
- authorization and concurrency behavior where specified;
- excluded or explicitly incomplete POC controls cannot mutate data.

Run the repository-supported sequence, normally `lint`, `typecheck`, focused tests, broader tests, and `build`. Use browser verification against `mockup_url` or the implemented route for every in-scope tab, dialog, and action. Run database integration tests only when safe connectivity and test data are available.

Never claim browser, database, or production readiness for checks that were not run.

### 10. Record the result

Maintain one implementation ownership and coverage manifest at:

```text
<project_directory>/.agentic-sdlc/implementations/<feature_name>.json
```

Keep it compact and machine-readable. Include:

- `governed_package_id`, feature and module keys;
- source requirement/specification paths and content hashes;
- mockup URL and resolved route/component paths;
- implementation mode and timestamp;
- owned files and narrowly edited shared files;
- local-key coverage with disposition and test references;
- error-translation coverage for every curated `error.*` row, including fallback and unresolved-message dispositions;
- validation commands and outcomes;
- consolidated unresolved gap keys and code impact;
- overall result: `production_ready`, `poc_ready_with_known_gaps`, `explicitly_incomplete`, or `blocked`.

On incremental runs, read this manifest and the current code/diff first. Preserve stable local-key mappings and already conformant code. Update only affected coverage. `overwrite: false` is merge-and-improve, never blind append or full regeneration.

If project governance expects a run record, write one concise link-oriented record under `work/` or `review/`; do not duplicate the full specification or create a global artifact per control, decision row, gap, file, or test.

## Completion standard

Report the outcome first, followed by:

1. implemented features and operations;
2. validation actually run and results;
3. unresolved gaps grouped once by severity, with exact code impact and fallback;
4. absolute implementation blockers, if any;
5. files changed and the ownership manifest path.

Call the module `production_ready` only when all in-scope local keys are implemented, all blocker/high implementation gaps are resolved, database behavior is integration-tested, and required browser/build/test validation passes. A POC can be complete for its declared scope while remaining `poc_ready_with_known_gaps`.

Do not modify curated requirements, mark open questions resolved, or upgrade readiness based solely on generated code. Route newly discovered requirement defects back to curation with the existing local gap key or one proposed local key.
