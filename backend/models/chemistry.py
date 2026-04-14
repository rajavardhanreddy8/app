from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid

class MolecularStructure(BaseModel):
    """Represents a molecular structure."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    smiles: str = Field(..., description="SMILES representation of the molecule")
    name: Optional[str] = Field(None, description="IUPAC name or common name")
    molecular_weight: Optional[float] = None
    properties: Optional[Dict[str, Any]] = None
    
    @field_validator('smiles')
    @classmethod
    def validate_smiles(cls, v):
        """Validate SMILES string format."""
        if not v or len(v) == 0:
            raise ValueError("SMILES string cannot be empty")
        return v.strip()

class ReactionCondition(BaseModel):
    """Represents reaction conditions."""
    temperature_celsius: Optional[float] = Field(None, ge=-273.15)
    pressure_atm: Optional[float] = Field(1.0, ge=0.01)
    solvent: Optional[str] = None
    catalyst: Optional[str] = None
    time_hours: Optional[float] = Field(None, gt=0)
    additional_conditions: Optional[Dict[str, Any]] = None

class ReactionStep(BaseModel):
    """Represents a single reaction step."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    reactants: List[MolecularStructure]
    product: MolecularStructure
    reaction_type: str
    conditions: Optional[ReactionCondition] = None
    estimated_yield_percent: float = Field(..., ge=0, le=100)
    estimated_cost_usd: Optional[float] = None
    difficulty: Optional[str] = None  # 'easy', 'moderate', 'difficult'
    notes: Optional[str] = None

class SynthesisRoute(BaseModel):
    """Complete synthesis route from starting material to target."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    target_molecule: MolecularStructure
    starting_materials: List[MolecularStructure]
    steps: List[ReactionStep]
    overall_yield_percent: float = Field(..., ge=0, le=100)
    yield_uncertainty: Optional[Dict[str, Any]] = None
    total_cost_usd: float
    total_time_hours: float
    score: float  # Multi-objective score
    created_at: datetime = Field(default_factory=datetime.utcnow)
    notes: Optional[str] = None

class SynthesisRequest(BaseModel):
    """Request for synthesis planning."""
    target_smiles: str = Field(..., description="Target molecule in SMILES format")
    starting_materials: Optional[List[str]] = Field(None, description="Optional starting material SMILES")
    max_steps: int = Field(5, ge=1, le=10, description="Maximum number of synthesis steps")
    optimize_for: str = Field("balanced", description="Optimization goal: 'yield', 'cost', 'time', or 'balanced'")
    constraints: Optional[Dict[str, Any]] = None

class SynthesisResponse(BaseModel):
    """Response containing synthesis routes."""
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    target_smiles: str
    routes: List[SynthesisRoute]
    computation_time_seconds: float
    tokens_used: Optional[int] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
