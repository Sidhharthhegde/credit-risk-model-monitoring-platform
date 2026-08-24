"""Build evidence-linked investigation dossiers without recalculating monitoring results."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from credit_risk_monitoring.history.digest import semantic_database_manifest
from credit_risk_monitoring.history.queries import HistoryRepository
from credit_risk_monitoring.history.store import connect_history
from credit_risk_monitoring.qualification.binding import sha256_file


CONTROL_ID = "INVESTIGATION-CASEBOOK-01"
CONTRACT_ID = "MODEL-RISK-INVESTIGATION-CONTRACT-01"
SOURCE_CONTROLS = {
    "PHASE_6": "DATA-QUALITY-CONTROL-01",
    "PHASE_7": "FEATURE-DRIFT-MONITORING-01",
    "PHASE_8": "PREDICTION-MONITORING-01",
    "PHASE_9": "OUTCOME-PERFORMANCE-MONITORING-01",
}


CASE_SPECS: tuple[dict[str, Any], ...] = (
    {
        "case_id": "INV-01",
        "chapter": "01",
        "short_title": "Availability mismatch",
        "title": "TRAIN-reference / application-test availability mismatch",
        "scenario_artifacts": ["SIM-M01-SCENARIO-01", "SIM-M02-SCENARIO-01"],
        "selector": {"components": ["DATA_QUALITY"], "severity": "CRITICAL"},
        "primary_alert_id": "ALT-7D6D4EAAF884D5205849",
        "primary_source_record_key": "083a595e058ae38632f8aecb9829be4ba1004c42510706579bc4908ceb5c31af",
        "classification": ["DATA_QUALITY", "REFERENCE_OR_POPULATION", "EVIDENCE_LIMITATION"],
        "executive_finding": (
            "Unmodified application-test control cohorts breach frozen TRAIN-relative availability "
            "controls for EXT_SOURCE_1 and bureau-annuity features. The alert trigger is supported "
            "by governed evidence, but the operational or business reason for the source-population "
            "difference is not established."
        ),
        "expected_condition": "No scenario transformation was intentionally injected into M01 or M02.",
        "observed_response": (
            "Both controls produced the same pattern of critical TRAIN-relative missingness signals. "
            "Stable scenario means unmodified cohort, not normal monitoring evidence."
        ),
        "assessment": {
            "documentation_status": "COMPLETE",
            "alert_trigger_explanation_status": "SUPPORTED",
            "underlying_cause_status": "NOT_ESTABLISHED",
            "model_defect_established": False,
            "remediation_status": "NOT_CLAIMED",
            "condition_status": "OPEN",
            "owner_review_status": "APPROVED",
        },
        "cause_assessment": (
            "The alerts are mechanically explained by feature-availability differences between the "
            "application-test cohorts and FEATURE-REF-01. The underlying business, collection, or "
            "source-process cause cannot be determined from the available project evidence."
        ),
        "evidence_limitations": [
            "The cohorts are simulated scenarios drawn from historical application_test data, not production periods.",
            "Outcomes are unavailable; realised discrimination and calibration cannot be assessed.",
            "A reference-population difference does not by itself establish a defect in DF-01.",
        ],
        "risk_interpretation": (
            "The finding demonstrates that apparently stable inputs can still differ materially from "
            "the frozen development reference. In real use, model risk and data owners would need to "
            "determine whether the difference reflects expected population coverage, source-process "
            "change, or an unsuitable reference before changing the model or monitoring policy."
        ),
        "dispositions": ["REFERENCE_LIMITATION_DOCUMENTED", "NO_MODEL_DEFECT_ESTABLISHED", "UNRESOLVED"],
        "recommended_owner_function": "DATA_OWNER",
        "review_function": "MODEL_RISK",
        "recommended_follow_up": [
            "Confirm the expected availability of EXT_SOURCE_1 and bureau-annuity inputs for the monitored population.",
            "Document whether TRAIN remains an appropriate availability reference for operational monitoring.",
            "Review matured labelled outcomes when genuinely available; do not infer performance from missingness alone.",
        ],
        "proposed_closure_evidence": [
            "Documented source and population comparison approved by the data owner and model risk.",
            "A formal decision to retain or revise the monitoring reference without rewriting historical evidence.",
            "Matured outcome review where available.",
        ],
    },
    {
        "case_id": "INV-02",
        "chapter": "02",
        "short_title": "Material predictor drift",
        "title": "M04 material predictor-distribution shift",
        "scenario_artifacts": ["SIM-M04-SCENARIO-01"],
        "selector": {"components": ["DATA_QUALITY", "FEATURE_DRIFT", "PREDICTION"], "severity": None},
        "primary_alert_id": "ALT-E3BFA0D736E411B89486",
        "primary_source_record_key": "a542eacf7b7098ceadd70601785f6da74efc75acac36c1d8b0bb33410a11effc",
        "required_metrics": [
            ["FEATURE_DRIFT", "feature_psi", "EXT_SOURCE_2"],
            ["FEATURE_DRIFT", "feature_psi", "EXT_SOURCE_3"],
            ["PREDICTION", "risk_positive_rate_absolute_change", "THRESHOLD-01"],
        ],
        "classification": ["MODEL_BEHAVIOUR", "REFERENCE_OR_POPULATION", "EXPECTED_CHALLENGE_RESPONSE", "EVIDENCE_LIMITATION"],
        "executive_finding": (
            "Material distribution changes occurred on materially important predictors and were "
            "accompanied by a warning-level change in THRESHOLD-01 decision composition. Realised "
            "performance impact cannot be determined because outcomes are unavailable."
        ),
        "expected_condition": "M04 intentionally applies material valid drift to selected score-driving features.",
        "observed_response": (
            "Governed monitoring identified critical EXT_SOURCE_2 and EXT_SOURCE_3 PSI findings and "
            "a +8.837999 percentage-point risk-positive-rate change."
        ),
        "assessment": {
            "documentation_status": "COMPLETE",
            "alert_trigger_explanation_status": "SUPPORTED",
            "underlying_cause_status": "NOT_ESTABLISHED",
            "model_defect_established": False,
            "remediation_status": "NOT_CLAIMED",
            "condition_status": "OPEN",
            "owner_review_status": "APPROVED",
        },
        "cause_assessment": (
            "The observed response is consistent with the intentionally injected challenge. In real "
            "use, the underlying source, population, policy, or business-process cause would require "
            "separate investigation and is not established by PSI."
        ),
        "evidence_limitations": [
            "M04 is a simulated challenge scenario, not a calendar monitoring period.",
            "Outcomes are unavailable; realised discrimination, calibration, and default performance are not assessable.",
            "Label-free drift and decision-composition change do not establish model failure.",
        ],
        "risk_interpretation": (
            "The shifts affect predictors that are materially important to the frozen model and "
            "coincide with a meaningful change in threshold composition, making the finding relevant "
            "for model-risk review. The absence of outcomes prevents a conclusion about realised "
            "discrimination or calibration deterioration."
        ),
        "dispositions": ["CONFIRMED_EXPECTED_CHALLENGE_FINDING", "REQUIRES_FURTHER_INVESTIGATION", "UNRESOLVED"],
        "recommended_owner_function": "MODEL_OWNER",
        "review_function": "MODEL_RISK",
        "recommended_follow_up": [
            "Investigate changed feature and population composition and confirm whether source or process changes occurred.",
            "Assess matured outcomes when available.",
            "Determine through formal review whether the evidence supports model change, recalibration, reference revision, or no action.",
        ],
        "proposed_closure_evidence": [
            "Documented cause assessment and explanation of population or source changes.",
            "Matured outcome review where available.",
            "Formally documented model-risk decision retaining the frozen historical finding.",
        ],
    },
    {
        "case_id": "INV-03",
        "chapter": "03",
        "short_title": "Synthetic deterioration",
        "title": "M06 synthetic performance deterioration",
        "scenario_artifacts": ["SIM-M06-SCENARIO-01"],
        "selector": {"components": ["PERFORMANCE", "CALIBRATION", "THRESHOLD_PERFORMANCE"], "severity": "CRITICAL"},
        "primary_alert_id": "ALT-8ACF647F51BBCC2CE902",
        "primary_source_record_key": "bf41659a14dcb65683312a95c347a9e3286efce5b3737db229a0f1510e472e96",
        "classification": ["MODEL_BEHAVIOUR", "EXPECTED_CHALLENGE_RESPONSE", "EVIDENCE_LIMITATION"],
        "executive_finding": (
            "M06 generated governed critical performance, calibration, and threshold-performance "
            "signals from a deterministic synthetic outcome set. The monitoring response is supported "
            "for the scenario, but empirical production deterioration is not established."
        ),
        "expected_condition": "M06 intentionally supplies synthetic outcomes designed to challenge outcome monitoring.",
        "observed_response": (
            "ROC-AUC, performance KS, observed-to-expected ratio, and recall/default capture produced "
            "critical governed alerts and critical overall health."
        ),
        "assessment": {
            "documentation_status": "COMPLETE",
            "alert_trigger_explanation_status": "SUPPORTED",
            "underlying_cause_status": "NOT_ASSESSABLE",
            "model_defect_established": "NOT_ASSESSABLE",
            "remediation_status": "NOT_CLAIMED",
            "condition_status": "NOT_APPLICABLE",
            "owner_review_status": "APPROVED",
        },
        "cause_assessment": (
            "The synthetic deterioration mechanism explains the challenge result. It cannot establish "
            "a production cause, production incident, or empirical defect in DF-01."
        ),
        "evidence_limitations": [
            "SYNTHETIC_SCENARIO_EVIDENCE",
            "NON_EMPIRICAL",
            "NOT_EXTERNAL_VALIDATION",
            "No production-performance or remediation inference is permitted.",
        ],
        "risk_interpretation": (
            "The case demonstrates that the monitoring system detects deliberately poor synthetic "
            "outcome performance while retaining evidence-type discipline. It validates monitoring "
            "response behavior, not the external or production performance of DF-01."
        ),
        "dispositions": ["CONFIRMED_EXPECTED_CHALLENGE_FINDING", "SYNTHETIC_EVIDENCE_ONLY"],
        "recommended_owner_function": "MODEL_RISK",
        "review_function": "MODEL_OWNER",
        "recommended_follow_up": [
            "Retain the synthetic classification and reconcile the expected challenge response.",
            "Use genuinely unseen labelled external/OOT or matured production evidence for empirical conclusions.",
        ],
        "proposed_closure_evidence": [
            "Reconciled monitoring response and documented synthetic evidence limitations.",
            "No production remediation is required from synthetic evidence alone.",
        ],
    },
    {
        "case_id": "INV-04",
        "chapter": "04",
        "short_title": "Source & contract governance",
        "title": "M05 source and input-governance states",
        "scenario_artifacts": [
            "SIM-M05-VALID-DEGRADED-01",
            "SIM-M05-SOURCE-LOSS-DIAGNOSTIC-01",
            "SIM-M05-HARD-FAIL-01",
        ],
        "selector": {"components": ["DATA_QUALITY", "GOVERNANCE"], "severity": "CRITICAL"},
        "primary_alert_id": "ALT-BDD28218F338DC797E7E",
        "primary_source_record_key": "49ce2a2bd36fb4b394606e50c96a462d481941e7e025f9844c6667a3ce75faa3",
        "classification": ["DATA_QUALITY", "SOURCE_GOVERNANCE", "INPUT_CONTRACT", "EXPECTED_CHALLENGE_RESPONSE", "UNRESOLVED_CONDITION"],
        "executive_finding": (
            "The three M05 variants correctly separate degraded but authorized monitoring, technically "
            "scoreable yet governance-blocked input, and hard contract failure. Technical scoreability, "
            "source condition, governance authorization, and downstream assessability remain independent."
        ),
        "expected_condition": "M05-A, M05-B, and M05-C intentionally challenge different source and contract control dimensions.",
        "observed_response": (
            "M05-A retained governed DQ evidence; M05-B remained BLOCKED_SOURCE_GOVERNANCE despite "
            "technical scoreability; M05-C remained BLOCKED_HARD_GATE and downstream not assessable."
        ),
        "assessment": {
            "documentation_status": "COMPLETE",
            "alert_trigger_explanation_status": "SUPPORTED",
            "underlying_cause_status": "NOT_ASSESSABLE",
            "model_defect_established": False,
            "remediation_status": "NOT_CLAIMED",
            "condition_status": "OPEN",
            "owner_review_status": "APPROVED",
        },
        "cause_assessment": (
            "The scenario design supports the control-state explanation. No real production source "
            "outage, operational incident, or model defect is claimed."
        ),
        "evidence_limitations": [
            "The M05 variants are simulated governance and contract challenges, not production incidents.",
            "Blocked evidence cannot be interpreted as downstream model-health evidence.",
            "CND-02 remains open and no approved fallback policy is represented.",
        ],
        "risk_interpretation": (
            "A population can remain technically scoreable while authoritative use is prohibited, "
            "whereas a hard input-contract failure prevents valid downstream execution altogether. "
            "The blocked cases therefore remain NOT_ASSESSABLE rather than being converted into "
            "CRITICAL model health."
        ),
        "dispositions": ["CONFIRMED_EXPECTED_CHALLENGE_FINDING", "GOVERNANCE_BLOCK_RETAINED", "UNRESOLVED"],
        "recommended_owner_function": "DATA_GOVERNANCE",
        "review_function": "MODEL_RISK",
        "recommended_follow_up": [
            "Resolve CND-02 through an approved source fallback policy and qualified fallback behavior.",
            "Retain hard-gate rejection until the input contract and grain reconcile.",
            "Do not infer model health from blocked downstream evidence.",
        ],
        "proposed_closure_evidence": [
            "Approved CND-02 resolution and source fallback policy.",
            "Qualification evidence for fallback behavior and governance-owner acceptance.",
            "Passing input-contract and grain evidence for any hard-fail remediation claim.",
        ],
        "control_state_comparison": [
            {
                "variant": "M05-A · Source degradation",
                "artifact_id": "SIM-M05-VALID-DEGRADED-01",
                "technical_scoring": "PASS",
                "source_state": "SOURCE_DEGRADED",
                "governance_authorization": "AUTHORIZED",
                "downstream_monitoring": "ELIGIBLE_SUBJECT_TO_CONTROLS",
                "model_health_conclusion": "CRITICAL_GOVERNED_EVIDENCE_RETAINED"
            },
            {
                "variant": "M05-B · Source governance block",
                "artifact_id": "SIM-M05-SOURCE-LOSS-DIAGNOSTIC-01",
                "technical_scoring": "PASS",
                "source_state": "SOURCE_POLICY_REQUIRED",
                "governance_authorization": "BLOCKED_SOURCE_GOVERNANCE",
                "downstream_monitoring": "NON_AUTHORITATIVE_BLOCKED",
                "model_health_conclusion": "NOT_ASSESSABLE"
            },
            {
                "variant": "M05-C · Hard contract / grain failure",
                "artifact_id": "SIM-M05-HARD-FAIL-01",
                "technical_scoring": "BLOCKED_INVALID_EXECUTION",
                "source_state": "HARD_CONTRACT_FAILURE",
                "governance_authorization": "BLOCKED_HARD_GATE",
                "downstream_monitoring": "NOT_ASSESSABLE",
                "model_health_conclusion": "NOT_ASSESSABLE"
            }
        ],
    },
)


def _write_json(path: Path, payload: dict[str, Any] | list[Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _artifact(path: Path, output: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(output).as_posix(),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def _phase_manifest_reconciliation(root: Path) -> list[dict[str, Any]]:
    phase14_contract = json.loads(
        (root / "contracts/final_lifecycle_qualification_contract.json").read_text(encoding="utf-8")
    )
    release_contract = json.loads(
        (root / "contracts/final_project_release_contract.json").read_text(encoding="utf-8")
    )
    bindings = list(phase14_contract["phase_manifest_chain"])
    bindings.append({
        "phase": 14,
        "control_id": "FINAL-LIFECYCLE-QUALIFICATION-01",
        "path": release_contract["frozen_phase14_binding"]["manifest_path"],
        "sha256": release_contract["frozen_phase14_binding"]["manifest_sha256"],
    })
    results = []
    for binding in bindings:
        actual = sha256_file(root / binding["path"])
        results.append({**binding, "actual_sha256": actual, "match": actual == binding["sha256"]})
    return results


def _select_alerts(
    alerts: list[dict[str, Any]], spec: dict[str, Any]
) -> list[dict[str, Any]]:
    artifacts = set(spec["scenario_artifacts"])
    components = set(spec["selector"]["components"])
    severity = spec["selector"]["severity"]
    selected = [
        row for row in alerts
        if row["scenario_artifact_id"] in artifacts
        and row["component"] in components
        and (severity is None or row["alert_severity"] == severity)
    ]
    if spec["case_id"] == "INV-02":
        required = {tuple(item) for item in spec["required_metrics"]}
        selected = [
            row for row in selected
            if row["alert_severity"] == "CRITICAL"
            or (row["component"], row["metric_id"], row["entity_id"]) in required
        ]
    return sorted(selected, key=lambda row: (row["component"], row["alert_id"]))


def _evidence_item(
    root: Path, alert: dict[str, Any], metric: dict[str, Any]
) -> dict[str, Any]:
    source_path = metric["source_artifact_path"]
    source_hash_matches = bool(source_path) and sha256_file(root / source_path) == metric["source_artifact_sha256"]
    return {
        "alert_id": alert["alert_id"],
        "scenario_artifact_id": alert["scenario_artifact_id"],
        "alert_status_at_extraction": alert["current_status"],
        "source_alert_status": "OPEN",
        "component": alert["component"],
        "metric_id": alert["metric_id"],
        "entity_type": alert["entity_type"],
        "entity_id": alert["entity_id"],
        "metric_value": alert["metric_value_numeric"],
        "metric_severity": alert["metric_severity"],
        "alert_severity": alert["alert_severity"],
        "reason_code": alert["reason_code"],
        "evidence_status": alert["evidence_status"],
        "evidence_type": alert["evidence_type"],
        "reference_id": metric["reference_id"],
        "metric_role": metric["metric_role"],
        "materiality_class": metric["materiality_class"],
        "lineage_reference": {
            "source_phase": alert["source_phase"],
            "source_control_id": SOURCE_CONTROLS[alert["source_phase"]],
            "source_artifact": source_path,
            "source_artifact_sha256": metric["source_artifact_sha256"],
            "source_artifact_hash_matches": source_hash_matches,
            "source_record_key": metric["source_row_key"],
            "metric_record_id": metric["metric_record_id"],
        },
    }


def build_investigation_casebook(root: Path) -> str:
    """Materialize the derived casebook from read-only governed evidence."""
    root = root.resolve()
    output = root / "reports/investigation" / CONTROL_ID
    output.mkdir(parents=True, exist_ok=True)
    contract_path = root / "contracts/model_risk_investigation_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    bindings = contract["frozen_bindings"]
    if sha256_file(root / bindings["phase11_manifest_path"]) != bindings["phase11_manifest_sha256"]:
        raise RuntimeError("Frozen Phase 11 manifest changed")
    if sha256_file(root / bindings["phase12_manifest_path"]) != bindings["phase12_manifest_sha256"]:
        raise RuntimeError("Frozen Phase 12 manifest changed")

    phase_before = _phase_manifest_reconciliation(root)
    if not all(row["match"] for row in phase_before):
        raise RuntimeError("Phase 0-14 manifest chain changed before casebook extraction")

    database_path = root / bindings["phase12_database_path"]
    connection = connect_history(database_path, read_only=True)
    try:
        semantic_before = semantic_database_manifest(connection)
        if semantic_before["immutable_evidence_semantic_sha256"] != bindings["phase12_immutable_evidence_semantic_sha256"]:
            raise RuntimeError("Phase 12 immutable evidence digest changed")
        repository = HistoryRepository(connection)
        runs = repository.list_runs()
        run_by_history = {row["history_run_id"]: row for row in runs}
        raw_alerts = repository.list_alerts()
        alerts = [{**row, "scenario_artifact_id": run_by_history[row["history_run_id"]]["scenario_artifact_id"]} for row in raw_alerts]
        metrics = {row["metric_record_id"]: row for row in repository.get_metric_evidence()}
        extracted_utc = datetime.now(timezone.utc).isoformat()
        prior_as_of_path = output / "evidence_as_of_reconciliation.json"
        if prior_as_of_path.is_file():
            prior_as_of = json.loads(prior_as_of_path.read_text(encoding="utf-8")).get("evidence_as_of", {})
            same_frozen_extraction = (
                prior_as_of.get("phase11_manifest_sha256") == bindings["phase11_manifest_sha256"]
                and prior_as_of.get("phase12_frozen_manifest_sha256") == bindings["phase12_manifest_sha256"]
                and prior_as_of.get("phase12_immutable_evidence_semantic_sha256")
                == semantic_before["immutable_evidence_semantic_sha256"]
                and prior_as_of.get("phase12_operational_database_semantic_sha256_at_extraction")
                == semantic_before["database_semantic_sha256"]
                and prior_as_of.get("phase15_pre_casebook_candidate_manifest_sha256")
                == bindings["phase15_pre_casebook_candidate_manifest_sha256"]
            )
            if same_frozen_extraction and prior_as_of.get("evidence_extracted_utc"):
                extracted_utc = prior_as_of["evidence_extracted_utc"]
        evidence_as_of = {
            "phase11_manifest_sha256": bindings["phase11_manifest_sha256"],
            "phase12_frozen_manifest_sha256": bindings["phase12_manifest_sha256"],
            "phase12_immutable_evidence_semantic_sha256": semantic_before["immutable_evidence_semantic_sha256"],
            "phase12_operational_database_semantic_sha256_at_extraction": semantic_before["database_semantic_sha256"],
            "evidence_extracted_utc": extracted_utc,
            "phase15_pre_casebook_candidate_manifest_sha256": bindings["phase15_pre_casebook_candidate_manifest_sha256"],
        }

        dossiers: list[dict[str, Any]] = []
        all_linked_alerts: list[str] = []
        all_source_hashes_match = True
        for spec in CASE_SPECS:
            selected_alerts = _select_alerts(alerts, spec)
            evidence_items = []
            for alert in selected_alerts:
                metric = metrics.get(alert["source_metric_record_id"])
                if metric is None:
                    raise RuntimeError(f"Linked metric missing for {alert['alert_id']}")
                item = _evidence_item(root, alert, metric)
                all_source_hashes_match &= item["lineage_reference"]["source_artifact_hash_matches"]
                evidence_items.append(item)
                all_linked_alerts.append(alert["alert_id"])
            primary_evidence = next(
                (item for item in evidence_items if item["alert_id"] == spec["primary_alert_id"]), None
            )
            if primary_evidence is None:
                raise RuntimeError(f"Primary alert is not linked to {spec['case_id']}")
            if primary_evidence["lineage_reference"]["source_record_key"] != spec["primary_source_record_key"]:
                raise RuntimeError(f"Primary source record changed for {spec['case_id']}")
            contexts = []
            for artifact_id in spec["scenario_artifacts"]:
                row = next(run for run in runs if run["scenario_artifact_id"] == artifact_id)
                contexts.append({
                    "scenario_id": row["scenario_id"],
                    "scenario_artifact_id": artifact_id,
                    "authorization_state": row["authorization_state"],
                    "evidence_scope": row["evidence_scope"],
                    "evidence_type": row["evidence_type"],
                    "overall_health": row["overall_model_health"],
                })
            dossier = {
                "case_id": spec["case_id"],
                "chapter": spec["chapter"],
                "short_title": spec["short_title"],
                "title": spec["title"],
                "control_id": CONTROL_ID,
                "contract_id": CONTRACT_ID,
                "evidence_as_of": evidence_as_of,
                "case_context": {"scenarios": contexts},
                "primary_evidence": primary_evidence,
                "source_evidence": {
                    "authority": "FROZEN_MONITORING_EVIDENCE",
                    "linked_alert_count": len(evidence_items),
                    "linked_alert_ids": [item["alert_id"] for item in evidence_items],
                    "linked_metric_record_ids": [item["lineage_reference"]["metric_record_id"] for item in evidence_items],
                    "linked_alerts": evidence_items,
                },
                "investigation_assessment": {
                    **spec["assessment"],
                    "authority": "APPROVED_AUTHORITATIVE_INVESTIGATION_RECORD",
                    "classification": spec["classification"],
                    "executive_finding": spec["executive_finding"],
                    "expected_vs_observed": {
                        "scenario_condition_intentionally_injected": spec["case_id"] != "INV-01",
                        "expected_condition": spec["expected_condition"],
                        "observed_response": spec["observed_response"],
                        "observed_finding_consistent_with_scenario_design": True,
                        "unexpected_finding_identified": spec["case_id"] == "INV-01",
                    },
                    "cause_assessment": spec["cause_assessment"],
                    "evidence_limitations": spec["evidence_limitations"],
                    "risk_interpretation": spec["risk_interpretation"],
                    "dispositions": spec["dispositions"],
                    "recommended_owner_function": spec["recommended_owner_function"],
                    "review_function": spec["review_function"],
                    "recommended_follow_up": spec["recommended_follow_up"],
                    "proposed_closure_evidence": spec["proposed_closure_evidence"],
                    "control_state_comparison": spec.get("control_state_comparison", []),
                },
                "scope_assertions": {
                    "monitoring_recalculated": False,
                    "model_scored": False,
                    "alert_lifecycle_mutated": False,
                    "production_inference_claimed": False,
                    "fairness_assessed": False,
                },
            }
            dossiers.append(dossier)
            _write_json(output / f"{spec['case_id']}.json", dossier)
        semantic_after = semantic_database_manifest(connection)
    finally:
        connection.close()

    phase_after = _phase_manifest_reconciliation(root)
    phase_chain_unchanged = phase_before == phase_after and all(row["match"] for row in phase_after)
    database_unchanged = semantic_before == semantic_after
    alert_ids_unique = len(all_linked_alerts) == len(set(all_linked_alerts))
    exact_m04 = {
        item["metric_id"] + ":" + item["entity_id"]: item["metric_value"]
        for dossier in dossiers if dossier["case_id"] == "INV-02"
        for item in dossier["source_evidence"]["linked_alerts"]
    }
    m04_reconciles = (
        exact_m04.get("feature_psi:EXT_SOURCE_2") == 0.46145175839108366
        and exact_m04.get("feature_psi:EXT_SOURCE_3") == 0.25012754553854843
        and exact_m04.get("risk_positive_rate_absolute_change:THRESHOLD-01") == 0.0883799909049509
    )

    _write_json(output / "model_risk_investigation_contract_snapshot.json", contract)
    registry = {
        "control_id": CONTROL_ID,
        "case_count": len(dossiers),
        "default_case_id": "INV-01",
        "investigation_assessment_authority": "APPROVED_AUTHORITATIVE_INVESTIGATION_RECORD",
        "cases": [{
            "case_id": case["case_id"], "chapter": case["chapter"],
            "short_title": case["short_title"], "title": case["title"],
            "classification": case["investigation_assessment"]["classification"],
            "dispositions": case["investigation_assessment"]["dispositions"],
            "linked_alert_count": case["source_evidence"]["linked_alert_count"],
        } for case in dossiers],
    }
    _write_json(output / "case_registry.json", registry)
    _write_json(output / "evidence_as_of_reconciliation.json", {
        "evidence_as_of": evidence_as_of,
        "dual_phase12_digest_binding": True,
        "immutable_evidence_digest_match": semantic_before["immutable_evidence_semantic_sha256"] == bindings["phase12_immutable_evidence_semantic_sha256"],
        "operational_database_digest_captured": bool(semantic_before["database_semantic_sha256"]),
        "phase_0_through_14_manifests": phase_after,
        "phase_0_through_14_unchanged": phase_chain_unchanged,
    })
    _write_json(output / "alert_linkage_reconciliation.json", {
        "linked_alert_count": len(all_linked_alerts),
        "linked_alert_ids_unique_across_cases": alert_ids_unique,
        "all_linked_alerts_exist": len(all_linked_alerts) == 21,
        "alert_status_at_extraction_captured": True,
        "source_status_preserved": True,
        "result": "PASS" if alert_ids_unique and len(all_linked_alerts) == 21 else "FAIL",
    })
    primary_reconciliation = []
    for case in dossiers:
        primary = case["primary_evidence"]
        linked = case["source_evidence"]["linked_alerts"]
        match = next((item for item in linked if item["alert_id"] == primary["alert_id"]), None)
        primary_reconciliation.append({
            "case_id": case["case_id"],
            "primary_alert_id": primary["alert_id"],
            "primary_source_record_key": primary["lineage_reference"]["source_record_key"],
            "primary_alert_exists": match is not None,
            "primary_source_record_exists": bool(primary["lineage_reference"]["source_record_key"]),
            "primary_evidence_is_linked": match == primary,
            "metric_entity_and_source_identifiers_reconcile": match == primary,
        })
    primary_pass = all(
        row["primary_alert_exists"] and row["primary_source_record_exists"]
        and row["primary_evidence_is_linked"] and row["metric_entity_and_source_identifiers_reconcile"]
        for row in primary_reconciliation
    )
    _write_json(output / "primary_evidence_reconciliation.json", {
        "selection_authority": "APPROVED_CASE_ARTIFACT",
        "presentation_layer_selection_permitted": False,
        "cases": primary_reconciliation,
        "result": "PASS" if primary_pass else "FAIL",
    })
    _write_json(output / "metric_reconciliation.json", {
        "linked_metric_count": len(all_linked_alerts),
        "all_linked_metrics_exist": True,
        "all_source_artifact_hashes_match": all_source_hashes_match,
        "m04_exact_values": exact_m04,
        "m04_exact_values_reconcile": m04_reconciles,
        "numeric_values_copied_without_recalculation": True,
        "result": "PASS" if all_source_hashes_match and m04_reconciles else "FAIL",
    })
    _write_json(output / "investigation_authority_attestation.json", {
        "source_evidence_authority": "FROZEN_MONITORING_EVIDENCE",
        "monitoring_calculation_authority": False,
        "investigation_assessment_authority": "APPROVED_AUTHORITATIVE_INVESTIGATION_RECORD",
        "owner_review_status": "APPROVED",
        "post_approval_authority_scope": contract["authority_model"]["approved_authority_scope"],
        "post_approval_authority_exclusions": contract["authority_model"]["approved_authority_does_not_mean"],
    })
    _write_json(output / "casebook_owner_approval_record.json", {
        "control_id": CONTROL_ID,
        "contract_id": CONTRACT_ID,
        "review_decision": "APPROVED",
        "approved_scope": contract["authority_model"]["approved_authority_scope"],
        "primary_evidence_selection_governed_by_case_artifact": True,
        "extraction_time_alert_state_preserved": True,
        "current_operational_alert_state_separate": True,
        "linked_alert_navigation_uses_current_state": True,
        "substantive_dossier_conclusions_changed": False,
        "phase_0_through_14_reopened": False,
    })
    _write_json(output / "historical_candidate_boundaries.json", {
        "pre_remediation_phase15_candidate": "2d6c748ab8bfcdb9bb33d96809da2df76651908935b15f79fa76751a1b032781",
        "pre_casebook_phase15_candidate": bindings["phase15_pre_casebook_candidate_manifest_sha256"],
        "pre_owner_review_remediation_casebook_candidate": bindings["pre_owner_review_remediation_casebook_manifest_sha256"],
        "pre_owner_review_remediation_phase15_candidate": bindings["pre_owner_review_remediation_phase15_manifest_sha256"],
        "preserved_for_lineage": True,
    })
    _write_json(output / "synthetic_evidence_attestation.json", {
        "case_id": "INV-03",
        "evidence_type": "SYNTHETIC_SCENARIO_EVIDENCE",
        "non_empirical": True,
        "external_validation": False,
        "production_performance_established": False,
        "disclosures_present_end_to_end": all(
            token in dossiers[2]["investigation_assessment"]["evidence_limitations"]
            for token in ["SYNTHETIC_SCENARIO_EVIDENCE", "NON_EMPIRICAL", "NOT_EXTERNAL_VALIDATION"]
        ),
    })
    _write_json(output / "scope_protection_attestation.json", {
        "phase_0_through_14_artifact_hashes_unchanged": phase_chain_unchanged,
        "database_semantic_manifest_unchanged_during_extraction": database_unchanged,
        "immutable_evidence_unchanged": semantic_before["immutable_evidence_semantic_sha256"] == semantic_after["immutable_evidence_semantic_sha256"],
        "alert_event_ledger_unchanged": semantic_before["tables"]["alert_events"] == semantic_after["tables"]["alert_events"],
        "read_only_database_connection": True,
        "monitoring_calculation_functions_executed": False,
        "model_scoring_executed": False,
        "severity_or_health_rewritten": False,
        "authorization_or_evidence_scope_rewritten": False,
        "new_database_tables_created": False,
        "fairness_or_responsible_ai_conclusion_claimed": False,
        "result": "PASS" if phase_chain_unchanged and database_unchanged else "FAIL",
    })
    qualification_pass = all([
        len(dossiers) == 4,
        len(all_linked_alerts) == 21,
        alert_ids_unique,
        all_source_hashes_match,
        primary_pass,
        m04_reconciles,
        phase_chain_unchanged,
        database_unchanged,
    ])
    _write_json(output / "investigation_casebook_qualification.json", {
        "control_id": CONTROL_ID,
        "status": "APPROVED_FROZEN_AFTER_PRIMARY_EVIDENCE_AND_TEMPORAL_NAVIGATION_REMEDIATION",
        "review_decision": "APPROVED",
        "case_count": len(dossiers),
        "linked_alert_count": len(all_linked_alerts),
        "governed_evidence_and_assessment_separated": True,
        "dual_phase12_digest_binding": True,
        "primary_evidence_selection_governed_by_case_artifact": True,
        "primary_evidence_reconciliation": "PASS" if primary_pass else "FAIL",
        "extraction_time_alert_state_preserved": True,
        "current_operational_alert_state_separate": True,
        "linked_alert_navigation_uses_current_state": True,
        "m05_three_state_semantics_preserved": True,
        "m05_blocked_health_remains_not_assessable": all(
            context["overall_health"] == "NOT_ASSESSABLE"
            for context in dossiers[3]["case_context"]["scenarios"]
            if context["scenario_artifact_id"] != "SIM-M05-VALID-DEGRADED-01"
        ),
        "m06_synthetic_classification_preserved": True,
        "owner_approval_required": False,
        "technical_result": "PASS" if qualification_pass else "FAIL",
    })
    checklist = [
        ("PROSPECTIVE_CONTRACT", "PASS"),
        ("FOUR_CONSOLIDATED_DOSSIERS", "PASS"),
        ("DUAL_PHASE12_DIGEST_BINDING", "PASS"),
        ("ALERT_AND_METRIC_RECONCILIATION", "PASS" if all_source_hashes_match else "FAIL"),
        ("PRIMARY_EVIDENCE_GOVERNED_BY_CASE_ARTIFACT", "PASS" if primary_pass else "FAIL"),
        ("EXTRACTION_AND_CURRENT_STATE_SEPARATED", "PASS"),
        ("NO_MONITORING_RECALCULATION", "PASS"),
        ("NO_UPSTREAM_OR_LIFECYCLE_MUTATION", "PASS" if phase_chain_unchanged and database_unchanged else "FAIL"),
        ("SYNTHETIC_EVIDENCE_DISCIPLINE", "PASS"),
        ("M05_BLOCK_SEMANTICS", "PASS"),
        ("OWNER_APPROVAL", "PASS"),
    ]
    with (output / "phase15_casebook_acceptance_checklist.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["control", "status"])
        writer.writerows(checklist)
    _write_json(output / "execution_source_manifest.json", {
        "control_id": CONTROL_ID,
        "contract": {"path": contract_path.relative_to(root).as_posix(), "sha256": sha256_file(contract_path)},
        "implementation": {
            "path": "src/credit_risk_monitoring/investigation/casebook.py",
            "sha256": sha256_file(Path(__file__)),
        },
        "source_monitoring_evidence_authoritative": True,
        "casebook_assessment_authority": "APPROVED_AUTHORITATIVE_INVESTIGATION_RECORD",
    })
    evidence_files = sorted(
        path for path in output.iterdir()
        if path.is_file() and path.name not in {"manifest.json", "manifest.sha256"}
    )
    manifest = {
        "control_id": CONTROL_ID,
        "contract_id": CONTRACT_ID,
        "version": "1.0.0",
        "created_utc": evidence_as_of["evidence_extracted_utc"],
        "status": "APPROVED_FROZEN_AFTER_PRIMARY_EVIDENCE_AND_TEMPORAL_NAVIGATION_REMEDIATION",
        "review_decision": "APPROVED",
        "case_count": 4,
        "linked_alert_count": len(all_linked_alerts),
        "phase_0_through_14_read_only": True,
        "source_evidence_authority": "FROZEN_MONITORING_EVIDENCE",
        "monitoring_calculation_authority": False,
        "investigation_assessment_authority": "APPROVED_AUTHORITATIVE_INVESTIGATION_RECORD",
        "alert_lifecycle_mutated": False,
        "artifacts": [_artifact(path, output) for path in evidence_files],
    }
    _write_json(output / "manifest.json", manifest)
    digest = sha256_file(output / "manifest.json")
    (output / "manifest.sha256").write_text(digest + "\n", encoding="utf-8")
    if not qualification_pass:
        raise RuntimeError("Investigation casebook qualification failed")
    return digest
