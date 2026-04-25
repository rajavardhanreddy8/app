"""Route comparison, condition prediction, scale/cost/yield optimization."""

import os
import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from dependencies import verify_api_key
import dependencies as deps

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["optimization"], dependencies=[Depends(verify_api_key)])


# ── Request models ──

class RouteComparisonRequest(BaseModel):
    routes: List[Dict[str, Any]]
    optimize_for: str = "balanced"

class ConditionPredictionRequest(BaseModel):
    reactants: List[str]
    products: List[str]
    reaction_type: Optional[str] = None

class CopilotQuery(BaseModel):
    query: str
    route_data: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None

class ScaleOptimizationRequest(BaseModel):
    reaction: Dict[str, Any]
    target_scale: str = "lab"
    batch_size_kg: float = 0.1

class IndustrialCostRequest(BaseModel):
    reaction: Dict[str, Any]
    scale: str = "lab"
    batch_size_kg: float = 0.1
    include_recovery: bool = False

class ProcessConstraintsRequest(BaseModel):
    reaction: Dict[str, Any]
    scale: str = "lab"
    batch_size_kg: float = 0.1

class RouteMutationRequest(BaseModel):
    route: Dict[str, Any]
    mutation_types: Optional[List[str]] = None

class ConstraintFeedbackRequest(BaseModel):
    reaction: Dict[str, Any]
    scale: str = "lab"
    batch_size_kg: float = 0.1

class ConfidenceScoreRequest(BaseModel):
    route: Dict[str, Any]
    mcts_visits: int = 0

class EquipmentFeasibilityRequest(BaseModel):
    route: Dict[str, Any]

class FullOptimizationRequest(BaseModel):
    route: Dict[str, Any]
    apply_mutations: bool = True
    check_constraints: bool = True
    calculate_confidence: bool = True
    check_equipment: bool = True
    mutation_types: Optional[List[str]] = None

class IterativeOptimizationRequest(BaseModel):
    routes: List[Dict[str, Any]]
    objective: str = "balanced"
    optimization_iterations: int = 3
    top_k: int = 5
    early_stop_threshold: float = 0.5
    pharma_mode: bool = False

class YieldOptimizationRequest(BaseModel):
    route: Dict[str, Any]
    pharma_mode: bool = False
    max_iterations: int = 5
    target_yield: float = 0.99


# ── Endpoints ──

@router.post("/conditions/predict")
async def predict_conditions(request: ConditionPredictionRequest):
    """Predict optimal reaction conditions using ML."""
    try:
        reaction_dict = {
            'reactants': request.reactants,
            'products': request.products,
            'reaction_type': request.reaction_type or 'unknown'
        }
        conditions = deps.condition_predictor.predict_safe(reaction_dict)
        return {'status': 'success', 'conditions': conditions}
    except Exception as e:
        logger.error(f"Condition prediction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/routes/compare")
async def compare_routes(request: RouteComparisonRequest):
    """Compare multiple synthesis routes using ML-powered scoring."""
    try:
        from models.chemistry import SynthesisRoute
        route_objects, errors = [], []
        for idx, rd in enumerate(request.routes):
            try:
                if 'target_molecule' not in rd:
                    errors.append(f"Route {idx}: Missing 'target_molecule'")
                    continue
                route_objects.append(SynthesisRoute(**rd))
            except Exception as e:
                errors.append(f"Route {idx}: {e}")
        if not route_objects:
            raise HTTPException(status_code=400, detail="No valid routes. " + " | ".join(errors[:3]))

        scored = deps.route_scorer.compare_routes(route_objects, request.optimize_for)
        results = [{'route': s['route'].model_dump(), 'score': s['score'], 'metrics': s['metrics']} for s in scored]
        return {'status': 'success', 'ranked_routes': results, 'optimization_goal': request.optimize_for}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Route comparison failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/copilot/optimize")
async def copilot_optimize(request: CopilotQuery):
    """AI Copilot for synthesis optimization."""
    from services.synthesis_copilot import SynthesisCopilot
    if deps.copilot_service is None:
        deps.copilot_service = SynthesisCopilot(claude_api_key=os.getenv('ANTHROPIC_API_KEY'))
    try:
        return await deps.copilot_service.process_query(
            user_query=request.query, current_route=request.route_data, context=request.context)
    except Exception as e:
        logger.error(f"Copilot query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scale/optimize")
async def optimize_for_scale(request: ScaleOptimizationRequest):
    """Optimize reaction parameters for production scale."""
    try:
        from services.scale_aware_optimizer import ScaleAwareOptimizer
        optimizer = ScaleAwareOptimizer()
        if request.target_scale not in ['lab', 'pilot', 'industrial']:
            raise HTTPException(status_code=400, detail="target_scale must be 'lab', 'pilot', or 'industrial'")
        return {'status': 'success', 'optimization': optimizer.optimize_for_scale(
            reaction=request.reaction, target_scale=request.target_scale, batch_size_kg=request.batch_size_kg)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Scale optimization failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cost/industrial")
async def calculate_industrial_cost(request: IndustrialCostRequest):
    """Calculate comprehensive industrial cost."""
    try:
        from services.advanced_cost_model import AdvancedCostModel
        costs = AdvancedCostModel().calculate_total_cost(
            reaction=request.reaction, scale=request.scale,
            batch_size_kg=request.batch_size_kg, include_recovery=request.include_recovery)
        return {'status': 'success', 'scale': request.scale, 'batch_size_kg': request.batch_size_kg, 'costs': costs}
    except Exception as e:
        logger.error(f"Industrial cost calculation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/constraints/evaluate")
async def evaluate_process_constraints(request: ProcessConstraintsRequest):
    """Evaluate physical realism and process constraints."""
    try:
        constraints = deps.constraints_engine.evaluate_reaction_constraints(
            reaction=request.reaction, scale=request.scale, batch_size_kg=request.batch_size_kg)
        return {
            'status': 'success', 'scale': request.scale, 'batch_size_kg': request.batch_size_kg,
            'constraints': {
                'heat_risk': constraints.heat_risk, 'heat_score': constraints.heat_score,
                'mixing_efficiency': constraints.mixing_efficiency, 'mixing_score': constraints.mixing_score,
                'mass_transfer': constraints.mass_transfer, 'mass_transfer_score': constraints.mass_transfer_score,
                'safety_risk': constraints.safety_risk, 'safety_score': constraints.safety_score,
                'purification_difficulty': constraints.purification_difficulty,
                'purification_score': constraints.purification_score,
                'phase_complexity': constraints.phase_complexity, 'total_penalty': constraints.total_penalty,
            },
            'recommendations': constraints.recommendations,
            'equipment_requirements': constraints.equipment_requirements,
        }
    except Exception as e:
        logger.error(f"Process constraints evaluation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/routes/mutate")
async def mutate_route(request: RouteMutationRequest):
    """Apply route mutations."""
    if not deps.route_optimizer:
        raise HTTPException(status_code=503, detail="Route optimizer not initialized")
    try:
        mutated = deps.route_optimizer.mutate_route(route=request.route, mutation_types=request.mutation_types)
        return {'status': 'success', 'original_route': request.route, 'mutated_route': mutated,
                'mutations_applied': mutated.get('mutations_applied', []),
                'mutation_count': mutated.get('mutation_count', 0)}
    except Exception as e:
        logger.error(f"Route mutation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/routes/constraint-feedback")
async def constraint_feedback(request: ConstraintFeedbackRequest):
    """Evaluate constraints and auto-fix issues."""
    if not deps.route_optimizer:
        raise HTTPException(status_code=503, detail="Route optimizer not initialized")
    try:
        fb = deps.route_optimizer.apply_constraint_feedback(
            reaction=request.reaction, scale=request.scale, batch_size_kg=request.batch_size_kg)
        return {'status': 'success', 'original_constraints': fb.original_constraints,
                'applied_fixes': fb.applied_fixes, 'improved_constraints': fb.improved_constraints,
                'improvement_summary': fb.improvement_summary, 'num_fixes': len(fb.applied_fixes)}
    except Exception as e:
        logger.error(f"Constraint feedback failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/routes/confidence")
async def calculate_confidence(request: ConfidenceScoreRequest):
    """Calculate route confidence/reliability score."""
    if not deps.route_optimizer:
        raise HTTPException(status_code=503, detail="Route optimizer not initialized")
    try:
        c = deps.route_optimizer.calculate_confidence(route=request.route, mcts_visits=request.mcts_visits)
        return {'status': 'success', 'overall_confidence': c.overall_confidence,
                'yield_confidence': c.yield_confidence, 'cost_confidence': c.cost_confidence,
                'safety_confidence': c.safety_confidence, 'equipment_feasibility': c.equipment_feasibility,
                'risk_level': c.risk_level, 'risk_factors': c.risk_factors,
                'reliability_breakdown': c.reliability_breakdown}
    except Exception as e:
        logger.error(f"Confidence calculation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/routes/equipment-check")
async def check_equipment(request: EquipmentFeasibilityRequest):
    """Check equipment feasibility."""
    if not deps.route_optimizer:
        raise HTTPException(status_code=503, detail="Route optimizer not initialized")
    try:
        return {'status': 'success', **deps.route_optimizer.check_equipment_feasibility(route=request.route)}
    except Exception as e:
        logger.error(f"Equipment check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/routes/optimize")
async def full_route_optimization(request: FullOptimizationRequest):
    """Full optimization pipeline."""
    if not deps.route_optimizer:
        raise HTTPException(status_code=503, detail="Route optimizer not initialized")
    try:
        result = {'status': 'success', 'original_route': request.route}
        current = request.route
        if request.apply_mutations:
            mutated = deps.route_optimizer.mutate_route(current, request.mutation_types)
            result['mutations'] = {'applied': mutated.get('mutations_applied', []),
                                   'count': mutated.get('mutation_count', 0)}
            current = mutated
        if request.check_constraints:
            steps = current.get('steps', [])
            rxn = steps[0].get('conditions', steps[0]) if steps and isinstance(steps[0], dict) else current
            fb = deps.route_optimizer.apply_constraint_feedback(rxn)
            result['constraint_feedback'] = {'original': fb.original_constraints, 'fixes': fb.applied_fixes,
                                             'improved': fb.improved_constraints, 'summary': fb.improvement_summary}
        if request.calculate_confidence:
            c = deps.route_optimizer.calculate_confidence(current)
            result['confidence'] = {'overall': c.overall_confidence, 'risk_level': c.risk_level,
                                    'risk_factors': c.risk_factors,
                                    'breakdown': {'yield': c.yield_confidence, 'cost': c.cost_confidence,
                                                  'safety': c.safety_confidence, 'equipment': c.equipment_feasibility}}
        if request.check_equipment:
            result['equipment'] = deps.route_optimizer.check_equipment_feasibility(current)
        result['optimized_route'] = current
        return result
    except Exception as e:
        logger.error(f"Full optimization failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/routes/iterative-optimize")
async def iterative_optimization(request: IterativeOptimizationRequest):
    """Iterative Optimization Convergence Loop."""
    if not deps.convergence_engine:
        raise HTTPException(status_code=503, detail="Convergence engine not initialized")
    if not request.routes:
        raise HTTPException(status_code=400, detail="At least one route required")
    try:
        r = deps.convergence_engine.optimize(
            routes=request.routes, objective=request.objective,
            max_iterations=request.optimization_iterations, top_k=request.top_k,
            early_stop_threshold=request.early_stop_threshold, pharma_mode=request.pharma_mode)
        return {'status': r.status, 'objective': r.objective, 'pharma_mode': r.pharma_mode,
                'total_iterations': r.total_iterations, 'total_improvement': r.total_improvement,
                'initial_score': r.initial_score, 'final_score': r.final_score,
                'early_stopped': r.early_stopped, 'early_stop_reason': r.early_stop_reason,
                'convergence_history': r.convergence_history, 'best_routes': r.best_routes,
                'total_duration_ms': r.total_duration_ms}
    except Exception as e:
        logger.error(f"Iterative optimization failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/routes/yield-optimize")
async def yield_optimization(request: YieldOptimizationRequest):
    """Yield Optimization Engine."""
    if not deps.yield_engine:
        raise HTTPException(status_code=503, detail="Yield optimization engine not initialized")
    try:
        r = deps.yield_engine.optimize_for_yield(
            route=request.route, pharma_mode=request.pharma_mode,
            max_iterations=request.max_iterations, target_yield=request.target_yield)
        return {
            'status': r.status, 'target_yield': r.target_yield,
            'initial_yield': r.initial_yield, 'final_yield': r.final_yield,
            'yield_improvement': r.yield_improvement,
            'yield_improvement_pct': round(r.yield_improvement * 100, 2),
            'iterations_used': r.iterations_used, 'step_yields': r.step_yields,
            'yield_bottleneck_step': r.yield_bottleneck_step,
            'cost_analysis': {'initial_cost': r.initial_cost, 'final_cost': r.final_cost,
                              'loss_cost_initial': r.loss_cost_initial,
                              'loss_cost_final': r.loss_cost_final,
                              'cost_saving_from_yield': r.cost_saving_from_yield},
            'scoring': {'initial_score': r.initial_score, 'final_score': r.final_score,
                        'score_formula': 'yield^5 × 100 - cost_penalty - constraint_penalty - equipment_penalty'},
            'optimization_history': r.optimization_history, 'optimized_route': r.optimized_route,
            'pharma_mode': r.pharma_mode, 'pharma_compliant': r.pharma_compliant,
            'duration_ms': r.duration_ms}
    except Exception as e:
        logger.error(f"Yield optimization failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
