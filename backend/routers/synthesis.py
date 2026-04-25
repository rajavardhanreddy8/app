"""Synthesis and retrosynthesis routes."""

import os
import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

from dependencies import deps, verify_api_key
from models.chemistry import SynthesisRequest, SynthesisResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["synthesis"], dependencies=[Depends(verify_api_key)])



class RetrosynthesisRequest(BaseModel):
    target_smiles: str
    max_depth: int = 5
    max_routes: int = 5


@router.post("/synthesis/plan", response_model=SynthesisResponse)
async def plan_synthesis(
    request: SynthesisRequest,
    use_advanced: bool = False,
    scale: str = "lab",
    batch_size_kg: float = 0.1,
    pharma_mode: bool = False,
    use_mcts: bool = False,
):
    """Plan synthesis routes for a target molecule."""
    from services.orchestrator import SynthesisPlanningOrchestrator

    if deps.orchestrator is None:
        api_key = os.getenv('ANTHROPIC_API_KEY')
        demo_mode = os.getenv('DEMO_MODE', 'false').lower() == 'true'
        if not api_key and not demo_mode:
            raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured.")
        deps.orchestrator = SynthesisPlanningOrchestrator(api_key=api_key, db=deps.db)

    try:
        if use_advanced:
            result = await deps.orchestrator.plan_synthesis_advanced(
                request=request, num_routes=5, scale=scale,
                batch_size_kg=batch_size_kg, use_mcts=use_mcts, pharma_mode=pharma_mode,
            )
        else:
            result = await deps.orchestrator.plan_synthesis(request)

        doc = result.model_dump()
        doc['_id'] = doc['request_id']
        doc['timestamp'] = doc['timestamp'].isoformat()
        for route in doc.get('routes', []):
            if 'created_at' in route:
                route['created_at'] = route['created_at'].isoformat()
        try:
            await deps.db.synthesis_plans.insert_one(doc)
        except Exception as e:
            logger.warning(f"Failed to save synthesis plan to history (DB down?): {e}")
        
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Synthesis planning error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/synthesis/history")
async def get_synthesis_history(limit: int = 10):
    """Get recent synthesis planning requests."""
    try:
        history = await deps.db.synthesis_plans.find({}, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
        return {"history": history}
    except Exception as e:
        logger.warning(f"Failed to fetch history (DB may be down): {e}")
        return {"history": [], "status": "db_unavailable"}


@router.post("/retrosynthesis/plan")
async def plan_retrosynthesis(request: RetrosynthesisRequest):
    """Generate retrosynthesis routes using tree-based search."""
    try:
        from services.retrosynthesis_engine import RetrosynthesisEngine
        engine = RetrosynthesisEngine()
        routes = engine.search_routes(
            target_smiles=request.target_smiles,
            max_depth=request.max_depth,
            max_routes=request.max_routes,
            beam_width=5,
        )
        return {'status': 'success', 'target_smiles': request.target_smiles,
                'num_routes': len(routes), 'routes': routes}
    except Exception as e:
        logger.error(f"Retrosynthesis planning failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
