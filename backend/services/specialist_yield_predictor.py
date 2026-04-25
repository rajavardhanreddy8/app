"""
Phase 7 Track B — Specialist Yield Predictor

Trains 5 reaction-family-specific XGBoost models and routes predictions
to the appropriate specialist, falling back to the global model when the
family has too few training samples.

Families
--------
coupling        → Suzuki, Buchwald-Hartwig, Heck, Negishi, Stille, ...
condensation    → Esterification, amide coupling, amidation, ...
reduction       → Reduction, hydrogenation, reductive amination, ...
c_c_formation   → Grignard, Wittig, Aldol, Diels-Alder, Knoevenagel, ...
other           → SN2, oxidation, deprotection, unknowns
"""

import asyncio
import logging
import pickle
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Any

import numpy as np
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
import xgboost as xgb

from services.yield_predictor import YieldPredictor

logger = logging.getLogger(__name__)

# ── Reaction family definitions ───────────────────────────────────────────────

REACTION_FAMILIES: Dict[str, List[str]] = {
    "coupling": [
        "suzuki", "buchwald_hartwig", "heck", "negishi",
        "stille", "cross_coupling", "kumada", "miyaura",
    ],
    "condensation": [
        "esterification", "amide_coupling", "amidation",
        "transesterification", "peptide_coupling",
    ],
    "reduction": [
        "reduction", "hydrogenation", "reductive_amination",
        "hydrogenolysis", "transfer_hydrogenation",
    ],
    "c_c_formation": [
        "grignard", "wittig", "aldol", "diels_alder", "diels-alder",
        "knoevenagel", "reformatsky", "friedel_crafts", "friedel-crafts",
        "mannich", "organolithium",
    ],
    "other": [],  # catches everything else
}


def classify_reaction_family(reaction_type: str) -> str:
    """Map a reaction type string → one of the 5 family keys."""
    rt = reaction_type.lower()
    for family, keywords in REACTION_FAMILIES.items():
        if family == "other":
            continue
        if any(kw in rt for kw in keywords):
            return family
    return "other"


# ── Specialist model ──────────────────────────────────────────────────────────

class SpecialistYieldPredictor:
    """
    Ensemble of 5 family-specialist XGBoost regressors + a global fallback.

    Usage
    -----
    svp = SpecialistYieldPredictor()
    metrics = svp.train_all(reactions)       # train
    svp.save()                               # persist
    ...
    svp.load()
    result = svp.predict_with_uncertainty(rxn)
    """

    DEFAULT_PKL = "backend/models/specialist_models.pkl"
    MIN_SAMPLES = 50  # minimum per family to train a specialist

    def __init__(self):
        # family → trained xgb.XGBRegressor
        self.specialists: Dict[str, xgb.XGBRegressor] = {}
        # family → training sample count
        self.specialist_sample_counts: Dict[str, int] = {}
        # global YieldPredictor used as fallback
        self.global_model: Optional[YieldPredictor] = None
        # The shared featurizer (reuses YieldPredictor logic)
        self._featurizer = YieldPredictor()

    @property
    def model(self):
        """Bridge property for compatibility with code expecting a single booster."""
        if self.specialists:
            return next(iter(self.specialists.values()))
        if self.global_model:
            return self.global_model.model
        return None

    def load_model(self, path: str = DEFAULT_PKL) -> bool:
        """Alias for load() to match the YieldPredictor interface."""
        return self.load(path)

    # ── Training ──────────────────────────────────────────────────────────────

    def _train_specialist(
        self,
        family: str,
        reactions: List[Dict],
        test_size: float = 0.2,
        random_state: int = 42,
    ) -> Dict[str, Any]:
        """Train one XGBoost specialist for `family`. Returns metric dict."""
        X_list, y_list = [], []
        for rxn in reactions:
            feat = self._featurizer.featurize_reaction(rxn)
            if feat is not None:
                X_list.append(feat)
                y_list.append(rxn.get("yield_percent", 0.0))

        if len(X_list) < self.MIN_SAMPLES:
            logger.warning(f"[{family}] Only {len(X_list)} featurizable reactions — skipping")
            return {}

        X = np.array(X_list)
        y = np.array(y_list)

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_state
        )

        model = xgb.XGBRegressor(
            n_estimators=400,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            min_child_weight=3,
            gamma=0.1,
            random_state=random_state,
            objective="reg:squarederror",
        )
        model.fit(
            X_train, y_train,
            eval_set=[(X_test, y_test)],
            verbose=False,
        )

        train_mae = mean_absolute_error(y_train, model.predict(X_train))
        test_mae  = mean_absolute_error(y_test,  model.predict(X_test))
        train_r2  = r2_score(y_train, model.predict(X_train))
        test_r2   = r2_score(y_test,  model.predict(X_test))

        self.specialists[family] = model
        self.specialist_sample_counts[family] = len(X_list)

        return {
            "n_samples": len(X_list),
            "train_mae": round(train_mae, 3),
            "test_mae":  round(test_mae,  3),
            "train_r2":  round(train_r2,  3),
            "test_r2":   round(test_r2,   3),
        }

    def train_all(
        self,
        data: List[Dict],
        random_state: int = 42,
    ) -> Dict[str, Any]:
        """
        Partition `data` into reaction families, train one specialist per
        family that has enough samples, then train the global fallback.
        """
        # Partition by family
        buckets: Dict[str, List[Dict]] = defaultdict(list)
        for rxn in data:
            family = classify_reaction_family(rxn.get("reaction_type", ""))
            buckets[family].append(rxn)

        all_metrics: Dict[str, Any] = {}

        for family in REACTION_FAMILIES:
            reactions = buckets[family]
            n = len(reactions)
            if n < self.MIN_SAMPLES:
                logger.info(f"[{family}] {n} samples < {self.MIN_SAMPLES} — skipping specialist")
                all_metrics[family] = {"n_samples": n, "skipped": True}
                continue

            logger.info(f"[{family}] Training specialist on {n} reactions ...")
            m = self._train_specialist(family, reactions, random_state=random_state)
            all_metrics[family] = m
            logger.info(
                f"[{family}] test_mae={m.get('test_mae','?')}%  test_r2={m.get('test_r2','?')}"
            )

        # Global fallback (async train bridged via asyncio.run)
        logger.info("[global] Training global fallback ...")
        self.global_model = YieldPredictor()
        global_metrics = asyncio.run(
            self.global_model.train(data=data, random_state=random_state)
        )
        all_metrics["global_fallback"] = {
            "n_samples":  global_metrics.get("n_samples", len(data)),
            "train_mae":  round(global_metrics.get("train_mae", 0), 3),
            "test_mae":   round(global_metrics.get("test_mae",  0), 3),
            "train_r2":   round(global_metrics.get("train_r2",  0), 3),
            "test_r2":    round(global_metrics.get("test_r2",   0), 3),
        }

        return all_metrics

    # ── Prediction ────────────────────────────────────────────────────────────

    def _predict_with_specialist(
        self,
        model: xgb.XGBRegressor,
        reaction: Dict,
    ) -> Optional[float]:
        feat = self._featurizer.featurize_reaction(reaction)
        if feat is None:
            return None
        raw = model.predict(feat.reshape(1, -1))[0]
        return float(max(0.0, min(100.0, raw)))

    def predict(self, reaction: Dict) -> Optional[float]:
        """Point estimate — uses specialist if available, else global fallback."""
        family = classify_reaction_family(reaction.get("reaction_type", ""))

        if family in self.specialists:
            return self._predict_with_specialist(self.specialists[family], reaction)

        if self.global_model:
            return self.global_model.predict(reaction)

        return None

    def predict_with_uncertainty(self, reaction: Dict) -> Dict[str, Any]:
        """
        Predict yield and attach calibrated uncertainty intervals.

        Uncertainty width is determined by how many samples the specialist
        was trained on — well-trained specialists get tighter intervals.
        """
        family = classify_reaction_family(reaction.get("reaction_type", ""))
        point_estimate = self.predict(reaction)

        if point_estimate is None:
            return {
                "yield_percent": 75.0,
                "lower_bound": 50.0,
                "upper_bound": 95.0,
                "confidence_interval": 45.0,
                "confidence_level": "low",
                "model": "fallback_default",
                "family": family,
                "n_training_samples": 0,
            }

        n_samples = self.specialist_sample_counts.get(family, 0)

        # Calibrated uncertainty based on sample count
        if n_samples > 1000:
            uncertainty = 8.0    # tight — well-trained specialist
        elif n_samples > 200:
            uncertainty = 12.0   # moderate
        elif n_samples > self.MIN_SAMPLES:
            uncertainty = 16.0   # sparse specialist
        else:
            uncertainty = 20.0   # global fallback

        lower = max(0.0, point_estimate - uncertainty)
        upper = min(100.0, point_estimate + uncertainty)

        if uncertainty <= 10:
            confidence_level = "high"
        elif uncertainty <= 15:
            confidence_level = "medium"
        else:
            confidence_level = "low"

        model_label = (
            f"specialist_{family}" if family in self.specialists else "global_fallback"
        )

        return {
            "yield_percent":      round(point_estimate, 1),
            "lower_bound":        round(lower, 1),
            "upper_bound":        round(upper, 1),
            "confidence_interval": round(upper - lower, 1),
            "confidence_level":   confidence_level,
            "model":              model_label,
            "family":             family,
            "n_training_samples": n_samples,
        }

    # ── Persistence ───────────────────────────────────────────────────────────

    def save(self, path: str = DEFAULT_PKL) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "specialists":             self.specialists,
            "specialist_sample_counts": self.specialist_sample_counts,
            "global_model":            self.global_model,
        }
        with open(p, "wb") as f:
            pickle.dump(payload, f)
        logger.info(f"Specialist models saved → {p}")

    def load(self, path: str = DEFAULT_PKL) -> bool:
        p = Path(path)
        if not p.exists():
            logger.warning(f"Specialist model file not found: {p}")
            return False
        try:
            with open(p, "rb") as f:
                payload = pickle.load(f)
            self.specialists             = payload.get("specialists", {})
            self.specialist_sample_counts = payload.get("specialist_sample_counts", {})
            self.global_model            = payload.get("global_model")
            # Re-init featurizer (not serialized)
            self._featurizer = YieldPredictor()
            logger.info(
                f"Loaded {len(self.specialists)} specialist(s) from {p}: "
                f"{list(self.specialists.keys())}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to load specialist models: {e}")
            return False
