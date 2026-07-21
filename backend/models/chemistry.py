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
    solvent_volume_ml: Optional[float] = Field(None, ge=0)
    concentration_m: Optional[float] = Field(None, ge=0)
    catalyst_loading_mol_percent: Optional[float] = Field(None, ge=0)
    additional_conditions: Optional[Dict[str, Any]] = None

class ReactionStep(BaseModel):
    """Represents a single reaction step."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    reactants: List[MolecularStructure]
    product: MolecularStructure
    reaction_type: str
    conditions: Optional[ReactionCondition] = None
    estimated_yield_percent: float = Field(..., ge=0, le=100)
    estimated_yield: Optional[float] = Field(None, ge=0, le=100)
    estimated_cost_usd: Optional[float] = None
    difficulty: Optional[str] = None  # 'easy', 'moderate', 'difficult'
    notes: Optional[str] = None
    reactant_quantities: Optional[List[Dict[str, Any]]] = None
    catalyst_loading: Optional[str] = None
    solvent_amount: Optional[str] = None
    concentration_m: Optional[float] = None
    batch_scale: Optional[str] = None
    cost_drivers: Optional[List[str]] = None
    feasibility_notes: Optional[List[str]] = None
    sanity_flags: Optional[List[str]] = None
    catalyst_intelligence: Optional[Dict[str, Any]] = None
    safety_warnings: Optional[List[str]] = None
    evidence: Optional[Dict[str, Any]] = None
    prediction_source: Optional[Dict[str, Any]] = None
    confidence: Optional[str] = None
    uncertainty: Optional[Dict[str, Any]] = None
    warnings: Optional[List[str]] = None
    review_status: str = "needs_human_review"
    human_review_required: bool = True

class SynthesisRoute(BaseModel):
    """Complete synthesis route from starting material to target."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    target_molecule: MolecularStructure
    starting_materials: List[MolecularStructure]
    steps: List[ReactionStep]
    overall_yield_percent: float = Field(..., ge=0, le=100)
    overall_yield: Optional[float] = Field(None, ge=0, le=100)
    total_cost_usd: float
    total_time_hours: float
    score: float  # Multi-objective score
    created_at: datetime = Field(default_factory=datetime.utcnow)
    notes: Optional[str] = None
    scale: Optional[str] = None
    batch_size_kg: Optional[float] = None
    scale_adjusted_yield: Optional[float] = None
    scale_up_warnings: Optional[List[str]] = None
    green_metrics: Optional[Dict[str, Any]] = None
    impurity_analysis: Optional[Dict[str, Any]] = None
    telescoping: Optional[Dict[str, Any]] = None
    score_breakdown: Optional[Dict[str, Any]] = None
    improvement_targets: Optional[List[str]] = None
    llm_metadata: Optional[Dict[str, Any]] = None
    evidence: Optional[Dict[str, Any]] = None
    prediction_source: Optional[Dict[str, Any]] = None
    confidence: Optional[str] = None
    uncertainty: Optional[Dict[str, Any]] = None
    warnings: Optional[List[str]] = None
    review_status: str = "needs_human_review"
    human_review_required: bool = True
    industrial_acceptability: Optional[Dict[str, Any]] = None
    byproduct_analysis: Optional[Dict[str, Any]] = None

class SynthesisRequest(BaseModel):
    """Request for synthesis planning."""
    target_smiles: str = Field(..., description="Target molecule in SMILES format")
    starting_materials: Optional[List[str]] = Field(None, description="Optional starting material SMILES")
    max_steps: int = Field(5, ge=1, le=10, description="Maximum number of synthesis steps")
    optimize_for: str = Field("balanced", description="Optimization goal: 'yield', 'cost', 'time', 'green', 'regulatory', or 'balanced'")
    batch_size_kg: float = 0.1
    scale: str = "lab"
    stage: str = "phase_2"
    include_green_metrics: bool = True
    include_impurity_analysis: bool = True
    include_telescoping: bool = True
    constraints: Optional[Dict[str, Any]] = None

class SynthesisResponse(BaseModel):
    """Response containing synthesis routes."""
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    target_smiles: str
    routes: List[SynthesisRoute]
    computation_time_seconds: float
    tokens_used: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
