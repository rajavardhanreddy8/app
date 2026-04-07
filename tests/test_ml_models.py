"""
Level 1 — Unit Tests
Test each service/module independently.
"""
import numpy as np
import pytest


# ═══════════════════════════════════════════════════════════════════
#  MolecularService
# ═══════════════════════════════════════════════════════════════════

class TestMolecularService:

    def test_parse_valid_smiles(self, molecular_service):
        result = molecular_service.parse_smiles("CCO")
        assert result["valid"] is True
        assert result["molecular_formula"] == "C2H6O"
        assert 40 < result["molecular_weight"] < 50  # ethanol ~46.07

    def test_parse_invalid_smiles(self, molecular_service):
        result = molecular_service.parse_smiles("NOT_A_SMILES!!!")
        assert result["valid"] is False

    def test_parse_empty_smiles(self, molecular_service):
        # RDKit treats empty string as a valid empty molecule
        result = molecular_service.parse_smiles("")
        # Either valid (RDKit accepts) or invalid — service should not crash
        assert "valid" in result

    def test_validate_aspirin(self, molecular_service, sample_molecules):
        result = molecular_service.validate_smiles(sample_molecules["aspirin"])
        assert result["valid"] is True

    def test_validate_caffeine(self, molecular_service, sample_molecules):
        result = molecular_service.validate_smiles(sample_molecules["caffeine"])
        assert result["valid"] is True

    def test_validate_invalid_string(self, molecular_service):
        result = molecular_service.validate_smiles("ZZZZZ")
        assert result["valid"] is False

    def test_molecular_properties_keys(self, molecular_service, sample_molecules):
        result = molecular_service.parse_smiles(sample_molecules["aspirin"])
        expected_keys = {
            "valid", "smiles", "canonical_smiles", "molecular_weight",
            "logp", "h_donors", "h_acceptors", "tpsa",
            "rotatable_bonds", "lipinski_violations", "num_atoms",
            "num_bonds", "molecular_formula",
        }
        assert expected_keys.issubset(set(result.keys()))

    def test_fingerprint_computation(self, molecular_service, sample_molecules):
        fp = molecular_service.calculate_fingerprint(sample_molecules["ethanol"])
        assert fp is not None
        assert len(fp) == 2048
        assert all(bit in (0, 1) for bit in fp)

    def test_reagent_cost_estimation(self, molecular_service, sample_molecules):
        cost = molecular_service.estimate_reagent_cost(sample_molecules["aspirin"])
        assert isinstance(cost, float)
        assert cost > 0


# ═══════════════════════════════════════════════════════════════════
#  ConditionPredictor
# ═══════════════════════════════════════════════════════════════════

class TestConditionPredictor:

    def test_predict_returns_required_keys(self, condition_predictor, sample_reaction):
        result = condition_predictor.predict_conditions(sample_reaction)
        assert "temperature_celsius" in result
        assert "catalyst" in result
        assert "solvent" in result
        assert "confidence" in result

    def test_temperature_in_range(self, condition_predictor, sample_reaction):
        result = condition_predictor.predict_conditions(sample_reaction)
        temp = result["temperature_celsius"]
        assert -50 <= temp <= 200, f"Temperature {temp} out of expected range"

    def test_confidence_values(self, condition_predictor, sample_reaction):
        result = condition_predictor.predict_conditions(sample_reaction)
        assert result["confidence"] in ("low", "medium", "high")

    def test_feature_computation_shape(self, condition_predictor, sample_reaction):
        features = condition_predictor.compute_reaction_features(sample_reaction)
        assert isinstance(features, np.ndarray)
        assert features.shape == (100,)

    def test_feature_computation_empty_reaction(self, condition_predictor):
        features = condition_predictor.compute_reaction_features({})
        assert features.shape == (100,)
        # All zeros when no data
        assert np.allclose(features, 0)


# ═══════════════════════════════════════════════════════════════════
#  CostDatabase
# ═══════════════════════════════════════════════════════════════════

class TestCostDatabase:

    def test_known_reagent_ethanol(self, cost_database):
        cost = cost_database.get_reagent_cost("CCO")
        assert cost is not None
        assert isinstance(cost, float)
        assert cost > 0

    def test_unknown_reagent_estimated(self, cost_database):
        cost = cost_database.get_reagent_cost("C1CCCCCCC1")  # cyclooctane
        assert isinstance(cost, float)
        assert cost > 0

    def test_reaction_cost_all_keys(self, cost_database):
        costs = cost_database.calculate_reaction_cost(
            reactants=["c1ccccc1", "CC(=O)Cl"],
            reagents=[],
            catalyst="AlCl3",
            solvent="DCM",
            target_mass_mg=100.0,
        )
        for key in ("reactants_cost", "reagents_cost", "catalyst_cost", "solvent_cost", "total_cost"):
            assert key in costs
            assert costs[key] >= 0

    def test_total_cost_is_sum(self, cost_database):
        costs = cost_database.calculate_reaction_cost(
            reactants=["CCO"],
            reagents=["CC(=O)O"],
            catalyst="Pd",
            solvent="THF",
        )
        expected_total = (
            costs["reactants_cost"]
            + costs["reagents_cost"]
            + costs["catalyst_cost"]
            + costs["solvent_cost"]
        )
        assert abs(costs["total_cost"] - expected_total) < 0.01

    def test_database_stats(self, cost_database):
        stats = cost_database.get_database_stats()
        assert stats["total_reagents"] > 0
        assert stats["avg_price"] > 0


# ═══════════════════════════════════════════════════════════════════
#  EquipmentRecommender
# ═══════════════════════════════════════════════════════════════════

class TestEquipmentRecommender:

    def test_recommend_returns_list(self, equipment_recommender):
        recs = equipment_recommender.recommend_reactor("organic", scale_mg=100)
        assert isinstance(recs, list)
        assert len(recs) > 0

    def test_recommendation_fields(self, equipment_recommender):
        recs = equipment_recommender.recommend_reactor("general", scale_mg=500)
        for rec in recs:
            assert "reactor" in rec
            assert "score" in rec
            assert "reasons" in rec
            assert rec["score"] > 0

    def test_complete_setup_keys(self, equipment_recommender):
        setup = equipment_recommender.recommend_complete_setup(
            reaction_type="organic",
            scale_mg=100,
            temperature_c=80,
        )
        for key in ("reactor", "workup", "purification", "analytical"):
            assert key in setup

    def test_large_scale_uses_distillation(self, equipment_recommender):
        setup = equipment_recommender.recommend_complete_setup(
            reaction_type="industrial",
            scale_mg=50000,
            temperature_c=60,
        )
        purification_names = [p["equipment"] for p in setup["purification"]]
        assert "Distillation Column" in purification_names

    def test_database_stats(self, equipment_recommender):
        stats = equipment_recommender.get_database_stats()
        assert stats["total_reactors"] > 0
        assert stats["total_analytical"] > 0
