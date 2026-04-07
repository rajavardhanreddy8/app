"""
Shared pytest fixtures for the AI Synthesis Route Planner test suite.
"""
import sys
import os
import pytest
from pathlib import Path

# Add backend to path so imports resolve
BACKEND_DIR = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

# Set env vars before any backend imports
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_database")
os.environ.setdefault("CORS_ORIGINS", "*")
os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test-placeholder")

from fastapi.testclient import TestClient
from server import app
from services.molecular_service import MolecularService
from services.condition_predictor import ConditionPredictor
from services.cost_database import CostDatabase
from services.equipment_recommender import EquipmentRecommender
from services.enhanced_route_scorer import EnhancedRouteScorer


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def test_client():
    """FastAPI TestClient — shared across all tests in the session."""
    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="session")
def molecular_service():
    return MolecularService()


@pytest.fixture(scope="session")
def condition_predictor():
    cp = ConditionPredictor(model_dir=str(BACKEND_DIR / "models"))
    cp.load_models()
    return cp


@pytest.fixture(scope="session")
def cost_database():
    return CostDatabase(cost_db_path=str(BACKEND_DIR / "data" / "reagent_costs.json"))


@pytest.fixture(scope="session")
def equipment_recommender():
    return EquipmentRecommender(equipment_db_path=str(BACKEND_DIR / "data" / "equipment.json"))


@pytest.fixture(scope="session")
def route_scorer():
    return EnhancedRouteScorer()


# ── Sample Data ───────────────────────────────────────────────────

@pytest.fixture(scope="session")
def sample_molecules():
    """Well-known molecules for testing."""
    return {
        "aspirin": "CC(=O)Oc1ccccc1C(=O)O",
        "caffeine": "CN1C=NC2=C1C(=O)N(C(=O)N2C)C",
        "ibuprofen": "CC(C)Cc1ccc(cc1)C(C)C(=O)O",
        "paracetamol": "CC(=O)Nc1ccc(O)cc1",
        "ethanol": "CCO",
        "benzene": "c1ccccc1",
    }


@pytest.fixture(scope="session")
def sample_reaction():
    """A standard Friedel-Crafts acylation reaction dict."""
    return {
        "reactants": ["c1ccccc1", "CC(=O)Cl"],
        "products": ["CC(=O)c1ccccc1"],
        "reaction_type": "Friedel-Crafts acylation",
    }


@pytest.fixture(scope="session")
def sample_esterification():
    """An esterification reaction dict."""
    return {
        "reactants": ["CC(=O)O", "CCO"],
        "products": ["CCOC(C)=O"],
        "reaction_type": "esterification",
    }
