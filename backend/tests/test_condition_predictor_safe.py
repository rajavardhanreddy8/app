import numpy as np

from services.condition_predictor import ConditionPredictor, SafeLabelEncoder


class _AlwaysFailModel:
    def predict(self, _features):
        return np.array([25.0])

    def predict_proba(self, _features):
        raise RuntimeError("forced model failure")


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
        "reaction_type": "oxidation",
        "catalyst": "NeverSeenCatalyst",
    }

    result = predictor.predict_safe(reaction)

    assert result == {
        "temperature_celsius": 25.0,
        "catalyst": "unknown",
        "solvent": "THF",
        "confidence": 0.0,
        "fallback": True,
    }
