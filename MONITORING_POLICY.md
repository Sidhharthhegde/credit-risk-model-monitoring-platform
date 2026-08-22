# Monitoring Policy

**Protocol ID:** `MONITORING-PROTOCOL-01`  
**Version:** `0.1.0`  
**Status:** `APPROVED_FROZEN`  
**Owner:** Sidharth Ravindra Hegde  
**Effective date:** 2026-08-21  
**Model:** `DF-01 / XGBT-01`

## 1. Purpose

This policy defines the prospective monitoring methodology, controls, evidence requirements, and escalation framework for Part B before monitoring calculations are implemented or executed.

The purpose is to demonstrate how the frozen Part A model would be monitored in a production-shaped environment. The project is a portfolio and model-risk demonstration. It is not evidence that DF-01 was deployed, used for real lending decisions, or approved for production.

## 2. Scope

The policy covers:

- Model binding and runtime qualification.
- Scoring-input and scoring-output controls.
- Data quality and source availability.
- Population and feature drift.
- Raw probability and analytical risk-class drift.
- Delayed-outcome ingestion and maturity.
- Discrimination and calibration when evidence is eligible.
- Frozen-threshold performance when evidence is eligible.
- Governed subgroup monitoring.
- Alert creation, escalation, evidence, and audit history.

The policy does not authorize:

- Production deployment.
- Approval or rejection decisions.
- Automatic recalibration, refitting, threshold adjustment, or redevelopment.
- External-performance claims without genuinely new labelled external or OOT data.
- Fairness certification or regulatory certification.

## 3. Relationship to Part A

Part A is the authoritative source for the frozen model, preprocessing, probability representation, threshold, feature contract, validation evidence, and remaining conditions.

Part B must access Part A read-only. It binds to Part A through `contracts/part_a_binding.json`, verifies the governed artifact before monitoring, and never copies the fitted model into the public repository.

## 4. Frozen model identity

The authoritative technical identity is maintained only in `contracts/part_a_binding.json`.

The monitored model is:

- Development freeze `DF-01`.
- Model `XGBT-01`.
- Version `xgbt01_raw_threshold01_df_v1`.
- Fitted sklearn pipeline with embedded preprocessing and XGBoost classifier.
- 176 governed raw predictors and 306 encoded predictors.
- Raw class-1 probability `P(TARGET=1 default | governed model inputs)`.
- Frozen analytical threshold `THRESHOLD-01` using probability `>= 0.080`.

The labels `risk_positive` and `risk_negative` are analytical decision proxies. They do not mean loan rejected or approved.

## 5. Production-shaped simulation disclaimer

DF-01 is not represented as actually deployed. Part B uses simulated monitoring cohorts to exercise production-shaped controls and longitudinal monitoring behaviour.

The monthly cadence and two-month outcome lag are demonstration assumptions. Simulated months are scenario labels, not observed calendar production periods in `application_test`.

Required wording:

> To demonstrate post-development monitoring, DF-01 is evaluated within a simulated production-shaped monitoring environment.

Prohibited wording:

> After DF-01 was deployed in production.

## 6. Model immutability

DF-01 is immutable.

Part B may calculate metrics, identify deterioration, generate alerts, recommend investigation, or recommend review of recalibration, threshold policy, refitting, or redevelopment.

Part B may not:

- Refit DF-01.
- Alter its embedded preprocessing.
- Add, remove, or revise predictors.
- Replace raw probability with a transformed probability.
- Add a calibrator.
- Change `THRESHOLD-01`.
- Replace the artifact.

Any implemented model change requires a new model identity, validation record, and governance lifecycle. It does not overwrite DF-01.

## 7. Monitoring populations

### 7.1 Input-distribution reference

The TRAIN deterministic base supplies the feature-distribution and preprocessing reference. Permitted uses include frozen PSI-bin creation, missingness reference, categorical reference frequencies, data-quality comparisons, and numeric or categorical distribution diagnostics.

Reference ID: `FEATURE-REF-01`.

### 7.2 Performance reference

The development-validation population supplies the primary internal analytical performance, calibration, and threshold-performance reference.

Reference ID: `PERF-REF-01`.

### 7.3 Threshold-selection lineage

TRAIN OOF evidence documents how `THRESHOLD-01` was selected. It is selection lineage, not the sole monitoring performance baseline.

Reference ID: `THRESHOLD-SELECTION-REF-01`.

### 7.4 Threshold-performance reference

Development-validation evidence supplies the primary comparator for later matured threshold-policy metrics.

Reference ID: `THRESHOLD-PERF-REF-01`.

### 7.5 Historical third split

The historically exposed third split is supplementary internal context only. It is not an untouched holdout, external population, or OOT population.

Reference ID: `HISTORICAL-CONTEXT-01`.

### 7.6 Unlabelled monitoring simulation

The historical Home Credit `application_test` population may be adapted into simulated observation cohorts.

Permitted uses:

- Data-quality monitoring.
- Feature and population drift.
- Score drift.
- Analytical risk-class composition.
- Source-availability assessment.

Prohibited uses without labels:

- Realised ROC-AUC, PR-AUC, KS, or Gini.
- Calibration or O/E.
- Brier score against outcomes.
- Recall, specificity, precision, or realised confusion matrix.
- External-performance or transportability conclusions.

Population ID: `APPLICATION-TEST-SIM-01`.

## 8. Reference version policy

Reference definitions must be approved before materialization. Reference statistics and bins may be created only after Part A binding, runtime qualification, and feature-adapter qualification pass.

Once `FEATURE-REF-01` is materialized:

- Bin edges do not change during ordinary monitoring runs.
- Missing and unseen-category buckets remain fixed.
- Monitoring periods apply the same bins.
- Reference changes require a new reference ID and approved protocol/configuration change.
- Previous references and their evidence remain retained.

## 9. Data contracts

### 9.1 Scoring input

The scoring input contains complete unique `SK_ID_CURR` and exactly the 176 governed raw predictors.

It does not require `TARGET`, a probability, or a risk class.

The contract inherits Part A rules:

- Exact feature set followed by canonical reorder.
- Numeric values must use compatible numeric dtypes and may not contain infinity.
- Governed numeric missingness is allowed.
- Non-missing categorical values must be strings.
- Governed categorical missingness is allowed.
- Unseen categories are permitted by the frozen encoder and may generate monitoring alerts without automatically failing scoring.
- Binary features must be complete numeric 0/1 values.

Training ranges and closed category vocabularies are monitoring references, not new hard scorer contracts.

### 9.2 Scoring output

The scoring output contains applicant ID, raw probability, frozen threshold identity and value, analytical risk class, model identity and version, run ID, and scoring timestamp.

One valid output must exist per accepted scoring input.

### 9.3 Outcomes

Outcomes are a separate governed object containing applicant ID, cohort, binary outcome, observation dates, maturity state, source, receipt time, and reconciliation status.

Scoring inputs must never be rejected merely because outcomes are unavailable.

## 10. Monitoring frequency

The demonstration uses monthly simulated monitoring periods. Monthly cadence is a project-defined simulation assumption, not a statement about the frequency an institution must use for DF-01.

## 11. Outcome maturity

Part A defines `TARGET=1` as observed default but does not establish a contractual performance horizon. The contractual horizon and reporting lag remain unresolved until supported by an approved target definition.

A two-month lag may be used solely to demonstrate delayed-outcome architecture.

Maturity states are:

- `UNMATURED`: the applicable observation period is incomplete.
- `PARTIALLY_MATURED`: some outcomes exist but the cohort is not fully mature.
- `MATURED`: the applicable observation period is complete.
- `NOT_AVAILABLE`: no usable outcome source is present.

Evidence eligibility is separate:

- `ELIGIBLE`: mature and all outcome-quality and minimum-evidence controls pass.
- `INSUFFICIENT_DATA`: mature but sample or event minimums fail.
- `NOT_ASSESSABLE`: another limitation prevents a defensible calculation.

Only `MATURED + ELIGIBLE` cohorts may enter authoritative outcome-dependent monitoring.

## 12. Label-free monitoring

Label-free monitoring is available immediately after input acceptance and scoring.

It covers:

- Schema and applicant-key integrity.
- Missingness and validity.
- Source availability.
- Feature PSI.
- Numeric KS and Wasserstein diagnostics.
- Categorical chi-square diagnostics.
- Raw PD summary and distribution.
- Score PSI.
- Risk-positive and risk-negative rates.
- Probability mass near the frozen threshold, after the boundary window is approved.

## 13. Outcome-dependent monitoring

Outcome-dependent monitoring requires `MATURED + ELIGIBLE` evidence.

It covers:

- ROC-AUC and performance KS as primary discrimination measures.
- PR-AUC and Gini as secondary evidence.
- Observed default rate, mean PD, O/E, Brier score, log loss, and fixed calibration bands.
- Recall/default capture, specificity, precision, confusion matrix, and risk-negative default rate at `0.080`.
- Eligible subgroup outcome metrics.

No 0.5 threshold may be introduced.

## 14. Metric inventory and alert roles

The prospective metric inventory is maintained in `configs/metric_registry.csv`.

Metrics are classified as:

- `DIRECT`: may generate a monitoring alert when an approved threshold exists.
- `HARD_GATE`: may invalidate the run or its authority.
- `SUPPORTING`: investigation evidence that does not independently create an alert.
- `DIRECT_PENDING_THRESHOLD`: retained and reported, but non-alerting until a versioned threshold rule is approved.

Statistical p-values never generate an alert independently.

## 15. Data-quality controls

Data-quality monitoring covers schema, completeness, validity, integrity, applicant grain, join coverage, source coverage, and output reconciliation.

Data-quality findings must distinguish:

- Expected structural missingness.
- Unexpected missingness deterioration.
- Unseen but technically accepted categories.
- Invalid values rejected by the frozen scorer contract.
- Source-level degradation or outage.

## 16. Source-availability policy

Source failures are classified by their effect:

- `SOURCE_TECHNICALLY_REQUIRED`: scoring cannot construct the governed input; hard failure.
- `SOURCE_POLICY_REQUIRED`: scoring may remain technically possible, but authoritative operational use requires an approved fallback.
- `SOURCE_DEGRADED`: partial loss or material coverage deterioration; alert and investigate.
- `SOURCE_UNAVAILABLE_NO_APPROVED_FALLBACK`: diagnostic scoring may be retained, but the run cannot receive authoritative operational completion.

Part A showed that DF-01 can remain finite during external-source loss while performance and classifications change materially. Therefore technical scoreability must not be confused with governance authorization.

No approved external-source fallback currently exists. This preserves Part A condition `CND-02`.

## 17. Population and feature drift

Core feature-drift metric:

- PSI using fixed reference bins.

Supporting diagnostics:

- Numeric KS statistic and p-value.
- Wasserstein distance.
- Categorical chi-square statistic and p-value.
- Optional Cramer's V when approved.

Implementation must include explicit missing, unseen, and tail buckets and a documented zero-frequency policy.

All 176 predictors receive a result or explicit non-assessability reason. Dashboard prioritization must not suppress the full evidence record.

## 18. Prediction and threshold-output monitoring

Observation-time prediction monitoring uses raw class-1 probability only.

It includes:

- Count, mean, median, standard deviation, minimum, maximum, and approved quantiles.
- Fixed score distribution and score PSI.
- Risk-positive and risk-negative counts and rates.
- Change from frozen reference rates.

Optional low/medium/high monitoring bands require approved fixed definitions and must not replace the two frozen analytical risk classes.

## 19. Performance monitoring

ROC-AUC and KS are primary. PR-AUC is retained because the outcome is imbalanced and Part A used it as authoritative evidence. Gini is secondary and must be identified as derived from ROC-AUC.

Point-estimate changes alone do not establish deterioration. Before performance alerts are enabled, the protocol must approve uncertainty handling, minimum practical deterioration, and warning/critical rules.

Until then, performance measures are reported as diagnostic evidence and cannot create an automated alert.

## 20. Calibration monitoring

Calibration monitoring uses raw DF-01 probabilities and may not fit a calibrator.

It includes observed default rate, expected default count, observed default count, O/E, Brier score, log loss, fixed calibration bands, and calibration curve. Intercept and slope are optional when numerically assessable.

O/E and Brier alerts remain disabled until a versioned amendment approves two-sided limits and uncertainty handling.

## 21. Threshold-policy monitoring

Observation-time threshold-output monitoring includes risk-positive and risk-negative rates.

Matured threshold-performance monitoring includes recall/default capture, specificity, precision, confusion matrix, and risk-negative default rate.

The 70% capture requirement is a project-defined Part A risk-control assumption. It is not an economic lending threshold or regulatory standard. Breach logic must account for uncertainty and may not automatically change the threshold.

## 22. Subpopulation monitoring

One generic configured engine evaluates the 12 frozen Part A subgroup families defined in `configs/subpopulations.yaml`.

The engine retains all groups. The dashboard may highlight only the most informative 3-4 families.

Gender and age results are exploratory model-monitoring evidence, not fairness certification.

## 23. Minimum evidence

Inherited Part A project-defined feasibility rules are:

Discrimination and calibration:

- At least 1,000 records.
- At least 50 defaults.
- At least 50 non-defaults.

Threshold and error-rate analysis:

- At least 500 records.
- At least 50 defaults.
- At least 50 non-defaults.

Failure produces `INSUFFICIENT_DATA`, not `NORMAL` or `CRITICAL`.

## 24. Threshold philosophy

PSI, missingness, novelty, and risk-class-rate thresholds in `configs/alert_thresholds.yaml` are proposed project-defined governance assumptions. They are not regulatory requirements or universal standards.

Metrics without approved alert limits have `alert_enabled: false`. This is a deliberate non-alerting state, not an implicit threshold.

## 25. Status dimensions

Metric severity, evidence eligibility, outcome maturity, alert lifecycle, and run control are separate dimensions. An ineligible metric has severity `N/A`; it must not be reported as normal.

## 26. Hard gates

Hard gates include:

- Model artifact hash mismatch.
- Frozen schema mismatch.
- Golden-fixture prediction or threshold mismatch.
- Missing or duplicate applicant keys.
- Missing governed predictor.
- Duplicate predictor.
- Invalid binary value.
- Non-finite or out-of-range probability.
- Technically required source failure.
- Evidence finalization failure.

A failed run may retain diagnostic evidence but cannot be described as an authoritative successful monitoring run.

## 27. Repeat breaches and health aggregation

Initial proposed logic is:

- One warning creates an open warning alert.
- Two consecutive warnings for the same governed identity escalate investigation.
- A critical breach escalates immediately.
- A hard control failure produces overall `NOT_ASSESSABLE`, not critical model performance.
- Otherwise, any critical domain produces overall `CRITICAL`.
- No critical and at least one warning produces overall `WARNING`.
- All eligible domains normal produces overall `NORMAL`.
- Unmatured performance does not force the overall result to normal or critical.

## 28. Alert lifecycle and escalation

Alert lifecycle states are `OPEN`, `ACKNOWLEDGED`, and `RESOLVED`.

Action levels are:

- Level 0 `CONTINUE_MONITORING`.
- Level 1 `INVESTIGATE`.
- Level 2 `ENHANCED_MONITORING`.
- Level 3 `FORMAL_MODEL_REVIEW`.
- Level 4 recommendation for `RECALIBRATION_REVIEW`, `THRESHOLD_REVIEW`, or `MODEL_REDEVELOPMENT`.

A recommendation does not authorize model modification.

## 29. Synthetic evidence

Synthetic outcomes may be used to test monitoring behaviour only. Every applicable cohort, run, report, and evidence package must state:

- `SYNTHETIC_SCENARIO_EVIDENCE`.
- `empirical_performance: false`.
- `external_validation: false`.

Synthetic outcomes do not support claims about realised DF-01 performance.

## 30. Evidence retention

Every run must preserve a run contract, Part A binding snapshot, configuration snapshot, input inventory and hashes, qualification results, metric tables, maturity decision, alerts, runtime, log, completion decision, manifest, and manifest hash.

SQLite is the query and presentation layer. Finalized run files and hashes are the authoritative evidence.

Corrections require a new event or superseding package. Finalized evidence is not silently overwritten.

## 31. Public and local evidence

Public artifacts may include source code, schemas, configuration templates, documentation, tests, synthetic examples, and sanitized aggregate reports.

The public repository excludes model binaries, raw data, local databases, generated cohorts, row-level predictions, row-level outcomes, credentials, and local absolute paths.

## 32. Known limitations

- No actual production deployment or population is observed.
- `application_test` is unlabelled.
- The contractual outcome horizon is unresolved.
- Monthly cadence and two-month lag are simulations.
- Alert limits are project-defined assumptions.
- Performance alert limits are not yet active.
- No approved source-outage fallback currently exists.
- External performance and transportability remain unassessed.
- Subpopulation monitoring is not fairness certification.
- Cross-platform scoring parity remains subject to runtime qualification.

## 33. Protocol approval and amendment

This policy became effective when the project/protocol owner approved `MONITORING-PROTOCOL-01` on 2026-08-21. Its approved manifest hash is recorded in the protocol package. The policy is frozen; later methodological changes require a versioned amendment.

Any later change to model binding, reference definitions, metrics, alert thresholds, outcome maturity, subgroup definitions, minimum evidence, health aggregation, escalation, or evidence rules requires a new configuration or protocol version under `CHANGE_CONTROL_POLICY.md`.
