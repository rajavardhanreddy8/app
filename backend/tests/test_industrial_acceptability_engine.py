"""
Phase 11 — Tests for IndustrialAcceptabilityEngine
"""
import sys
import os

# Allow running as: PYTHONPATH=backend pytest ...
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from services.industrial_acceptability_engine import IndustrialAcceptabilityEngine


@pytest.fixture
def engine():
    return IndustrialAcceptabilityEngine()


# ── Helpers ──────────────────────────────────────────────────────────────────
def _route(yield_pct=82, base_cost=90000, constraint_penalty=10,
           equipment_rejected=False, equipment_penalty=5,
           purification_risk="medium", steps=None):
    return {
        "overall_yield_percent": yield_pct,
        "base_cost":             base_cost,
        "constraint_penalty":    constraint_penalty,
        "equipment_rejected":    equipment_rejected,
        "equipment_penalty":     equipment_penalty,
        "purification_risk":     purification_risk,
        "steps":                 steps or [],
    }


# ── Test 1: 82% yield in pharma mode → rejected or ard_required ─────────────
def test_82_pct_yield_pharma_mode(engine):
    result = engine.evaluate(_route(yield_pct=82, base_cost=90000), mode="pharma")

    assert result["industrial_status"] in ("rejected", "ard_required"), \
        f"Expected rejected/ard_required, got {result['industrial_status']}"
    assert result["requires_ard"] is True
    assert result["yield_loss_cost"] == pytest.approx(16200.0, rel=1e-3), \
        f"Expected yield_loss_cost=16200, got {result['yield_loss_cost']}"
    assert result["effective_cost"] == pytest.approx(106200.0, rel=1e-3), \
        f"Expected effective_cost=106200, got {result['effective_cost']}"
    assert any("yield" in r.lower() or "threshold" in r.lower()
               for r in result["rejection_reasons"]), \
        f"No yield threshold reason in {result['rejection_reasons']}"


# ── Test 2: 99.2% yield, low constraints → accepted ─────────────────────────
def test_992_pct_yield_accepted(engine):
    result = engine.evaluate(
        _route(yield_pct=99.2, base_cost=50000, constraint_penalty=5,
               equipment_rejected=False, purification_risk="low"),
        mode="pharma"
    )
    assert result["industrial_status"] == "accepted", \
        f"Expected accepted, got {result['industrial_status']}"
    assert result["pharma_status"] == "accepted"
    assert result["requires_ard"] is False


# ── Test 3: 5.2% yield → exploratory_only ───────────────────────────────────
def test_52_pct_yield_exploratory(engine):
    result = engine.evaluate(_route(yield_pct=5.2, base_cost=30000), mode="pharma")

    assert result["industrial_status"] == "exploratory_only", \
        f"Expected exploratory_only, got {result['industrial_status']}"
    assert result["requires_ard"] is True


# ── Test 4: equipment_rejected=True → rejected ───────────────────────────────
def test_equipment_rejected(engine):
    result = engine.evaluate(
        _route(yield_pct=92, base_cost=80000, equipment_rejected=True),
        mode="pharma"
    )
    assert result["industrial_status"] == "rejected", \
        f"Expected rejected, got {result['industrial_status']}"
    assert any("equipment" in r.lower() for r in result["rejection_reasons"]), \
        f"No equipment reason in {result['rejection_reasons']}"


# ── Test 5: constraint_penalty > 35 → high process risk flag ─────────────────
def test_high_constraint_penalty_flag(engine):
    result = engine.evaluate(
        _route(yield_pct=85, base_cost=70000, constraint_penalty=40),
        mode="pharma"
    )
    assert any("constraint" in f.lower() or "process" in f.lower()
               for f in result["risk_flags"]), \
        f"Expected process risk flag, got risk_flags={result['risk_flags']}"


# ── Test 6: high purification_risk → purification actions recommended ─────────
def test_high_purification_risk_recommendation(engine):
    result = engine.evaluate(
        _route(yield_pct=96, base_cost=60000, purification_risk="high"),
        mode="pharma"
    )
    all_text = " ".join(result["recommended_actions"] + result["risk_flags"]).lower()
    assert "purif" in all_text or "selectiv" in all_text, \
        f"Expected purification/selectivity action. Got: {result['recommended_actions']}"


# ── Test 7: bottleneck step detection ────────────────────────────────────────
def test_bottleneck_step_detection(engine):
    steps = [
        {"estimated_yield_percent": 98},
        {"estimated_yield_percent": 71},   # bottleneck
        {"estimated_yield_percent": 96},
    ]
    result = engine.evaluate(
        _route(yield_pct=65, base_cost=80000, steps=steps),
        mode="pharma"
    )
    actions_text = " ".join(result["recommended_actions"]).lower()
    flags_text   = " ".join(result["risk_flags"]).lower()
    assert "bottleneck" in actions_text or "bottleneck" in flags_text, \
        f"Expected bottleneck detection. Actions={result['recommended_actions']}, Flags={result['risk_flags']}"


# ── Test 8: model uncertainty / disagreement → risk flag ─────────────────────
def test_model_uncertainty_risk_flag(engine):
    steps = [
        {
            "estimated_yield_percent": 85,
            "yield_prediction": {
                "individual_predictions": {
                    "xgboost": 60.0,
                    "random_forest": 90.0,
                    "extra_trees": 85.0,
                }
            },
        }
    ]
    result = engine.evaluate(
        _route(yield_pct=78, base_cost=50000, steps=steps),
        mode="pharma"
    )
    flags_text = " ".join(result["risk_flags"]).lower()
    assert "disagree" in flags_text or "uncertainty" in flags_text or "spread" in flags_text, \
        f"Expected model disagreement flag. Got risk_flags={result['risk_flags']}"


# ── Test 9: acceptability score is numeric 0-100 ─────────────────────────────
def test_acceptability_score_range(engine):
    result = engine.evaluate(_route(yield_pct=82), mode="pharma")
    score = result["acceptability_score"]
    assert isinstance(score, int)
    assert 0 <= score <= 100, f"Score out of range: {score}"


# ── Test 10: safe on empty route dict ────────────────────────────────────────
def test_empty_route_no_crash(engine):
    result = engine.evaluate({}, mode="pharma")
    assert "industrial_status" in result
    assert "requires_ard" in result


# ── Test 11: ard_plan is present and structured ───────────────────────────────
def test_ard_plan_present(engine):
    result = engine.evaluate(_route(yield_pct=82), mode="pharma")
    assert "ard_plan" in result
    plan = result["ard_plan"]
    assert "ard_required" in plan
    assert "priority" in plan
    assert isinstance(plan["optimization_targets"], list)
    assert isinstance(plan["recommended_sequence"], list)
