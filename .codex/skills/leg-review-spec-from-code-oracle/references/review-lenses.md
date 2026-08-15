# Semantic Review Lenses

Apply every lens to the linked package. Record a finding only when the relationship is material, surprising, conflicting, under-specified, or important for later curation.

## 1. Identity And Retrieval Scope

- Compare the form title, module identity, menu purpose, first navigation block, startup mode, block `WhereClause`, query triggers, and global parameters.
- Flag filters that admit domain types or states not explained by the screen identity.
- Distinguish directly observed filter behavior from the unknown business reason for that behavior.

Example: a Standard Contract form normally filters `CTT_TYPE = 'S'` but admits `N/U` during auto-query. Preserve both facts, examine assignments and callers of the startup global, and leave intent open if caller context is missing.

## 2. UI Structure And Persistence

- Compare each visible and hidden Forms item with `DatabaseItem`, `ColumnName`, block data source, DML target, DDL type, default, nullability, and constraints.
- Flag visible values without established persistence, database items without physical mappings, mirror/display items whose source is unclear, and typed conflicts.
- Do not infer a column from an item name.

## 3. CRUD And Runtime Restrictions

- Compare block and item design-time query/insert/update/delete flags with property overrides, triggers, validation, navigation, and effective runtime evidence.
- Flag a declared capability that decoded code disables or conditions, and a runtime operation absent from design-time declarations.
- Preserve unknown inherited or binary-library behavior as a gap.

## 4. Condition, Message, Stop, And Outcome

- Verify that each message associated with a business condition is inside the active decoded branch or has equally explicit control-flow evidence.
- Compare message severity with stop effects, raises, navigation, rollback, and continuing execution.
- Flag reused catalog messages whose business meaning differs by context, unbound messages, and conditions with unexplained outcomes.

## 5. Master-Detail And Delete Consequences

- Compare Forms relations, delete triggers, explicit dependency checks, inbound foreign keys, `ON DELETE` behavior, cascades, and manual child deletion.
- Flag database-enforced consequences not surfaced by Forms behavior and Forms warnings not supported by supplied DDL.
- Do not claim runtime delete safety when referenced DDL or called routines are missing.

## 6. Transaction Ownership

- Compare save, commit, rollback, clear-form, exception, and exit behavior across reachable paths.
- Identify whether the form, a framework library, a called form, or the database owns the boundary.
- Flag partial work, swallowed exceptions, or unknown commit ownership without inventing the runtime contract.

## 7. Navigation And Runtime Context

- Compare buttons and navigation routines with target forms, parameter lists, startup globals, menu declarations, callers, and return context.
- Flag behavior whose meaning depends on missing menus, object libraries, PLLs, FMX files, or called modules.
- Treat binary-only components as boundaries, not decoded evidence.

## 8. Defaults, Derivations, And Audit Ownership

- Compare Forms initial values and assignments with DDL defaults, database triggers, required columns, and audit columns.
- Flag conflicting defaults and required values whose owner is not established.
- Distinguish a displayed derivation from a persisted value.

## 9. DDL And Dynamic SQL

- Compare direct SQL, dynamic SQL fragments, synonyms, views, sequences, procedures, triggers, and dependencies.
- Flag object-name ambiguity, unresolved schema/synonym resolution, and dynamic SQL whose assembled predicate or target is incomplete.
- Prefer the exact decoded source and complete DDL child over summary wording.

## 10. Screenshot And Structural Evidence

- Use screenshots to corroborate visible grouping, labels, regions, and tab presentation.
- Flag a material screenshot/XML mismatch without allowing the screenshot to override Forms or PL/SQL behavior.
- Treat identical hashes under different filenames as duplicate provenance, not additional runtime states.

## 11. Coverage And Confidence Interactions

- Determine whether several individually minor gaps combine into a material semantic uncertainty.
- Reassess confidence when a conclusion crosses readable Forms, missing library behavior, and unresolved DDL.
- Do not downgrade directly established facts merely because adjacent intent is unknown.

## 12. Historical Ambiguity Continuity

- Use earlier specifications to recover useful questions, not answers.
- Confirm each underlying fact in the current package.
- Register an ambiguity when current facts still support the cross-fact tension even if the old wording is absent.
- Exclude POC assumptions, target web behavior, target requirements, and implementation proposals.

## Resolution Test

Before setting `resolved_automatically`, ask:

1. Can every premise be cited in the current package?
2. Is the conclusion the only source-consistent interpretation?
3. Does it avoid business intent and target design?
4. Would another reviewer reproduce it without unstated domain knowledge?

If any answer is no, propose a resolution and leave it for human review or missing-evidence acquisition.
