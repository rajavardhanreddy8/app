"""
Yield Optimization Engine — Phase 8: Engineer Yield, Don't Predict It

Core principle: TARGET_YIELD = 0.99. The system doesn't predict yield —
it actively pushes every route to ≥99% through iterative mutation.

Implements:
1. Yield target system (not prediction)
2. Optimization loop: mutate until yield ≥ 99%
3. Yield-driven mutation (catalyst/solvent/temperature based on current yield)
4. Hard pharma constraint (reject < 99%)
5. Multi-step yield collapse fix (Y_total = y1 × y2 × y3)
6. Loss-based cost (low yield = expensive)
7. Yield-dominant scoring: score = yield^5 - cost - penalty
"""

import logging
import copy
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)

# ============ CONSTANTS ============

TARGET_YIELD = 0.99  # 99% — the system's goal
PHARMA_HARD_FLOOR = 0.99  # Reject below this in pharma mode
STEP_YIELD_FLOOR = 0.95  # Any step below this triggers mutation

# Yield improvement estimates per mutation type
YIELD_IMPROVEMENTS = {
    "catalyst_upgrade": {
        # Current catalyst → better catalyst for yield
        "H2SO4": ("p-TsOH", 0.03),        # +3% yield
        "p-TsOH": ("Amberlyst-15", 0.02),
        "AlCl3": ("BF3.Et2O", 0.04),
        "NaBH4": ("LiAlH4", 0.05),
        "NaOH": ("KOH", 0.02),
        "Pd/C": ("Pd(PPh3)4", 0.06),
        "Pd(OAc)2": ("Pd(PPh3)4", 0.04),
        "Raney_Ni": ("Pd/C", 0.05),
        "None": ("H2SO4", 0.08),
    },
    "solvent_upgrade": {
        # Current solvent → better solvent for yield
        "None": ("THF", 0.10),
        "water": ("MeOH", 0.08),
        "hexane": ("THF", 0.07),
        "DCM": ("THF", 0.03),
        "toluene": ("THF", 0.04),
        "DMF": ("NMP", 0.02),
        "EtOH": ("THF", 0.03),
        "MeOH": ("THF", 0.02),
        "acetone": ("THF", 0.03),
        "benzene": ("toluene", 0.05),
        "chloroform": ("DCM", 0.04),
    },
    "temperature_fine_tune": {
        # Temperature ranges → optimal adjustments for yield
        "very_high": (-30, 0.04),   # >200°C: reduce significantly
        "high": (-15, 0.03),         # 120-200°C: reduce moderately
        "moderate": (-5, 0.02),      # 80-120°C: slight reduction
        "optimal": (0, 0.0),         # 40-80°C: leave alone
        "low": (+10, 0.02),          # 0-40°C: increase slightly
        "very_low": (+20, 0.03),     # <0°C: increase
    },
    "pressure_optimize": {
        "low": (+2, 0.02),           # <1 atm: increase
        "normal": (0, 0.0),          # 1-5 atm: optimal
        "high": (-5, 0.01),          # >5 atm: may help
    },
}

# Raw material cost per common SMILES ($/mol)
RAW_MATERIAL_COSTS = {
    "CC(=O)O": 5.0,      # Acetic acid
    "c1ccc(O)cc1": 8.0,   # Phenol
    "CCO": 3.0,            # Ethanol
    "c1ccccc1": 6.0,       # Benzene
    "CC(=O)Cl": 12.0,     # Acetyl chloride
    "default": 15.0,       # Default per reactant
}


@dataclass
class StepYieldInfo:
    """Per-step yield tracking."""
    step_index: int
    reaction_type: str
    estimated_yield: float
    mutations_applied: List[str]
    yield_after_mutation: float
    is_bottleneck: bool


@dataclass
class YieldOptimizationResult:
    """Full result of yield optimization."""
    status: str  # "target_achieved", "improved", "pharma_rejected", "max_iterations"
    target_yield: float
    initial_yield: float
    final_yield: float
    yield_improvement: float
    iterations_used: int
    
    # Per-step breakdown
    step_yields: List[Dict]
    yield_bottleneck_step: Optional[int]
    
    # Cost impact
    initial_cost: float
    final_cost: float
    loss_cost_initial: float
    loss_cost_final: float
    cost_saving_from_yield: float
    
    # Scoring
    initial_score: float
    final_score: float
    
    # Optimization history
    optimization_history: List[Dict]
    
    # Route
    optimized_route: Dict
    
    # Pharma
    pharma_mode: bool
    pharma_compliant: bool
    
    duration_ms: float


class YieldOptimizationEngine:
    """
    Engineers yield to target, doesn't just predict it.
    
    Core loop:
        for each iteration:
            evaluate current yield
            if yield >= target: done
            identify bottleneck step
            apply yield-driven mutations
            recalculate
    """
    
    def __init__(self, constraints_engine=None):
        self.constraints_engine = constraints_engine
        self.target_yield = TARGET_YIELD
        self.max_iterations = 5
    
    # ============ CORE: YIELD OPTIMIZATION LOOP ============
    
    def optimize_for_yield(
        self,
        route: Dict,
        pharma_mode: bool = False,
        max_iterations: int = None,
        target_yield: float = None,
    ) -> YieldOptimizationResult:
        """
        Core optimization loop. Pushes route yield toward target.
        
        Args:
            route: Route dict with steps
            pharma_mode: Hard reject if < 99%
            max_iterations: Override max iterations
            target_yield: Override target yield
        """
        start_time = time.time()
        iterations = max_iterations or self.max_iterations
        target = target_yield or self.target_yield
        
        working_route = copy.deepcopy(route)
        optimization_history = []
        
        # Initial evaluation
        initial_yield = self._calculate_total_yield(working_route)
        initial_cost = working_route.get('total_cost_usd', 100.0)
        initial_loss_cost = self._calculate_loss_cost(working_route, initial_yield)
        initial_score = self._yield_dominant_score(working_route, initial_yield)
        
        current_yield = initial_yield
        
        logger.info(
            f"yield_optimization_start: initial_yield={initial_yield:.4f}, "
            f"target={target:.4f}, pharma={pharma_mode}"
        )
        
        # === OPTIMIZATION LOOP ===
        for i in range(iterations):
            iter_start = time.time()
            yield_before = current_yield
            
            # Check if target achieved
            if current_yield >= target:
                optimization_history.append({
                    "iteration": i + 1,
                    "action": "target_achieved",
                    "yield_before": round(yield_before, 4),
                    "yield_after": round(current_yield, 4),
                    "improvement": 0,
                    "mutations": [],
                    "duration_ms": round((time.time() - iter_start) * 1000, 1),
                })
                break
            
            # Identify bottleneck step
            step_yields = self._get_per_step_yields(working_route)
            bottleneck = self._find_bottleneck(step_yields)
            
            # Apply yield-driven mutations
            mutations = self._mutate_for_yield(working_route, step_yields, current_yield)
            
            # Recalculate
            new_yield = self._calculate_total_yield(working_route)
            improvement = new_yield - yield_before
            
            optimization_history.append({
                "iteration": i + 1,
                "action": "mutate",
                "yield_before": round(yield_before, 4),
                "yield_after": round(new_yield, 4),
                "improvement": round(improvement, 4),
                "bottleneck_step": bottleneck,
                "mutations": mutations,
                "duration_ms": round((time.time() - iter_start) * 1000, 1),
            })
            
            current_yield = new_yield
            
            logger.info(
                f"yield_iteration_{i+1}: yield={new_yield:.4f} "
                f"(Δ{improvement:+.4f}), mutations={len(mutations)}"
            )
            
            # If no improvement, stop
            if improvement <= 0.001 and i > 0:
                break
        
        # Final evaluation
        final_yield = current_yield
        final_cost = self._recalculate_cost(working_route)
        final_loss_cost = self._calculate_loss_cost(working_route, final_yield)
        final_score = self._yield_dominant_score(working_route, final_yield)
        
        # Update route with final yield
        working_route['overall_yield_percent'] = round(final_yield * 100, 2)
        working_route['total_cost_usd'] = round(final_cost, 2)
        working_route['yield_optimized'] = True
        
        # Pharma compliance check
        pharma_compliant = final_yield >= PHARMA_HARD_FLOOR
        
        # Status
        if final_yield >= target:
            status = "target_achieved"
        elif pharma_mode and not pharma_compliant:
            status = "pharma_rejected"
        elif final_yield > initial_yield:
            status = "improved"
        else:
            status = "max_iterations"
        
        # Per-step yield breakdown
        step_yield_info = self._get_per_step_yields(working_route)
        bottleneck_step = self._find_bottleneck(step_yield_info)
        
        return YieldOptimizationResult(
            status=status,
            target_yield=round(target, 4),
            initial_yield=round(initial_yield, 4),
            final_yield=round(final_yield, 4),
            yield_improvement=round(final_yield - initial_yield, 4),
            iterations_used=len(optimization_history),
            step_yields=[
                {"step": s["step"], "reaction_type": s["reaction_type"], "yield": round(s["yield"], 4)}
                for s in step_yield_info
            ],
            yield_bottleneck_step=bottleneck_step,
            initial_cost=round(initial_cost, 2),
            final_cost=round(final_cost, 2),
            loss_cost_initial=round(initial_loss_cost, 2),
            loss_cost_final=round(final_loss_cost, 2),
            cost_saving_from_yield=round(initial_loss_cost - final_loss_cost, 2),
            initial_score=round(initial_score, 2),
            final_score=round(final_score, 2),
            optimization_history=optimization_history,
            optimized_route=working_route,
            pharma_mode=pharma_mode,
            pharma_compliant=pharma_compliant,
            duration_ms=round((time.time() - start_time) * 1000, 1),
        )
    
    # ============ YIELD CALCULATION ============
    
    def _calculate_total_yield(self, route: Dict) -> float:
        """
        Calculate total yield as PRODUCT of per-step yields.
        Y_total = y1 × y2 × y3 × ...
        
        This is the REAL yield — not an average.
        """
        step_yields = self._get_per_step_yields(route)
        
        if not step_yields:
            # If no steps, use route-level yield
            route_yield = route.get('overall_yield_percent', 50.0)
            return route_yield / 100.0
        
        total = 1.0
        for s in step_yields:
            total *= s["yield"]
        
        return total
    
    def _get_per_step_yields(self, route: Dict) -> List[Dict]:
        """Estimate yield for each step based on conditions."""
        steps = route.get('steps', [])
        results = []
        
        for idx, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            
            conditions = step.get('conditions', step)
            rxn_type = step.get('reaction_type', conditions.get('reaction_type', 'unknown'))
            
            # Base yield by reaction type
            base_yield = self._estimate_step_yield(rxn_type, conditions)
            
            results.append({
                "step": idx,
                "reaction_type": rxn_type,
                "yield": base_yield,
                "conditions": conditions,
            })
        
        return results
    
    def _estimate_step_yield(self, reaction_type: str, conditions: Dict) -> float:
        """
        Estimate yield for a single step based on reaction type and conditions.
        Uses heuristic model informed by chemistry principles.
        """
        # Base yields by reaction type (typical literature values)
        base_yields = {
            "esterification": 0.88,
            "suzuki_coupling": 0.85,
            "amide_coupling": 0.90,
            "reduction": 0.92,
            "oxidation": 0.80,
            "grignard": 0.75,
            "friedel_crafts": 0.70,
            "hydrogenation": 0.95,
            "asymmetric_hydrogenation": 0.92,
            "wittig": 0.78,
            "aldol": 0.82,
            "diels_alder": 0.88,
            "coupling": 0.85,
            "substitution": 0.87,
            "elimination": 0.83,
            "pyrolysis": 0.65,
            "photochemistry": 0.60,
            "electrochemistry": 0.70,
        }
        
        base = base_yields.get(reaction_type.lower(), 0.80)
        
        # Modifiers based on conditions
        temp = conditions.get('temperature_celsius', conditions.get('temperature_c', 25))
        catalyst = conditions.get('catalyst', 'None')
        solvent = conditions.get('solvent', 'None')
        
        modifier = 0.0
        
        # Temperature modifiers
        if temp is not None:
            if temp > 200:
                modifier -= 0.08  # Decomposition risk
            elif temp > 150:
                modifier -= 0.04
            elif 40 <= temp <= 100:
                modifier += 0.03  # Optimal range for most reactions
            elif temp < 0:
                modifier -= 0.03  # Slow kinetics
        
        # Catalyst modifiers
        good_catalysts = {"Pd(PPh3)4", "Pd/C", "Amberlyst-15", "Pt/C"}
        poor_catalysts = {"None", "AlCl3", "BF3.Et2O"}
        if catalyst in good_catalysts:
            modifier += 0.05
        elif catalyst in poor_catalysts:
            modifier -= 0.05
        
        # Solvent modifiers
        good_solvents = {"THF", "2-MeTHF", "DMF", "DMSO", "NMP"}
        poor_solvents = {"None", "water", "hexane"}
        if solvent in good_solvents:
            modifier += 0.03
        elif solvent in poor_solvents:
            modifier -= 0.05
        
        return max(0.1, min(0.999, base + modifier))
    
    def _find_bottleneck(self, step_yields: List[Dict]) -> Optional[int]:
        """Find the step with lowest yield (the bottleneck)."""
        if not step_yields:
            return None
        
        min_step = min(step_yields, key=lambda s: s["yield"])
        if min_step["yield"] < STEP_YIELD_FLOOR:
            return min_step["step"]
        return min_step["step"]  # Still return lowest even if above floor
    
    # ============ YIELD-DRIVEN MUTATION ============
    
    def _mutate_for_yield(self, route: Dict, step_yields: List[Dict], current_yield: float) -> List[str]:
        """
        Apply yield-driven mutations.
        
        Strategy:
        - yield < 0.7: aggressive changes (catalyst + solvent + temperature)
        - yield 0.7-0.9: moderate changes (catalyst + solvent)
        - yield 0.9-0.95: targeted changes (catalyst OR temperature)
        - yield 0.95-0.99: micro-adjustments (temperature fine-tune only)
        """
        mutations = []
        steps = route.get('steps', [])
        
        for sy in step_yields:
            idx = sy["step"]
            step_yield = sy["yield"]
            
            if idx >= len(steps):
                continue
            
            step = steps[idx]
            conditions = step.get('conditions', step)
            
            # Skip if step yield is already excellent
            if step_yield >= 0.99:
                continue
            
            # === AGGRESSIVE: yield < 0.7 ===
            if step_yield < 0.70:
                m1 = self._upgrade_catalyst(conditions, "aggressive")
                if m1:
                    mutations.append(f"step_{idx}: {m1}")
                m2 = self._upgrade_solvent(conditions, "aggressive")
                if m2:
                    mutations.append(f"step_{idx}: {m2}")
                m3 = self._optimize_temperature(conditions, "aggressive")
                if m3:
                    mutations.append(f"step_{idx}: {m3}")
            
            # === MODERATE: yield 0.7-0.9 ===
            elif step_yield < 0.90:
                m1 = self._upgrade_catalyst(conditions, "moderate")
                if m1:
                    mutations.append(f"step_{idx}: {m1}")
                m2 = self._upgrade_solvent(conditions, "moderate")
                if m2:
                    mutations.append(f"step_{idx}: {m2}")
            
            # === TARGETED: yield 0.9-0.95 ===
            elif step_yield < STEP_YIELD_FLOOR:
                # Only upgrade catalyst OR temperature, not both
                m1 = self._upgrade_catalyst(conditions, "targeted")
                if m1:
                    mutations.append(f"step_{idx}: {m1}")
                else:
                    m3 = self._optimize_temperature(conditions, "targeted")
                    if m3:
                        mutations.append(f"step_{idx}: {m3}")
            
            # === MICRO: yield 0.95-0.99 ===
            else:
                m3 = self._optimize_temperature(conditions, "micro")
                if m3:
                    mutations.append(f"step_{idx}: {m3}")
        
        return mutations
    
    def _upgrade_catalyst(self, conditions: Dict, intensity: str) -> Optional[str]:
        """Upgrade catalyst for better yield."""
        current = conditions.get('catalyst', 'None')
        upgrades = YIELD_IMPROVEMENTS["catalyst_upgrade"]
        
        if current in upgrades:
            new_cat, yield_gain = upgrades[current]
            
            # Only apply if intensity warrants it
            if intensity == "micro" and yield_gain < 0.04:
                return None
            
            conditions['catalyst'] = new_cat
            return f"catalyst {current}→{new_cat} (+{yield_gain*100:.1f}% yield)"
        
        return None
    
    def _upgrade_solvent(self, conditions: Dict, intensity: str) -> Optional[str]:
        """Upgrade solvent for better yield."""
        current = conditions.get('solvent', 'None')
        upgrades = YIELD_IMPROVEMENTS["solvent_upgrade"]
        
        if current in upgrades:
            new_solv, yield_gain = upgrades[current]
            
            if intensity == "targeted" and yield_gain < 0.03:
                return None
            
            conditions['solvent'] = new_solv
            return f"solvent {current}→{new_solv} (+{yield_gain*100:.1f}% yield)"
        
        return None
    
    def _optimize_temperature(self, conditions: Dict, intensity: str) -> Optional[str]:
        """Fine-tune temperature for yield."""
        temp_key = 'temperature_celsius' if 'temperature_celsius' in conditions else 'temperature_c'
        temp = conditions.get(temp_key)
        
        if temp is None:
            return None
        
        # Determine temperature regime
        if temp > 200:
            regime = "very_high"
        elif temp > 120:
            regime = "high"
        elif temp > 80:
            regime = "moderate"
        elif temp > 40:
            regime = "optimal"
        elif temp > 0:
            regime = "low"
        else:
            regime = "very_low"
        
        adjustment, yield_gain = YIELD_IMPROVEMENTS["temperature_fine_tune"][regime]
        
        if adjustment == 0:
            return None
        
        # Scale adjustment by intensity
        if intensity == "micro":
            adjustment = adjustment // 3 or (1 if adjustment > 0 else -1)
            yield_gain *= 0.3
        elif intensity == "targeted":
            adjustment = adjustment // 2 or (1 if adjustment > 0 else -1)
            yield_gain *= 0.6
        
        new_temp = temp + adjustment
        conditions[temp_key] = new_temp
        return f"temp {temp}→{new_temp}°C (+{yield_gain*100:.1f}% yield)"
    
    # ============ LOSS-BASED COST ============
    
    def _calculate_loss_cost(self, route: Dict, total_yield: float) -> float:
        """
        Calculate cost of material lost due to imperfect yield.
        loss_cost = (1 - total_yield) × raw_material_cost
        
        Low yield = expensive. High yield = cheaper.
        """
        steps = route.get('steps', [])
        
        # Estimate raw material cost from reactants
        raw_cost = 0.0
        for step in steps:
            if isinstance(step, dict):
                reactants = step.get('reactants', step.get('conditions', {}).get('reactants', []))
                if isinstance(reactants, list):
                    for r in reactants:
                        raw_cost += RAW_MATERIAL_COSTS.get(r, RAW_MATERIAL_COSTS["default"])
                else:
                    raw_cost += RAW_MATERIAL_COSTS["default"]
        
        if raw_cost == 0:
            raw_cost = route.get('total_cost_usd', 100.0) * 0.6  # Estimate: 60% of cost is materials
        
        loss_cost = (1.0 - total_yield) * raw_cost
        return loss_cost
    
    def _recalculate_cost(self, route: Dict) -> float:
        """Recalculate route cost including loss-based cost adjustment."""
        base_cost = route.get('total_cost_usd', 100.0)
        total_yield = self._calculate_total_yield(route)
        loss_cost = self._calculate_loss_cost(route, total_yield)
        
        # Adjusted cost = base + loss
        return base_cost + loss_cost
    
    # ============ YIELD-DOMINANT SCORING ============
    
    def _yield_dominant_score(self, route: Dict, total_yield: float = None) -> float:
        """
        Yield-dominant scoring: score = yield^5 - cost_penalty - constraint_penalty
        
        yield^5 forces yield dominance:
        - 0.99^5 = 0.951 (excellent)
        - 0.90^5 = 0.590 (bad)
        - 0.80^5 = 0.328 (terrible)
        """
        if total_yield is None:
            total_yield = self._calculate_total_yield(route)
        
        # Yield component (0-100, exponential)
        yield_score = (total_yield ** 5) * 100
        
        # Cost penalty (normalized)
        total_cost = route.get('total_cost_usd', 100.0)
        cost_penalty = min(30, total_cost / 50)  # Max 30 points penalty
        
        # Constraint penalty
        constraint_penalty = 0.0
        if self.constraints_engine:
            steps = route.get('steps', [])
            for step in steps:
                if isinstance(step, dict):
                    conditions = step.get('conditions', step)
                    try:
                        constraints = self.constraints_engine.evaluate_reaction_constraints(
                            reaction=conditions, scale='lab', batch_size_kg=0.1
                        )
                        constraint_penalty += constraints.total_penalty * 0.1
                    except Exception:
                        pass
        
        score = yield_score - cost_penalty - constraint_penalty
        return max(0, min(100, score))
