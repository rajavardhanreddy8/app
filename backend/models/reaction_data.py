from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid

class ReactionData(BaseModel):
    """Represents a chemical reaction from USPTO or ORD database."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    reaction_smiles: str = Field(..., description="Reaction SMILES (reactants>>products)")
    reactants: List[str] = Field(default_factory=list)
    products: List[str] = Field(default_factory=list)
    reagents: List[str] = Field(default_factory=list)
    
    # Reaction metadata
    reaction_type: Optional[str] = None
    source: str = Field(..., description="USPTO or ORD")
    patent_id: Optional[str] = None
    
    # Conditions
    temperature_celsius: Optional[float] = None
    pressure_atm: Optional[float] = None
    solvent: Optional[str] = None
    catalyst: Optional[str] = None
    time_hours: Optional[float] = None
    
    # Yields
    yield_percent: Optional[float] = Field(None, ge=0, le=100)
    conversion: Optional[float] = None
    selectivity: Optional[float] = None
    
    # Classification
    reaction_class: Optional[str] = None
    functional_groups: Optional[List[str]] = None
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    validated: bool = False

class ReactionTemplate(BaseModel):
    """Extracted reaction template for retrosynthesis."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    reaction_type: str
    template_smarts: str = Field(..., description="SMARTS pattern for the reaction")
    
    # Statistics from data
    num_examples: int = Field(0, description="Number of examples in dataset")
    avg_yield: float = Field(0.0, description="Average yield from examples")
    std_yield: float = Field(0.0, description="Standard deviation of yields")
    
    # Conditions
    common_solvents: List[str] = Field(default_factory=list)
    common_catalysts: List[str] = Field(default_factory=list)
    typical_temp_range: Optional[tuple] = None
    
    # Classification
    difficulty: str = Field("moderate", description="easy, moderate, or difficult")
    reliability: float = Field(0.5, description="Reliability score 0-1")
    
    created_at: datetime = Field(default_factory=datetime.utcnow)

class ReagentCost(BaseModel):
    """Reagent cost information."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    smiles: str
    name: Optional[str] = None
    cas_number: Optional[str] = None
    
    # Pricing (USD per gram)
    price_per_gram: float
    price_per_kg: Optional[float] = None
    
    # Availability
    supplier: str
    catalog_number: Optional[str] = None
    availability: str = Field("in_stock", description="in_stock, backorder, discontinued")
    
    # Metadata
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    source: str = Field("manual", description="Source of pricing data")
