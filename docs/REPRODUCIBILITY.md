# Reproducibility

## Public clone

A public clone supports source review, contract inspection, aggregate evidence review and dependency-light release checks:

```powershell
python scripts/verify_public_release.py
python -m pytest -q tests/release/test_public_release.py
```

Public CI runs only those checks. It does not download restricted data, copy the Part A model, rebuild the ignored history database or execute full monitoring.

## Governed local qualification

Full local qualification requires:

- the frozen Part A repository at the sibling workspace path and exact bound commit;
- the governed raw and derived local data excluded from Git;
- the ignored Phase 12 SQLite database or inputs required to rebuild it;
- Python 3.12 dependencies pinned in `requirements-lock.txt`.

Run the complete local regression suite with:

```powershell
python -m pytest
```

Run frozen unattended verification with:

```powershell
python scripts/run_scheduled_monitoring.py --profile VERIFY_FROZEN
```

The receipt records Phase 14 binding, report verification, before/after database semantics, lock outcome, status and exit code. It intentionally contains aggregate control facts only.

## Replay boundary

`ISOLATED_QUALIFICATION_REPLAY` is a qualification profile, not the scheduled default. It writes only beneath the selected run directory and may not overwrite Phase 0–14 evidence. Reproducibility means deterministic governed outputs from the same bound inputs; it does not mean excluded licensed or restricted inputs are bundled publicly.
