"""Molecule validation and analysis routes."""

import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from dependencies import verify_api_key
import dependencies as deps

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["molecule"], dependencies=[Depends(verify_api_key)])


class MoleculeValidationRequest(BaseModel):
    smiles: str


@router.post("/molecule/validate")
async def validate_molecule(request: MoleculeValidationRequest):
    """Validate a SMILES string for chemical correctness."""
    try:
        return deps.molecular_service.validate_smiles(request.smiles)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/molecule/analyze")
async def analyze_molecule(request: MoleculeValidationRequest):
    """Analyze a molecule and return detailed properties."""
    try:
        analysis = deps.molecular_service.parse_smiles(request.smiles)
        if not analysis.get("valid"):
            raise HTTPException(status_code=400, detail=analysis.get("error"))
        return analysis
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
