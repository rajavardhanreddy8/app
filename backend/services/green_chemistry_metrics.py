"""Green chemistry metrics for synthesis routes.

Implements route-level sustainability metrics used in process chemistry:
atom economy, E-factor, PMI, solvent intensity, rough carbon footprint, and
route convergence.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

SOLVENT_FACTORS = {
    "lab": 10.0,
    "pilot": 7.0,
    "industrial": 5.0,
}

CO2_KG_PER_KG_SOLVENT = 2.5
CO2_KG_PER_KWH = 0.4
KWH_PER_KG_REACTANT_HOUR = 0.05


@dataclass
class StepGreenMetrics:
    """Sustainability metrics for a single reaction step."""

    step_index: int
    atom_economy_percent: float
    atom_utilization: float
    reactant_mass_kg_per_kg_product: float
    solvent_mass_kg_per_kg_product: float
    waste_kg_per_kg_product: float
    e_factor: float
    pmi: float
    product_mw: float
    reactant_mw_sum: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_index": self.step_index + 1,
            "atom_economy_percent": round(self.atom_economy_percent, 2),
            "atom_utilization": round(self.atom_utilization, 4),
            "reactant_mass_kg_per_kg_product": round(self.reactant_mass_kg_per_kg_product, 2),
            "solvent_mass_kg_per_kg_product": round(self.solvent_mass_kg_per_kg_product, 2),
            "waste_kg_per_kg_product": round(self.waste_kg_per_kg_product, 2),
            "e_factor": round(self.e_factor, 2),
            "pmi": round(self.pmi, 2),
        }


@dataclass
class RouteGreenMetrics:
    """Route-level green chemistry metrics exposed on synthesis routes."""

    atom_economy_percent: float
    e_factor: float
    pmi: float
    pmi_rating: str
    route_type: str
    convergence_score: float
    estimated_co2_kg_per_kg_product: float
    bottleneck_step: int
    solvent_intensity_kg_per_kg: float
    step_details: List[StepGreenMetrics] = field(default_factory=list)

    def to_dict(self, include_step_details: bool = False) -> Dict[str, Any]:
        payload = {
            "atom_economy_percent": round(self.atom_economy_percent, 2),
            "e_factor": round(self.e_factor, 2),
            "pmi": round(self.pmi, 2),
            "pmi_rating": self.pmi_rating,
            "route_type": self.route_type,
            "convergence_score": round(self.convergence_score, 3),
            "estimated_co2_kg_per_kg_product": round(self.estimated_co2_kg_per_kg_product, 2),
            "bottleneck_step": self.bottleneck_step,
            "solvent_intensity_kg_per_kg": round(self.solvent_intensity_kg_per_kg, 2),
        }
        if include_step_details:
            payload["step_details"] = [step.to_dict() for step in self.step_details]
        return payload


class GreenChemistryMetrics:
    """Calculate process sustainability metrics for synthesis routes.

    Expected route shape:

    {
        "steps": [
            {
                "reactants": [{"smiles": "..."}, "..."],
                "product": {"smiles": "..."},
                "conditions": {"time_hours": 4.0}
            }
        ]
    }
    """

    def calculate(self, route: Dict[str, Any], scale: str = "lab") -> RouteGreenMetrics:
        steps = route.get("steps") or []
        if not steps:
            return self._empty_metrics()

        solvent_factor = SOLVENT_FACTORS.get(scale, SOLVENT_FACTORS["lab"])
        step_metrics = [
            self._calculate_step_metrics(step, index, solvent_factor)
            for index, step in enumerate(steps)
        ]

        atom_economy = self._geometric_mean(
            [step.atom_economy_percent for step in step_metrics if step.atom_economy_percent > 0]
        )
        e_factor = sum(step.e_factor for step in step_metrics)
        pmi = e_factor + 1.0
        solvent_intensity = sum(step.solvent_mass_kg_per_kg_product for step in step_metrics)

        total_energy_kwh = 0.0
        for step, metrics in zip(steps, step_metrics):
            conditions = step.get("conditions") or step.get("predicted_conditions") or {}
            time_hours = self._safe_float(conditions.get("time_hours", step.get("predicted_time_hours", 4.0)), 4.0)
            total_energy_kwh += metrics.reactant_mass_kg_per_kg_product * time_hours * KWH_PER_KG_REACTANT_HOUR

        co2 = solvent_intensity * CO2_KG_PER_KG_SOLVENT + total_energy_kwh * CO2_KG_PER_KWH
        bottleneck_step = min(
            range(len(step_metrics)),
            key=lambda idx: step_metrics[idx].atom_economy_percent,
        ) + 1
        convergence_score, route_type = self._calculate_convergence(steps)

        return RouteGreenMetrics(
            atom_economy_percent=atom_economy,
            e_factor=e_factor,
            pmi=pmi,
            pmi_rating=self._pmi_rating(pmi),
            route_type=route_type,
            convergence_score=convergence_score,
            estimated_co2_kg_per_kg_product=co2,
            bottleneck_step=bottleneck_step,
            solvent_intensity_kg_per_kg=solvent_intensity,
            step_details=step_metrics,
        )

    def rank_routes(self, routes: List[Dict[str, Any]], scale: str = "lab") -> List[Dict[str, Any]]:
        """Rank routes by PMI, atom economy, E-factor, then convergence."""

        ranked: List[Dict[str, Any]] = []
        for index, route in enumerate(routes):
            metrics = self.calculate(route, scale=scale)
            ranked.append(
                {
                    "route": route,
                    "green_metrics": metrics.to_dict(),
                    "_sort_key": (
                        metrics.pmi,
                        -metrics.atom_economy_percent,
                        metrics.e_factor,
                        -metrics.convergence_score,
                        index,
                    ),
                }
            )

        ranked.sort(key=lambda item: item["_sort_key"])

        for rank, item in enumerate(ranked, start=1):
            item["sustainability_rank"] = rank
            item["sustainability_score"] = self._ranking_score(item["green_metrics"])
            del item["_sort_key"]

        return ranked

    def _calculate_step_metrics(
        self,
        step: Dict[str, Any],
        step_index: int,
        solvent_factor: float,
    ) -> StepGreenMetrics:
        reactants = self._extract_smiles_list(step.get("reactants", []))
        product = self._extract_smiles(step.get("product", ""))

        reactant_mws = [mw for mw in (self._exact_mw(smiles) for smiles in reactants) if mw and mw > 0]
        product_mw = self._exact_mw(product)

        reactant_mw_sum = sum(reactant_mws)
        if reactant_mw_sum <= 0:
            reactant_mw_sum = 100.0
        if not product_mw or product_mw <= 0:
            product_mw = reactant_mw_sum * 0.7

        atom_economy = min((product_mw / reactant_mw_sum) * 100.0, 100.0)

        # Normalize every step to 1 kg desired product.
        product_mass_kg = 1.0
        reactant_mass_kg = reactant_mw_sum / product_mw
        solvent_mass_kg = solvent_factor * reactant_mass_kg
        total_input_mass_kg = reactant_mass_kg + solvent_mass_kg
        waste_mass_kg = max(total_input_mass_kg - product_mass_kg, 0.0)
        e_factor = waste_mass_kg / product_mass_kg
        pmi = total_input_mass_kg / product_mass_kg

        return StepGreenMetrics(
            step_index=step_index,
            atom_economy_percent=atom_economy,
            atom_utilization=atom_economy / 100.0,
            reactant_mass_kg_per_kg_product=reactant_mass_kg,
            solvent_mass_kg_per_kg_product=solvent_mass_kg,
            waste_kg_per_kg_product=waste_mass_kg,
            e_factor=e_factor,
            pmi=pmi,
            product_mw=product_mw,
            reactant_mw_sum=reactant_mw_sum,
        )

    def _calculate_convergence(self, steps: List[Dict[str, Any]]) -> Tuple[float, str]:
        produced: set[str] = set()
        max_merge_score = 0.0

        for step in steps:
            reactants = self._extract_smiles_list(step.get("reactants", []))
            previous_products_used = sum(1 for smiles in reactants if smiles in produced)

            if previous_products_used >= 2:
                max_merge_score = max(max_merge_score, 1.0)
            elif previous_products_used == 1 and len(reactants) > 2:
                max_merge_score = max(max_merge_score, 0.5)

            product = self._extract_smiles(step.get("product", ""))
            if product:
                produced.add(product)

        if max_merge_score >= 1.0:
            return 1.0, "convergent"
        if max_merge_score >= 0.5:
            return 0.5, "semi-convergent"
        return 0.0, "linear"

    @staticmethod
    def _pmi_rating(pmi: float) -> str:
        if pmi < 10:
            return "excellent"
        if pmi <= 25:
            return "acceptable"
        if pmi <= 50:
            return "needs improvement"
        return "unsustainable at scale"

    @staticmethod
    def _ranking_score(metrics: Dict[str, Any]) -> float:
        pmi_score = max(0.0, 100.0 - min(metrics["pmi"], 100.0))
        ae_score = metrics["atom_economy_percent"]
        ef_score = max(0.0, 100.0 - min(metrics["e_factor"], 100.0))
        convergence_score = metrics["convergence_score"] * 100.0
        return round(0.40 * pmi_score + 0.30 * ae_score + 0.20 * ef_score + 0.10 * convergence_score, 2)

    @staticmethod
    def _geometric_mean(values: List[float]) -> float:
        if not values:
            return 0.0
        return math.exp(sum(math.log(value) for value in values) / len(values))

    @staticmethod
    def _extract_smiles_list(items: Any) -> List[str]:
        if not isinstance(items, list):
            return []
        return [smiles for smiles in (GreenChemistryMetrics._extract_smiles(item) for item in items) if smiles]

    @staticmethod
    def _extract_smiles(item: Any) -> str:
        if isinstance(item, dict):
            return str(item.get("smiles") or item.get("SMILES") or "").strip()
        return str(item or "").strip()

    @staticmethod
    def _exact_mw(smiles: str) -> Optional[float]:
        if not smiles:
            return None
        try:
            from rdkit import Chem
            from rdkit.Chem import Descriptors

            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return None
            return float(Descriptors.ExactMolWt(mol))
        except Exception as exc:
            logger.debug("RDKit exact MW failed for %s: %s", smiles, exc)
            return GreenChemistryMetrics._heuristic_mw(smiles)

    @staticmethod
    def _heuristic_mw(smiles: str) -> float:
        heavy_atom_count = sum(1 for char in smiles if char.isalpha() and char.upper() != "H")
        return max(heavy_atom_count * 13.0, 1.0)

    @staticmethod
    def _safe_float(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _empty_metrics() -> RouteGreenMetrics:
        return RouteGreenMetrics(
            atom_economy_percent=0.0,
            e_factor=0.0,
            pmi=1.0,
            pmi_rating="excellent",
            route_type="linear",
            convergence_score=0.0,
            estimated_co2_kg_per_kg_product=0.0,
            bottleneck_step=0,
            solvent_intensity_kg_per_kg=0.0,
        )


_green_metrics_instance: Optional[GreenChemistryMetrics] = None


def get_green_metrics() -> GreenChemistryMetrics:
    global _green_metrics_instance
    if _green_metrics_instance is None:
        _green_metrics_instance = GreenChemistryMetrics()
    return _green_metrics_instance
