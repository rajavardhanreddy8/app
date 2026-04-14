import os
from pathlib import Path

_yield_predictor = None

def get_yield_predictor():
    """Get the global YieldPredictor instance."""
    global _yield_predictor
    if _yield_predictor is None:
        # Lazy import to avoid circular dependencies
        from services.yield_predictor import YieldPredictor
        
        # Determine model path
        model_path = os.getenv("YIELD_MODEL_PATH", "backend/models/yield_model.pkl")
        _yield_predictor = YieldPredictor(model_path=model_path)
        # Attempt to load model if it exists
        if Path(model_path).exists():
            _yield_predictor.load_model()
    return _yield_predictor
