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
async def get_status_checks():
    # Exclude MongoDB's _id field from the query results
    status_checks = await db.status_checks.find({}, {"_id": 0}).to_list(1000)
    
    # Convert ISO string timestamps back to datetime objects
    for check in status_checks:
        if isinstance(check['timestamp'], str):
            check['timestamp'] = datetime.fromisoformat(check['timestamp'])
    
    return status_checks

# ============ CHEMISTRY SYNTHESIS ENDPOINTS ============

@api_router.post("/synthesis/plan", response_model=SynthesisResponse)
async def plan_synthesis(request: SynthesisRequest):
    """
    Plan synthesis routes for a target molecule.
    
    Returns multiple routes ranked by yield, cost, and complexity.
    """
    global orchestrator
    
    # Initialize orchestrator if not done
    if orchestrator is None:
        api_key = os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="ANTHROPIC_API_KEY not configured. Please add it to environment variables."
            )
        orchestrator = SynthesisPlanningOrchestrator(api_key=api_key)
    
    try:
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
    
    Returns routes ranked by score with detailed metrics.
    """
    try:
        from models.chemistry import SynthesisRoute
        
        # Convert dict routes to SynthesisRoute objects
        route_objects = []
        for route_data in request.routes:
            try:
                route = SynthesisRoute(**route_data)
                route_objects.append(route)
            except:
                continue
        
        if not route_objects:
            raise HTTPException(status_code=400, detail="No valid routes provided")
        
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