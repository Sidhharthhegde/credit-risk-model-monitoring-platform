# Decision Log

## Decision statuses

- `PROPOSED`
- `APPROVED`
- `REJECTED`
- `SUPERSEDED`

## Decisions

| Decision ID | Date | Status | Decision | Rationale |
|---|---|---|---|---|
| PB-DEC-001 | 2026-08-21 | APPROVED | Part B uses a separate Git repository. | Preserves the frozen Part A repository and separates lifecycle workstreams. |
| PB-DEC-002 | 2026-08-21 | APPROVED | Part B is described as production-shaped simulation, not actual deployment. | Part A did not grant production approval. |
| PB-DEC-003 | 2026-08-21 | APPROVED | DF-01 remains immutable. | Monitoring cannot silently change a frozen validated model. |
| PB-DEC-004 | 2026-08-21 | APPROVED | Part B binds to the local Part A model by identity and hashes and does not copy the fitted binary. | Avoids artifact duplication and preserves Part A authority. |
| PB-DEC-005 | 2026-08-21 | APPROVED | Input, scoring output, and outcome data use separate contracts. | Prevents target/prediction fields from being incorrectly required at scoring input. |
| PB-DEC-006 | 2026-08-21 | APPROVED | TRAIN, development validation, TRAIN OOF, historical third split, and `application_test` have distinct reference roles. | No single available population supports every monitoring purpose. |
| PB-DEC-007 | 2026-08-21 | APPROVED | Monthly cadence and a two-month outcome lag are simulation assumptions only. | Part A does not define an actual deployment cadence or contractual outcome horizon. |
| PB-DEC-008 | 2026-08-21 | APPROVED | All 12 Part A subgroup families are retained through one generic configured engine. | Preserves governance continuity without duplicate implementations. |
| PB-DEC-009 | 2026-08-21 | APPROVED | Full local evidence packages are authoritative; SQLite is a query and history layer. | Mutable database history alone is insufficient for reproducibility. |
| PB-DEC-010 | 2026-08-21 | APPROVED | Protocol version `MONITORING-PROTOCOL-01` is authoritative and Phase 0 is complete. | Approved by `USER_PROTOCOL_OWNER`; the three controlled-deferred items remain inactive and Phase 1 is authorized. |
| PB-DEC-011 | 2026-08-22 | APPROVED | Phase 1 scorer parity uses the exact equality rules inherited from Part A golden-fixture evidence. | Qualification must reproduce the frozen scorer; a newly introduced loose tolerance would weaken the established control. |
| PB-DEC-012 | 2026-08-22 | APPROVED | Phase 1 source-outage work qualifies technical scoring and governance-authorization control states only. | Source-loss performance or drift analysis belongs to later monitoring phases and is not authorized during qualification. |
| PB-DEC-013 | 2026-08-22 | APPROVED | The phase after approved runtime qualification is Phase 2 reference strategy and snapshot specification, not reference materialization. | Reference definitions require prospective approval before statistics, bins, or snapshots are created. |
| PB-DEC-014 | 2026-08-22 | APPROVED | Accept and freeze `RUNTIME-QUALIFICATION-01`; Phase 1 is complete. | All technical acceptance checks passed and `USER_PROTOCOL_OWNER` approved the qualification evidence. |
| PB-DEC-015 | 2026-08-22 | APPROVED | Authorize entry into Phase 2 reference strategy and snapshot specification only. | Reference definitions must be approved before statistics, bins, snapshots, scenarios, or monitoring outputs are materialized. |
| PB-DEC-016 | 2026-08-22 | APPROVED | Use JSON as the authoritative reference registry and metadata contract, with CSV as the human-readable role matrix. | This provides dependency-free machine validation and prevents divergence between duplicate YAML and JSON authorities. |
| PB-DEC-017 | 2026-08-22 | APPROVED | Require Phase 3 label-free adapter qualification before Phase 4 reference materialization. | Phase 0 prohibits materialization until feature-adapter qualification passes; Phase 2 approval alone cannot bypass that gate. |
| PB-DEC-018 | 2026-08-22 | APPROVED | Use development validation as the primary score-distribution comparator and TRAIN scoring only as supporting in-sample context. | Honest validation inference is the cleaner score baseline while TRAIN remains the primary input-distribution and PSI-bin source. |
| PB-DEC-019 | 2026-08-22 | APPROVED | Assign simulated `application_test` cohorts by deterministic SHA-256 ordering and round-robin allocation. | This produces reproducible, disjoint, exhaustive and balanced simulation labels without inventing calendar chronology. |
| PB-DEC-020 | 2026-08-22 | APPROVED | Accept and freeze `REFERENCE-STRATEGY-01`; Phase 2 is complete. | All specification checks passed and `USER_PROTOCOL_OWNER` approved the reference strategy evidence. |
| PB-DEC-021 | 2026-08-22 | APPROVED | Authorize Phase 3 contracts and label-free feature-adapter implementation and qualification only. | Reference materialization remains prohibited until the adapter proves the exact governed 176-feature interface. |
| PB-DEC-022 | 2026-08-22 | APPROVED | Bridge the frozen deterministic function's training-only TARGET presence check with a temporary internal placeholder and require exact placeholder-value invariance. | This reuses Part A code without requiring caller labels, copying feature logic, modifying Part A, or allowing TARGET to affect or enter adapter output. |
| PB-DEC-023 | 2026-08-22 | APPROVED | Use the lowest 256 labelled TRAIN applicant IDs as the deterministic exact-parity fixture. | The governed selection rule is reproducible, covers raw-source construction, and avoids unnecessary duplicate full-population reconstruction. |
| PB-DEC-024 | 2026-08-22 | APPROVED | Persist only aggregate dry-run qualification diagnostics; never persist the Phase 3 candidate frame, row-level predictions, score summaries, or simulated cohorts. | Phase 3 proves technical adaptation without prematurely materializing or analyzing the monitoring population. |
| PB-DEC-025 | 2026-08-22 | APPROVED | Require imported Part A feature modules to resolve to their exact hash-verified filesystem paths. | File-hash verification alone does not prevent Python from resolving a same-named module from another import location. |
| PB-DEC-026 | 2026-08-22 | APPROVED | Require labelled parity evidence to cover all four history combinations and material deterministic/missingness branches. | Implementation equivalence depends on branch coverage, not merely deterministic sample size. |
| PB-DEC-027 | 2026-08-22 | APPROVED | Define the parity base as the lowest 256 applicants from Part A's frozen TRAIN split, with minimal deterministic supplements only if coverage is absent. | This corrects population lineage and preserves reproducibility; observed coverage required no supplemental applicants. |
| PB-DEC-028 | 2026-08-22 | APPROVED | Accept and freeze `FEATURE-ADAPTER-QUALIFICATION-01`; Phase 3 is complete. | The conditional branch-coverage blocker passed and all parity, dry-run, source-control and scope gates reconcile. |
| PB-DEC-029 | 2026-08-22 | APPROVED | Authorize Phase 4 reference materialization and frozen-bin construction only. | Adapter qualification now supports governed baseline construction; monitoring execution remains unauthorized. |
