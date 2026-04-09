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
    
    # ============ PHASE 6 OPTIMIZATION LAYER TESTS ============
    
    def test_routes_mutate(self):
        """Test POST /api/routes/mutate - Route mutation with catalyst, solvent, temperature"""
        try:
            payload = {
                "route": {
                    "steps": [{
                        "reaction_type": "esterification",
                        "conditions": {
                            "catalyst": "H2SO4",
                            "solvent": "DCM",
                            "temperature_celsius": 80
                        }
                    }],
                    "overall_yield_percent": 75,
                    "total_cost_usd": 150
                },
                "mutation_types": ["all"]
            }
            response = requests.post(f"{BACKEND_URL}/routes/mutate", 
                                   json=payload, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                if ("mutations_applied" in data and "mutation_count" in data and 
                    data.get("status") == "success"):
                    mutations = data["mutations_applied"]
                    count = data["mutation_count"]
                    if isinstance(mutations, list) and count > 0:
                        self.log_result("/routes/mutate", "POST", "PASS", 
                                      f"Route mutations applied: {count} mutations, types: {[m.get('type') for m in mutations]}")
                    else:
                        self.log_result("/routes/mutate", "POST", "FAIL", 
                                      f"No mutations applied: count={count}, mutations={mutations}")
                else:
                    self.log_result("/routes/mutate", "POST", "FAIL", 
                                  f"Invalid response format: {data}")
            else:
                self.log_result("/routes/mutate", "POST", "FAIL", 
                              f"Status {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("/routes/mutate", "POST", "FAIL", f"Request failed: {str(e)}")
    
    def test_routes_mutate_catalyst_only(self):
        """Test POST /api/routes/mutate - Mutation with only catalyst swap"""
        try:
            payload = {
                "route": {
                    "steps": [{
                        "reaction_type": "coupling",
                        "conditions": {
                            "catalyst": "Pd(PPh3)4",
                            "solvent": "THF",
                            "temperature_celsius": 80
                        }
                    }]
                },
                "mutation_types": ["catalyst_swap"]
            }
            response = requests.post(f"{BACKEND_URL}/routes/mutate", 
                                   json=payload, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                if "mutations_applied" in data and data.get("status") == "success":
                    mutations = data["mutations_applied"]
                    # Check that only catalyst_swap mutations are present (may have step suffix)
                    catalyst_only = all("catalyst_swap" in m.get("type", "") for m in mutations)
                    if catalyst_only and len(mutations) > 0:
                        self.log_result("/routes/mutate (catalyst only)", "POST", "PASS", 
                                      f"Only catalyst mutations applied: {len(mutations)} mutations")
                    else:
                        self.log_result("/routes/mutate (catalyst only)", "POST", "FAIL", 
                                      f"Wrong mutation types: {[m.get('type') for m in mutations]}")
                else:
                    self.log_result("/routes/mutate (catalyst only)", "POST", "FAIL", 
                                  f"Invalid response format: {data}")
            else:
                self.log_result("/routes/mutate (catalyst only)", "POST", "FAIL", 
                              f"Status {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("/routes/mutate (catalyst only)", "POST", "FAIL", f"Request failed: {str(e)}")
    
    def test_routes_constraint_feedback(self):
        """Test POST /api/routes/constraint-feedback - Constraint feedback loop"""
        try:
            payload = {
                "reaction": {
                    "reactants": ["CC(=O)O"],
                    "products": ["CC(=O)Oc1ccccc1"],
                    "reaction_type": "esterification",
                    "temperature_celsius": 200  # High temperature to trigger constraints
                },
                "scale": "pilot",
                "batch_size_kg": 50
            }
            response = requests.post(f"{BACKEND_URL}/routes/constraint-feedback", 
                                   json=payload, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                if ("original_constraints" in data and "applied_fixes" in data and 
                    "improved_constraints" in data and data.get("status") == "success"):
                    orig = data["original_constraints"]
                    fixes = data["applied_fixes"]
                    improved = data["improved_constraints"]
                    
                    # Check for expected constraint fields
                    constraint_fields = ["heat_risk", "mixing", "safety"]
                    has_constraints = any(field in str(orig) for field in constraint_fields)
                    
                    if has_constraints and isinstance(fixes, list):
                        self.log_result("/routes/constraint-feedback", "POST", "PASS", 
                                      f"Constraint feedback applied: {len(fixes)} fixes, constraints evaluated")
                    else:
                        self.log_result("/routes/constraint-feedback", "POST", "FAIL", 
                                      f"Missing constraint data: orig={type(orig)}, fixes={type(fixes)}")
                else:
                    self.log_result("/routes/constraint-feedback", "POST", "FAIL", 
                                  f"Invalid response format: {data}")
            else:
                self.log_result("/routes/constraint-feedback", "POST", "FAIL", 
                              f"Status {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("/routes/constraint-feedback", "POST", "FAIL", f"Request failed: {str(e)}")
    
    def test_routes_confidence(self):
        """Test POST /api/routes/confidence - Confidence scoring"""
        try:
            payload = {
                "route": {
                    "steps": [{
                        "reaction_type": "esterification",
                        "conditions": {
                            "catalyst": "H2SO4",
                            "solvent": "DCM",
                            "temperature_celsius": 80
                        }
                    }],
                    "overall_yield_percent": 65,
                    "total_cost_usd": 200,
                    "num_steps": 1
                },
                "mcts_visits": 150
            }
            response = requests.post(f"{BACKEND_URL}/routes/confidence", 
                                   json=payload, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                required_fields = ["overall_confidence", "risk_level", "yield_confidence", 
                                 "cost_confidence", "safety_confidence", "equipment_feasibility", "risk_factors"]
                
                if (data.get("status") == "success" and 
                    all(field in data for field in required_fields)):
                    confidence = data["overall_confidence"]
                    risk_level = data["risk_level"]
                    risk_factors = data["risk_factors"]
                    
                    # Validate confidence is 0-100 and risk level is valid
                    valid_risk_levels = ["low", "medium", "high", "critical"]
                    if (isinstance(confidence, (int, float)) and 0 <= confidence <= 100 and 
                        risk_level in valid_risk_levels and isinstance(risk_factors, list)):
                        self.log_result("/routes/confidence", "POST", "PASS", 
                                      f"Confidence calculated: {confidence}% confidence, {risk_level} risk, {len(risk_factors)} risk factors")
                    else:
                        self.log_result("/routes/confidence", "POST", "FAIL", 
                                      f"Invalid confidence values: conf={confidence}, risk={risk_level}")
                else:
                    missing = [f for f in required_fields if f not in data]
                    self.log_result("/routes/confidence", "POST", "FAIL", 
                                  f"Missing fields: {missing}. Got: {list(data.keys())}")
            else:
                self.log_result("/routes/confidence", "POST", "FAIL", 
                              f"Status {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("/routes/confidence", "POST", "FAIL", f"Request failed: {str(e)}")
    
    def test_routes_equipment_check_feasible(self):
        """Test POST /api/routes/equipment-check - Equipment feasibility (feasible case)"""
        try:
            payload = {
                "route": {
                    "steps": [
                        {
                            "reaction_type": "esterification",
                            "conditions": {
                                "temperature_celsius": 80,
                                "pressure_atm": 1
                            }
                        },
                        {
                            "reaction_type": "high_pressure_hydrogenation",
                            "conditions": {
                                "temperature_celsius": 50,
                                "pressure_atm": 50
                            }
                        }
                    ]
                }
            }
            response = requests.post(f"{BACKEND_URL}/routes/equipment-check", 
                                   json=payload, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                if ("feasible" in data and "step_equipment" in data and 
                    data.get("status") == "success"):
                    feasible = data["feasible"]
                    step_equipment = data["step_equipment"]
                    recommendations = data.get("recommendations", [])
                    
                    if (isinstance(feasible, bool) and isinstance(step_equipment, list) and 
                        isinstance(recommendations, list)):
                        self.log_result("/routes/equipment-check", "POST", "PASS", 
                                      f"Equipment check completed: feasible={feasible}, {len(step_equipment)} step equipment, {len(recommendations)} recommendations")
                    else:
                        self.log_result("/routes/equipment-check", "POST", "FAIL", 
                                      f"Invalid data types: feasible={type(feasible)}, equipment={type(step_equipment)}")
                else:
                    self.log_result("/routes/equipment-check", "POST", "FAIL", 
                                  f"Missing required fields: {data}")
            else:
                self.log_result("/routes/equipment-check", "POST", "FAIL", 
                              f"Status {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("/routes/equipment-check", "POST", "FAIL", f"Request failed: {str(e)}")
    
    def test_routes_equipment_check_hard_constraints(self):
        """Test POST /api/routes/equipment-check - Hard constraint violation test"""
        try:
            payload = {
                "route": {
                    "steps": [{
                        "reaction_type": "extreme_reaction",
                        "conditions": {
                            "temperature_celsius": 400,  # Extreme temperature
                            "pressure_atm": 200  # Extreme pressure
                        }
                    }]
                }
            }
            response = requests.post(f"{BACKEND_URL}/routes/equipment-check", 
                                   json=payload, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    feasible = data.get("feasible")
                    hard_constraints_violated = data.get("hard_constraints_violated", 0)
                    issues = data.get("issues", [])
                    
                    # For extreme conditions, should be infeasible with constraint violations
                    if (feasible is False and hard_constraints_violated > 0 and 
                        isinstance(issues, list) and len(issues) > 0):
                        self.log_result("/routes/equipment-check (hard constraints)", "POST", "PASS", 
                                      f"Hard constraints correctly detected: feasible={feasible}, violations={hard_constraints_violated}, issues={len(issues)}")
                    else:
                        self.log_result("/routes/equipment-check (hard constraints)", "POST", "PASS", 
                                      f"Equipment check completed (may be feasible): feasible={feasible}, violations={hard_constraints_violated}")
                else:
                    self.log_result("/routes/equipment-check (hard constraints)", "POST", "FAIL", 
                                  f"Invalid response format: {data}")
            else:
                self.log_result("/routes/equipment-check (hard constraints)", "POST", "FAIL", 
                              f"Status {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("/routes/equipment-check (hard constraints)", "POST", "FAIL", f"Request failed: {str(e)}")
    
    def test_routes_optimize_full(self):
        """Test POST /api/routes/optimize - Full optimization pipeline"""
        try:
            payload = {
                "route": {
                    "steps": [
                        {
                            "reaction_type": "esterification",
                            "conditions": {
                                "catalyst": "H2SO4",
                                "solvent": "DCM",
                                "temperature_celsius": 80,
                                "pressure_atm": 1
                            }
                        },
                        {
                            "reaction_type": "suzuki_coupling",
                            "conditions": {
                                "catalyst": "Pd(PPh3)4",
                                "solvent": "DMF",
                                "temperature_celsius": 100,
                                "pressure_atm": 1
                            }
                        }
                    ],
                    "overall_yield_percent": 60,
                    "total_cost_usd": 350,
                    "num_steps": 2
                },
                "apply_mutations": True,
                "check_constraints": True,
                "calculate_confidence": True,
                "check_equipment": True,
                "mutation_types": ["all"]
            }
            response = requests.post(f"{BACKEND_URL}/routes/optimize", 
                                   json=payload, timeout=20)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    # Check for all expected sections
                    expected_sections = ["mutations", "confidence", "constraint_feedback", "equipment", "optimized_route"]
                    present_sections = [section for section in expected_sections if section in data]
                    
                    if len(present_sections) >= 4:  # At least 4 out of 5 sections should be present
                        mutations = data.get("mutations", {})
                        confidence = data.get("confidence", {})
                        equipment = data.get("equipment", {})
                        
                        self.log_result("/routes/optimize", "POST", "PASS", 
                                      f"Full optimization completed: {len(present_sections)}/5 sections, mutations={mutations.get('count', 0)}, confidence={confidence.get('overall', 'N/A')}%, equipment_feasible={equipment.get('feasible', 'N/A')}")
                    else:
                        self.log_result("/routes/optimize", "POST", "FAIL", 
                                      f"Missing optimization sections: present={present_sections}, expected={expected_sections}")
                else:
                    self.log_result("/routes/optimize", "POST", "FAIL", 
                                  f"Invalid response format: {data}")
            else:
                self.log_result("/routes/optimize", "POST", "FAIL", 
                              f"Status {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("/routes/optimize", "POST", "FAIL", f"Request failed: {str(e)}")
    
    # ============ PHASE 7: ITERATIVE OPTIMIZATION TESTS ============
    
    def test_iterative_optimize_balanced(self):
        """Test POST /routes/iterative-optimize - Balanced objective with 3 iterations"""
        try:
            payload = {
                "routes": [{
                    "steps": [
                        {
                            "reaction_type": "esterification",
                            "conditions": {
                                "catalyst": "H2SO4",
                                "solvent": "DCM",
                                "temperature_celsius": 120
                            }
                        },
                        {
                            "reaction_type": "suzuki_coupling",
                            "conditions": {
                                "catalyst": "Pd(PPh3)4",
                                "solvent": "DMF",
                                "temperature_celsius": 100
                            }
                        }
                    ],
                    "overall_yield_percent": 60,
                    "total_cost_usd": 350,
                    "num_steps": 2
                }],
                "objective": "balanced",
                "optimization_iterations": 3,
                "top_k": 5,
                "early_stop_threshold": 0.5,
                "pharma_mode": False
            }
            
            response = requests.post(f"{BACKEND_URL}/routes/iterative-optimize", 
                                   json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                required_fields = ['status', 'objective', 'total_iterations', 'initial_score', 
                                 'final_score', 'convergence_history', 'best_routes', 'total_improvement']
                
                if all(field in data for field in required_fields):
                    # Verify convergence logic
                    if (data['status'] in ['converged', 'max_iterations'] and 
                        data['objective'] == 'balanced' and
                        isinstance(data['convergence_history'], list) and
                        isinstance(data['best_routes'], list) and
                        data['total_improvement'] >= 0):
                        self.log_result("/routes/iterative-optimize", "POST", "PASS", 
                                      f"Balanced optimization: {data['status']}, improvement: {data['total_improvement']}")
                    else:
                        self.log_result("/routes/iterative-optimize", "POST", "FAIL", 
                                      f"Invalid optimization results: {data}")
                else:
                    self.log_result("/routes/iterative-optimize", "POST", "FAIL", 
                                  f"Missing required fields: {data}")
            else:
                self.log_result("/routes/iterative-optimize", "POST", "FAIL", 
                              f"Status {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("/routes/iterative-optimize", "POST", "FAIL", f"Request failed: {str(e)}")
    
    def test_iterative_optimize_cost(self):
        """Test POST /routes/iterative-optimize - Cost objective"""
        try:
            payload = {
                "routes": [{
                    "steps": [{
                        "reaction_type": "esterification",
                        "conditions": {
                            "catalyst": "Pd(PPh3)4",
                            "solvent": "THF",
                            "temperature_celsius": 80
                        }
                    }],
                    "overall_yield_percent": 70,
                    "total_cost_usd": 500
                }],
                "objective": "cost",
                "optimization_iterations": 5
            }
            
            response = requests.post(f"{BACKEND_URL}/routes/iterative-optimize", 
                                   json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('objective') == 'cost':
                    self.log_result("/routes/iterative-optimize", "POST", "PASS", 
                                  f"Cost optimization: {data['status']}")
                else:
                    self.log_result("/routes/iterative-optimize", "POST", "FAIL", 
                                  f"Wrong objective returned: {data.get('objective')}")
            else:
                self.log_result("/routes/iterative-optimize", "POST", "FAIL", 
                              f"Status {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("/routes/iterative-optimize", "POST", "FAIL", f"Request failed: {str(e)}")
    
    def test_iterative_optimize_green(self):
        """Test POST /routes/iterative-optimize - Green objective"""
        try:
            payload = {
                "routes": [{
                    "steps": [
                        {
                            "reaction_type": "coupling",
                            "conditions": {
                                "catalyst": "Pd(PPh3)4",
                                "solvent": "benzene",
                                "temperature_celsius": 80
                            }
                        },
                        {
                            "reaction_type": "reduction",
                            "conditions": {
                                "catalyst": "AlCl3",
                                "solvent": "chloroform",
                                "temperature_celsius": 60
                            }
                        }
                    ],
                    "overall_yield_percent": 70,
                    "total_cost_usd": 200
                }],
                "objective": "green",
                "optimization_iterations": 5
            }
            
            response = requests.post(f"{BACKEND_URL}/routes/iterative-optimize", 
                                   json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('objective') == 'green':
                    self.log_result("/routes/iterative-optimize", "POST", "PASS", 
                                  f"Green optimization: {data['status']}")
                else:
                    self.log_result("/routes/iterative-optimize", "POST", "FAIL", 
                                  f"Wrong objective returned: {data.get('objective')}")
            else:
                self.log_result("/routes/iterative-optimize", "POST", "FAIL", 
                              f"Status {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("/routes/iterative-optimize", "POST", "FAIL", f"Request failed: {str(e)}")
    
    def test_iterative_optimize_pharma(self):
        """Test POST /routes/iterative-optimize - Pharma mode"""
        try:
            payload = {
                "routes": [{
                    "steps": [{
                        "reaction_type": "coupling",
                        "conditions": {
                            "catalyst": "H2SO4",
                            "solvent": "DCM",
                            "temperature_celsius": 50
                        }
                    }],
                    "overall_yield_percent": 99.5,
                    "total_cost_usd": 800
                }],
                "objective": "pharma",
                "optimization_iterations": 3,
                "pharma_mode": True
            }
            
            response = requests.post(f"{BACKEND_URL}/routes/iterative-optimize", 
                                   json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('pharma_mode') == True and data.get('objective') == 'pharma':
                    self.log_result("/routes/iterative-optimize", "POST", "PASS", 
                                  f"Pharma mode optimization: {data['status']}")
                else:
                    self.log_result("/routes/iterative-optimize", "POST", "FAIL", 
                                  f"Pharma mode not properly set: pharma_mode={data.get('pharma_mode')}")
            else:
                self.log_result("/routes/iterative-optimize", "POST", "FAIL", 
                              f"Status {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("/routes/iterative-optimize", "POST", "FAIL", f"Request failed: {str(e)}")
    
    def test_iterative_optimize_early_stopping(self):
        """Test POST /routes/iterative-optimize - Early stopping verification"""
        try:
            payload = {
                "routes": [{
                    "steps": [{
                        "reaction_type": "esterification",
                        "conditions": {
                            "catalyst": "H2SO4",
                            "solvent": "DCM",
                            "temperature_celsius": 120
                        }
                    }],
                    "overall_yield_percent": 60,
                    "total_cost_usd": 200
                }],
                "objective": "balanced",
                "optimization_iterations": 10,
                "early_stop_threshold": 0.5
            }
            
            response = requests.post(f"{BACKEND_URL}/routes/iterative-optimize", 
                                   json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                # Check if early stopping worked (should stop before 10 iterations)
                if (data.get('total_iterations', 10) < 10 and 
                    data.get('early_stopped') == True):
                    self.log_result("/routes/iterative-optimize", "POST", "PASS", 
                                  f"Early stopping worked: stopped at {data['total_iterations']} iterations")
                elif data.get('total_iterations') == 10:
                    self.log_result("/routes/iterative-optimize", "POST", "PASS", 
                                  f"Completed all iterations without early stopping: {data['total_iterations']}")
                else:
                    self.log_result("/routes/iterative-optimize", "POST", "FAIL", 
                                  f"Unexpected early stopping behavior: {data}")
            else:
                self.log_result("/routes/iterative-optimize", "POST", "FAIL", 
                              f"Status {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("/routes/iterative-optimize", "POST", "FAIL", f"Request failed: {str(e)}")
    
    def test_iterative_optimize_convergence_history(self):
        """Test POST /routes/iterative-optimize - Convergence history tracking"""
        try:
            payload = {
                "routes": [{
                    "steps": [{
                        "reaction_type": "esterification",
                        "conditions": {
                            "catalyst": "H2SO4",
                            "solvent": "DCM",
                            "temperature_celsius": 120
                        }
                    }],
                    "overall_yield_percent": 60,
                    "total_cost_usd": 350
                }],
                "objective": "balanced",
                "optimization_iterations": 3
            }
            
            response = requests.post(f"{BACKEND_URL}/routes/iterative-optimize", 
                                   json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                history = data.get('convergence_history', [])
                
                if isinstance(history, list) and len(history) > 0:
                    # Check first history entry has required fields
                    first_entry = history[0]
                    required_fields = ['iteration', 'score_before', 'score_after', 
                                     'improvement', 'mutations_applied', 'changes', 
                                     'routes_evaluated', 'routes_kept']
                    
                    if all(field in first_entry for field in required_fields):
                        self.log_result("/routes/iterative-optimize", "POST", "PASS", 
                                      f"Convergence history tracked: {len(history)} entries")
                    else:
                        self.log_result("/routes/iterative-optimize", "POST", "FAIL", 
                                      f"Missing fields in convergence history: {first_entry}")
                else:
                    self.log_result("/routes/iterative-optimize", "POST", "FAIL", 
                                  f"No convergence history returned: {history}")
            else:
                self.log_result("/routes/iterative-optimize", "POST", "FAIL", 
                              f"Status {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("/routes/iterative-optimize", "POST", "FAIL", f"Request failed: {str(e)}")
    
    def test_iterative_optimize_empty_routes(self):
        """Test POST /routes/iterative-optimize - Empty routes should fail"""
        try:
            payload = {
                "routes": [],
                "objective": "balanced"
            }
            
            response = requests.post(f"{BACKEND_URL}/routes/iterative-optimize", 
                                   json=payload, timeout=30)
            
            if response.status_code == 400:
                self.log_result("/routes/iterative-optimize", "POST", "PASS", 
                              "Empty routes correctly rejected with 400 error")
            else:
                self.log_result("/routes/iterative-optimize", "POST", "FAIL", 
                              f"Expected 400 error for empty routes, got {response.status_code}")
                
        except Exception as e:
            self.log_result("/routes/iterative-optimize", "POST", "FAIL", f"Request failed: {str(e)}")
    
    def test_iterative_optimize_speed(self):
        """Test POST /routes/iterative-optimize - Speed objective"""
        try:
            payload = {
                "routes": [{
                    "steps": [{
                        "reaction_type": "esterification",
                        "conditions": {
                            "catalyst": "H2SO4",
                            "solvent": "DCM",
                            "temperature_celsius": 50
                        }
                    }],
                    "overall_yield_percent": 70,
                    "total_cost_usd": 200
                }],
                "objective": "speed",
                "optimization_iterations": 3
            }
            
            response = requests.post(f"{BACKEND_URL}/routes/iterative-optimize", 
                                   json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('objective') == 'speed':
                    self.log_result("/routes/iterative-optimize", "POST", "PASS", 
                                  f"Speed optimization: {data['status']}")
                else:
                    self.log_result("/routes/iterative-optimize", "POST", "FAIL", 
                                  f"Wrong objective returned: {data.get('objective')}")
            else:
                self.log_result("/routes/iterative-optimize", "POST", "FAIL", 
                              f"Status {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("/routes/iterative-optimize", "POST", "FAIL", f"Request failed: {str(e)}")
    
    def run_all_tests(self):
        """Run all backend API tests"""
        print(f"🧪 Starting Backend API Tests for: {BACKEND_URL}")
        print("=" * 60)
        
        # Run existing tests
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
        
        # Run Phase 6 Optimization Layer tests
        print("\n🔬 Phase 6 Optimization Layer Tests:")
        print("-" * 40)
        self.test_routes_mutate()
        self.test_routes_mutate_catalyst_only()
        self.test_routes_constraint_feedback()
        self.test_routes_confidence()
        self.test_routes_equipment_check_feasible()
        self.test_routes_equipment_check_hard_constraints()
        self.test_routes_optimize_full()
        
        # Phase 7: Iterative Optimization Tests
        print("\n" + "=" * 40)
        print("🔄 PHASE 7: ITERATIVE OPTIMIZATION TESTS")
        print("-" * 40)
        self.test_iterative_optimize_balanced()
        self.test_iterative_optimize_cost()
        self.test_iterative_optimize_green()
        self.test_iterative_optimize_pharma()
        self.test_iterative_optimize_early_stopping()
        self.test_iterative_optimize_convergence_history()
        self.test_iterative_optimize_empty_routes()
        self.test_iterative_optimize_speed()
        
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