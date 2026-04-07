"""
Level 4 — Route Quality Tests
Verify route scoring, complexity, and feasibility calculations.
"""
import sys
import os
from pathlib import Path

# Ensure backend is on sys.path BEFORE importing backend modules
BACKEND_DIR = Path(__file__).parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Set env vars before any backend imports
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_database")

import pytest
from models.chemistry import (
    SynthesisRoute,
    ReactionStep,
    MolecularStructure,
    ReactionCondition,
)


# ── Helpers ───────────────────────────────────────────────────────

def _make_step(
    reaction_type="esterification",
    yield_pct=75.0,
    cost=10.0,
    difficulty="moderate",
    temp=80.0,
    time_h=2.0,
    catalyst=None,
    solvent="THF",
):
    return ReactionStep(
        reactants=[
            MolecularStructure(smiles="CCO"),
            MolecularStructure(smiles="CC(=O)O"),
        ],
        product=MolecularStructure(smiles="CCOC(C)=O"),
        reaction_type=reaction_type,
        estimated_yield_percent=yield_pct,
        estimated_cost_usd=cost,
        difficulty=difficulty,
        conditions=ReactionCondition(
            temperature_celsius=temp,
            time_hours=time_h,
            catalyst=catalyst,
            solvent=solvent,
        ),
    )


def _make_route(steps=None, num_steps=3):
    if steps is None:
        steps = [_make_step() for _ in range(num_steps)]
    return SynthesisRoute(
        target_molecule=MolecularStructure(smiles="CCOC(C)=O"),
        starting_materials=[MolecularStructure(smiles="CCO")],
        steps=steps,
        overall_yield_percent=50.0,
        total_cost_usd=30.0,
        total_time_hours=6.0,
        score=60.0,
    )


# ═══════════════════════════════════════════════════════════════════
#  Optimization Weights
# ═══════════════════════════════════════════════════════════════════

class TestOptimizationWeights:

    @pytest.mark.parametrize("mode", ["balanced", "yield", "cost", "time"])
    def test_weights_sum_to_one(self, route_scorer, mode):
        weights = route_scorer._get_optimization_weights(mode)
        assert abs(sum(weights.values()) - 1.0) < 0.001, f"Weights for '{mode}' don't sum to 1.0"

    def test_yield_mode_prioritizes_yield(self, route_scorer):
        w = route_scorer._get_optimization_weights("yield")
        assert w["yield"] >= 0.5

    def test_cost_mode_prioritizes_cost(self, route_scorer):
        w = route_scorer._get_optimization_weights("cost")
        assert w["cost"] >= 0.3

    def test_time_mode_prioritizes_steps(self, route_scorer):
        w = route_scorer._get_optimization_weights("time")
        assert w["steps"] >= 0.3


# ═══════════════════════════════════════════════════════════════════
#  Scoring
# ═══════════════════════════════════════════════════════════════════

class TestRouteScoring:

    def test_score_in_valid_range(self, route_scorer):
        route = _make_route(num_steps=2)
        result = route_scorer.score_route(route, optimize_for="balanced")
        assert 0 <= result["score"] <= 100

    def test_score_returns_metrics(self, route_scorer):
        route = _make_route(num_steps=2)
        result = route_scorer.score_route(route, optimize_for="balanced")
        metrics = result["metrics"]
        assert "overall_yield" in metrics
        assert "total_cost" in metrics
        assert "num_steps" in metrics
        assert "complexity" in metrics
        assert "feasibility" in metrics

    def test_high_yield_route_scores_well_in_yield_mode(self, route_scorer):
        high_yield_steps = [_make_step(yield_pct=95.0) for _ in range(2)]
        low_yield_steps = [_make_step(yield_pct=30.0) for _ in range(2)]

        high_route = _make_route(steps=high_yield_steps)
        low_route = _make_route(steps=low_yield_steps)

        high_score = route_scorer.score_route(high_route, optimize_for="yield")["score"]
        low_score = route_scorer.score_route(low_route, optimize_for="yield")["score"]

        assert high_score > low_score, "High-yield route should score higher in yield mode"


# ═══════════════════════════════════════════════════════════════════
#  Complexity & Feasibility
# ═══════════════════════════════════════════════════════════════════

class TestComplexityAndFeasibility:

    def test_complexity_increases_with_steps(self, route_scorer):
        short = _make_route(num_steps=1)
        long = _make_route(num_steps=5)

        c_short = route_scorer._calculate_complexity(short)
        c_long = route_scorer._calculate_complexity(long)

        assert c_long > c_short, "More steps should increase complexity"

    def test_difficult_steps_increase_complexity(self, route_scorer):
        easy_steps = [_make_step(difficulty="easy") for _ in range(3)]
        hard_steps = [_make_step(difficulty="difficult") for _ in range(3)]

        easy_route = _make_route(steps=easy_steps)
        hard_route = _make_route(steps=hard_steps)

        c_easy = route_scorer._calculate_complexity(easy_route)
        c_hard = route_scorer._calculate_complexity(hard_route)

        assert c_hard > c_easy, "Difficult steps should increase complexity"

    def test_feasibility_decreases_with_difficulty(self, route_scorer):
        easy_steps = [_make_step(difficulty="easy", yield_pct=90) for _ in range(2)]
        hard_steps = [_make_step(difficulty="high", yield_pct=40) for _ in range(6)]

        easy_route = _make_route(steps=easy_steps)
        hard_route = _make_route(steps=hard_steps)

        f_easy = route_scorer._calculate_feasibility(easy_route, [90, 90])
        f_hard = route_scorer._calculate_feasibility(hard_route, [40] * 6)

        assert f_easy > f_hard, "Hard routes should have lower feasibility"

    def test_complexity_capped_at_100(self, route_scorer):
        many_hard = [_make_step(difficulty="difficult", temp=150, catalyst="Pd(PPh3)4") for _ in range(8)]
        route = _make_route(steps=many_hard)
        c = route_scorer._calculate_complexity(route)
        assert c <= 100

    def test_feasibility_never_negative(self, route_scorer):
        hard = [_make_step(difficulty="high", yield_pct=10) for _ in range(10)]
        route = _make_route(steps=hard)
        f = route_scorer._calculate_feasibility(route, [10] * 10)
        assert f >= 0
