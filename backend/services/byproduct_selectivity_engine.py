"""
Phase 12: Byproduct, Selectivity, and Reversibility Engine.

This engine evaluates each step of a synthesis route for:
- Byproduct generation
- Main product selectivity
- Reversible reaction behavior and equilibrium limits
- Impurity risks and purification burden

It adjusts step effective yield based on selectivity loss and equilibrium limits,
and flags high-risk issues for AR&D optimization, especially in pharma mode.
"""

import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class ByproductSelectivityEngine:
    def __init__(self):
        # Heuristic rules for reversibility and byproducts based on reaction type
        self.reversible_types = ["esterification", "imine formation", "condensation", "transesterification", "acetal formation"]
        
        self.byproduct_map = {
            "esterification": ["H2O"],
            "condensation": ["H2O"],
            "imine formation": ["H2O"],
            "suzuki coupling": ["boric acid", "halide salts"],
            "buchwald-hartwig": ["amine salts", "halide salts"],
            "oxidation": ["reduced oxidant byproducts"],
            "reduction": ["oxidized reductant byproducts"],
            "amidation": ["H2O", "coupling reagent byproducts"],
            "grignard": ["magnesium salts"],
        }

    def evaluate(self, route_dict: Dict[str, Any], pharma_mode: bool = False) -> Dict[str, Any]:
        """
        Evaluate the entire route for selectivity, byproducts, and reversibility.
        Updates steps in-place with `byproduct_analysis` and computes route penalties.
        """
        if not route_dict or "steps" not in route_dict:
            return route_dict

        total_byproduct_penalty = 0.0
        total_selectivity_penalty = 0.0
        total_reversibility_penalty = 0.0
        max_impurity_risk_score = 1
        
        impurity_risk_map = {"low": 1, "medium": 2, "high": 3}
        reverse_risk_map = {1: "low", 2: "medium", 3: "high"}

        # Track if we need to reject or flag for AR&D
        overall_status = "accepted"
        rejection_reasons = []
        ard_flags = []

        steps = route_dict.get("steps", [])
        
        for step in steps:
            rxn_type = step.get("reaction_type", "").lower()
            difficulty = step.get("difficulty", "moderate").lower()
            original_yield = step.get("scale_adjusted_yield", step.get("estimated_yield", 80.0))
            
            # 1. Determine Reversibility
            reversible = any(rt in rxn_type for rt in self.reversible_types)
            equilibrium_penalty = 0.0
            if reversible:
                # If reaction is reversible, assume a 5-15% yield penalty due to equilibrium limits 
                # unless a driving force (e.g., Dean-Stark) is explicitly modeled (simplified here).
                equilibrium_penalty = 10.0 if difficulty == "high" else 5.0

            # 2. Estimate Selectivity
            # Base selectivity on difficulty: easy=95%+, moderate=85-95%, high=<85%
            if difficulty == "easy":
                selectivity = 98.0
            elif difficulty == "moderate":
                selectivity = 90.0
            else:
                selectivity = 82.0
            
            # 3. Predict Byproducts
            step_byproducts = []
            for key, b_list in self.byproduct_map.items():
                if key in rxn_type:
                    step_byproducts.extend(b_list)
            if not step_byproducts:
                step_byproducts = ["unspecified side-products"]

            # 4. Impurity Risk & Purification Burden
            if selectivity < 85.0 or (reversible and difficulty == "high"):
                impurity_risk = "high"
                purification_burden = "high"
                impurity_score = 3
            elif selectivity < 95.0 or reversible:
                impurity_risk = "medium"
                purification_burden = "medium"
                impurity_score = 2
            else:
                impurity_risk = "low"
                purification_burden = "low"
                impurity_score = 1
                
            max_impurity_risk_score = max(max_impurity_risk_score, impurity_score)

            # 5. Calculate Effective Yield
            # Yield is multiplied by selectivity, then equilibrium penalty is subtracted
            effective_yield = (original_yield * (selectivity / 100.0)) - equilibrium_penalty
            effective_yield = max(0.0, round(effective_yield, 2))

            # Store results on the step
            step["byproduct_analysis"] = {
                "main_product_selectivity_percent": selectivity,
                "reversible": reversible,
                "equilibrium_penalty_percent": equilibrium_penalty,
                "byproducts": step_byproducts,
                "impurity_risk": impurity_risk,
                "purification_burden": purification_burden,
                "original_yield": original_yield,
                "effective_yield": effective_yield
            }
            
            # Accumulate penalties (scale 0-100 where higher means worse)
            total_selectivity_penalty += (100.0 - selectivity)
            total_reversibility_penalty += equilibrium_penalty
            total_byproduct_penalty += (len(step_byproducts) * 2.0)  # arbitrary minor penalty per byproduct type

            # Update the step's primary yield field so subsequent engines (like cost) use the effective yield
            step["scale_adjusted_yield"] = effective_yield

            # Pharma mode rules
            if pharma_mode:
                if impurity_risk == "high":
                    rejection_reasons.append(f"High impurity risk in step: {rxn_type}")
                    overall_status = "rejected"
                if selectivity < 90.0:
                    ard_flags.append(f"Low selectivity ({selectivity}%) in step: {rxn_type}")
                    if overall_status != "rejected":
                        overall_status = "ard_required"

        # Route level aggregation
        num_steps = len(steps) if steps else 1
        avg_selectivity_penalty = total_selectivity_penalty / num_steps
        avg_reversibility_penalty = total_reversibility_penalty / num_steps
        
        route_impurity_risk = reverse_risk_map.get(max_impurity_risk_score, "low")
        impurity_risk_penalty = (max_impurity_risk_score - 1) * 10.0  # 0, 10, or 20

        # Update route overall yield based on the new step yields
        new_overall_yield = 100.0
        for step in steps:
            y = step.get("scale_adjusted_yield", 100.0)
            new_overall_yield *= (y / 100.0)
        route_dict["scale_adjusted_overall_yield"] = round(new_overall_yield, 2)

        route_dict["byproduct_analysis"] = {
            "byproduct_penalty": round(total_byproduct_penalty, 2),
            "selectivity_penalty": round(avg_selectivity_penalty, 2),
            "reversibility_penalty": round(avg_reversibility_penalty, 2),
            "impurity_risk_penalty": round(impurity_risk_penalty, 2),
            "overall_impurity_risk": route_impurity_risk,
            "pharma_status": overall_status,
            "rejection_reasons": rejection_reasons,
            "ard_flags": ard_flags
        }

        # Embed pharma mode decisions so IndustrialAcceptabilityEngine can see them
        if pharma_mode:
            # We can use the existing extra_flags or constraints list
            if overall_status == "rejected":
                route_dict["equipment_rejected"] = True  # Force rejection in later stages if needed, or rely on industrial engine reading this
                # A cleaner way is to inject a high constraint penalty
                route_dict["constraint_penalty"] = route_dict.get("constraint_penalty", 0.0) + 50.0

        return route_dict
