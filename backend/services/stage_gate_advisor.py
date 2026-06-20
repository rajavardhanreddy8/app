"""Clinical development stage-gate advisor for synthesis routes."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


DEVELOPMENT_STAGES = {
    "discovery": {
        "quantity_kg": (0.001, 0.1),
        "priority": "speed",
        "route_preference": "fewest_steps",
        "catalyst_preference": "any",
        "pmi_threshold": None,
        "key_question": "Can we make it at all?",
        "acceptable_yield": 20.0,
    },
    "phase_1": {
        "quantity_kg": (0.1, 1.0),
        "priority": "purity_and_speed",
        "route_preference": "safest_route",
        "catalyst_preference": "any",
        "pmi_threshold": 100,
        "key_question": "Is it safe? Can we make enough?",
        "acceptable_yield": 40.0,
    },
    "phase_2": {
        "quantity_kg": (1.0, 10.0),
        "priority": "route_robustness",
        "route_preference": "most_reproducible",
        "catalyst_preference": "heterogeneous_preferred",
        "pmi_threshold": 50,
        "key_question": "Will this route work at 10kg? Impurity profile ok?",
        "acceptable_yield": 55.0,
    },
    "phase_3": {
        "quantity_kg": (10.0, 100.0),
        "priority": "cogs_and_scalability",
        "route_preference": "convergent_preferred",
        "catalyst_preference": "heterogeneous_required",
        "pmi_threshold": 25,
        "key_question": "Can we file this route? What is the commercial CoG?",
        "acceptable_yield": 65.0,
    },
    "commercial": {
        "quantity_kg": (100.0, float("inf")),
        "priority": "minimum_cost",
        "route_preference": "telescoped_convergent",
        "catalyst_preference": "biocatalysis_or_heterogeneous",
        "pmi_threshold": 15,
        "key_question": "Is this the most profitable route at multi-ton scale?",
        "acceptable_yield": 75.0,
    },
}


class StageGateAdvisor:
    """Rank and annotate routes according to clinical development stage."""

    def advise_for_stage(
        self,
        routes: List[Dict[str, Any]],
        stage: str,
        target_quantity_kg: float,
    ) -> Dict[str, Any]:
        stage = self._normalize_stage(stage)
        stage_config = DEVELOPMENT_STAGES[stage]
        target_quantity_kg = float(target_quantity_kg)

        annotated = [self._annotate_route(route, stage_config) for route in routes]
        viable = [
            route for route in annotated
            if route["stage_gate"]["yield_ok"] and route["stage_gate"]["pmi_ok"]
        ]
        ranked = self._rank_routes(viable, stage)
        recommended = ranked[0] if ranked else None

        return {
            "stage": stage,
            "stage_config": self._public_stage_config(stage_config),
            "recommended_route": recommended,
            "stage_rationale": stage_config["key_question"],
            "quantity_guidance": self._quantity_guidance(stage, target_quantity_kg, stage_config),
            "route_evolution_needed": stage in ("phase_3", "commercial"),
            "next_stage_changes": self._predict_route_changes(recommended, stage) if recommended else [],
            "cmo_recommendation": self._recommend_cmo_type(stage),
            "regulatory_milestone": self._get_regulatory_milestone(stage),
            "viable_route_count": len(ranked),
            "rejected_route_count": max(len(routes) - len(ranked), 0),
            "ranked_routes": ranked,
            "rejected_routes": [route for route in annotated if route not in ranked],
        }

    def _rank_routes(self, viable: List[Dict[str, Any]], stage: str) -> List[Dict[str, Any]]:
        if stage in ("discovery", "phase_1"):
            return sorted(viable, key=lambda route: (self._num_steps(route), -self._overall_yield(route)))
        if stage in ("phase_2", "phase_3"):
            return sorted(
                viable,
                key=lambda route: (
                    self._pmi(route),
                    -self._convergence_score(route),
                    self._num_steps(route),
                    -self._overall_yield(route),
                ),
            )
        return sorted(
            viable,
            key=lambda route: (
                self._cost_per_kg(route),
                self._pmi(route),
                -self._convergence_score(route),
                -self._overall_yield(route),
            ),
        )

    def _annotate_route(self, route: Dict[str, Any], stage_config: Dict[str, Any]) -> Dict[str, Any]:
        annotated = dict(route)
        overall_yield = self._overall_yield(route)
        pmi = self._pmi(route)
        pmi_threshold = stage_config["pmi_threshold"]
        yield_ok = overall_yield >= stage_config["acceptable_yield"]
        pmi_ok = pmi_threshold is None or pmi <= pmi_threshold
        issues = []
        if not yield_ok:
            issues.append(
                f"Overall yield {overall_yield:.1f}% is below stage threshold "
                f"{stage_config['acceptable_yield']:.1f}%"
            )
        if not pmi_ok:
            issues.append(f"PMI {pmi:.1f} exceeds stage threshold {pmi_threshold}")
        annotated["stage_gate"] = {
            "yield_ok": yield_ok,
            "pmi_ok": pmi_ok,
            "issues": issues,
            "priority": stage_config["priority"],
            "route_preference": stage_config["route_preference"],
            "catalyst_preference": stage_config["catalyst_preference"],
        }
        return annotated

    def _predict_route_changes(self, route: Optional[Dict[str, Any]], current_stage: str) -> List[str]:
        if not route:
            return []
        changes = []
        pmi = self._pmi(route)
        catalysts = [self._step_catalyst(step) for step in route.get("steps", [])]

        if current_stage == "discovery":
            changes.append("Add impurity controls and salt/polymorph screening before Phase I.")
        if current_stage == "phase_1":
            changes.append("Replace chromatography-heavy operations before Phase II scale-up.")
        if current_stage == "phase_2":
            if any("Pd(PPh3)4" in catalyst for catalyst in catalysts):
                changes.append("Replace homogeneous Pd with Pd/C or another easy-removal catalyst before Phase III.")
            if pmi > 50:
                changes.append("Solvent reduction required - current PMI too high for Phase III.")
            changes.append("Lock impurity fate/purge strategy before pivotal batches.")
        if current_stage == "phase_3":
            if pmi > 25:
                changes.append("PMI must move below 25 before commercial launch.")
            if not self._has_heterogeneous_or_biocatalyst(route):
                changes.append("Move catalysis toward heterogeneous or biocatalytic options for commercial supply.")
            changes.append("Demonstrate validated control strategy and process robustness for filing.")
        if current_stage == "commercial":
            if pmi > 15:
                changes.append("Further solvent recovery, telescoping, or route redesign needed for multi-ton economics.")
            if not route.get("telescoping_summary"):
                changes.append("Evaluate telescoping and continuous processing for cycle-time reduction.")
        return changes

    @staticmethod
    def _recommend_cmo_type(stage: str) -> str:
        return {
            "discovery": "medicinal chemistry CRO with rapid analog synthesis",
            "phase_1": "GMP kilo lab with rapid analytical method development",
            "phase_2": "pilot-plant CMO with impurity profiling and scale-up engineering",
            "phase_3": "late-stage GMP CMO with validation, PPQ readiness, and regulatory documentation",
            "commercial": "commercial API manufacturer with multi-ton capacity and strong solvent recovery",
        }[stage]

    @staticmethod
    def _get_regulatory_milestone(stage: str) -> str:
        return {
            "discovery": "pre-IND route scouting",
            "phase_1": "IND-enabling GMP tox and first-in-human supply",
            "phase_2": "clinical proof-of-concept supply with impurity trend monitoring",
            "phase_3": "registration route definition and process validation planning",
            "commercial": "validated commercial process and lifecycle cost control",
        }[stage]

    @staticmethod
    def _quantity_guidance(stage: str, quantity_kg: float, stage_config: Dict[str, Any]) -> str:
        lo, hi = stage_config["quantity_kg"]
        if hi == float("inf"):
            range_text = f">={lo:g} kg"
        else:
            range_text = f"{lo:g}-{hi:g} kg"
        fit = "within" if lo <= quantity_kg <= hi else "outside"
        return f"Target: {quantity_kg:g}kg - {stage} scale ({range_text}); target is {fit} normal range"

    @staticmethod
    def _public_stage_config(stage_config: Dict[str, Any]) -> Dict[str, Any]:
        public_config = dict(stage_config)
        lo, hi = public_config["quantity_kg"]
        public_config["quantity_kg"] = {"min": lo, "max": None if hi == float("inf") else hi}
        return public_config

    @staticmethod
    def _normalize_stage(stage: str) -> str:
        normalized = (stage or "").lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "phase_i": "phase_1",
            "phase_ii": "phase_2",
            "phase_iii": "phase_3",
            "p1": "phase_1",
            "p2": "phase_2",
            "p3": "phase_3",
        }
        normalized = aliases.get(normalized, normalized)
        if normalized not in DEVELOPMENT_STAGES:
            raise ValueError(f"Unknown development stage: {stage}")
        return normalized

    @staticmethod
    def _overall_yield(route: Dict[str, Any]) -> float:
        value = route.get("overall_yield", route.get("overall_yield_percent", route.get("scale_adjusted_overall_yield", 0.0)))
        return StageGateAdvisor._safe_float(value, 0.0)

    @staticmethod
    def _num_steps(route: Dict[str, Any]) -> int:
        return int(route.get("num_steps") or len(route.get("steps", [])) or 999)

    @staticmethod
    def _pmi(route: Dict[str, Any]) -> float:
        green_metrics = route.get("green_metrics") or {}
        return StageGateAdvisor._safe_float(green_metrics.get("pmi"), 999.0)

    @staticmethod
    def _convergence_score(route: Dict[str, Any]) -> float:
        green_metrics = route.get("green_metrics") or {}
        return StageGateAdvisor._safe_float(green_metrics.get("convergence_score"), 0.0)

    @staticmethod
    def _cost_per_kg(route: Dict[str, Any]) -> float:
        return StageGateAdvisor._safe_float(
            route.get("cost_per_kg_product", route.get("cost_per_kg", route.get("total_cost_usd"))),
            9999.0,
        )

    @staticmethod
    def _step_catalyst(step: Dict[str, Any]) -> str:
        conditions = step.get("conditions") or step.get("predicted_conditions") or {}
        return str(step.get("catalyst") or conditions.get("catalyst") or "")

    @staticmethod
    def _has_heterogeneous_or_biocatalyst(route: Dict[str, Any]) -> bool:
        catalysts = " ".join(StageGateAdvisor._step_catalyst(step).lower() for step in route.get("steps", []))
        return any(token in catalysts for token in ("pd/c", "pd/al2o3", "raney", "hzsm", "lipase", "transaminase", "ketoreductase", "laccase"))

    @staticmethod
    def _safe_float(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
