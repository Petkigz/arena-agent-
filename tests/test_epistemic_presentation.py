"""Behavioral contracts for user-facing epistemic status."""

from app.cognition.epistemic_presentation import (
    LABEL_HIGH,
    LABEL_MODERATE,
    LABEL_TENTATIVE,
    LABEL_UNKNOWN,
    build_epistemic_presentation,
    presentation_for_cycle,
)


def test_unknown_cannot_be_upgraded_by_fluent_output():
    presentation = build_epistemic_presentation(
        evidence_state="unknown",
        confidence_score=0.99,
        evidence_basis=["the model produced a fluent answer"],
    )

    assert presentation.confidence_label == LABEL_UNKNOWN
    assert "unknown" in presentation.user_text().lower()


def test_direct_verified_observation_is_high_confidence():
    presentation = presentation_for_cycle(
        goal_verified=True,
        environment_observed=True,
        evidence_items=["fresh process observation matched the requested state"],
        source_count=1,
    )

    assert presentation.confidence_label == LABEL_HIGH
    assert presentation.evidence_state == "verified"
    assert presentation.freshness == "current cycle"
    assert "fresh process observation" in presentation.user_text()


def test_inference_is_not_presented_as_verified():
    presentation = presentation_for_cycle(
        goal_verified=True,
        environment_observed=False,
        evidence_items=["the answer was inferred from conversation context"],
    )

    assert presentation.confidence_label == LABEL_TENTATIVE
    assert presentation.evidence_state == "inferred"
    assert presentation.calibration_status == "evidence_derived"


def test_multiple_indirect_sources_are_moderate_not_high():
    presentation = build_epistemic_presentation(
        evidence_state="inferred",
        confidence_score=0.8,
        evidence_basis=["memory A", "memory B"],
        source_count=2,
    )

    assert presentation.confidence_label == LABEL_MODERATE
    assert presentation.confidence_label != LABEL_HIGH


def test_append_is_idempotent_and_explanation_excludes_private_reasoning():
    presentation = presentation_for_cycle(
        goal_verified=False,
        unknown=True,
        evidence_items=["no authoritative observation was available"],
    )
    first = presentation.append_to("I cannot verify that.")
    second = presentation.append_to(first)

    assert first == second
    explanation = presentation.explanation()
    assert explanation["evidence_basis"] == ["no authoritative observation was available"]
    assert all("chain-of-thought" in item or "Private" in item for item in explanation["unknowns"])
