# Public dashboard deployment

The portfolio dashboard is prepared for Streamlit Community Cloud as a public, read-only application.

Deployment adapter version: `1.0.1`. The frozen Project B release remains `1.0.0`.

## Deployment coordinates

- Repository: `Sidhharthhegde/credit-risk-model-monitoring-platform`
- Branch: `main`
- Entrypoint: `streamlit_app.py`
- Python: `3.12`

## Runtime design

The public repository intentionally excludes the local Phase 12 SQLite database. On a cold start, `streamlit_app.py` enables public-demo mode and deterministically materializes an ephemeral SQLite query copy from the frozen aggregate Phase 0–11 evidence already committed to the repository.

The bootstrap must match the frozen Phase 12 complete semantic digest before the dashboard opens. The database remains non-authoritative and disposable; frozen report packages remain authoritative.

Public mode is deliberately read-only:

- alert acknowledgement and resolution are disabled;
- no monitoring metric, alert, severity or model-health result is recalculated;
- no model binary, raw application data or applicant-level prediction is required;
- the governed HTML report is offered as a device-safe download instead of a local `file://` link;
- a cold restart reconstructs the same initial 329-event lifecycle state.

## Deploy

1. Sign in to [Streamlit Community Cloud](https://share.streamlit.io/) with the GitHub account that administers the repository.
2. Select **Create app**.
3. Enter the repository, branch and entrypoint coordinates above.
4. Select Python 3.12 and deploy.

No secrets are required for this public repository deployment.
