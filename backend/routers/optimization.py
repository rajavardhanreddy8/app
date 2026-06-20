"""Route comparison, condition prediction, scale/cost/yield optimization."""

import os
import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from dependencies import deps, verify_api_key

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

class GreenCompareRequest(BaseModel):
    routes: List[Dict[str, Any]]
    scale: str = "lab"   # lab | pilot | industrial

class TelescopingAnalysisRequest(BaseModel):
    route: Dict[str, Any]

class StageGateAnalysisRequest(BaseModel):
    routes: List[Dict[str, Any]]
    stage: str
    quantity_kg: float

class YieldOptimizationRequest(BaseModel):
    route: Dict[str, Any]
    pharma_mode: bool = False
    max_iterations: int = 5
    target_yield: float = 0.99


def _quality_metadata(
    source: str,
    confidence: float,
    *,
    uncertainty: Optional[Dict[str, Any]] = None,
    warnings: Optional[List[str]] = None,
    model_version: str = "quality_contract_v1",
) -> Dict[str, Any]:
    """Build additive provenance metadata for estimated API outputs."""
    warning_list = [str(item) for item in (warnings or []) if item]
    normalized_confidence = round(max(0.0, min(1.0, float(confidence))), 3)
    return {
        "prediction_source": source,
        "confidence": normalized_confidence,
        "uncertainty": uncertainty,
        "warnings": warning_list,
        "review_status": "needs_human_review",
        "human_review_required": True,
        "evidence": {
            "source": source,
            "model_version": model_version,
            "confidence": normalized_confidence,
            "uncertainty_calibrated": False,
        },
    }


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
        decision = str(conditions.get("model_decision", conditions.get("source", "fallback"))).lower()
        if decision in {"ensemble", "legacy_model"}:
            source, evidence_confidence = "ml", 0.7
        elif "prior" in decision or decision == "rules":
            source, evidence_confidence = "rules", 0.55
        else:
            source, evidence_confidence = "fallback", 0.25

        temperature = conditions.get("temperature_celsius")
        uncertainty = None
        if isinstance(temperature, (int, float)):
            uncertainty = {
                "temperature_celsius": {
                    "lower": round(float(temperature) - 20.0, 2),
                    "upper": round(float(temperature) + 20.0, 2),
                    "calibrated": False,
                }
            }
        metadata = _quality_metadata(
            source,
            evidence_confidence,
            uncertainty=uncertainty,
            warnings=conditions.get("safety_warnings", []) + (
                ["Condition predictor used fallback values."] if source == "fallback" else []
            ),
            model_version="condition_predictor_v1",
        )
        for key in (
            "prediction_source",
            "uncertainty",
            "warnings",
            "review_status",
            "human_review_required",
            "evidence",
        ):
            conditions.setdefault(key, metadata[key])
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
        score_metadata = _quality_metadata(
            "heuristic",
            0.5,
            warnings=["Route ranking uses weighted heuristic scoring and requires chemist review."],
            model_version="enhanced_route_scorer_v1",
        )
        results = [
            {
                'route': s['route'].model_dump(),
                'score': s['score'],
                'metrics': s['metrics'],
                'score_evidence': score_metadata,
            }
            for s in scored
        ]
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
        claude_key = os.getenv('ANTHROPIC_API_KEY') if os.getenv("LLM_PROVIDER", "anthropic").lower() != "openrouter" else None
        deps.copilot_service = SynthesisCopilot(claude_api_key=claude_key)
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
        optimization = optimizer.optimize_for_scale(
            reaction=request.reaction,
            target_scale=request.target_scale,
            batch_size_kg=request.batch_size_kg,
        )
        optimization.update(_quality_metadata(
            "heuristic",
            0.4,
            warnings=["Scale-up estimates are engineering heuristics, not validated batch records."],
            model_version="scale_aware_optimizer_v1",
        ))
        return {'status': 'success', 'optimization': optimization}
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
        return {
            'status': 'success',
            'scale': request.scale,
            'batch_size_kg': request.batch_size_kg,
            'costs': costs,
            **_quality_metadata(
                "heuristic",
                0.35,
                uncertainty={
                    "relative_cost_percent": {
                        "lower": -30.0,
                        "upper": 75.0,
                        "calibrated": False,
                    }
                },
                warnings=["Costs use local catalog assumptions and simplified scale factors."],
                model_version="advanced_cost_model_v1",
            ),
        }
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
            **_quality_metadata(
                "rules",
                0.5,
                warnings=[
                    "Safety and process scores are rule-based screening outputs, not a process hazard analysis."
                ],
                model_version="process_constraints_rules_v1",
            ),
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
                'reliability_breakdown': c.reliability_breakdown,
                **_quality_metadata(
                    "heuristic",
                    0.5,
                    warnings=[
                        "Reliability scores combine heuristic sub-scores and are not calibrated probabilities."
                    ],
                    model_version="route_optimizer_confidence_v1",
                )}
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


@router.post("/routes/telescoping-analysis")
async def telescoping_analysis(request: TelescopingAnalysisRequest):
    """Analyze whether consecutive route steps can be telescoped one-pot."""
    if not request.route.get("steps"):
        raise HTTPException(status_code=400, detail="route.steps is required")

    try:
        from services.telescoping_analyzer import TelescopingAnalyzer

        analyzer = TelescopingAnalyzer()
        analysis = analyzer.analyze_route_telescoping(request.route)
        return {"status": "success", **analysis}
    except Exception as e:
        logger.error(f"Telescoping analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/routes/stage-gate-analysis")
async def stage_gate_analysis(request: StageGateAnalysisRequest):
    """Return route recommendations appropriate for a clinical development stage."""
    if not request.routes:
        raise HTTPException(status_code=400, detail="At least one route is required")

    try:
        from services.stage_gate_advisor import StageGateAdvisor

        advisor = StageGateAdvisor()
        return {
            "status": "success",
            **advisor.advise_for_stage(
                routes=request.routes,
                stage=request.stage,
                target_quantity_kg=request.quantity_kg,
            ),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Stage-gate analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Green Chemistry Comparison ───────────────────────────────────────────────

@router.post("/routes/green-compare")
async def green_compare_routes(request: GreenCompareRequest):
    """
    Rank multiple synthesis routes by sustainability.

    Returns a sustainability ranking (separate from yield/cost) based on:
      1. PMI  — Process Mass Intensity   (lower is greener)
      2. AE   — Atom Economy             (higher is greener)
      3. E-factor                        (lower is greener)
      4. Convergence score               (higher is greener)

    Also returns individual green_metrics for each route.
    """
    if not request.routes:
        raise HTTPException(status_code=400, detail="At least one route is required")

    try:
        from services.green_chemistry_metrics import get_green_metrics
        green = get_green_metrics()
        ranked = green.rank_routes(request.routes, scale=request.scale)

        # Build summary table
        summary = []
        for entry in ranked:
            gm = entry["green_metrics"]
            summary.append({
                "sustainability_rank":  entry["sustainability_rank"],
                "sustainability_score": entry["sustainability_score"],
                "atom_economy_percent":            gm.get("atom_economy_percent"),
                "e_factor":                        gm.get("e_factor"),
                "pmi":                             gm.get("pmi"),
                "pmi_rating":                      gm.get("pmi_rating"),
                "route_type":                      gm.get("route_type"),
                "convergence_score":               gm.get("convergence_score"),
                "estimated_co2_kg_per_kg_product": gm.get("estimated_co2_kg_per_kg_product"),
                "bottleneck_step":                 gm.get("bottleneck_step"),
                "solvent_intensity_kg_per_kg":     gm.get("solvent_intensity_kg_per_kg"),
            })

        return {
            "status": "success",
            "scale": request.scale,
            "num_routes": len(ranked),
            "sustainability_ranking": summary,
            "ranked_routes": ranked,
        }
    except Exception as e:
        logger.error(f"Green comparison failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
