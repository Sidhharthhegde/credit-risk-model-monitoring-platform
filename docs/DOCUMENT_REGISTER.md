# Document Register

| Document | Current version | Status | Purpose |
|---|---:|---|---|
| `docs/PROJECT_IMPLEMENTATION_PLAN.md` | 0.2.1 | Active; Phase 1 technical qualification recorded | Detailed implementation roadmap |
| `MONITORING_POLICY.md` | 0.1.0 | Approved and frozen | Authoritative monitoring methodology and governance |
| `CHANGE_CONTROL_POLICY.md` | 0.1.0 | Approved and frozen | Model and monitoring change classification |
| `docs/DECISION_LOG.md` | 0.1.0 | Active | Controlled project decisions |
| `reports/protocol/MONITORING-PROTOCOL-01/` | 0.1.0 | Approved and frozen | Phase 0 approval, checklist, manifest and decision package |
| `contracts/part_a_binding.json` | 0.1.0 | Approved expected binding; technically verified in Phase 1 | Frozen Part A identity and hash contract |
| `reports/qualification/RUNTIME-QUALIFICATION-01/` | 0.1.0 | Approved and frozen | Phase 1 binding, runtime, exact parity, control-state and immutability evidence |
| `contracts/reference_strategy.json` | 0.1.0 | Approved and frozen | Authoritative reference roles and physical snapshot mapping |
| `contracts/reference_snapshot_contract.json` | 0.1.0 | Approved and frozen | Future snapshot metadata contract |
| `docs/REFERENCE_STRATEGY.md` | 0.1.0 | Approved explanatory document | Reader-oriented Phase 2 scope and sequencing |
| `reports/reference/REFERENCE-STRATEGY-01/` | 0.1.0 | Approved and frozen | Phase 2 specification evidence and manifest |
| `contracts/monitoring_feature_adapter_contract.json` | 0.1.0 | Approved and frozen | Executable scope and invariants for the label-free adapter |
| `reports/adapter/FEATURE-ADAPTER-QUALIFICATION-01/` | 0.1.0 | Approved and frozen | Phase 3 exact feature/scoring parity, branch coverage, failure controls, dry-run and immutability evidence |
| `src/credit_risk_monitoring/reference/` | 0.1.0 | Implemented and tested | Phase 4 materialization, statistics, binning, reproducibility and qualification logic |
| `reports/reference/REFERENCE-MATERIALIZATION-01/` | 0.1.0 | Approved and frozen | Sanitized aggregate Phase 4 evidence and manifest; no row-level snapshots |
| `artifacts/reference_snapshots/REFERENCE-MATERIALIZATION-01/` | 0.1.0 | Local-only, approved and frozen | Restricted Parquet snapshots, metadata, lifecycle evidence and manifests; ignored by Git |
| `contracts/simulation_scenario_contract.json` | 0.1.0 | Approved and frozen | Prospective six-cohort scenario design and transformation policy |
| `src/credit_risk_monitoring/simulation/` | 0.1.0 | Implemented and tested | Deterministic assignment, scenario transformation, source degradation and synthetic-outcome generation |
| `reports/simulation/SIMULATION-SCENARIO-SET-01/` | 0.1.0 | Approved and frozen | Sanitized Phase 5 construction and integrity evidence; no applicant-level data or monitoring results |
| `artifacts/simulation_scenarios/SIMULATION-SCENARIO-SET-01/` | 0.1.0 | Local-only, approved and frozen | Restricted cohort, scenario, diagnostic and synthetic-outcome Parquet artifacts; ignored by Git |
| `contracts/data_quality_monitoring_contract.json` | 0.1.0 | Approved and frozen | Phase 6 control registry, threshold bindings, governed source-control roles, result vocabularies and scope barriers |
| `src/credit_risk_monitoring/data_quality/` | 0.1.0 | Implemented and tested | Reusable read-only schema, grain, completeness, validity, novelty, range, source and reconciliation engine |
| `reports/monitoring/DATA-QUALITY-CONTROL-01/` | 0.1.0 | Approved and frozen | Aggregate Phase 6 monitoring evidence with no row-level offenders, alerts or drift results |
| `contracts/feature_drift_monitoring_contract.json` | 0.1.0 | Approved and frozen | Phase 7 eligibility, frozen-bin, PSI, diagnostic, materiality-lineage and scope contract |
| `src/credit_risk_monitoring/drift/` | 0.1.0 | Implemented and tested | Frozen-bin PSI, bin reconciliation and supporting numeric/categorical diagnostics |
| `reports/monitoring/FEATURE-DRIFT-MONITORING-01/` | 0.1.0 | Approved and frozen | Aggregate Phase 7 evidence for six eligible artifacts plus two explicit exclusions |
| `contracts/prediction_monitoring_contract.json` | 0.1.0 | Approved and frozen | Phase 8 model, score-reference, frozen-bin, threshold-output, gate and scope contract |
| `src/credit_risk_monitoring/prediction/` | 0.1.0 | Implemented and tested | Qualified raw scoring, prediction integrity, score PSI and analytical threshold-output monitoring |
| `artifacts/monitoring_predictions/PREDICTION-MONITORING-01/` | 0.1.0 | Local-only, approved and frozen | Six governed row-level prediction artifacts with semantic and physical hashes; ignored by Git |
| `reports/monitoring/PREDICTION-MONITORING-01/` | 0.1.0 | Approved and frozen | Aggregate Phase 8 evidence with no row-level predictions, outcomes, alerts or overall-health results |
| `contracts/outcome_performance_monitoring_contract.json` | 0.1.0 | Approved and frozen | Phase 9 outcome availability, simulation maturity, evidence eligibility, metric, severity and scope contract |
| `src/credit_risk_monitoring/outcome/` | 0.1.0 | Implemented and tested | Exact prediction/outcome reconciliation plus synthetic performance, calibration-band and threshold-performance calculations |
| `reports/monitoring/OUTCOME-PERFORMANCE-MONITORING-01/` | 0.1.0 | Approved and frozen | Aggregate Phase 9 synthetic evidence; no joined row-level evidence, alerts, subgroup results or overall health |
| `contracts/segment_monitoring_contract.json` | 0.1.0 | Frozen prospective specification; evidence approved | Phase 10 definition, reference, sufficiency, severity and scope contract; unchanged during result approval |
| `src/credit_risk_monitoring/segment/` | 0.1.0 | Implemented and tested | Generic frozen-definition assignment, segment reference, label-free and sufficiency-gated outcome engine |
| `reports/monitoring/SEGMENT-MONITORING-01/` | 0.1.0 | Approved and frozen | Aggregate Phase 10 evidence across 12 families and 32 frozen levels; no row-level membership, alerts, fairness certification or overall health |
| `configs/alert_aggregation_policy.yaml` | 0.1.1 | Approved and frozen | Phase 11 metric roles, criticality, explicitly directed performance controls, authorization, health, lifecycle and persistence rules |
| `contracts/alert_engine_contract.json` | 0.1.1 | Approved and frozen | Phase 11 read-only dependency, fail-closed directionality, policy, scope and aggregation contract |
| `src/credit_risk_monitoring/alert/` | 0.1.1 | Implemented and tested | Generic breach qualification, deterministic alerts, lifecycle, persistence, component and overall-health engine |
| `reports/monitoring/ALERT-ENGINE-01/` | 0.1.1 | Approved and frozen | Aggregate Phase 11 policies, alerts, authorization, evidence-scope, health and approval evidence |
| `contracts/monitoring_history_contract.json` | 0.1.1 | Approved and frozen | Phase 12 authority model, frozen sources, identities, temporal rules and source-versus-current count semantics |
| `schemas/monitoring_history_schema.sql` | 1 | Approved and frozen | Versioned SQLite tables, dynamic lifecycle views, constraints, indexes, immutability and continuity controls |
| `migrations/001_initial_monitoring_history.sql` | 1 | Approved and frozen | Executable initial SQLite migration identical to the governed schema |
| `src/credit_risk_monitoring/history/` | 0.1.1 | Implemented and tested | Fail-closed ingestion, semantic digests, append-only lifecycle persistence and parameterized query repository |
| `artifacts/monitoring_history/MONITORING-HISTORY-01/` | 0.1.1 | Local-only; approved and rebuildable | Generated SQLite database; ignored by Git and not authoritative evidence |
| `reports/persistence/MONITORING-HISTORY-01/` | 0.1.1 | Approved and frozen | Aggregate Phase 12 schema, ingestion, reconciliation, lifecycle, temporal, query, lineage, rebuild and approval evidence |
| `contracts/monitoring_dashboard_contract.json` | 0.1.0 | Approved and frozen | Phase 13 presentation authority, Phase 12 binding, six-page scope, lifecycle and temporal semantics |
| `configs/dashboard_display_policy.yaml` | 0.1.0 | Approved and frozen | Governed display labels, disclosures and context-only segment registry; contains no monitoring thresholds |
| `src/credit_risk_monitoring/dashboard/` | 0.1.0 | Approved implementation | Thin Phase 12 data service, immutable view models, six Streamlit pages and fixture-only qualification |
| `reports/dashboard/MONITORING-DASHBOARD-01/` | 0.1.0 | Approved and frozen | Aggregate Phase 13 reconciliation, lifecycle, scope, temporal, lineage, smoke and approval evidence |
| `configs/model_config.yaml` | 0.1.0 | Approved and frozen | Semantic model metadata referencing the binding |
| `configs/monitoring_config.yaml` | 0.1.0 | Approved and frozen | Monitoring scope and execution policy |
| `configs/alert_thresholds.yaml` | 0.1.0 | Approved and frozen | Project-defined alert assumptions |
| `configs/subpopulations.yaml` | 0.1.0 | Approved and frozen | Governed Part A subgroup definitions |

Finalized documents must be superseded through a new version. They must not be silently rewritten after approval.
