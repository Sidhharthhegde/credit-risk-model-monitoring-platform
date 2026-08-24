# Architecture

## System boundary

Part B is a local, production-shaped model-risk monitoring demonstration. It reads the frozen Part A `DF-01 / XGBT-01` model binding and governed Part B evidence; it does not contain the fitted model or claim production deployment.

```text
Frozen Part A binding + governed source data
                    |
     Phases 0-11 monitoring evidence
                    |
      Phase 12 SQLite query/lifecycle layer
              /                     \
 Phase 13 dashboard          Phase 14 report
              \                     /
        Phase 14 verification orchestrator
                    |
   Phase 15 scheduler-safe wrapper + receipts
                    |
 Phase 15 governed investigation casebook
```

## Authority model

Frozen phase artifacts are authoritative evidence. The Phase 12 database is rebuildable and non-authoritative. The dashboard, report and scheduled receipts are derived governance and operational-control artifacts. `INVESTIGATION-CASEBOOK-01` copies governed source evidence and keeps it semantically separate from the approved authoritative project investigation assessment. That authority covers only the project's interpretation and disposition, never an authoritative metric calculation, production decision or regulatory conclusion. A derived layer cannot change an upstream severity, eligibility, evidence type, model output or threshold decision.

## Model Risk Evidence System presentation

The Phase 15 presentation redesign retains the frozen Phase 13 six-page contract while applying an authored navigation layer: Control Room, Input Integrity, Drift Observatory, Model Behaviour, Outcome Evidence and Investigation Desk. Its product identity is built from a lifecycle signal spectrum: input/mint, drift/violet, model/electric blue, outcome/amber, alert/coral and lineage/ice. Those product voices are separate from the frozen governed severity palette.

Shared components provide the Model Passport, non-calendar Scenario Lab, evidence-signal topology, THRESHOLD-01 probability spectrum, dossiers, lineage and governed-unavailable states. The Investigation Desk opens with four consolidated casebook chapters before the governed Alert Queue, Segments, Lifecycle and Lineage workspaces. Large evidence ledgers preserve their governed order while exposing 12/25/50-row presentation slices. Chart, table, dossier and investigation modes render one instrument at a time; session-local query reuse is invalidated when the Phase 12 database revision changes. The monitoring pages consume immutable dashboard view models; the Casebook reads only its version-controlled, hash-bound derived package and does not calculate monitoring decisions.

## Investigation evidence boundary

Every dossier binds the frozen Phase 11 and Phase 12 manifests, the Phase 12 immutable-evidence semantic digest, and the complete operational database semantic digest at extraction. Each approved case artifact identifies its primary alert and source-record key; the dashboard has no independent primary-evidence mapping. A later legitimate lifecycle event may change operational state without implying that frozen monitoring evidence changed: the dossier retains status at extraction, while queue navigation uses `All` current statuses and selects the exact alert ID. The four dossiers cover TRAIN-reference/application-test availability differences, M04 material predictor drift, M06 synthetic performance deterioration and all three M05 source/contract-governance states. No case-management database, employee assignment, SLA timer, automated root-cause inference or alert closure is introduced.

## Frozen analytical interface

- model: `DF-01 / XGBT-01`
- output: raw `P(TARGET=1)`
- decision: `THRESHOLD-01`, probability `>= 0.080`
- Part A commit: `0f758a8ee76906b2a870ebacbdcac0ef6c951485`
- Phase 14 manifest: `dc63b5dd1834811d056146cf3f86287c50717fdee420ccb70db7b27f9431047a`

Phase 15 never refits, recalibrates, retunes or recalculates monitoring evidence. Its scheduled default invokes Phase 14 in `VERIFY_FROZEN` mode with report generation disabled.

## Persistence and state

The SQLite store exposes governed query views and an append-only alert-event ledger. Interactive lifecycle actions use the Phase 12 service. Scheduled execution is strictly read-only and reconciles complete semantic database digests plus alert and event counts before and after the run.

Execution receipts and aggregate JSONL events are local-only under `artifacts/scheduled_execution/`. Applicant records, predictions, labels and secrets are prohibited from these artifacts.
