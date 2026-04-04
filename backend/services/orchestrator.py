import os
import sys
import logging
import structlog
import time
from typing import Dict, Any
from models.chemistry import SynthesisRequest, SynthesisResponse
from services.claude_service import ClaudeService
from services.molecular_service import MolecularService  
from services.synthesis_planner import SynthesisPlanner

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logger = structlog.get_logger()

class SynthesisPlanningOrchestrator:
    """Orchestrates the complete synthesis planning workflow."""
    
    def __init__(self, api_key: str = None):
        self.claude_service = ClaudeService(api_key=api_key)
        self.molecular_service = MolecularService()
        self.synthesis_planner = SynthesisPlanner()
        
    async def plan_synthesis(self, request: SynthesisRequest) -> SynthesisResponse:
        """Complete synthesis planning workflow."""
        
        start_time = time.time()
        
        logger.info(
            "starting_synthesis_planning",
            target_smiles=request.target_smiles,
            max_steps=request.max_steps,
            optimize_for=request.optimize_for
        )
        
        # Step 1: Validate target molecule
        validation = self.molecular_service.validate_smiles(request.target_smiles)
        if not validation.get("valid"):
            raise ValueError(f"Invalid target SMILES: {validation.get('reason')}")
        
        # Step 2: Request synthesis plan from Claude
        claude_response = await self.claude_service.plan_synthesis(
            target_smiles=request.target_smiles,
            starting_materials=request.starting_materials,
            max_steps=request.max_steps,
            optimize_for=request.optimize_for
        )
        
        # Step 3: Parse Claude's response
        parsed_data = self.synthesis_planner.parse_claude_response(
            claude_response["content"]
        )
        
        # Step 4: Build structured synthesis routes
        routes = []
        if parsed_data:
            routes = self.synthesis_planner.build_synthesis_routes(
                target_smiles=request.target_smiles,
                claude_response=parsed_data,
                optimize_for=request.optimize_for
            )
        
        # Step 5: Create response
        computation_time = time.time() - start_time
        
        response = SynthesisResponse(
            target_smiles=request.target_smiles,
            routes=routes,
            computation_time_seconds=round(computation_time, 2),
            tokens_used=claude_response["usage"]["total_tokens"]
        )
        
        logger.info(
            "synthesis_planning_complete",
            num_routes=len(routes),
            computation_time=computation_time,
            tokens_used=response.tokens_used
        )
        
        return response
