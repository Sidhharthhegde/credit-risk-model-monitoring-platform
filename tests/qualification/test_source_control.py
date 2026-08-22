from credit_risk_monitoring.qualification.source_control import (
    classify_source_state,
    qualification_scenarios,
)


def test_technically_required_source_stops_scoring() -> None:
    decision = classify_source_state(
        "missing",
        governed_input_constructible=False,
        total_policy_required_source_loss=False,
        partial_degradation=False,
        approved_fallback_exists=False,
    )
    assert decision.state == "SOURCE_TECHNICALLY_REQUIRED"
    assert not decision.technical_scoring_possible
    assert not decision.authoritative_operational_completion


def test_policy_required_source_allows_diagnostic_only() -> None:
    decision = classify_source_state(
        "outage",
        governed_input_constructible=True,
        total_policy_required_source_loss=True,
        partial_degradation=False,
        approved_fallback_exists=False,
    )
    assert decision.state == "SOURCE_UNAVAILABLE_NO_APPROVED_FALLBACK"
    assert decision.technical_scoring_possible
    assert not decision.authoritative_operational_completion


def test_qualification_state_order_is_frozen() -> None:
    assert [row["state"] for row in qualification_scenarios()] == [
        "SOURCE_TECHNICALLY_REQUIRED",
        "SOURCE_UNAVAILABLE_NO_APPROVED_FALLBACK",
        "SOURCE_DEGRADED",
        "SOURCE_AVAILABLE",
    ]

