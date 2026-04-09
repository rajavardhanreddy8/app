from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone

# Import chemistry models and services
from models.chemistry import SynthesisRequest, SynthesisResponse, MolecularStructure
from services.orchestrator import SynthesisPlanningOrchestrator
from services.molecular_service import MolecularService
from services.synthesis_copilot import SynthesisCopilot
from services.condition_predictor import ConditionPredictor
from services.enhanced_route_scorer import EnhancedRouteScorer
from services.template_extractor import TemplateExtractor
from services.equipment_recommender import EquipmentRecommender
from services.route_optimizer import RouteOptimizer
from services.process_constraints_engine import ProcessConstraintsEngine
from services.convergence_engine import ConvergenceEngine

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Initialize services
orchestrator = None  # Will be initialized after env check
molecular_service = MolecularService()
copilot_service = None  # Will be initialized after env check
condition_predictor = ConditionPredictor()
route_scorer = EnhancedRouteScorer()
template_extractor = TemplateExtractor()
equipment_recommender = EquipmentRecommender()

# Phase 6 Optimization Layer
constraints_engine = ProcessConstraintsEngine()
route_optimizer = None  # Will be initialized in startup
convergence_engine = None  # Phase 7 convergence engine

# Load ML models and templates on startup
condition_predictor.load_models()
template_extractor.load_templates()
logging.info("ML models and templates loading...")

# Create the main app without a prefix
app = FastAPI(
    title="Chemistry Synthesis Planning API",
    description="AI-powered synthesis route planning using Claude Sonnet 4.5",
    version="1.0.0"
)

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")


# Define Models
class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")  # Ignore MongoDB's _id field
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StatusCheckCreate(BaseModel):
    client_name: str

class MoleculeValidationRequest(BaseModel):
    smiles: str

# Add your routes to the router instead of directly to app
@api_router.get("/")
async def root():
    return {
        "message": "Chemistry Synthesis Planning API",
        "version": "1.0.0",
        "endpoints": {
            "synthesis_plan": "/api/synthesis/plan",
            "validate_molecule": "/api/molecule/validate",
            "analyze_molecule": "/api/molecule/analyze"
        }
    }

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.model_dump()
    status_obj = StatusCheck(**status_dict)
    
    # Convert to dict and serialize datetime to ISO string for MongoDB
    doc = status_obj.model_dump()
    doc['timestamp'] = doc['timestamp'].isoformat()
    
    _ = await db.status_checks.insert_one(doc)
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks(limit: int = 100, skip: int = 0):
    """Get status check history with pagination support."""
    # Exclude MongoDB's _id field from the query results with proper pagination
    status_checks = await db.status_checks.find({}, {"_id": 0}).skip(skip).limit(min(limit, 1000)).to_list(min(limit, 1000))
    
    # Convert ISO string timestamps back to datetime objects
    for check in status_checks:
        if isinstance(check['timestamp'], str):
            check['timestamp'] = datetime.fromisoformat(check['timestamp'])
    
    return status_checks



# Phase 6: Initialize chemical graph on startup
@app.on_event("startup")
async def startup_event():
    """Initialize chemical graph from MongoDB (Phase 6 critical integration)."""
    global orchestrator, route_optimizer, convergence_engine
    
    if orchestrator:
        try:
            await orchestrator.initialize_graph()
            logging.info("✓ Chemical graph initialized from MongoDB")
        except Exception as e:
            logging.error(f"✗ Chemical graph init failed: {str(e)}")
    
    # Initialize route optimizer with constraints engine and equipment recommender
    try:
        route_optimizer = RouteOptimizer(
            constraints_engine=constraints_engine,
            equipment_recommender=equipment_recommender
        )
        convergence_engine = ConvergenceEngine(
            route_optimizer=route_optimizer,
            constraints_engine=constraints_engine
        )
        logging.info("✓ Route optimizer + convergence engine initialized")
    except Exception as e:
        logging.error(f"✗ Route optimizer init failed: {str(e)}")
        route_optimizer = RouteOptimizer()
        convergence_engine = ConvergenceEngine(route_optimizer=route_optimizer)

# ============ CHEMISTRY SYNTHESIS ENDPOINTS ============

@api_router.post("/synthesis/plan", response_model=SynthesisResponse)
async def plan_synthesis(
    request: SynthesisRequest, 
    use_advanced: bool = False, 
    scale: str = "lab", 
    batch_size_kg: float = 0.1,
    pharma_mode: bool = False,  # Phase 5: Pharma yield enforcement
    use_mcts: bool = False  # Phase 6: MCTS global optimization
):
    """
    Plan synthesis routes for a target molecule.
    
    **Parameters:**
    - `use_advanced` (bool): Use advanced planning with retrosynthesis, ML, scale optimization, and cost modeling
    - `scale` (str): Target scale - "lab", "pilot", or "industrial" (only for use_advanced=True)
    - `batch_size_kg` (float): Batch size in kg (only for use_advanced=True)
    - `pharma_mode` (bool): Enforce pharma-grade ≥99% yield requirement (Phase 5)
    - `use_mcts` (bool): Use MCTS for global route optimization instead of beam search (Phase 6)
    
    **Returns:**
    - Basic mode: Multiple routes from Claude ranked by yield, cost, and complexity
    - Advanced mode: 5 optimized routes with full ML predictions, scale optimization, and industrial cost analysis
    - Pharma mode: Only routes with ≥99% yield, optimized for cost via multi-step routes
    - MCTS mode: Global optimization using Monte Carlo Tree Search on chemical graph
    """
    global orchestrator
    
    # Initialize orchestrator if not done (Phase 6: with database)
    if orchestrator is None:
        api_key = os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="ANTHROPIC_API_KEY not configured. Please add it to environment variables."
            )
        orchestrator = SynthesisPlanningOrchestrator(api_key=api_key, db=db)  # Phase 6: Pass db
    
    try:
        # Route to advanced or basic planning
        if use_advanced:
            logger.info(f"using_advanced_synthesis_planning: scale={scale}, batch={batch_size_kg}kg, mcts={use_mcts}, pharma={pharma_mode}")
            result = await orchestrator.plan_synthesis_advanced(
                request=request,
                num_routes=5,
                scale=scale,
                batch_size_kg=batch_size_kg,
                use_mcts=use_mcts,  # Phase 6
                pharma_mode=pharma_mode  # Phase 5
            )
        else:
            logger.info("using_basic_synthesis_planning")
            result = await orchestrator.plan_synthesis(request)
        
        # Store in MongoDB for history
        doc = result.model_dump()
        doc['_id'] = doc['request_id']
        doc['timestamp'] = doc['timestamp'].isoformat()
        
        # Convert datetime objects in nested structures
        for route in doc.get('routes', []):
            if 'created_at' in route:
                route['created_at'] = route['created_at'].isoformat()
        
        await db.synthesis_plans.insert_one(doc)
        
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logging.error(f"Synthesis planning error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/molecule/validate")
async def validate_molecule(request: MoleculeValidationRequest):
    """Validate a SMILES string for chemical correctness."""
    try:
        validation = molecular_service.validate_smiles(request.smiles)
        return validation
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/molecule/analyze")
async def analyze_molecule(request: MoleculeValidationRequest):
    """Analyze a molecule and return detailed properties."""
    try:
        analysis = molecular_service.parse_smiles(request.smiles)
        
        if not analysis.get("valid"):
            raise HTTPException(status_code=400, detail=analysis.get("error"))
        
        return analysis
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/synthesis/history")
async def get_synthesis_history(limit: int = 10):
    """Get recent synthesis planning requests."""
    try:
        history = await db.synthesis_plans.find({}, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
        return {"history": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============ AI COPILOT ENDPOINTS ============

class CopilotQuery(BaseModel):
    query: str
    route_data: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None

@api_router.post("/copilot/optimize")
async def copilot_optimize(request: CopilotQuery):
    """
    AI Copilot for synthesis optimization.
    
    Natural language queries like:
    - "How can I reduce the cost?"
    - "Increase the yield"
    - "Make it faster"
    - "Predict yield for this reaction"
    """
    global copilot_service
    
    # Initialize copilot if needed
    if copilot_service is None:
        api_key = os.getenv('ANTHROPIC_API_KEY')
        copilot_service = SynthesisCopilot(claude_api_key=api_key)
    
    try:
        result = await copilot_service.process_query(
            user_query=request.query,
            current_route=request.route_data,
            context=request.context
        )
        return result
    except Exception as e:
        logging.error(f"Copilot query failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ============ CONDITION PREDICTION ENDPOINTS ============

class ConditionPredictionRequest(BaseModel):
    reactants: List[str]
    products: List[str]
    reaction_type: Optional[str] = None

@api_router.post("/conditions/predict")
async def predict_conditions(request: ConditionPredictionRequest):
    """
    Predict optimal reaction conditions using ML.
    
    Returns temperature, catalyst, solvent predictions with confidence scores.
    """
    try:
        reaction_dict = {
            'reactants': request.reactants,
            'products': request.products,
            'reaction_type': request.reaction_type or 'unknown'
        }
        
        conditions = condition_predictor.predict_conditions(reaction_dict)
        
        return {
            'status': 'success',
            'conditions': conditions
        }
        
    except Exception as e:
        logging.error(f"Condition prediction failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ============ ROUTE COMPARISON ENDPOINT ============

class RouteComparisonRequest(BaseModel):
    routes: List[Dict[str, Any]]
    optimize_for: str = "balanced"

@api_router.post("/routes/compare")
async def compare_routes(request: RouteComparisonRequest):
    """
    Compare multiple synthesis routes using ML-powered scoring.
    
    Bug Fix 4 & 5: Improved validation and error messages.
    
    Required fields in each route:
    - target_molecule: {smiles: str} 
    - starting_materials: [{smiles: str}]
    - steps: [{reactants: [...], product: {...}, reaction_type: str, estimated_yield_percent: float}]
    - overall_yield_percent: float
    - total_cost_usd: float
    - total_time_hours: float
    - score: float
    
    Returns routes ranked by score with detailed metrics.
    """
    try:
        from models.chemistry import SynthesisRoute
        
        # Convert dict routes to SynthesisRoute objects with better error handling
        route_objects = []
        errors = []
        
        for idx, route_data in enumerate(request.routes):
            try:
                # Validate required fields before attempting conversion
                if 'target_molecule' not in route_data:
                    errors.append(f"Route {idx}: Missing required field 'target_molecule'")
                    continue
                
                route = SynthesisRoute(**route_data)
                route_objects.append(route)
            except Exception as e:
                errors.append(f"Route {idx}: {str(e)}")
                continue
        
        if not route_objects:
            error_detail = "No valid routes provided. " + " | ".join(errors[:3])
            raise HTTPException(status_code=400, detail=error_detail)
        
        # Score routes
        scored_routes = route_scorer.compare_routes(route_objects, request.optimize_for)
        
        # Convert back to dicts for JSON response
        results = []
        for scored in scored_routes:
            results.append({
                'route': scored['route'].model_dump(),
                'score': scored['score'],
                'metrics': scored['metrics']
            })
        
        return {
            'status': 'success',
            'ranked_routes': results,
            'optimization_goal': request.optimize_for
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Route comparison failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ============ TEMPLATE & EQUIPMENT ENDPOINTS ============

@api_router.get("/templates/stats")
async def get_template_statistics():
    """Get reaction template database statistics."""
    try:
        stats = template_extractor.get_statistics()
        return {'status': 'success', 'statistics': stats}
    except Exception as e:
        logging.error(f"Template stats failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/templates/{reaction_type}")
async def get_templates_by_type(reaction_type: str):
    """Get templates for a specific reaction type."""
    try:
        templates = template_extractor.get_templates_for_reaction_type(reaction_type)
        if templates:
            return {'status': 'success', 'reaction_type': reaction_type, 'templates': templates}
        else:
            raise HTTPException(status_code=404, detail=f"No templates found for {reaction_type}")
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Template retrieval failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

class EquipmentRequest(BaseModel):
    reaction_type: str
    scale_mg: float
    temperature_c: Optional[float] = None
    pressure_atm: Optional[float] = None

@api_router.post("/equipment/recommend")
async def recommend_equipment(request: EquipmentRequest):
    """
    Recommend laboratory equipment for a reaction.
    
    Returns reactor recommendations with scoring and reasoning.
    """
    try:
        recommendations = equipment_recommender.recommend_reactor(
            reaction_type=request.reaction_type,
            scale_mg=request.scale_mg,
            temperature_c=request.temperature_c,
            pressure_atm=request.pressure_atm
        )
        
        complete_setup = equipment_recommender.recommend_complete_setup(
            reaction_type=request.reaction_type,
            scale_mg=request.scale_mg,
            temperature_c=request.temperature_c
        )
        
        return {
            'status': 'success',
            'reactor_recommendations': recommendations,
            'complete_setup': complete_setup
        }
        
    except Exception as e:
        logging.error(f"Equipment recommendation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))



# ============ PHASE 4: ADVANCED MODULE ENDPOINTS ============

class RetrosynthesisRequest(BaseModel):
    target_smiles: str
    max_depth: int = 5
    max_routes: int = 5

@api_router.post("/retrosynthesis/plan")
async def plan_retrosynthesis(request: RetrosynthesisRequest):
    """
    Generate retrosynthesis routes using tree-based search.
    
    Returns multiple disconnection strategies ranked by feasibility.
    """
    try:
        from services.retrosynthesis_engine import RetrosynthesisEngine
        
        engine = RetrosynthesisEngine()
        
        routes = engine.search_routes(
            target_smiles=request.target_smiles,
            max_depth=request.max_depth,
            max_routes=request.max_routes,
            beam_width=5
        )
        
        return {
            'status': 'success',
            'target_smiles': request.target_smiles,
            'num_routes': len(routes),
            'routes': routes
        }
        
    except Exception as e:
        logging.error(f"Retrosynthesis planning failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


class ScaleOptimizationRequest(BaseModel):
    reaction: Dict[str, Any]
    target_scale: str = "lab"  # "lab", "pilot", or "industrial"
    batch_size_kg: float = 0.1

@api_router.post("/scale/optimize")
async def optimize_for_scale(request: ScaleOptimizationRequest):
    """
    Optimize reaction parameters for specific production scale.
    
    Returns scale-adjusted conditions, yield predictions, and recommendations.
    """
    try:
        from services.scale_aware_optimizer import ScaleAwareOptimizer
        
        optimizer = ScaleAwareOptimizer()
        
        # Validate scale
        if request.target_scale not in ['lab', 'pilot', 'industrial']:
            raise HTTPException(
                status_code=400,
                detail="target_scale must be 'lab', 'pilot', or 'industrial'"
            )
        
        result = optimizer.optimize_for_scale(
            reaction=request.reaction,
            target_scale=request.target_scale,
            batch_size_kg=request.batch_size_kg
        )
        
        return {
            'status': 'success',
            'optimization': result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Scale optimization failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


class IndustrialCostRequest(BaseModel):
    reaction: Dict[str, Any]
    scale: str = "lab"
    batch_size_kg: float = 0.1
    include_recovery: bool = False



# ============ PHASE 5: PROCESS CONSTRAINTS ENDPOINT ============

class ProcessConstraintsRequest(BaseModel):
    reaction: Dict[str, Any]
    scale: str = "lab"
    batch_size_kg: float = 0.1

@api_router.post("/constraints/evaluate")
async def evaluate_process_constraints(request: ProcessConstraintsRequest):
    """
    Evaluate physical realism and process constraints for a reaction.
    
    Returns thermal, mixing, mass transfer, safety, and purification analysis
    with actionable recommendations.
    """
    try:
        from services.process_constraints_engine import ProcessConstraintsEngine
        
        engine = ProcessConstraintsEngine()
        
        constraints = engine.evaluate_reaction_constraints(
            reaction=request.reaction,
            scale=request.scale,
            batch_size_kg=request.batch_size_kg
        )
        
        return {
            'status': 'success',
            'scale': request.scale,
            'batch_size_kg': request.batch_size_kg,
            'constraints': {
                'heat_risk': constraints.heat_risk,
                'heat_score': constraints.heat_score,
                'mixing_efficiency': constraints.mixing_efficiency,
                'mixing_score': constraints.mixing_score,
                'mass_transfer': constraints.mass_transfer,
                'mass_transfer_score': constraints.mass_transfer_score,
                'safety_risk': constraints.safety_risk,
                'safety_score': constraints.safety_score,
                'purification_difficulty': constraints.purification_difficulty,
                'purification_score': constraints.purification_score,
                'phase_complexity': constraints.phase_complexity,
                'total_penalty': constraints.total_penalty
            },
            'recommendations': constraints.recommendations,
            'equipment_requirements': constraints.equipment_requirements
        }
        
    except Exception as e:
        logging.error(f"Process constraints evaluation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/cost/industrial")
async def calculate_industrial_cost(request: IndustrialCostRequest):
    """
    Calculate comprehensive industrial cost including reagents, energy, labor, equipment, and waste.
    
    Returns detailed cost breakdown with recovery savings if enabled.
    """
    try:
        from services.advanced_cost_model import AdvancedCostModel
        
        cost_model = AdvancedCostModel()
        
        costs = cost_model.calculate_total_cost(
            reaction=request.reaction,
            scale=request.scale,
            batch_size_kg=request.batch_size_kg,
            include_recovery=request.include_recovery
        )
        
        return {
            'status': 'success',
            'scale': request.scale,
            'batch_size_kg': request.batch_size_kg,
            'costs': costs
        }
        
    except Exception as e:
        logging.error(f"Industrial cost calculation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ============ PHASE 6 OPTIMIZATION LAYER ENDPOINTS ============

class RouteMutationRequest(BaseModel):
    route: Dict[str, Any]
    mutation_types: Optional[List[str]] = None  # ["catalyst_swap", "solvent_optimization", "temperature_tune", "all"]

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
    objective: str = "balanced"  # "pharma", "cost", "green", "speed", "balanced"
    optimization_iterations: int = 3
    top_k: int = 5
    early_stop_threshold: float = 0.5
    pharma_mode: bool = False


@api_router.post("/routes/mutate")
async def mutate_route(request: RouteMutationRequest):
    """
    Apply route mutations: catalyst swapping, solvent optimization, temperature tuning.
    
    Returns the mutated route with improvement tracking.
    """
    try:
        if not route_optimizer:
            raise HTTPException(status_code=503, detail="Route optimizer not initialized")
        
        mutated = route_optimizer.mutate_route(
            route=request.route,
            mutation_types=request.mutation_types
        )
        
        return {
            'status': 'success',
            'original_route': request.route,
            'mutated_route': mutated,
            'mutations_applied': mutated.get('mutations_applied', []),
            'mutation_count': mutated.get('mutation_count', 0)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Route mutation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/routes/constraint-feedback")
async def constraint_feedback(request: ConstraintFeedbackRequest):
    """
    Evaluate constraints and auto-fix issues.
    
    If heat_risk=high → reduce temperature
    If mixing_issue → change solvent
    If safety_risk=high → reduce batch size
    """
    try:
        if not route_optimizer:
            raise HTTPException(status_code=503, detail="Route optimizer not initialized")
        
        feedback = route_optimizer.apply_constraint_feedback(
            reaction=request.reaction,
            scale=request.scale,
            batch_size_kg=request.batch_size_kg
        )
        
        return {
            'status': 'success',
            'original_constraints': feedback.original_constraints,
            'applied_fixes': feedback.applied_fixes,
            'improved_constraints': feedback.improved_constraints,
            'improvement_summary': feedback.improvement_summary,
            'num_fixes': len(feedback.applied_fixes)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Constraint feedback failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/routes/confidence")
async def calculate_confidence(request: ConfidenceScoreRequest):
    """
    Calculate route confidence/reliability score with risk assessment.
    """
    try:
        if not route_optimizer:
            raise HTTPException(status_code=503, detail="Route optimizer not initialized")
        
        confidence = route_optimizer.calculate_confidence(
            route=request.route,
            mcts_visits=request.mcts_visits
        )
        
        return {
            'status': 'success',
            'overall_confidence': confidence.overall_confidence,
            'yield_confidence': confidence.yield_confidence,
            'cost_confidence': confidence.cost_confidence,
            'safety_confidence': confidence.safety_confidence,
            'equipment_feasibility': confidence.equipment_feasibility,
            'risk_level': confidence.risk_level,
            'risk_factors': confidence.risk_factors,
            'reliability_breakdown': confidence.reliability_breakdown
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Confidence calculation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/routes/equipment-check")
async def check_equipment(request: EquipmentFeasibilityRequest):
    """
    Check if route steps can be executed with available equipment.
    Hard constraints: reject if equipment unavailable.
    """
    try:
        if not route_optimizer:
            raise HTTPException(status_code=503, detail="Route optimizer not initialized")
        
        feasibility = route_optimizer.check_equipment_feasibility(
            route=request.route
        )
        
        return {
            'status': 'success',
            **feasibility
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Equipment check failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/routes/optimize")
async def full_route_optimization(request: FullOptimizationRequest):
    """
    Full optimization pipeline: mutations + constraint feedback + confidence + equipment check.
    
    Runs the complete optimization layer on a route.
    """
    try:
        if not route_optimizer:
            raise HTTPException(status_code=503, detail="Route optimizer not initialized")
        
        result = {
            'status': 'success',
            'original_route': request.route,
        }
        
        current_route = request.route
        
        # 1. Apply mutations
        if request.apply_mutations:
            mutated = route_optimizer.mutate_route(current_route, request.mutation_types)
            result['mutations'] = {
                'applied': mutated.get('mutations_applied', []),
                'count': mutated.get('mutation_count', 0)
            }
            current_route = mutated
        
        # 2. Constraint feedback
        if request.check_constraints:
            steps = current_route.get('steps', [])
            if steps and isinstance(steps[0], dict):
                reaction = steps[0].get('conditions', steps[0])
            else:
                reaction = current_route
            
            feedback = route_optimizer.apply_constraint_feedback(reaction)
            result['constraint_feedback'] = {
                'original': feedback.original_constraints,
                'fixes': feedback.applied_fixes,
                'improved': feedback.improved_constraints,
                'summary': feedback.improvement_summary
            }
        
        # 3. Confidence scoring
        if request.calculate_confidence:
            confidence = route_optimizer.calculate_confidence(current_route)
            result['confidence'] = {
                'overall': confidence.overall_confidence,
                'risk_level': confidence.risk_level,
                'risk_factors': confidence.risk_factors,
                'breakdown': {
                    'yield': confidence.yield_confidence,
                    'cost': confidence.cost_confidence,
                    'safety': confidence.safety_confidence,
                    'equipment': confidence.equipment_feasibility
                }
            }
        
        # 4. Equipment binding
        if request.check_equipment:
            feasibility = route_optimizer.check_equipment_feasibility(current_route)
            result['equipment'] = feasibility
        
        result['optimized_route'] = current_route
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Full optimization failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/routes/iterative-optimize")
async def iterative_optimization(request: IterativeOptimizationRequest):
    """
    Phase 7: Iterative Optimization Convergence Loop.
    
    Runs: search → improve → re-search → converge → best possible route
    
    Supports objectives: pharma, cost, green, speed, balanced
    Includes early stopping, pharma mode, and improvement tracking.
    """
    try:
        if not convergence_engine:
            raise HTTPException(status_code=503, detail="Convergence engine not initialized")
        
        if not request.routes:
            raise HTTPException(status_code=400, detail="At least one route required")
        
        result = convergence_engine.optimize(
            routes=request.routes,
            objective=request.objective,
            max_iterations=request.optimization_iterations,
            top_k=request.top_k,
            early_stop_threshold=request.early_stop_threshold,
            pharma_mode=request.pharma_mode,
        )
        
        return {
            'status': result.status,
            'objective': result.objective,
            'pharma_mode': result.pharma_mode,
            'total_iterations': result.total_iterations,
            'total_improvement': result.total_improvement,
            'initial_score': result.initial_score,
            'final_score': result.final_score,
            'early_stopped': result.early_stopped,
            'early_stop_reason': result.early_stop_reason,
            'convergence_history': result.convergence_history,
            'best_routes': result.best_routes,
            'total_duration_ms': result.total_duration_ms,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Iterative optimization failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()