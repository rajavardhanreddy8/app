"""Equipment and template routes."""

import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

from dependencies import verify_api_key
import dependencies as deps

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["equipment"], dependencies=[Depends(verify_api_key)])


class EquipmentRequest(BaseModel):
    reaction_type: str
    scale_mg: float
    temperature_c: Optional[float] = None
    pressure_atm: Optional[float] = None


@router.get("/templates/stats")
async def get_template_statistics():
    """Get reaction template database statistics."""
    try:
        return {'status': 'success', 'statistics': deps.template_extractor.get_statistics()}
    except Exception as e:
        logger.error(f"Template stats failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates/{reaction_type}")
async def get_templates_by_type(reaction_type: str):
    """Get templates for a specific reaction type."""
    try:
        templates = deps.template_extractor.get_templates_for_reaction_type(reaction_type)
        if templates:
            return {'status': 'success', 'reaction_type': reaction_type, 'templates': templates}
        raise HTTPException(status_code=404, detail=f"No templates found for {reaction_type}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Template retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/equipment/recommend")
async def recommend_equipment(request: EquipmentRequest):
    """Recommend laboratory equipment for a reaction."""
    try:
        recommendations = deps.equipment_recommender.recommend_reactor(
            reaction_type=request.reaction_type, scale_mg=request.scale_mg,
            temperature_c=request.temperature_c, pressure_atm=request.pressure_atm)
        complete_setup = deps.equipment_recommender.recommend_complete_setup(
            reaction_type=request.reaction_type, scale_mg=request.scale_mg,
            temperature_c=request.temperature_c)
        return {'status': 'success', 'reactor_recommendations': recommendations,
                'complete_setup': complete_setup}
    except Exception as e:
        logger.error(f"Equipment recommendation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
