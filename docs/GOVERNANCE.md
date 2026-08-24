# Governance and evidence interpretation

## Decision rights

The project owner approves frozen phase evidence, deployment cadence, scheduler identity, notification routing, retention changes and release publication. The code can technically qualify a release candidate; it cannot approve itself.

## Evidence dimensions

Eligibility, evidence type, source availability, governance authority and severity remain independent dimensions. Synthetic scenario evidence may be analytically eligible while remaining non-empirical. An unavailable source may still be technically scoreable while authoritative downstream use is prohibited.

## Thresholds

Monitoring thresholds and the six-hour stale-lock boundary are project-defined governance assumptions. They are not represented as regulation, supervisory mandates, or universal industry standards. `THRESHOLD-01` remains the frozen Part A operational threshold and is not replaced by optional risk bands.

## Release gate

Phase 15 candidate qualification left both `phase_15_complete` and `project_b_complete` false. The separate owner approval is now recorded in `PROJECT-RELEASE-01`; both completion fields are true and publication under `model-monitoring-platform-v1.0.0` is authorized. The annotated tag and GitHub release are external publication evidence rather than fields retroactively written into the tagged commit.

## Investigation authority

`INVESTIGATION-CASEBOOK-01` is an approved and frozen controlled Phase 15 addendum. Frozen monitoring evidence remains authoritative for metric values, severity, alerts, authorization, evidence scope and health. The casebook is not a calculation authority and cannot alter alert lifecycle state. Its authority is `APPROVED_AUTHORITATIVE_INVESTIGATION_RECORD` only for the project's interpretation and disposition of that frozen evidence. The separate Phase 15 owner decision completes Project B but does not authorize production or create an external-performance claim.

Primary-evidence selection belongs to each approved dossier and is bound by alert ID plus source-record key. The dashboard only renders that selection. Extraction-time alert status remains frozen in the dossier; current operational state is queried independently, and linked-alert navigation uses an unrestrictive status filter so a later legitimate lifecycle transition cannot hide the governed alert.

Documentation, trigger explanation, underlying cause, model-defect conclusion, remediation claim, open condition and owner review remain separate dimensions. `DOCUMENTED` never means `RESOLVED`, and a supported alert-trigger explanation does not establish an underlying business cause. Recommended owners are functions rather than fictitious employees, and closure evidence is proposed rather than system-enforced.

## Claims not made

This project does not claim:

- production approval or deployment;
- enterprise scheduling, IAM, availability, backup or incident-management controls;
- empirical validation from the unlabelled `application_test` data;
- external/OOT labelled validation, fairness certification or regulatory certification;
- calibration or realised-default confirmation from synthetic M06 outcomes.
- fairness, bias, Responsible-AI, production-remediation or root-cause conclusions from the investigation casebook.

`CND-02` therefore remains open.
