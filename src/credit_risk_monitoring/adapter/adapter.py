"""Thin label-free integration wrapper over frozen Part A feature functions."""

from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass
from typing import Any

import pandas as pd

from credit_risk_monitoring.qualification.contract import validate_scoring_frame

from .part_a import FrozenPartAFeatureFunctions


class AdapterError(ValueError):
    """Controlled adapter failure with a stable reason code."""

    def __init__(self, reason_code: str, message: str):
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True)
class AdapterBuildResult:
    scoring_frame: pd.DataFrame
    bureau_aggregate: pd.DataFrame
    previous_aggregate: pd.DataFrame
    source_states: dict[str, str]
    authoritative_use_permitted: bool


def _require_columns(frame: pd.DataFrame, required: set[str], source: str) -> None:
    if frame.columns.duplicated().any():
        raise AdapterError("ADAPTER_INPUT_CONTRACT_FAILED", f"{source} has duplicate columns")
    missing = required - set(frame.columns)
    if missing:
        raise AdapterError(
            "ADAPTER_INPUT_CONTRACT_FAILED",
            f"{source} is missing required columns: {sorted(missing)}",
        )


def _validate_anchor(application: pd.DataFrame, required: set[str]) -> None:
    _require_columns(application, required, "application")
    if "TARGET" in application.columns:
        raise AdapterError("UNSUPPORTED_TARGET_DEPENDENCY", "Label-free adapter input must not contain TARGET")
    if application.empty:
        raise AdapterError("SOURCE_TECHNICALLY_REQUIRED", "Application anchor is empty")
    if application["SK_ID_CURR"].isna().any() or not application["SK_ID_CURR"].is_unique:
        raise AdapterError("ADAPTER_GRAIN_VIOLATION", "Application SK_ID_CURR must be complete and unique")


def _validate_raw_many(frame: pd.DataFrame, required: set[str], source: str, record_key: str) -> None:
    _require_columns(frame, required, source)
    if frame["SK_ID_CURR"].isna().any() or frame[record_key].isna().any():
        raise AdapterError("ADAPTER_INPUT_CONTRACT_FAILED", f"{source} keys must be complete")
    if not frame[record_key].is_unique:
        raise AdapterError("ADAPTER_INPUT_CONTRACT_FAILED", f"{source} {record_key} must be unique")


def _validate_aggregate(frame: pd.DataFrame, source: str) -> None:
    if frame.columns.duplicated().any() or frame["SK_ID_CURR"].isna().any() or not frame["SK_ID_CURR"].is_unique:
        raise AdapterError("ADAPTER_GRAIN_VIOLATION", f"{source} aggregate is not one row per SK_ID_CURR")


def _integrate_label_free(
    application: pd.DataFrame,
    bureau_aggregate: pd.DataFrame,
    previous_aggregate: pd.DataFrame,
) -> pd.DataFrame:
    _validate_aggregate(bureau_aggregate, "bureau")
    _validate_aggregate(previous_aggregate, "previous_application")
    try:
        result = application.merge(
            bureau_aggregate, on="SK_ID_CURR", how="left", validate="one_to_one", sort=False
        ).copy()
        result = result.assign(
            HAS_BUREAU_HISTORY=result["BUREAU_ACCOUNT_COUNT"].notna().astype(int)
        )
        result = result.merge(
            previous_aggregate,
            on="SK_ID_CURR",
            how="left",
            validate="one_to_one",
            sort=False,
        ).copy()
        result = result.assign(
            HAS_PREV_APPLICATION_HISTORY=result["PREV_APPLICATION_COUNT"]
            .notna()
            .astype(int)
        )
    except pd.errors.MergeError as exc:
        raise AdapterError("ADAPTER_GRAIN_VIOLATION", "One-to-one source integration failed") from exc
    if len(result) != len(application):
        raise AdapterError("ADAPTER_ROW_MULTIPLICATION", "Adapter changed the anchor row count")
    if result["SK_ID_CURR"].tolist() != application["SK_ID_CURR"].tolist():
        raise AdapterError("ADAPTER_GRAIN_VIOLATION", "Adapter changed applicant identity or order")
    return result


class MonitoringFeatureAdapter:
    def __init__(
        self,
        functions: FrozenPartAFeatureFunctions,
        governed_features: tuple[str, ...],
        required_application_columns: set[str],
        required_bureau_columns: set[str],
        required_previous_columns: set[str],
        bureau_aggregate_features: tuple[str, ...],
        previous_aggregate_features: tuple[str, ...],
    ) -> None:
        self.functions = functions
        self.governed_features = governed_features
        self.required_application_columns = required_application_columns
        self.required_bureau_columns = required_bureau_columns
        self.required_previous_columns = required_previous_columns
        self.bureau_aggregate_features = bureau_aggregate_features
        self.previous_aggregate_features = previous_aggregate_features
        if len(governed_features) != 176 or len(set(governed_features)) != 176:
            raise AdapterError("ADAPTER_CONTRACT_INVALID", "Governed feature identity must be 176 unique names")

    def _empty_aggregate(self, features: tuple[str, ...]) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "SK_ID_CURR": pd.Series(dtype="int64"),
                **{feature: pd.Series(dtype="float64") for feature in features},
            }
        )

    def _deterministic_label_free(self, integrated: pd.DataFrame, placeholder: int = 0) -> pd.DataFrame:
        if "TARGET" in integrated.columns:
            raise AdapterError("UNSUPPORTED_TARGET_DEPENDENCY", "TARGET reached the label-free bridge")
        bridged = integrated.copy()
        bridged["TARGET"] = placeholder
        with contextlib.redirect_stdout(io.StringIO()):
            transformed = self.functions.apply_deterministic_transformations(bridged)
        return transformed.drop(columns=["TARGET"])

    def build(
        self,
        application: pd.DataFrame | None,
        bureau: pd.DataFrame | None,
        previous_application: pd.DataFrame | None,
        *,
        pipeline: Any | None = None,
        diagnostic_source_loss: bool = False,
    ) -> AdapterBuildResult:
        if application is None:
            raise AdapterError("SOURCE_TECHNICALLY_REQUIRED", "Application anchor is unavailable")
        _validate_anchor(application, self.required_application_columns)
        source_states: dict[str, str] = {"application": "SOURCE_AVAILABLE"}
        authoritative = True

        if bureau is None:
            if not diagnostic_source_loss:
                raise AdapterError(
                    "SOURCE_UNAVAILABLE_NO_APPROVED_FALLBACK", "Bureau source is unavailable"
                )
            bureau_aggregate = self._empty_aggregate(self.bureau_aggregate_features)
            source_states["bureau"] = "SOURCE_UNAVAILABLE_NO_APPROVED_FALLBACK"
            authoritative = False
        else:
            _validate_raw_many(bureau, self.required_bureau_columns, "bureau", "SK_ID_BUREAU")
            with contextlib.redirect_stdout(io.StringIO()):
                bureau_aggregate = self.functions.build_bureau_features(bureau)
            source_states["bureau"] = "SOURCE_AVAILABLE"

        if previous_application is None:
            if not diagnostic_source_loss:
                raise AdapterError(
                    "SOURCE_UNAVAILABLE_NO_APPROVED_FALLBACK",
                    "Previous-application source is unavailable",
                )
            previous_aggregate = self._empty_aggregate(self.previous_aggregate_features)
            source_states["previous_application"] = "SOURCE_UNAVAILABLE_NO_APPROVED_FALLBACK"
            authoritative = False
        else:
            _validate_raw_many(
                previous_application,
                self.required_previous_columns,
                "previous_application",
                "SK_ID_PREV",
            )
            with contextlib.redirect_stdout(io.StringIO()):
                previous_aggregate = self.functions.build_previous_application_features(
                    previous_application
                )
            source_states["previous_application"] = "SOURCE_AVAILABLE"

        integrated = _integrate_label_free(application, bureau_aggregate, previous_aggregate)
        transformed_zero = self._deterministic_label_free(integrated, placeholder=0)
        transformed_one = self._deterministic_label_free(integrated, placeholder=1)
        missing = set(self.governed_features) - set(transformed_zero.columns)
        if missing:
            raise AdapterError(
                "ADAPTER_OUTPUT_CONTRACT_FAILED",
                f"Adapter did not construct governed predictors: {sorted(missing)}",
            )
        selected_zero = transformed_zero.loc[:, ["SK_ID_CURR", *self.governed_features]].copy()
        selected_one = transformed_one.loc[:, ["SK_ID_CURR", *self.governed_features]].copy()
        if not selected_zero.equals(selected_one):
            raise AdapterError(
                "UNSUPPORTED_TARGET_DEPENDENCY",
                "Predictor output depends on the temporary TARGET placeholder",
            )
        if pipeline is not None:
            validate_scoring_frame(selected_zero, pipeline)
        return AdapterBuildResult(
            scoring_frame=selected_zero,
            bureau_aggregate=bureau_aggregate,
            previous_aggregate=previous_aggregate,
            source_states=source_states,
            authoritative_use_permitted=authoritative,
        )


__all__ = ["AdapterBuildResult", "AdapterError", "MonitoringFeatureAdapter", "_integrate_label_free"]
