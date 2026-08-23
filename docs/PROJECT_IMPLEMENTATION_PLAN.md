# Credit Risk Model Monitoring Platform

## Authoritative Phase-by-Phase Implementation Plan

**Project:** Part B - Model Monitoring Platform  
**Repository:** `credit-risk-model-monitoring-platform`  
**Repository URL:** `https://github.com/Sidhharthhegde/credit-risk-model-monitoring-platform`  
**Document status:** `APPROVED_IMPLEMENTATION_PLAN`  
**Plan version:** `0.2.3`  
**Document owner:** Sidharth Ravindra Hegde  
**Last updated:** 2026-08-22  
**Part A dependency:** Frozen development model `DF-01 / XGBT-01`

---

## 1. Purpose of this document

This document is the controlled implementation roadmap for Part B. It is intended to be used throughout the project to answer:

1. What must be completed in each phase?
2. Which earlier phases must be complete before work begins?
3. What artifacts must each phase produce?
4. Which tests and reconciliations are required?
5. What constitutes phase completion?
6. Which claims are and are not supported at each point?
7. Which decisions require protocol approval or formal change control?

This plan does not authorize monitoring execution by itself. No reference statistics, drift metrics, simulated monitoring results, performance estimates, dashboards, or monitoring reports should be produced until the Phase 0 monitoring protocol has been reviewed and frozen.

After approval, update `Document status` to `APPROVED_IMPLEMENTATION_PLAN` and record the approval in the project decision log. Later changes must be versioned and explained rather than silently overwritten.

---

## 2. Project objective

Build a production-shaped, end-to-end monitoring platform demonstrating how the frozen Part A credit-risk model would be monitored through simulated observation cohorts and, when eligible outcomes exist, outcome-matured cohorts.

The platform must answer:

- Is the incoming scoring population contractually valid?
- Are required application and external data sources available?
- Has data completeness or validity deteriorated?
- Has the applicant population changed?
- Have governed model inputs drifted?
- Has the distribution of raw predicted default probabilities changed?
- Has behaviour around the frozen `0.080` threshold changed?
- When outcomes are mature, has discrimination deteriorated?
- When outcomes are mature, has probability calibration deteriorated?
- When outcomes are mature, has threshold-policy performance deteriorated?
- Is deterioration concentrated in governed subpopulations?
- Which monitoring assumptions or limits have been breached?
- What escalation, investigation, restriction, review, or redevelopment action should follow?
- Can every reported result be reproduced and traced to exact inputs, configuration, code, model identity, and evidence?

Part B demonstrates a controlled monitoring capability. It must not claim that DF-01 was deployed in a real lending process or granted production approval.

---

## 3. Non-negotiable Part A boundary

Part A is complete and frozen. Part B must treat it as a read-only dependency.

| Item | Frozen value |
|---|---|
| Development freeze | `DF-01` |
| Selected model | `XGBT-01` |
| Model version | `xgbt01_raw_threshold01_df_v1` |
| Implementation | Fitted sklearn pipeline with embedded preprocessing and XGBoost classifier |
| Model artifact | `models/tuning/step45_xgb_tuning_v1/finalists/XGBT-01.joblib` |
| Model SHA-256 | `ab0000a4ae092f0444760839e185384d44f9a9760be298189bdfcd80c67fa500` |
| Raw predictors | 176 governed post-feature-engineering predictors |
| Encoded predictors | 306 exact ordered columns |
| Identifier | `SK_ID_CURR` |
| Positive class | `TARGET=1` |
| Probability | Raw `P(TARGET=1)` |
| Threshold | `THRESHOLD-01` |
| Threshold rule | Raw probability `>= 0.080` |
| Output classes | `risk_negative`, `risk_positive` |
| Validation disposition | `VALIDATED_WITH_CONDITIONS` |
| Validation scope | `INTERNAL_ANALYTICAL_VALIDATION` |
| Production approval | Not granted; separate governance decision |
| Published Part A commit | `0f758a8ee76906b2a870ebacbdcac0ef6c951485` |

Part B must never:

- Refit DF-01.
- Refit or replace its embedded preprocessor.
- Reorder or change the 176-feature contract.
- Change the XGBoost configuration.
- Add a calibrator to DF-01.
- Change the raw probability representation.
- Change `THRESHOLD-01` or its `>=` comparator.
- Treat `risk_positive` as an actual rejection decision.
- Treat `risk_negative` as an actual approval decision.
- Overwrite Part A artifacts or evidence.
- Present synthetic monitoring outcomes as empirical external performance.
- Present `application_test` as labelled performance evidence.

Any future recalibration, threshold revision, feature revision, preprocessing change, refit, or redevelopment produces a new governed model version. DF-01 remains immutable.

---

## 4. Supported and unsupported claims

### 4.1 Claims Part B may support

- A production-shaped monitoring architecture was implemented.
- DF-01 identity and scoring parity were verified before monitoring.
- Monitoring cohorts were validated against a frozen input contract.
- Data quality, population drift, feature drift, score drift, and analytical threshold behaviour were monitored on unlabelled cohorts.
- Outcome-dependent metrics were conditionally executed only for eligible mature cohorts.
- Synthetic scenarios correctly triggered expected control and deterioration states.
- Monitoring alerts, evidence, escalation logic, and audit history were retained.
- The historical `application_test` population supplied unlabelled monitoring simulation evidence.

### 4.2 Claims Part B may not support without new evidence

- Actual production deployment.
- Real production monitoring.
- Real loan approval or rejection outcomes.
- External validation based only on `application_test`.
- Out-of-time validation unless a genuine time-based population is obtained.
- External transportability.
- Realised discrimination or calibration on an unlabelled population.
- Fairness certification or disparate-impact assessment.
- Regulatory certification or compliance.
- Universal validity of project-defined alert thresholds.

---

## 5. Monitoring architecture

```text
Part A binding and runtime qualification
                    |
                    v
           Reference definitions
                    |
                    v
        Incoming observation cohort
                    |
                    v
       Contract and data validation
                    |
          +---------+---------+
          |                   |
          v                   v
 Label-free monitoring   Outcome ingestion
 - data quality                |
 - source availability         v
 - feature drift         Maturity evaluation
 - score drift                 |
 - decision distribution  +----+----+
          |               |         |
          |           ineligible  eligible
          |               |         |
          |               v         v
          |        NOT_ASSESSABLE  Performance
          |                         Calibration
          |                         Threshold outcomes
          +-------------+-----------+
                        |
                        v
               Subpopulation analysis
                        |
                        v
                Alert and escalation
                        |
                        v
           Immutable evidence + SQLite
                        |
                 +------+------+
                 |             |
                 v             v
             Dashboard       Report
```

---

## 6. Global implementation rules

### 6.1 Determinism

- Reference bins are created once and versioned.
- Monitoring periods reuse the exact frozen bins.
- Random scenario generation uses declared seeds.
- Every run records its configuration and runtime.
- Sorting, category ordering, tie handling, and missing buckets are deterministic.

### 6.2 Separation of concerns

- Monitoring components return structured objects or tables.
- Core metrics do not print directly or depend on the dashboard.
- Dashboard and reports consume persisted results.
- SQLite is a query/history layer, not the sole audit record.
- Immutable evidence packages are the authoritative run record.

### 6.3 Status vocabularies

Metric severity:

- `NORMAL`
- `WARNING`
- `CRITICAL`
- `INSUFFICIENT_DATA`
- `NOT_ASSESSABLE`

Outcome maturity:

- `UNMATURED`
- `PARTIALLY_MATURED`
- `MATURED`
- `NOT_AVAILABLE`

Alert lifecycle:

- `OPEN`
- `ACKNOWLEDGED`
- `RESOLVED`

Execution/control states:

- `RUN_STARTED`
- `RUN_COMPLETED`
- `RUN_COMPLETED_WITH_WARNINGS`
- `RUN_FAILED`
- `DATA_INVALID`
- `MODEL_BINDING_FAILED`
- `SCHEMA_VALIDATION_FAILED`
- `SCORING_PARITY_FAILED`
- `SOURCE_UNAVAILABLE`
- `EVIDENCE_FINALIZATION_FAILED`

### 6.4 Hard-gate principle

A hard-gate failure prevents downstream results from being described as authoritative. The system may retain diagnostic outputs from the failed run, but they must be labelled non-authoritative.

Hard-gate examples include:

- Model artifact hash mismatch.
- Frozen schema mismatch.
- Golden-fixture prediction mismatch.
- Threshold comparator mismatch.
- Missing required identifiers.
- Duplicate applicant identifiers.
- Required feature absence.
- Invalid binary domain.
- Non-finite probabilities.
- Critical source unavailability when no approved fallback exists.
- Evidence manifest finalization failure.

---

## 7. Phase overview and dependency map

| Phase | Name | Depends on | Primary completion gate |
|---:|---|---|---|
| 0 | Repository foundation and monitoring protocol freeze | None | Protocol reviewed, approved and hash-bound |
| 1 | Part A binding and runtime qualification | Phase 0 | All identities reconcile and golden-fixture parity passes |
| 2 | Reference strategy and snapshot specification | Phases 0-1 | Reference definitions approved |
| 3 | Contracts and label-free feature adapter | Phases 1-2 | 176-feature scoring input parity passes |
| 4 | Reference materialization and frozen bins | Phase 3 | Versioned snapshots and bins frozen |
| 5 | Scenario framework | Phases 0, 3-4 | Six scenarios reproduce expected conditions |
| 6 | Data-quality and source monitoring | Phases 3-5 | Contract failures and hard gates validated |
| 7 | Population and feature drift | Phases 4, 6 | Drift metrics reproduce controlled fixtures |
| 8 | Score and observation-time threshold monitoring | Phases 1, 4, 6 | Score/decision monitoring passes parity tests |
| 9 | Outcome ingestion and maturity | Phases 0, 3 | Ineligible cohorts cannot enter performance |
| 10 | Discrimination monitoring | Phases 4, 8-9 | Mature-cohort metrics and uncertainty verified |
| 11 | Calibration and portfolio outcomes | Phases 4, 8-10 | Calibration outputs reconcile |
| 12 | Matured threshold-policy monitoring | Phases 8-11 | Frozen-threshold outcome metrics reconcile |
| 13 | Governed subpopulation monitoring | Phases 9-12 | Generic engine covers all 12 families |
| 14 | Alert and escalation engine | Phases 6-13 | Severity, lifecycle and aggregation tests pass |
| 15 | Evidence, persistence and audit trail | Phases 1-14 | Immutable package and SQLite reconcile |
| 16 | End-to-end monitoring runner | Phases 1-15 | One command produces governed completion state |
| 17 | Test suite and independent reconciliation | Phases 0-16 | Unit, regression and scenario gates pass |
| 18 | Dashboard, report and public release | Phases 15-17 | Visual QA and publication controls pass |

No phase may be marked complete merely because code exists. The stated completion gate and evidence must exist and pass.

---

# Phase 0A - Repository Foundation and Document Control

## Objective

Create the governed Part B repository structure without executing monitoring calculations.

## Entry conditions

- Part B repository strategy agreed: separate repository from Part A.
- Repository URL created.
- Part A remains read-only.

## Tasks

1. Initialize or connect the local Part B folder to the approved GitHub repository.
2. Create the initial folder structure.
3. Add `README.md`, `LICENSE`, `.gitignore`, `pyproject.toml`, and dependency-lock policy.
4. Add `MONITORING_POLICY.md` and `CHANGE_CONTROL_POLICY.md` placeholders.
5. Add a document register and decision log.
6. Define authoritative versus explanatory artifact rules.
7. Define public versus local-only evidence rules.
8. Configure formatting, linting and basic CI without monitoring execution.
9. Record copyright and licence ownership.

## Required deliverables

```text
README.md
LICENSE
.gitignore
pyproject.toml
docs/PROJECT_IMPLEMENTATION_PLAN.md
docs/DOCUMENT_REGISTER.md
docs/DECISION_LOG.md
MONITORING_POLICY.md
CHANGE_CONTROL_POLICY.md
```

## Required tests and checks

- Repository root is Part B, not the portfolio parent and not Part A.
- Part A working tree remains unchanged.
- `.gitignore` excludes raw data, model binaries, SQLite files, local full evidence, row-level predictions and sensitive outcomes.
- Documentation links resolve.
- Initial CI performs only safe source and documentation checks.

## Completion criteria

- Repository foundation is reviewed.
- No monitoring metric has been executed.
- Phase completion decision records all created artifacts.

## Prohibited actions

- Copying the DF-01 binary into Git.
- Committing raw Kaggle data.
- Calculating reference statistics before protocol approval.

---

# Phase 0B - Monitoring Protocol Freeze

## Objective

Prospectively define how monitoring will work before observing monitoring results.

## Entry conditions

- Phase 0A foundation complete.
- Frozen Part A identity is known.

## Tasks

1. Define monitoring purpose, scope and intended use.
2. State that the platform is production-shaped and simulation-based.
3. Identify model owner, monitoring owner, model-risk role, data owner and escalation roles.
4. Define monitored population inclusion and exclusion rules.
5. Define observation cohort, outcome cohort and cohort identifiers.
6. Define monthly monitoring frequency as a project assumption.
7. Define outcome maturity states and prohibit performance calculations on ineligible cohorts.
8. Record that the contractual target horizon is unknown.
9. Define a two-month lag only as a simulation assumption, if retained.
10. Define reference populations by monitoring purpose.
11. Predeclare metrics and diagnostics.
12. Predeclare alert thresholds and label them project-defined governance assumptions.
13. Define hard execution gates.
14. Define repeat-breach logic and overall-health aggregation.
15. Define subgroup families and minimum-evidence rules.
16. Define escalation actions, owners and target response times.
17. Define evidence, hashing, retention and reproducibility rules.
18. Define protocol amendment control.
19. Define supported and unsupported claims.

## Provisional threshold assumptions requiring approval

| Metric | Warning | Critical | Status before approval |
|---|---:|---:|---|
| Feature PSI | `>= 0.10` | `>= 0.25` | Project-defined assumption |
| Score PSI | `>= 0.10` | `>= 0.25` | Project-defined assumption |
| Missing-rate change | `>= 0.02` | `>= 0.05` | Project-defined assumption |
| Unknown-category share | `>= 0.01` | `>= 0.05` | Project-defined assumption |
| Risk-positive-rate change | `>= 0.05` | `>= 0.10` | Project-defined assumption |
| ROC-AUC deterioration | To approve | To approve | Must account for uncertainty |
| Brier-score deterioration | To approve | To approve | Must account for uncertainty |
| O/E ratio | To approve | To approve | Two-sided limits required |

These values are not regulatory requirements or universal industry standards.

## Required deliverables

```text
MONITORING_POLICY.md
configs/monitoring_config.yaml
configs/alert_thresholds.yaml
configs/subpopulations.yaml
reports/protocol/monitoring_protocol_v1/
```

The protocol package should include a manifest, sidecar hash, approval decision and amendment policy.

## Required tests and checks

- Every metric identifies required inputs and label dependence.
- Every threshold identifies its governance classification.
- Performance execution is prohibited for `UNMATURED`, `PARTIALLY_MATURED`, and `NOT_AVAILABLE` outcomes.
- No protocol statement implies real deployment.
- No protocol statement treats `application_test` as performance evidence.

## Completion criteria

- Protocol approved before metric implementation or execution.
- Approved protocol hash recorded.
- Later changes require a versioned amendment.

---

# Phase 1A - Part A Binding Contract

## Objective

Create a machine-readable contract binding every Part B run to the exact frozen Part A model and interface.

## Entry conditions

- Phase 0 protocol approved.
- Read-only access to authoritative Part A artifacts.

## Tasks

1. Record Part A repository URL and published commit.
2. Record DF-01, XGBT-01 and model version.
3. Record model path expectation, size and SHA-256.
4. Record raw and encoded predictor counts.
5. Record probability semantics and positive-class ordering.
6. Record threshold identity, value and comparator.
7. Hash the scoring input schema.
8. Hash the feature lineage and governance registry.
9. Hash golden-fixture inputs, predictions and encoded matrix.
10. Record required runtime versions from Part A.
11. Record the rule that the standalone preprocessor is reconciliation evidence only.
12. Define configurable read-only Part A runtime location.
13. Create a verifier that reports every reconciliation independently.

## Required deliverables

```text
contracts/part_a_binding.json
contracts/schemas/part_a_binding.schema.json
src/credit_risk_monitoring/qualification/binding.py
tests/qualification/test_part_a_binding.py
```

## Required tests and checks

- Valid Part A installation passes.
- Modified model hash fails.
- Wrong model version fails.
- Wrong threshold or comparator fails.
- Wrong probability semantics fails.
- Missing schema or fixture fails safely.
- Windows and POSIX-style serialized relative paths are normalized safely.

## Completion criteria

- All binding fields reconcile with authoritative Part A.
- Binding contract and verifier are reviewed.
- No model or Part A artifact was modified.

---

# Phase 1B - Runtime Qualification

## Objective

Prove that the current Part B runtime is monitoring the governed scorer and reproduces frozen inference behaviour.

## Entry conditions

- Phase 1A binding complete.
- Compatible local dependencies available.

## Tasks

1. Verify model SHA-256 before deserialization.
2. Load the canonical sklearn pipeline from the configured read-only path.
3. Verify pipeline steps are exactly `preprocessor` and `model`.
4. Verify fitted raw and encoded feature identities.
5. Verify model classes are exactly `[0, 1]`.
6. Score frozen golden-fixture inputs.
7. Compare probabilities using the protocol-approved parity rule.
8. Compare frozen risk classifications.
9. Verify boundary behaviour below, at and above `0.080`.
10. Verify pipeline probability and explicit component probability agree.
11. Record runtime and dependency versions.
12. Emit an authoritative qualification decision.

## Required deliverables

```text
src/credit_risk_monitoring/qualification/runtime.py
src/credit_risk_monitoring/qualification/golden_fixture.py
reports/qualification/runtime_qualification_v1/
tests/qualification/test_runtime_qualification.py
```

## Hard failures

- `MODEL_BINDING_FAILED`
- `SCORING_PARITY_FAILED`
- `SCHEMA_VALIDATION_FAILED`

## Completion criteria

- Golden-fixture inputs, encoded representation, probabilities and threshold classes reconcile.
- Qualification evidence is finalized and hash-bound.
- A failed qualification cannot start monitoring.

---

# Phase 2 - Reference Strategy and Snapshot Specification

## Objective

Define which Part A population supplies each baseline without yet calculating monitoring results.

## Reference hierarchy

| Reference | Role | Permitted use |
|---|---|---|
| TRAIN deterministic base | Input and preprocessing reference | Feature distributions, completeness, category vocabulary context, reference bins |
| Development validation | Internal performance reference | Discrimination, calibration and threshold comparison |
| TRAIN OOF predictions | Threshold-selection lineage | Context for the 70% capture project assumption |
| Historical third split | Supplementary internal comparison | Context only; not untouched or external evidence |
| `application_test` | Unlabelled monitoring simulation | Data quality, feature drift, score drift and decision distribution |
| Future labelled OOT/external cohort | Future external evidence | Only after eligibility, lineage and maturity controls pass |

## Tasks

1. Define snapshot IDs such as `REF-INPUT-001` and `REF-PERF-001`.
2. Define row inclusion, exclusions, keys and lineage.
3. Define the exact 176-feature ordering.
4. Define numeric binning rules, missing buckets and tail handling.
5. Define categorical reference categories, missing category and unseen-category bucket.
6. Define score bins and optional monitoring bands.
7. Keep multi-band monitoring separate from the frozen binary risk classes.
8. Define reference version-change governance.
9. Define how reference snapshots are stored without committing restricted row-level data.
10. Define baseline metrics and uncertainty evidence to be inherited from Part A.

## Required deliverables

```text
configs/reference_populations.yaml
contracts/reference_snapshot_contract.json
docs/REFERENCE_STRATEGY.md
reports/protocol/reference_strategy_v1/
```

## Completion criteria

- Every metric maps to exactly one appropriate reference or explicitly has none.
- No reference is described as production or OOT without supporting evidence.
- Reference definitions are approved before materialization.

---

# Phase 3 - Contracts and Label-Free Feature Adapter

## Objective

Create governed interfaces for inputs, outputs and outcomes, and construct a label-free route to the exact frozen 176-predictor scorer input.

## Contracts

### Scoring input

- Unique, complete `SK_ID_CURR`.
- Exactly 176 governed predictors plus identifier.
- Exact feature set, then canonical reorder.
- Numeric, categorical and binary domain rules inherited from Part A.
- No target required.
- No precomputed prediction required.

### Scoring output

- `SK_ID_CURR`.
- Raw XGBT probability.
- Threshold ID and value.
- Frozen binary risk class.
- Model ID and version.
- Pipeline/run identity.

### Outcome

- `SK_ID_CURR`.
- Cohort ID.
- Outcome value and semantics.
- Observation start and end.
- Maturity date or eligibility fields.
- Outcome source and extraction timestamp.
- Completeness and reconciliation status.

## Feature-adapter tasks

1. Reuse or faithfully port the governed deterministic feature logic without modifying Part A.
2. Use `application_test` as the label-free anchor only for the simulation route.
3. Integrate bureau and previous-application sources at governed applicant grain.
4. Produce the same governed application, aggregate and missing-history features.
5. Reconcile one-to-one applicant preservation.
6. Reject target leakage.
7. Reject unexpected columns at the scorer boundary.
8. Verify the adapter emits all 176 features with compatible dtypes.
9. Bind adapter source code and configuration by hash.
10. Test missing history and unseen-category paths.

## Required deliverables

```text
contracts/scoring_input_contract.json
contracts/scoring_output_contract.json
contracts/outcome_contract.json
src/credit_risk_monitoring/contracts/
src/credit_risk_monitoring/feature_adapter/
tests/contracts/
tests/feature_adapter/
```

## Completion criteria

- Adapter passes the frozen scoring contract.
- Applicant grain and keys reconcile.
- No label is required for scoring.
- Part A remains unchanged.

---

# Phase 4 - Reference Materialization and Frozen Bins

## Objective

Materialize the approved reference definitions only after the runtime and feature adapter are qualified.

## Tasks

1. Generate reference snapshots from approved populations.
2. Record source file hashes and key fingerprints.
3. Create fixed numeric reference bins.
4. Create fixed categorical reference distributions.
5. Create fixed score bins.
6. Create optional monitoring score bands, if approved.
7. Store missingness, category, range and distribution summaries.
8. Record Part A performance baselines without recomputing or changing them unless explicitly authorized.
9. Version every reference artifact.
10. Write manifest and sidecar hash.
11. Verify rerun determinism.

## Required deliverables

```text
artifacts/reference_snapshots/REF-INPUT-001/
artifacts/reference_snapshots/REF-PERF-001/
artifacts/reference_bins/REF-BINS-001/
reports/reference/reference_freeze_v1/
```

Row-level reference snapshots are local-only unless specifically approved for public release.

## Required tests and checks

- Bin edges are monotonic and deterministic.
- Missing values have an explicit bucket.
- Values outside reference range are retained in tail buckets.
- Categorical unseen values map to an explicit monitoring bucket.
- Reference proportions reconcile to one within tolerance.
- Repeated generation produces identical hashes in the qualified environment.

## Completion criteria

- Reference freeze decision approved.
- Bins cannot change during ordinary monthly runs.
- Any reference change requires a new reference version.

---

# Phase 5 - Scenario Framework

## Objective

Create controlled monitoring cohorts that exercise normal, warning, critical and control-failure behaviour.

## Required scenario timeline

| Period | Scenario | Expected high-level state |
|---|---|---|
| M1 | Stable | `NORMAL` |
| M2 | Stable with natural variation | `NORMAL` |
| M3 | Mild population drift | `WARNING` |
| M4 | Severe feature and score drift | `CRITICAL` |
| M5 | Data-quality or source-control failure | Hard failure or `CRITICAL` |
| M6 | Synthetic performance deterioration | Performance alert on synthetic evidence only |

## Tasks

1. Define scenario contracts before generation.
2. Declare random seeds and affected variables.
3. Implement numeric shifts, category-mix shifts and missingness injection.
4. Implement outlier, unseen-category, duplicate-key and invalid-value scenarios.
5. Implement source-outage scenarios.
6. Implement synthetic concept/performance deterioration using synthetic labels only.
7. Preserve untouched control cohorts.
8. Define expected metric direction and expected final state.
9. Prevent scenario metadata from being lost during ingestion.
10. Label M6 evidence explicitly:
   - `SYNTHETIC_SCENARIO_EVIDENCE`
   - `NOT_EMPIRICAL_PERFORMANCE`
   - `NOT_EXTERNAL_VALIDATION`

## Required deliverables

```text
src/credit_risk_monitoring/scenarios/
configs/scenarios/
contracts/scenario_contract.json
tests/scenarios/
```

Generated scenario data remains local-only.

## Completion criteria

- Scenarios are deterministic.
- Expected conditions are independently testable.
- Synthetic evidence cannot be confused with empirical evidence.

---

# Phase 6 - Data-Quality and Source Monitoring

## Objective

Establish whether the cohort is safe and meaningful to monitor before interpreting drift.

## Monitoring domains

### Schema

- Required fields.
- Unexpected fields.
- Duplicate columns.
- Dtype compatibility.
- Batch and cohort identity.

### Completeness

- Missing count and rate.
- Change from reference missingness.
- Structural versus unexpected missingness.
- Critical source coverage.

### Validity

- Numeric finiteness.
- Binary 0/1 domains.
- Categorical type and unseen categories.
- Range and impossible-value rules.
- Period and timestamp validity.

### Integrity

- Unique, complete applicant keys.
- Row counts.
- Join coverage.
- Source-to-feature reconciliation.
- Output row preservation.

## Tasks

1. Implement reusable validation results with structured fields.
2. Classify checks as hard gate, warning, diagnostic or informational.
3. Compare current results with frozen reference expectations.
4. Distinguish valid structural missingness from source failure.
5. Detect total and partial bureau/previous/external-score availability loss.
6. Implement critical-source policy hooks.
7. Block scoring or authoritative interpretation where required.
8. Produce feature-level and run-level results.

## Required output fields

```text
run_id
cohort_id
scope
feature_or_source
check_name
reference_value
current_value
threshold
severity
gate_class
status
evidence_detail
```

## Completion criteria

- Stable scenario passes.
- Corruption and source-outage scenarios produce expected hard gates.
- Downstream monitoring cannot ignore a failed gate.

---

# Phase 7 - Population and Feature Drift

## Objective

Measure whether the incoming applicant population differs materially from the frozen input reference.

## Core metrics

- PSI for numeric and categorical predictors.
- KS statistic and p-value for numeric predictors.
- Wasserstein distance as a numeric diagnostic.
- Chi-square statistic and p-value for categorical predictors.
- Cramer's V as an optional categorical effect-size diagnostic.
- Missingness and category-share changes.

Jensen-Shannon divergence is outside core scope unless later justified through change control.

## Tasks

1. Apply frozen numeric bins.
2. Include missing and tail buckets.
3. Apply frozen categorical levels plus missing and unseen buckets.
4. Stabilize zero-frequency calculations using a documented epsilon policy.
5. Emit bin-level PSI contributions.
6. Emit total feature PSI.
7. Calculate statistical diagnostics.
8. Prevent p-values from independently driving alerts.
9. Define feature materiality tiers using Part A evidence.
10. Implement multiple-feature aggregation rules.
11. Track critical source-dependent features separately.
12. Record top contributors without suppressing the full 176-feature result.

## Required tests and checks

- Hand-calculated PSI fixtures.
- Identical population produces zero or near-zero drift.
- Missing and unseen buckets reconcile.
- Constant and sparse features behave safely.
- Large samples with small effects do not create p-value-only alerts.
- All 176 features receive a result or an explicit reason for non-assessability.

## Completion criteria

- M1/M2 preserve their observed TRAIN-versus-`application_test` drift state without assuming that an unmodified cohort must be `NORMAL`.
- M3 records the mild injected drivers descriptively without requiring a threshold crossing.
- M4 identifies intended drivers without tuning frozen bins or thresholds to the observed result.
- Prospective scenario signals remain diagnostics rather than acceptance targets.

---

# Phase 8 - Score and Observation-Time Threshold Monitoring

## Objective

Monitor DF-01 output behaviour immediately, without requiring outcomes.

## Score metrics

- Count of scored applicants.
- Mean, median and standard deviation of raw PD.
- Minimum and maximum PD.
- P10, P25, P50, P75 and P90.
- Fixed-bin score distribution.
- Score PSI.
- Optional fixed monitoring-band composition.

## Observation-time threshold metrics

- `risk_positive` count and rate.
- `risk_negative` count and rate.
- Change from reference classification rates.
- Probability mass near `0.080` using a predeclared boundary window.
- Threshold crossing sensitivity as a diagnostic only.

## Tasks

1. Score only after qualification and data-quality gates pass.
2. Use raw class-1 probability only.
3. Apply exactly `probability >= 0.080`.
4. Verify one output per input key.
5. Verify probability finiteness and range.
6. Calculate score distribution and score PSI.
7. Apply fixed monitoring bands if approved.
8. Keep monitoring bands separate from frozen risk classes.
9. Do not calculate recall, specificity or precision in this phase.

## Completion criteria

- Golden and regression parity remain intact.
- Stable cohorts reproduce expected score behaviour.
- Severe scenario produces expected score/decision shift.
- No 0.5 threshold is introduced anywhere.

---

# Phase 9 - Outcome Maturity, Performance and Calibration Monitoring

> Execution-plan amendment (2026-08-23): the later Phase 9 plan authorized after Phase 8 consolidates outcome availability, maturity, discrimination, calibration, frozen-band and `THRESHOLD-01` realised-performance monitoring in this phase. It supersedes the narrower legacy descriptions in the original Phase 9–12 roadmap for this execution. Future phase numbering remains subject to the Phase 9 owner decision.

## Objective

Ensure only eligible, sufficiently complete outcomes enter performance monitoring.

## Tasks

1. Validate the outcome contract.
2. Reconcile outcomes to scored applicants.
3. Detect duplicate, conflicting and missing outcomes.
4. Record outcome extraction and as-of times.
5. Evaluate contractual maturity when the true horizon becomes available.
6. Support a clearly labelled two-month simulation lag for the demonstration.
7. Assign maturity state.
8. Calculate outcome coverage and unresolved counts.
9. Prohibit performance calculation for `UNMATURED`, `PARTIALLY_MATURED`, and `NOT_AVAILABLE` cohorts.
10. Distinguish outcome immaturity from insufficient mature sample size.
11. Retain late-arriving and corrected outcome audit history.

## Required deliverables

```text
src/credit_risk_monitoring/outcomes/contract.py
src/credit_risk_monitoring/outcomes/maturity.py
src/credit_risk_monitoring/outcomes/reconciliation.py
tests/outcomes/
```

## Completion criteria

- Ineligible cohorts cannot enter performance functions.
- Mature synthetic scenario is correctly admitted and labelled synthetic.
- Outcome corrections are traceable rather than silently overwritten.

---

# Phase 10 - Discrimination Monitoring

## Objective

Assess ranking performance only on eligible matured cohorts.

## Metrics

Primary:

- ROC-AUC.
- KS.

Secondary:

- PR-AUC.
- Gini, explicitly identified as `2 * ROC-AUC - 1`.

## Tasks

1. Enforce maturity eligibility.
2. Enforce binary target and both-class presence.
3. Apply minimum evidence requirements.
4. Calculate point estimates.
5. Calculate protocol-approved uncertainty intervals.
6. Compare with the approved Part A performance reference.
7. Evaluate absolute level and deterioration.
8. Prevent tiny, uncertain changes from generating unsupported conclusions.
9. Record event rate and sample composition alongside performance.
10. Mark non-assessable or insufficient cohorts explicitly.

## Required tests and checks

- Known metric fixtures.
- Single-class outcome is not assessable.
- Immature cohort is rejected.
- Insufficient sample yields `INSUFFICIENT_DATA`.
- Synthetic deterioration triggers the intended state.

## Completion criteria

- Results reconcile with trusted library calculations.
- Uncertainty handling is documented and tested.
- No synthetic result is presented as external evidence.

---

# Phase 11 - Calibration and Portfolio Outcomes

## Objective

Assess whether raw DF-01 probabilities remain aligned with observed default outcomes on eligible mature cohorts.

## Metrics

- Mean predicted PD.
- Observed default rate.
- Expected default count.
- Observed default count.
- O/E ratio.
- Brier score.
- Log loss.
- Probability bias.
- Fixed calibration bands.
- Calibration curve.
- Calibration intercept and slope when numerically assessable.

## Tasks

1. Enforce maturity and sample sufficiency.
2. Use raw probabilities without fitting a calibrator.
3. Apply fixed reference calibration bands.
4. Show mean predicted PD versus observed rate per band.
5. Handle zero expected or observed events safely.
6. Define O/E warning and critical ranges before scenario evaluation.
7. Calculate uncertainty for observed rates and O/E where approved.
8. Treat failed calibration regressions as undefined, not zero or failed performance.
9. Record probability-quality results separately from discrimination.
10. Preserve DF-01 immutability even when recalibration is recommended.

## Completion criteria

- Calibration fixtures reconcile.
- Fixed bands remain unchanged across periods.
- Unstable regression diagnostics do not corrupt the run.
- Recommendations do not alter DF-01.

---

# Phase 12 - Matured Threshold-Policy Monitoring

## Objective

Evaluate realised behaviour of the frozen `0.080` analytical risk-classification policy on eligible mature cohorts.

## Metrics

- Recall/default capture.
- Specificity.
- Precision.
- Confusion matrix.
- Risk-positive rate.
- Risk-negative rate.
- Risk-negative default rate.
- Optional F1 as secondary evidence only.

## Tasks

1. Apply exactly `>= 0.080`.
2. Reconcile classifications with Phase 8 outputs.
3. Enforce mature outcomes.
4. Enforce threshold/error-rate minimum evidence rules.
5. Compare default capture with the project-defined 70% assumption.
6. Use uncertainty-aware breach logic.
7. Avoid automatic threshold adjustment.
8. Preserve analytical `risk_positive`/`risk_negative` language.
9. Record that the threshold is not an economic lending policy or regulatory standard.

## Completion criteria

- Boundary and confusion-matrix tests pass.
- Immature or insufficient cohorts do not produce misleading metrics.
- Any recommendation for threshold revision explicitly requires a new governed model version.

---

# Phase 13 - Governed Subpopulation Monitoring

## Objective

Use one generic, configuration-driven engine to monitor all 12 frozen Part A subgroup families.

## Required subgroup families

1. Bureau history.
2. Previous-application history.
3. Joint bureau/previous history.
4. Housing-information availability.
5. Car-age availability.
6. Employment sentinel.
7. Bureau-request availability.
8. External-score availability.
9. Gender.
10. Age band.
11. Region rating.
12. Contract type.

Gender and age analysis remains exploratory and is not fairness certification.

## Minimum evidence rules inherited from Part A

Discrimination or calibration:

- Total records `>= 1000`.
- Defaults `>= 50`.
- Non-defaults `>= 50`.

Threshold or error-rate analysis:

- Total records `>= 500`.
- Defaults `>= 50`.
- Non-defaults `>= 50`.

These are project-defined feasibility rules, not universal standards.

## Tasks

1. Build one `SegmentMonitor` driven by configuration.
2. Reproduce frozen subgroup definitions exactly.
3. Report every configured level and count.
4. Prohibit post-result category consolidation.
5. Calculate observation-time volume, PD and composition for all assessable groups.
6. Calculate matured performance, calibration and threshold metrics only when eligible.
7. Compare subgroup with overall and complement where approved.
8. Apply minimum-evidence rules.
9. Return `INSUFFICIENT_DATA` rather than normal or critical when minimums fail.
10. Configure the dashboard to highlight only 3-4 informative families while retaining full evidence.

## Completion criteria

- All 12 families run through one generic implementation.
- Frozen definitions and minimums reconcile with Part A.
- Sparse groups cannot generate misleading health states.

---

# Phase 14 - Alert and Escalation Engine

## Objective

Convert metric and control results into governed, traceable alerts and decisions.

## Alert record

```text
alert_id
run_id
cohort_id
created_at
model_id
model_version
reference_version
scope_type
scope_name
metric_name
current_value
reference_value
threshold
severity
lifecycle_status
first_seen
last_seen
breach_count
evidence_path
recommended_action
owner_role
due_date
resolution_record
```

## Tasks

1. Separate control failures from model/business deterioration.
2. Implement hard gates.
3. Implement warning and critical thresholds.
4. Implement repeated-breach escalation.
5. Deduplicate recurring alerts by governed identity.
6. Preserve first-seen and last-seen history.
7. Implement acknowledgement and resolution transitions.
8. Implement multiple-feature aggregation.
9. Implement critical-feature logic.
10. Define overall run and model-health status.
11. Prevent `INSUFFICIENT_DATA` and `NOT_ASSESSABLE` from becoming normal.
12. Map alerts to investigation and governance actions.

## Permitted recommendations

- Continue ordinary monitoring.
- Continue with enhanced monitoring.
- Investigate upstream source quality.
- Investigate population or business-process change.
- Increase monitoring frequency.
- Review calibration.
- Restrict model use.
- Trigger formal model review.
- Recommend a new recalibrated or redeveloped version.

Recommendations do not themselves authorize a model change.

## Completion criteria

- Stable scenario produces no unsupported alerts.
- Repeated warnings escalate as specified.
- Critical control failures prevent authoritative completion.
- Alert lifecycle transitions are auditable.

---

# Phase 15 - Evidence, Persistence and Audit Trail

## Objective

Make every monitoring result traceable, reproducible and reviewable.

## Authoritative run package

```text
evidence/<cohort_id>/<run_id>/
├── run_contract.json
├── part_a_binding_snapshot.json
├── config_snapshot.yaml
├── input_inventory.json
├── qualification_results.json
├── data_quality.csv
├── feature_drift.csv
├── feature_drift_bins.csv
├── score_monitoring.csv
├── threshold_observation.csv
├── outcome_maturity.json
├── performance.csv
├── calibration.csv
├── threshold_performance.csv
├── subpopulation_results.csv
├── alerts.json
├── execution.log
├── runtime.json
├── completion_decision.json
├── manifest.json
└── manifest.sha256
```

Files that do not apply must be represented through an explicit non-applicability record rather than silently omitted where ambiguity would result.

## SQLite role

SQLite supports longitudinal queries, dashboards and alert lifecycle state. It is not the sole authoritative evidence source.

Suggested tables:

- `model_registry`
- `reference_registry`
- `monitoring_runs`
- `metric_results`
- `data_quality_results`
- `alerts`
- `alert_events`
- `outcome_maturity`
- `evidence_registry`

## Tasks

1. Define schemas and migrations.
2. Write evidence atomically.
3. Hash every authoritative artifact.
4. Hash the completed manifest.
5. Prevent mutation after finalization.
6. Reconcile SQLite rows to evidence run IDs.
7. Store only appropriate aggregate evidence in the public repository.
8. Exclude local full evidence and databases from Git.
9. Define recovery behaviour for partially written runs.
10. Record corrections through new events or superseding packages.

## Completion criteria

- Dashboard metric can be traced to SQLite, run ID and evidence artifact.
- Evidence hash verification passes.
- Failed finalization produces `EVIDENCE_FINALIZATION_FAILED`.
- Corrections do not silently rewrite finalized history.

---

# Phase 16 - End-to-End Monitoring Runner

## Objective

Expose the complete platform through one governed command and orchestration flow.

## Target interface

```powershell
python run_monitoring.py --period 2026-06 --batch <path> --outcomes <optional-path>
```

## Required execution order

```text
Create run contract
        |
Verify Part A binding
        |
Run runtime qualification
        |
Validate and adapt inputs
        |
Run data-quality gates
        |
Score DF-01
        |
Run feature and score monitoring
        |
Run observation-time threshold monitoring
        |
Ingest and evaluate outcomes, if supplied
        |
Run eligible performance/calibration/threshold analyses
        |
Run governed subpopulation monitoring
        |
Evaluate alerts and overall state
        |
Finalize evidence
        |
Persist SQLite history
        |
Write completion decision
```

## Tasks

1. Implement validated CLI arguments.
2. Generate unique run and cohort identifiers.
3. Prevent duplicate authoritative runs unless explicit replay mode is used.
4. Stop safely at hard gates.
5. Record partial diagnostic evidence on failure.
6. Make rerun/replay semantics explicit.
7. Return meaningful process exit codes.
8. Keep orchestration thin; business calculations remain in tested modules.
9. Support dry-run contract validation.
10. Produce a concise machine- and human-readable completion summary.

## Completion criteria

- One command processes every scenario appropriately.
- Hard failures stop downstream authoritative claims.
- Successful runs finalize evidence and persistence consistently.
- Reruns do not corrupt or duplicate history.

---

# Phase 17 - Test Suite and Independent Reconciliation

## Objective

Establish credible evidence that calculations, controls and governance behaviour work as designed.

## Unit-test coverage

- Part A hash binding.
- Golden-fixture parity.
- Schema enforcement.
- Key uniqueness.
- Feature-adapter reconciliation.
- Reference bin freezing.
- PSI calculations.
- Zero-frequency handling.
- Missing and unseen buckets.
- KS and Wasserstein calculations.
- Categorical tests.
- Score PSI.
- Frozen threshold boundary.
- Outcome maturity.
- ROC-AUC, PR-AUC, KS and Gini.
- Brier score, log loss and O/E.
- Calibration bands and regression failure handling.
- Confusion matrix and threshold metrics.
- Subgroup minimum evidence.
- Alert aggregation and deduplication.
- Evidence hashing.
- SQLite reconciliation.

## Regression tests

- DF-01 golden probabilities.
- DF-01 risk classes.
- Exact `>= 0.080` boundary.
- Reference snapshot and bin hashes.
- Stable monitoring-run outputs.

## Scenario tests

| Scenario | Expected result |
|---|---|
| Stable | `NORMAL` |
| Natural variation | `NORMAL` |
| Mild drift | `WARNING` |
| Severe drift | `CRITICAL` |
| Data corruption | Hard data-quality failure |
| Source outage | Hard gate or approved fallback state |
| Synthetic deterioration | Expected performance/calibration alert |
| Unmatured outcomes | Performance `NOT_ASSESSABLE` |
| Insufficient mature sample | `INSUFFICIENT_DATA` |

## Independent reconciliation

1. Recompute selected metrics through a separate simple implementation or trusted library path.
2. Verify model and threshold parity independently.
3. Verify manifests independently.
4. Review claims against evidence status.
5. Confirm Part A immutability.

## Completion criteria

- Full suite passes.
- Scenario expected-versus-actual register passes.
- Independent reconciliation has no unresolved critical exceptions.
- Test evidence is included in the release package.

---

# Phase 18 - Dashboard, Monitoring Report and Public Release

## Objective

Present governed monitoring evidence clearly without changing or overstating it.

## Dashboard pages

### 1. Model health

- DF-01 / XGBT-01 identity.
- Current monitoring cohort.
- Latest matured outcome cohort.
- Reference version.
- Run ID.
- Overall state.
- Domain-level states.
- Open warning and critical alerts.

### 2. Data quality and feature drift

- Source availability.
- Missingness changes.
- Top drifted features.
- Full feature table.
- Reference versus current distributions.
- PSI contributions and trend.

### 3. Score and threshold behaviour

- Mean and quantile PD trends.
- Score PSI.
- Reference versus current score distribution.
- Risk-positive and risk-negative rates.
- Probability mass near `0.080`.

### 4. Performance and calibration

- Mature cohorts only.
- ROC-AUC, KS, PR-AUC and Gini.
- Observed versus predicted default rate.
- O/E and Brier score.
- Calibration bands and curve.
- Latest observation versus latest matured period clearly distinguished.

### 5. Subpopulations

- Highlight 3-4 informative families.
- Retain access to all configured families.
- Show counts, events, average PD and eligible metrics.
- Display `INSUFFICIENT_DATA` and `NOT_ASSESSABLE` explicitly.

### 6. Alerts and run history

- Severity and lifecycle state.
- Evidence links.
- Recommended action.
- First seen, last seen and repeat count.
- Run completion history.

## Monitoring report structure

1. Executive summary.
2. Scope and evidence status.
3. Model and reference identity.
4. Observation and outcome periods.
5. Data quality and source availability.
6. Population and feature drift.
7. Score and threshold behaviour.
8. Discrimination, when eligible.
9. Calibration and portfolio outcomes, when eligible.
10. Threshold-policy outcomes, when eligible.
11. Subpopulation findings.
12. Active alerts.
13. Limitations and delayed-outcome status.
14. Investigation and possible contributors.
15. Recommendation and governance decision.
16. Evidence and reproducibility appendix.

Every material issue should distinguish:

- Observation.
- Evidence.
- Interpretation.
- Possible cause.
- Required investigation.
- Governance decision.

Possible causes must never be stated as established facts without evidence.

## Public-release tasks

1. Create reader-first README and project map.
2. Include architecture and lifecycle diagrams.
3. Include a curated synthetic sample run.
4. Exclude model binary, raw data, databases and row-level records.
5. Document local reproduction requirements.
6. Document all project-defined assumptions.
7. Document Part A relationship and conditions.
8. Run visual QA on dashboard and report.
9. Run link, licence, secret and repository-hygiene checks.
10. Optionally add scheduled execution only after core release quality passes.

## Completion criteria

- Dashboard values reconcile with evidence.
- Monitoring report passes content and visual QA.
- Unsupported claims are absent.
- Public repository contains no restricted artifacts.
- Release manifest and completion decision are approved.

---

## 8. Proposed repository architecture

```text
Part B - Model Monitoring Platform/
├── .github/
│   └── workflows/
├── configs/
│   ├── environments/
│   ├── scenarios/
│   ├── alert_thresholds.yaml
│   ├── monitoring_config.yaml
│   ├── reference_populations.yaml
│   └── subpopulations.yaml
├── contracts/
│   ├── schemas/
│   ├── evidence_schemas/
│   ├── part_a_binding.json
│   ├── scoring_input_contract.json
│   ├── scoring_output_contract.json
│   ├── outcome_contract.json
│   └── reference_snapshot_contract.json
├── dashboard/
│   ├── app.py
│   └── pages/
├── data/
│   ├── README.md
│   ├── external/
│   ├── interim/
│   └── processed/
├── docs/
│   ├── PROJECT_IMPLEMENTATION_PLAN.md
│   ├── PROJECT_MAP.md
│   ├── DOCUMENT_REGISTER.md
│   ├── DECISION_LOG.md
│   ├── REFERENCE_STRATEGY.md
│   ├── OUTCOME_MATURITY.md
│   └── ESCALATION_RUNBOOK.md
├── evidence/
│   ├── README.md
│   └── sample_public_run/
├── artifacts/
│   ├── reference_bins/
│   └── reference_snapshots/
├── notebooks/
│   └── README.md
├── reports/
│   ├── protocol/
│   ├── qualification/
│   ├── reference/
│   ├── monitoring/
│   ├── alerts/
│   └── release/
├── scripts/
├── src/
│   └── credit_risk_monitoring/
│       ├── qualification/
│       ├── contracts/
│       ├── ingestion/
│       ├── feature_adapter/
│       ├── reference/
│       ├── scenarios/
│       ├── data_quality/
│       ├── drift/
│       ├── scoring/
│       ├── outcomes/
│       ├── performance/
│       ├── calibration/
│       ├── decisions/
│       ├── subpopulations/
│       ├── alerts/
│       ├── evidence/
│       ├── storage/
│       ├── reporting/
│       └── pipeline/
├── tests/
│   ├── qualification/
│   ├── contracts/
│   ├── feature_adapter/
│   ├── unit/
│   ├── regression/
│   ├── integration/
│   └── scenarios/
├── .gitignore
├── CHANGE_CONTROL_POLICY.md
├── LICENSE
├── MONITORING_POLICY.md
├── pyproject.toml
├── README.md
├── requirements-lock.txt
└── run_monitoring.py
```

The full structure is a target architecture. Directories should be created when their phase begins, not filled with empty placeholder modules without purpose.

---

## 9. Public repository exclusion policy

Do not publicly commit:

- DF-01 or any fitted model binary.
- Standalone fitted preprocessors.
- Raw Kaggle data.
- Generated production or scenario cohorts.
- Row-level applicant features.
- Row-level predictions.
- Sensitive or row-level outcomes.
- Local SQLite databases.
- Full local monitoring evidence containing restricted records.
- Environment secrets, tokens or local absolute-path configuration.

The public repository may contain:

- Source code.
- Tests using synthetic fixtures.
- Contracts and schemas.
- Hash-bound Part A identity metadata.
- Aggregate reference descriptions where permitted.
- Curated synthetic monitoring evidence.
- Aggregate reports and screenshots.
- Documentation and governance policies.

---

## 10. Change-control triggers

The following changes require a new protocol or configuration version and documented approval:

- Monitoring purpose or scope.
- Model or model version.
- Probability representation.
- Threshold or comparator.
- Feature contract.
- Reference population or reference bins.
- Monitoring frequency.
- Outcome maturity rules.
- Metric definitions.
- Alert limits.
- Overall-health aggregation.
- Critical-feature list.
- Subgroup definitions or sufficiency rules.
- Evidence schema.
- Escalation roles or actions.

Changes to DF-01 itself are outside ordinary Part B change control and require a new model-governance lifecycle.

---

## 11. Phase status tracker

Update this table only when supported by a phase completion decision.

| Phase | Status | Completion decision | Notes |
|---:|---|---|---|
| 0 | `COMPLETE` | `reports/protocol/MONITORING-PROTOCOL-01/phase0_completion_decision.json` | Protocol approved and frozen on 2026-08-21 |
| 1 | `COMPLETE` | `reports/qualification/RUNTIME-QUALIFICATION-01/phase1_completion_decision.json` | Approved and frozen on 2026-08-22 |
| 2 | `COMPLETE` | `reports/reference/REFERENCE-STRATEGY-01/phase2_completion_decision.json` | Approved and frozen on 2026-08-22 |
| 3 | `COMPLETE` | `reports/adapter/FEATURE-ADAPTER-QUALIFICATION-01/phase3_completion_decision.json` | Conditional review blocker resolved; approved and frozen on 2026-08-22 |
| 4 | `COMPLETE` | `reports/reference/REFERENCE-MATERIALIZATION-01/phase4_completion_decision.json` | Approved and frozen on 2026-08-22 |
| 5 | `COMPLETE` | `reports/simulation/SIMULATION-SCENARIO-SET-01/phase5_completion_decision.json` | Conditional blocker resolved; approved and frozen on 2026-08-22 |
| 6 | `COMPLETE` | `reports/monitoring/DATA-QUALITY-CONTROL-01/phase6_completion_decision.json` | Conditional source-role blocker resolved; approved and frozen on 2026-08-22 |
| 7 | `COMPLETE` | `reports/monitoring/FEATURE-DRIFT-MONITORING-01/phase7_completion_decision.json` | Approved and frozen on 2026-08-22; Phase 8 authorized |
| 8 | `COMPLETE` | `reports/monitoring/PREDICTION-MONITORING-01/phase8_completion_decision.json` | Approved and frozen on 2026-08-23; Phase 9 authorized |
| 9 | `IN_PROGRESS` | `reports/monitoring/OUTCOME-PERFORMANCE-MONITORING-01/phase9_completion_decision.json` | Technical qualification passed on 2026-08-23; owner review pending; Phase 10 unauthorized |
| 10 | `NOT_STARTED` | Not issued |  |
| 11 | `NOT_STARTED` | Not issued |  |
| 12 | `NOT_STARTED` | Not issued |  |
| 13 | `NOT_STARTED` | Not issued |  |
| 14 | `NOT_STARTED` | Not issued |  |
| 15 | `NOT_STARTED` | Not issued |  |
| 16 | `NOT_STARTED` | Not issued |  |
| 17 | `NOT_STARTED` | Not issued |  |
| 18 | `NOT_STARTED` | Not issued |  |

Allowed status values:

- `NOT_STARTED`
- `IN_PROGRESS`
- `BLOCKED`
- `COMPLETE`
- `SUPERSEDED`

---

## 12. Immediate next actions

The next controlled action is owner review of the technically qualified Phase 9 candidate:

1. Review `OUTCOME-PERFORMANCE-MONITORING-01`, its manifest and acceptance checklist.
2. Confirm M01–M05 remain `NOT_ASSESSABLE` and only M06 uses synthetic outcome evidence.
3. Confirm performance, calibration and threshold results are descriptive metrics with severity `N/A` and no alerts.
4. Approve and freeze Phase 9 separately if the evidence is accepted.
5. Keep Phase 10 closed until that explicit owner decision is recorded.

Phase 9 is technically qualified but not complete or frozen. Phase 10 is not authorized.
