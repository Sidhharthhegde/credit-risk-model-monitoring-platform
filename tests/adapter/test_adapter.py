from types import SimpleNamespace

import pandas as pd
import pytest

from credit_risk_monitoring.adapter.adapter import (
    AdapterError,
    MonitoringFeatureAdapter,
    _integrate_label_free,
)


def make_adapter() -> MonitoringFeatureAdapter:
    fixed = tuple(f"F{i:03d}" for i in range(172))
    governed = (
        *fixed,
        "BUREAU_ACCOUNT_COUNT",
        "PREV_APPLICATION_COUNT",
        "HAS_BUREAU_HISTORY",
        "HAS_PREV_APP_HISTORY",
    )

    def bureau(raw: pd.DataFrame) -> pd.DataFrame:
        return raw.groupby("SK_ID_CURR", as_index=False).agg(BUREAU_ACCOUNT_COUNT=("SK_ID_BUREAU", "count"))

    def previous(raw: pd.DataFrame) -> pd.DataFrame:
        return raw.groupby("SK_ID_CURR", as_index=False).agg(PREV_APPLICATION_COUNT=("SK_ID_PREV", "count"))

    def deterministic(frame: pd.DataFrame) -> pd.DataFrame:
        result = frame.copy()
        result["HAS_PREV_APP_HISTORY"] = result.pop("HAS_PREV_APPLICATION_HISTORY")
        return result

    functions = SimpleNamespace(
        build_bureau_features=bureau,
        build_previous_application_features=previous,
        apply_deterministic_transformations=deterministic,
    )
    return MonitoringFeatureAdapter(
        functions,
        governed,
        {"SK_ID_CURR", *fixed},
        {"SK_ID_CURR", "SK_ID_BUREAU"},
        {"SK_ID_CURR", "SK_ID_PREV"},
        ("BUREAU_ACCOUNT_COUNT",),
        ("PREV_APPLICATION_COUNT",),
    )


def frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    application = pd.DataFrame(
        {"SK_ID_CURR": [1, 2], **{f"F{i:03d}": [i, i + 1] for i in range(172)}}
    )
    bureau = pd.DataFrame({"SK_ID_CURR": [1, 1], "SK_ID_BUREAU": [10, 11]})
    previous = pd.DataFrame({"SK_ID_CURR": [2], "SK_ID_PREV": [20]})
    return application, bureau, previous


def test_adapter_is_label_free_and_preserves_anchor() -> None:
    application, bureau, previous = frames()
    result = make_adapter().build(application, bureau, previous)
    assert "TARGET" not in result.scoring_frame
    assert result.scoring_frame["SK_ID_CURR"].tolist() == [1, 2]
    assert result.scoring_frame.shape == (2, 177)
    assert result.authoritative_use_permitted is True


def test_missing_policy_source_can_only_produce_non_authoritative_diagnostic() -> None:
    application, _, previous = frames()
    adapter = make_adapter()
    with pytest.raises(AdapterError, match="Bureau source is unavailable") as captured:
        adapter.build(application, None, previous)
    assert captured.value.reason_code == "SOURCE_UNAVAILABLE_NO_APPROVED_FALLBACK"
    result = adapter.build(application, None, previous, diagnostic_source_loss=True)
    assert result.authoritative_use_permitted is False
    assert result.source_states["bureau"] == "SOURCE_UNAVAILABLE_NO_APPROVED_FALLBACK"


def test_duplicate_anchor_is_rejected() -> None:
    application, bureau, previous = frames()
    duplicate = pd.concat([application, application.iloc[[0]]], ignore_index=True)
    with pytest.raises(AdapterError) as captured:
        make_adapter().build(duplicate, bureau, previous)
    assert captured.value.reason_code == "ADAPTER_GRAIN_VIOLATION"


def test_duplicate_aggregate_is_rejected_before_join() -> None:
    application, _, _ = frames()
    bureau_aggregate = pd.DataFrame(
        {"SK_ID_CURR": [1, 1], "BUREAU_ACCOUNT_COUNT": [1, 2]}
    )
    previous_aggregate = pd.DataFrame(
        {"SK_ID_CURR": [2], "PREV_APPLICATION_COUNT": [1]}
    )
    with pytest.raises(AdapterError) as captured:
        _integrate_label_free(application, bureau_aggregate, previous_aggregate)
    assert captured.value.reason_code == "ADAPTER_GRAIN_VIOLATION"
