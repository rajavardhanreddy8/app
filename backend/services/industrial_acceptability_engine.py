"""
Phase 11: Industrial Acceptability Engine

Evaluates fully-enriched synthesis routes and classifies them as:
  - accepted
  - ard_required
  - rejected
  - exploratory_only

Standalone service — importable without touching existing pipeline.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Default thresholds ──────────────────────────────────────────────────────
_PHARMA_MIN_ROUTE_YIELD = 99.0   # % — total route yield for pharma acceptance
_PHARMA_MIN_STEP_YIELD  = 95.0   # % — per-step threshold (recommended)
_EXPLORATORY_YIELD_MAX  = 30.0   # % — below this → exploratory only
_MAX_CONSTRAINT_PENALTY = 35.0
_MAX_EQUIPMENT_PENALTY  = 25.0


class IndustrialAcceptabilityEngine:
    """
    Classifies a synthesis route for industrial production readiness.

    Usage::
        engine = IndustrialAcceptabilityEngine()
        result = engine.evaluate(route_dict, mode="pharma")
    """

    # ── Public API ──────────────────────────────────────────────────────────
    def evaluate(self, route: Dict[str, Any], mode: str = "pharma") -> Dict[str, Any]:
        """
        Evaluate a fully-enriched route dict.

        Args:
            route: Route dictionary with yield, cost, constraint, equipment,
                   purification, step, and ML-prediction fields.
            mode:  Evaluation mode — one of 'pharma', 'cost', 'balanced',
                   'green', 'speed'.

        Returns:
            Full acceptability result dict (see module docstring).
        """
        try:
            return self._evaluate_safe(route, mode)
        except Exception as exc:
            logger.warning("industrial_acceptability_engine_error: %s", exc, exc_info=True)
            return self._fallback_result(route, mode, str(exc))

    # ── Core evaluation ─────────────────────────────────────────────────────
    def _evaluate_safe(self, route: Dict[str, Any], mode: str) -> Dict[str, Any]:
        # ── Extract fields safely ──────────────────────────────────────────
        yield_pct        = float(route.get("yield_percent")
                                 or route.get("overall_yield_percent")
                                 or route.get("overall_yield")
                                 or route.get("scale_adjusted_overall_yield")
                                 or 0.0)
        base_cost        = float(route.get("base_cost")
                                 or route.get("total_cost_usd")
                                 or route.get("total_cost")
                                 or 0.0)
        constraint_pen   = float(route.get("constraint_penalty", 0.0) or 0.0)
        equipment_pen    = float(route.get("equipment_penalty", 0.0) or 0.0)
        equipment_rej    = bool(route.get("equipment_rejected", False))
        purif_risk       = (route.get("purification_risk") or "low").lower()
        steps            = route.get("steps") or []

        # ── Loss-based cost ────────────────────────────────────────────────
        yield_loss_pct, yield_loss_cost, effective_cost = \
            self._calculate_yield_loss_cost(yield_pct, base_cost)

        # ── Mode-specific rule evaluation ──────────────────────────────────
        rejection_reasons: List[str] = []
        risk_flags:        List[str] = []
        recommended_actions: List[str] = []

        if mode == "pharma":
            self._evaluate_pharma_rules(
                yield_pct, constraint_pen, equipment_pen, equipment_rej,
                purif_risk, rejection_reasons, risk_flags, recommended_actions
            )
        else:
            self._evaluate_generic_rules(
                yield_pct, constraint_pen, equipment_pen, equipment_rej,
                purif_risk, mode, rejection_reasons, risk_flags, recommended_actions
            )

        # ── Bottleneck detection ───────────────────────────────────────────
        bottleneck = self._detect_bottleneck_steps(steps)
        if bottleneck["found"]:
            risk_flags.append(
                f"Bottleneck step {bottleneck['step_index'] + 1}: "
                f"yield {bottleneck['yield']:.1f}%"
            )
            recommended_actions.append(
                f"Optimize bottleneck step {bottleneck['step_index'] + 1} "
                f"(yield {bottleneck['yield']:.1f}%)"
            )

        # ── Model uncertainty ──────────────────────────────────────────────
        self._evaluate_model_uncertainty(route, risk_flags, recommended_actions)

        # ── Classify ──────────────────────────────────────────────────────
        industrial_status, pharma_status, requires_ard = self._classify(
            yield_pct, equipment_rej, constraint_pen, equipment_pen,
            rejection_reasons, mode
        )

        # ── AR&D plan ─────────────────────────────────────────────────────
        required_yield = _PHARMA_MIN_ROUTE_YIELD if mode == "pharma" else 85.0

        result: Dict[str, Any] = {
            "industrial_status":    industrial_status,
            "pharma_status":        pharma_status,
            "requires_ard":         requires_ard,
            "yield_percent":        round(yield_pct, 2),
            "required_yield_percent": required_yield,
            "base_cost":            round(base_cost, 2),
            "yield_loss_percent":   round(yield_loss_pct, 2),
            "yield_loss_cost":      round(yield_loss_cost, 2),
            "effective_cost":       round(effective_cost, 2),
            "rejection_reasons":    rejection_reasons,
            "risk_flags":           risk_flags,
            "recommended_actions":  self._recommend_ard_actions(
                                        industrial_status, recommended_actions,
                                        yield_pct, purif_risk, bottleneck
                                    ),
            "acceptability_score":  self._calculate_acceptability_score(
                                        yield_pct, constraint_pen, equipment_pen,
                                        equipment_rej, purif_risk, mode
                                    ),
            "mode":                 mode,
        }

        # Attach AR&D routing plan
        try:
            from services.ard_routing_engine import ARDRoutingEngine
            ard_router = ARDRoutingEngine()
            result["ard_plan"] = ard_router.route(route, result)
        except ImportError:
            result["ard_plan"] = self._basic_ard_plan(
                yield_pct, equipment_rej, purif_risk, constraint_pen, requires_ard
            )
        except Exception as exc:
            logger.warning("ard_routing_failed: %s", exc)
            result["ard_plan"] = self._basic_ard_plan(
                yield_pct, equipment_rej, purif_risk, constraint_pen, requires_ard
            )

        return result

    # ── Loss-based cost ─────────────────────────────────────────────────────
    def _calculate_yield_loss_cost(
        self, yield_pct: float, base_cost: float
    ) -> tuple[float, float, float]:
        """
        Compute yield-loss-adjusted effective cost.

        Example: 82% yield, ₹90,000 base
          yield_fraction = 0.82
          yield_loss_cost = (1 - 0.82) * 90000 = 16200
          effective_cost = 90000 + 16200 = 106200
        """
        yield_pct = max(0.0, min(100.0, yield_pct))
        yield_fraction   = yield_pct / 100.0
        yield_loss_pct   = 100.0 - yield_pct
        yield_loss_cost  = (1.0 - yield_fraction) * base_cost
        effective_cost   = base_cost + yield_loss_cost
        return yield_loss_pct, yield_loss_cost, effective_cost

    # ── Pharma rules ────────────────────────────────────────────────────────
    def _evaluate_pharma_rules(
        self,
        yield_pct:       float,
        constraint_pen:  float,
        equipment_pen:   float,
        equipment_rej:   bool,
        purif_risk:      str,
        rejection_reasons: List[str],
        risk_flags:        List[str],
        recommended_actions: List[str],
    ) -> None:
        if yield_pct < _EXPLORATORY_YIELD_MAX:
            rejection_reasons.append(
                f"Yield critically low ({yield_pct:.1f}%) — exploratory chemistry only"
            )
        elif yield_pct < _PHARMA_MIN_ROUTE_YIELD:
            rejection_reasons.append(
                f"Yield {yield_pct:.1f}% below pharma threshold "
                f"({_PHARMA_MIN_ROUTE_YIELD:.0f}%) — AR&D required"
            )
            recommended_actions.append("Run yield optimization engine")
            recommended_actions.append("Try catalyst substitution")
            recommended_actions.append("Try solvent replacement")
            recommended_actions.append("Tune temperature profile")

        if equipment_rej:
            rejection_reasons.append(
                "Equipment infeasible — route cannot be manufactured with available equipment"
            )
            recommended_actions.append("Check equipment feasibility")
            recommended_actions.append("Evaluate longer but cleaner multi-step route")

        if constraint_pen > _MAX_CONSTRAINT_PENALTY:
            rejection_reasons.append(
                f"Process constraint penalty {constraint_pen:.1f} exceeds limit "
                f"({_MAX_CONSTRAINT_PENALTY:.0f})"
            )
            risk_flags.append("High process constraint risk")
            recommended_actions.append("Send to AR&D optimization")

        if equipment_pen > _MAX_EQUIPMENT_PENALTY:
            risk_flags.append(
                f"Equipment penalty {equipment_pen:.1f} exceeds "
                f"threshold ({_MAX_EQUIPMENT_PENALTY:.0f})"
            )

        if purif_risk == "high":
            risk_flags.append("High purification risk — downstream processing burden")
            recommended_actions.append("Improve selectivity / reduce byproducts")
            recommended_actions.append("Reduce purification burden")

    # ── Generic rules (non-pharma) ──────────────────────────────────────────
    def _evaluate_generic_rules(
        self,
        yield_pct:       float,
        constraint_pen:  float,
        equipment_pen:   float,
        equipment_rej:   bool,
        purif_risk:      str,
        mode:            str,
        rejection_reasons: List[str],
        risk_flags:        List[str],
        recommended_actions: List[str],
    ) -> None:
        min_yield = {"cost": 60.0, "balanced": 70.0, "green": 65.0, "speed": 55.0}.get(mode, 70.0)

        if yield_pct < _EXPLORATORY_YIELD_MAX:
            rejection_reasons.append(
                f"Yield critically low ({yield_pct:.1f}%) for industrial production"
            )
        elif yield_pct < min_yield:
            rejection_reasons.append(
                f"Yield {yield_pct:.1f}% below minimum for {mode} mode ({min_yield:.0f}%)"
            )
            recommended_actions.append("Run yield optimization engine")

        if equipment_rej:
            rejection_reasons.append("Equipment infeasible")
            recommended_actions.append("Check equipment feasibility")

        if constraint_pen > _MAX_CONSTRAINT_PENALTY:
            risk_flags.append("High process constraint risk")
            recommended_actions.append("Send to AR&D optimization")

        if purif_risk == "high":
            risk_flags.append("High purification risk")
            recommended_actions.append("Reduce purification burden")

    # ── Classification ──────────────────────────────────────────────────────
    def _classify(
        self,
        yield_pct:       float,
        equipment_rej:   bool,
        constraint_pen:  float,
        equipment_pen:   float,
        rejection_reasons: List[str],
        mode:            str,
    ) -> tuple[str, str, bool]:
        """Return (industrial_status, pharma_status, requires_ard)."""

        # Hard rejections first
        if yield_pct < _EXPLORATORY_YIELD_MAX:
            return "exploratory_only", "rejected", True

        if equipment_rej:
            return "rejected", "rejected" if mode == "pharma" else "not_applicable", True

        if constraint_pen > _MAX_CONSTRAINT_PENALTY:
            return "rejected", "rejected" if mode == "pharma" else "not_applicable", True

        # Pharma yield check
        if mode == "pharma":
            if yield_pct >= _PHARMA_MIN_ROUTE_YIELD and not rejection_reasons:
                return "accepted", "accepted", False
            if yield_pct >= _PHARMA_MIN_ROUTE_YIELD and rejection_reasons:
                return "ard_required", "rejected", True
            return "ard_required", "rejected", True

        # Generic mode
        min_yield = {"cost": 60.0, "balanced": 70.0, "green": 65.0, "speed": 55.0}.get(mode, 70.0)
        if yield_pct >= min_yield and not rejection_reasons:
            return "accepted", "not_applicable", False
        if rejection_reasons:
            return "ard_required", "not_applicable", True
        return "accepted", "not_applicable", False

    # ── Bottleneck detection ─────────────────────────────────────────────────
    def _detect_bottleneck_steps(self, steps: List[Dict]) -> Dict[str, Any]:
        """Find the lowest-yield step in the route."""
        best = {"found": False, "step_index": -1, "yield": 100.0}
        for i, step in enumerate(steps):
            y = float(
                step.get("estimated_yield_percent")
                or step.get("estimated_yield")
                or step.get("predicted_yield")
                or step.get("scale_adjusted_yield")
                or 100.0
            )
            if y < best["yield"]:
                best = {"found": True, "step_index": i, "yield": y}
        # Only flag as bottleneck if meaningfully below recommended minimum
        if best["found"] and best["yield"] >= _PHARMA_MIN_STEP_YIELD:
            best["found"] = False
        return best

    # ── Model uncertainty ────────────────────────────────────────────────────
    def _evaluate_model_uncertainty(
        self,
        route: Dict[str, Any],
        risk_flags: List[str],
        recommended_actions: List[str],
    ) -> None:
        """Use ML model disagreement / low confidence as a risk signal."""
        model_results       = route.get("model_results") or {}
        individual_preds    = route.get("individual_predictions") or {}
        model_metrics       = route.get("model_metrics") or {}
        ensemble_prediction = route.get("ensemble_prediction")

        # Check per-step yield_prediction dicts
        steps = route.get("steps") or []
        preds: List[float] = []
        for step in steps:
            yp = step.get("yield_prediction") or {}
            if isinstance(yp, dict):
                ind = yp.get("individual_predictions") or {}
                vals = [v for v in ind.values() if isinstance(v, (int, float))]
                preds.extend(vals)
                # Also check confidence
                conf = (yp.get("confidence") or "medium").lower()
                if conf == "low":
                    risk_flags.append("Low model confidence on step yield prediction")

        # Direct route-level individual predictions
        if individual_preds and not preds:
            vals = [v for v in individual_preds.values() if isinstance(v, (int, float))]
            preds.extend(vals)

        if len(preds) >= 2:
            spread = max(preds) - min(preds)
            if spread > 20:
                risk_flags.append(
                    f"High model disagreement: prediction spread {spread:.1f}% "
                    f"— ensemble uncertainty elevated"
                )
                recommended_actions.append(
                    "Collect experimental data to resolve model disagreement"
                )
            elif spread > 10:
                risk_flags.append(
                    f"Moderate model disagreement: spread {spread:.1f}%"
                )

        # Route-level metrics
        if model_metrics:
            for model_name, metrics in model_metrics.items():
                if isinstance(metrics, dict):
                    r2 = metrics.get("r2") or metrics.get("test_r2")
                    if r2 is not None and float(r2) < 0.5:
                        risk_flags.append(
                            f"Low model quality ({model_name}): R²={float(r2):.2f}"
                        )

    # ── Action recommendations ───────────────────────────────────────────────
    def _recommend_ard_actions(
        self,
        status:             str,
        existing_actions:   List[str],
        yield_pct:          float,
        purif_risk:         str,
        bottleneck:         Dict[str, Any],
    ) -> List[str]:
        """Deduplicate and augment recommended actions."""
        actions = list(dict.fromkeys(existing_actions))  # deduplicate, preserve order

        if status in ("ard_required", "rejected", "exploratory_only"):
            if "Run yield optimization engine" not in actions:
                actions.append("Run yield optimization engine")
            if bottleneck["found"] and "Optimize bottleneck step" not in " ".join(actions):
                actions.append(
                    f"Optimize bottleneck step "
                    f"{bottleneck['step_index'] + 1} (yield {bottleneck['yield']:.1f}%)"
                )
            if yield_pct < 50 and "Evaluate longer but cleaner multi-step route" not in actions:
                actions.append("Evaluate longer but cleaner multi-step route")
            if purif_risk == "high":
                for a in ["Improve selectivity / reduce byproducts", "Reduce purification burden"]:
                    if a not in actions:
                        actions.append(a)
            if "Send to AR&D optimization" not in actions:
                actions.append("Send to AR&D optimization")

        return actions[:10]  # cap at 10

    # ── Acceptability score ──────────────────────────────────────────────────
    def _calculate_acceptability_score(
        self,
        yield_pct:      float,
        constraint_pen: float,
        equipment_pen:  float,
        equipment_rej:  bool,
        purif_risk:     str,
        mode:           str,
    ) -> int:
        """Return 0–100 acceptability score."""
        if equipment_rej:
            return 0

        required_yield = _PHARMA_MIN_ROUTE_YIELD if mode == "pharma" else 80.0

        # Yield component (60 points)
        yield_score = min(60, max(0, (yield_pct / required_yield) * 60))

        # Constraint component (20 points)
        constraint_score = max(0, 20 - (constraint_pen / _MAX_CONSTRAINT_PENALTY) * 20)

        # Equipment component (10 points)
        equip_score = max(0, 10 - (equipment_pen / _MAX_EQUIPMENT_PENALTY) * 10)

        # Purification component (10 points)
        purif_score = {"low": 10, "medium": 6, "high": 0}.get(purif_risk, 5)

        total = yield_score + constraint_score + equip_score + purif_score
        return max(0, min(100, int(round(total))))

    # ── Basic AR&D plan fallback ─────────────────────────────────────────────
    def _basic_ard_plan(
        self,
        yield_pct:      float,
        equipment_rej:  bool,
        purif_risk:     str,
        constraint_pen: float,
        requires_ard:   bool,
    ) -> Dict[str, Any]:
        if not requires_ard:
            return {"ard_required": False, "priority": "none", "optimization_targets": [], "recommended_sequence": []}

        targets: List[str] = []
        if yield_pct < 30:
            priority = "critical"
            targets = ["yield", "bottleneck_step", "catalyst", "solvent"]
        elif yield_pct < 90:
            priority = "high"
            targets = ["yield", "bottleneck_step", "catalyst"]
        elif yield_pct < 99:
            priority = "medium"
            targets = ["yield", "temperature"]
        else:
            priority = "low"
            targets = ["cost"]

        if equipment_rej:
            priority = "critical"
            targets.insert(0, "equipment")
        if purif_risk == "high":
            targets.append("purification")
        if constraint_pen > _MAX_CONSTRAINT_PENALTY:
            targets.append("cost")

        seq = [f"Optimize {t.replace('_', ' ')}" for t in targets[:5]]
        seq.append("Recalculate effective cost")

        return {
            "ard_required":         True,
            "priority":             priority,
            "optimization_targets": targets,
            "recommended_sequence": seq,
        }

    # ── Fallback result ──────────────────────────────────────────────────────
    def _fallback_result(self, route: Dict[str, Any], mode: str, error: str) -> Dict[str, Any]:
        return {
            "industrial_status":      "ard_required",
            "pharma_status":          "not_applicable",
            "requires_ard":           True,
            "yield_percent":          float(route.get("overall_yield_percent", 0)),
            "required_yield_percent": _PHARMA_MIN_ROUTE_YIELD if mode == "pharma" else 85.0,
            "base_cost":              float(route.get("total_cost_usd", 0)),
            "yield_loss_percent":     0.0,
            "yield_loss_cost":        0.0,
            "effective_cost":         float(route.get("total_cost_usd", 0)),
            "rejection_reasons":      [f"Evaluation error: {error}"],
            "risk_flags":             ["Evaluation incomplete"],
            "recommended_actions":    ["Manual review required"],
            "acceptability_score":    0,
            "mode":                   mode,
            "ard_plan":               {"ard_required": True, "priority": "high",
                                       "optimization_targets": [], "recommended_sequence": []},
        }
