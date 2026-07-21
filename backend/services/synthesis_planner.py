from typing import List, Dict, Any, Optional
import logging
from models.chemistry import (
    MolecularStructure, 
    ReactionStep, 
    SynthesisRoute, 
    ReactionCondition
)
from services.molecular_service import MolecularService
from models import get_yield_predictor

logger = logging.getLogger(__name__)

class SynthesisPlanner:
    """Service for planning synthesis routes."""
    
    def __init__(self):
        self.molecular_service = MolecularService()
        self.yield_predictor = get_yield_predictor()
        # Common reaction types and their typical yields
        self.reaction_patterns = {
            "suzuki": {"yield": 85, "difficulty": "moderate", "cost_factor": 1.2},
            "wittig": {"yield": 80, "difficulty": "moderate", "cost_factor": 1.1},
            "grignard": {"yield": 75, "difficulty": "high", "cost_factor": 1.3},
            "sn2": {"yield": 90, "difficulty": "easy", "cost_factor": 0.9},
            "aldol": {"yield": 70, "difficulty": "moderate", "cost_factor": 1.0},
            "diels-alder": {"yield": 85, "difficulty": "easy", "cost_factor": 0.8},
            "esterification": {"yield": 88, "difficulty": "easy", "cost_factor": 0.7},
            "amidation": {"yield": 85, "difficulty": "easy", "cost_factor": 0.9},
            "reduction": {"yield": 90, "difficulty": "easy", "cost_factor": 0.8},
            "oxidation": {"yield": 85, "difficulty": "moderate", "cost_factor": 1.0},
        }
    
    def calculate_route_score(
        self, 
        overall_yield: float, 
        total_cost: float, 
        num_steps: int,
        optimize_for: str = "balanced"
    ) -> float:
        """Calculate multi-objective score for a synthesis route."""
        
        # Normalize factors (0-100 scale)
        yield_score = overall_yield  # Already 0-100
        cost_score = max(0, 100 - (total_cost / 10))  # Lower cost = higher score
        step_score = max(0, 100 - (num_steps * 15))  # Fewer steps = higher score
        
        # Weight based on optimization goal
        if optimize_for == "yield":
            weights = {"yield": 0.7, "cost": 0.15, "steps": 0.15}
        elif optimize_for == "cost":
            weights = {"yield": 0.15, "cost": 0.7, "steps": 0.15}
        elif optimize_for == "time":
            weights = {"yield": 0.2, "cost": 0.2, "steps": 0.6}
        else:  # balanced
            weights = {"yield": 0.4, "cost": 0.3, "steps": 0.3}
        
        score = (
            yield_score * weights["yield"] +
            cost_score * weights["cost"] +
            step_score * weights["steps"]
        )
        
        return round(score, 2)
    
    def build_synthesis_routes(
        self,
        target_smiles: str,
        claude_response: Dict[str, Any],
        optimize_for: str = "balanced"
    ) -> List[SynthesisRoute]:
        """Build SynthesisRoute objects from Claude's response."""
        
        routes = []
        
        if "routes" not in claude_response:
            logger.error("No routes found in Claude response")
            return routes
        
        # Parse target molecule
        target_data = self.molecular_service.parse_smiles(target_smiles)
        if not target_data.get("valid"):
            logger.error(f"Invalid target SMILES: {target_smiles}")
            return routes
        
        target_mol = MolecularStructure(
            smiles=target_smiles,
            molecular_weight=target_data.get("molecular_weight"),
            properties=target_data
        )
        
        for route_data in claude_response["routes"]:
            try:
                # Parse starting materials
                starting_materials = []
                for sm_entry in route_data.get("starting_materials", []):
                    # Robust SMILES extraction
                    sm_smiles = sm_entry.get('smiles', sm_entry) if isinstance(sm_entry, dict) else sm_entry
                    sm_data = self.molecular_service.parse_smiles(sm_smiles)
                    if sm_data.get("valid"):
                        starting_materials.append(
                            MolecularStructure(
                                smiles=str(sm_smiles),
                                molecular_weight=sm_data.get("molecular_weight"),
                                properties=sm_data
                            )
                        )
                
                # Parse reaction steps
                steps = []
                total_cost = 0.0
                total_time = 0.0
                
                for step_data in route_data.get("steps", []):
                    # Parse reactants
                    reactants = []
                    for r_entry in step_data.get("reactants", []):
                        r_smiles = r_entry.get('smiles', r_entry) if isinstance(r_entry, dict) else r_entry
                        r_data = self.molecular_service.parse_smiles(r_smiles)
                        if r_data.get("valid"):
                            reactants.append(
                                MolecularStructure(
                                    smiles=str(r_smiles),
                                    molecular_weight=r_data.get("molecular_weight"),
                                    properties=r_data
                                )
                            )
                    
                    # Parse product
                    p_entry = step_data.get("product", "")
                    p_smiles = p_entry.get('smiles', p_entry) if isinstance(p_entry, dict) else p_entry
                    p_data = self.molecular_service.parse_smiles(p_smiles)
                    if not p_data.get("valid"):
                        continue
                    
                    product = MolecularStructure(
                        smiles=str(p_smiles),
                        molecular_weight=p_data.get("molecular_weight"),
                        properties=p_data
                    )
                    
                    # Parse conditions
                    conditions_data = step_data.get("conditions", {})
                    conditions = ReactionCondition(
                        temperature_celsius=conditions_data.get("temperature_celsius"),
                        pressure_atm=conditions_data.get("pressure_atm", 1.0),
                        solvent=conditions_data.get("solvent"),
                        catalyst=conditions_data.get("catalyst"),
                        time_hours=conditions_data.get("time_hours", 4.0),
                        solvent_volume_ml=conditions_data.get("solvent_volume_ml"),
                        concentration_m=conditions_data.get("concentration_m") or step_data.get("concentration_m"),
                        catalyst_loading_mol_percent=conditions_data.get("catalyst_loading_mol_percent"),
                        additional_conditions={
                            key: value
                            for key, value in conditions_data.items()
                            if key not in {
                                "temperature_celsius",
                                "pressure_atm",
                                "solvent",
                                "catalyst",
                                "time_hours",
                                "solvent_volume_ml",
                                "concentration_m",
                                "catalyst_loading_mol_percent",
                            }
                        } or None,
                    )
                    
                    # Get reaction info
                    reaction_type = step_data.get("reaction_type", "unknown").lower()
                    
                    # Phase 3: Use ML for yield prediction if available
                    estimated_yield = step_data.get("estimated_yield")
                    if estimated_yield is None:
                        estimated_yield = step_data.get("estimated_yield_percent")
                    if estimated_yield is None:
                        try:
                            # Standard format for predictor
                            rxn_dict = {
                                "reactants": [r.smiles for r in reactants],
                                "products": [product.smiles],
                                "reaction_type": reaction_type
                            }
                            prediction = self.yield_predictor.predict(rxn_dict)
                            estimated_yield = prediction if prediction is not None else 75.0
                        except Exception:
                            estimated_yield = 75.0
                    try:
                        estimated_yield = float(estimated_yield)
                        if 0 < estimated_yield <= 1:
                            estimated_yield *= 100
                    except (TypeError, ValueError):
                        estimated_yield = 75.0
                            
                    estimated_cost = step_data.get("estimated_cost_usd", 100.0)
                    sanity_flags = self._sanity_flags(
                        step_data=step_data,
                        conditions_data=conditions_data,
                        estimated_yield=estimated_yield,
                        estimated_cost=estimated_cost,
                    )
                    
                    # Get difficulty from pattern database
                    difficulty = "moderate"
                    for pattern_name, pattern_info in self.reaction_patterns.items():
                        if pattern_name in reaction_type:
                            difficulty = pattern_info["difficulty"]
                            break
                    
                    step = ReactionStep(
                        reactants=reactants,
                        product=product,
                        reaction_type=reaction_type,
                        conditions=conditions,
                        estimated_yield_percent=estimated_yield,
                        estimated_cost_usd=estimated_cost,
                        difficulty=difficulty,
                        notes=step_data.get("notes"),
                        reactant_quantities=step_data.get("reactant_quantities"),
                        catalyst_loading=step_data.get("catalyst_loading"),
                        solvent_amount=step_data.get("solvent_amount"),
                        concentration_m=step_data.get("concentration_m") or conditions.concentration_m,
                        batch_scale=step_data.get("batch_scale"),
                        cost_drivers=step_data.get("cost_drivers"),
                        feasibility_notes=step_data.get("feasibility_notes"),
                        sanity_flags=sanity_flags,
                        safety_warnings=step_data.get("safety_flags"),
                    )
                    
                    steps.append(step)
                    total_cost += estimated_cost
                    total_time += conditions.time_hours or 4.0
                
                if not steps:
                    continue
                
                # Calculate overall yield
                overall_yield = route_data.get(
                    "overall_yield",
                    route_data.get("overall_yield_percent", 50.0)
                )
                try:
                    overall_yield = float(overall_yield)
                    if 0 < overall_yield <= 1:
                        overall_yield *= 100
                except (TypeError, ValueError):
                    overall_yield = 50.0
                
                # Calculate score
                score = self.calculate_route_score(
                    overall_yield=overall_yield,
                    total_cost=total_cost,
                    num_steps=len(steps),
                    optimize_for=optimize_for
                )
                
                improvement_targets = []
                final_product = steps[-1].product.properties.get("canonical_smiles") if steps[-1].product.properties else steps[-1].product.smiles
                target_canonical = target_mol.properties.get("canonical_smiles") if target_mol.properties else target_mol.smiles
                if final_product and target_canonical and final_product != target_canonical:
                    improvement_targets.append(
                        "Final step product does not match target canonical SMILES; route needs chemistry review."
                    )
                low_yield_steps = [
                    f"Step {idx + 1} yield {step.estimated_yield_percent:.1f}%"
                    for idx, step in enumerate(steps)
                    if step.estimated_yield_percent < 40
                ]
                if low_yield_steps:
                    improvement_targets.append("Low-yield bottleneck: " + "; ".join(low_yield_steps[:3]))

                route_cost_drivers = []
                for step in steps:
                    for driver in step.cost_drivers or []:
                        if driver not in route_cost_drivers:
                            route_cost_drivers.append(driver)

                # Create route
                route = SynthesisRoute(
                    target_molecule=target_mol,
                    starting_materials=starting_materials,
                    steps=steps,
                    overall_yield_percent=overall_yield,
                    total_cost_usd=total_cost,
                    total_time_hours=total_time,
                    score=score,
                    notes=route_data.get("notes"),
                    batch_size_kg=route_data.get("batch_size_kg"),
                    scale=route_data.get("batch_scale"),
                    improvement_targets=improvement_targets or route_data.get("feasibility_notes"),
                )
                route.llm_metadata = {
                    "batch_scale": route_data.get("batch_scale"),
                    "cost_drivers": route_data.get("cost_drivers") or route_cost_drivers,
                    "feasibility_notes": route_data.get("feasibility_notes"),
                }
                
                routes.append(route)
                logger.info(f"Successfully built route with {len(steps)} steps")
                
            except Exception as e:
                logger.error(f"Error building route: {str(e)}", exc_info=True)
                continue
        
        # Sort routes by score (highest first)
        routes.sort(key=lambda r: r.score, reverse=True)
        
        return routes

    def _sanity_flags(
        self,
        step_data: Dict[str, Any],
        conditions_data: Dict[str, Any],
        estimated_yield: float,
        estimated_cost: float,
    ) -> List[str]:
        flags: List[str] = []
        reaction_type = str(step_data.get("reaction_type") or "").lower()
        notes = str(step_data.get("notes") or "").lower()
        catalyst = str(conditions_data.get("catalyst") or "").lower()
        solvent = str(conditions_data.get("solvent") or "").lower()

        if estimated_yield < 5:
            flags.append("Yield estimate is near-zero; route is likely not useful without redesign.")
        elif estimated_yield < 40:
            flags.append("Low step yield; screen conditions before spending on scale-up.")
        elif estimated_yield > 98:
            flags.append("Very high yield estimate; verify with literature or experiment.")

        if estimated_cost > 1000:
            flags.append("Step cost is unusually high for planning scale.")

        if "suzuki" in reaction_type:
            if "pd" not in catalyst:
                flags.append("Suzuki route should specify a Pd source and ligand.")
            if not any(base in notes for base in ["k2co3", "cs2co3", "na2co3", "base"]):
                flags.append("Suzuki route should specify a base.")

        if solvent in {"benzene", "chloroform"}:
            flags.append("Solvent is poor for green/process chemistry; prefer alternatives if possible.")

        return flags
