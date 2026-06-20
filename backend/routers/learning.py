"""Learning engine, feedback, and retraining routes."""

import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from dependencies import deps, verify_api_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["learning"], dependencies=[Depends(verify_api_key)])


class FeedbackIngestionRequest(BaseModel):
    predicted_route_id: Optional[str] = None
    actual_yield_percent: float
    actual_temperature_c: Optional[float] = None
    actual_time_hours: Optional[float] = None
    failures: List[str] = []
    deviations: List[str] = []
    equipment_performance: Dict[str, Any] = {}
    mutation_history: List[Any] = []
    source: str = "manual"
    verified: Optional[bool] = None
    timestamp: Optional[str] = None


class RetrainRequest(BaseModel):
    reason: str = "manual"


@router.post("/feedback/ingest")
async def ingest_feedback(request: FeedbackIngestionRequest):
    """Ingest real-world process feedback for closed-loop learning."""
    if not deps.learning_engine:
        raise HTTPException(status_code=503, detail="Learning engine not initialized")
    try:
        result = await deps.learning_engine.ingest_feedback(request.model_dump())
        priorities = await deps.learning_engine.mutation_priorities()
        if deps.yield_engine and priorities:
            deps.yield_engine.set_mutation_priorities(priorities)
        return {
            "status": "success", "feedback_id": result.feedback_id,
            "verified": result.verified, "outlier_score": result.outlier_score,
            "retrain_triggered": result.retrain_triggered,
            "model_versions": result.model_versions,
            "mutation_priorities": priorities,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Feedback ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/learning/retrain")
async def trigger_manual_retraining(request: RetrainRequest = RetrainRequest()):
    """Manually trigger model retraining."""
    if not deps.learning_engine:
        raise HTTPException(status_code=503, detail="Learning engine not initialized")
    try:
        versions = await deps.learning_engine.trigger_retraining(reason=request.reason)
        return {"status": "success", "message": "Retraining triggered", "versions": versions}
    except Exception as e:
        logger.error(f"Retraining failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/models/retrain")
async def retrain_models(request: RetrainRequest):
    """Manual model retraining trigger with version bump."""
    if not deps.learning_engine:
        raise HTTPException(status_code=503, detail="Learning engine not initialized")
    try:
        versions = await deps.learning_engine.trigger_retraining(reason=request.reason)
        return {"status": "success", "versions": versions}
    except Exception as e:
        logger.error(f"Manual retraining failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/routes/impurity-analysis")
async def analyze_route_impurities(payload: Dict[str, Any]):
    """Analyze byproduct propagation and ICH M7 GTI flags for a route."""
    try:
        from services.impurity_tracker import ImpurityTracker

        route = payload.get("route", payload)
        return {
            "status": "success",
            "impurity_analysis": ImpurityTracker().propagate_route(route),
        }
    except Exception as e:
        logger.error(f"Impurity analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/learning/status")
async def learning_status():
    """Closed-loop learning status and memory diagnostics."""
    if not deps.learning_engine:
        raise HTTPException(status_code=503, detail="Learning engine not initialized")
    try:
        total = await deps.db.feedback.count_documents({})
        verified = await deps.db.feedback.count_documents({"verified": True})
        priorities = await deps.learning_engine.mutation_priorities()
        latest_versions = {}
        for model in deps.learning_engine.model_names:
            latest = await deps.db.model_versions.find_one({"model": model}, sort=[("created_at", -1)])
            latest_versions[model] = latest["version"] if latest else "v0"
        threshold = deps.learning_engine.config.min_samples_required
        return {
            "status": "success",
            "feedback": {"total": total, "verified": verified,
                         "retrain_threshold": threshold},
            "models": latest_versions,
            "mutation_priorities": priorities,
        }
    except Exception as e:
        logger.error(f"Learning status failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
