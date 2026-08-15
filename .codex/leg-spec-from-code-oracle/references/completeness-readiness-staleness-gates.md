# Evidence Completeness And Staleness Gates

## Purpose

These gates determine whether the selected module has been exhaustively extracted against the supplied readable evidence and whether source changes make evidence regions stale.

They do not assess POC readiness, production parity, target implementation feasibility, target architecture, or requirement approval. Those decisions belong to later curation and engineering workflows.

## Gate Record

```json
{
  "gate_id": "GATE-FORMS-STRUCTURE",
  "level": "evidence",
  "operation": "module|query|insert|update|delete|validate|save|custom",
  "status": "pass|pass_with_registered_gaps|fail|not_applicable",
  "supporting_record_ids": [],
  "blocking_record_ids": [],
  "reason": ""
}
```

## Mandatory Evidence Gates

### Source classification

Pass when every supplied file has a hash, role, module association or explicit unrelated disposition, readability, and parse status.

### Source integrity

Pass when current hashes and the specification fingerprint reconcile and no source changed after extraction.

### Forms structure

Pass when every selected-module window, canvas, tab page, block, relation, LOV, record group, trigger, program unit, and item from readable Forms sources is represented with its extracted properties or precisely gapped. Aggregate counts do not satisfy this gate.

### Visual placement

Pass when every item is assigned to its evidenced canvas/tab/section/grid or has a precise ambiguous-placement gap. A database block is not automatically a visual section.

### Effective CRUD

Pass when design-time CRUD is recorded and every runtime/inherited uncertainty is either resolved or precisely gapped. Do not collapse design-time and effective values.

### Physical mapping

Pass when each applicable item-to-column mapping is supported by Forms properties, SQL, or DDL, or is precisely gapped, and every DDL-resolved mapping shows the physical type directly beside `TABLE.COLUMN`.

### Durable evidence fidelity

Pass when the linked Markdown package contains no truncation marker or lossy `+N more` placeholder; every normalized operation and relevant DDL record is present completely in its designated child; and every decoded trigger/program-unit body retained by the normalized model is present exactly with its source hash. The master and all children must share module, run, and fingerprint metadata and have resolving relative links.

### Delete dependency reconciliation

Pass when every supplied inbound foreign key to each selected persistence object is rendered with referencing/referenced columns and `ON DELETE` behavior, then explicitly reconciled with the dependencies checked by decoded Forms delete paths. Forms routines must not be described as a complete database-dependency inventory unless both sets are proven equal.

### Audit population ownership

Pass when required audit columns have a source-established population mechanism. Otherwise pass only with a precise runtime/source gap naming the affected table and columns; never infer that Forms or a database trigger owns population.

### Entry points and call reachability

Pass when all decoded entry points and reachable calls are recorded, and unresolved calls identify affected operations and source locators.

### Operation paths

Pass when query, insert, update, delete, validate, save/commit/rollback, and custom paths found in readable source are represented separately.

### Database references

Pass when every referenced database object is resolved to supplied DDL or appears in a precise missing-DDL gap.

### Rules and messages

Pass when decoded branches, validations, calculations, message codes/text, stop effects, and exception paths are represented or precisely gapped. In the master rule ledger, associate a message with a business condition only when it occurs inside the active decoded `IF`/`ELSIF` branch in the same unit or another explicit control-flow relation proves it. Preserve unbound messages explicitly and never repeat a path-wide message/stop-effect collection for each branch.

### Screenshot association

Pass when every supplied image is scored for module association and every plausible match is linked in the specification with basis and confidence. No screenshot is required for overall extraction to pass; absence is recorded.

### Coverage reconciliation

Pass when every coverage denominator equals extracted/accounted records plus precise unresolved records and the numbers can be recomputed from normalized evidence.

### Comparison continuity

When one or more prior specifications are used, pass when each legacy anchor or exact source statement independently supported by current evidence remains represented anywhere in the current package. Ignore target-only IDs and proposals. In fresh mode, include adjacent `previous_<output-name>.md`, the same-named flat historical specification when output is nested, and `<output-stem>_v*.md` specifications unless an explicit oracle or opt-out is supplied. For a nested feature package, also search its parent `evidence/features/` folder for historical flat specifications.

## Status Meaning

- `pass`: the dimension is fully accounted for by readable supplied evidence.
- `pass_with_registered_gaps`: every known denominator member is accounted for, but exact source or runtime evidence remains missing.
- `fail`: supplied readable evidence is omitted, inconsistent, stale, or not traceable.
- `not_applicable`: the dimension has a source-backed reason not to apply.

An open, precise source gap is not itself an extraction failure. An unregistered omission is.

## Negative-Claim Policy

Statements such as “no validation”, “read-only”, “no delete logic”, “no dependency”, or “no external effect” are allowed only when:

1. relevant source families were inventoried;
2. readable sources were searched;
3. reachability and inherited/runtime gaps were considered;
4. the statement is bounded to supplied evidence; and
5. conflicting evidence is absent.

Otherwise write “not established by supplied evidence” and register a gap when material.

## Staleness

Map source changes to affected evidence regions:

| Change kind | Minimum stale regions |
| --- | --- |
| Forms structure/item property | Screen overview, module structure, layout, fields, full item inventory |
| Trigger/program-unit body | Operation ledger, actions, rules, workflow, processing, messages, event mapping |
| DDL | Data mapping, constraints/defaults, processing, DDL inventory |
| Screenshot | Screen overview and source/screenshot inventory |
| Gap lifecycle | Evidence summary, unknowns, coverage/gaps, extraction history |
| Extractor semantic version | All generated evidence regions |

Refresh must replace all impacted marker regions and update the fingerprint/history. It must preserve unrelated human review notes outside generated regions.

## Patch Failure Conditions

Fail a generated or refreshed specification when:

- a canonical section, appendix, or marker is missing;
- a required operation, decoded-source, or database-reference child is missing, unlinked, or metadata-mismatched;
- a truncation marker or lossy high-cardinality placeholder appears;
- a complete normalized operation or DDL record is absent from its designated child;
- Section 6 has a table row over 4,000 characters or the Section 12 rule ledger has a row over 5,000 characters;
- a path-wide message or stop-effect collection is repeated for every rule instead of being structurally associated or left explicitly unbound;
- an item, region, operation entry, source path, gap subject, or plausible screenshot is omitted;
- a DDL-resolved item mapping omits its physical type;
- an inbound foreign key or its `ON DELETE` effect is omitted;
- exact decoded trigger/program-unit source is missing;
- required audit columns lack both a source-established population owner and a precise gap;
- a field appears under the wrong region without an explicit ambiguity record;
- coverage arithmetic does not reconcile;
- a fingerprint is stale;
- a current-source-supported comparison anchor is lost;
- a negative claim exceeds the evidence;
- target requirements, target tests, target design, POC assumptions, feasibility, or row-level requirement ID families appear in the evidence document.

## Report

Report evidence status by dimension and operation:

```json
{
  "overall_evidence": "pass_with_registered_gaps",
  "operations": {
    "query": "pass",
    "insert": "pass_with_registered_gaps",
    "update": "pass_with_registered_gaps",
    "delete": "not_applicable"
  },
  "open_gap_subjects": [],
  "stale_sections": []
}
```
