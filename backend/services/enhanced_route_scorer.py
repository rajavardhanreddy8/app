import logging
from typing import Any, Dict, List, Optional

import numpy as np

from models import get_yield_predictor
from models.chemistry import ReactionStep, SynthesisRoute
from services.cost_database import CostDatabase

logger = logging.getLogger(__name__)


MODE_WEIGHTS = {
    "yield": {
        "yield": 0.35, "cost": 0.10, "steps": 0.05, "time": 0.05,
        "pmi": 0.10, "atom_economy": 0.10, "convergence": 0.05,
        "catalyst_burden": 0.10, "impurity_risk": 0.10,
    },
    "cost": {
        "yield": 0.15, "cost": 0.30, "steps": 0.05, "time": 0.05,
        "pmi": 0.15, "atom_economy": 0.05, "convergence": 0.10,
        "catalyst_burden": 0.10, "impurity_risk": 0.05,
    },
    "green": {
        "yield": 0.10, "cost": 0.10, "steps": 0.05, "time": 0.05,
        "pmi": 0.30, "atom_economy": 0.20, "convergence": 0.10,
        "catalyst_burden": 0.05, "impurity_risk": 0.05,
    },
    "regulatory": {
        "yield": 0.15, "cost": 0.10, "steps": 0.10, "time": 0.05,
        "pmi": 0.05, "atom_economy": 0.05, "convergence": 0.05,
        "catalyst_burden": 0.15, "impurity_risk": 0.30,
    },
    "balanced": {
        "yield": 0.20, "cost": 0.15, "steps": 0.10, "time": 0.05,
        "pmi": 0.12, "atom_economy": 0.08, "convergence": 0.10,
        "catalyst_burden": 0.10, "impurity_risk": 0.10,
    },
}


class EnhancedRouteScorer:
    """Nine-dimension route scorer for process chemistry route selection."""

    def __init__(self, pharma_mode: bool = False):
        self.yield_predictor = get_yield_predictor()
        self.cost_database = CostDatabase()
        self.pharma_mode = pharma_mode
        self.pharma_min_yield = 99.0
        self.ml_available = getattr(self.yield_predictor, "model", None) is not None
        if not self.ml_available:
            try:
                self.yield_predictor.load_model()
                self.ml_available = getattr(self.yield_predictor, "model", None) is not None
            except Exception:
                self.ml_available = False
        if not self.ml_available:
            logger.warning("ML yield predictor not available, using heuristics")

    def predict_step_yield(self, step: ReactionStep) -> float:
        if self.ml_available:
            try:
                reaction_dict = {
                    "reactants": [r.smiles for r in step.reactants],
                    "products": [step.product.smiles],
                    "reaction_type": step.reaction_type,
                    "temperature_celsius": step.conditions.temperature_celsius if step.conditions else 25,
                    "catalyst": step.conditions.catalyst if step.conditions else None,
                    "solvent": step.conditions.solvent if step.conditions else None,
                }
                predicted_yield = self.yield_predictor.predict(reaction_dict)
                if predicted_yield is not None:
                    return float(predicted_yield)
            except Exception as exc:
                logger.debug(f"ML prediction failed: {exc}, using heuristic")
        return float(step.estimated_yield_percent)

    def calculate_step_cost(self, step: ReactionStep, target_mass_mg: float = 100.0) -> float:
        try:
            costs = self.cost_database.calculate_reaction_cost(
                reactants=[r.smiles for r in step.reactants],
                reagents=[],
                catalyst=step.conditions.catalyst if step.conditions else None,
                solvent=step.conditions.solvent if step.conditions else None,
                target_mass_mg=target_mass_mg,
            )
            return float(costs["total_cost"])
        except Exception as exc:
            logger.debug(f"Cost calculation failed: {exc}")
            return float(step.estimated_cost_usd or 50.0)

    def score_route_unified(
        self,
        route: Dict[str, Any],
        optimize_for: str = "balanced",
        stage: str = "phase_2",
        weights_override: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        route_dict = self._route_to_dict(route)
        optimize_for = optimize_for if optimize_for in MODE_WEIGHTS else "balanced"
        weights = dict(MODE_WEIGHTS[optimize_for])
        if weights_override:
            weights.update(weights_override)

        scores = self._dimension_raw_scores(route_dict)
        weighted = {
            dim: scores[dim] * weights.get(dim, 0.0)
            for dim in MODE_WEIGHTS["balanced"]
        }
        raw_score = sum(weighted.values())
        final_score = round(raw_score * 100.0, 2)
        dimension_scores = {
            dim: {
                "raw": round(scores[dim], 3),
                "weighted": round(weighted[dim], 3),
                "contribution_pct": round((weighted[dim] / raw_score) * 100) if raw_score > 0 else 0,
            }
            for dim in weighted
        }
        return {
            "score": final_score,
            "optimize_for": optimize_for,
            "stage": stage,
            "weights": weights,
            "dimension_scores": dimension_scores,
            "improvement_targets": self._improvement_targets(route_dict),
        }

    def score_route(
        self,
        route: SynthesisRoute,
        optimize_for: str = "balanced",
        weights: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        route_dict = self._route_to_dict(route)
        overall_yield = route_dict.get("overall_yield", 0.0)
        if self.pharma_mode and overall_yield < self.pharma_min_yield:
            return {
                "score": float("-inf"),
                "metrics": self._legacy_metrics(route_dict),
                "weights": {},
                "optimization_goal": "pharma",
                "rejected": True,
                "rejection_reason": f"Yield {overall_yield:.2f}% below pharma minimum {self.pharma_min_yield}%",
            }

        result = self.score_route_unified(route_dict, optimize_for=optimize_for, weights_override=weights)
        result.update({
            "metrics": self._legacy_metrics(route_dict),
            "optimization_goal": optimize_for,
            "rejected": False,
        })
        return result

    def compare_routes(self, routes: List[SynthesisRoute], optimize_for: str = "balanced") -> List[Dict[str, Any]]:
        scored_routes = []
        for route in routes:
            try:
                result = self.score_route(route, optimize_for)
                if result.get("rejected"):
                    continue
                scored_routes.append({
                    "route": route,
                    "score": result["score"],
                    "metrics": result["metrics"],
                    "dimension_scores": result.get("dimension_scores", {}),
                    "improvement_targets": result.get("improvement_targets", []),
                })
            except Exception as exc:
                logger.error(f"Failed to score route: {exc}")
                if not self.pharma_mode:
                    scored_routes.append({"route": route, "score": getattr(route, "score", 0.0) or 0.0, "metrics": {}})

        scored_routes.sort(key=lambda item: item["score"], reverse=True)
        seen = set()
        unique_routes = []
        for entry in scored_routes:
            metrics = entry.get("metrics", {})
            key = (
                round(entry.get("score", 0), 2),
                round(metrics.get("overall_yield", 0), 1),
                round(metrics.get("total_cost", 0), 0),
            )
            if key not in seen:
                seen.add(key)
                unique_routes.append(entry)
        return unique_routes

    def _dimension_raw_scores(self, route: Dict[str, Any]) -> Dict[str, float]:
        overall_yield = self._num(route.get("overall_yield", route.get("overall_yield_percent", 0.0)))
        total_cost = self._num(route.get("total_cost_usd", route.get("total_cost", 0.0)))
        num_steps = int(self._num(route.get("num_steps", len(route.get("steps", [])))))
        total_hours = self._total_hours(route)
        green = route.get("green_metrics") or {}
        pmi = self._num(green.get("pmi", 50.0))
        ae = self._num(green.get("atom_economy_percent", 50.0))
        convergence = max(0.0, min(1.0, self._num(green.get("convergence_score", 0.0))))

        pd_steps = sum(
            1 for step in route.get("steps", [])
            if "Pd" in self._step_catalyst(step)
            and "/C" not in self._step_catalyst(step)
            and "Al2O3" not in self._step_catalyst(step)
        )
        bio_steps = sum(
            1 for step in route.get("steps", [])
            if any(token in self._step_catalyst(step).lower() for token in ["lipase", "transaminase", "kred", "enzyme"])
        )
        impurity = route.get("impurity_analysis") or {}
        risk = str(impurity.get("overall_impurity_risk", "medium")).lower()
        risk_map = {"low": 1.0, "medium": 0.6, "high": 0.2}
        gti_penalty = -0.3 if impurity.get("ich_m7_assessment_required") else 0.0

        return {
            "yield": max(0.0, min(1.0, overall_yield / 100.0)),
            "cost": max(0.0, 1.0 - (total_cost / 100000.0)),
            "steps": max(0.0, 1.0 - (num_steps / 10.0)),
            "time": max(0.0, 1.0 - (total_hours / 48.0)),
            "pmi": self._pmi_score(pmi),
            "atom_economy": max(0.0, min(1.0, ae / 100.0)),
            "convergence": convergence,
            "catalyst_burden": min(1.0, max(0.0, 1.0 - (pd_steps * 0.2)) + (bio_steps * 0.1)),
            "impurity_risk": max(0.0, min(1.0, risk_map.get(risk, 0.5) + gti_penalty)),
        }

    def _route_to_dict(self, route: Any) -> Dict[str, Any]:
        if isinstance(route, dict):
            result = dict(route)
            result["overall_yield"] = self._num(result.get("overall_yield", result.get("overall_yield_percent", 0.0)))
            result["total_cost_usd"] = self._num(result.get("total_cost_usd", result.get("total_cost", 0.0)))
            result["num_steps"] = int(self._num(result.get("num_steps", len(result.get("steps", [])))))
            return result

        steps = getattr(route, "steps", []) or []
        step_yields = [self.predict_step_yield(step) for step in steps]
        step_costs = [self.calculate_step_cost(step) for step in steps]
        total_time = sum(
            float(step.conditions.time_hours or 0.0)
            for step in steps
            if getattr(step, "conditions", None)
        )
        overall_yield = float(np.prod([value / 100.0 for value in step_yields]) * 100.0) if step_yields else 0.0
        return {
            "overall_yield": overall_yield,
            "overall_yield_percent": overall_yield,
            "total_cost_usd": float(sum(step_costs)),
            "total_cost": float(sum(step_costs)),
            "num_steps": len(steps),
            "total_time_hours": total_time,
            "steps": [self._step_to_dict(step) for step in steps],
            "green_metrics": getattr(route, "green_metrics", {}) or {},
            "impurity_analysis": getattr(route, "impurity_analysis", {}) or {},
        }

    def _legacy_metrics(self, route: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "overall_yield": route.get("overall_yield", route.get("overall_yield_percent", 0.0)),
            "total_cost": route.get("total_cost_usd", route.get("total_cost", 0.0)),
            "num_steps": route.get("num_steps", len(route.get("steps", []))),
            "total_time_hours": self._total_hours(route),
            "complexity": max(0.0, 100.0 - (self._dimension_raw_scores(route)["steps"] * 100.0)),
            "feasibility": round(self._dimension_raw_scores(route)["yield"] * 100.0, 2),
        }

    def _step_to_dict(self, step: ReactionStep) -> Dict[str, Any]:
        return {
            "reaction_type": step.reaction_type,
            "estimated_yield_percent": step.estimated_yield_percent,
            "estimated_cost_usd": step.estimated_cost_usd,
            "difficulty": step.difficulty,
            "conditions": {
                "catalyst": step.conditions.catalyst if step.conditions else None,
                "solvent": step.conditions.solvent if step.conditions else None,
                "temperature_celsius": step.conditions.temperature_celsius if step.conditions else None,
                "time_hours": step.conditions.time_hours if step.conditions else None,
            },
        }

    def _total_hours(self, route: Dict[str, Any]) -> float:
        if route.get("total_time_hours") is not None:
            return self._num(route.get("total_time_hours"))
        total = 0.0
        for step in route.get("steps", []):
            conditions = step.get("conditions", {}) if isinstance(step, dict) else {}
            total += self._num(conditions.get("time_hours", step.get("time_hours", 0.0) if isinstance(step, dict) else 0.0))
        return total

    def _step_catalyst(self, step: Dict[str, Any]) -> str:
        if not isinstance(step, dict):
            return ""
        conditions = step.get("conditions") or {}
        if isinstance(conditions, dict):
            return str(conditions.get("catalyst", step.get("catalyst", "")) or "")
        return str(step.get("catalyst", "") or "")

    def _pmi_score(self, pmi: float) -> float:
        if pmi < 10:
            return 1.0
        if pmi < 25:
            return 0.7
        if pmi < 50:
            return 0.4
        return 0.1

    def _improvement_targets(self, route: Dict[str, Any]) -> List[str]:
        targets = []
        green = route.get("green_metrics") or {}
        pmi = self._num(green.get("pmi", 50))
        ae = self._num(green.get("atom_economy_percent", 50))
        if pmi >= 25:
            targets.append(f"Reduce PMI from {pmi:g} to <25 by solvent recovery or telescoping")
        if ae < 50:
            targets.append(f"Improve atom economy from {ae:g}% by replacing stoichiometric reagents")
        for index, step in enumerate(route.get("steps", []), start=1):
            catalyst = self._step_catalyst(step)
            if "Pd" in catalyst and "/C" not in catalyst and "Al2O3" not in catalyst:
                targets.append(f"Replace homogeneous Pd in Step {index} with a heterogeneous or earth-abundant option")
                break
        impurity = route.get("impurity_analysis") or {}
        if impurity.get("ich_m7_assessment_required"):
            targets.append("Add purge controls for ICH M7 GTI risk before route filing")
        if route.get("num_steps", len(route.get("steps", []))) > 6:
            targets.append("Reduce step count or telescope compatible consecutive steps")
        return targets

    def _get_optimization_weights(self, optimize_for: str) -> Dict[str, float]:
        return dict(MODE_WEIGHTS.get(optimize_for, MODE_WEIGHTS["balanced"]))

    def _get_weights(self, optimize_for: str) -> Dict[str, float]:
        return self._get_optimization_weights(optimize_for)

    @staticmethod
    def _num(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
