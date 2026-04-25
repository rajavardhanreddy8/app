"""
models/__init__.py — singleton accessor for the yield predictor.

Priority order
--------------
1. SpecialistYieldPredictor (specialist_models.pkl exists)
2. YieldPredictor global fallback (yield_model.pkl exists)
3. Untrained YieldPredictor instance (model loaded on-demand)
"""

import os
from pathlib import Path

_yield_predictor = None


def get_yield_predictor():
    """
    Return the best available yield predictor singleton.

    Prefers the specialist ensemble if its model file is present;
    otherwise falls back to the global YieldPredictor.
    """
    global _yield_predictor
    if _yield_predictor is not None:
        return _yield_predictor

    specialist_path = os.getenv(
        "SPECIALIST_MODEL_PATH", "backend/models/specialist_models.pkl"
    )
    global_path = os.getenv(
        "YIELD_MODEL_PATH", "backend/models/yield_model.pkl"
    )

    # Try specialist ensemble first
    if Path(specialist_path).exists():
        try:
            from services.specialist_yield_predictor import SpecialistYieldPredictor
            svp = SpecialistYieldPredictor()
            if svp.load(specialist_path):
                _yield_predictor = svp
                return _yield_predictor
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"Specialist model load failed ({e}), falling back to global model"
            )

    # Fall back to single global model
    from services.yield_predictor import YieldPredictor
    yp = YieldPredictor(model_path=global_path)
    if Path(global_path).exists():
        yp.load_model()
    _yield_predictor = yp
    return _yield_predictor


def reset_yield_predictor():
    """Force singleton re-initialisation (useful in tests)."""
    global _yield_predictor
    _yield_predictor = None
