#!/usr/bin/env python3
"""
Comprehensive Backend API Testing for AI Synthesis Route Planner
Tests all 13 API endpoints with realistic chemical data
"""

import requests
import json
import sys
from typing import Dict, Any, List

# Backend URL from environment
BACKEND_URL = "https://continue-boost.preview.emergentagent.com/api"

class BackendTester:
    def __init__(self):
        self.results = []
        self.passed = 0
        self.failed = 0
        
    def log_result(self, endpoint: str, method: str, status: str, details: str):
        """Log test result"""
        result = {
            "endpoint": endpoint,
            "method": method,
            "status": status,
            "details": details
        }
        self.results.append(result)
        
        if status == "PASS":
            self.passed += 1
            print(f"✅ {method} {endpoint} - {details}")
        else:
            self.failed += 1
            print(f"❌ {method} {endpoint} - {details}")
    
    def test_api_root(self):
        """Test GET /api/ - Should return API info"""
        try:
            response = requests.get(f"{BACKEND_URL}/", timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if "message" in data and "version" in data and "endpoints" in data:
                    self.log_result("/", "GET", "PASS", f"API info returned: {data['message']}")
                else:
                    self.log_result("/", "GET", "FAIL", f"Missing required fields in response: {data}")
            else:
                self.log_result("/", "GET", "FAIL", f"Status {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("/", "GET", "FAIL", f"Request failed: {str(e)}")
    
    def test_molecule_validate_valid(self):
        """Test POST /api/molecule/validate with valid SMILES"""
        try:
            payload = {"smiles": "CCO"}  # Ethanol
            response = requests.post(f"{BACKEND_URL}/molecule/validate", 
                                   json=payload, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("valid") is True:
                    self.log_result("/molecule/validate", "POST", "PASS", 
                                  f"Valid SMILES correctly identified: {data}")
                else:
                    self.log_result("/molecule/validate", "POST", "FAIL", 
                                  f"Valid SMILES marked as invalid: {data}")
            else:
                self.log_result("/molecule/validate", "POST", "FAIL", 
                              f"Status {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("/molecule/validate", "POST", "FAIL", f"Request failed: {str(e)}")
    
    def test_molecule_validate_empty(self):
        """Test POST /api/molecule/validate with empty string"""
        try:
            payload = {"smiles": ""}
            response = requests.post(f"{BACKEND_URL}/molecule/validate", 
                                   json=payload, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("valid") is False:
                    self.log_result("/molecule/validate (empty)", "POST", "PASS", 
                                  f"Empty SMILES correctly handled: {data}")
                else:
                    self.log_result("/molecule/validate (empty)", "POST", "FAIL", 
                                  f"Empty SMILES not properly validated: {data}")
            else:
                self.log_result("/molecule/validate (empty)", "POST", "FAIL", 
                              f"Status {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("/molecule/validate (empty)", "POST", "FAIL", f"Request failed: {str(e)}")
    
    def test_molecule_analyze(self):
        """Test POST /api/molecule/analyze - Should return molecular properties"""
        try:
            payload = {"smiles": "CC(=O)Oc1ccccc1C(=O)O"}  # Aspirin
            response = requests.post(f"{BACKEND_URL}/molecule/analyze", 
                                   json=payload, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                required_fields = ["molecular_weight", "logp", "h_donors", "h_acceptors", "tpsa", "molecular_formula"]
                missing_fields = [field for field in required_fields if field not in data]
                
                if not missing_fields:
                    self.log_result("/molecule/analyze", "POST", "PASS", 
                                  f"All molecular properties returned: MW={data.get('molecular_weight')}, LogP={data.get('logp')}")
                else:
                    self.log_result("/molecule/analyze", "POST", "FAIL", 
                                  f"Missing fields: {missing_fields}. Got: {list(data.keys())}")
            else:
                self.log_result("/molecule/analyze", "POST", "FAIL", 
                              f"Status {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("/molecule/analyze", "POST", "FAIL", f"Request failed: {str(e)}")
    
    def test_conditions_predict(self):
        """Test POST /api/conditions/predict - Should return temperature, catalyst, solvent"""
        try:
            payload = {
                "reactants": ["CC(=O)O", "c1ccc(O)cc1"],  # Acetic acid + Phenol
                "products": ["CC(=O)Oc1ccccc1"],  # Phenyl acetate
                "reaction_type": "esterification"
            }
            response = requests.post(f"{BACKEND_URL}/conditions/predict", 
                                   json=payload, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if "conditions" in data and data.get("status") == "success":
                    conditions = data["conditions"]
                    # Check for temperature (could be 'temperature' or 'temperature_celsius')
                    temp_field = "temperature_celsius" if "temperature_celsius" in conditions else "temperature"
                    if temp_field in conditions and "catalyst" in conditions and "solvent" in conditions:
                        self.log_result("/conditions/predict", "POST", "PASS", 
                                      f"Conditions predicted: T={conditions.get(temp_field)}, Cat={conditions.get('catalyst')}")
                    else:
                        self.log_result("/conditions/predict", "POST", "FAIL", 
                                      f"Missing condition fields: {conditions}")
                else:
                    self.log_result("/conditions/predict", "POST", "FAIL", 
                                  f"Invalid response format: {data}")
            else:
                self.log_result("/conditions/predict", "POST", "FAIL", 
                              f"Status {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("/conditions/predict", "POST", "FAIL", f"Request failed: {str(e)}")
    
    def test_equipment_recommend(self):
        """Test POST /api/equipment/recommend - Should return reactor recommendations"""
        try:
            payload = {
                "reaction_type": "esterification",
                "scale_mg": 100,
                "temperature_c": 80,
                "pressure_atm": 1
            }
            response = requests.post(f"{BACKEND_URL}/equipment/recommend", 
                                   json=payload, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if "reactor_recommendations" in data and data.get("status") == "success":
                    recommendations = data["reactor_recommendations"]
                    if isinstance(recommendations, list) and len(recommendations) > 0:
                        self.log_result("/equipment/recommend", "POST", "PASS", 
                                      f"Equipment recommendations returned: {len(recommendations)} reactors")
                    else:
                        self.log_result("/equipment/recommend", "POST", "FAIL", 
                                      f"No reactor recommendations: {recommendations}")
                else:
                    self.log_result("/equipment/recommend", "POST", "FAIL", 
                                  f"Invalid response format: {data}")
            else:
                self.log_result("/equipment/recommend", "POST", "FAIL", 
                              f"Status {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("/equipment/recommend", "POST", "FAIL", f"Request failed: {str(e)}")
    
    def test_retrosynthesis_plan(self):
        """Test POST /api/retrosynthesis/plan - Should return routes"""
        try:
            payload = {
                "target_smiles": "CC(=O)Oc1ccccc1C(=O)O",  # Aspirin
                "max_depth": 3,
                "max_routes": 2
            }
            response = requests.post(f"{BACKEND_URL}/retrosynthesis/plan", 
                                   json=payload, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                if "routes" in data and data.get("status") == "success":
                    routes = data["routes"]
                    if isinstance(routes, list):
                        self.log_result("/retrosynthesis/plan", "POST", "PASS", 
                                      f"Retrosynthesis routes returned: {len(routes)} routes")
                    else:
                        self.log_result("/retrosynthesis/plan", "POST", "FAIL", 
                                      f"Routes not in list format: {type(routes)}")
                else:
                    self.log_result("/retrosynthesis/plan", "POST", "FAIL", 
                                  f"Invalid response format: {data}")
            else:
                self.log_result("/retrosynthesis/plan", "POST", "FAIL", 
                              f"Status {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("/retrosynthesis/plan", "POST", "FAIL", f"Request failed: {str(e)}")
    
    def test_scale_optimize(self):
        """Test POST /api/scale/optimize - Should return optimization"""
        try:
            payload = {
                "reaction": {
                    "reactants": ["CC(=O)O"],
                    "products": ["CC(=O)Oc1ccccc1"],
                    "reaction_type": "esterification",
                    "temperature_celsius": 80
                },
                "target_scale": "pilot",
                "batch_size_kg": 10
            }
            response = requests.post(f"{BACKEND_URL}/scale/optimize", 
                                   json=payload, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if "optimization" in data and data.get("status") == "success":
                    self.log_result("/scale/optimize", "POST", "PASS", 
                                  f"Scale optimization returned: {data['optimization']}")
                else:
                    self.log_result("/scale/optimize", "POST", "FAIL", 
                                  f"Invalid response format: {data}")
            else:
                self.log_result("/scale/optimize", "POST", "FAIL", 
                              f"Status {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("/scale/optimize", "POST", "FAIL", f"Request failed: {str(e)}")
    
    def test_cost_industrial(self):
        """Test POST /api/cost/industrial - Should return costs"""
        try:
            payload = {
                "reaction": {
                    "reactants": ["CC(=O)O"],
                    "products": ["CC(=O)Oc1ccccc1"],
                    "reaction_type": "esterification",
                    "temperature_celsius": 80
                },
                "scale": "lab",
                "batch_size_kg": 0.1,
                "include_recovery": False
            }
            response = requests.post(f"{BACKEND_URL}/cost/industrial", 
                                   json=payload, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if "costs" in data and data.get("status") == "success":
                    self.log_result("/cost/industrial", "POST", "PASS", 
                                  f"Industrial costs calculated: {data['costs']}")
                else:
                    self.log_result("/cost/industrial", "POST", "FAIL", 
                                  f"Invalid response format: {data}")
            else:
                self.log_result("/cost/industrial", "POST", "FAIL", 
                              f"Status {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("/cost/industrial", "POST", "FAIL", f"Request failed: {str(e)}")
    
    def test_constraints_evaluate(self):
        """Test POST /api/constraints/evaluate - Should return constraints"""
        try:
            payload = {
                "reaction": {
                    "reactants": ["CC(=O)O"],
                    "products": ["CC(=O)Oc1ccccc1"],
                    "reaction_type": "esterification",
                    "temperature_celsius": 80
                },
                "scale": "lab",
                "batch_size_kg": 0.1
            }
            response = requests.post(f"{BACKEND_URL}/constraints/evaluate", 
                                   json=payload, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if "constraints" in data and data.get("status") == "success":
                    constraints = data["constraints"]
                    required_fields = ["heat_risk", "mixing", "safety"]
                    if any(field in str(constraints) for field in required_fields):
                        self.log_result("/constraints/evaluate", "POST", "PASS", 
                                      f"Process constraints evaluated: {list(constraints.keys()) if isinstance(constraints, dict) else 'constraints returned'}")
                    else:
                        self.log_result("/constraints/evaluate", "POST", "FAIL", 
                                      f"Missing constraint fields: {constraints}")
                else:
                    self.log_result("/constraints/evaluate", "POST", "FAIL", 
                                  f"Invalid response format: {data}")
            else:
                self.log_result("/constraints/evaluate", "POST", "FAIL", 
                              f"Status {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("/constraints/evaluate", "POST", "FAIL", f"Request failed: {str(e)}")
    
    def test_copilot_optimize(self):
        """Test POST /api/copilot/optimize - Should return suggestions"""
        try:
            payload = {"query": "How can I reduce the cost?"}
            response = requests.post(f"{BACKEND_URL}/copilot/optimize", 
                                   json=payload, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                if "suggestions" in data or "action" in data:
                    self.log_result("/copilot/optimize", "POST", "PASS", 
                                  f"Copilot suggestions returned: {data}")
                else:
                    self.log_result("/copilot/optimize", "POST", "FAIL", 
                                  f"No suggestions in response: {data}")
            else:
                self.log_result("/copilot/optimize", "POST", "FAIL", 
                              f"Status {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("/copilot/optimize", "POST", "FAIL", f"Request failed: {str(e)}")
    
    def test_templates_stats(self):
        """Test GET /api/templates/stats - Should return template statistics"""
        try:
            response = requests.get(f"{BACKEND_URL}/templates/stats", timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if "statistics" in data and data.get("status") == "success":
                    stats = data["statistics"]
                    if isinstance(stats, dict) and len(stats) > 0:
                        self.log_result("/templates/stats", "GET", "PASS", 
                                      f"Template statistics returned: {stats}")
                    else:
                        self.log_result("/templates/stats", "GET", "FAIL", 
                                      f"Empty or invalid statistics: {stats}")
                else:
                    self.log_result("/templates/stats", "GET", "FAIL", 
                                  f"Invalid response format: {data}")
            else:
                self.log_result("/templates/stats", "GET", "FAIL", 
                              f"Status {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("/templates/stats", "GET", "FAIL", f"Request failed: {str(e)}")
    
    def test_synthesis_history(self):
        """Test GET /api/synthesis/history?limit=5 - Should return history array"""
        try:
            response = requests.get(f"{BACKEND_URL}/synthesis/history?limit=5", timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if "history" in data and isinstance(data["history"], list):
                    self.log_result("/synthesis/history", "GET", "PASS", 
                                  f"Synthesis history returned: {len(data['history'])} items")
                else:
                    self.log_result("/synthesis/history", "GET", "FAIL", 
                                  f"Invalid response format: {data}")
            else:
                self.log_result("/synthesis/history", "GET", "FAIL", 
                              f"Status {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("/synthesis/history", "GET", "FAIL", f"Request failed: {str(e)}")
    
    def run_all_tests(self):
        """Run all backend API tests"""
        print(f"🧪 Starting Backend API Tests for: {BACKEND_URL}")
        print("=" * 60)
        
        # Run all tests
        self.test_api_root()
        self.test_molecule_validate_valid()
        self.test_molecule_validate_empty()
        self.test_molecule_analyze()
        self.test_conditions_predict()
        self.test_equipment_recommend()
        self.test_retrosynthesis_plan()
        self.test_scale_optimize()
        self.test_cost_industrial()
        self.test_constraints_evaluate()
        self.test_copilot_optimize()
        self.test_templates_stats()
        self.test_synthesis_history()
        
        # Summary
        print("\n" + "=" * 60)
        print(f"📊 TEST SUMMARY: {self.passed} PASSED, {self.failed} FAILED")
        print("=" * 60)
        
        if self.failed > 0:
            print("\n❌ FAILED TESTS:")
            for result in self.results:
                if result["status"] == "FAIL":
                    print(f"   {result['method']} {result['endpoint']}: {result['details']}")
        
        return self.failed == 0

if __name__ == "__main__":
    tester = BackendTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)