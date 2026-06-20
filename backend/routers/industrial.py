"""Industrial acceptability API endpoints — Phase 11."""

import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

from dependencies import verify_api_key

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/industrial",
    tags=["industrial"],
    dependencies=[Depends(verify_api_key)],
)


class IndustrialAcceptabilityRequest(BaseModel):
    route: Dict[str, Any] = Field(..., description="Fully-enriched route dict")
    mode:  str            = Field("pharma", description="Evaluation mode: pharma|cost|balanced|green|speed")


@router.post("/acceptability")
async def evaluate_industrial_acceptability(body: IndustrialAcceptabilityRequest):
    """
    Evaluate a synthesis route for industrial acceptability.

    Returns full IndustrialAcceptabilityEngine classification including
    effective cost, rejection reasons, AR&D plan, and acceptability score.
    """
    try:
        from services.industrial_acceptability_engine import IndustrialAcceptabilityEngine
        engine = IndustrialAcceptabilityEngine()
        result = engine.evaluate(route=body.route, mode=body.mode)
        return result
    except ImportError as exc:
        logger.error("industrial_acceptability_engine not found: %s", exc)
        raise HTTPException(status_code=500, detail="IndustrialAcceptabilityEngine unavailable")
    except Exception as exc:
        logger.error("industrial_acceptability_error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/ard/route")
async def route_to_ard(body: IndustrialAcceptabilityRequest):
    """
    Evaluate a route AND return the full AR&D routing plan.

    Returns acceptability result with embedded ard_plan showing
    priority, optimization targets, and recommended sequence.
    """
    try:
        from services.industrial_acceptability_engine import IndustrialAcceptabilityEngine
        engine = IndustrialAcceptabilityEngine()
        result = engine.evaluate(route=body.route, mode=body.mode)
        return result
    except Exception as exc:
        logger.error("ard_routing_error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
