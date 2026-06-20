"""Reaction quality API endpoints — Phase 12."""

import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Any, Dict

from dependencies import verify_api_key

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/reaction-quality",
    tags=["reaction-quality"],
    dependencies=[Depends(verify_api_key)],
)

class ReactionQualityRequest(BaseModel):
    route: Dict[str, Any] = Field(..., description="Fully-enriched route dict")
    pharma_mode: bool = Field(False, description="Apply strict pharma mode rejections")

@router.post("/evaluate")
async def evaluate_reaction_quality(body: ReactionQualityRequest):
    """
    Evaluate a synthesis route for byproducts, selectivity, reversibility, and impurity risk.
    """
    try:
        from services.byproduct_selectivity_engine import ByproductSelectivityEngine
        engine = ByproductSelectivityEngine()
        result = engine.evaluate(route_dict=body.route, pharma_mode=body.pharma_mode)
        return result
    except ImportError as exc:
        logger.error("byproduct_selectivity_engine not found: %s", exc)
        raise HTTPException(status_code=500, detail="ByproductSelectivityEngine unavailable")
    except Exception as exc:
        logger.error("reaction_quality_evaluate_error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
