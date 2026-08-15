---
artifact_kind: legacy_evidence_semantic_review
authority: review_overlay_not_extracted_fact
module_id: {{MODULE_ID}}
module_evidence_id: {{MODULE_EVIDENCE_ID}}
evidence_fingerprint: {{EVIDENCE_FINGERPRINT}}
reviewed_package_sha256: {{PACKAGE_SHA256}}
parent_specification: {{PARENT_SPECIFICATION}}
review_status: in_progress
reviewed_at: {{REVIEWED_AT}}
---

# {{MODULE_ID}} - Legacy Evidence Semantic Review

> This file reviews relationships across extracted legacy evidence. It is not extracted fact, an approved requirement, target design, target test, or implementation decision.

## 1. Review Control

| Attribute | Value |
| --- | --- |
| Module evidence | `{{MODULE_EVIDENCE_ID}}` |
| Evidence fingerprint | `{{EVIDENCE_FINGERPRINT}}` |
| Reviewed package SHA-256 | `{{PACKAGE_SHA256}}` |
| Parent specification | [{{PARENT_SPECIFICATION}}]({{PARENT_SPECIFICATION}}) |
| Operation details | [{{OPERATION_DETAILS}}]({{OPERATION_DETAILS}}) |
| Decoded source | [{{DECODED_SOURCE}}]({{DECODED_SOURCE}}) |
| Database reference | [{{DATABASE_REFERENCE}}]({{DATABASE_REFERENCE}}) |
| Review status | `in_progress` |

## 2. Review Scope And Method

Review the master and all linked children as one evidence package. Apply every semantic lens in the skill. Preserve observations separately from interpretations and do not alter the extraction package.

Package inventory at review start:

| Measure | Count |
| --- | ---: |
| Operation paths | {{OPERATION_COUNT}} |
| Decoded units | {{DECODED_UNIT_COUNT}} |
| Relevant database objects | {{DATABASE_OBJECT_COUNT}} |
| Controlled master sections | {{CONTROLLED_SECTION_COUNT}} |
| Linked screenshots | {{SCREENSHOT_COUNT}} |
| Open extraction gaps | {{OPEN_GAP_COUNT}} |

## 3. Semantic Findings Register

| Local key | Type | Severity | Status | Summary | Human review |
| --- | --- | --- | --- | --- | --- |
| _No findings recorded yet_ | - | - | - | Review pending | - |

## 4. Finding Details

Add one detail section per material finding using this exact structure:

<!--
### `MOD-{{MODULE_ID}}#review.semantic-slug`

Type: ambiguity
Severity: medium
Status: proposed_for_human_review
Confidence: medium

#### Facts In Relationship Or Tension

- Fact supported by the package.
- Related fact supported by the package.

#### Source References

- [Master evidence]({{PARENT_SPECIFICATION}}#relevant-anchor) - natural locator such as `CTT.WhereClause`.
- [Exact operation path]({{OPERATION_DETAILS}}#operation-anchor) - source locator or code line.

#### Analysis

Explain the semantic relationship without inventing intent.

#### Proposed Resolution

State a source-acquisition step, a human question, or the only source-supported reconciliation.

#### Applied Interpretation

Use `Not applied` unless the automatic-resolution test passes.

#### Human Review Needed

State the decision or confirmation needed, or `None` for an automatic resolution.

#### Downstream Evidence Impact

State what later curation must keep visible. Do not propose target behavior.
-->

No detailed findings have been recorded yet.

## 5. Automatically Reconciled Interpretations

List only findings with status `resolved_automatically`. Include the local key, conclusion, and decisive source references. Do not edit the extraction master.

None yet.

## 6. Human Review Queue

Summarize findings with status `proposed_for_human_review` or `accepted_as_legacy_behavior`, the precise question, and the reviewer role if known. Use `TBD` rather than inventing an owner.

None yet.

## 7. Missing Runtime Context

Summarize findings with status `blocked_by_missing_evidence`, including the missing artifact or runtime observation and the behavior it affects.

None yet.

## 8. Review Coverage And Limitations

Record which lenses were completed, which package areas were sampled or inspected exhaustively, and any limitation that could hide cross-fact relationships.

Status: review pending.

## 9. Downstream Handoff

List the review keys that later evidence hardening or target requirement curation must consider. Do not decide target treatment here.

None yet.

## 10. Review History

| Date | Evidence fingerprint | Change | Finding keys |
| --- | --- | --- | --- |
| {{REVIEWED_AT}} | `{{EVIDENCE_FINGERPRINT}}` | Review scaffold created | - |
