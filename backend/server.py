from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List
import uuid
from datetime import datetime, timezone

# Import chemistry models and services
from models.chemistry import SynthesisRequest, SynthesisResponse, MolecularStructure
from services.orchestrator import SynthesisPlanningOrchestrator
from services.molecular_service import MolecularService

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Initialize services
orchestrator = None  # Will be initialized after env check
molecular_service = MolecularService()

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