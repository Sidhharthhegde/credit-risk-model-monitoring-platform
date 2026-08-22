# Reference Strategy

`REFERENCE-STRATEGY-01` defines the populations, semantic roles, physical snapshot design, adapter boundary, future statistics, bin methodology, contamination controls, qualification rules, and evidence requirements that must govern later reference construction.

This is a specification-only phase. No row-level reference snapshot, descriptive statistic, bin edge, score distribution, simulated cohort, drift value, performance result, or alert is created here.

The authoritative role registry is `contracts/reference_strategy.json`. A physical snapshot may support more than one semantic role; in particular, `DEV-VAL-PHYSICAL-01` supports both `PERF-REF-01` and `THRESHOLD-PERF-REF-01`. Physical reuse does not make the roles interchangeable.

Every comparison metric must declare its governed `reference_id`. An absolute contract-only metric may instead declare `NOT_APPLICABLE_CONTRACT_ONLY`; it may never silently use an unnamed DataFrame as a baseline.

The Phase 2 approval gate does not authorize reference materialization. Phase 3 must first implement and qualify the label-free feature adapter. Phase 4 may materialize references only after that qualification and its own entry authorization.
