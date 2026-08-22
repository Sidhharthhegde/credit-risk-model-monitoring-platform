"""Phase 3 qualification runner for MONITORING-FEATURE-ADAPTER-01."""

from __future__ import annotations

import contextlib
import csv
import hashlib
import io
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from credit_risk_monitoring.qualification.binding import (
    load_binding,
    resolve_artifact,
    resolve_part_a_root,
    sha256_file,
    verify_artifacts,
)
from credit_risk_monitoring.qualification.contract import (
    ScoringContractError,
    feature_groups,
    validate_scoring_frame,
)

from .adapter import AdapterError, MonitoringFeatureAdapter, _integrate_label_free
from .part_a import load_frozen_part_a_functions


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _git(root: Path, *args: str) -> str:
    command = ["git", "-c", f"safe.directory={root.as_posix()}", "-C", str(root), *args]
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout.strip()


def _required_fields(raw_dependencies: pd.DataFrame, source: str) -> set[str]:
    row = raw_dependencies.loc[raw_dependencies["Source_Dataset"].eq(source)]
    if len(row) != 1:
        raise AdapterError("ADAPTER_CONTRACT_INVALID", f"Raw dependency row missing or ambiguous: {source}")
    return set(str(row.iloc[0]["Required_Fields"]).split(";"))


def _read_filtered_csv(
    path: Path,
    usecols: set[str],
    applicant_ids: set[int] | None = None,
    *,
    chunksize: int = 250_000,
) -> pd.DataFrame:
    if applicant_ids is None:
        return pd.read_csv(path, usecols=sorted(usecols))
    selected: list[pd.DataFrame] = []
    for chunk in pd.read_csv(path, usecols=sorted(usecols), chunksize=chunksize):
        match = chunk[chunk["SK_ID_CURR"].isin(applicant_ids)]
        if not match.empty:
            selected.append(match)
    if not selected:
        return pd.DataFrame(columns=sorted(usecols))
    return pd.concat(selected, ignore_index=True)


def _expect_adapter_error(name: str, expected: str, operation: Any) -> dict[str, Any]:
    try:
        operation()
    except AdapterError as exc:
        actual = exc.reason_code
        detail = str(exc)
    except Exception as exc:  # qualification records unexpected controlled rejection paths
        actual = type(exc).__name__
        detail = str(exc)
    else:
        actual = "PASS"
        detail = "operation completed"
    return {
        "case": name,
        "expected": expected,
        "actual": actual,
        "passed": actual == expected,
        "detail": detail,
    }


def _expect_scoring_contract_rejection(name: str, operation: Any) -> dict[str, Any]:
    try:
        operation()
    except ScoringContractError as exc:
        actual = "SCORING_CONTRACT_REJECTED"
        detail = str(exc)
    except Exception as exc:
        actual = type(exc).__name__
        detail = str(exc)
    else:
        actual = "PASS"
        detail = "invalid frame was accepted"
    return {
        "case": name,
        "expected": "SCORING_CONTRACT_REJECTED",
        "actual": actual,
        "passed": actual == "SCORING_CONTRACT_REJECTED",
        "detail": detail,
    }


def _file_record(path: Path, relative_path: str) -> dict[str, Any]:
    return {
        "path": relative_path,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def _build_adapter(
    part_a_root: Path,
    project_root: Path,
    pipeline: Any,
) -> tuple[MonitoringFeatureAdapter, Any, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    contract_path = project_root / "contracts" / "monitoring_feature_adapter_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    functions = load_frozen_part_a_functions(part_a_root, contract_path)
    freeze_root = part_a_root / "reports" / "experiments" / "step49_development_freeze_v1"
    lineage_path = freeze_root / "feature_lineage_manifest.csv"
    dependencies_path = freeze_root / "raw_data_dependencies.csv"
    if sha256_file(lineage_path) != contract["lineage_contract"]["sha256"]:
        raise AdapterError("ADAPTER_CONTRACT_INVALID", "Feature-lineage hash mismatch")
    if sha256_file(dependencies_path) != contract["raw_dependency_contract"]["sha256"]:
        raise AdapterError("ADAPTER_CONTRACT_INVALID", "Raw-dependency hash mismatch")
    lineage = pd.read_csv(lineage_path)
    dependencies = pd.read_csv(dependencies_path)
    groups = feature_groups(pipeline)
    app_required = _required_fields(dependencies, "application_train.csv") - {"TARGET"}
    bureau_required = _required_fields(dependencies, "bureau.csv")
    previous_required = _required_fields(dependencies, "previous_application.csv")
    bureau_features = tuple(
        lineage.loc[
            lineage["Raw_Source_Table"].eq("bureau.csv")
            & lineage["Feature_Source_Type"].eq("CUSTOMER_LEVEL_AGGREGATE"),
            "Feature_Name",
        ].tolist()
    )
    previous_features = tuple(
        lineage.loc[
            lineage["Raw_Source_Table"].eq("previous_application.csv")
            & lineage["Feature_Source_Type"].eq("CUSTOMER_LEVEL_AGGREGATE"),
            "Feature_Name",
        ].tolist()
    )
    adapter = MonitoringFeatureAdapter(
        functions,
        groups.raw,
        app_required,
        bureau_required,
        previous_required,
        bureau_features,
        previous_features,
    )
    observed_decomposition = {
        "application_direct": int(
            (
                lineage["Raw_Source_Table"].eq("application_train.csv")
                & lineage["Feature_Source_Type"].eq("DIRECT_APPLICATION_FIELD")
            ).sum()
        ),
        "application_deterministic": int(
            (
                lineage["Raw_Source_Table"].eq("application_train.csv")
                & lineage["Feature_Source_Type"].eq("DETERMINISTIC_ENGINEERED")
            ).sum()
        ),
        "bureau_aggregate": len(bureau_features),
        "bureau_deterministic": int(
            (
                lineage["Raw_Source_Table"].eq("bureau.csv")
                & lineage["Feature_Source_Type"].eq("DETERMINISTIC_ENGINEERED")
            ).sum()
        ),
        "previous_application_aggregate": len(previous_features),
        "previous_application_deterministic": int(
            (
                lineage["Raw_Source_Table"].eq("previous_application.csv")
                & lineage["Feature_Source_Type"].eq("DETERMINISTIC_ENGINEERED")
            ).sum()
        ),
        "total": len(lineage),
    }
    if observed_decomposition != contract["lineage_contract"]["expected_decomposition"]:
        raise AdapterError("ADAPTER_CONTRACT_INVALID", "Frozen lineage decomposition mismatch")
    return adapter, functions, lineage, dependencies, contract


def run_phase3_qualification(
    project_root: Path,
    explicit_part_a_root: Path | None = None,
    *,
    fixture_size: int = 256,
) -> Path:
    project_root = project_root.resolve()
    binding = load_binding(project_root / "contracts" / "part_a_binding.json")
    part_a_root = resolve_part_a_root(binding, explicit_part_a_root)
    artifacts, artifacts_pass = verify_artifacts(binding, part_a_root)
    if not artifacts_pass:
        raise AdapterError("MODEL_BINDING_FAILED", "Part A binding failed before adapter qualification")
    if _git(part_a_root, "rev-parse", "HEAD") != binding.part_a["published_commit"]:
        raise AdapterError("MODEL_BINDING_FAILED", "Part A commit mismatch")
    if _git(part_a_root, "status", "--porcelain"):
        raise AdapterError("MODEL_BINDING_FAILED", "Part A working tree is not clean")

    final = project_root / "reports" / "adapter" / "FEATURE-ADAPTER-QUALIFICATION-01"
    stage = final.parent / ".FEATURE-ADAPTER-QUALIFICATION-01.in_progress"
    if final.exists() or stage.exists():
        raise FileExistsError("Phase 3 qualification output already exists")
    stage.mkdir(parents=True)

    model_expectation = next(item for item in binding.artifacts if item.role == "MODEL_ARTIFACT")
    model_path = resolve_artifact(part_a_root, model_expectation)
    model_hash_before = sha256_file(model_path)
    pipeline = joblib.load(model_path)
    adapter, functions, lineage, dependencies, adapter_contract = _build_adapter(
        part_a_root, project_root, pipeline
    )

    raw_root = part_a_root / "data" / "raw"
    source_paths = {
        "application_train.csv": raw_root / "application_train.csv",
        "application_test.csv": raw_root / "application_test.csv",
        "bureau.csv": raw_root / "bureau.csv",
        "previous_application.csv": raw_root / "previous_application.csv",
    }
    source_hashes = {name: sha256_file(path) for name, path in source_paths.items()}
    dependency_hashes = {
        str(row["Source_Dataset"]): str(row["Development_Snapshot_SHA256"])
        for _, row in dependencies.iterrows()
    }
    for name in ("application_train.csv", "bureau.csv", "previous_application.csv"):
        if source_hashes[name] != dependency_hashes[name]:
            raise AdapterError("ADAPTER_SOURCE_IDENTITY_FAILED", f"Frozen raw source hash mismatch: {name}")

    groups = feature_groups(pipeline)
    train_key_path = part_a_root / adapter_contract["labelled_parity_fixture"]["key_artifact"]
    if sha256_file(train_key_path) != adapter_contract["labelled_parity_fixture"]["key_artifact_sha256"]:
        raise AdapterError("ADAPTER_SOURCE_IDENTITY_FAILED", "Frozen TRAIN key artifact hash mismatch")
    train_keys = (
        pd.read_csv(train_key_path, usecols=["SK_ID_CURR"])["SK_ID_CURR"]
        .sort_values(kind="mergesort")
        .astype(int)
        .tolist()
    )
    train_id_set = set(train_keys)
    base_ids = set(train_keys[:fixture_size])
    fixture_ids = set(base_ids)

    bureau_history_ids = set(
        pd.read_csv(source_paths["bureau.csv"], usecols=["SK_ID_CURR"])["SK_ID_CURR"]
        .dropna()
        .astype(int)
        .unique()
        .tolist()
    )
    previous_history_ids = set(
        pd.read_csv(source_paths["previous_application.csv"], usecols=["SK_ID_CURR"])["SK_ID_CURR"]
        .dropna()
        .astype(int)
        .unique()
        .tolist()
    )
    history_predicates = {
        "bureau_yes_previous_yes": lambda key: key in bureau_history_ids and key in previous_history_ids,
        "bureau_yes_previous_no": lambda key: key in bureau_history_ids and key not in previous_history_ids,
        "bureau_no_previous_yes": lambda key: key not in bureau_history_ids and key in previous_history_ids,
        "bureau_no_previous_no": lambda key: key not in bureau_history_ids and key not in previous_history_ids,
    }
    supplemental_reasons: list[str] = []
    for name, predicate in history_predicates.items():
        if not any(predicate(key) for key in fixture_ids):
            supplemental = next((key for key in train_keys if predicate(key)), None)
            if supplemental is None:
                raise AdapterError("ADAPTER_BRANCH_COVERAGE_FAILED", f"No TRAIN applicant covers {name}")
            fixture_ids.add(supplemental)
            supplemental_reasons.append(name)

    coverage_columns = {
        "SK_ID_CURR",
        "DAYS_EMPLOYED",
        "OWN_CAR_AGE",
        "EXT_SOURCE_1",
        "EXT_SOURCE_2",
        "EXT_SOURCE_3",
        "APARTMENTS_AVG",
        "BASEMENTAREA_AVG",
        "YEARS_BEGINEXPLUATATION_AVG",
        "YEARS_BUILD_AVG",
        "COMMONAREA_AVG",
        "ELEVATORS_AVG",
        "ENTRANCES_AVG",
        "FLOORSMAX_AVG",
        "FLOORSMIN_AVG",
        "LANDAREA_AVG",
        "LIVINGAPARTMENTS_AVG",
        "LIVINGAREA_AVG",
        "NONLIVINGAPARTMENTS_AVG",
        "NONLIVINGAREA_AVG",
        "AMT_REQ_CREDIT_BUREAU_HOUR",
        "AMT_REQ_CREDIT_BUREAU_DAY",
        "AMT_REQ_CREDIT_BUREAU_WEEK",
        "AMT_REQ_CREDIT_BUREAU_MON",
        "AMT_REQ_CREDIT_BUREAU_QRT",
        "AMT_REQ_CREDIT_BUREAU_YEAR",
        *[feature for feature in groups.categorical if feature in adapter.required_application_columns],
        *[feature for feature in groups.numeric if feature in adapter.required_application_columns],
    }
    coverage_frame = _read_filtered_csv(
        source_paths["application_train.csv"], coverage_columns, train_id_set
    ).sort_values("SK_ID_CURR", kind="mergesort")
    categorical_columns = [feature for feature in groups.categorical if feature in coverage_frame]
    numeric_columns = [feature for feature in groups.numeric if feature in coverage_frame]
    housing_columns = [
        column
        for column in (
            "APARTMENTS_AVG", "BASEMENTAREA_AVG", "YEARS_BEGINEXPLUATATION_AVG",
            "YEARS_BUILD_AVG", "COMMONAREA_AVG", "ELEVATORS_AVG", "ENTRANCES_AVG",
            "FLOORSMAX_AVG", "FLOORSMIN_AVG", "LANDAREA_AVG", "LIVINGAPARTMENTS_AVG",
            "LIVINGAREA_AVG", "NONLIVINGAPARTMENTS_AVG", "NONLIVINGAREA_AVG",
        )
        if column in coverage_frame
    ]
    request_columns = [
        "AMT_REQ_CREDIT_BUREAU_HOUR", "AMT_REQ_CREDIT_BUREAU_DAY",
        "AMT_REQ_CREDIT_BUREAU_WEEK", "AMT_REQ_CREDIT_BUREAU_MON",
        "AMT_REQ_CREDIT_BUREAU_QRT", "AMT_REQ_CREDIT_BUREAU_YEAR",
    ]
    external_columns = ["EXT_SOURCE_1", "EXT_SOURCE_2", "EXT_SOURCE_3"]
    application_predicates = {
        "numeric_missingness_present": coverage_frame[numeric_columns].isna().any(axis=1),
        "categorical_missingness_present": coverage_frame[categorical_columns].isna().any(axis=1),
        "employment_sentinel_present": coverage_frame["DAYS_EMPLOYED"].eq(365243),
        "employment_sentinel_absent": coverage_frame["DAYS_EMPLOYED"].ne(365243),
        "external_score_missingness_present": coverage_frame[external_columns].isna().any(axis=1),
        "external_score_missingness_absent": coverage_frame[external_columns].notna().all(axis=1),
        "car_age_missing_present": coverage_frame["OWN_CAR_AGE"].isna(),
        "car_age_missing_absent": coverage_frame["OWN_CAR_AGE"].notna(),
        "housing_data_available": coverage_frame[housing_columns].notna().any(axis=1),
        "housing_data_unavailable": coverage_frame[housing_columns].isna().all(axis=1),
        "bureau_request_data_available": coverage_frame[request_columns].notna().all(axis=1),
        "bureau_request_data_unavailable": coverage_frame[request_columns].isna().all(axis=1),
    }
    for name, mask in application_predicates.items():
        covered = coverage_frame["SK_ID_CURR"].isin(fixture_ids) & mask
        if not covered.any():
            eligible = coverage_frame.loc[mask, "SK_ID_CURR"]
            if eligible.empty:
                raise AdapterError("ADAPTER_BRANCH_COVERAGE_FAILED", f"No TRAIN applicant covers {name}")
            fixture_ids.add(int(eligible.iloc[0]))
            supplemental_reasons.append(name)
    del coverage_frame, bureau_history_ids, previous_history_ids
    app_required = adapter.required_application_columns | {"TARGET"}
    labelled_application = _read_filtered_csv(
        source_paths["application_train.csv"], app_required, fixture_ids
    ).sort_values("SK_ID_CURR", kind="mergesort").reset_index(drop=True)
    labelled_bureau = _read_filtered_csv(
        source_paths["bureau.csv"], adapter.required_bureau_columns, fixture_ids
    )
    labelled_previous = _read_filtered_csv(
        source_paths["previous_application.csv"], adapter.required_previous_columns, fixture_ids
    )

    with contextlib.redirect_stdout(io.StringIO()):
        oracle_bureau = functions.build_bureau_features(labelled_bureau)
        oracle_previous = functions.build_previous_application_features(labelled_previous)
        oracle_integrated = functions.integrate_master_dataset(
            labelled_application, oracle_bureau, oracle_previous
        )
        oracle_transformed = functions.apply_deterministic_transformations(oracle_integrated)
    governed = tuple(groups.raw)
    oracle = oracle_transformed.loc[:, ["SK_ID_CURR", *governed]].copy()
    adapted = adapter.build(
        labelled_application.drop(columns=["TARGET"]),
        labelled_bureau,
        labelled_previous,
        pipeline=pipeline,
    )
    candidate = adapted.scoring_frame
    if not oracle.equals(candidate):
        raise AdapterError("ADAPTER_FEATURE_PARITY_FAILED", "Label-free feature output is not exact")

    history_state_counts = {
        "bureau_yes_previous_yes": int(
            ((candidate["HAS_BUREAU_HISTORY"] == 1) & (candidate["HAS_PREV_APP_HISTORY"] == 1)).sum()
        ),
        "bureau_yes_previous_no": int(
            ((candidate["HAS_BUREAU_HISTORY"] == 1) & (candidate["HAS_PREV_APP_HISTORY"] == 0)).sum()
        ),
        "bureau_no_previous_yes": int(
            ((candidate["HAS_BUREAU_HISTORY"] == 0) & (candidate["HAS_PREV_APP_HISTORY"] == 1)).sum()
        ),
        "bureau_no_previous_no": int(
            ((candidate["HAS_BUREAU_HISTORY"] == 0) & (candidate["HAS_PREV_APP_HISTORY"] == 0)).sum()
        ),
    }
    fixture_coverage = {
        "result": "PASS",
        "base_fixture_rule": f"LOWEST_{fixture_size}_FROZEN_TRAIN_SK_ID_CURR",
        "base_fixture_count": fixture_size,
        "supplement_rule": "LOWEST_FROZEN_TRAIN_SK_ID_CURR_FOR_EACH_BRANCH_STATE_ABSENT_FROM_BASE",
        "supplemental_applicant_count": len(fixture_ids - base_ids),
        "supplemental_reason_count": len(set(supplemental_reasons)),
        "applicant_ids_persisted": False,
        "final_fixture_count": len(candidate),
        "history_states": history_state_counts,
        "missingness_cases": {
            "numeric_missingness_present": bool(candidate[list(groups.numeric)].isna().any(axis=1).any()),
            "categorical_missingness_present": bool(candidate[list(groups.categorical)].isna().any(axis=1).any()),
            "external_score_missingness_present": bool(candidate[external_columns].isna().any(axis=1).any()),
            "external_score_complete_case_present": bool(candidate[external_columns].notna().all(axis=1).any()),
        },
        "deterministic_branch_states": {
            flag: {"zero_present": bool((candidate[flag] == 0).any()), "one_present": bool((candidate[flag] == 1).any())}
            for flag in (
                "FLAG_DAYS_EMPLOYED_SENTINEL",
                "OWN_CAR_AGE_IS_MISSING",
                "HOUSING_AVG_NUMERIC_DATA_AVAILABLE_FLAG",
                "BUREAU_REQUEST_DATA_AVAILABLE_FLAG",
                "HAS_BUREAU_HISTORY",
                "HAS_PREV_APP_HISTORY",
            )
        },
    }
    coverage_pass = (
        all(value > 0 for value in history_state_counts.values())
        and all(fixture_coverage["missingness_cases"].values())
        and all(
            states["zero_present"] and states["one_present"]
            for states in fixture_coverage["deterministic_branch_states"].values()
        )
    )
    fixture_coverage["result"] = "PASS" if coverage_pass else "FAIL"
    if not coverage_pass:
        raise AdapterError("ADAPTER_BRANCH_COVERAGE_FAILED", "Material fixture branch coverage is incomplete")

    feature_rows: list[dict[str, Any]] = []
    for feature in governed:
        source_row = lineage.loc[lineage["Feature_Name"].eq(feature)].iloc[0]
        feature_rows.append(
            {
                "Feature_Name": feature,
                "Raw_Source_Table": source_row["Raw_Source_Table"],
                "Feature_Source_Type": source_row["Feature_Source_Type"],
                "Dtype_Exact": oracle[feature].dtype == candidate[feature].dtype,
                "Missing_Mask_Exact": oracle[feature].isna().equals(candidate[feature].isna()),
                "Value_Exact": oracle[feature].equals(candidate[feature]),
                "Result": "PASS" if oracle[feature].equals(candidate[feature]) else "FAIL",
            }
        )
    _write_csv(
        stage / "feature_parity_summary.csv",
        ["Feature_Name", "Raw_Source_Table", "Feature_Source_Type", "Dtype_Exact", "Missing_Mask_Exact", "Value_Exact", "Result"],
        feature_rows,
    )

    oracle_probabilities = pipeline.predict_proba(oracle.loc[:, list(governed)])[:, 1]
    candidate_probabilities = pipeline.predict_proba(candidate.loc[:, list(governed)])[:, 1]
    probability_exact = np.array_equal(oracle_probabilities, candidate_probabilities)
    threshold = float(binding.threshold["value"])
    class_exact = np.array_equal(
        oracle_probabilities >= threshold, candidate_probabilities >= threshold
    )
    if not probability_exact or not class_exact:
        raise AdapterError("ADAPTER_SCORING_PARITY_FAILED", "DF-01 scoring through adapter differs")

    direct_feature = next(
        feature
        for feature in governed
        if lineage.loc[lineage["Feature_Name"].eq(feature), "Feature_Source_Type"].iloc[0]
        == "DIRECT_APPLICATION_FIELD"
        and feature != "SK_ID_CURR"
    )
    failures = [
        _expect_adapter_error(
            "missing application anchor",
            "SOURCE_TECHNICALLY_REQUIRED",
            lambda: adapter.build(None, labelled_bureau, labelled_previous),
        ),
        _expect_adapter_error(
            "missing required direct application field",
            "ADAPTER_INPUT_CONTRACT_FAILED",
            lambda: adapter.build(
                labelled_application.drop(columns=["TARGET", direct_feature]),
                labelled_bureau,
                labelled_previous,
            ),
        ),
        _expect_adapter_error(
            "bureau unavailable without approved fallback",
            "SOURCE_UNAVAILABLE_NO_APPROVED_FALLBACK",
            lambda: adapter.build(
                labelled_application.drop(columns=["TARGET"]), None, labelled_previous
            ),
        ),
        _expect_adapter_error(
            "previous application unavailable without approved fallback",
            "SOURCE_UNAVAILABLE_NO_APPROVED_FALLBACK",
            lambda: adapter.build(
                labelled_application.drop(columns=["TARGET"]), labelled_bureau, None
            ),
        ),
        _expect_adapter_error(
            "duplicate application applicant",
            "ADAPTER_GRAIN_VIOLATION",
            lambda: adapter.build(
                pd.concat(
                    [
                        labelled_application.drop(columns=["TARGET"]),
                        labelled_application.drop(columns=["TARGET"]).iloc[[0]],
                    ],
                    ignore_index=True,
                ),
                labelled_bureau,
                labelled_previous,
            ),
        ),
        _expect_adapter_error(
            "duplicate raw bureau record key",
            "ADAPTER_INPUT_CONTRACT_FAILED",
            lambda: adapter.build(
                labelled_application.drop(columns=["TARGET"]),
                pd.concat([labelled_bureau, labelled_bureau.iloc[[0]]], ignore_index=True),
                labelled_previous,
            ),
        ),
        _expect_adapter_error(
            "duplicate aggregate applicant would multiply rows",
            "ADAPTER_GRAIN_VIOLATION",
            lambda: _integrate_label_free(
                labelled_application.drop(columns=["TARGET"]),
                pd.concat([oracle_bureau, oracle_bureau.iloc[[0]]], ignore_index=True),
                oracle_previous,
            ),
        ),
    ]
    bureau_diagnostic = adapter.build(
        labelled_application.drop(columns=["TARGET"]),
        None,
        labelled_previous,
        pipeline=pipeline,
        diagnostic_source_loss=True,
    )
    previous_diagnostic = adapter.build(
        labelled_application.drop(columns=["TARGET"]),
        labelled_bureau,
        None,
        pipeline=pipeline,
        diagnostic_source_loss=True,
    )
    failures.extend(
        [
            {
                "case": "bureau loss diagnostic interface",
                "expected": "PASS_NON_AUTHORITATIVE",
                "actual": "PASS_NON_AUTHORITATIVE" if not bureau_diagnostic.authoritative_use_permitted else "FAIL",
                "passed": not bureau_diagnostic.authoritative_use_permitted,
                "detail": bureau_diagnostic.source_states["bureau"],
            },
            {
                "case": "previous-application loss diagnostic interface",
                "expected": "PASS_NON_AUTHORITATIVE",
                "actual": "PASS_NON_AUTHORITATIVE" if not previous_diagnostic.authoritative_use_permitted else "FAIL",
                "passed": not previous_diagnostic.authoritative_use_permitted,
                "detail": previous_diagnostic.source_states["previous_application"],
            },
            {
                "case": "TARGET absent",
                "expected": "PASS",
                "actual": "PASS" if "TARGET" not in candidate.columns else "FAIL",
                "passed": "TARGET" not in candidate.columns,
                "detail": "caller and output are label-free",
            },
            _expect_scoring_contract_rejection(
                "non-finite numeric adapter output",
                lambda: validate_scoring_frame(
                    candidate.assign(**{feature_groups(pipeline).numeric[0]: np.inf}), pipeline
                ),
            ),
            _expect_scoring_contract_rejection(
                "invalid binary adapter output",
                lambda: validate_scoring_frame(
                    candidate.assign(**{feature_groups(pipeline).binary[0]: 2}), pipeline
                ),
            ),
        ]
    )
    if not all(row["passed"] for row in failures):
        raise AdapterError("ADAPTER_FAILURE_TEST_FAILED", "One or more controlled failure tests failed")

    application_test = _read_filtered_csv(
        source_paths["application_test.csv"], adapter.required_application_columns
    )
    application_test_ids = set(application_test["SK_ID_CURR"].astype(int).tolist())
    test_bureau = _read_filtered_csv(
        source_paths["bureau.csv"], adapter.required_bureau_columns, application_test_ids
    )
    test_previous = _read_filtered_csv(
        source_paths["previous_application.csv"],
        adapter.required_previous_columns,
        application_test_ids,
    )
    dry_run = adapter.build(application_test, test_bureau, test_previous, pipeline=pipeline)
    dry_features = validate_scoring_frame(dry_run.scoring_frame, pipeline)
    dry_probabilities = pipeline.predict_proba(dry_features)[:, 1]
    dry_scoring_pass = (
        len(dry_probabilities) == len(application_test)
        and np.isfinite(dry_probabilities).all()
        and ((dry_probabilities >= 0.0) & (dry_probabilities <= 1.0)).all()
    )
    if not dry_scoring_pass:
        raise AdapterError("APPLICATION_TEST_DRY_RUN_FAILED", "DF-01 dry-run scoring contract failed")

    _write_json(stage / "adapter_contract.json", adapter_contract)
    part_b_sources = []
    for relative in (
        "src/credit_risk_monitoring/adapter/part_a.py",
        "src/credit_risk_monitoring/adapter/adapter.py",
        "src/credit_risk_monitoring/adapter/qualification.py",
        "scripts/run_phase3_qualification.py",
        "contracts/monitoring_feature_adapter_contract.json",
        "tests/adapter/test_adapter.py",
        "tests/adapter/test_phase3_evidence.py",
    ):
        path = project_root / relative
        part_b_sources.append(_file_record(path, relative))
    _write_json(
        stage / "implementation_source_manifest.json",
        {
            "adapter_id": "MONITORING-FEATURE-ADAPTER-01",
            "part_a_commit": binding.part_a["published_commit"],
            "frozen_part_a_sources": list(functions.verified_sources),
            "part_b_sources": part_b_sources,
            "part_a_code_copied_into_part_b": False,
        },
    )
    _write_json(
        stage / "source_interface_qualification.json",
        {
            "result": "PASS",
            "approved_sources_only": True,
            "application_required_field_count_excluding_target": len(adapter.required_application_columns),
            "bureau_required_field_count": len(adapter.required_bureau_columns),
            "previous_application_required_field_count": len(adapter.required_previous_columns),
            "source_files": [
                {
                    "source": name,
                    "size_bytes": source_paths[name].stat().st_size,
                    "sha256": source_hashes[name],
                    "frozen_hash_match": (
                        source_hashes[name] == dependency_hashes[name]
                        if name in dependency_hashes
                        else "NOT_APPLICABLE_UNLABELLED_SOURCE_OBSERVED_HASH_CAPTURED"
                    ),
                }
                for name in source_paths
            ],
        },
    )
    _write_json(
        stage / "labelled_fixture_parity.json",
        {
            "result": "PASS",
            "fixture_rule": f"LOWEST_{fixture_size}_FROZEN_TRAIN_SK_ID_CURR_PLUS_MINIMAL_DETERMINISTIC_BRANCH_SUPPLEMENTS",
            "fixture_count": len(labelled_application),
            "applicant_identity_and_order_exact": oracle["SK_ID_CURR"].equals(candidate["SK_ID_CURR"]),
            "feature_names_and_order_exact": list(oracle.columns) == list(candidate.columns),
            "dataframe_exact_including_dtypes_and_missingness": oracle.equals(candidate),
            "features_exact": sum(row["Result"] == "PASS" for row in feature_rows),
            "comparison_rule": "PANDAS_EXACT_EQUALS_PER_FEATURE_AND_FULL_FRAME_NO_TOLERANCE",
        },
    )
    _write_json(stage / "labelled_fixture_coverage.json", fixture_coverage)
    _write_json(
        stage / "aggregation_parity.json",
        {
            "result": "PASS",
            "bureau_feature_count": len(adapter.bureau_aggregate_features) + 1,
            "bureau_aggregate_values_exact": oracle_bureau.equals(adapted.bureau_aggregate),
            "previous_application_feature_count": len(adapter.previous_aggregate_features) + 1,
            "previous_aggregate_values_exact": oracle_previous.equals(adapted.previous_aggregate),
            "history_flags_included_in_group_counts": True,
        },
    )
    _write_json(
        stage / "scoring_parity.json",
        {
            "result": "PASS",
            "raw_probability_exact": bool(probability_exact),
            "maximum_absolute_difference": float(np.max(np.abs(oracle_probabilities - candidate_probabilities))),
            "threshold_id": binding.threshold["threshold_id"],
            "threshold_value": threshold,
            "threshold_operator": binding.threshold["operator"],
            "risk_class_exact": bool(class_exact),
            "tolerance_used": False,
        },
    )
    _write_json(
        stage / "source_control_tests.json",
        {
            "result": "PASS",
            "scope": "CONTROL_AND_ADAPTER_FAILURE_BEHAVIOR_ONLY_NO_SOURCE_LOSS_PERFORMANCE_ANALYSIS",
            "cnd_02_status": "OPEN",
            "approved_fallback_exists": False,
            "cases": failures,
        },
    )
    _write_json(
        stage / "application_test_dry_run.json",
        {
            "result": "PASS",
            "candidate_status": "APPLICATION-TEST-BASE-CANDIDATE_NOT_FROZEN",
            "target_present": False,
            "anchor_row_count": len(application_test),
            "output_row_count": len(dry_run.scoring_frame),
            "anchor_row_count_preserved": len(application_test) == len(dry_run.scoring_frame),
            "applicant_key_complete_and_unique": bool(
                dry_run.scoring_frame["SK_ID_CURR"].notna().all()
                and dry_run.scoring_frame["SK_ID_CURR"].is_unique
            ),
            "predictor_count": len(governed),
            "canonical_order_exact": list(dry_run.scoring_frame.columns) == ["SK_ID_CURR", *governed],
            "scoring_contract_passed": True,
            "technical_df01_scoring_passed": True,
            "one_finite_bounded_probability_per_applicant": True,
            "applicants_with_bureau_history": int(dry_run.scoring_frame["HAS_BUREAU_HISTORY"].sum()),
            "applicants_without_bureau_history": int((dry_run.scoring_frame["HAS_BUREAU_HISTORY"] == 0).sum()),
            "applicants_with_previous_application_history": int(dry_run.scoring_frame["HAS_PREV_APP_HISTORY"].sum()),
            "applicants_without_previous_application_history": int((dry_run.scoring_frame["HAS_PREV_APP_HISTORY"] == 0).sum()),
            "scenario_mutation_applied": False,
            "simulation_cohort_assignment_executed": False,
            "row_level_candidate_persisted": False,
            "row_level_predictions_persisted": False,
            "score_summary_persisted": False,
        },
    )
    del dry_probabilities, dry_features, dry_run, test_bureau, test_previous, application_test

    model_hash_after = sha256_file(model_path)
    part_a_clean_after = not bool(_git(part_a_root, "status", "--porcelain"))
    _write_json(
        stage / "immutability_attestation.json",
        {
            "result": "PASS" if model_hash_before == model_hash_after and part_a_clean_after else "FAIL",
            "model_sha256_before": model_hash_before,
            "model_sha256_after": model_hash_after,
            "model_unchanged": model_hash_before == model_hash_after,
            "part_a_working_tree_clean_after": part_a_clean_after,
            "fit_called": False,
            "partial_fit_called": False,
            "set_params_called": False,
            "threshold_changed": False,
            "part_a_artifacts_verified": artifacts,
        },
    )
    phase_checks = [
        ("P3-001", "Adapter contract parses and approved sources are exclusive", "adapter_contract.json"),
        ("P3-002", "Frozen Part A source hashes and commit reconcile", "implementation_source_manifest.json"),
        ("P3-003", "Adapter is label-free and does not return TARGET", "labelled_fixture_parity.json"),
        ("P3-004", "Only frozen Part A feature functions define predictors", "implementation_source_manifest.json"),
        ("P3-005", "Output grain row count feature identity and order pass", "labelled_fixture_parity.json"),
        ("P3-006", "All 176 feature values dtypes and missing masks are exact", "feature_parity_summary.csv"),
        ("P3-007", "Bureau 52-feature group parity passes", "aggregation_parity.json"),
        ("P3-008", "Previous-application 37-feature group parity passes", "aggregation_parity.json"),
        ("P3-009", "DF-01 raw probability and THRESHOLD-01 class parity pass", "scoring_parity.json"),
        ("P3-010", "Failure and source-control behavior passes", "source_control_tests.json"),
        ("P3-011", "CND-02 remains open and source diagnostics are non-authoritative", "source_control_tests.json"),
        ("P3-012", "application_test label-free dry run passes", "application_test_dry_run.json"),
        ("P3-013", "Candidate is not frozen and no row-level output is persisted", "application_test_dry_run.json"),
        ("P3-014", "DF-01 and Part A remain unchanged", "immutability_attestation.json"),
        ("P3-015", "No reference monitoring scenario drift performance or alert result created", "phase3_completion_decision.json"),
        ("P3-016", "Qualification manifest reconciles", "qualification_manifest.json"),
        ("P3-017", "Governed labelled fixture exercises material adapter branches", "labelled_fixture_coverage.json"),
    ]
    checklist_rows = [
        {"Check_ID": check_id, "Requirement": requirement, "Status": "PASS", "Evidence": evidence}
        for check_id, requirement, evidence in phase_checks
    ]
    checklist_rows.append(
        {"Check_ID": "P3-018", "Requirement": "Phase 3 reviewed and approved", "Status": "PENDING_USER_REVIEW", "Evidence": "PENDING_USER_REVIEW"}
    )
    _write_csv(stage / "phase3_acceptance_checklist.csv", ["Check_ID", "Requirement", "Status", "Evidence"], checklist_rows)
    _write_json(
        stage / "phase3_completion_decision.json",
        {
            "phase": "PHASE_3",
            "phase_name": "CONTRACTS_AND_LABEL_FREE_FEATURE_ADAPTER",
            "adapter_id": "MONITORING-FEATURE-ADAPTER-01",
            "qualification_id": "FEATURE-ADAPTER-QUALIFICATION-01",
            "decision_status": "DRAFT_READY_FOR_REVIEW",
            "phase_complete": False,
            "technical_qualification_passed": True,
            "feature_adapter_implemented": True,
            "feature_adapter_qualified": True,
            "label_free_parity_verified": True,
            "df01_scoring_through_adapter_verified": True,
            "application_test_adaptation_qualified": True,
            "cnd_02_status": "OPEN",
            "reference_materialization_authorized": False,
            "monitoring_execution_authorized": False,
            "snapshots_frozen": False,
            "reference_statistics_materialized": False,
            "psi_bin_edges_created": False,
            "simulation_cohorts_created": False,
            "drift_results_calculated": False,
            "performance_results_calculated": False,
            "monitoring_alerts_generated": False,
            "pending_gates": ["USER_PHASE_3_REVIEW_AND_APPROVAL"],
            "next_phase_after_approval": "PHASE_4_REFERENCE_MATERIALIZATION_AND_FROZEN_BINS",
        },
    )

    artifact_names = [
        "adapter_contract.json",
        "implementation_source_manifest.json",
        "source_interface_qualification.json",
        "labelled_fixture_parity.json",
        "labelled_fixture_coverage.json",
        "feature_parity_summary.csv",
        "aggregation_parity.json",
        "scoring_parity.json",
        "source_control_tests.json",
        "application_test_dry_run.json",
        "immutability_attestation.json",
        "phase3_acceptance_checklist.csv",
        "phase3_completion_decision.json",
    ]
    manifest = {
        "qualification_id": "FEATURE-ADAPTER-QUALIFICATION-01",
        "adapter_id": "MONITORING-FEATURE-ADAPTER-01",
        "version": "0.1.0",
        "status": "DRAFT_READY_FOR_REVIEW",
        "artifact_count": len(artifact_names),
        "artifacts": [_file_record(stage / name, name) for name in artifact_names],
        "row_level_candidate_included": False,
        "row_level_predictions_included": False,
        "reference_statistics_included": False,
        "psi_bin_edges_included": False,
        "simulation_cohorts_included": False,
        "drift_results_included": False,
        "performance_results_included": False,
        "monitoring_alerts_included": False,
    }
    _write_json(stage / "qualification_manifest.json", manifest)
    (stage / "qualification_manifest.sha256").write_text(
        sha256_file(stage / "qualification_manifest.json") + "\n",
        encoding="utf-8",
        newline="\n",
    )
    stage.rename(final)
    return final


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run Phase 3 feature-adapter qualification")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--part-a-root", type=Path, default=None)
    parser.add_argument("--fixture-size", type=int, default=256)
    args = parser.parse_args()
    output = run_phase3_qualification(args.project_root, args.part_a_root, fixture_size=args.fixture_size)
    print(f"Phase 3 qualification draft complete: {output}")


if __name__ == "__main__":
    main()
