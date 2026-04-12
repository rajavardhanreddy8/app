"""
Process Constraints & Physical Realism Engine

Evaluates reaction steps based on chemical engineering constraints to ensure
physically feasible, safe, and industrially scalable synthesis routes.
"""

# FIELD_REFERENCE: expected reaction dict keys consumed by ProcessConstraintsEngine
# -------------------------------------------------------------------------------
# Required/primary (with defaults if missing):
# - temperature_c (float): reaction temperature in °C
# - time_hours (float): reaction duration in hours
# - catalyst (str): catalyst identifier/name
# - solvent (str): solvent identifier/name
# - pressure_atm (float): operating pressure in atm
#
# Additional contextual keys used in scoring:
# - reaction_type (str): used for exotherm/runaway heuristics
# - phase_type (str): single, gas-liquid, liquid-liquid, solid-liquid
# - reactants (list): safety heuristics
# - products (list): purification scoring
# - yield_percent (float): purification difficulty adjustments
#
# NOTE:
# Upstream route/LLM payloads may use aliases such as temperature_celsius/time_hours.
# These should be normalized before constraint evaluation to avoid silent defaults.

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ConstraintEvaluation:
    """Results from constraint evaluation of a reaction step."""
    heat_risk: str  # "low", "medium", "high", "critical"
    mixing_efficiency: str
    mass_transfer: str
    safety_risk: str
    purification_difficulty: str
    phase_complexity: str
    
    # Numerical scores (0-100, higher = more problematic)
    heat_score: float
    mixing_score: float
    mass_transfer_score: float
    safety_score: float
    purification_score: float
    
    # Overall constraint penalty (0-100)
    total_penalty: float
    
    # Actionable recommendations
    recommendations: List[str]
    
    # Equipment modifications needed
    equipment_requirements: List[str]


class ProcessConstraintsEngine:
    """
    Evaluates chemical reactions for physical realism and process constraints.
    
    Analyzes thermal, mixing, mass transfer, safety, and downstream processing
    constraints to ensure industrial feasibility.
    """
    
    def __init__(self):
        # Constraint weights for penalty calculation
        self.weights = {
            'heat': 0.25,
            'mixing': 0.15,
            'mass_transfer': 0.15,
            'safety': 0.30,
            'purification': 0.15
        }
        
        # Temperature thresholds (°C)
        self.temp_thresholds = {
            'cryogenic': -40,
            'low': 0,
            'ambient': 25,
            'moderate': 80,
            'high': 150,
            'very_high': 250
        }
        
        # Pressure thresholds (atm)
        self.pressure_thresholds = {
            'vacuum': 0.1,
            'ambient': 1.0,
            'moderate': 5.0,
            'high': 20.0,
            'very_high': 50.0
        }
    
    def evaluate_reaction_constraints(
        self,
        reaction: Dict[str, Any],
        scale: str = "lab",
        batch_size_kg: float = 0.1
    ) -> ConstraintEvaluation:
        """
        Comprehensive constraint evaluation for a single reaction step.
        
        Args:
            reaction: Reaction dict with conditions, reactants, products
            scale: Production scale (lab/pilot/industrial)
            batch_size_kg: Batch size in kilograms
            
        Returns:
            ConstraintEvaluation with scores, risks, and recommendations
        """
        
        # Extract reaction parameters
        temp_c = reaction.get('temperature_c', 25.0)
        time_hours = reaction.get('time_hours', 4.0)
        catalyst = reaction.get('catalyst', '')
        solvent = reaction.get('solvent', 'THF')
        pressure_atm = reaction.get('pressure_atm', 1.0)
        
        # Evaluate individual constraints
        heat_eval = self._evaluate_thermal_constraints(
            temp_c, reaction.get('reaction_type', ''), batch_size_kg
        )
        
        mixing_eval = self._evaluate_mixing_constraints(
            temp_c, solvent, batch_size_kg, scale
        )
        
        mass_transfer_eval = self._evaluate_mass_transfer(
            catalyst, solvent, reaction.get('phase_type', 'single')
        )
        
        safety_eval = self._evaluate_safety_constraints(
            temp_c, pressure_atm, reaction.get('reactants', []), 
            reaction.get('reaction_type', '')
        )
        
        purification_eval = self._evaluate_purification_difficulty(
            reaction.get('products', []), solvent, reaction.get('yield_percent', 80.0)
        )
        
        # Calculate total penalty
        total_penalty = (
            self.weights['heat'] * heat_eval['score'] +
            self.weights['mixing'] * mixing_eval['score'] +
            self.weights['mass_transfer'] * mass_transfer_eval['score'] +
            self.weights['safety'] * safety_eval['score'] +
            self.weights['purification'] * purification_eval['score']
        )
        
        # Aggregate recommendations
        recommendations = []
        recommendations.extend(heat_eval['recommendations'])
        recommendations.extend(mixing_eval['recommendations'])
        recommendations.extend(mass_transfer_eval['recommendations'])
        recommendations.extend(safety_eval['recommendations'])
        recommendations.extend(purification_eval['recommendations'])
        
        # Equipment requirements
        equipment_requirements = self._determine_equipment_requirements(
            heat_eval, mixing_eval, safety_eval, temp_c, pressure_atm
        )
        
        return ConstraintEvaluation(
            heat_risk=heat_eval['risk'],
            mixing_efficiency=mixing_eval['risk'],
            mass_transfer=mass_transfer_eval['risk'],
            safety_risk=safety_eval['risk'],
            purification_difficulty=purification_eval['risk'],
            phase_complexity=mass_transfer_eval.get('phase_complexity', 'single'),
            heat_score=heat_eval['score'],
            mixing_score=mixing_eval['score'],
            mass_transfer_score=mass_transfer_eval['score'],
            safety_score=safety_eval['score'],
            purification_score=purification_eval['score'],
            total_penalty=total_penalty,
            recommendations=recommendations,
            equipment_requirements=equipment_requirements
        )
    
    def _evaluate_thermal_constraints(
        self,
        temp_c: float,
        reaction_type: str,
        batch_size_kg: float
    ) -> Dict[str, Any]:
        """Evaluate heat generation, cooling requirements, and thermal runaway risk."""
        
        score = 0.0
        risk = "low"
        recommendations = []
        
        # Temperature extremes
        if temp_c < self.temp_thresholds['cryogenic']:
            score += 40
            risk = "high"
            recommendations.append("Cryogenic cooling required - use dry ice/liquid nitrogen bath")
        elif temp_c < self.temp_thresholds['low']:
            score += 25
            risk = "medium"
            recommendations.append("Sub-zero cooling - use ice/salt bath or chiller")
        elif temp_c > self.temp_thresholds['very_high']:
            score += 45
            risk = "critical"
            recommendations.append("Very high temperature - pressure-rated reactor required")
        elif temp_c > self.temp_thresholds['high']:
            score += 30
            risk = "high"
            recommendations.append("High temperature - use thermal oil heating with safety controls")
        
        # Exothermic reactions (heuristic based on reaction type)
        if any(word in reaction_type.lower() for word in ['oxidation', 'nitration', 'halogenation', 'hydrolysis']):
            score += 20
            if risk in ["low", "medium"]:
                risk = "medium"
            recommendations.append("Exothermic reaction - add slowly with temperature monitoring")
            
            # Scale-dependent heat accumulation
            if batch_size_kg > 10:
                score += 15
                risk = "high"
                recommendations.append("Large batch exotherm - jacketed reactor with external cooling essential")
        
        # Thermal runaway risk (high temp + exothermic + large scale)
        if temp_c > 100 and batch_size_kg > 50 and 'oxidation' in reaction_type.lower():
            score += 25
            risk = "critical"
            recommendations.append("THERMAL RUNAWAY RISK - implement emergency cooling and pressure relief")
        
        return {
            'score': min(score, 100),
            'risk': risk,
            'recommendations': recommendations
        }
    
    def _evaluate_mixing_constraints(
        self,
        temp_c: float,
        solvent: str,
        batch_size_kg: float,
        scale: str
    ) -> Dict[str, Any]:
        """Evaluate mixing efficiency, turbulence, and dead zone risk."""
        
        score = 0.0
        risk = "low"
        recommendations = []
        
        # Viscosity estimation (temperature-dependent)
        if temp_c < 0:
            viscosity_factor = 2.0  # Higher viscosity at low temp
            score += 20
            risk = "medium"
            recommendations.append("Low temperature increases viscosity - use high-shear mixer")
        elif temp_c > 150:
            viscosity_factor = 0.5  # Lower viscosity at high temp
        else:
            viscosity_factor = 1.0
        
        # Reynolds number estimation (simplified heuristic)
        # Re = (density * velocity * length) / viscosity
        # Higher Re = more turbulent = better mixing
        
        if scale == 'industrial' and batch_size_kg > 100:
            # Large-scale mixing challenges
            score += 25
            risk = "medium"
            recommendations.append("Industrial scale - use baffled reactor with anchor/helical impeller")
            
            if viscosity_factor > 1.5:
                score += 15
                recommendations.append("High viscosity at scale - consider CSTR or scraped-surface reactor")
        
        # Solvent-based mixing considerations
        if solvent in ['DMF', 'DMSO']:  # High-boiling, viscous solvents
            score += 10
            recommendations.append("Viscous solvent - ensure adequate agitation (>200 rpm)")
        
        # Multi-phase mixing
        if batch_size_kg > 10:
            score += 10
            recommendations.append("Large batch - verify mixing uniformity with tracer studies")
        
        return {
            'score': min(score, 100),
            'risk': risk,
            'recommendations': recommendations
        }
    
    def _evaluate_mass_transfer(
        self,
        catalyst: str,
        solvent: str,
        phase_type: str
    ) -> Dict[str, Any]:
        """Evaluate diffusion limitations and catalyst contact efficiency."""
        
        score = 0.0
        risk = "low"
        recommendations = []
        phase_complexity = phase_type or "single"
        
        # Heterogeneous catalysis (solid catalyst)
        if catalyst and any(metal in catalyst for metal in ['Pd', 'Pt', 'Ni', 'Cu']):
            score += 15
            risk = "medium"
            recommendations.append("Heterogeneous catalyst - ensure fine particle size for surface area")
            recommendations.append("Consider catalyst loading: 1-5 mol% for optimal contact")
            phase_complexity = "multi-phase"
        
        # Gas-liquid reactions
        if phase_type == "gas-liquid":
            score += 25
            risk = "medium"
            recommendations.append("Gas-liquid interface - use sparged/bubble column reactor")
            recommendations.append("Monitor gas flow rate and bubble size distribution")
        
        # Liquid-liquid reactions (biphasic)
        elif phase_type == "liquid-liquid":
            score += 20
            risk = "medium"
            recommendations.append("Biphasic system - use phase transfer catalyst or high-speed mixing")
            recommendations.append("Consider emulsion stability and phase separation downstream")
        
        # Solid-liquid (suspension)
        elif phase_type == "solid-liquid":
            score += 18
            risk = "medium"
            recommendations.append("Suspension - maintain agitation to prevent settling")
            recommendations.append("Use overhead stirrer with pitched-blade impeller")
        
        # Solvent effects on diffusion
        if solvent in ['Water', 'MeOH', 'EtOH']:  # Low-viscosity solvents
            score -= 5  # Better mass transfer
        elif solvent in ['DMF', 'DMSO', 'Toluene']:  # Higher viscosity
            score += 10
            recommendations.append(f"Moderate viscosity solvent ({solvent}) - verify diffusion isn't limiting")
        
        return {
            'score': max(min(score, 100), 0),
            'risk': risk,
            'recommendations': recommendations,
            'phase_complexity': phase_complexity
        }
    
    def _evaluate_safety_constraints(
        self,
        temp_c: float,
        pressure_atm: float,
        reactants: List[str],
        reaction_type: str
    ) -> Dict[str, Any]:
        """Evaluate pressure risk, flammability, toxicity, and corrosiveness."""
        
        score = 0.0
        risk = "low"
        recommendations = []
        
        # Pressure hazards
        if pressure_atm > self.pressure_thresholds['very_high']:
            score += 50
            risk = "critical"
            recommendations.append("VERY HIGH PRESSURE - use autoclave with rupture disk and pressure relief")
        elif pressure_atm > self.pressure_thresholds['high']:
            score += 35
            risk = "high"
            recommendations.append("High pressure - pressure-rated vessel and safety interlocks required")
        elif pressure_atm > self.pressure_thresholds['moderate']:
            score += 20
            risk = "medium"
            recommendations.append("Moderate pressure - sealed reactor with pressure gauge")
        
        # Gas evolution reactions (pressure buildup risk)
        if any(word in reaction_type.lower() for word in ['decarboxylation', 'diazo', 'decomposition']):
            score += 25
            risk = "high" if risk == "low" else risk
            recommendations.append("Gas evolution - use pressure-relief system and vent scrubber")
        
        # Flammable solvents at high temperature
        if temp_c > 60:
            flammable_check = any(s in str(reactants).lower() for s in ['ether', 'hexane', 'benzene', 'toluene'])
            if flammable_check:
                score += 30
                risk = "high" if risk in ["low", "medium"] else risk
                recommendations.append("Flammable solvent at elevated temp - use closed system with nitrogen blanket")
        
        # Toxic/hazardous reagents (heuristic)
        hazardous_keywords = ['chlor', 'brom', 'iod', 'cyan', 'azide', 'hydrazine', 'phosgene']
        if any(kw in str(reactants).lower() for kw in hazardous_keywords):
            score += 20
            if risk == "low":
                risk = "medium"
            recommendations.append("Hazardous reagent - use fume hood or enclosed system with scrubber")
        
        # Corrosive conditions (strong acids/bases)
        if any(word in reaction_type.lower() for word in ['acid', 'base', 'hydrolysis']):
            score += 15
            recommendations.append("Corrosive conditions - use glass-lined or Hastelloy reactor")
        
        # Combined high temp + high pressure
        if temp_c > 150 and pressure_atm > 10:
            score += 25
            risk = "critical"
            recommendations.append("CRITICAL: High temp + high pressure - specialized autoclave with full safety system")
        
        return {
            'score': min(score, 100),
            'risk': risk,
            'recommendations': recommendations
        }
    
    def _evaluate_purification_difficulty(
        self,
        products: List[str],
        solvent: str,
        yield_percent: float
    ) -> Dict[str, Any]:
        """Evaluate downstream processing complexity."""
        
        score = 0.0
        risk = "low"
        recommendations = []
        
        # Low yield = more impurities to separate
        if yield_percent < 50:
            score += 30
            risk = "high"
            recommendations.append("Low yield - expect difficult purification, consider recrystallization")
        elif yield_percent < 70:
            score += 15
            risk = "medium"
            recommendations.append("Moderate yield - plan for chromatography or multiple crystallizations")
        
        # High-boiling solvents (difficult to remove)
        if solvent in ['DMF', 'DMSO', 'DMA']:
            score += 20
            risk = "medium"
            recommendations.append(f"High-boiling solvent ({solvent}) - use rotovap under vacuum or azeotropic distillation")
        
        # Multiple products (separation needed)
        if len(products) > 1:
            score += 25
            risk = "high"
            recommendations.append("Multiple products - requires chromatography or fractional distillation")
        
        # Water-miscible solvents (extraction challenges)
        if solvent in ['MeOH', 'EtOH', 'Acetone', 'THF']:
            score += 10
            recommendations.append("Water-miscible solvent - use brine wash or salting out for extraction")
        
        return {
            'score': min(score, 100),
            'risk': risk,
            'recommendations': recommendations
        }
    
    def _determine_equipment_requirements(
        self,
        heat_eval: Dict,
        mixing_eval: Dict,
        safety_eval: Dict,
        temp_c: float,
        pressure_atm: float
    ) -> List[str]:
        """Determine required equipment based on constraint evaluations."""
        
        equipment = []
        
        # Thermal equipment
        if heat_eval['risk'] in ['high', 'critical']:
            equipment.append("Jacketed reactor with external cooling/heating")
            if temp_c > 150:
                equipment.append("Thermal oil circulation system")
            elif temp_c < -20:
                equipment.append("Cryogenic cooling system")
        
        # Mixing equipment
        if mixing_eval['risk'] in ['medium', 'high']:
            equipment.append("High-shear mixer or anchor impeller")
        
        # Pressure equipment
        if pressure_atm > 5:
            equipment.append("Pressure-rated autoclave")
            equipment.append("Rupture disk and pressure relief valve")
        
        # Safety equipment
        if safety_eval['risk'] in ['high', 'critical']:
            equipment.append("Emergency cooling system")
            equipment.append("Pressure relief and vent scrubber")
            if temp_c > 100 or 'flam' in str(safety_eval['recommendations']).lower():
                equipment.append("Nitrogen blanketing system")
        
        return equipment


# Demo/testing code
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    engine = ProcessConstraintsEngine()
    
    # Test case 1: High-temperature oxidation (challenging)
    test_reaction_1 = {
        'reactants': ['toluene', 'KMnO4'],
        'products': ['benzoic acid'],
        'reaction_type': 'oxidation',
        'temperature_c': 110.0,
        'time_hours': 6.0,
        'catalyst': '',
        'solvent': 'Water',
        'pressure_atm': 1.0,
        'yield_percent': 75.0
    }
    
    print("\n=== Test 1: High-Temperature Oxidation ===")
    result_1 = engine.evaluate_reaction_constraints(test_reaction_1, scale='pilot', batch_size_kg=10.0)
    print(f"Heat Risk: {result_1.heat_risk} (score: {result_1.heat_score:.1f})")
    print(f"Safety Risk: {result_1.safety_risk} (score: {result_1.safety_score:.1f})")
    print(f"Total Penalty: {result_1.total_penalty:.1f}")
    print(f"Recommendations ({len(result_1.recommendations)}):")
    for rec in result_1.recommendations[:5]:
        print(f"  - {rec}")
    
    # Test case 2: Heterogeneous catalysis (mass transfer issues)
    test_reaction_2 = {
        'reactants': ['styrene', 'H2'],
        'products': ['ethylbenzene'],
        'reaction_type': 'hydrogenation',
        'temperature_c': 80.0,
        'time_hours': 4.0,
        'catalyst': 'Pd/C',
        'solvent': 'EtOH',
        'pressure_atm': 10.0,
        'yield_percent': 95.0,
        'phase_type': 'gas-liquid'
    }
    
    print("\n=== Test 2: Heterogeneous Catalytic Hydrogenation ===")
    result_2 = engine.evaluate_reaction_constraints(test_reaction_2, scale='industrial', batch_size_kg=100.0)
    print(f"Mass Transfer: {result_2.mass_transfer} (score: {result_2.mass_transfer_score:.1f})")
    print(f"Safety Risk: {result_2.safety_risk} (score: {result_2.safety_score:.1f})")
    print(f"Total Penalty: {result_2.total_penalty:.1f}")
    print(f"Equipment Required ({len(result_2.equipment_requirements)}):")
    for eq in result_2.equipment_requirements:
        print(f"  - {eq}")
    
    print("\n✓ Process Constraints Engine Test Complete")
