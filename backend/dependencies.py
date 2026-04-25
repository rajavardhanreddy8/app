"""
Singleton service instances shared across all routers.

Import from here instead of creating new instances in each router.
"""

import os
import logging
from fastapi import Header, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorClient

from services.molecular_service import MolecularService
from services.condition_predictor import ConditionPredictor
from services.enhanced_route_scorer import EnhancedRouteScorer
from services.template_extractor import TemplateExtractor
from services.equipment_recommender import EquipmentRecommender
from services.process_constraints_engine import ProcessConstraintsEngine

logger = logging.getLogger(__name__)

# ── API key auth ──
API_KEY = os.getenv("API_KEY", None)

def verify_api_key(x_api_key: str = Header(None)) -> str:
    """Validate X-API-Key header.

    If API_KEY env var is not set → dev mode, skip auth entirely.
    If set → require header to match exactly, else 401.
    """
    if API_KEY is None:
        return "dev_mode"
    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Pass X-API-Key header.",
        )
    return x_api_key


# ── MongoDB ──
class MockCollection:
    async def insert_one(self, doc): return True
    def find(self, *args, **kwargs):
        class Cursor:
            def sort(self, *args): return self
            def limit(self, *args): return self
            async def to_list(self, *args): return []
        return Cursor()
    async def count_documents(self, *args): return 0

class MockDatabase:
    def __getattr__(self, name): return MockCollection()

class Dependencies:
    def __init__(self):
        self.mongo_client = None
        self.db = MockDatabase() # Default to mock
        self.molecular_service = MolecularService()
        self.condition_predictor = ConditionPredictor()
        self.route_scorer = EnhancedRouteScorer()
        self.template_extractor = TemplateExtractor()
        self.equipment_recommender = EquipmentRecommender()
        self.constraints_engine = ProcessConstraintsEngine()
        
        # Lazy-init services
        self.orchestrator = None
        self.copilot_service = None
        self.route_optimizer = None
        self.convergence_engine = None
        self.yield_engine = None
        self.learning_engine = None
        self.yield_predictor = None
        
        # Load models
        self.condition_predictor.load_models()
        self.template_extractor.load_templates()

deps = Dependencies()

async def init_db():
    try:
        mongo_url = os.getenv('MONGODB_URL', 'mongodb://localhost:27017')
        deps.mongo_client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=2000)
        # Verify connection
        await deps.mongo_client.server_info()
        deps.db = deps.mongo_client.rxn_planner
        logging.info("✓ Connected to MongoDB")
    except Exception as e:
        logging.warning(f"✗ MongoDB unavailable ({e}), using in-memory mock")
        deps.db = MockDatabase()

# ── Lazy-init services (set during startup event) ──
# These are exposed at the module level for backward compatibility with router imports.
# Routers should ideally use `deps.service_name`.
db = deps.db
molecular_service = deps.molecular_service
condition_predictor = deps.condition_predictor
route_scorer = deps.route_scorer
template_extractor = deps.template_extractor
equipment_recommender = deps.equipment_recommender
constraints_engine = deps.constraints_engine

orchestrator = None
copilot_service = None
route_optimizer = None
convergence_engine = None
yield_engine = None
learning_engine = None
yield_predictor = None
