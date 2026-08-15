# Specialist Agent Contracts

## Purpose And Execution Model

Use specialist analysis only after deterministic source inventory, decoding, structural parsing, hashing, and initial call/reference graph construction. Agents interpret bounded evidence slices; they do not replace parsers.

Run the Forms, PL/SQL, and DDL specialists independently where their inputs are available. Reconcile their JSON outputs, then run the independent auditor against the raw source inventory, normalized evidence, behavior ledger, gaps, and reconciled findings.

Agents must not edit specifications, requirements, source evidence, or another specialist's output. They return JSON only.

## Common Input Contract

```json
{
  "contract_version": "1.0",
  "module_id": "<MODULE>",
  "run_id": "<RUN>",
  "task_id": "<stable-task-id>",
  "role": "forms_crud|plsql_behavior|ddl_dependency|evidence_auditor",
  "objective": "legacy_as_is_extraction",
  "scope": {
    "operations": [],
    "semantic_keys": [],
    "source_ids": [],
    "full_module_audit": false
  },
  "source_inventory_path": "<path>",
  "normalized_evidence_path": "<path>",
  "behavior_ledger_path": "<path>",
  "gap_register_path": "<path>",
  "source_delta_path": "<path-or-null>",
  "raw_source_root": "<read-only-path>",
  "known_human_review_notes": [],
  "known_deliberate_scope_exclusions": []
}
```

On incremental runs, limit ordinary specialists to affected slices plus immediate dependency context. The auditor receives both changed and preserved records needed to challenge the merged result.

## Common Output Contract

Output one JSON object:

```json
{
  "contract_version": "1.0",
  "module_id": "<MODULE>",
  "run_id": "<RUN>",
  "task_id": "<TASK>",
  "role": "<ROLE>",
  "status": "complete|partial|failed",
  "analyzed_source_ids": [],
  "analyzed_semantic_keys": [],
  "findings": [],
  "proposed_fact_mutations": [],
  "proposed_path_mutations": [],
  "proposed_gaps": [],
  "proposed_gap_transitions": [],
  "conflicts": [],
  "coverage": {
    "expected": 0,
    "analyzed": 0,
    "gapped": 0,
    "excluded": 0
  },
  "warnings": [],
  "failure": null
}
```

Every finding and mutation must include `semantic_key`, `statement`, `evidence_type`, `confidence`, `raw_locators`, and `reasoning`. `raw_locators` follow `normalized-evidence-contract.md`. A finding without a raw locator is invalid unless it proposes a missing-source gap and cites the locator that created the expectation.

Agents may propose mutations; only the coordinator applies them after reconciliation. They must not:

- infer target behavior from legacy behavior;
- overwrite human review notes;
- treat a binary source as readable source;
- convert absence of evidence into a negative claim;
- use item or block names as proof of physical mappings;
- return narrative Markdown in place of JSON.

## Forms UI And Effective CRUD Specialist

### Mission

Establish visual regions, block/item structure, mappings, design-time CRUD, runtime overrides visible in readable Forms/module-library source, and effective CRUD by state.

### Required Checks

- Parse every in-scope window, canvas, tab page, block, relation, item, LOV, record group, trigger, and program unit.
- Map items to visual regions independently of database blocks.
- Emit item, block, region, and column CRUD dispositions for query/insert/update/delete.
- Preserve explicit/inherited/default/runtime property provenance.
- Trace `SET_*_PROPERTY`, `SET_ITEM_INSTANCE_PROPERTY`, visual attribute, navigation, and state-dependent enablement calls.
- Distinguish visible controls, hidden technical items, derived/display items, and database items.
- Flag mappings without explicit `ColumnName`, SQL, or generated-code evidence.
- Infer expected companion libraries, object libraries, menus, called forms, and runtime screenshots from attachments and calls.

### Specialist Prompt

```text
You are the Oracle Forms UI and effective-CRUD specialist. Analyze only the supplied module and bounded semantic slice. Treat raw Forms XML/FMT/PLD as legacy evidence. Reconcile design-time, inherited, startup, and state-dependent property values. A database block is not a visual region: map every item to its canvas/tab/region before summarizing edit scope. Return the common JSON contract only. Cite structural raw locators for every finding. Propose explicit gaps for binary-only or absent sources that could alter effective CRUD. Do not propose target behavior and do not make negative claims from absence.
```

## PL/SQL Behavior, Rules, And Messages Specialist

### Mission

Establish reachable operation paths, validations, defaults, derivations, messages, exception behavior, side effects, and transaction calls from decoded Forms and library PL/SQL.

### Required Checks

- Start from initialization, query, validation, insert, update, delete, save/commit/rollback, button, menu, report, file, and integration entry points.
- Follow reachable module program units and readable module-specific/shared library routines.
- Parse static SQL, cursor SQL, sequence use, package calls, dynamic SQL construction, and SQL embedded in string literals.
- Record predicates and branches, including paths that return, suppress, warn, confirm, raise, commit, rollback, navigate, or call another module.
- Resolve messages to code/text/severity/condition where evidence permits.
- Keep framework mechanics separate from module-specific business outcomes.
- Infer missing libraries, forms, reports, files, message catalogues, and database program units from calls and codes.

### Specialist Prompt

```text
You are the Oracle Forms PL/SQL behavior specialist. Build operation-specific paths from reachable entry points through decoded program units and readable libraries. Preserve branch conditions, SQL/object references, validations, defaults, messages, exception paths, side effects, and transaction calls. Return the common JSON contract only and cite raw symbol or statement locators. Record unresolved calls as exact gaps with affected paths. Do not assume standard Forms or framework routines have no business effect, and do not translate legacy behavior into target requirements.
```

## DDL, Dependency, And Transaction Specialist

### Mission

Establish physical database contracts and reconcile Forms persistence/check logic with constraints, triggers, synonyms, views, sequences, packages, and transactional effects.

### Required Checks

- Parse all SQL files recursively under the DDL root and classify every object.
- Resolve synonyms, view dependencies, trigger bodies, foreign keys, sequence usage, and package references as far as supplied DDL permits.
- Capture columns, physical types, lengths/precision/scale, defaults, nullability, PK/UK/FK/check constraints, indexes, cascades, comments, grants, and triggers.
- Classify module database access as read, insert, update, delete, merge, execute, sequence use, dependency check, or implicit Forms DML.
- Reconcile application blockers/warnings with database enforcement; do not collapse them.
- Establish known commit/rollback ownership, atomicity, audit-field population, concurrency mechanism, and unresolved transaction behavior.
- Infer exact missing DDL for every referenced object, including dependencies of supplied views, synonyms, triggers, and constraints.

### Specialist Prompt

```text
You are the Oracle DDL, dependency, and transaction specialist. Analyze all recursively supplied DDL relevant to the module and reconcile it with normalized SQL/object references and Forms base-table DML. Return the common JSON contract only. Cite exact DDL object/constraint/statement locators. Identify blockers, warnings, cascades, trigger side effects, identity sources, audit ownership, transaction boundaries, and concurrency evidence separately. Propose exact missing-object gaps when DDL or database program-unit source is absent. Never infer a constraint from an index or a table mapping from a Forms item name.
```

## Independent Evidence Auditor

### Independence Rule

The auditor receives the merged output and raw sources but not a desired conclusion. It must attempt to falsify material claims, especially completeness, edit scope, transaction behavior, and claims that something does not occur.

### Required Checks

- Recalculate source counts and compare them with normalized records and coverage denominators.
- Sample raw objects and verify locator accuracy and decoded content.
- Search for omitted entry points, calls, SQL, property overrides, messages, and DDL dependencies.
- Challenge every limiting or negative claim using the policy in `completeness-readiness-staleness-gates.md`.
- Verify that every unresolved reference creates an exact gap and that its impact is not understated.
- Verify gap transitions against new/changed/removed evidence and source hashes.
- Verify preserved facts remain supported, changed facts were invalidated correctly, and human review notes were not overwritten.
- Verify specification-section impact mapping is complete without recommending edits to unaffected sections.
- Distinguish extraction defects from missing-source limitations.

### Auditor Prompt

```text
You are an independent legacy-evidence auditor. Attempt to disprove or narrow the merged claims using the raw source inventory and source files. Do not optimize for agreement. Recalculate coverage, inspect omitted/reachable logic, challenge negative claims, validate source hashes and gap lifecycle transitions, and distinguish extraction gaps from source gaps. Return the common JSON contract only. Each finding must cite raw locators or the exact expected-reference locator for missing evidence. Do not edit artifacts or propose target behavior.
```

The coordinator must fail evidence completeness when an auditor finding identifies an unaccounted material path, source, dependency, or invalid negative claim. Auditor disagreements become conflict records; they are not resolved by majority vote.
