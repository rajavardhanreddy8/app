"""
Chemistry Synthesis Planning API Tests
Phase 1 Stabilization - Testing existing functionality

Modules tested:
- API Health Check
- Molecule Validation & Analysis
- Synthesis Planning
- Condition Prediction
- Route Comparison
- LLM Copilot
- Template Statistics
- Equipment Recommendation
"""

import pytest
import requests
import os
import time

# Get backend URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://kinetics-predict.preview.emergentagent.com"

API_URL = f"{BASE_URL}/api"

# Test SMILES strings for chemical molecules
TEST_MOLECULES = {
    "aspirin": "CC(=O)Oc1ccccc1C(=O)O",
    "caffeine": "CN1C=NC2=C1C(=O)N(C(=O)N2C)C",
    "ibuprofen": "CC(C)Cc1ccc(cc1)C(C)C(=O)O",
    "paracetamol": "CC(=O)Nc1ccc(O)cc1",
    "benzene": "c1ccccc1",
    "ethanol": "CCO",
    "invalid": "INVALID_SMILES_STRING_XYZ"
}


class TestAPIHealth:
    """API Health Check Tests"""
    
    def test_api_root_returns_200(self):
        """Test that API root endpoint returns 200"""
        response = requests.get(f"{API_URL}/")
        assert response.status_code == 200
        print(f"✓ API root returns 200")
    
    def test_api_root_returns_correct_version(self):
        """Test that API returns correct version info"""
        response = requests.get(f"{API_URL}/")
        data = response.json()
        
        assert "version" in data
        assert data["version"] == "1.0.0"
        assert "message" in data
        assert "Chemistry Synthesis Planning API" in data["message"]
        print(f"✓ API version: {data['version']}")
    
    def test_api_root_returns_endpoints_list(self):
        """Test that API returns list of available endpoints"""
        response = requests.get(f"{API_URL}/")
        data = response.json()
        
        assert "endpoints" in data
        endpoints = data["endpoints"]
        assert "synthesis_plan" in endpoints
        assert "validate_molecule" in endpoints
        assert "analyze_molecule" in endpoints
        print(f"✓ API endpoints listed: {list(endpoints.keys())}")


class TestMoleculeValidation:
    """Molecule Validation Endpoint Tests"""
    
    def test_validate_valid_smiles_aspirin(self):
        """Test validation of valid SMILES (Aspirin)"""
        response = requests.post(
            f"{API_URL}/molecule/validate",
            json={"smiles": TEST_MOLECULES["aspirin"]}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] == True
        print(f"✓ Aspirin SMILES validated successfully")
    
    def test_validate_valid_smiles_caffeine(self):
        """Test validation of valid SMILES (Caffeine)"""
        response = requests.post(
            f"{API_URL}/molecule/validate",
            json={"smiles": TEST_MOLECULES["caffeine"]}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] == True
        print(f"✓ Caffeine SMILES validated successfully")
    
    def test_validate_invalid_smiles(self):
        """Test validation of invalid SMILES string"""
        response = requests.post(
            f"{API_URL}/molecule/validate",
            json={"smiles": TEST_MOLECULES["invalid"]}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] == False
        print(f"✓ Invalid SMILES correctly rejected")
    
    def test_validate_empty_smiles_returns_invalid(self):
        """Test validation with empty SMILES - Bug #1 Fixed: returns valid=False"""
        response = requests.post(
            f"{API_URL}/molecule/validate",
            json={"smiles": ""}
        )
        assert response.status_code == 200
        data = response.json()
        # Bug #1 Fixed: Empty SMILES now correctly returns valid=False
        assert data["valid"] == False
        assert "reason" in data
        print(f"✓ Empty SMILES correctly returns valid=False with reason: {data.get('reason')}")


class TestMoleculeAnalysis:
    """Molecule Analysis Endpoint Tests"""
    
    def test_analyze_aspirin(self):
        """Test analysis of Aspirin molecule"""
        response = requests.post(
            f"{API_URL}/molecule/analyze",
            json={"smiles": TEST_MOLECULES["aspirin"]}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify molecular properties are returned
        assert data["valid"] == True
        assert "molecular_weight" in data
        assert "logp" in data
        assert "h_donors" in data
        assert "h_acceptors" in data
        assert "tpsa" in data
        
        # Aspirin molecular weight should be ~180
        assert 175 < data["molecular_weight"] < 185
        print(f"✓ Aspirin analysis: MW={data['molecular_weight']}, LogP={data['logp']}")
    
    def test_analyze_caffeine(self):
        """Test analysis of Caffeine molecule"""
        response = requests.post(
            f"{API_URL}/molecule/analyze",
            json={"smiles": TEST_MOLECULES["caffeine"]}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["valid"] == True
        assert "molecular_formula" in data
        # Caffeine molecular weight should be ~194
        assert 190 < data["molecular_weight"] < 200
        print(f"✓ Caffeine analysis: MW={data['molecular_weight']}, Formula={data.get('molecular_formula')}")
    
    def test_analyze_invalid_smiles_returns_400(self):
        """Test analysis of invalid SMILES returns 400 error status"""
        response = requests.post(
            f"{API_URL}/molecule/analyze",
            json={"smiles": TEST_MOLECULES["invalid"]}
        )
        # Bug Fixed: Now correctly returns 400 with detail message
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        print(f"✓ Invalid SMILES analysis correctly returns 400 with error detail")


class TestSynthesisPlanning:
    """Synthesis Planning Endpoint Tests"""
    
    def test_synthesis_plan_aspirin(self):
        """Test synthesis planning for Aspirin"""
        response = requests.post(
            f"{API_URL}/synthesis/plan",
            json={
                "target_smiles": TEST_MOLECULES["aspirin"],
                "max_steps": 5,
                "optimize_for": "balanced"
            },
            timeout=60  # LLM calls may take time
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "request_id" in data
        assert "target_smiles" in data
        assert "routes" in data
        assert isinstance(data["routes"], list)
        
        # Should have at least one route
        if len(data["routes"]) > 0:
            route = data["routes"][0]
            assert "steps" in route
            assert "overall_yield_percent" in route
            assert "total_cost_usd" in route
            print(f"✓ Aspirin synthesis: {len(data['routes'])} routes, best yield: {route['overall_yield_percent']}%")
        else:
            print(f"✓ Aspirin synthesis: No routes found (may be expected)")
    
    def test_synthesis_plan_simple_molecule(self):
        """Test synthesis planning for simple molecule (ethanol)"""
        response = requests.post(
            f"{API_URL}/synthesis/plan",
            json={
                "target_smiles": TEST_MOLECULES["ethanol"],
                "max_steps": 3,
                "optimize_for": "yield"
            },
            timeout=60
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "routes" in data
        print(f"✓ Ethanol synthesis: {len(data['routes'])} routes found")
    
    def test_synthesis_plan_invalid_smiles_returns_400(self):
        """Test synthesis planning with invalid SMILES returns 400"""
        response = requests.post(
            f"{API_URL}/synthesis/plan",
            json={
                "target_smiles": TEST_MOLECULES["invalid"],
                "max_steps": 5,
                "optimize_for": "balanced"
            },
            timeout=30
        )
        # Should return 400 for invalid molecule
        assert response.status_code == 400
        print(f"✓ Invalid SMILES synthesis correctly returns 400")


class TestConditionPrediction:
    """Condition Prediction Endpoint Tests"""
    
    def test_predict_conditions_esterification(self):
        """Test condition prediction for esterification reaction"""
        response = requests.post(
            f"{API_URL}/conditions/predict",
            json={
                "reactants": ["c1ccccc1O", "CC(=O)Cl"],  # Phenol + Acetyl chloride
                "products": ["CC(=O)Oc1ccccc1"],  # Phenyl acetate
                "reaction_type": "esterification"
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "success"
        assert "conditions" in data
        conditions = data["conditions"]
        
        # Verify condition fields
        assert "temperature_celsius" in conditions
        assert "confidence" in conditions
        print(f"✓ Condition prediction: Temp={conditions['temperature_celsius']}°C, Confidence={conditions['confidence']}")
    
    def test_predict_conditions_suzuki(self):
        """Test condition prediction for Suzuki coupling"""
        response = requests.post(
            f"{API_URL}/conditions/predict",
            json={
                "reactants": ["c1ccccc1Br", "c1ccccc1B(O)O"],  # Bromobenzene + Phenylboronic acid
                "products": ["c1ccc(-c2ccccc2)cc1"],  # Biphenyl
                "reaction_type": "suzuki"
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "success"
        print(f"✓ Suzuki coupling conditions predicted successfully")


class TestRouteComparison:
    """Route Comparison Endpoint Tests"""
    
    def test_compare_routes_basic(self):
        """Test route comparison with sample routes"""
        sample_routes = [
            {
                "id": "route_1",
                "target_molecule": {"smiles": "CC(=O)Oc1ccccc1"},
                "steps": [
                    {
                        "id": "step_1",
                        "reaction_type": "esterification",
                        "reactants": [{"smiles": "c1ccccc1O"}],
                        "product": {"smiles": "CC(=O)Oc1ccccc1"},
                        "estimated_yield_percent": 85,
                        "estimated_cost_usd": 10.0,
                        "estimated_time_hours": 2.0,
                        "difficulty": "easy"
                    }
                ],
                "starting_materials": [{"smiles": "c1ccccc1O", "name": "Phenol"}],
                "overall_yield_percent": 85,
                "total_cost_usd": 10.0,
                "total_time_hours": 2.0,
                "score": 0.8
            },
            {
                "id": "route_2",
                "target_molecule": {"smiles": "c1ccccc1CO"},
                "steps": [
                    {
                        "id": "step_1",
                        "reaction_type": "reduction",
                        "reactants": [{"smiles": "c1ccccc1C=O"}],
                        "product": {"smiles": "c1ccccc1CO"},
                        "estimated_yield_percent": 90,
                        "estimated_cost_usd": 15.0,
                        "estimated_time_hours": 3.0,
                        "difficulty": "moderate"
                    }
                ],
                "starting_materials": [{"smiles": "c1ccccc1C=O", "name": "Benzaldehyde"}],
                "overall_yield_percent": 90,
                "total_cost_usd": 15.0,
                "total_time_hours": 3.0,
                "score": 0.75
            }
        ]
        
        response = requests.post(
            f"{API_URL}/routes/compare",
            json={
                "routes": sample_routes,
                "optimize_for": "balanced"
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "success"
        assert "ranked_routes" in data
        assert len(data["ranked_routes"]) == 2
        print(f"✓ Route comparison: {len(data['ranked_routes'])} routes ranked")
    
    def test_compare_routes_empty_returns_400(self):
        """Test route comparison with empty routes returns 400"""
        response = requests.post(
            f"{API_URL}/routes/compare",
            json={
                "routes": [],
                "optimize_for": "balanced"
            }
        )
        assert response.status_code == 400
        print(f"✓ Empty routes comparison correctly returns 400")


class TestCopilotOptimize:
    """LLM Copilot Endpoint Tests"""
    
    def test_copilot_reduce_cost_direct_query(self):
        """Test copilot with direct cost reduction query (matches intent pattern)"""
        # Use exact phrase that matches intent parser: "reduce cost"
        response = requests.post(
            f"{API_URL}/copilot/optimize",
            json={
                "query": "reduce cost",
                "route_data": None,
                "context": None
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "success"
        assert data["action"] == "cost_optimization"
        print(f"✓ Copilot cost optimization query successful")
    
    def test_copilot_reduce_cost_natural_language(self):
        """Test copilot with natural language cost reduction query - Bug #2 Fixed"""
        # Bug #2 Fixed: Now correctly parses "How can I reduce the cost?"
        response = requests.post(
            f"{API_URL}/copilot/optimize",
            json={
                "query": "How can I reduce the cost?",
                "route_data": None,
                "context": None
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "success"
        assert data["action"] == "cost_optimization"
        print(f"✓ Copilot natural language cost query successful")
    
    def test_copilot_increase_yield_direct_query(self):
        """Test copilot with direct yield improvement query (matches intent pattern)"""
        # Use exact phrase that matches intent parser: "increase yield"
        response = requests.post(
            f"{API_URL}/copilot/optimize",
            json={
                "query": "increase yield",
                "route_data": None,
                "context": None
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "success"
        assert data["action"] == "yield_optimization"
        print(f"✓ Copilot yield optimization query successful")
    
    def test_copilot_increase_yield_natural_language(self):
        """Test copilot with natural language yield improvement query - Bug #2 Fixed"""
        # Bug #2 Fixed: Now correctly parses "How can I improve the yield?"
        response = requests.post(
            f"{API_URL}/copilot/optimize",
            json={
                "query": "How can I improve the yield?",
                "route_data": None,
                "context": None
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "success"
        assert data["action"] == "yield_optimization"
        print(f"✓ Copilot natural language yield query successful")
    
    def test_copilot_speed_optimization_query(self):
        """Test copilot with speed optimization query"""
        response = requests.post(
            f"{API_URL}/copilot/optimize",
            json={
                "query": "Make it faster with fewer steps",
                "route_data": None,
                "context": None
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "success"
        assert data["action"] == "speed_optimization"
        print(f"✓ Copilot speed optimization query successful")


class TestTemplateStatistics:
    """Template Statistics Endpoint Tests"""
    
    def test_get_template_stats(self):
        """Test getting template statistics"""
        response = requests.get(f"{API_URL}/templates/stats")
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "success"
        assert "statistics" in data
        stats = data["statistics"]
        
        # Verify statistics structure
        assert "total_templates" in stats or "template_types" in stats
        print(f"✓ Template statistics retrieved: {stats}")


class TestEquipmentRecommendation:
    """Equipment Recommendation Endpoint Tests"""
    
    def test_recommend_equipment_esterification(self):
        """Test equipment recommendation for esterification"""
        response = requests.post(
            f"{API_URL}/equipment/recommend",
            json={
                "reaction_type": "esterification",
                "scale_mg": 100.0,
                "temperature_c": 80.0,
                "pressure_atm": 1.0
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "success"
        assert "reactor_recommendations" in data
        assert "complete_setup" in data
        print(f"✓ Equipment recommendation: {len(data['reactor_recommendations'])} reactors suggested")
    
    def test_recommend_equipment_high_pressure(self):
        """Test equipment recommendation for high pressure reaction"""
        response = requests.post(
            f"{API_URL}/equipment/recommend",
            json={
                "reaction_type": "hydrogenation",
                "scale_mg": 500.0,
                "temperature_c": 50.0,
                "pressure_atm": 10.0
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "success"
        print(f"✓ High pressure equipment recommendation successful")


class TestSynthesisHistory:
    """Synthesis History Endpoint Tests"""
    
    def test_get_synthesis_history(self):
        """Test getting synthesis history"""
        response = requests.get(f"{API_URL}/synthesis/history?limit=5")
        assert response.status_code == 200
        data = response.json()
        
        assert "history" in data
        assert isinstance(data["history"], list)
        print(f"✓ Synthesis history: {len(data['history'])} records found")


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
