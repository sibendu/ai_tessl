# Module Archetype Detection And Analysis Lenses

## Principle

Run the common inventory, structural extraction, reachability, gap, and completeness passes for every module. Archetypes add conditional depth; they never remove common checks. Classification is multi-label because one Forms module may be both CRUD-heavy and workflow-driven.

## Detection Output

Emit:

```json
{
  "module_id": "<MODULE>",
  "archetypes": [
    {
      "name": "crud_master_detail",
      "score": 0.92,
      "confidence": "high",
      "signals": [
        {"signal": "database_blocks_with_write_crud", "value": 4, "locators": []}
      ],
      "required_lenses": ["effective_crud", "master_detail", "persistence", "delete_dependency"]
    }
  ],
  "unclassified_signals": [],
  "manual_review_required": false
}
```

Scores rank attention; they do not prove behavior. Use `high` confidence only when multiple independent structural or reachable-logic signals agree. Apply every archetype at or above the configured threshold. If no archetype meets it, classify as `unknown_or_hybrid` and run all operation lenses indicated by reachable entry points.

## Common Signals

Use deterministic counts and raw locators for:

- database and control blocks, master-detail relations, CRUD properties, row counts, and commit/delete triggers;
- button/menu/action triggers and called modules;
- state/status fields, transition routines, approvals, routing, notifications, timers, and record locking;
- formula density, branch density, validation units, lookup/rate tables, and numeric/date derivations;
- query-only blocks, dynamic query construction, reports, aggregates, grouping, exports, and parameter forms;
- host/file/WebUtil calls, database packages, external program units, queues, batch controls, retry/checkpoint logic, and interface tables.

Do not use filenames or screen titles as the sole signal.

## CRUD / Master-Detail Lens

### Detection Signals

- one or more database blocks with insert, update, or delete enabled;
- master-detail relations or coordinated header/child blocks;
- `PRE/POST-INSERT`, `PRE/POST-UPDATE`, `PRE/ON/POST-DELETE`, validation, commit, sequence, or row-lock behavior;
- dependency-check routines, uniqueness checks, audit fields, or database cascades.

### Mandatory Analysis

- effective CRUD at region, block, item, column, and record-state level;
- full Add/Edit/Delete/Save ledgers with fields and tables affected;
- master-detail synchronization and atomicity;
- identity generation, defaults, audit ownership, validation ordering, optimistic/pessimistic locking, lost-update handling;
- hard blockers, warnings/confirmations, cascades, trigger side effects, and rollback behavior;
- PK/UK/FK/check constraints and application-versus-database enforcement;
- immutable keys and add/delete-only child collections.

### Additional Readiness Condition

Do not summarize an update as “header only” until every updateable item is mapped to a visual region and physical target or explicitly gapped.

## Workflow / Stateful Lens

### Detection Signals

- status/state columns, status-specific enablement, approval/submit/reject/reopen actions;
- transition routines, role/authority checks, routing, work queues, notifications, timers, or escalations;
- branch-heavy action logic keyed by current state.

### Mandatory Analysis

- state catalogue with initial, terminal, exceptional, and unknown states;
- transition matrix with trigger, prior state, resulting legacy state, guards, authorization evidence, validation, writes, messages, and side effects;
- invalid-transition and re-entry behavior;
- transaction/locking boundary across transition effects;
- scheduled/timer and external notification outcomes;
- recovery behavior after partial failure.

### Additional Readiness Condition

Every reachable transition must be represented or gapped. A CRUD update to a status field does not by itself explain the workflow.

## Calculation / Business-Rules Lens

### Detection Signals

- formula program units, extensive validation branches, rates/percentages, date-effective lookups, thresholds, scoring, classification, or allocation logic;
- derived non-database items or write-back calculations;
- repeated condition/code/message combinations.

### Mandatory Analysis

- decision tables with precedence and short-circuit behavior;
- formulas with input sources, null handling, datatype/rounding/precision, units/currency, date-effective selection, and output destinations;
- defaults versus recalculation triggers;
- boundary, exception, and override paths;
- lookup/reference tables and missing-period behavior;
- message and audit consequences of rule failure.

### Additional Readiness Condition

Every formula operand and lookup dependency must have provenance. Similar item names are insufficient evidence for a calculation.

## Query / Report Lens

### Detection Signals

- query-only database blocks, `EXECUTE_QUERY`, dynamic `DEFAULT_WHERE`/`ORDER_BY`, parameter forms, report calls, aggregates, grouping, or exports;
- significant `PRE-QUERY`/`POST-QUERY` enrichment;
- temporary/report tables or cursor-heavy routines.

### Mandatory Analysis

- input parameters, defaults, validation, query construction, bind variables, joins, optional predicates, and ordering;
- row identity, pagination implications, post-query derivations, null display, and selection behavior;
- aggregate/grouping/formula definitions and reconciliation totals;
- report destination, format, parameters, security-sensitive filters, and no-data/error behavior;
- export columns, encoding, delimiters, filenames, and volume limits when present.

### Additional Readiness Condition

Dynamic SQL fragments and post-query enrichment must be dispositioned before claiming the report/query logic is complete.

## Integration / File / Batch Lens

### Detection Signals

- file-system, host, WebUtil/OLE, FTP, HTTP, email, queue, external program, or database package calls;
- interface/staging tables, batch IDs, commit loops, timers, checkpoints, retry counters, or control totals;
- import/export buttons or unattended parameters.

### Mandatory Analysis

- endpoint/program/package/file contract and ownership;
- field layout, encoding, separators, headers/trailers, control totals, filenames, locations, credentials indirection, and retention evidence;
- invocation mode, schedule, batching, idempotency, checkpointing, retry, timeout, duplicate detection, and restart behavior;
- transaction boundary and partial-success recovery;
- acknowledgements, status updates, reconciliation, messages, logs, and operational dependencies;
- security and sensitive-data handling evidenced by source.

### Additional Readiness Condition

An unresolved external call affecting data or workflow is a material evidence gap and must identify the affected operations and observable boundary.

## Navigation / Orchestration Lens

Apply as a secondary lens when the form mainly launches forms, reports, or contextual actions.

Analyze launch conditions, parameters, shared context/global variables, return/refresh behavior, unsaved-change handling, unavailable-child behavior, and whether the called module changes current records. Missing called modules become exact gaps; target-scope disposition belongs to later curation.

## Lens Re-evaluation On Incremental Runs

Added or changed source may alter archetype classification. Recompute signal counts for the affected module. When a new archetype crosses the analysis threshold, run its full lens and expand the affected slice; do not patch only the newly discovered routine. When an archetype falls below the threshold because source was removed, retain prior findings as invalidated history and reopen relevant gaps.

Archetype choice, signal locators, thresholds, and omitted lenses must be recorded in coverage output so an auditor can reproduce the decision.
