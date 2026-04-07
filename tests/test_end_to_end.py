"""
Level 3 — End-to-End Tests
Full pipeline: Validate → Analyze → Predict Conditions → Recommend Equipment.
"""
import pytest


class TestFullPipelineAspirin:
    """Full pipeline for Aspirin (CC(=O)Oc1ccccc1C(=O)O)."""

    SMILES = "CC(=O)Oc1ccccc1C(=O)O"

    def test_step1_validate(self, test_client):
        res = test_client.post("/api/molecule/validate", json={"smiles": self.SMILES})
        assert res.status_code == 200
        assert res.json()["valid"] is True

    def test_step2_analyze(self, test_client):
        res = test_client.post("/api/molecule/analyze", json={"smiles": self.SMILES})
        assert res.status_code == 200
        data = res.json()
        assert data["valid"] is True
        assert data["molecular_formula"] == "C9H8O4"
        assert 170 < data["molecular_weight"] < 190  # aspirin ~180.16

    def test_step3_predict_conditions(self, test_client):
        res = test_client.post(
            "/api/conditions/predict",
            json={
                "reactants": ["c1ccccc1O", "CC(=O)Cl"],
                "products": [self.SMILES],
                "reaction_type": "esterification",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert "temperature_celsius" in data["conditions"]

    def test_step4_recommend_equipment(self, test_client):
        res = test_client.post(
            "/api/equipment/recommend",
            json={
                "reaction_type": "esterification",
                "scale_mg": 1000,
                "temperature_c": 60,
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert len(data["reactor_recommendations"]) > 0
        assert data["complete_setup"]["reactor"] is not None


class TestFullPipelineEthanol:
    """Full pipeline for a simple molecule: Ethanol (CCO)."""

    SMILES = "CCO"

    def test_step1_validate(self, test_client):
        res = test_client.post("/api/molecule/validate", json={"smiles": self.SMILES})
        assert res.status_code == 200
        assert res.json()["valid"] is True

    def test_step2_analyze(self, test_client):
        res = test_client.post("/api/molecule/analyze", json={"smiles": self.SMILES})
        assert res.status_code == 200
        data = res.json()
        assert data["valid"] is True
        assert data["molecular_formula"] == "C2H6O"

    def test_step3_predict_conditions(self, test_client):
        res = test_client.post(
            "/api/conditions/predict",
            json={
                "reactants": ["C=C", "O"],
                "products": [self.SMILES],
                "reaction_type": "hydration",
            },
        )
        assert res.status_code == 200

    def test_step4_recommend_equipment(self, test_client):
        res = test_client.post(
            "/api/equipment/recommend",
            json={
                "reaction_type": "hydration",
                "scale_mg": 500,
                "temperature_c": 40,
            },
        )
        assert res.status_code == 200


class TestPipelineInvalidInput:
    """Ensure invalid input fails gracefully at the validation step."""

    def test_invalid_smiles_rejected(self, test_client):
        res = test_client.post(
            "/api/molecule/validate",
            json={"smiles": "THIS_IS_NOT_CHEMISTRY"},
        )
        assert res.status_code == 200
        assert res.json()["valid"] is False

    def test_invalid_analyze_returns_error(self, test_client):
        res = test_client.post(
            "/api/molecule/analyze",
            json={"smiles": "GARBAGE_SMILES"},
        )
        assert res.status_code in (400, 500)


class TestCrossServiceConsistency:
    """Verify outputs from different services are consistent with each other."""

    def test_molecular_weight_consistency(self, test_client):
        """Aspirin analysis should give a MW the cost estimator would expect for a mid-complexity molecule."""
        # Analyze molecule
        res = test_client.post(
            "/api/molecule/analyze",
            json={"smiles": "CC(=O)Oc1ccccc1C(=O)O"},
        )
        data = res.json()
        mw = data["molecular_weight"]

        # MW for aspirin should be ~180
        assert 170 < mw < 190, f"Unexpected MW: {mw}"

        # Number of atoms should be reasonable for MW ~180
        assert data["num_atoms"] > 5

    def test_all_example_molecules_valid(self, test_client, sample_molecules):
        """Every sample molecule must pass validation."""
        for name, smiles in sample_molecules.items():
            res = test_client.post(
                "/api/molecule/validate",
                json={"smiles": smiles},
            )
            assert res.status_code == 200
            assert res.json()["valid"] is True, f"{name} ({smiles}) failed validation"
