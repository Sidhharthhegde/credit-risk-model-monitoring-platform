"""Qualification-only source-control state classification.

This module does not calculate model performance under source loss.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class SourceControlDecision:
    scenario: str
    state: str
    technical_scoring_possible: bool
    authoritative_operational_completion: bool
    control_finding_required: bool
    cnd_02_status: str = "OPEN"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def classify_source_state(
    scenario: str,
    *,
    governed_input_constructible: bool,
    total_policy_required_source_loss: bool,
    partial_degradation: bool,
    approved_fallback_exists: bool,
) -> SourceControlDecision:
    if not governed_input_constructible:
        return SourceControlDecision(
            scenario,
            "SOURCE_TECHNICALLY_REQUIRED",
            False,
            False,
            True,
        )
    if total_policy_required_source_loss and not approved_fallback_exists:
        return SourceControlDecision(
            scenario,
            "SOURCE_UNAVAILABLE_NO_APPROVED_FALLBACK",
            True,
            False,
            True,
        )
    if partial_degradation:
        return SourceControlDecision(
            scenario,
            "SOURCE_DEGRADED",
            True,
            True,
            True,
        )
    return SourceControlDecision(scenario, "SOURCE_AVAILABLE", True, True, False)


def qualification_scenarios() -> list[dict[str, object]]:
    cases = [
        classify_source_state(
            "technically required source missing",
            governed_input_constructible=False,
            total_policy_required_source_loss=False,
            partial_degradation=False,
            approved_fallback_exists=False,
        ),
        classify_source_state(
            "policy-required source unavailable without fallback",
            governed_input_constructible=True,
            total_policy_required_source_loss=True,
            partial_degradation=False,
            approved_fallback_exists=False,
        ),
        classify_source_state(
            "partial source degradation",
            governed_input_constructible=True,
            total_policy_required_source_loss=False,
            partial_degradation=True,
            approved_fallback_exists=False,
        ),
        classify_source_state(
            "all governed sources available",
            governed_input_constructible=True,
            total_policy_required_source_loss=False,
            partial_degradation=False,
            approved_fallback_exists=False,
        ),
    ]
    return [case.to_dict() for case in cases]

