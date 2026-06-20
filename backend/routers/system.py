"""System readiness and model provenance endpoints."""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends

from dependencies import deps, verify_api_key

router = APIRouter(prefix="/api", tags=["system"], dependencies=[Depends(verify_api_key)])

BACKEND_DIR = Path(__file__).resolve().parents[1]
MODELS_DIR = BACKEND_DIR / "models"


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": f"Could not read {path.name}: {exc}"}


def _artifact_status(path: Path) -> Dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else 0,
    }


def _collect_model_status() -> Dict[str, Any]:
    try:
        if deps.yield_predictor is None:
            from models import get_yield_predictor

            deps.yield_predictor = get_yield_predictor()
    except Exception as exc:
        yield_load_error = str(exc)
    else:
        yield_load_error = None

    yield_artifacts = {
        "specialist_models": _artifact_status(MODELS_DIR / "specialist_models.pkl"),
        "global_model": _artifact_status(MODELS_DIR / "yield_model.pkl"),
        "multi_model": _artifact_status(MODELS_DIR / "yield_model_multi.pkl"),
        "quantile_model": _artifact_status(MODELS_DIR / "yield_model_quantile.pkl"),
    }
    condition_artifacts = {
        "condition_models": _artifact_status(MODELS_DIR / "condition_models.pkl"),
    }

    yield_predictor = deps.yield_predictor
    yield_predictor_type = type(yield_predictor).__name__ if yield_predictor else None
    if yield_predictor_type == "SpecialistYieldPredictor":
        yield_fallback_state = "specialist_ensemble"
    elif yield_artifacts["global_model"]["exists"] or yield_artifacts["multi_model"]["exists"]:
        yield_fallback_state = "global_model"
    else:
        yield_fallback_state = "heuristic_fallback"

    condition_loaded = bool(getattr(deps.condition_predictor, "models_loaded", False))
    condition_fallback_state = "ml_model" if condition_loaded else "rules_or_prior_fallback"

    return {
        "yield_predictor": {
            "loaded_type": yield_predictor_type,
            "fallback_state": yield_fallback_state,
            "load_error": yield_load_error,
            "artifacts": yield_artifacts,
            "metrics": {
                "global": _read_json(MODELS_DIR / "yield_model_metadata.json")
                or _read_json(MODELS_DIR / "yield_model_metrics.json"),
                "specialist": _read_json(MODELS_DIR / "specialist_model_metrics.json"),
            },
        },
        "condition_predictor": {
            "loaded": condition_loaded,
            "fallback_state": condition_fallback_state,
            "artifacts": condition_artifacts,
            "metrics": _read_json(MODELS_DIR / "condition_model_metrics.json"),
        },
    }


def _llm_status() -> Dict[str, Any]:
    status = getattr(deps, "llm_status", None)
    if status:
        return status
    try:
        from services.claude_service import ClaudeService

        return ClaudeService().status_snapshot()
    except Exception as exc:
        return {"health": "unavailable", "error": str(exc)}


@router.get("/models/status")
async def model_status():
    """Return loaded model type, artifact status, metrics, and fallback state."""
    return {"status": "success", "models": _collect_model_status()}


@router.get("/system/readiness")
async def system_readiness():
    """Return operational readiness and research-mode blockers."""
    models = _collect_model_status()
    llm = _llm_status()
    auth_mode = "api_key" if os.getenv("API_KEY") else "dev_mode"

    blockers = []
    warnings = []
    if deps.db_mode != "mongodb":
        blockers.append("MongoDB is unavailable; persistence, history, and learning use mock storage.")
    if models["yield_predictor"]["fallback_state"] == "heuristic_fallback":
        blockers.append("Yield predictor is in heuristic fallback; trained yield artifacts are missing or unavailable.")
    if models["condition_predictor"]["fallback_state"] != "ml_model":
        warnings.append("Condition predictor is using rules/prior fallback instead of trained models.")
    if auth_mode == "dev_mode":
        warnings.append("API_KEY is not configured; backend is running in open development mode.")
    if llm.get("health") in {"demo", "unavailable"}:
        warnings.append("LLM planner is not live; planning may use demo or fallback behavior.")
    if os.getenv("DEMO_MODE", "false").lower() in {"1", "true", "yes", "on"}:
        warnings.append("DEMO_MODE is enabled; routes may be hardcoded examples or generic fallbacks.")

    return {
        "status": "success",
        "research_grade_ready": not blockers,
        "auth": {"mode": auth_mode},
        "database": {
            "mode": deps.db_mode,
            "connected": deps.db_mode == "mongodb",
            "error": deps.db_error,
        },
        "llm": llm,
        "models": models,
        "blockers": blockers,
        "warnings": warnings,
    }
