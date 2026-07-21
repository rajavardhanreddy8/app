"""Reusable multi-model training helpers for ChemPlan ML services."""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

import numpy as np
from sklearn.ensemble import (
    ExtraTreesClassifier,
    ExtraTreesRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.metrics import accuracy_score, f1_score, mean_absolute_error, r2_score
from sklearn.neural_network import MLPClassifier, MLPRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.svm import LinearSVC, SVR

try:
    import xgboost as xgb
except Exception:  # pragma: no cover - handled at runtime when xgboost is absent
    xgb = None

logger = logging.getLogger(__name__)


def _safe_r2(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    if len(y_true) < 2:
        return 0.0
    return float(r2_score(y_true, y_pred))


def _clip_float(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return float(np.clip(float(value), low, high))


def _sample_training_rows(
    X: np.ndarray,
    y: np.ndarray,
    max_samples: Optional[int],
    random_state: int,
) -> Tuple[np.ndarray, np.ndarray, int]:
    if max_samples is None or len(X) <= max_samples:
        return X, y, len(X)

    rng = np.random.default_rng(random_state)
    idx = rng.choice(len(X), size=max_samples, replace=False)
    return X[idx], y[idx], int(max_samples)


@dataclass
class MultiModelRegressor:
    """Train several regression algorithms and expose ensemble predictions."""

    random_state: int = 42
    svm_max_samples: int = 1500
    ann_max_samples: int = 2000
    models: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Dict[str, float]] = field(default_factory=dict)
    best_model_name: Optional[str] = None
    skipped_models: Dict[str, str] = field(default_factory=dict)

    def _candidate_models(self) -> Dict[str, Any]:
        candidates: Dict[str, Any] = {
            "random_forest": RandomForestRegressor(
                n_estimators=160,
                random_state=self.random_state,
                n_jobs=-1,
                min_samples_leaf=2,
            ),
            "extra_trees": ExtraTreesRegressor(
                n_estimators=160,
                random_state=self.random_state,
                n_jobs=-1,
                min_samples_leaf=2,
            ),
            "svm": Pipeline(
                [
                    ("scaler", StandardScaler()),
                    ("model", SVR(C=10.0, epsilon=2.0)),
                ]
            ),
            "ann_mlp": Pipeline(
                [
                    ("scaler", StandardScaler()),
                    (
                        "model",
                        MLPRegressor(
                            hidden_layer_sizes=(64, 32),
                            activation="relu",
                            early_stopping=True,
                            max_iter=300,
                            random_state=self.random_state,
                        ),
                    ),
                ]
            ),
        }
        if xgb is not None:
            candidates = {
                "xgboost": xgb.XGBRegressor(
                    n_estimators=180,
                    max_depth=5,
                    learning_rate=0.06,
                    subsample=0.85,
                    colsample_bytree=0.85,
                    min_child_weight=2,
                    random_state=self.random_state,
                    objective="reg:squarederror",
                ),
                **candidates,
            }
        return candidates

    def fit(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_test: Optional[np.ndarray] = None,
        y_test: Optional[np.ndarray] = None,
    ) -> Dict[str, Dict[str, float]]:
        X_train = np.asarray(X_train)
        y_train = np.asarray(y_train, dtype=float)
        X_test = np.asarray(X_test) if X_test is not None else X_train
        y_test = np.asarray(y_test, dtype=float) if y_test is not None else y_train

        for name, model in self._candidate_models().items():
            max_samples = None
            if name == "svm":
                max_samples = self.svm_max_samples
            elif name == "ann_mlp":
                max_samples = self.ann_max_samples

            train_X, train_y, trained_samples = _sample_training_rows(
                X_train, y_train, max_samples, self.random_state
            )
            try:
                model.fit(train_X, train_y)
                y_train_pred = np.asarray(model.predict(X_train), dtype=float)
                y_test_pred = np.asarray(model.predict(X_test), dtype=float)

                self.models[name] = model
                self.metrics[name] = {
                    "train_mae": float(mean_absolute_error(y_train, y_train_pred)),
                    "test_mae": float(mean_absolute_error(y_test, y_test_pred)),
                    "train_r2": _safe_r2(y_train, y_train_pred),
                    "test_r2": _safe_r2(y_test, y_test_pred),
                    "trained_samples": int(trained_samples),
                }
            except Exception as exc:
                self.skipped_models[name] = str(exc)
                logger.warning("Skipping %s regressor: %s", name, exc)

        if self.models:
            self.best_model_name = min(
                self.models,
                key=lambda key: self.metrics.get(key, {}).get("test_mae", float("inf")),
            )
            self.metrics["ensemble"] = self._ensemble_metrics(
                X_train, y_train, X_test, y_test
            )
        return self.metrics

    def _ensemble_metrics(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_test: np.ndarray,
        y_test: np.ndarray,
    ) -> Dict[str, float]:
        y_train_pred = self.predict_array(X_train)
        y_test_pred = self.predict_array(X_test)
        return {
            "train_mae": float(mean_absolute_error(y_train, y_train_pred)),
            "test_mae": float(mean_absolute_error(y_test, y_test_pred)),
            "train_r2": _safe_r2(y_train, y_train_pred),
            "test_r2": _safe_r2(y_test, y_test_pred),
            "trained_samples": int(len(X_train)),
        }

    def get_best_model(self) -> Optional[Any]:
        if self.best_model_name:
            return self.models.get(self.best_model_name)
        if self.models:
            return next(iter(self.models.values()))
        return None

    def predict_individual(
        self,
        X: np.ndarray,
        clip_range: Optional[Tuple[float, float]] = None,
    ) -> Dict[str, float]:
        if not self.models:
            return {}
        X = np.asarray(X)
        if X.ndim == 1:
            X = X.reshape(1, -1)

        results: Dict[str, float] = {}
        for name, model in self.models.items():
            try:
                value = float(np.asarray(model.predict(X))[0])
                if clip_range is not None:
                    value = _clip_float(value, clip_range[0], clip_range[1])
                results[name] = value
            except Exception as exc:
                logger.warning("Prediction failed for %s regressor: %s", name, exc)
        return results

    def predict_array(
        self,
        X: np.ndarray,
        clip_range: Optional[Tuple[float, float]] = None,
    ) -> np.ndarray:
        X = np.asarray(X)
        if X.ndim == 1:
            X = X.reshape(1, -1)
        if not self.models:
            return np.zeros(len(X), dtype=float)
        preds = []
        for model in self.models.values():
            try:
                preds.append(np.asarray(model.predict(X), dtype=float))
            except Exception:
                continue
        if not preds:
            return np.zeros(len(X), dtype=float)
        values = np.mean(np.vstack(preds), axis=0)
        if clip_range is not None:
            values = np.clip(values, clip_range[0], clip_range[1])
        return values.astype(float)

    def predict(
        self,
        X: np.ndarray,
        clip_range: Optional[Tuple[float, float]] = None,
    ) -> Optional[float]:
        if not self.models:
            return None
        return float(self.predict_array(X, clip_range=clip_range)[0])

    def prediction_summary(
        self,
        X: np.ndarray,
        clip_range: Optional[Tuple[float, float]] = None,
    ) -> Dict[str, Any]:
        individual = self.predict_individual(X, clip_range=clip_range)
        if not individual:
            return {
                "individual_predictions": {},
                "ensemble_prediction": None,
                "best_model": None,
                "model_metrics": self.metrics,
            }
        values = np.array(list(individual.values()), dtype=float)
        return {
            "individual_predictions": {
                key: round(float(value), 3) for key, value in individual.items()
            },
            "ensemble_prediction": round(float(np.mean(values)), 3),
            "prediction_std": round(float(np.std(values)), 3),
            "best_model": self.best_model_name,
            "model_metrics": self.metrics,
            "skipped_models": self.skipped_models,
        }


@dataclass
class MultiModelClassifier:
    """Train several classifiers and expose majority-vote consensus."""

    random_state: int = 42
    svm_max_samples: int = 1500
    ann_max_samples: int = 2000
    models: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Dict[str, float]] = field(default_factory=dict)
    best_model_name: Optional[str] = None
    skipped_models: Dict[str, str] = field(default_factory=dict)
    label_encoder: LabelEncoder = field(default_factory=LabelEncoder)

    def _candidate_models(self) -> Dict[str, Any]:
        candidates: Dict[str, Any] = {
            "random_forest": RandomForestClassifier(
                n_estimators=120,
                random_state=self.random_state,
                n_jobs=-1,
                min_samples_leaf=1,
                class_weight="balanced",
            ),
            "extra_trees": ExtraTreesClassifier(
                n_estimators=120,
                random_state=self.random_state,
                n_jobs=-1,
                min_samples_leaf=1,
                class_weight="balanced",
            ),
            "svm": Pipeline(
                [
                    ("scaler", StandardScaler()),
                    (
                        "model",
                        LinearSVC(
                            C=1.5,
                            class_weight="balanced",
                            dual="auto",
                            max_iter=3000,
                            random_state=self.random_state,
                        ),
                    ),
                ]
            ),
            "ann_mlp": Pipeline(
                [
                    ("scaler", StandardScaler()),
                    (
                        "model",
                        MLPClassifier(
                            hidden_layer_sizes=(48, 24),
                            activation="relu",
                            early_stopping=True,
                            max_iter=200,
                            random_state=self.random_state,
                        ),
                    ),
                ]
            ),
        }
        if xgb is not None:
            candidates = {
                "xgboost": xgb.XGBClassifier(
                    n_estimators=120,
                    max_depth=4,
                    learning_rate=0.08,
                    subsample=0.85,
                    colsample_bytree=0.85,
                    random_state=self.random_state,
                    eval_metric="mlogloss",
                ),
                **candidates,
            }
        return candidates

    def fit(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_test: Optional[np.ndarray] = None,
        y_test: Optional[np.ndarray] = None,
    ) -> Dict[str, Dict[str, float]]:
        X_train = np.asarray(X_train)
        y_train_raw = np.asarray([str(y) for y in y_train], dtype=object)
        if len(set(y_train_raw)) < 2:
            self.skipped_models["all"] = "classification requires at least two classes"
            return self.metrics

        self.label_encoder.fit(y_train_raw)
        y_train_enc = self.label_encoder.transform(y_train_raw)

        X_test = np.asarray(X_test) if X_test is not None else X_train
        y_test_raw = np.asarray([str(y) for y in (y_test if y_test is not None else y_train)], dtype=object)
        known_test_mask = np.isin(y_test_raw, self.label_encoder.classes_)
        X_test_known = X_test[known_test_mask] if len(X_test) == len(known_test_mask) else X_test
        y_test_known_raw = y_test_raw[known_test_mask] if len(y_test_raw) == len(known_test_mask) else y_test_raw
        if len(y_test_known_raw) == 0:
            X_test_known = X_train
            y_test_known_raw = y_train_raw
        y_test_enc = self.label_encoder.transform(y_test_known_raw)

        for name, model in self._candidate_models().items():
            max_samples = None
            if name == "svm":
                max_samples = self.svm_max_samples
            elif name == "ann_mlp":
                max_samples = self.ann_max_samples

            train_X, train_y, trained_samples = _sample_training_rows(
                X_train, y_train_enc, max_samples, self.random_state
            )
            try:
                if len(set(train_y)) < 2:
                    raise ValueError("sampled subset has fewer than two classes")
                model.fit(train_X, train_y)
                train_pred = np.asarray(model.predict(X_train), dtype=int)
                test_pred = np.asarray(model.predict(X_test_known), dtype=int)
                self.models[name] = model
                self.metrics[name] = {
                    "train_accuracy": float(accuracy_score(y_train_enc, train_pred)),
                    "accuracy": float(accuracy_score(y_test_enc, test_pred)),
                    "macro_f1": float(f1_score(y_test_enc, test_pred, average="macro", zero_division=0)),
                    "trained_samples": int(trained_samples),
                }
            except Exception as exc:
                self.skipped_models[name] = str(exc)
                logger.warning("Skipping %s classifier: %s", name, exc)

        if self.models:
            self.best_model_name = max(
                self.models,
                key=lambda key: (
                    self.metrics.get(key, {}).get("accuracy", 0.0),
                    self.metrics.get(key, {}).get("macro_f1", 0.0),
                ),
            )
            self.metrics["ensemble"] = self._ensemble_metrics(X_test_known, y_test_enc)
        return self.metrics

    def _ensemble_metrics(self, X_test: np.ndarray, y_test_enc: np.ndarray) -> Dict[str, float]:
        pred_labels = self.predict_array(X_test, return_encoded=True)
        return {
            "accuracy": float(accuracy_score(y_test_enc, pred_labels)),
            "macro_f1": float(f1_score(y_test_enc, pred_labels, average="macro", zero_division=0)),
            "trained_samples": int(len(X_test)),
        }

    def get_best_model(self) -> Optional[Any]:
        if self.best_model_name:
            return self.models.get(self.best_model_name)
        if self.models:
            return next(iter(self.models.values()))
        return None

    def _confidence_for_model(self, model: Any, X: np.ndarray, pred_idx: int) -> Optional[float]:
        if not hasattr(model, "predict_proba"):
            return None
        try:
            proba = np.asarray(model.predict_proba(X))[0]
            classes = getattr(model, "classes_", None)
            if classes is None and isinstance(model, Pipeline):
                classes = getattr(model.steps[-1][1], "classes_", None)
            if classes is not None:
                matches = np.where(np.asarray(classes, dtype=int) == int(pred_idx))[0]
                if len(matches):
                    return float(proba[int(matches[0])])
            if 0 <= pred_idx < len(proba):
                return float(proba[pred_idx])
        except Exception:
            return None
        return None

    def predict_individual(self, X: np.ndarray) -> Dict[str, Dict[str, Any]]:
        if not self.models:
            return {}
        X = np.asarray(X)
        if X.ndim == 1:
            X = X.reshape(1, -1)

        results: Dict[str, Dict[str, Any]] = {}
        for name, model in self.models.items():
            try:
                pred_idx = int(np.asarray(model.predict(X))[0])
                label = str(self.label_encoder.inverse_transform([pred_idx])[0])
                confidence = self._confidence_for_model(model, X, pred_idx)
                results[name] = {
                    "prediction": label,
                    "confidence": round(float(confidence), 4) if confidence is not None else None,
                }
            except Exception as exc:
                logger.warning("Prediction failed for %s classifier: %s", name, exc)
        return results

    def predict_array(self, X: np.ndarray, return_encoded: bool = False) -> np.ndarray:
        X = np.asarray(X)
        if X.ndim == 1:
            X = X.reshape(1, -1)
        encoded_predictions = []
        for row in X:
            summary = self.prediction_summary(row.reshape(1, -1))
            label = summary.get("ensemble_prediction")
            if label is None:
                encoded_predictions.append(0)
            else:
                encoded_predictions.append(int(self.label_encoder.transform([str(label)])[0]))
        encoded = np.asarray(encoded_predictions, dtype=int)
        if return_encoded:
            return encoded
        return self.label_encoder.inverse_transform(encoded)

    def prediction_summary(self, X: np.ndarray) -> Dict[str, Any]:
        individual = self.predict_individual(X)
        if not individual:
            return {
                "individual_predictions": {},
                "ensemble_prediction": None,
                "best_model": None,
                "model_metrics": self.metrics,
            }

        votes = [item["prediction"] for item in individual.values()]
        counts = Counter(votes)
        top_count = max(counts.values())
        winners = [label for label, count in counts.items() if count == top_count]

        if len(winners) == 1:
            consensus = winners[0]
        elif self.best_model_name and self.best_model_name in individual:
            consensus = individual[self.best_model_name]["prediction"]
        else:
            consensus = sorted(winners)[0]

        alternatives = []
        by_label_confidence: Dict[str, list] = defaultdict(list)
        for item in individual.values():
            if item.get("confidence") is not None:
                by_label_confidence[item["prediction"]].append(float(item["confidence"]))
        for label, count in counts.most_common():
            avg_conf = by_label_confidence.get(label)
            alternatives.append(
                {
                    "option": label,
                    "votes": int(count),
                    "confidence": round(float(np.mean(avg_conf)), 4) if avg_conf else None,
                }
            )

        return {
            "individual_predictions": individual,
            "ensemble_prediction": consensus,
            "consensus_fraction": round(float(top_count / len(votes)), 4),
            "alternatives": alternatives,
            "best_model": self.best_model_name,
            "model_metrics": self.metrics,
            "skipped_models": self.skipped_models,
        }
