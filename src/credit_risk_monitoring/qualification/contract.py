"""Independent Phase 1 qualification of DF-01's scoring interface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype


class ScoringContractError(ValueError):
    """Raised when a scoring frame violates the frozen DF-01 interface."""


@dataclass(frozen=True)
class FeatureGroups:
    raw: tuple[str, ...]
    numeric: tuple[str, ...]
    categorical: tuple[str, ...]
    binary: tuple[str, ...]
    encoded: tuple[str, ...]


def feature_groups(pipeline: Any) -> FeatureGroups:
    if not hasattr(pipeline, "named_steps") or list(pipeline.named_steps) != [
        "preprocessor",
        "model",
    ]:
        raise ScoringContractError("Frozen scorer must be Pipeline(preprocessor, model)")
    preprocessor = pipeline.named_steps["preprocessor"]
    if not hasattr(preprocessor, "feature_names_in_"):
        raise ScoringContractError("Embedded preprocessor lacks fitted feature names")
    routed = {
        str(name): tuple(str(value) for value in columns)
        for name, _, columns in preprocessor.transformers_
        if str(name) in {"numeric", "categorical", "binary"}
    }
    groups = FeatureGroups(
        raw=tuple(str(value) for value in preprocessor.feature_names_in_),
        numeric=routed.get("numeric", ()),
        categorical=routed.get("categorical", ()),
        binary=routed.get("binary", ()),
        encoded=tuple(str(value) for value in preprocessor.get_feature_names_out()),
    )
    if len(groups.raw) != 176 or len(set(groups.raw)) != 176:
        raise ScoringContractError("Frozen raw feature identity is not 176 unique predictors")
    if len(groups.encoded) != 306 or len(set(groups.encoded)) != 306:
        raise ScoringContractError("Frozen encoded identity is not 306 unique predictors")
    routed_union = set(groups.numeric) | set(groups.categorical) | set(groups.binary)
    if routed_union != set(groups.raw):
        raise ScoringContractError("Frozen transformer routing does not reconcile")
    if any(
        left & right
        for left, right in (
            (set(groups.numeric), set(groups.categorical)),
            (set(groups.numeric), set(groups.binary)),
            (set(groups.categorical), set(groups.binary)),
        )
    ):
        raise ScoringContractError("Frozen transformer groups overlap")
    return groups


def validate_scoring_frame(frame: pd.DataFrame, pipeline: Any) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise ScoringContractError("Scoring input must be a non-empty DataFrame")
    if frame.columns.duplicated().any():
        raise ScoringContractError("Scoring input contains duplicate columns")
    groups = feature_groups(pipeline)
    required = {"SK_ID_CURR", *groups.raw}
    missing = required - set(frame.columns)
    unexpected = set(frame.columns) - required
    if missing:
        raise ScoringContractError(f"Missing required input columns: {sorted(missing)}")
    if unexpected:
        raise ScoringContractError(f"Unexpected input columns: {sorted(unexpected)}")
    if frame["SK_ID_CURR"].isna().any() or not frame["SK_ID_CURR"].is_unique:
        raise ScoringContractError("SK_ID_CURR must be complete and unique")
    for feature in groups.numeric:
        series = frame[feature]
        if not is_numeric_dtype(series.dtype):
            raise ScoringContractError(f"Numeric feature {feature} has incompatible dtype")
        values = series.to_numpy(dtype=np.float64, na_value=np.nan)
        if np.isinf(values).any():
            raise ScoringContractError(f"Numeric feature {feature} contains infinity")
    for feature in groups.categorical:
        if any(not isinstance(value, str) for value in frame[feature].dropna().tolist()):
            raise ScoringContractError(
                f"Categorical feature {feature} contains a non-string value"
            )
    for feature in groups.binary:
        series = frame[feature]
        if not is_numeric_dtype(series.dtype) or series.isna().any():
            raise ScoringContractError(f"Binary feature {feature} must be complete numeric 0/1")
        values = set(series.astype(float).unique().tolist())
        if not values.issubset({0.0, 1.0}):
            raise ScoringContractError(f"Binary feature {feature} contains values outside 0/1")
    return frame.loc[:, list(groups.raw)].copy()


def _case(name: str, expected: str, operation: Any) -> dict[str, Any]:
    try:
        result = operation()
    except (ScoringContractError, ValueError, TypeError) as exc:
        actual = "REJECT"
        detail = f"{type(exc).__name__}: {exc}"
    else:
        actual = "ACCEPT"
        detail = f"accepted_shape={result.shape}"
    return {
        "case": name,
        "expected": expected,
        "actual": actual,
        "passed": expected == actual,
        "detail": detail,
    }


def qualify_contract_cases(fixture: pd.DataFrame, pipeline: Any) -> list[dict[str, Any]]:
    groups = feature_groups(pipeline)
    base = fixture.drop(columns=["SYNTHETIC_FIXTURE_ROW"]).copy()
    rows: list[dict[str, Any]] = []
    rows.append(_case("canonical governed fixture", "ACCEPT", lambda: validate_scoring_frame(base, pipeline)))
    rows.append(_case("valid numeric missingness", "ACCEPT", lambda: validate_scoring_frame(base.iloc[[1]], pipeline)))
    rows.append(_case("valid categorical missingness", "ACCEPT", lambda: validate_scoring_frame(base.iloc[[2]], pipeline)))
    rows.append(_case("valid unseen categorical value", "ACCEPT", lambda: validate_scoring_frame(base.iloc[[3]], pipeline)))
    reordered = base.loc[:, ["SK_ID_CURR", *reversed(groups.raw)]]
    rows.append(_case("reordered columns", "ACCEPT", lambda: validate_scoring_frame(reordered, pipeline)))
    rows.append(_case("historical numeric range is not a hard gate", "ACCEPT", lambda: validate_scoring_frame(base.assign(**{groups.numeric[0]: 1e30}), pipeline)))
    rows.append(_case("missing predictor", "REJECT", lambda: validate_scoring_frame(base.drop(columns=[groups.raw[0]]), pipeline)))
    rows.append(_case("unexpected predictor", "REJECT", lambda: validate_scoring_frame(base.assign(__EXTRA__=1), pipeline)))
    duplicate_columns = pd.concat([base, base[[groups.raw[0]]]], axis=1)
    rows.append(_case("duplicate predictor", "REJECT", lambda: validate_scoring_frame(duplicate_columns, pipeline)))
    rows.append(_case("numeric infinity", "REJECT", lambda: validate_scoring_frame(base.assign(**{groups.numeric[0]: np.inf}), pipeline)))
    rows.append(_case("binary value outside 0/1", "REJECT", lambda: validate_scoring_frame(base.assign(**{groups.binary[0]: 2}), pipeline)))
    rows.append(_case("non-string categorical", "REJECT", lambda: validate_scoring_frame(base.assign(**{groups.categorical[0]: 7}), pipeline)))
    duplicate_key = base.iloc[:2].copy()
    duplicate_key.iloc[1, duplicate_key.columns.get_loc("SK_ID_CURR")] = duplicate_key.iloc[0]["SK_ID_CURR"]
    rows.append(_case("duplicate applicant key", "REJECT", lambda: validate_scoring_frame(duplicate_key, pipeline)))
    missing_key = base.iloc[[0]].copy()
    missing_key["SK_ID_CURR"] = missing_key["SK_ID_CURR"].astype("Int64")
    missing_key.loc[:, "SK_ID_CURR"] = pd.NA
    rows.append(_case("missing applicant key", "REJECT", lambda: validate_scoring_frame(missing_key, pipeline)))
    return rows
