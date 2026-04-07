"""
Level 2 — API Tests
Test HTTP endpoints for response format, status codes, and latency.
"""
import time
import pytest


# ═══════════════════════════════════════════════════════════════════
#  Root / Health
# ═══════════════════════════════════════════════════════════════════

class TestRootEndpoint:

    def test_root_returns_200(self, test_client):
        res = test_client.get("/api/")
        assert res.status_code == 200

    def test_root_contains_message(self, test_client):
        data = test_client.get("/api/").json()
        assert "message" in data
        assert "endpoints" in data


# ═══════════════════════════════════════════════════════════════════
#  Molecule Validation
# ═══════════════════════════════════════════════════════════════════

class TestMoleculeValidation:

    def test_validate_valid_molecule(self, test_client, sample_molecules):
        res = test_client.post(
            "/api/molecule/validate",
            json={"smiles": sample_molecules["aspirin"]},
        )
        assert res.status_code == 200
        assert res.json()["valid"] is True

    def test_validate_invalid_molecule(self, test_client):
        res = test_client.post(
            "/api/molecule/validate",
            json={"smiles": "NOT_VALID_SMILES"},
        )
        assert res.status_code == 200
        assert res.json()["valid"] is False

    def test_validate_missing_field(self, test_client):
        res = test_client.post("/api/molecule/validate", json={})
        assert res.status_code == 422  # Pydantic validation error

    def test_validate_ethanol(self, test_client):
        res = test_client.post(
            "/api/molecule/validate",
            json={"smiles": "CCO"},
        )
        assert res.status_code == 200
        assert res.json()["valid"] is True


# ═══════════════════════════════════════════════════════════════════
#  Molecule Analysis
# ═══════════════════════════════════════════════════════════════════

class TestMoleculeAnalysis:

    def test_analyze_valid_molecule(self, test_client, sample_molecules):
        res = test_client.post(
            "/api/molecule/analyze",
            json={"smiles": sample_molecules["aspirin"]},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["valid"] is True
        assert "molecular_weight" in data
        assert "logp" in data
        assert "h_donors" in data
        assert "h_acceptors" in data
        assert "molecular_formula" in data

    def test_analyze_returns_correct_formula(self, test_client):
        res = test_client.post(
            "/api/molecule/analyze",
            json={"smiles": "CCO"},
        )
        assert res.status_code == 200
        assert res.json()["molecular_formula"] == "C2H6O"

    def test_analyze_invalid_molecule(self, test_client):
        res = test_client.post(
            "/api/molecule/analyze",
            json={"smiles": "INVALID"},
        )
        # Should return 400 or 500 for invalid molecules
        assert res.status_code in (400, 500)


# ═══════════════════════════════════════════════════════════════════
#  Condition Prediction
# ═══════════════════════════════════════════════════════════════════

class TestConditionPrediction:

    def test_predict_conditions_success(self, test_client):
        res = test_client.post(
            "/api/conditions/predict",
            json={
                "reactants": ["c1ccccc1", "CC(=O)Cl"],
                "products": ["CC(=O)c1ccccc1"],
                "reaction_type": "Friedel-Crafts acylation",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert "conditions" in data

    def test_predict_conditions_has_temperature(self, test_client):
        res = test_client.post(
            "/api/conditions/predict",
            json={
                "reactants": ["CCO", "CC(=O)O"],
                "products": ["CCOC(C)=O"],
            },
        )
        assert res.status_code == 200
        conditions = res.json()["conditions"]
        assert "temperature_celsius" in conditions


# ═══════════════════════════════════════════════════════════════════
#  Equipment Recommendation
# ═══════════════════════════════════════════════════════════════════

class TestEquipmentRecommendation:

    def test_recommend_equipment_success(self, test_client):
        res = test_client.post(
            "/api/equipment/recommend",
            json={
                "reaction_type": "organic",
                "scale_mg": 100,
                "temperature_c": 80,
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert "reactor_recommendations" in data
        assert "complete_setup" in data

    def test_recommend_equipment_fields(self, test_client):
        res = test_client.post(
            "/api/equipment/recommend",
            json={"reaction_type": "general", "scale_mg": 500},
        )
        assert res.status_code == 200
        recs = res.json()["reactor_recommendations"]
        assert isinstance(recs, list)


# ═══════════════════════════════════════════════════════════════════
#  Template Stats
# ═══════════════════════════════════════════════════════════════════

class TestTemplateStats:

    def test_template_stats_endpoint(self, test_client):
        res = test_client.get("/api/templates/stats")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert "statistics" in data


# ═══════════════════════════════════════════════════════════════════
#  Latency
# ═══════════════════════════════════════════════════════════════════

class TestAPILatency:

    def test_validate_endpoint_latency(self, test_client, sample_molecules):
        """Validation endpoint should respond in < 500ms on average."""
        times = []
        for smi in list(sample_molecules.values())[:4]:
            start = time.perf_counter()
            test_client.post("/api/molecule/validate", json={"smiles": smi})
            times.append(time.perf_counter() - start)

        avg_ms = (sum(times) / len(times)) * 1000
        assert avg_ms < 500, f"Average latency {avg_ms:.0f}ms exceeds 500ms threshold"

    def test_analyze_endpoint_latency(self, test_client, sample_molecules):
        """Analysis endpoint should respond in < 500ms on average."""
        times = []
        for smi in list(sample_molecules.values())[:4]:
            start = time.perf_counter()
            test_client.post("/api/molecule/analyze", json={"smiles": smi})
            times.append(time.perf_counter() - start)

        avg_ms = (sum(times) / len(times)) * 1000
        assert avg_ms < 500, f"Average latency {avg_ms:.0f}ms exceeds 500ms threshold"
