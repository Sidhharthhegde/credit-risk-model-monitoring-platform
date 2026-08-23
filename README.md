# Credit Risk Model Monitoring Platform

A governance-first, production-shaped monitoring platform for the frozen Part A credit-risk model `DF-01 / XGBT-01`.

Part B will demonstrate data-quality monitoring, population and feature drift, raw score drift, frozen-threshold behaviour, delayed-outcome controls, discrimination, calibration, governed subpopulation monitoring, alerts, escalation, and reproducible audit evidence.

## Current status

`PHASE_14_APPROVED_FROZEN`

Phases 0–14 are approved and frozen. Phase 14 produced the governed HTML/PDF monitoring report, verification-first lifecycle orchestrator and final-lifecycle technical qualification. Project B is not complete: Phase 15 scheduled/unattended execution and final project release remains authorized and pending.

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

## Run the dashboard

From this repository, use `scripts/run_phase13_dashboard.py` with the isolated dependencies in `requirements-lock.txt`. The interface is a local, non-authoritative presentation and investigation layer; lifecycle actions are written only through the Phase 12 append-only service.

## Architecture

```text
Frozen Part A model and governed Part B evidence
  -> Phase 12 SQLite query/lifecycle layer
  -> Phase 13 dashboard and Phase 14 monitoring report
  -> Phase 14 verification and reproducibility evidence
```

The dashboard and report are presentation artifacts. Frozen source artifacts remain authoritative.

## Local commands

Run tests:

```powershell
python -m pytest
```

Rebuild the local Phase 12 history store:

```powershell
python scripts/run_phase12_qualification.py
```

Generate or verify the current monitoring report:

```powershell
python scripts/run_monitoring_lifecycle.py --mode verify-frozen
```

Run isolated semantic replay qualification:

```powershell
python scripts/run_monitoring_lifecycle.py --mode qualification-replay
```

Full local replay requires the governed local model, raw data and ignored row-level artifacts. The public repository supports architecture review, aggregate evidence, tests and semantic verification; it does not claim to recreate excluded governed inputs immediately after cloning.

## Final limitations

- `CND-02` remains open.
- Threshold-boundary-density monitoring remains `CONTROLLED_DEFERRED`.
- M06 performance is synthetic scenario evidence, not empirical production performance.
- The model is not represented as deployed or approved for production.
- No external validation, fairness certification or regulatory certification is claimed.

## Licence

Project code is licensed under the MIT License. Dataset files remain subject to their original terms and are not relicensed by this repository.
