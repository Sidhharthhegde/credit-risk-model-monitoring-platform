# Scheduler deployment templates

These examples invoke the Phase 15 `VERIFY_FROZEN` profile. They deliberately do not select a cadence: cadence, service identity, credential storage, notification routing and retention obligations are deployment-owner decisions.

Before enabling either template:

1. create an isolated Python 3.12 environment and install `requirements-lock.txt`;
2. replace every `__...__` placeholder;
3. run `python scripts/run_scheduled_monitoring.py` interactively and inspect its receipt;
4. configure the scheduler to treat every non-zero governed exit code as a failure;
5. protect the local `artifacts/scheduled_execution/` directory and monitoring-history database;
6. define external log collection and notification routing where required.

The default profile verifies frozen evidence. It does not recalculate monitoring results, regenerate the Phase 14 report, mutate alert lifecycle state, or represent enterprise production deployment.

Stale locks fail closed. An operator may use `--recover-stale-lock` only after investigating the prior run; the recovered lock is copied into the new run directory as evidence.

Receipts use `NO_AUTOMATIC_DELETION_V1`. Any later retention or deletion policy requires separate owner approval and must preserve applicable audit obligations.
