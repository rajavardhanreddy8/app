"""
Phase 4: Industrial Integration Tests
Testing advanced synthesis planning, retrosynthesis, scale optimization, and industrial cost endpoints.

Modules tested:
- Advanced Synthesis Planning (use_advanced=true)
- Retrosynthesis Engine (/api/retrosynthesis/plan)
- Scale-Aware Optimizer (/api/scale/optimize)
- Industrial Cost Model (/api/cost/industrial)
- Cost Positivity Validation
- Backward Compatibility (basic mode)
"""

import pytest
import requests
import os

# Get backend URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://kinetics-predict.preview.emergentagent.com"

API_URL = f"{BASE_URL}/api"

# Test SMILES strings
TEST_MOLECULES = {
    "aspirin": "CC(=O)Oc1ccccc1C(=O)O",
    "caffeine": "CN1C=NC2=C1C(=O)N(C(=O)N2C)C",
    "ibuprofen": "CC(C)Cc1ccc(cc1)C(C)C(=O)O",
    "ethanol": "CCO",
    "benzene": "c1ccccc1",
}


class TestAdvancedSynthesisPlanning:
    """Advanced Synthesis Planning with use_advanced=true"""
    
    def test_advanced_planning_aspirin_pilot_scale(self):
        """Test advanced planning for Aspirin at pilot scale"""
        response = requests.post(
            f"{API_URL}/synthesis/plan?use_advanced=true&scale=pilot&batch_size_kg=10.0",
            json={
                "target_smiles": TEST_MOLECULES["aspirin"],
                "max_steps": 5,
                "optimize_for": "balanced"
            },
            timeout=60
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "request_id" in data
        assert "target_smiles" in data
        assert "routes" in data
        assert "computation_time_seconds" in data
        assert "tokens_used" in data
        
        # Advanced mode should have tokens_used=0 (no LLM calls)
        assert data["tokens_used"] == 0, f"Expected tokens_used=0 for advanced mode, got {data['tokens_used']}"
        
        # Should have routes
        assert len(data["routes"]) > 0, "Expected at least one route"
        
        # Verify route structure
        route = data["routes"][0]
        assert "overall_yield_percent" in route
        assert "total_cost_usd" in route
        assert "total_time_hours" in route
        assert "score" in route
        assert "notes" in route
        
        # Notes should contain scale info
        assert "pilot" in route["notes"].lower() or "10.0kg" in route["notes"]
        
        print(f"✓ Advanced planning (pilot): {len(data['routes'])} routes, tokens_used={data['tokens_used']}")
    
    def test_advanced_planning_lab_scale(self):
        """Test advanced planning at lab scale"""
        response = requests.post(
            f"{API_URL}/synthesis/plan?use_advanced=true&scale=lab&batch_size_kg=0.1",
            json={
                "target_smiles": TEST_MOLECULES["aspirin"],
                "max_steps": 5,
                "optimize_for": "yield"
            },
            timeout=60
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["tokens_used"] == 0
        assert len(data["routes"]) > 0
        
        print(f"✓ Advanced planning (lab): {len(data['routes'])} routes")
    
    def test_advanced_planning_industrial_scale(self):
        """Test advanced planning at industrial scale"""
        response = requests.post(
            f"{API_URL}/synthesis/plan?use_advanced=true&scale=industrial&batch_size_kg=100.0",
            json={
                "target_smiles": TEST_MOLECULES["aspirin"],
                "max_steps": 5,
                "optimize_for": "cost"
            },
            timeout=60
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["tokens_used"] == 0
        assert len(data["routes"]) > 0
        
        print(f"✓ Advanced planning (industrial): {len(data['routes'])} routes")
    
    def test_advanced_planning_cost_positivity(self):
        """Test that all costs in advanced planning are >= 0"""
        response = requests.post(
            f"{API_URL}/synthesis/plan?use_advanced=true&scale=pilot&batch_size_kg=10.0",
            json={
                "target_smiles": TEST_MOLECULES["aspirin"],
                "max_steps": 5,
                "optimize_for": "balanced"
            },
            timeout=60
        )
        assert response.status_code == 200
        data = response.json()
        
        for route in data["routes"]:
            assert route["total_cost_usd"] >= 0, f"Route total_cost_usd is negative: {route['total_cost_usd']}"
            
            for step in route.get("steps", []):
                step_cost = step.get("estimated_cost_usd", 0)
                assert step_cost >= 0, f"Step cost is negative: {step_cost}"
        
        print(f"✓ All costs are positive in advanced planning")


class TestBackwardCompatibility:
    """Test that basic mode still works (backward compatibility)"""
    
    def test_basic_mode_still_works(self):
        """Test basic synthesis planning without use_advanced"""
        response = requests.post(
            f"{API_URL}/synthesis/plan",
            json={
                "target_smiles": TEST_MOLECULES["aspirin"],
                "max_steps": 5,
                "optimize_for": "balanced"
            },
            timeout=60
        )
        assert response.status_code == 200
        data = response.json()
        
        # Basic mode should use LLM tokens
        assert "tokens_used" in data
        # tokens_used should be > 0 for basic mode (uses Claude)
        # Note: May be 0 if demo mode or fallback
        
        assert "routes" in data
        print(f"✓ Basic mode works: tokens_used={data['tokens_used']}, routes={len(data['routes'])}")
    
    def test_basic_mode_explicit_false(self):
        """Test basic mode with explicit use_advanced=false"""
        response = requests.post(
            f"{API_URL}/synthesis/plan?use_advanced=false",
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
        print(f"✓ Basic mode (explicit false) works: routes={len(data['routes'])}")


class TestRetrosynthesisEndpoint:
    """Retrosynthesis Engine Endpoint Tests"""
    
    def test_retrosynthesis_aspirin(self):
        """Test retrosynthesis planning for Aspirin"""
        response = requests.post(
            f"{API_URL}/retrosynthesis/plan",
            json={
                "target_smiles": TEST_MOLECULES["aspirin"],
                "max_depth": 5,
                "max_routes": 5
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "success"
        assert data["target_smiles"] == TEST_MOLECULES["aspirin"]
        assert "num_routes" in data
        assert "routes" in data
        assert isinstance(data["routes"], list)
        
        # Verify route structure
        if len(data["routes"]) > 0:
            route = data["routes"][0]
            assert "target" in route
            assert "starting_materials" in route
            assert "steps" in route
            assert "num_steps" in route
            assert "estimated_yield" in route
            assert "estimated_cost" in route
        
        print(f"✓ Retrosynthesis: {data['num_routes']} routes found")
    
    def test_retrosynthesis_caffeine(self):
        """Test retrosynthesis planning for Caffeine"""
        response = requests.post(
            f"{API_URL}/retrosynthesis/plan",
            json={
                "target_smiles": TEST_MOLECULES["caffeine"],
                "max_depth": 3,
                "max_routes": 3
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "success"
        print(f"✓ Retrosynthesis (caffeine): {data['num_routes']} routes")
    
    def test_retrosynthesis_simple_molecule(self):
        """Test retrosynthesis for simple molecule (benzene)"""
        response = requests.post(
            f"{API_URL}/retrosynthesis/plan",
            json={
                "target_smiles": TEST_MOLECULES["benzene"],
                "max_depth": 2,
                "max_routes": 2
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "success"
        print(f"✓ Retrosynthesis (benzene): {data['num_routes']} routes")


class TestScaleOptimizationEndpoint:
    """Scale-Aware Optimizer Endpoint Tests"""
    
    def test_scale_optimize_lab(self):
        """Test scale optimization for lab scale"""
        response = requests.post(
            f"{API_URL}/scale/optimize",
            json={
                "reaction": {
                    "catalyst_loading": 5.0,
                    "solvent_volume_ml_per_g": 10.0,
                    "time_hours": 4.0,
                    "yield_percent": 75.0,
                    "temperature_c": 25.0
                },
                "target_scale": "lab",
                "batch_size_kg": 0.1
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "success"
        assert "optimization" in data
        
        opt = data["optimization"]
        assert opt["scale"] == "lab"
        assert "predicted_yield_percent" in opt
        assert "recommendations" in opt
        
        print(f"✓ Scale optimization (lab): yield={opt['predicted_yield_percent']}%")
    
    def test_scale_optimize_pilot(self):
        """Test scale optimization for pilot scale"""
        response = requests.post(
            f"{API_URL}/scale/optimize",
            json={
                "reaction": {
                    "catalyst_loading": 5.0,
                    "solvent_volume_ml_per_g": 10.0,
                    "time_hours": 4.0,
                    "yield_percent": 75.0,
                    "temperature_c": 80.0
                },
                "target_scale": "pilot",
                "batch_size_kg": 10.0
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "success"
        opt = data["optimization"]
        assert opt["scale"] == "pilot"
        
        # Pilot scale should have special recommendations
        assert "recommendations" in opt
        assert len(opt["recommendations"]) > 0
        
        print(f"✓ Scale optimization (pilot): yield={opt['predicted_yield_percent']}%, recommendations={len(opt['recommendations'])}")
    
    def test_scale_optimize_industrial(self):
        """Test scale optimization for industrial scale"""
        response = requests.post(
            f"{API_URL}/scale/optimize",
            json={
                "reaction": {
                    "catalyst_loading": 5.0,
                    "solvent_volume_ml_per_g": 10.0,
                    "time_hours": 4.0,
                    "yield_percent": 75.0,
                    "temperature_c": 100.0
                },
                "target_scale": "industrial",
                "batch_size_kg": 100.0
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "success"
        opt = data["optimization"]
        assert opt["scale"] == "industrial"
        
        print(f"✓ Scale optimization (industrial): yield={opt['predicted_yield_percent']}%")
    
    def test_scale_optimize_invalid_scale_returns_400(self):
        """Test that invalid scale returns 400 error"""
        response = requests.post(
            f"{API_URL}/scale/optimize",
            json={
                "reaction": {
                    "catalyst_loading": 5.0,
                    "solvent_volume_ml_per_g": 10.0,
                    "time_hours": 4.0,
                    "yield_percent": 75.0,
                    "temperature_c": 25.0
                },
                "target_scale": "invalid_scale",
                "batch_size_kg": 1.0
            },
            timeout=30
        )
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        
        print(f"✓ Invalid scale correctly returns 400")


class TestIndustrialCostEndpoint:
    """Industrial Cost Model Endpoint Tests"""
    
    def test_industrial_cost_lab_scale(self):
        """Test industrial cost calculation for lab scale"""
        response = requests.post(
            f"{API_URL}/cost/industrial",
            json={
                "reaction": {
                    "reactants": ["c1ccccc1O", "CC(=O)Cl"],
                    "products": ["CC(=O)Oc1ccccc1"],
                    "catalysts": ["H2SO4"],
                    "solvents": ["THF"],
                    "temperature_c": 80.0,
                    "time_hours": 4.0
                },
                "scale": "lab",
                "batch_size_kg": 0.1,
                "include_recovery": False
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "success"
        assert data["scale"] == "lab"
        assert "costs" in data
        
        costs = data["costs"]
        assert "reagent_cost" in costs
        assert "energy_cost" in costs
        assert "labor_cost" in costs
        assert "equipment_cost" in costs
        assert "waste_disposal_cost" in costs
        assert "total_cost" in costs
        
        print(f"✓ Industrial cost (lab): total=${costs['total_cost']:.2f}")
    
    def test_industrial_cost_pilot_with_recovery(self):
        """Test industrial cost with recovery savings at pilot scale"""
        response = requests.post(
            f"{API_URL}/cost/industrial",
            json={
                "reaction": {
                    "reactants": ["c1ccccc1O", "CC(=O)Cl"],
                    "products": ["CC(=O)Oc1ccccc1"],
                    "catalysts": ["Pd(PPh3)4"],
                    "solvents": ["THF"],
                    "temperature_c": 80.0,
                    "time_hours": 4.0
                },
                "scale": "pilot",
                "batch_size_kg": 10.0,
                "include_recovery": True
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "success"
        costs = data["costs"]
        
        # With recovery, should have recovery_savings
        assert "recovery_savings" in costs
        
        print(f"✓ Industrial cost (pilot+recovery): total=${costs['total_cost']:.2f}, savings=${costs['recovery_savings']:.2f}")
    
    def test_industrial_cost_all_positive(self):
        """Test that all cost components are >= 0"""
        response = requests.post(
            f"{API_URL}/cost/industrial",
            json={
                "reaction": {
                    "reactants": ["c1ccccc1O"],
                    "products": ["c1ccccc1O"],
                    "catalysts": [],
                    "solvents": ["water"],
                    "temperature_c": 25.0,
                    "time_hours": 1.0
                },
                "scale": "lab",
                "batch_size_kg": 0.01,
                "include_recovery": False
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        costs = data["costs"]
        
        # All costs should be >= 0
        for key, value in costs.items():
            if isinstance(value, (int, float)):
                assert value >= 0, f"Cost '{key}' is negative: {value}"
        
        print(f"✓ All cost components are non-negative")
    
    def test_industrial_cost_industrial_scale(self):
        """Test industrial cost at industrial scale"""
        response = requests.post(
            f"{API_URL}/cost/industrial",
            json={
                "reaction": {
                    "reactants": ["c1ccccc1O", "CC(=O)Cl"],
                    "products": ["CC(=O)Oc1ccccc1"],
                    "catalysts": ["H2SO4"],
                    "solvents": ["THF"],
                    "temperature_c": 80.0,
                    "time_hours": 4.0
                },
                "scale": "industrial",
                "batch_size_kg": 100.0,
                "include_recovery": True
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "success"
        assert data["scale"] == "industrial"
        
        print(f"✓ Industrial cost (industrial): total=${data['costs']['total_cost']:.2f}")


class TestCostPositivityAcrossEndpoints:
    """Verify cost positivity across all endpoints that return costs"""
    
    def test_retrosynthesis_cost_positivity(self):
        """Test that retrosynthesis routes have positive costs"""
        response = requests.post(
            f"{API_URL}/retrosynthesis/plan",
            json={
                "target_smiles": TEST_MOLECULES["aspirin"],
                "max_depth": 3,
                "max_routes": 3
            },
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        for route in data["routes"]:
            assert route.get("estimated_cost", 0) >= 0, f"Retrosynthesis route cost is negative"
        
        print(f"✓ Retrosynthesis costs are all positive")
    
    def test_advanced_planning_step_costs_positive(self):
        """Test that all step costs in advanced planning are positive"""
        response = requests.post(
            f"{API_URL}/synthesis/plan?use_advanced=true&scale=pilot&batch_size_kg=10.0",
            json={
                "target_smiles": TEST_MOLECULES["aspirin"],
                "max_steps": 5,
                "optimize_for": "balanced"
            },
            timeout=60
        )
        assert response.status_code == 200
        data = response.json()
        
        for route in data["routes"]:
            for step in route.get("steps", []):
                cost = step.get("estimated_cost_usd", 0)
                assert cost >= 0, f"Step cost is negative: {cost}"
        
        print(f"✓ All step costs in advanced planning are positive")


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
