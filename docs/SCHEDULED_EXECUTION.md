# Scheduled execution

## Default command

```powershell
python scripts/run_scheduled_monitoring.py --profile VERIFY_FROZEN
```

The default command acquires an exclusive lock, verifies Phase 14 and Part A bindings, verifies the frozen report, reads the Phase 12 query layer, reconciles database and alert lifecycle state, writes an aggregate receipt, and exits with a stable machine code.

## Exit codes

| Code | Meaning |
|---:|---|
| 0 | Success |
| 10 | Configuration or contract failure |
| 20 | Frozen-source verification failure |
| 21 | Manifest-chain failure |
| 22 | Immutable-evidence digest failure |
| 30 | Active lock |
| 31 | Invalid or stale lock |
| 40 | Frozen-write attempt |
| 50 | Orchestration failure |
| 60 | Report or query failure |
| 70 | Dependency or environment failure |
| 80 | Receipt or logging failure |
| 99 | Unexpected failure |

## Lock handling

An active lock rejects a second execution. A stale lock also rejects by default. After investigating the prior process, an operator may run with `--recover-stale-lock`; the wrapper copies the stale lock into the new run directory before replacement. A corrupt lock always fails closed and cannot be automatically recovered.

The six-hour stale boundary is a project-defined governance assumption, not a universal operating standard.

## Receipts and logs

Local output is stored under:

```text
artifacts/scheduled_execution/SCHEDULED-EXECUTION-01/
├── execution.lock.json                 # present only while a run owns the lock
└── runs/<execution_id>/
    ├── execution_receipt.json
    ├── execution_events.jsonl
    └── recovered_stale_lock.json       # only after explicit recovery
```

No automatic deletion occurs under `NO_AUTOMATIC_DELETION_V1`. Receipt deletion or archival requires an approved deployment-specific retention policy.

## Deployment

Examples are in [`deployment/scheduling/`](../deployment/scheduling/README.md). They contain placeholders and intentionally omit cadence. Do not treat them as an installed scheduler or production service.
