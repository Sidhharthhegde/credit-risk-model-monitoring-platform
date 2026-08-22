# Change Control Policy

**Policy ID:** `PART-B-CHANGE-CONTROL-01`  
**Version:** `0.1.0`  
**Status:** `APPROVED_FROZEN`

## 1. Purpose

This policy separates immutable DF-01 model changes from Part B monitoring-policy, implementation, evidence, and presentation changes.

## 2. Model changes

The following are model changes:

- Refit or changed fitted parameters.
- Hyperparameter change.
- Feature addition, removal, substitution, or changed ordering.
- Changed feature-engineering logic.
- Changed missing-value or categorical treatment.
- Changed preprocessing fit or state.
- Changed probability representation.
- Added or changed calibration.
- Changed threshold value or comparator.
- Replaced model artifact.

Part B may recommend these actions but may not implement them as changes to DF-01. An implemented model change requires a new model/version identity, new validation/governance lineage, and separate approval. DF-01 remains unchanged.

## 3. Monitoring-policy changes

The following require a new monitoring protocol or configuration version:

- Changed reference population or bins.
- Changed monitoring frequency.
- Changed maturity or eligibility rule.
- Added, removed, or redefined metric.
- Changed warning or critical threshold.
- Enabled an alert previously marked diagnostic-only.
- Changed repeat-breach or overall-health logic.
- Changed source-criticality classification.
- Changed subgroup definition or minimum-evidence rule.
- Changed escalation action or owner.
- Changed evidence schema or retention rule.

Monitoring-policy changes do not change DF-01, but they must be documented, reviewed, approved, and versioned.

## 4. Implementation changes

Implementation changes that do not alter approved methodology may use ordinary source control if tests demonstrate semantic equivalence. Examples include refactoring, performance improvement, additional internal validation, documentation correction, or dashboard layout changes.

If semantic equivalence is uncertain, treat the change as a monitoring-policy change.

## 5. Evidence corrections

Finalized evidence is append-only. Corrections require:

1. A correction reason.
2. The original evidence identity.
3. A new or superseding artifact/package.
4. New hashes and manifest.
5. Disclosure of the affected conclusion.

Do not silently overwrite finalized evidence.

## 6. Versioning

Use:

- `MONITORING-PROTOCOL-01`, `MONITORING-PROTOCOL-02`, and so on for protocol changes.
- `FEATURE-REF-01`, `FEATURE-REF-02`, and so on for input-reference changes.
- `PERF-REF-01`, `PERF-REF-02`, and so on for performance-reference changes.
- Semantic versions for source and configuration artifacts.
- Unique run IDs for executions.

## 7. Required change record

Every governed change record must state:

- Change ID and requester.
- Date and reason.
- Classification.
- Affected artifacts and evidence.
- Whether DF-01 is affected.
- Required tests.
- Reviewer and decision.
- Effective version and date.
- Rollback or supersession plan.

## 8. Emergency changes

Emergency changes do not permit silent modification of DF-01 or finalized evidence. Temporary controls must be identified as temporary, approved by the applicable governance role, time-bound, tested proportionately, and replaced or retired through normal change control.
