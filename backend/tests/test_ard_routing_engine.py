"""
Phase 11 — Tests for ARDRoutingEngine
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from services.ard_routing_engine import ARDRoutingEngine


@pytest.fixture
def engine():
    return ARDRoutingEngine()


def _acceptability(
    status="ard_required",
    yield_pct=82,
    base_cost=90000,
    effective_cost=106200,
    requires_ard=True,
    risk_flags=None,
    mode="pharma",
):
    return {
        "industrial_status": status,
        "yield_percent":     yield_pct,
        "base_cost":         base_cost,
        "effective_cost":    effective_cost,
        "requires_ard":      requires_ard,
        "risk_flags":        risk_flags or [],
        "mode":              mode,
    }


def _route(
    constraint_penalty=10,
    equipment_rejected=False,
    purification_risk="medium",
):
    return {
        "constraint_penalty":  constraint_penalty,
        "equipment_rejected":  equipment_rejected,
        "purification_risk":   purification_risk,
    }


# ── Test 1: accepted route → ard_required=False ───────────────────────────────
def test_accepted_route_no_ard(engine):
    result = engine.route(
        _route(),
        _acceptability(status="accepted", yield_pct=99.5, requires_ard=False),
    )
    assert result["ard_required"] is False
    assert result["priority"] == "none"
    assert result["optimization_targets"] == []


# ── Test 2: exploratory_only → critical priority ──────────────────────────────
def test_exploratory_critical_priority(engine):
    result = engine.route(
        _route(),
        _acceptability(status="exploratory_only", yield_pct=5, requires_ard=True),
    )
    assert result["ard_required"] is True
    assert result["priority"] == "critical"


# ── Test 3: yield 30-90 → high priority ──────────────────────────────────────
def test_mid_yield_high_priority(engine):
    result = engine.route(
        _route(),
        _acceptability(status="ard_required", yield_pct=65, requires_ard=True),
    )
    assert result["priority"] in ("critical", "high")


# ── Test 4: pharma 90-99% yield → medium priority ────────────────────────────
def test_pharma_near_threshold_medium_priority(engine):
    result = engine.route(
        _route(),
        _acceptability(status="ard_required", yield_pct=95, requires_ard=True, mode="pharma"),
    )
    assert result["priority"] in ("medium", "high")


# ── Test 5: equipment rejected → critical priority ───────────────────────────
def test_equipment_rejected_critical(engine):
    result = engine.route(
        _route(equipment_rejected=True),
        _acceptability(status="rejected", yield_pct=85, requires_ard=True),
    )
    assert result["priority"] == "critical"
    assert "equipment" in result["optimization_targets"]


# ── Test 6: high purification risk → purification target ─────────────────────
def test_high_purification_target(engine):
    result = engine.route(
        _route(purification_risk="high"),
        _acceptability(status="ard_required", yield_pct=80, requires_ard=True),
    )
    targets = result["optimization_targets"]
    assert "purification" in targets or "selectivity" in targets


# ── Test 7: high constraint penalty → cost target ────────────────────────────
def test_high_constraint_penalty_target(engine):
    result = engine.route(
        _route(constraint_penalty=40),
        _acceptability(status="ard_required", yield_pct=80, requires_ard=True),
    )
    assert "cost" in result["optimization_targets"]


# ── Test 8: recommended_sequence is non-empty for ard_required ───────────────
def test_recommended_sequence_nonempty(engine):
    result = engine.route(
        _route(),
        _acceptability(status="ard_required", yield_pct=82, requires_ard=True),
    )
    assert len(result["recommended_sequence"]) > 0


# ── Test 9: model disagreement in risk_flags → data_collection target ─────────
def test_model_disagreement_target(engine):
    result = engine.route(
        _route(),
        _acceptability(
            status="ard_required", yield_pct=82, requires_ard=True,
            risk_flags=["High model disagreement: prediction spread 30%"],
        ),
    )
    assert "data_collection" in result["optimization_targets"]


# ── Test 10: safe on empty dicts ─────────────────────────────────────────────
def test_empty_dicts_no_crash(engine):
    result = engine.route({}, {})
    assert "ard_required" in result
