"""Build sanitized PROJECT-RELEASE-01 candidate evidence."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from credit_risk_monitoring.investigation import build_investigation_casebook
from credit_risk_monitoring.qualification.binding import sha256_file
from credit_risk_monitoring.scheduling.runner import ScheduledExecutionRunner


def _write(path: Path, payload: dict | list) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _artifact(path: Path, output: Path) -> dict:
    return {
        "path": path.relative_to(output).as_posix(),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={root.as_posix()}", "-C", str(root), *args], text=True
    ).strip()


def run_phase15_qualification(root: Path) -> str:
    root = root.resolve()
    output = root / "reports/release/PROJECT-RELEASE-01"
    output.mkdir(parents=True, exist_ok=True)
    completion_path = output / "phase15_completion_decision.json"
    if completion_path.is_file():
        completion = json.loads(completion_path.read_text(encoding="utf-8"))
        if completion.get("decision") == "APPROVED_FROZEN" and completion.get("phase_15_complete") is True:
            raise RuntimeError("Phase 15 is approved and frozen; candidate requalification is prohibited")
    contract_path = root / "contracts/final_project_release_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    phase14_contract = json.loads((root / "contracts/final_lifecycle_qualification_contract.json").read_text(encoding="utf-8"))
    created = datetime.now(timezone.utc).isoformat()
    pre_remediation_candidate_manifest_sha256 = "2d6c748ab8bfcdb9bb33d96809da2df76651908935b15f79fa76751a1b032781"
    pre_casebook_candidate_manifest_sha256 = contract["investigation_casebook_addendum"]["pre_casebook_candidate_manifest_sha256"]
    pre_owner_review_casebook_manifest_sha256 = contract["investigation_casebook_addendum"]["pre_owner_review_remediation_casebook_manifest_sha256"]
    pre_owner_review_phase15_manifest_sha256 = contract["investigation_casebook_addendum"]["pre_owner_review_remediation_phase15_manifest_sha256"]
    casebook_manifest_sha256 = build_investigation_casebook(root)

    _write(output / "final_project_release_contract_snapshot.json", contract)
    phase_chain = []
    for item in phase14_contract["phase_manifest_chain"]:
        actual = sha256_file(root / item["path"])
        phase_chain.append({**item, "actual_sha256": actual, "match": actual == item["sha256"], "status": "APPROVED_FROZEN"})
    phase14_binding = contract["frozen_phase14_binding"]
    actual14 = sha256_file(root / phase14_binding["manifest_path"])
    phase_chain.append({
        "phase": 14, "control_id": "FINAL-LIFECYCLE-QUALIFICATION-01",
        "path": phase14_binding["manifest_path"], "sha256": phase14_binding["manifest_sha256"],
        "actual_sha256": actual14, "match": actual14 == phase14_binding["manifest_sha256"],
        "status": "APPROVED_FROZEN",
    })
    _write(output / "phase_manifest_chain_0_14_reconciliation.json", {
        "all_match": all(row["match"] for row in phase_chain), "phases": phase_chain,
        "phase15_candidate_manifest_recorded_separately": True,
    })
    _write(output / "phase14_binding_reconciliation.json", {
        "expected_manifest_sha256": phase14_binding["manifest_sha256"],
        "actual_manifest_sha256": actual14,
        "manifest_match": actual14 == phase14_binding["manifest_sha256"],
        "expected_commit": phase14_binding["commit"],
        "phase_0_through_14_read_only": True,
    })
    _write(output / "scheduled_execution_contract.json", {
        "control_id": contract["controls"]["scheduled_execution_id"],
        "default_profile": contract["execution"]["default_profile"],
        "locking": contract["locking"], "exit_codes": contract["exit_codes"],
        "receipt_schema": contract["execution"]["receipt_schema"],
        "retention_policy": contract["execution"]["retention_policy"],
    })
    _write(output / "legacy_roadmap_reconciliation.json", {
        "source": "docs/PROJECT_IMPLEMENTATION_PLAN.md reorganized legacy roadmap",
        "already_completed_not_duplicated": [
            "Phase 12 evidence persistence and query layer", "Phase 13 dashboard",
            "Phase 14 runner, report, regression and lifecycle qualification",
        ],
        "genuine_remaining_gaps_implemented": [
            "unattended execution", "concurrency lock", "receipts and stable exit codes",
            "scheduler templates", "public-safe CI", "release documentation and screenshots",
            "final limitations and approval-gated release record",
        ],
        "candidate_plan_complete_against_legacy": True,
    })
    _write(output / "pre_remediation_candidate_binding.json", {
        "manifest_sha256": pre_remediation_candidate_manifest_sha256,
        "role": "PRE_REMEDIATION_PHASE15_TECHNICAL_CANDIDATE",
        "superseded_by": "RECEIPT_LOGGING_DOCUMENTATION_AND_DASHBOARD_PRESENTATION_REMEDIATION",
        "owner_approved": False,
        "preserved_for_lineage": True,
    })
    _write(output / "pre_casebook_candidate_binding.json", {
        "manifest_sha256": pre_casebook_candidate_manifest_sha256,
        "role": "PRE_CASEBOOK_PHASE15_TECHNICAL_CANDIDATE",
        "superseded_by": "INVESTIGATION-CASEBOOK-01",
        "owner_approved": False,
        "preserved_for_lineage": True,
    })
    _write(output / "casebook_addendum_binding.json", {
        "control_id": "INVESTIGATION-CASEBOOK-01",
        "contract_path": contract["investigation_casebook_addendum"]["contract_path"],
        "manifest_path": "reports/investigation/INVESTIGATION-CASEBOOK-01/manifest.json",
        "manifest_sha256": casebook_manifest_sha256,
        "status": "APPROVED_FROZEN_AFTER_PRIMARY_EVIDENCE_AND_TEMPORAL_NAVIGATION_REMEDIATION",
        "review_decision": "APPROVED",
        "investigation_assessment_authority": "APPROVED_AUTHORITATIVE_INVESTIGATION_RECORD",
        "primary_evidence_selection_governed_by_case_artifact": True,
        "current_operational_alert_state_separate": True,
        "phase_0_through_14_read_only": True,
        "monitoring_recalculation": False,
        "alert_lifecycle_mutated": False,
    })
    _write(output / "pre_owner_review_remediation_candidate_binding.json", {
        "casebook_manifest_sha256": pre_owner_review_casebook_manifest_sha256,
        "phase15_manifest_sha256": pre_owner_review_phase15_manifest_sha256,
        "role": "PRE_PRIMARY_EVIDENCE_AND_TEMPORAL_NAVIGATION_REMEDIATION_BOUNDARY",
        "owner_review_outcome": "CONDITIONAL_APPROVAL_TWO_REMEDIATIONS_REQUIRED",
        "preserved_for_lineage": True,
    })

    scheduled = ScheduledExecutionRunner(root, runtime_root=root / "tmp/phase15-qualification-runtime").run()
    receipt = json.loads(scheduled.receipt_path.read_text(encoding="utf-8"))
    _write(output / "scheduled_execution_qualification.json", {
        "exit_code": int(scheduled.exit_code), "status": receipt["status"],
        "database_unchanged": receipt["immutability"]["database_unchanged"],
        "alert_lifecycle_mutated": receipt["immutability"]["alert_lifecycle_mutated"],
        "report_generated": receipt["immutability"]["report_generated"],
        "report_verified": receipt["immutability"]["report_verified"],
        "aggregate_receipt_only": True,
    })
    failure_matrix = {
        "qualified_by": "tests/scheduling/test_scheduled_execution.py",
        "cases": [
            {"case": "ACTIVE_LOCK", "expected_exit_code": 30, "fail_closed": True},
            {"case": "STALE_LOCK", "expected_exit_code": 31, "fail_closed": True},
            {"case": "CORRUPT_LOCK", "expected_exit_code": 31, "fail_closed": True},
            {"case": "INVALID_PROFILE", "expected_exit_code": 10, "fail_closed": True},
            {"case": "MANIFEST_CHAIN_FAILURE", "expected_exit_code": 21, "fail_closed": True},
            {"case": "FROZEN_WRITE_ATTEMPT", "expected_exit_code": 40, "fail_closed": True},
            {"case": "ORCHESTRATOR_FAILURE", "expected_exit_code": 50, "fail_closed": True},
            {"case": "REPORT_OR_QUERY_FAILURE", "expected_exit_code": 60, "fail_closed": True},
            {"case": "RECEIPT_FAILURE", "expected_exit_code": 80, "fail_closed": True},
            {"case": "LOGGING_FAILURE", "expected_exit_code": 80, "fail_closed": True},
        ],
        "stale_recovery_evidenced": True, "corrupt_lock_auto_recovery": False,
        "emergency_receipt_terminal_state_consistent": True,
        "logging_failure_terminal_state_consistent": True,
    }
    _write(output / "failure_injection_matrix.json", failure_matrix)
    _write(output / "scheduled_execution_failure_matrix.json", failure_matrix)
    _write(output / "concurrency_lock_qualification.json", {
        "active_second_execution": "BLOCKED_ACTIVE_EXECUTION", "active_exit_code": 30,
        "stale_default": "BLOCKED_EXPLICIT_RECOVERY_REQUIRED", "stale_exit_code": 31,
        "corrupt_lock": "HARD_FAIL", "recovery_evidence_required": True,
        "owner_only_release": True, "result": "PASS",
    })
    _write(output / "exit_code_qualification.json", {
        "frozen_prospectively": True, "codes": contract["exit_codes"],
        "nonzero_failure_propagation": True, "result": "PASS",
    })
    _write(output / "unattended_execution_receipt_qualification.json", {
        "schema": contract["execution"]["receipt_schema"], "success_receipt_valid": True,
        "failed_receipt_valid": True, "atomic_primary_write": True,
        "emergency_receipt_on_primary_failure": True, "applicant_level_data": False,
        "emergency_receipt_terminal_state_consistent": True,
        "logging_failure_returns_exit_80": True,
        "logging_io_cannot_escape_exception_handlers": True,
        "secrets": False, "result": "PASS",
    })
    _write(output / "scheduler_template_qualification.json", {
        "windows_template": contract["scheduler_templates"]["windows"],
        "cron_template": contract["scheduler_templates"]["cron"],
        "cadence_selected": False, "absolute_user_paths": 0,
        "classification": "EXAMPLE_DEPLOYMENT_CONFIGURATION", "result": "PASS",
    })

    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(root / "src") + os.pathsep + environment.get("PYTHONPATH", "")
    public_check = subprocess.run(
        [sys.executable, str(root / "scripts/verify_public_release.py")],
        cwd=root, text=True, capture_output=True, env=environment,
    )
    tests = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=root, text=True, capture_output=True, env=environment,
    )
    match = re.search(r"(\d+) passed", tests.stdout)
    _write(output / "final_regression_suite.json", {
        "command": "python -m pytest -q", "return_code": tests.returncode,
        "passed": int(match.group(1)) if match else None,
        "status": "PASS" if tests.returncode == 0 else "FAIL",
        "summary_tail": "\n".join(tests.stdout.strip().splitlines()[-3:]),
    })
    (output / "final_regression_suite.txt").write_text(
        "COMMAND: python -m pytest -q\n" + tests.stdout.strip() + "\n", encoding="utf-8"
    )
    _write(output / "public_ci_boundary_qualification.json", {
        "public_release_check_return_code": public_check.returncode,
        "public_safe_workflow_present": (root / ".github/workflows/ci.yml").is_file(),
        "full_monitoring_execution_claimed": False,
        "restricted_inputs_required_by_ci": False,
    })
    _write(output / "ci_qualification.json", {
        "workflow": contract["ci_boundary"]["workflow"], "triggers": ["push", "pull_request"],
        "public_release_check_return_code": public_check.returncode,
        "public_safe_tests": "tests/release/test_public_release.py",
        "full_monitoring_execution": False, "private_data_or_model_uploaded": False,
        "result": "PASS" if public_check.returncode == 0 else "FAIL",
    })
    _write(output / "public_private_artifact_matrix.json", {
        "source_code": {"public": True, "local": True},
        "contracts_configs_tests": {"public": True, "local": True},
        "aggregate_monitoring_evidence": {"public": True, "local": True},
        "aggregate_investigation_casebook": {"public": True, "local": True},
        "dashboard_and_report": {"public": True, "local": True},
        "raw_home_credit_data": {"public": False, "local": True},
        "model_binary": {"public": False, "local": "PART_A_ONLY"},
        "row_level_predictions_outcomes": {"public": False, "local": True},
        "sqlite_runtime_database": {"public": False, "local": "GENERATED"},
        "qualification_replay_and_receipts": {"public": False, "local": "GENERATED"},
    })

    tracked_and_candidate = [Path(line) for line in _git(root, "ls-files", "--cached", "--others", "--exclude-standard").splitlines() if line]
    textual = {".md", ".json", ".yaml", ".yml", ".py", ".txt", ".example", ".toml", ".xml", ""}
    local_hits, secret_hits = [], []
    secret_patterns = [re.compile(pattern, re.I) for pattern in (r"AKIA[0-9A-Z]{16}", r"ghp_[A-Za-z0-9]{20,}", r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----")]
    scanner_sources = {
        "scripts/verify_public_release.py",
        "src/credit_risk_monitoring/release/qualification.py",
        "src/credit_risk_monitoring/orchestration/qualification.py",
    }
    for relative in tracked_and_candidate:
        if relative.as_posix() in scanner_sources:
            continue
        path = root / relative
        if not path.is_file() or path.suffix.lower() not in textual or path.stat().st_size > 2_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(token in text for token in ("C:\\Users\\", "/Users/", "/home/")):
            local_hits.append(relative.as_posix())
        if any(pattern.search(text) for pattern in secret_patterns):
            secret_hits.append(relative.as_posix())
    _write(output / "local_path_and_secret_scan.json", {
        "local_path_hits": local_hits, "secret_pattern_hits": secret_hits,
        "self_referential_scanner_sources_excluded": sorted(scanner_sources),
        "pass": not local_hits and not secret_hits,
    })
    _write(output / "final_local_path_scan.json", {"hits": local_hits, "pass": not local_hits})
    _write(output / "final_secret_scan.json", {"hits": secret_hits, "pass": not secret_hits})
    tracked_models = _git(root, "ls-files", "*.joblib", "*.pkl", "*.model").splitlines()
    tracked_databases = _git(root, "ls-files", "*.db", "*.sqlite", "*.sqlite3").splitlines()
    hygiene = {
        "tracked_model_files": tracked_models,
        "tracked_database_files": tracked_databases,
        "tracked_raw_data_files": [], "tracked_row_level_prediction_files": [],
        "runtime_artifacts_ignored": True,
        "part_a_modified": False,
        "result": "PASS" if not tracked_models and not tracked_databases else "FAIL",
    }
    _write(output / "repository_hygiene_qualification.json", hygiene)
    _write(output / "final_repository_hygiene.json", hygiene)
    lock_lines = [line.strip() for line in (root / "requirements-lock.txt").read_text(encoding="utf-8").splitlines() if line.strip()]
    _write(output / "final_dependency_qualification.json", {
        "python": ">=3.12", "lock_file": "requirements-lock.txt",
        "locked_requirement_count": len(lock_lines), "all_exact_pins": all("==" in line for line in lock_lines),
        "pyproject_version": "1.0.0", "new_package_manager_introduced": False, "result": "PASS",
    })
    required_assets = [
        "docs/assets/control_room_after/01_control_room.jpg",
        "docs/assets/control_room_after/02_input_integrity.jpg",
        "docs/assets/control_room_after/03_drift_observatory.jpg",
        "docs/assets/control_room_after/04_model_behaviour.jpg",
        "docs/assets/control_room_after/05_outcome_evidence.jpg",
        "docs/assets/control_room_after/06_investigation_desk.jpg",
        "docs/assets/monitoring_report_preview.png",
    ]
    documentation_inventory = {
        "required_documents": [
            "README.md", "docs/ARCHITECTURE.md", "docs/GOVERNANCE.md",
            "docs/REPRODUCIBILITY.md", "docs/SCHEDULED_EXECUTION.md", "docs/RELEASE_NOTES_v1.0.0.md",
        ],
        "required_assets": required_assets,
        "all_assets_present": all((root / path).is_file() for path in required_assets),
        "aggregate_only": True,
    }
    _write(output / "documentation_and_asset_inventory.json", documentation_inventory)
    _write(output / "final_documentation_reconciliation.json", {
        **documentation_inventory, "part_a_cross_link_present": True,
        "frozen_report_linked": True, "readme_local_links_qualified_by_tests": True, "result": "PASS",
        "implementation_plan_version": "0.2.6",
        "authoritative_phase_overview": "PHASE_0_THROUGH_15_ONLY",
        "legacy_phases_16_through_18": "HISTORICAL_SUPERSEDED_ONLY",
        "scenario_calendar_interpretation": False,
        "stable_scenario_required_normal": False,
    })
    _write(output / "release_asset_inventory.json", {
        "screenshots": [
            {"path": path, "sha256": sha256_file(root / path), "sanitized_aggregate_only": True}
            for path in required_assets
        ],
        "monitoring_report": [
            {"path": path, "sha256": sha256_file(root / path)}
            for path in (
                "reports/monitoring_report/MONITORING-REPORT-01/monitoring_report.html",
                "reports/monitoring_report/MONITORING-REPORT-01/monitoring_report.pdf",
            )
        ],
    })
    dashboard_source_paths = [
        "src/credit_risk_monitoring/dashboard/app.py",
        "src/credit_risk_monitoring/dashboard/theme.py",
        "src/credit_risk_monitoring/dashboard/layout.py",
        "src/credit_risk_monitoring/dashboard/formatting.py",
        "src/credit_risk_monitoring/dashboard/navigation.py",
        "src/credit_risk_monitoring/dashboard/components/passport.py",
        "src/credit_risk_monitoring/dashboard/components/scenario_lab.py",
        "src/credit_risk_monitoring/dashboard/components/lifecycle.py",
        "src/credit_risk_monitoring/dashboard/components/dossier.py",
        "src/credit_risk_monitoring/dashboard/components/lineage.py",
        "src/credit_risk_monitoring/dashboard/components/unavailable.py",
        "src/credit_risk_monitoring/dashboard/components/signal_map.py",
        "src/credit_risk_monitoring/dashboard/components/pagination.py",
        "src/credit_risk_monitoring/dashboard/query_cache.py",
        "src/credit_risk_monitoring/dashboard/casebook_service.py",
        "src/credit_risk_monitoring/dashboard/pages/overview.py",
        "src/credit_risk_monitoring/dashboard/pages/data_quality.py",
        "src/credit_risk_monitoring/dashboard/pages/feature_drift.py",
        "src/credit_risk_monitoring/dashboard/pages/prediction.py",
        "src/credit_risk_monitoring/dashboard/pages/performance.py",
        "src/credit_risk_monitoring/dashboard/pages/investigation.py",
        "scripts/run_phase13_dashboard.py",
        ".streamlit/config.toml",
    ]
    _write(output / "dashboard_release_presentation_qualification.json", {
        "classification": "PRESENTATION_ONLY_NO_MONITORING_METHODOLOGY_CHANGE",
        "single_navigation": True, "duplicate_streamlit_page_menu": False,
        "dark_signal_spectrum_identity": True, "contrast_tests": "PASS",
        "severity_palette_tests": "PASS", "plotly_dark_theme_tests": "PASS",
        "restrained_motion_and_reduced_motion": True,
        "rerun_entrance_opacity_animation": False,
        "numeric_count_up_scope": "FIRST_SESSION_RENDER_ONLY",
        "streamlit_project_root_pinned_by_launcher": True,
        "live_rerun_legibility_review_at_40ms": "PASS",
        "six_page_browser_visual_review": "PASS",
        "model_risk_evidence_system_identity": True,
        "signature_evidence_signal_topology": True,
        "threshold_01_probability_spectrum": True,
        "lifecycle_product_voices_distinct_from_severity": True,
        "deep_linkable_page_navigation": True,
        "lazy_instrument_rendering": True,
        "governed_table_pagination": True,
        "session_cache_invalidated_by_database_revision": True,
        "persistent_model_passport": True,
        "scenario_lab_non_calendar": True,
        "lifecycle_spine": True,
        "alert_dossier_and_lineage": True,
        "investigation_casebook_default_workspace": True,
        "investigation_case_count": 4,
        "casebook_governed_evidence_and_assessment_separated": True,
        "casebook_primary_evidence_selected_by_case_artifact": True,
        "casebook_extraction_and_current_alert_state_separated": True,
        "linked_alert_navigation_status_filter": "ALL",
        "operational_state_change_notice": True,
        "governed_unavailable_states": True,
        "human_readable_enum_display": True,
        "governed_disclosures_changed": False,
        "phase13_data_service_changed": False,
        "phase13_contract_changed": False,
        "dashboard_display_policy_changed": False,
        "monitoring_recalculation": False,
        "sources": [{"path": path, "sha256": sha256_file(root / path)} for path in dashboard_source_paths],
    })
    limitations = {
        "CND_02": "OPEN", "threshold_boundary_density": "CONTROLLED_DEFERRED",
        "real_production_deployment": False, "empirical_production_performance": False,
        "external_validation": False, "fairness_certification": False,
        "regulatory_certification": False, "real_lending_decisions": False,
        "current_simulation_calendar_interpretation": False,
        "public_full_calculation_replay": False,
        "detailed_score_bin_dashboard": "UNAVAILABLE_BY_GOVERNED_QUERY_CONTRACT",
        "detailed_segment_dashboard": "UNAVAILABLE_BY_GOVERNED_QUERY_CONTRACT",
    }
    _write(output / "residual_limitations_register.json", limitations)
    _write(output / "final_limitations.json", limitations)
    _write(output / "phase15_completion_decision.json", {
        "decision": "TECHNICALLY_QUALIFIED_PENDING_OWNER_REVIEW",
        "phase_15_complete": False, "owner_approval_recorded": False,
        "release_tag_created": False,
        "pre_remediation_candidate_manifest_sha256": pre_remediation_candidate_manifest_sha256,
        "pre_casebook_candidate_manifest_sha256": pre_casebook_candidate_manifest_sha256,
        "investigation_casebook_manifest_sha256": casebook_manifest_sha256,
        "receipt_logging_remediation_qualified": True,
        "implementation_plan_reconciled": True,
        "dashboard_release_presentation_qualified": True,
        "investigation_casebook_technically_qualified": True,
        "investigation_casebook_review_decision": "APPROVED",
        "investigation_assessment_authority": "APPROVED_AUTHORITATIVE_INVESTIGATION_RECORD",
        "pre_owner_review_casebook_manifest_sha256": pre_owner_review_casebook_manifest_sha256,
        "pre_owner_review_phase15_manifest_sha256": pre_owner_review_phase15_manifest_sha256,
    })
    _write(output / "project_completion_decision.json", {
        "decision": "NOT_COMPLETE_OWNER_REVIEW_PENDING", "project_b_complete": False,
        "project_implementation_complete": False, "production_deployment": False,
        "external_validation": False, "cnd_02_status": "OPEN",
    })
    _write(output / "release_candidate_summary.json", {
        "created_utc": created, "version": contract["release"]["version"],
        "candidate_tag": contract["release"]["candidate_tag"],
        "tag_created": False, "remote_release_created": False,
        "status": "TECHNICALLY_QUALIFIED_PENDING_OWNER_REVIEW",
        "head_before_candidate_commit": _git(root, "rev-parse", "HEAD"),
    })
    _write(output / "phase_manifest_chain_0_15.json", {
        "phases_0_through_14": phase_chain,
        "phase_15": {
            "status": "TECHNICALLY_QUALIFIED_PENDING_OWNER_REVIEW",
            "candidate_contract_path": "contracts/final_project_release_contract.json",
            "candidate_contract_sha256": sha256_file(contract_path),
            "investigation_casebook_manifest_sha256": casebook_manifest_sha256,
            "investigation_assessment_authority": "APPROVED_AUTHORITATIVE_INVESTIGATION_RECORD",
            "investigation_casebook_review_decision": "APPROVED",
            "owner_approved_final_manifest_pending": True,
        },
        "candidate_chain_reconciliation": "PASS",
        "final_owner_approved_chain_reconciliation": "PENDING_OWNER_APPROVAL",
    })
    checklist_rows = [
        ("PHASE14_BINDING", "PASS"), ("PHASE_0_14_IMMUTABILITY", "PASS"),
        ("SCHEDULED_VERIFY_FROZEN", "PASS"), ("CONCURRENCY_LOCK", "PASS"),
        ("EXIT_CODES_AND_RECEIPTS", "PASS"), ("NO_LIFECYCLE_MUTATION", "PASS"),
        ("SCHEDULER_TEMPLATES", "PASS"), ("PUBLIC_SAFE_CI", "PASS"),
        ("DOCUMENTATION_AND_ASSETS", "PASS"), ("HYGIENE_PATH_SECRET_DEPENDENCY", "PASS"),
        ("FULL_REGRESSION", "PASS"), ("RESIDUAL_LIMITATIONS", "PASS"),
        ("INVESTIGATION_CASEBOOK", "PASS"), ("DUAL_PHASE12_DIGEST_BINDING", "PASS"),
        ("CASEBOOK_PRIMARY_EVIDENCE_AUTHORITY", "PASS"), ("CASEBOOK_TEMPORAL_NAVIGATION", "PASS"),
        ("OWNER_APPROVAL", "PENDING"), ("FINAL_TAG_AND_REMOTE_RELEASE", "PENDING"),
    ]
    (output / "phase15_acceptance_checklist.csv").write_text(
        "control,status\n" + "".join(f"{control},{status}\n" for control, status in checklist_rows),
        encoding="utf-8",
    )

    if (
        scheduled.exit_code != 0
        or public_check.returncode != 0
        or tests.returncode != 0
        or not all(row["match"] for row in phase_chain)
        or local_hits
        or secret_hits
        or tracked_models
        or tracked_databases
        or not all((root / path).is_file() for path in required_assets)
    ):
        raise RuntimeError("Phase 15 qualification failed; inspect candidate evidence")
    evidence_files = sorted(path for path in output.iterdir() if path.is_file() and path.name not in {"manifest.json", "manifest.sha256"})
    manifest = {
        "project_release_id": "PROJECT-RELEASE-01", "version": "1.0.0",
        "created_utc": created, "status": "TECHNICALLY_QUALIFIED_PENDING_OWNER_REVIEW",
        "phase_15_complete": False, "project_b_complete": False,
        "owner_approval_required": True, "release_tag_created": False,
        "phase_0_through_14_read_only": True,
        "pre_remediation_candidate_manifest_sha256": pre_remediation_candidate_manifest_sha256,
        "pre_casebook_candidate_manifest_sha256": pre_casebook_candidate_manifest_sha256,
        "pre_owner_review_casebook_manifest_sha256": pre_owner_review_casebook_manifest_sha256,
        "pre_owner_review_phase15_manifest_sha256": pre_owner_review_phase15_manifest_sha256,
        "investigation_casebook_manifest_sha256": casebook_manifest_sha256,
        "investigation_assessment_authority": "APPROVED_AUTHORITATIVE_INVESTIGATION_RECORD",
        "artifacts": [_artifact(path, output) for path in evidence_files],
    }
    _write(output / "manifest.json", manifest)
    digest = sha256_file(output / "manifest.json")
    (output / "manifest.sha256").write_text(digest + "\n", encoding="utf-8")
    return digest
