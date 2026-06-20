"""
Phase 1 tests for ConditionPredictor.

Heavy deps: numpy, sklearn, xgboost, rdkit.
Uses pytest.importorskip so the entire file is SKIPPED (not ERROR)
if any dep is missing.
"""
import sys
import os
import types
import pytest

# ── Guard heavy deps ─────────────────────────────────────────────
np = pytest.importorskip("numpy")
pytest.importorskip("sklearn")
pytest.importorskip("xgboost")
pytest.importorskip("rdkit")

# Stub structlog if missing (condition_predictor chains into it via
# reaction_database -> motor, but doesn't use structlog directly)
if "structlog" not in sys.modules:
    _sl = types.ModuleType("structlog")
    _sl.get_logger = lambda *a, **kw: __import__("logging").getLogger("stub")
    _sl.stdlib = types.ModuleType("structlog.stdlib")
    _sl.stdlib.filter_by_level = None
    _sl.stdlib.LoggerFactory = lambda: None
    _sl.processors = types.ModuleType("structlog.processors")
    _sl.processors.TimeStamper = lambda **kw: None
    _sl.processors.JSONRenderer = lambda: None
    _sl.configure = lambda **kw: None
    sys.modules["structlog"] = _sl
    sys.modules["structlog.stdlib"] = _sl.stdlib
    sys.modules["structlog.processors"] = _sl.processors

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_db")

from services.condition_predictor import ConditionPredictor
from sklearn.preprocessing import LabelEncoder


# ── SafeLabelEncoder / LabelEncoder tests ─────────────────────────

class TestSafeLabelEncoder:
    """Test sklearn LabelEncoder behavior used by ConditionPredictor."""

    def test_known_label_encodes_correctly(self):
        enc = LabelEncoder()
        enc.fit(["Water", "THF", "DCM"])
        result = enc.transform(["THF"])[0]
        assert isinstance(int(result), int)

    def test_unseen_label_raises(self):
        """LabelEncoder raises on unseen labels by default."""
        enc = LabelEncoder()
        enc.fit(["Water", "THF"])
        with pytest.raises(ValueError):
            enc.transform(["UnknownSolvent"])

    def test_roundtrip_encode_decode(self):
        enc = LabelEncoder()
        labels = ["DCM", "Water", "THF", "DMF"]
        enc.fit(labels)
        encoded = enc.transform(labels)
        decoded = enc.inverse_transform(encoded)
        assert list(decoded) == labels


# ── Feature computation tests ─────────────────────────────────────

class TestFeatureComputation:
    """Test ConditionPredictor.compute_reaction_features."""

    @pytest.fixture(scope="class")
    def predictor(self):
        return ConditionPredictor(model_dir=str(
            os.path.join(os.path.dirname(__file__), "..", "models")
        ))

    def test_returns_numpy_array(self, predictor):
        rxn = {
            "reactants": ["c1ccccc1", "CC(=O)Cl"],
            "products": ["CC(=O)c1ccccc1"],
            "reaction_type": "Friedel-Crafts acylation",
        }
        features = predictor.compute_reaction_features(rxn)
        assert isinstance(features, np.ndarray)

    def test_fixed_feature_length(self, predictor):
        rxn = {
            "reactants": ["CCO"],
            "products": ["CCOC(C)=O"],
            "reaction_type": "esterification",
        }
        features = predictor.compute_reaction_features(rxn)
        assert features.shape == (predictor.CONDITION_FEATURE_SIZE,)

    def test_empty_reactants_returns_zeros(self, predictor):
        rxn = {"reactants": [], "products": [], "reaction_type": "unknown"}
        features = predictor.compute_reaction_features(rxn)
        assert features.shape == (predictor.CONDITION_FEATURE_SIZE,)
        assert np.all(features == 0)

    def test_invalid_smiles_degrades_gracefully(self, predictor):
        rxn = {
            "reactants": ["INVALID_SMILES"],
            "products": ["ALSO_INVALID"],
            "reaction_type": "unknown",
        }
        features = predictor.compute_reaction_features(rxn)
        assert features.shape == (predictor.CONDITION_FEATURE_SIZE,)  # Should pad with zeros


# ── Prediction fallback tests ─────────────────────────────────────

class TestPredictionFallback:
    """When no trained model is available, predict_conditions returns defaults."""

    def test_no_model_returns_low_confidence(self):
        pred = ConditionPredictor(model_dir="/nonexistent")
        pred.models_loaded = False
        result = pred.predict_conditions({
            "reactants": ["CCO"],
            "products": ["CCOC(C)=O"],
            "reaction_type": "unknown_new_reaction",
        })
        assert result["confidence"] == "low"
        assert result["temperature_celsius"] == 25.0

    def test_fallback_has_all_keys(self):
        pred = ConditionPredictor(model_dir="/nonexistent")
        pred.models_loaded = False
        result = pred.predict_conditions({"reactants": ["CCO"], "products": ["CC=O"]})
        for key in ("temperature_celsius", "catalyst", "solvent", "confidence", "time_hours"):
            assert key in result, f"Missing key: {key}"
import numpy as np

from services.condition_predictor import ConditionPredictor, SafeLabelEncoder


class _AlwaysFailModel:
    def predict(self, _features):
        return np.array([25.0])

    def predict_proba(self, _features):
        raise RuntimeError("forced model failure")


class _FakeRegressorBundle:
    best_model_name = "fake_regressor"
    skipped_models = {}

    def prediction_summary(self, _features, clip_range=None):
        return {
            "individual_predictions": {"random_forest": 42.0, "xgboost": 44.0},
            "ensemble_prediction": 43.0,
            "prediction_std": 1.0,
            "best_model": self.best_model_name,
            "model_metrics": {"ensemble": {"test_mae": 2.0}},
        }

    def predict(self, _features, clip_range=None):
        return 43.0


class _FakeClassifierBundle:
    def __init__(self, label):
        self.label = label
        self.best_model_name = "fake_classifier"
        self.skipped_models = {}

    def prediction_summary(self, _features):
        return {
            "individual_predictions": {
                "random_forest": {"prediction": self.label, "confidence": 0.8},
                "xgboost": {"prediction": self.label, "confidence": 0.7},
            },
            "ensemble_prediction": self.label,
            "consensus_fraction": 1.0,
            "alternatives": [{"option": self.label, "votes": 2, "confidence": 0.75}],
            "best_model": self.best_model_name,
            "model_metrics": {"ensemble": {"accuracy": 1.0, "macro_f1": 1.0}},
        }


def test_safe_label_encoder_unseen_maps_to_unknown_index_zero():
    encoder = SafeLabelEncoder()
    encoder.fit(["Pd/C", "CuI"])

    encoded = encoder.transform(["Pd/C", "BrandNewCatalyst"])

    assert int(encoded[0]) != 0
    assert int(encoded[1]) == 0


def test_predict_safe_with_unseen_catalyst_returns_fallback_instead_of_raising():
    predictor = ConditionPredictor(model_dir="/tmp/condition_predictor_test_models")
    predictor.models_loaded = True

    predictor.temp_model = _AlwaysFailModel()
    predictor.catalyst_model = _AlwaysFailModel()
    predictor.solvent_model = _AlwaysFailModel()

    predictor.catalyst_encoder.fit(["Pd/C", "CuI"])
    predictor.solvent_encoder.fit(["THF", "EtOH"])

    reaction = {
        "reactants": ["CCO"],
        "products": ["CC=O"],
        "reaction_type": "unknown_new_reaction",
        "catalyst": "NeverSeenCatalyst",
    }

    result = predictor.predict_safe(reaction)

    assert result["temperature_celsius"] == 25.0
    assert result["solvent"] == "THF"
    assert result["confidence"] in {"low", 0.0}
    assert result["fallback"] is True
    assert result["source"] == "fallback"


def test_chemistry_prior_includes_model_decision_and_overrides_ml():
    predictor = ConditionPredictor(model_dir="/tmp/condition_predictor_test_models")
    predictor.models_loaded = False

    result = predictor.predict_conditions({
        "reactants": ["O=[N+]([O-])c1ccccc1"],
        "products": ["Nc1ccccc1"],
        "reaction_type": "nitro_reduction",
    })

    assert result["catalyst"] in {"Fe", "Fe powder"}
    assert result["model_decision"] == "chemistry_prior"
    assert "model_results" in result
    assert "ensemble_consensus" in result


def test_condition_predictor_returns_multi_model_results_for_unknown_reaction():
    predictor = ConditionPredictor(model_dir="/tmp/condition_predictor_test_models")
    predictor.models_loaded = True
    predictor.temp_multi_model = _FakeRegressorBundle()
    predictor.catalyst_multi_model = _FakeClassifierBundle("Pd/C")
    predictor.solvent_multi_model = _FakeClassifierBundle("EtOAc")

    result = predictor.predict_conditions({
        "reactants": ["CCO"],
        "products": ["CC=O"],
        "reaction_type": "custom_reaction_without_prior",
    })

    assert result["temperature_celsius"] == 43.0
    assert result["catalyst"] == "Pd/C"
    assert result["solvent"] == "EtOAc"
    assert result["model_results"]["temperature"]["ensemble_prediction"] == 43.0
    assert result["ensemble_consensus"]["catalyst"] == "Pd/C"
    assert result["model_decision"] == "ensemble"
