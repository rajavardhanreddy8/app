import logging
from typing import List, Dict, Any, Optional
from models.chemistry import SynthesisRoute, ReactionStep
from services.yield_predictor import YieldPredictor
from services.cost_database import CostDatabase
import numpy as np

logger = logging.getLogger(__name__)

class EnhancedRouteScorer:
    """Advanced multi-objective route scoring with ML predictions."""
    
    def __init__(self):
        self.yield_predictor = YieldPredictor()
        self.cost_database = CostDatabase()
        
        # Try to load ML model
        self.ml_available = self.yield_predictor.load_model()
        if not self.ml_available:
            logger.warning("ML yield predictor not available, using heuristics")
    
    def predict_step_yield(self, step: ReactionStep) -> float:
        """Predict yield for a reaction step using ML or heuristics."""
        if self.ml_available:
            try:
                # Prepare reaction dict for ML model
                reaction_dict = {
                    'reactants': [r.smiles for r in step.reactants],
                    'products': [step.product.smiles],
                    'reaction_type': step.reaction_type,
                    'temperature_celsius': step.conditions.temperature_celsius if step.conditions else 25,
                    'catalyst': step.conditions.catalyst if step.conditions else None,
                    'solvent': step.conditions.solvent if step.conditions else None,
                }
                
                predicted_yield = self.yield_predictor.predict(reaction_dict)
                if predicted_yield is not None:
                    return predicted_yield
                    
            except Exception as e:
                logger.debug(f"ML prediction failed: {str(e)}, using heuristic")
        
        # Fallback to heuristic
        return step.estimated_yield_percent
    
    def calculate_step_cost(self, step: ReactionStep, target_mass_mg: float = 100.0) -> float:
        """Calculate cost for a reaction step."""
        try:
            reactant_smiles = [r.smiles for r in step.reactants]
            
            costs = self.cost_database.calculate_reaction_cost(
                reactants=reactant_smiles,
                reagents=[],
                catalyst=step.conditions.catalyst if step.conditions else None,
                solvent=step.conditions.solvent if step.conditions else None,
                target_mass_mg=target_mass_mg
            )
            
            return costs['total_cost']
            
        except Exception as e:
            logger.debug(f"Cost calculation failed: {str(e)}")
            return step.estimated_cost_usd or 50.0
    
    def score_route(
        self, 
        route: SynthesisRoute, 
        optimize_for: str = "balanced",
        weights: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        """Score a synthesis route using multi-objective optimization."""
        
        # Calculate metrics
        metrics = self._calculate_route_metrics(route)
        
        # Determine weights based on optimization goal
        if weights is None:
            weights = self._get_optimization_weights(optimize_for)
        
        # Calculate score
        score = self._calculate_weighted_score(metrics, weights)
        
        return {
            'score': score,
            'metrics': metrics,
            'weights': weights,
            'optimization_goal': optimize_for
        }
    
    def _calculate_route_metrics(self, route: SynthesisRoute) -> Dict[str, float]:
        """Calculate all metrics for a route."""
        
        # Step-by-step yield predictions
        step_yields = []
        step_costs = []
        total_time = 0.0
        
        for step in route.steps:
            # Predict yield with ML
            predicted_yield = self.predict_step_yield(step)
            step_yields.append(predicted_yield)
            
            # Calculate cost
            step_cost = self.calculate_step_cost(step)
            step_costs.append(step_cost)
            
            # Accumulate time
            if step.conditions and step.conditions.time_hours:
                total_time += step.conditions.time_hours
        
        # Overall yield (product of steps)
        overall_yield = np.prod([y/100.0 for y in step_yields]) * 100.0 if step_yields else 0.0
        
        # Total cost
        total_cost = sum(step_costs)
        
        # Number of steps (fewer is better)
        num_steps = len(route.steps)
        
        # Complexity score (0-100, lower is better)
        complexity = self._calculate_complexity(route)
        
        # Feasibility score (0-100, higher is better)
        feasibility = self._calculate_feasibility(route, step_yields)
        
        return {
            'overall_yield': float(overall_yield),
            'total_cost': float(total_cost),
            'num_steps': num_steps,
            'total_time_hours': float(total_time),
            'complexity': float(complexity),
            'feasibility': float(feasibility),
            'step_yields': [float(y) for y in step_yields],
            'step_costs': [float(c) for c in step_costs]
        }
    
    def _calculate_complexity(self, route: SynthesisRoute) -> float:
        """Calculate route complexity score (0-100)."""
        complexity = 0.0
        
        # Step count penalty
        complexity += len(route.steps) * 10
        
        # Difficult reaction penalty
        for step in route.steps:
            if step.difficulty == "high" or step.difficulty == "difficult":
                complexity += 15
            elif step.difficulty == "moderate":
                complexity += 5
        
        # Special conditions penalty
        for step in route.steps:
            if step.conditions:
                if step.conditions.temperature_celsius:
                    if step.conditions.temperature_celsius < 0 or step.conditions.temperature_celsius > 100:
                        complexity += 10
                if step.conditions.catalyst and 'pd' in step.conditions.catalyst.lower():
                    complexity += 5  # Expensive catalysts add complexity
        
        return min(100, complexity)
    
    def _calculate_feasibility(self, route: SynthesisRoute, predicted_yields: List[float]) -> float:
        """Calculate route feasibility score (0-100)."""
        feasibility = 100.0
        
        # Yield confidence
        avg_yield = np.mean(predicted_yields) if predicted_yields else 0
        if avg_yield < 50:
            feasibility -= 20
        elif avg_yield < 70:
            feasibility -= 10
        
        # Step count penalty
        if len(route.steps) > 5:
            feasibility -= (len(route.steps) - 5) * 10
        
        # Check for very difficult steps
        difficult_steps = sum(1 for step in route.steps if step.difficulty == "high")
        feasibility -= difficult_steps * 15
        
        return max(0, feasibility)
    
    def _get_optimization_weights(self, optimize_for: str) -> Dict[str, float]:
        """Get weights for different optimization goals."""
        
        if optimize_for == "yield":
            return {
                'yield': 0.70,
                'cost': 0.10,
                'steps': 0.10,
                'time': 0.05,
                'feasibility': 0.05
            }
        elif optimize_for == "cost":
            return {
                'yield': 0.20,
                'cost': 0.50,
                'steps': 0.15,
                'time': 0.10,
                'feasibility': 0.05
            }
        elif optimize_for == "time":
            return {
                'yield': 0.20,
                'cost': 0.15,
                'steps': 0.40,
                'time': 0.20,
                'feasibility': 0.05
            }
        else:  # balanced
            return {
                'yield': 0.35,
                'cost': 0.25,
                'steps': 0.20,
                'time': 0.10,
                'feasibility': 0.10
            }
    
    def _calculate_weighted_score(self, metrics: Dict[str, float], weights: Dict[str, float]) -> float:
        """Calculate final weighted score (0-100)."""
        
        # Normalize metrics to 0-100 scale
        yield_score = metrics['overall_yield']  # Already 0-100
        cost_score = max(0, 100 - (metrics['total_cost'] / 5))  # $5 per step = 80 score
        steps_score = max(0, 100 - (metrics['num_steps'] * 15))  # 1 step = 85, 5 steps = 25
        time_score = max(0, 100 - (metrics['total_time_hours'] / 2))  # 2 hours per step
        feasibility_score = metrics['feasibility']  # Already 0-100
        
        # Calculate weighted sum
        score = (
            yield_score * weights['yield'] +
            cost_score * weights['cost'] +
            steps_score * weights['steps'] +
            time_score * weights['time'] +
            feasibility_score * weights['feasibility']
        )
        
        return float(min(100, max(0, score)))
