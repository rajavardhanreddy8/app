"""
Route Optimization Layer

Implements:
1. Route Mutation: Catalyst swapping, solvent optimization, temperature tuning
2. Constraint Feedback Loop: Auto-fix based on constraint analysis
3. Confidence Scoring: Reliability and risk metrics
4. Equipment Binding: Hard constraints based on equipment availability
"""

import logging
import copy
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ============ SOLVENT & CATALYST DATABASES ============

SOLVENT_ALTERNATIVES = {
    # Greener/cheaper alternatives for common solvents
    "THF": ["2-MeTHF", "EtOAc", "acetone"],
    "DCM": ["EtOAc", "CPME", "2-MeTHF"],
    "DMF": ["DMAc", "NMP", "DMSO"],
    "toluene": ["anisole", "CPME", "heptane"],
    "diethyl_ether": ["MTBE", "CPME", "2-MeTHF"],
    "chloroform": ["DCM", "EtOAc", "2-MeTHF"],
    "DMSO": ["NMP", "sulfolane", "DMAc"],
    "MeOH": ["EtOH", "iPrOH", "BuOH"],
    "EtOH": ["MeOH", "iPrOH", "BuOH"],
    "acetonitrile": ["acetone", "EtOAc", "MeOH"],
    "hexane": ["heptane", "petroleum_ether", "MTBE"],
    "benzene": ["toluene", "anisole", "xylene"],
    "None": ["EtOH", "water", "acetone"],
}

SOLVENT_PROPERTIES = {
    "THF": {"bp_c": 66, "green_score": 3, "cost_per_L": 25},
    "2-MeTHF": {"bp_c": 80, "green_score": 7, "cost_per_L": 45},
    "EtOAc": {"bp_c": 77, "green_score": 6, "cost_per_L": 15},
    "acetone": {"bp_c": 56, "green_score": 7, "cost_per_L": 10},
    "DCM": {"bp_c": 40, "green_score": 1, "cost_per_L": 18},
    "CPME": {"bp_c": 106, "green_score": 8, "cost_per_L": 55},
    "DMF": {"bp_c": 153, "green_score": 2, "cost_per_L": 20},
    "DMAc": {"bp_c": 165, "green_score": 3, "cost_per_L": 30},
    "NMP": {"bp_c": 202, "green_score": 3, "cost_per_L": 35},
    "DMSO": {"bp_c": 189, "green_score": 5, "cost_per_L": 22},
    "toluene": {"bp_c": 111, "green_score": 4, "cost_per_L": 12},
    "anisole": {"bp_c": 154, "green_score": 7, "cost_per_L": 40},
    "heptane": {"bp_c": 98, "green_score": 5, "cost_per_L": 15},
    "MeOH": {"bp_c": 65, "green_score": 6, "cost_per_L": 8},
    "EtOH": {"bp_c": 78, "green_score": 8, "cost_per_L": 10},
    "iPrOH": {"bp_c": 82, "green_score": 7, "cost_per_L": 12},
    "water": {"bp_c": 100, "green_score": 10, "cost_per_L": 0.5},
    "acetonitrile": {"bp_c": 82, "green_score": 4, "cost_per_L": 30},
}

CATALYST_ALTERNATIVES = {
    "Pd(PPh3)4": ["Pd/C", "Pd(OAc)2", "PdCl2(dppf)"],
    "Pd/C": ["Pd(OAc)2", "Raney_Ni", "Pt/C"],
    "H2SO4": ["p-TsOH", "Amberlyst-15", "H3PO4"],
    "NaOH": ["KOH", "K2CO3", "NaHCO3"],
    "NaBH4": ["LiAlH4", "DIBAL-H", "NaCNBH3"],
    "LiAlH4": ["NaBH4", "DIBAL-H", "Red-Al"],
    "AlCl3": ["BF3.Et2O", "FeCl3", "SnCl4"],
    "BuLi": ["LDA", "NaH", "KHMDS"],
    "None": ["H2SO4", "p-TsOH", "Amberlyst-15"],
}

CATALYST_PROPERTIES = {
    "Pd(PPh3)4": {"cost_per_g": 45, "recyclable": False, "toxicity": "medium"},
    "Pd/C": {"cost_per_g": 35, "recyclable": True, "toxicity": "low"},
    "Pd(OAc)2": {"cost_per_g": 40, "recyclable": False, "toxicity": "medium"},
    "Raney_Ni": {"cost_per_g": 5, "recyclable": True, "toxicity": "low"},
    "H2SO4": {"cost_per_g": 0.5, "recyclable": False, "toxicity": "high"},
    "p-TsOH": {"cost_per_g": 3, "recyclable": False, "toxicity": "low"},
    "Amberlyst-15": {"cost_per_g": 8, "recyclable": True, "toxicity": "low"},
    "NaOH": {"cost_per_g": 0.3, "recyclable": False, "toxicity": "medium"},
    "K2CO3": {"cost_per_g": 0.5, "recyclable": False, "toxicity": "low"},
    "NaBH4": {"cost_per_g": 12, "recyclable": False, "toxicity": "medium"},
    "AlCl3": {"cost_per_g": 2, "recyclable": False, "toxicity": "medium"},
    "BF3.Et2O": {"cost_per_g": 15, "recyclable": False, "toxicity": "high"},
    "None": {"cost_per_g": 0, "recyclable": True, "toxicity": "none"},
}


@dataclass
class MutationResult:
    """Result of applying a mutation to a route step."""
    mutation_type: str  # "catalyst_swap", "solvent_optimization", "temperature_tune"
    original_value: str
    new_value: str
    improvement_reason: str
    estimated_impact: Dict  # {"yield_change": float, "cost_change": float, "green_improvement": float}


@dataclass
class ConfidenceScore:
    """Route confidence and risk assessment."""
    overall_confidence: float  # 0-100
    yield_confidence: float
    cost_confidence: float
    safety_confidence: float
    equipment_feasibility: float
    risk_level: str  # "low", "medium", "high", "critical"
    risk_factors: List[str]
    reliability_breakdown: Dict


@dataclass
class ConstraintFeedback:
    """Feedback from constraint analysis with auto-fix suggestions."""
    original_constraints: Dict
    applied_fixes: List[Dict]
    improved_constraints: Dict
    improvement_summary: str


class RouteOptimizer:
    """
    Optimization layer for synthesis routes.
    
    Provides mutation, constraint feedback, confidence scoring,
    and equipment binding capabilities.
    """
    
    def __init__(self, constraints_engine=None, equipment_recommender=None):
        self.constraints_engine = constraints_engine
        self.equipment_recommender = equipment_recommender
        
        # Mutation parameters
        self.temperature_step = 10  # °C per tuning step
        self.max_temperature_mutations = 3
        
        # Caching
        self._constraint_cache = {}
        self._equipment_cache = {}
    
    # ============ 1. ROUTE MUTATION ============
    
    def mutate_route(self, route: Dict, mutation_types: List[str] = None) -> Dict:
        """
        Apply mutations to optimize a route.
        
        Args:
            route: Route dict with steps
            mutation_types: List of mutations to apply. 
                Options: ["catalyst_swap", "solvent_optimization", "temperature_tune", "all"]
        
        Returns:
            Mutated route with improvements tracked
        """
        if mutation_types is None or "all" in (mutation_types or []):
            mutation_types = ["catalyst_swap", "solvent_optimization", "temperature_tune"]
        
        mutated_route = copy.deepcopy(route)
        mutations_applied = []
        
        steps = mutated_route.get('steps', [])
        if not steps:
            # Try to mutate the route-level reaction data
            if 'reaction_type' in mutated_route or 'catalyst' in mutated_route:
                steps = [mutated_route]
        
        for step_idx, step in enumerate(steps):
            conditions = step.get('conditions', step)
            
            if "catalyst_swap" in mutation_types:
                mutation = self._mutate_catalyst(conditions, step_idx)
                if mutation:
                    mutations_applied.append(mutation)
            
            if "solvent_optimization" in mutation_types:
                mutation = self._mutate_solvent(conditions, step_idx)
                if mutation:
                    mutations_applied.append(mutation)
            
            if "temperature_tune" in mutation_types:
                mutation = self._mutate_temperature(conditions, step_idx)
                if mutation:
                    mutations_applied.append(mutation)
        
        mutated_route['mutations_applied'] = [
            {
                'type': m.mutation_type,
                'original': m.original_value,
                'new': m.new_value,
                'reason': m.improvement_reason,
                'impact': m.estimated_impact
            }
            for m in mutations_applied
        ]
        mutated_route['mutation_count'] = len(mutations_applied)
        
        return mutated_route
    
    def _mutate_catalyst(self, conditions: Dict, step_idx: int) -> Optional[MutationResult]:
        """Swap catalyst for cheaper/greener/more efficient alternative."""
        current_cat = conditions.get('catalyst', 'None')
        
        alternatives = CATALYST_ALTERNATIVES.get(current_cat, [])
        if not alternatives:
            return None
        
        current_props = CATALYST_PROPERTIES.get(current_cat, {"cost_per_g": 10, "recyclable": False})
        
        # Find best alternative (cheapest recyclable option)
        best_alt = None
        best_score = 0
        
        for alt in alternatives:
            alt_props = CATALYST_PROPERTIES.get(alt, {"cost_per_g": 10, "recyclable": False})
            score = 0
            
            # Prefer cheaper
            if alt_props['cost_per_g'] < current_props['cost_per_g']:
                score += 3
            
            # Prefer recyclable
            if alt_props.get('recyclable', False):
                score += 2
            
            # Prefer lower toxicity
            tox_scores = {"none": 4, "low": 3, "medium": 1, "high": 0}
            score += tox_scores.get(alt_props.get('toxicity', 'medium'), 1)
            
            if score > best_score:
                best_score = score
                best_alt = alt
        
        if best_alt and best_alt != current_cat:
            alt_props = CATALYST_PROPERTIES.get(best_alt, {})
            cost_saving = current_props['cost_per_g'] - alt_props.get('cost_per_g', 10)
            
            conditions['catalyst'] = best_alt
            
            return MutationResult(
                mutation_type=f"catalyst_swap_step_{step_idx}",
                original_value=current_cat,
                new_value=best_alt,
                improvement_reason=f"Lower cost (${cost_saving:.1f}/g saving), {'recyclable' if alt_props.get('recyclable') else 'better safety'}",
                estimated_impact={
                    "cost_change_per_g": -cost_saving,
                    "yield_change": -2.0,  # Small yield penalty for untested catalyst
                    "green_improvement": 1 if alt_props.get('recyclable') else 0
                }
            )
        
        return None
    
    def _mutate_solvent(self, conditions: Dict, step_idx: int) -> Optional[MutationResult]:
        """Optimize solvent for greener/cheaper alternative."""
        current_solv = conditions.get('solvent', 'None')
        
        alternatives = SOLVENT_ALTERNATIVES.get(current_solv, [])
        if not alternatives:
            return None
        
        current_props = SOLVENT_PROPERTIES.get(current_solv, {"green_score": 5, "cost_per_L": 20, "bp_c": 100})
        temp = conditions.get('temperature_celsius', conditions.get('temperature_c', 25))
        
        best_alt = None
        best_score = 0
        
        for alt in alternatives:
            alt_props = SOLVENT_PROPERTIES.get(alt, {"green_score": 5, "cost_per_L": 20, "bp_c": 100})
            score = 0
            
            # Green score improvement
            if alt_props['green_score'] > current_props.get('green_score', 5):
                score += (alt_props['green_score'] - current_props.get('green_score', 5))
            
            # Cost improvement
            if alt_props['cost_per_L'] < current_props.get('cost_per_L', 20):
                score += 2
            
            # Must be compatible with temperature (bp > reaction temp + 10°C margin)
            if alt_props['bp_c'] < (temp + 10):
                score -= 10  # Big penalty for boiling point issue
            
            if score > best_score:
                best_score = score
                best_alt = alt
        
        if best_alt and best_score > 0:
            alt_props = SOLVENT_PROPERTIES.get(best_alt, {})
            green_improvement = alt_props.get('green_score', 5) - current_props.get('green_score', 5)
            
            conditions['solvent'] = best_alt
            
            return MutationResult(
                mutation_type=f"solvent_optimization_step_{step_idx}",
                original_value=current_solv,
                new_value=best_alt,
                improvement_reason=f"Greener (score {current_props.get('green_score', '?')}→{alt_props.get('green_score', '?')}), compatible with {temp}°C",
                estimated_impact={
                    "cost_change_per_L": alt_props.get('cost_per_L', 20) - current_props.get('cost_per_L', 20),
                    "yield_change": -1.0,  # Small yield uncertainty
                    "green_improvement": green_improvement
                }
            )
        
        return None
    
    def _mutate_temperature(self, conditions: Dict, step_idx: int) -> Optional[MutationResult]:
        """Tune temperature for better yield/safety balance."""
        temp_key = 'temperature_celsius' if 'temperature_celsius' in conditions else 'temperature_c'
        current_temp = conditions.get(temp_key, 25)
        
        if current_temp is None:
            return None
        
        # Evaluate if temperature should be lowered (safety) or raised (yield)
        optimal_temp = current_temp
        reason = ""
        
        # High temperature → suggest lowering for safety
        if current_temp > 150:
            optimal_temp = current_temp - self.temperature_step * 2
            reason = f"Reduced from {current_temp}°C for improved safety margin"
        elif current_temp > 100:
            optimal_temp = current_temp - self.temperature_step
            reason = f"Reduced from {current_temp}°C for better selectivity"
        # Low temperature → suggest slight increase for faster kinetics
        elif current_temp < 0:
            optimal_temp = current_temp + self.temperature_step
            reason = f"Increased from {current_temp}°C for faster kinetics"
        else:
            return None  # Temperature is in reasonable range
        
        if optimal_temp != current_temp:
            conditions[temp_key] = optimal_temp
            
            return MutationResult(
                mutation_type=f"temperature_tune_step_{step_idx}",
                original_value=f"{current_temp}°C",
                new_value=f"{optimal_temp}°C",
                improvement_reason=reason,
                estimated_impact={
                    "temperature_change": optimal_temp - current_temp,
                    "yield_change": 1.0 if optimal_temp > current_temp else -1.5,
                    "safety_improvement": 1 if optimal_temp < current_temp else -1
                }
            )
        
        return None
    
    # ============ 2. CONSTRAINT FEEDBACK LOOP ============
    
    def apply_constraint_feedback(self, reaction: Dict, scale: str = "lab", batch_size_kg: float = 0.1) -> ConstraintFeedback:
        """
        Evaluate constraints and auto-fix issues.
        
        Args:
            reaction: Reaction dict
            scale: Production scale
            batch_size_kg: Batch size
            
        Returns:
            ConstraintFeedback with fixes applied
        """
        if not self.constraints_engine:
            return ConstraintFeedback(
                original_constraints={},
                applied_fixes=[],
                improved_constraints={},
                improvement_summary="No constraints engine available"
            )
        
        # Evaluate original constraints
        try:
            original = self.constraints_engine.evaluate_reaction_constraints(
                reaction=reaction, scale=scale, batch_size_kg=batch_size_kg
            )
        except Exception as e:
            logger.error(f"constraint_evaluation_failed: {e}")
            return ConstraintFeedback(
                original_constraints={},
                applied_fixes=[],
                improved_constraints={},
                improvement_summary=f"Evaluation failed: {str(e)}"
            )
        
        original_dict = {
            'heat_risk': original.heat_risk,
            'heat_score': original.heat_score,
            'mixing_efficiency': original.mixing_efficiency,
            'mixing_score': original.mixing_score,
            'safety_risk': original.safety_risk,
            'safety_score': original.safety_score,
            'total_penalty': original.total_penalty,
        }
        
        # Apply feedback fixes
        fixed_reaction = copy.deepcopy(reaction)
        fixes = []
        
        # Fix 1: High heat risk → reduce temperature
        if original.heat_risk in ("high", "critical"):
            old_temp = fixed_reaction.get('temperature_celsius', 25)
            new_temp = max(old_temp - 20, 0)
            fixed_reaction['temperature_celsius'] = new_temp
            fixes.append({
                'issue': f'heat_risk={original.heat_risk}',
                'fix': f'Reduced temperature {old_temp}°C → {new_temp}°C',
                'parameter': 'temperature_celsius',
                'old_value': old_temp,
                'new_value': new_temp
            })
        
        # Fix 2: Mixing issues → change solvent
        if original.mixing_efficiency in ("poor", "very_poor"):
            old_solvent = fixed_reaction.get('solvent', 'None')
            # Find a better-mixing solvent (lower viscosity / better solvation)
            better_solvents = {
                "None": "THF",
                "water": "MeOH",
                "hexane": "THF",
                "toluene": "DCM",
            }
            new_solvent = better_solvents.get(old_solvent, "THF")
            fixed_reaction['solvent'] = new_solvent
            fixes.append({
                'issue': f'mixing_efficiency={original.mixing_efficiency}',
                'fix': f'Changed solvent {old_solvent} → {new_solvent} for better mixing',
                'parameter': 'solvent',
                'old_value': old_solvent,
                'new_value': new_solvent
            })
        
        # Fix 3: Safety risk → reduce scale or add safety measures
        if original.safety_risk in ("high", "critical"):
            if batch_size_kg > 1.0:
                new_batch = batch_size_kg / 2
                fixes.append({
                    'issue': f'safety_risk={original.safety_risk}',
                    'fix': f'Recommend reducing batch size {batch_size_kg}kg → {new_batch}kg',
                    'parameter': 'batch_size_kg',
                    'old_value': batch_size_kg,
                    'new_value': new_batch
                })
            else:
                fixes.append({
                    'issue': f'safety_risk={original.safety_risk}',
                    'fix': 'Recommend adding blast shield and inert atmosphere',
                    'parameter': 'safety_equipment',
                    'old_value': 'none',
                    'new_value': 'blast_shield,inert_atmosphere'
                })
        
        # Fix 4: High purification difficulty → suggest column chromatography
        if original.purification_difficulty in ("difficult", "very_difficult"):
            fixes.append({
                'issue': f'purification={original.purification_difficulty}',
                'fix': 'Add recrystallization step or switch to column chromatography',
                'parameter': 'purification_method',
                'old_value': 'standard',
                'new_value': 'column_chromatography'
            })
        
        # Re-evaluate improved constraints
        try:
            improved = self.constraints_engine.evaluate_reaction_constraints(
                reaction=fixed_reaction, scale=scale, batch_size_kg=batch_size_kg
            )
            improved_dict = {
                'heat_risk': improved.heat_risk,
                'heat_score': improved.heat_score,
                'mixing_efficiency': improved.mixing_efficiency,
                'mixing_score': improved.mixing_score,
                'safety_risk': improved.safety_risk,
                'safety_score': improved.safety_score,
                'total_penalty': improved.total_penalty,
            }
        except Exception:
            improved_dict = original_dict
        
        penalty_improvement = original_dict['total_penalty'] - improved_dict.get('total_penalty', original_dict['total_penalty'])
        
        return ConstraintFeedback(
            original_constraints=original_dict,
            applied_fixes=fixes,
            improved_constraints=improved_dict,
            improvement_summary=f"Applied {len(fixes)} fixes, penalty reduced by {penalty_improvement:.1f} points"
        )
    
    # ============ 3. CONFIDENCE SCORING ============
    
    def calculate_confidence(self, route: Dict, mcts_visits: int = 0) -> ConfidenceScore:
        """
        Calculate confidence/reliability score for a route.
        
        Args:
            route: Route dict with steps and metrics
            mcts_visits: Number of MCTS visits (higher = more explored)
            
        Returns:
            ConfidenceScore with detailed breakdown
        """
        risk_factors = []
        
        # 1. Yield confidence (based on overall yield and step count)
        overall_yield = route.get('overall_yield_percent', route.get('estimated_yield', 50.0))
        num_steps = route.get('num_steps', len(route.get('steps', [])))
        
        yield_confidence = min(100, overall_yield * 1.2)
        if num_steps > 5:
            yield_confidence *= 0.8
            risk_factors.append(f"Long route ({num_steps} steps) reduces yield reliability")
        if overall_yield < 30:
            risk_factors.append(f"Very low predicted yield ({overall_yield:.1f}%)")
        
        # 2. Cost confidence (lower cost variance = higher confidence)
        total_cost = route.get('total_cost_usd', 100)
        cost_confidence = max(0, 100 - total_cost / 10)
        if total_cost > 500:
            risk_factors.append(f"High estimated cost (${total_cost:.0f})")
        
        # 3. Safety confidence (from constraint analysis)
        safety_confidence = 80.0  # Default
        if self.constraints_engine:
            steps = route.get('steps', [])
            if steps:
                try:
                    # Evaluate first step as representative
                    step = steps[0] if isinstance(steps[0], dict) else {}
                    reaction_data = step.get('conditions', step)
                    if reaction_data:
                        constraints = self.constraints_engine.evaluate_reaction_constraints(
                            reaction=reaction_data, scale='lab', batch_size_kg=0.1
                        )
                        safety_confidence = max(0, 100 - constraints.safety_score)
                        if constraints.safety_risk in ("high", "critical"):
                            risk_factors.append(f"Safety concern: {constraints.safety_risk}")
                except Exception:
                    pass
        
        # 4. Equipment feasibility
        equipment_feasibility = 85.0  # Default
        if self.equipment_recommender:
            steps = route.get('steps', [])
            for step in steps:
                rxn_type = step.get('reaction_type', 'unknown') if isinstance(step, dict) else 'unknown'
                temp = step.get('conditions', {}).get('temperature_celsius', 25) if isinstance(step, dict) else 25
                
                if temp > 250:
                    equipment_feasibility -= 20
                    risk_factors.append(f"Extreme temperature ({temp}°C) may need specialized equipment")
                if rxn_type in ('photochemistry', 'electrochemistry'):
                    equipment_feasibility -= 10
                    risk_factors.append(f"Specialized equipment needed for {rxn_type}")
        
        # 5. MCTS exploration confidence
        exploration_bonus = min(20, mcts_visits / 5) if mcts_visits > 0 else 0
        
        # Overall confidence
        overall = (
            0.30 * yield_confidence +
            0.20 * cost_confidence +
            0.25 * safety_confidence +
            0.15 * equipment_feasibility +
            0.10 * (50 + exploration_bonus)  # Base + exploration
        )
        overall = max(0, min(100, overall))
        
        # Risk level
        if overall >= 75:
            risk_level = "low"
        elif overall >= 50:
            risk_level = "medium"
        elif overall >= 25:
            risk_level = "high"
        else:
            risk_level = "critical"
        
        return ConfidenceScore(
            overall_confidence=round(overall, 1),
            yield_confidence=round(yield_confidence, 1),
            cost_confidence=round(cost_confidence, 1),
            safety_confidence=round(safety_confidence, 1),
            equipment_feasibility=round(equipment_feasibility, 1),
            risk_level=risk_level,
            risk_factors=risk_factors,
            reliability_breakdown={
                "yield_weight": 0.30,
                "cost_weight": 0.20,
                "safety_weight": 0.25,
                "equipment_weight": 0.15,
                "exploration_weight": 0.10,
                "mcts_visits": mcts_visits,
                "exploration_bonus": round(exploration_bonus, 1)
            }
        )
    
    # ============ 4. EQUIPMENT BINDING ============
    
    def check_equipment_feasibility(self, route: Dict) -> Dict:
        """
        Check if route steps can be executed with available equipment.
        
        Args:
            route: Route dict with steps
            
        Returns:
            Equipment feasibility report
        """
        if not self.equipment_recommender:
            return {
                'feasible': True,
                'issues': [],
                'recommendations': [],
                'overall_score': 85.0,
                'note': 'Equipment recommender not available, using defaults'
            }
        
        issues = []
        recommendations = []
        step_results = []
        
        steps = route.get('steps', [])
        for idx, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            
            rxn_type = step.get('reaction_type', 'unknown')
            temp = step.get('conditions', {}).get('temperature_celsius', 25)
            pressure = step.get('conditions', {}).get('pressure_atm', 1)
            
            # Check temperature limits
            if temp > 300:
                issues.append({
                    'step': idx,
                    'issue': 'temperature_exceeds_limit',
                    'detail': f'Step {idx+1}: {temp}°C exceeds standard equipment limit (300°C)',
                    'severity': 'hard_constraint'
                })
            
            # Check pressure limits
            if pressure and pressure > 100:
                issues.append({
                    'step': idx,
                    'issue': 'pressure_exceeds_limit',
                    'detail': f'Step {idx+1}: {pressure} atm exceeds standard equipment (100 atm)',
                    'severity': 'hard_constraint'
                })
            
            # Check for specialized equipment needs
            specialized_reactions = {
                'photochemistry': 'UV reactor required',
                'electrochemistry': 'Electrochemical cell required',
                'microwave': 'Microwave reactor required',
                'flow_chemistry': 'Continuous flow reactor required',
                'high_pressure_hydrogenation': 'Parr reactor required',
                'cryogenic': 'Cryogenic equipment required (-78°C bath)',
            }
            
            for rxn_key, equipment_need in specialized_reactions.items():
                if rxn_key in rxn_type.lower():
                    recommendations.append({
                        'step': idx,
                        'equipment': equipment_need,
                        'reaction_type': rxn_type
                    })
            
            # Get equipment recommendation
            try:
                rec = self.equipment_recommender.recommend_reactor(
                    reaction_type=rxn_type,
                    scale_mg=100,
                    temperature_c=temp,
                    pressure_atm=pressure
                )
                step_results.append({
                    'step': idx,
                    'reactor': rec[0].get('reactor', 'unknown') if rec else 'unknown',
                    'score': rec[0].get('score', 0) if rec else 0
                })
            except Exception:
                step_results.append({
                    'step': idx,
                    'reactor': 'standard',
                    'score': 50
                })
        
        # Determine feasibility
        hard_constraints = [i for i in issues if i.get('severity') == 'hard_constraint']
        feasible = len(hard_constraints) == 0
        
        avg_score = sum(s['score'] for s in step_results) / max(len(step_results), 1)
        # Normalize score to 0-100 range
        if avg_score > 100:
            avg_score = avg_score / 100 * 100  # If scores are in 0-100 already
        overall_score = min(100, avg_score) if feasible else 0
        
        return {
            'feasible': feasible,
            'issues': issues,
            'recommendations': recommendations,
            'step_equipment': step_results,
            'overall_score': round(overall_score, 1),
            'hard_constraints_violated': len(hard_constraints)
        }
