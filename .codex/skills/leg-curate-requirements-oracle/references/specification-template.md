# Oracle Modernization Specification Templates

Use these templates with the authority, identifier, taxonomy, incremental/overwrite, and rerun rules in the parent skill. On an incremental run, merge stable local-key rows into the existing artifact and retain supported content; do not recreate the template over the existing file. Remove unused optional sections only when the coverage matrix proves they are not applicable.

## Feature Requirement Package

```markdown
---
id: FEAT-<DOMAIN>-<NNN>
artifact_type: feature
title: <Feature title>
status: draft-curated
taxonomy_path: <Controlled taxonomy path>
taxonomy_node_id: <Existing taxonomy node or TBD>
origin_type: legacy_modified
change_intent: improve
origin_classification_scope: package-default-with-local-overrides
source_ids:
  - <Source ID>
candidate_ids:
  - <Candidate ID>
architecture_decision_ids: []
implementation_specification: <relative-link-to-implementation-spec>
validation_status: validation_required
local_key_scheme: "FEAT-<DOMAIN>-<NNN>#<local-key>"
last_updated: YYYY-MM-DD
---

# <Feature Title>

## Purpose And Authority

<Purpose, evidence posture, target intent, and authority limits.>

## Scope And Applicability

| Local key | Requirement | Actors/conditions | Origin and intent | Status |
| --- | --- | --- | --- | --- |
| `scope.applicability` | <Testable scope statement> | <Actor/condition> | <origin>/<intent> | <status> |

## Target Workflow

| Local key | Trigger/state | Required behavior | Outcome |
| --- | --- | --- | --- |
| `workflow.search` | <Trigger> | <Behavior> | <Outcome> |

## Local Requirements

| Local key | Requirement | Missing-data/configuration behavior | Validation status |
| --- | --- | --- | --- |
| `input.example` | <Logical requirement> | <Explicit behavior> | <status> |

## Business Rules And Exceptions

| Local key | Trigger/condition | Rule | Outcome/error |
| --- | --- | --- | --- |
| `rule.example` | <Condition> | <Deterministic rule> | <Outcome> |

## Origin And Target Differences

| Local key or area | Legacy behavior | Target behavior | Origin type | Change intent | Rationale/decision |
| --- | --- | --- | --- | --- | --- |
| `workflow.search` | <Legacy> | <Target> | <origin> | <intent> | <Evidence or decision> |

## Acceptance Criteria

1. `<local-key>`: <Testable outcome.>
2. `<local-key>`: <Failure or missing-configuration outcome.>

## Assumptions Register

| Label | Assumption | Affected local keys | Status | Validation owner/source |
| --- | --- | --- | --- | --- |
| `A1` | <Assumption> | `<local-key>` | validation-required | <Owner/source or TBD> |

## Open Questions Register

| Label | Question | Affected local keys | Downstream effect | Required decision/evidence |
| --- | --- | --- | --- | --- |
| `Q1` | <Question> | `<local-key>` | <Effect> | <Need> |

## Evidence Coverage

| Evidence source/locator | Covered local keys | Confidence | Notes |
| --- | --- | --- | --- |
| `<path>#<locator>` | `<local-key>` | high/medium/low | <Notes> |

## Change History

| Date | Change | Evidence/decision | Notes |
| --- | --- | --- | --- |
| YYYY-MM-DD | Created/updated | <Reference> | <Semantic package change> |
```

Use the predominant package-level `origin_type` and `change_intent`. Preserve meaningful local differences in the Origin And Target Differences table.

## Target Implementation Specification

```markdown
---
artifact_type: target_implementation_specification
title: <Feature Title> Target Implementation Specification
status: draft
governed_package_id: FEAT-<DOMAIN>-<NNN>
review_readiness: reviewable_with_gaps
implementation_readiness: not_implementation_ready
code_generation_posture: allowed_with_known_gaps
source_ids:
  - <Source ID>
architecture_decision_ids: []
mockup_url: <URL>
target_project: <absolute or repository-relative path>
resolved_oracle_modules:
  - <module>
last_updated: YYYY-MM-DD
---

# <Feature Title> Target Implementation Specification

## Purpose And Scope

<Implementation boundary, included flows, excluded flows, and authority posture.>

## Source Authority And Evidence

| Source | Responsibility | Locator/version | Limitations |
| --- | --- | --- | --- |
| <Source> | <What it governs> | <Exact locator> | <Limitations> |

## Target UI Contract

Create one concise row for every visible control and material state in the reviewed mockup. `Contract reference` points to the mapping UI key for data controls, the action key for interactive controls, or `not-applicable` with rationale for presentation-only elements.

| UI key | Element kind | Location/label | Modes | Visible/enabled rule | Required/read-only/default | Dependency/trigger and behavior | Requirement reference | Contract reference | Gap key |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ui.example` | field/grid-column/button/tab/dialog/state | <Location / label> | search/view/add/edit | <Exact rule> | <Exact contract> | <Dependency and behavior> | `FEAT-ID#local-key` | `ui.example` / `action.save` / not-applicable | none or `gap.behavior-example` |

## UI-To-Data Mapping

Create one row for every field and grid column. Use `TBD` rather than guessing.

| UI key | Logical attribute | Legacy block.item | Legacy table.column/object | Physical type/nullability | Target data/API member and type | Transform/default | CRUD | Evidence locator | Confidence | Disposition | Gap key |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ui.example` | <Attribute> | `<BLOCK.ITEM>` | `<TABLE.COLUMN>` or TBD | <Type/nullability or TBD> | `<member>: <type>` or TBD | <Rule/default> | CRU | `<path>#<locator>` | high/medium/low | verified/inferred/conflict/TBD/not-applicable | none or `gap.mapping-example` |

## LOV Contracts

| UI key | Display value | Return value | Source object/query | Parameters/dependencies | Filter/sort | Inactive-value behavior | Cache/refresh | Evidence locator | Confidence | Disposition | Gap key |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ui.example-lov` | <Display> | <Return> | <Object/query or TBD> | <Dependencies> | <Rules> | <Behavior> | <Policy> | `<path>#<locator>` | high/medium/low | <disposition> | none or `gap.lov-example` |

If the feature has no LOV, include one `not-applicable` row with the evidence/rationale. Do not leave this section empty.

## Validation And Business Rules

| Rule key | Requirement reference | Trigger/layer | Inputs | Ordered rule/sequence | Exact outcome/error message | Evidence locator | Confidence | Disposition | Gap key |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `validation.example` | `FEAT-ID#local-key` | save/client+server | <Inputs> | <Ordered checks> | <Exact message/status> | `<path>#<locator>` | high/medium/low | <disposition> | none or `gap.validation-example` |

## Oracle Constraint And Error Translation

Create one row for every in-scope database constraint or application-raised failure reachable from a declared operation. Preserve the two-stage legacy mapping: Oracle failure signature to application code, then application code to final message/template. Normalize schema-qualified and unqualified forms in one row. Use a local gap when either stage, parameters, attribution, or transaction behavior is unresolved.

| Error mapping key | Applies to action/control | Oracle failure signature | Database object/constraint semantics | Legacy application code | User-facing message/template | Message parameters | Match and precedence | Structured API/UI outcome | Transaction/editor behavior | Evidence locator | Confidence | Disposition | Gap key |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `error.constraint.example-uk1` | `action.save`; `ui.example` | `ORA-00001`; `SCHEMA.EXAMPLE_UK1` and `EXAMPLE_UK1` | `EXAMPLE_TABLE(EXAMPLE_KEY)` unique | `GLA-00000` or TBD | <Exact catalogue text/template or TBD> | <Named/ordered parameters or N/A> | exact normalized constraint before generic ORA-00001 | `code`, `message`, `constraint`, `target`; keep editor open and focus `ui.example` | rollback current transaction; preserve submitted editor state | `<path>#<handler-branch>`; `<message-catalogue>#<code>` | high/medium/low | verified/inferred/conflict/TBD | none or `gap.error-example-uk1` |

Include a final `error.fallback.unknown-database` row specifying safe unknown-error handling. It may retain a sanitized Oracle/driver code for diagnosis, but it must not masquerade as a legacy application message. Do not use the fallback for a known constraint-to-code mapping merely because the final catalogue text is unresolved.

Reference applicable `error.*` keys in Validation And Business Rules, Action And Transaction Contracts, Operation Decision Tables, API Or Service Contracts, and Acceptance Scenarios. This table remains the single source for translation detail; those sections should reference rather than duplicate it.

## Search And Retrieval Contract

| Concern | Required behavior | Limits/defaults | Errors/empty behavior | Evidence/decision | Disposition | Gap key |
| --- | --- | --- | --- | --- | --- | --- |
| Operators | <Exact semantics> | <Defaults> | <Invalid-input behavior> | <Locator> | <disposition> | none or `gap.search-example` |
| Sorting | <Stable sort> | <Defaults> | <Failure behavior> | <Locator> | <disposition> | none or `gap.sort-example` |
| Pagination | <Cursor/page behavior> | <Limits> | <Boundary behavior> | <Locator> | <disposition> | none or `gap.pagination-example` |
| No results | <Response/UI behavior> | N/A | <Exact empty state> | <Locator> | <disposition> | none or `gap.empty-example` |

## Action And Transaction Contracts

Create one row for every button, form submission, row action, and material state transition.

| Action key | UI keys/modes | Visible/enabled and preconditions | Authorization | Ordered client/server validations | Transaction and database operation sequence | Final objects/procedures/functions | Commit/rollback/partial failure | Response/side effects | Exact errors/messages | Requirement references | Evidence locator | Confidence | Disposition | Gap key |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `action.save` | `ui.save`; add/edit | <Exact rules> | <Policy> | <Ordered checks and rule keys> | <Boundary and ordered INSERT/UPDATE/DELETE/calls> | <Tables/views/packages/procedures/functions or TBD> | <Exact behavior> | <Response and refresh/navigation> | <Message/code per failure> | `FEAT-ID#local-key` | `<path>#<locator>` | high/medium/low | <disposition> | none or `gap.action-save` |

Every button, form submission, row action, navigator action, tab transition, child add/remove, and material state transition needs a row. Use explicit `not-applicable` values for purely client-side actions; do not omit their behavior.

Reference the applicable `operation.*` local row keys in the ordered-validation and transaction-sequence cells when the action has detailed operation decisions.

## Operation Decision Tables

Use this one consolidated table for every materially complex operation, including Delete, Add, Edit, Save/Submit, Search, Clear/Cancel, LOV selection, child-row actions, tab actions, and module-specific operations found in evidence. Keep one atomic row per ordered predicate, validation, warning, query, DML statement, procedure/function call, message, state transition, confirmation, exception outcome, or transaction effect. A simple operation may use one complete row. If no operation is applicable, include one `not-applicable` row with rationale.

| Operation row key | Parent action/operation | Phase/trigger | Order | Decision kind | Condition and inputs/binds | Detailed rule/check or call | Physical operation/object | Outcome and control flow | Exact message/error | Transaction effect | Evidence locator | Confidence | Disposition | Gap key |
| --- | --- | --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `operation.delete.precheck.child-exists` | `action.delete` | pre-delete | 10 | hard_blocker | `<Predicate and bind values>` | `<Atomic check or call>` | `<SELECT/DML/package.procedure/function and objects>` | `<Continue/stop/confirm/retry and state change>` | `<Exact code/message or N/A>` | `<None/commit/rollback/savepoint effect>` | `<path>#<trigger/program-unit/branch>` | high/medium/low | verified/inferred/conflict/TBD/not-applicable | none or `gap.operation-delete-child` |

Preserve source execution order even when multiple rows use the same object or message. If evidence declares hard-check or warning counts, the represented rows must reconcile to those counts. Add a `TBD` row linked to a consolidated gap for every unresolved expected row; never hide a count mismatch in prose.

## CRUD And Submit Completeness

Use one row for each operation below. `not-applicable` requires a rationale and evidence/decision. A missing contract uses `TBD` plus a gap key.

| Operation | Applicable | Entry action keys | Validations | Transaction/database effect | Final objects/procedures/functions | Success/error outcome | Evidence/decision | Gap key |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| create | yes/no | <Action keys> | <Rule keys/N/A> | <Effect/N/A/TBD> | <Objects/N/A/TBD> | <Outcome> | <Locator/rationale> | none or `gap.crud-create` |
| retrieve | yes/no | <Action keys> | <Rule keys/N/A> | <Effect/N/A/TBD> | <Objects/N/A/TBD> | <Outcome> | <Locator/rationale> | none or `gap.crud-retrieve` |
| update | yes/no | <Action keys> | <Rule keys/N/A> | <Effect/N/A/TBD> | <Objects/N/A/TBD> | <Outcome> | <Locator/rationale> | none or `gap.crud-update` |
| delete | yes/no | <Action keys> | <Rule keys/N/A> | <Effect/N/A/TBD> | <Objects/N/A/TBD> | <Outcome> | <Locator/rationale> | none or `gap.crud-delete` |
| submit/save | yes/no | <Action keys> | <Rule keys/N/A> | <Effect/N/A/TBD> | <Objects/N/A/TBD> | <Outcome> | <Locator/rationale> | none or `gap.submit` |
| cancel/clear | yes/no | <Action keys> | <Rule keys/N/A> | <Effect/N/A> | <Objects/N/A> | <Outcome> | <Locator/rationale> | none or `gap.cancel-clear` |

## Parent-Child Persistence

| Relationship | Load behavior | Save order | Update/delete semantics | Orphan/partial-failure behavior | Evidence/decision | Disposition | Gap key |
| --- | --- | --- | --- | --- | --- | --- | --- |
| <Parent-child or not-applicable> | <Behavior/rationale> | <Order/N/A/TBD> | <Rules/N/A/TBD> | <Behavior/N/A/TBD> | <Locator> | <disposition> | none or `gap.parent-child` |

## Tab And Population Logic

| Tab/section | Initial population | Refresh/lazy-load trigger | Dependencies | Dirty/stale behavior | Failure behavior | Evidence/decision | Disposition | Gap key |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| <Tab or not-applicable> | <Behavior/rationale> | <Trigger/N/A/TBD> | <Dependencies/N/A> | <Behavior/N/A/TBD> | <Behavior/N/A/TBD> | <Locator> | <disposition> | none or `gap.tab-example` |

## API Or Service Contracts

| Contract key | Method/operation | Request | Response | Validation/errors | Authorization | Idempotency/concurrency | Requirement references | Evidence/decision | Disposition | Gap key |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `api.example` | <Operation or TBD> | <Shape/TBD> | <Shape/TBD> | <Contract/TBD> | <Policy/TBD> | <Policy/TBD> | `FEAT-ID#local-key` | <Locator> | <disposition> | none or `gap.api-example` |

## Cross-Cutting Requirements

| Concern | Implementation requirement | Enforcement/failure behavior | Evidence/decision | Disposition | Gap key |
| --- | --- | --- | --- | --- | --- |
| Authorization | <Requirement or TBD> | <Enforcement and error/TBD> | <Reference> | <disposition> | none or `gap.authorization` |
| Concurrency | <Requirement or TBD> | <Conflict behavior/TBD> | <Reference> | <disposition> | none or `gap.concurrency` |
| Audit | <Requirement or TBD> | <Recording/failure behavior/TBD> | <Reference> | <disposition> | none or `gap.audit` |
| Security | <Requirement or TBD> | <Enforcement/failure behavior/TBD> | <Reference> | <disposition> | none or `gap.security` |
| Observability | <Requirement or TBD> | <Signals/failure behavior/TBD> | <Reference> | <disposition> | none or `gap.observability` |
| Performance | <Requirement or TBD> | <Limits/degradation behavior/TBD> | <Reference> | <disposition> | none or `gap.performance` |

## Acceptance Scenarios

| Scenario key | Requirement references | Given | When | Then | Failure/rollback evidence | Disposition | Gap key |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `scenario.save-success` | `FEAT-ID#local-key` | <Precondition> | <Action> | <Outcome> | <Evidence/expected behavior> | <disposition> | none or `gap.scenario-save` |

Include happy paths, validation failures, authorization failures, concurrency conflicts, missing configuration, dependency failures, and transaction rollback where applicable.

## Coverage Matrix

Every target UI inventory row must appear exactly once.

| UI key | Mockup location | Oracle evidence | Requirement reference | Implementation sections | Disposition | Gap key/rationale |
| --- | --- | --- | --- | --- | --- | --- |
| `ui.example` | <Location> | `<path>#<locator>` or none | `FEAT-ID#local-key` | <Sections> | verified/inferred/conflict/TBD/not-applicable | none or `gap.example`: <rationale> |

## Implementation Readiness And Consolidated Gaps

This is the single implementation-facing register. Include every unresolved material assumption, open question, conflict, evidence gap, blank/TBD contract value, risk, and blocker once; other sections reference its local gap key.

| Outcome | Value | Reason |
| --- | --- | --- |
| Review readiness | review_ready/reviewable_with_gaps/not_review_ready | <Derived explanation> |
| Implementation readiness | implementation_ready/implementation_ready_with_known_gaps/not_implementation_ready | <Derived explanation> |
| Code generation posture | allowed/allowed_with_known_gaps | <Production-safe or POC-only explanation> |

| Gap key | Type | Severity | Statement | Affected local keys | Likely generated-code/behavior impact | Safe POC fallback | Resolution needed | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `gap.example` | gap/open-question/conflict/assumption/risk/implementation-blocker | blocker/high/medium/low | <Unresolved fact> | <UI/rule/action/API keys> | <Specific omission, wrong behavior, or unsafe default likely in generated code> | <Explicit stub, disabled path, fail-closed behavior, or bounded mock> | <Evidence/decision and owner if known> | open/accepted-for-poc/resolved |

## Evidence And Confidence Summary

| Category | Verified | Inferred | Conflict | TBD | Not applicable | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Fields/grid columns | 0 | 0 | 0 | 0 | 0 | <Notes> |
| LOVs | 0 | 0 | 0 | 0 | 0 | <Notes> |
| Actions | 0 | 0 | 0 | 0 | 0 | <Notes> |
| Rules | 0 | 0 | 0 | 0 | 0 | <Notes> |

## Change History

| Date | Change | Evidence/decision | Notes |
| --- | --- | --- | --- |
| YYYY-MM-DD | Incrementally updated/overwritten | <Reference> | <Semantic design change, preserved content, and superseded content if any> |
```

## Evidence Locator Rules

- Prefer `<repository-relative-path>#<heading-or-symbol>` for Markdown and source files.
- Use `<path>:<line>` only when the line is stable enough to be useful.
- Use `Oracle module > block.item > trigger/program unit` for extracted Forms behavior.
- For error translations, cite both the exact handler branch that maps the Oracle signature to the application code and the message-catalogue/lookup locator that resolves the code to final text; cite a gap when the second locator is unavailable.
- Use `screenshot-file > tab/section/label` for visible-layout evidence only.
- Use `mockup route > component > control/state` for target UI intent only.
- Cite an accepted ADR or target architecture section for target design decisions.
- Use `none` only with `TBD` or `not-applicable`, never with `verified`.

## Confidence Rules

| Confidence | Meaning |
| --- | --- |
| `high` | Direct Forms XML/PLD/FMT/SQL evidence, explicit accepted decision, or directly observed target contract. |
| `medium` | Consistent inference from compile logs, binary strings, multiple corroborating files, or stable target conventions. |
| `low` | Plausible but weakly supported; retain as `inferred` or `TBD`, never silently promote to verified. |

Do not use confidence to hide a conflict. Use `conflict` whenever authoritative sources disagree materially.
