# Authority and conformance rules

Read this reference before assessing or changing a target implementation.

## Source precedence

| Concern | Authority | Supporting input | Never use as authority |
|---|---|---|---|
| Visual layout, labels, control presence, tabs, grids, dialogs, responsive presentation | Running approved mockup and its live route/component | Curated UI inventory | Sample records or legacy database naming |
| Client interaction shape | Running approved mockup, unless the curated package explicitly replaces it | Curated control/action contract | Convenient behavior already present in unrelated code |
| Field meaning, type, requiredness, defaults, dependencies, normalization | Curated feature package and target implementation specification | Canonical acceptance artifacts | Mock values or HTML control defaults |
| Entity identity and LOV stored values | Target implementation specification | Oracle mappings recorded by curation | Display labels, array positions, sample IDs |
| Validation, business rules, messages, and operation order | Requirement/action contracts and operation decision tables | Canonical acceptance artifacts | Generic framework validation or raw evidence reinterpretation |
| Oracle constraint and application-error translation | `Oracle Constraint And Error Translation` in the target implementation specification | Curated validation/action contracts | One-off constraint special cases, guessed legacy text, or raw exception strings |
| Tables, views, sequences, procedures, functions, predicates, and binds | Target implementation specification | Approved architecture decisions | Guessed Oracle names, dynamic client input, mock API shapes |
| Parent-child persistence, transactions, cascade/restrict, rollback | Target implementation specification | Approved architecture decisions | UI component behavior or ORM defaults |
| Authorization, audit, concurrency, error propagation | Target implementation specification | Project security architecture | Client assertions or mock user data |
| Code structure and reusable components | Existing target repository conventions | Framework documentation | Legacy source structure as a mandatory target design |

The mockup is never backend authority. The curated specification is never a styling license to redesign the approved mockup.

## Conflict handling

| Conflict | Required handling |
|---|---|
| Mockup shows a label while specification stores a key | Display the label; retain and submit the specified key through the adapter. |
| Mockup label and physical Oracle domain are known but their mapping is not | Keep the visual label, record the mapping gap, and use only an explicitly curated POC fallback. Otherwise disable/preserve the field; never assume Yes/No implies `Y/N`. |
| Mockup contains sample/default data absent from specification | Render no production default. Load or derive only specified data. |
| Mockup exposes a field with no supported backend mapping | Keep the approved visual control, but use the consolidated gap fallback: disabled/read-only/blank/explicitly unavailable. Never silently persist or discard it. |
| Existing API names differ from UI field names | Use one explicit DTO/adapter mapping. Prefer readable alignment, not false equivalence. |
| Existing code behavior conflicts with an operation decision row | Change the code; preserve the decision row's ordering, condition, message, and consequence. |
| Raw evidence appears to contradict the curated package | Do not adjudicate inside implementation. Record the conflict against a local gap key and send it to curation. |
| A stale artifact points to the wrong mockup component | Resolve the live route/import graph and record the locator discrepancy; do not change backend meaning. |

## Safe POC fallback rules

A POC may proceed with known gaps only when the affected behavior has one of these safe outcomes:

| Gap type | Allowed POC behavior |
|---|---|
| Database is unavailable but physical contract is specified | Implement the real repository boundary and tests around it; mark integration unverified. Never return fake production success. |
| Optional read-only enrichment is unknown | Show blank/unavailable with an explicit state and gap trace. |
| Mutation for a visible control is unknown | Disable the mutation or control and identify why. |
| Physical domain is known but label-to-stored-value mapping is unknown | Preserve the untouched legacy value and omit it from unrelated updates; make direct editing explicitly incomplete unless the consolidated gap supplies a safe mapping. |
| Launcher or secondary action is explicitly excluded by Notes | Render consistently with approved scope, disabled or absent as Notes require; record `EXCLUDED_SCOPE`. |
| Exact error mapping is incomplete but mutation is otherwise safe | Fail closed, retain editor state, show a safe generic error, log/retain the backend code, and trace the gap. |
| Constraint-to-application-code mapping is known but final catalogue text is missing | Return the known application code and only the curated safe fallback text; retain the normalized constraint and target. Do not show only the raw constraint or invent legacy wording. |
| Authorization is unknown for a mutation | Deny or disable; never default-allow. |
| Transaction, key generation, referential identity, destructive predicate, or confirmation semantics are unknown | `BLOCKED` for that mutation unless the curated gap register supplies a safe explicit-incomplete behavior. |

No fallback may fabricate a database object, key, sequence, validation result, successful commit, user identity, or authorization decision.

## Conformance failures to search for

Before completion, search the production path for:

- mock imports, hard-coded sample records, in-memory mutations, and fake success responses;
- display labels sent where Oracle keys/codes are required;
- adapter outputs not proven against the target column domain, nullability, and check constraints;
- generic Yes/No conversion applied to columns whose physical domain is not `Y/N`;
- client-owned created/updated user or timestamp values;
- client-supplied SQL identifiers or fragments;
- mutation success returned before commit;
- swallowed database errors or dialogs that close on failure;
- generic Delete/Add/Edit validation that bypasses ordered decision rows;
- child deletes that duplicate authoritative `ON DELETE CASCADE` behavior;
- destructive operations authorized by an unverified client confirmation alone;
- fields accepted by the API but neither persisted nor explicitly rejected;
- full-form updates that rewrite unchanged parent fields during child-only changes;
- omitted child collections collapsed into explicit empty collections, or explicit empty changed collections treated as omitted;
- unrelated edits that normalize or default untouched legacy values;
- known constraint failures returned without attribution to the responsible control/action;
- exact constraint mappings shadowed by a generic ORA/constraint fallback, or implemented as scattered one-off branches instead of the centralized curated translator;
- known legacy application codes discarded merely because their final message-catalogue text is unresolved;
- defaults copied from the mockup instead of derived from requirements;
- requirements or acceptance tests edited merely to match generated code.

Each surviving instance must be resolved or tied to one consolidated local gap and a safe disposition.
