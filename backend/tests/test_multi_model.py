import pickle
import os
import sys

import numpy as np
import pytest

pytest.importorskip("sklearn")
pytest.importorskip("xgboost")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.multi_model import MultiModelClassifier, MultiModelRegressor


def test_multi_model_regressor_trains_predicts_and_reloads(tmp_path):
    rng = np.random.default_rng(42)
    X = rng.normal(size=(80, 8))
    y = 55 + X[:, 0] * 10 - X[:, 1] * 4 + rng.normal(scale=2, size=80)

    model = MultiModelRegressor(random_state=42, svm_max_samples=40, ann_max_samples=50)
    metrics = model.fit(X[:60], y[:60], X[60:], y[60:])

    assert model.models
    assert "ensemble" in metrics
    assert "xgboost" in metrics or "xgboost" in model.skipped_models

    summary = model.prediction_summary(X[0].reshape(1, -1), clip_range=(0, 100))
    assert summary["individual_predictions"]
    assert isinstance(summary["ensemble_prediction"], float)
    assert 0.0 <= summary["ensemble_prediction"] <= 100.0

    path = tmp_path / "regressor.pkl"
    with open(path, "wb") as f:
        pickle.dump(model, f)
    with open(path, "rb") as f:
        loaded = pickle.load(f)

    assert loaded.predict(X[1].reshape(1, -1), clip_range=(0, 100)) is not None


def test_multi_model_classifier_trains_predicts_and_reloads(tmp_path):
    rng = np.random.default_rng(7)
    X = rng.normal(size=(90, 6))
    y = np.where(X[:, 0] + X[:, 1] > 0.5, "Pd/C", np.where(X[:, 2] > 0, "Cu", "None"))

    model = MultiModelClassifier(random_state=7, svm_max_samples=45, ann_max_samples=50)
    metrics = model.fit(X[:70], y[:70], X[70:], y[70:])

    assert model.models
    assert "ensemble" in metrics
    assert "xgboost" in metrics or "xgboost" in model.skipped_models

    summary = model.prediction_summary(X[0].reshape(1, -1))
    assert summary["individual_predictions"]
    assert summary["ensemble_prediction"] in {"Pd/C", "Cu", "None"}
    assert summary["alternatives"]

    path = tmp_path / "classifier.pkl"
    with open(path, "wb") as f:
        pickle.dump(model, f)
    with open(path, "rb") as f:
        loaded = pickle.load(f)

    loaded_summary = loaded.prediction_summary(X[1].reshape(1, -1))
    assert loaded_summary["ensemble_prediction"] in {"Pd/C", "Cu", "None"}
