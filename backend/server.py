"""
Chemistry Synthesis Planning API — server entry point.

All endpoint logic lives in routers/. Service singletons live in dependencies.py.
"""

from fastapi import FastAPI
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List
import uuid
from datetime import datetime, timezone

from dependencies import deps
from routers import synthesis, molecule, optimization, equipment, learning

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# ── App ──
app = FastAPI(
    title="Chemistry Synthesis Planning API",
    description="AI-powered synthesis route planning using Claude Sonnet 4.5",
    version="2.0.0",
)

# ── Status-check models (kept here — tiny, server-level) ──
class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StatusCheckCreate(BaseModel):
    client_name: str

@app.post("/api/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    obj = StatusCheck(**input.model_dump())
    doc = obj.model_dump()
    doc['timestamp'] = doc['timestamp'].isoformat()
    await deps.db.status_checks.insert_one(doc)
    return obj

@app.get("/api/status", response_model=List[StatusCheck])
async def get_status_checks(limit: int = 100, skip: int = 0):
    checks = await deps.db.status_checks.find({}, {"_id": 0}).skip(skip).limit(min(limit, 1000)).to_list(min(limit, 1000))
    for c in checks:
        if isinstance(c['timestamp'], str):
            c['timestamp'] = datetime.fromisoformat(c['timestamp'])
    return checks

@app.get("/api/")
async def root():
    return {"message": "Chemistry Synthesis Planning API", "version": "2.0.0"}

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}

@app.get("/api/auth/verify")
async def auth_verify(x_api_key: str = None):
    """Public endpoint — verify API key status without triggering 401."""
    from dependencies import API_KEY, verify_api_key
    if API_KEY is None:
        return {"status": "dev_mode", "message": "No API_KEY configured — all requests accepted"}
    if x_api_key == API_KEY:
        return {"status": "valid", "mode": "authenticated"}
    return {"status": "invalid", "message": "Key provided but does not match"}

# ── Register routers ──
app.include_router(synthesis.router)
app.include_router(molecule.router)
app.include_router(optimization.router)
app.include_router(equipment.router)
app.include_router(learning.router)

# ── Startup ──
@app.on_event("startup")
async def startup_event():
    from dependencies import init_db
    await init_db()
    
    from services.orchestrator import SynthesisPlanningOrchestrator
    from services.route_optimizer import RouteOptimizer
    from services.convergence_engine import ConvergenceEngine
    from services.yield_optimization_engine import YieldOptimizationEngine
    from services.closed_loop_learning_engine import ClosedLoopLearningEngine, RetrainingConfig
    try:
        deps.route_optimizer = RouteOptimizer(constraints_engine=deps.constraints_engine, equipment_recommender=deps.equipment_recommender)
        deps.convergence_engine = ConvergenceEngine(route_optimizer=deps.route_optimizer, constraints_engine=deps.constraints_engine)
        deps.yield_engine = YieldOptimizationEngine(constraints_engine=deps.constraints_engine)
        from models import get_yield_predictor
        deps.yield_predictor = get_yield_predictor()
        deps.learning_engine = ClosedLoopLearningEngine(
            db=deps.db,
            yield_predictor=deps.yield_predictor,
            config=RetrainingConfig(min_samples_required=int(os.getenv("FEEDBACK_RETRAIN_THRESHOLD", "25")))
        )
        logging.info("✓ All engines initialized")
    except Exception as e:
        logging.error(f"✗ Engine init failed: {e}")
        deps.route_optimizer = RouteOptimizer()
        deps.convergence_engine = ConvergenceEngine(route_optimizer=deps.route_optimizer)
        deps.yield_engine = YieldOptimizationEngine()
        deps.learning_engine = ClosedLoopLearningEngine(db=deps.db)

@app.on_event("shutdown")
async def shutdown_db_client():
    if deps.mongo_client:
        deps.mongo_client.close()

# ── CORS ──
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','), allow_methods=["*"], allow_headers=["*"])

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')