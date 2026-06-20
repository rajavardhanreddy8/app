"""
Phase 11: AR&D Routing Engine

Inspects industrial acceptability results and routes failed/borderline
routes to specific optimization modules.  Returns a structured AR&D plan
without running heavy loops automatically.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_PHARMA_MIN_ROUTE_YIELD = 99.0
_EXPLORATORY_MAX        = 30.0
_MAX_CONSTRAINT_PENALTY = 35.0


class ARDRoutingEngine:
    """
    Decides what optimization module(s) should handle a failed route.

    Usage::
        ard = ARDRoutingEngine()
        plan = ard.route(route_dict, acceptability_dict)
    """

    def route(
        self, route: Dict[str, Any], acceptability: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Build an AR&D routing plan.

        Args:
            route:         Raw route dict (from orchestrator).
            acceptability: Result from IndustrialAcceptabilityEngine.evaluate().

        Returns::
            {
              "ard_required": bool,
              "priority": "critical"|"high"|"medium"|"low",
              "optimization_targets": [...],
              "recommended_sequence": [...],
            }
        """
        try:
            return self._route_safe(route, acceptability)
        except Exception as exc:
            logger.warning("ard_routing_error: %s", exc, exc_info=True)
            return {
                "ard_required":         True,
                "priority":             "high",
                "optimization_targets": ["yield"],
                "recommended_sequence": ["Manual AR&D review required"],
            }

    # ── Internal ────────────────────────────────────────────────────────────
    def _route_safe(
        self, route: Dict[str, Any], acceptability: Dict[str, Any]
    ) -> Dict[str, Any]:
        requires_ard    = acceptability.get("requires_ard", False)
        industrial_stat = acceptability.get("industrial_status", "ard_required")

        if not requires_ard and industrial_stat == "accepted":
            return {
                "ard_required":         False,
                "priority":             "none",
                "optimization_targets": [],
                "recommended_sequence": [],
            }

        yield_pct       = float(acceptability.get("yield_percent", 0.0))
        base_cost       = float(acceptability.get("base_cost", 0.0))
        effective_cost  = float(acceptability.get("effective_cost", 0.0))
        constraint_pen  = float(route.get("constraint_penalty", 0.0) or 0.0)
        equipment_rej   = bool(route.get("equipment_rejected", False))
        purif_risk      = (route.get("purification_risk") or "low").lower()
        rejection_rsns  = acceptability.get("rejection_reasons", [])
        risk_flags      = acceptability.get("risk_flags", [])
        mode            = acceptability.get("mode", "pharma")

        # ── Priority ────────────────────────────────────────────────────────
        priority = self._compute_priority(
            yield_pct, equipment_rej, constraint_pen,
            industrial_stat, mode
        )

        # ── Optimization targets ────────────────────────────────────────────
        targets = self._compute_targets(
            yield_pct, base_cost, effective_cost, constraint_pen,
            equipment_rej, purif_risk, risk_flags, mode
        )

        # ── Recommended sequence ────────────────────────────────────────────
        sequence = self._build_sequence(targets, yield_pct, purif_risk)

        return {
            "ard_required":         True,
            "priority":             priority,
            "optimization_targets": targets,
            "recommended_sequence": sequence,
        }

    # ── Priority logic ───────────────────────────────────────────────────────
    def _compute_priority(
        self,
        yield_pct:      float,
        equipment_rej:  bool,
        constraint_pen: float,
        status:         str,
        mode:           str,
    ) -> str:
        if status == "exploratory_only" or yield_pct < _EXPLORATORY_MAX:
            return "critical"
        if equipment_rej:
            return "critical"
        if yield_pct < 30:
            return "critical"
        if yield_pct < 70:
            return "high"
        if mode == "pharma" and yield_pct < _PHARMA_MIN_ROUTE_YIELD:
            return "high" if yield_pct < 90 else "medium"
        if constraint_pen > _MAX_CONSTRAINT_PENALTY:
            return "high"
        return "low"

    # ── Target selection ─────────────────────────────────────────────────────
    def _compute_targets(
        self,
        yield_pct:      float,
        base_cost:      float,
        effective_cost: float,
        constraint_pen: float,
        equipment_rej:  bool,
        purif_risk:     str,
        risk_flags:     List[str],
        mode:           str,
    ) -> List[str]:
        targets: List[str] = []
        seen = set()

        def add(t: str) -> None:
            if t not in seen:
                targets.append(t)
                seen.add(t)

        # Yield always first priority
        if yield_pct < _PHARMA_MIN_ROUTE_YIELD:
            add("yield")
            add("bottleneck_step")

        # Catalyst / solvent for low yields
        if yield_pct < 80:
            add("catalyst")
            add("solvent")
            add("temperature")

        # Selectivity and purification
        if purif_risk == "high":
            add("selectivity")
            add("purification")

        # Equipment redesign
        if equipment_rej:
            add("equipment")

        # Process constraints
        if constraint_pen > _MAX_CONSTRAINT_PENALTY:
            add("cost")

        # High effective cost even with OK yield
        if base_cost > 0 and effective_cost > base_cost * 1.3:
            add("cost")

        # Model disagreement → data collection
        if any("disagree" in f.lower() or "uncertainty" in f.lower() for f in risk_flags):
            add("data_collection")

        return targets if targets else ["yield"]

    # ── Sequence builder ─────────────────────────────────────────────────────
    def _build_sequence(
        self,
        targets:    List[str],
        yield_pct:  float,
        purif_risk: str,
    ) -> List[str]:
        _labels: Dict[str, str] = {
            "yield":           "Run yield optimization engine",
            "bottleneck_step": "Optimize bottleneck step",
            "catalyst":        "Try catalyst substitution",
            "solvent":         "Try solvent replacement",
            "temperature":     "Tune temperature profile",
            "selectivity":     "Improve selectivity / reduce byproducts",
            "purification":    "Reduce purification burden",
            "equipment":       "Evaluate equipment / process redesign",
            "cost":            "Recalculate effective cost after optimization",
            "data_collection": "Collect experimental data to resolve model disagreement",
        }
        seq = [_labels[t] for t in targets if t in _labels]
        seq.append("Recalculate effective cost")
        return seq[:8]  # cap at 8 steps
