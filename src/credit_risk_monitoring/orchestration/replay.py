"""Isolated semantic replay controls; never overwrites authoritative evidence."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from credit_risk_monitoring.history.digest import semantic_database_manifest
from credit_risk_monitoring.history.ingest import HistoryIngestor
from credit_risk_monitoring.history.store import connect_history
from credit_risk_monitoring.qualification.binding import sha256_file


def isolated_semantic_replay(project_root: Path, output_root: Path, contract: dict) -> dict:
    output_root.mkdir(parents=True, exist_ok=False)
    rebuilt = output_root / "monitoring_history_replay.db"
    result = HistoryIngestor(project_root, rebuilt).ingest()
    connection = connect_history(rebuilt, read_only=True)
    try:
        semantic = semantic_database_manifest(connection)
    finally:
        connection.close()
    chain = [{
        "phase": item["phase"], "control_id": item["control_id"], "actual_sha256": sha256_file(project_root / item["path"]),
        "expected_sha256": item["sha256"], "match": sha256_file(project_root / item["path"]) == item["sha256"],
    } for item in contract["phase_manifest_chain"]]
    payload = {
        "mode": "ISOLATED_SEMANTIC_REPLAY", "result": "PASS",
        "full_upstream_calculation_replay_performed": False,
        "reason": "Frozen Phase 6-11 evidence is hash-verified; Phase 12 is rebuilt semantically in isolation without overwriting authoritative artifacts.",
        "public_repository_full_local_replay_claimed": False,
        "history_ingestion_status": result.status,
        "database_semantic_sha256": semantic["database_semantic_sha256"],
        "database_semantic_match": semantic["database_semantic_sha256"] == contract["database_binding"]["initial_complete_semantic_sha256"],
        "immutable_evidence_semantic_match": semantic["immutable_evidence_semantic_sha256"] == contract["database_binding"]["immutable_evidence_semantic_sha256"],
        "phase_manifest_chain": chain, "all_phase_manifests_match": all(item["match"] for item in chain),
    }
    if not payload["database_semantic_match"] or not payload["immutable_evidence_semantic_match"] or not payload["all_phase_manifests_match"]:
        payload["result"] = "FAIL"
        raise RuntimeError("Isolated semantic replay did not reconcile")
    (output_root / "semantic_replay_result.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rebuilt.unlink()
    return payload


def remove_replay_output(output_root: Path, approved_parent: Path) -> None:
    target = output_root.resolve()
    parent = approved_parent.resolve()
    if parent not in target.parents:
        raise RuntimeError(f"Refusing to remove replay output outside approved root: {target}")
    if target.exists():
        shutil.rmtree(target)
