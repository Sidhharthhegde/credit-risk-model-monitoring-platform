# Credit Risk Model Monitoring Platform

A governance-first, production-shaped monitoring platform for the frozen Part A credit-risk model `DF-01 / XGBT-01`.

Part B will demonstrate data-quality monitoring, population and feature drift, raw score drift, frozen-threshold behaviour, delayed-outcome controls, discrimination, calibration, governed subpopulation monitoring, alerts, escalation, and reproducible audit evidence.

## Current status

`PHASE_7_APPROVED_FROZEN`

Phases 0–7 are approved and frozen. `FEATURE-DRIFT-MONITORING-01` retains frozen-bin PSI and supporting distribution diagnostics for the six Phase 6 downstream-eligible artifacts. Its component state is explicitly not overall model health or an alert lifecycle event. Phase 8 prediction and threshold-output monitoring is authorized; outcome-dependent monitoring remains unauthorized.

## Important scope statement

DF-01 was not granted production approval and is not represented as actually deployed. Part B is a portfolio and model-risk demonstration using simulated production-shaped cohorts.

The unlabelled Home Credit `application_test` population may support data quality, feature drift, score drift, and analytical risk-class distribution monitoring. It cannot independently support realised discrimination, calibration, threshold performance, external validation, or transportability claims.

## Frozen model dependency

- Development freeze: `DF-01`
- Model: `XGBT-01`
- Version: `xgbt01_raw_threshold01_df_v1`
- Probability: raw `P(TARGET=1)`
- Threshold: `THRESHOLD-01`, raw probability `>= 0.080`
- Part A repository: <https://github.com/Sidhharthhegde/credit-risk-model-validation-suite>

The fitted model remains in the governed local Part A workspace. It is not copied into this repository. Part B binds to it through [`contracts/part_a_binding.json`](contracts/part_a_binding.json).

## Start here

1. [`docs/PROJECT_IMPLEMENTATION_PLAN.md`](docs/PROJECT_IMPLEMENTATION_PLAN.md)
2. [`MONITORING_POLICY.md`](MONITORING_POLICY.md)
3. [`CHANGE_CONTROL_POLICY.md`](CHANGE_CONTROL_POLICY.md)
4. [`docs/DECISION_LOG.md`](docs/DECISION_LOG.md)

## Licence

Project code is licensed under the MIT License. Dataset files remain subject to their original terms and are not relicensed by this repository.
