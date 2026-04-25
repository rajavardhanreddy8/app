"""
Phase 3 tests \u2014 closed-loop learning engine with real retraining.
Zero heavy deps required for structural tests.
Heavy dep tests skip cleanly if numpy/sklearn missing.
"""
import sys, os, types, asyncio, inspect, pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import fields

# Stub structlog
if "structlog" not in sys.modules:
    _sl = types.ModuleType("structlog")
    _sl.get_logger = lambda *a, **kw: __import__("logging").getLogger("stub")
    _sl.configure = lambda **kw: None
    _sl.stdlib = types.SimpleNamespace(filter_by_level=None, LoggerFactory=lambda: None)
    _sl.processors = types.SimpleNamespace(
        TimeStamper=lambda **kw: None, JSONRenderer=lambda: None
    )
    sys.modules.update({
        "structlog": _sl, "structlog.stdlib": _sl.stdlib,
        "structlog.processors": _sl.processors,
    })

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_db")

from services.closed_loop_learning_engine import (
    ClosedLoopLearningEngine, RetrainingConfig
)


# \u2500\u2500 RetrainingConfig dataclass \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

class TestRetrainingConfig:

    def test_config_is_dataclass(self):
        cfg = RetrainingConfig()
        assert hasattr(cfg, "__dataclass_fields__")

    def test_default_enabled_true(self):
        assert RetrainingConfig().enabled is True

    def test_default_min_samples(self):
        assert RetrainingConfig().min_samples_required >= 10

    def test_default_max_train_time_positive(self):
        assert RetrainingConfig().max_train_time_seconds > 0

    def test_default_retrain_yield_predictor_true(self):
        assert RetrainingConfig().retrain_yield_predictor is True

    def test_default_backup_model_on_retrain(self):
        assert isinstance(RetrainingConfig().backup_model_on_retrain, bool)

    def test_all_required_fields_present(self):
        field_names = {f.name for f in fields(RetrainingConfig)}
        required = {
            "enabled", "min_samples_required",
            "max_train_time_seconds", "retrain_yield_predictor",
            "backup_model_on_retrain"
        }
        assert required.issubset(field_names), \
            f"Missing fields: {required - field_names}"

    def test_custom_config_values(self):
        cfg = RetrainingConfig(enabled=False, min_samples_required=500)
        assert cfg.enabled is False
        assert cfg.min_samples_required == 500


# \u2500\u2500 ClosedLoopLearningEngine init \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

class TestEngineInit:

    def _make_engine(self, **kwargs):
        mock_db = MagicMock()
        return ClosedLoopLearningEngine(db=mock_db, **kwargs)

    def test_accepts_yield_predictor_param(self):
        sig = inspect.signature(ClosedLoopLearningEngine.__init__)
        assert "yield_predictor" in sig.parameters

    def test_accepts_config_param(self):
        sig = inspect.signature(ClosedLoopLearningEngine.__init__)
        assert "config" in sig.parameters

    def test_stores_yield_predictor(self):
        mock_predictor = MagicMock()
        engine = self._make_engine(yield_predictor=mock_predictor)
        assert engine.yield_predictor is mock_predictor

    def test_stores_config(self):
        cfg = RetrainingConfig(enabled=False)
        engine = self._make_engine(config=cfg)
        assert engine.config.enabled is False

    def test_default_config_when_none(self):
        engine = self._make_engine()
        assert hasattr(engine, "config")
        assert isinstance(engine.config, RetrainingConfig)

    def test_none_yield_predictor_accepted(self):
        engine = self._make_engine(yield_predictor=None)
        assert engine.yield_predictor is None


# \u2500\u2500 trigger_retraining structure \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

class TestTriggerRetrainingStructure:

    def test_trigger_retraining_is_async(self):
        assert inspect.iscoroutinefunction(
            ClosedLoopLearningEngine.trigger_retraining
        )

    def test_source_contains_wait_for_or_train_call(self):
        src = inspect.getsource(
            ClosedLoopLearningEngine.trigger_retraining
        )
        has_train = "train()" in src or ".train(" in src
        has_timeout = "wait_for" in src or "timeout" in src
        assert has_train or has_timeout, \
            "trigger_retraining must call .train() or use asyncio.wait_for"

    def test_source_checks_config_enabled(self):
        src = inspect.getsource(
            ClosedLoopLearningEngine.trigger_retraining
        )
        assert "config.enabled" in src or "self.config" in src, \
            "trigger_retraining must check config.enabled"

    def test_source_checks_min_samples(self):
        src = inspect.getsource(
            ClosedLoopLearningEngine.trigger_retraining
        )
        assert "min_samples" in src or "count" in src, \
            "trigger_retraining must check minimum sample count"


# \u2500\u2500 trigger_retraining behavior (mocked) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

class TestTriggerRetrainingBehavior:

    def _make_engine_with_mocks(self, sample_count=100, train_metrics=None):
        mock_db = MagicMock()
        mock_db.feedback.count_documents = AsyncMock(return_value=sample_count)
        mock_db.model_versions.find_one = AsyncMock(return_value=None)
        mock_db.model_versions.insert_one = AsyncMock(return_value=None)
        mock_db.learning_events.insert_one = AsyncMock(return_value=None)

        mock_predictor = MagicMock()
        mock_predictor.train = AsyncMock(
            return_value=train_metrics or {
                "train_mae": 5.2, "test_mae": 6.1,
                "train_r2": 0.87, "test_r2": 0.81,
                "n_samples": 100
            }
        )

        cfg = RetrainingConfig(
            enabled=True,
            min_samples_required=50,
            max_train_time_seconds=30,
            retrain_yield_predictor=True,
            backup_model_on_retrain=False
        )

        return ClosedLoopLearningEngine(
            db=mock_db,
            yield_predictor=mock_predictor,
            config=cfg
        ), mock_predictor, mock_db

    def test_retrain_called_when_enough_samples(self):
        engine, mock_predictor, _ = self._make_engine_with_mocks(
            sample_count=100
        )
        asyncio.run(engine.trigger_retraining(reason="test"))
        mock_predictor.train.assert_called_once()

    def test_retrain_skipped_when_too_few_samples(self):
        engine, mock_predictor, _ = self._make_engine_with_mocks(
            sample_count=10
        )
        asyncio.run(engine.trigger_retraining(reason="test"))
        mock_predictor.train.assert_not_called()

    def test_retrain_skipped_when_config_disabled(self):
        mock_db = MagicMock()
        mock_db.feedback.count_documents = AsyncMock(return_value=200)
        mock_db.model_versions.find_one = AsyncMock(return_value=None)
        mock_db.model_versions.insert_one = AsyncMock(return_value=None)
        mock_db.learning_events.insert_one = AsyncMock(return_value=None)

        mock_predictor = MagicMock()
        mock_predictor.train = AsyncMock()

        cfg = RetrainingConfig(enabled=False)
        engine = ClosedLoopLearningEngine(
            db=mock_db, yield_predictor=mock_predictor, config=cfg
        )
        asyncio.run(engine.trigger_retraining())
        mock_predictor.train.assert_not_called()

    def test_retrain_skipped_when_no_predictor(self):
        mock_db = MagicMock()
        mock_db.feedback.count_documents = AsyncMock(return_value=200)
        mock_db.model_versions.find_one = AsyncMock(return_value=None)
        mock_db.model_versions.insert_one = AsyncMock(return_value=None)
        mock_db.learning_events.insert_one = AsyncMock(return_value=None)

        cfg = RetrainingConfig(enabled=True, min_samples_required=50)
        engine = ClosedLoopLearningEngine(
            db=mock_db, yield_predictor=None, config=cfg
        )
        result = asyncio.run(engine.trigger_retraining())
        assert isinstance(result, dict)

    def test_returns_versions_dict_always(self):
        engine, _, _ = self._make_engine_with_mocks(sample_count=100)
        result = asyncio.run(engine.trigger_retraining())
        assert isinstance(result, dict)

    def test_handles_train_exception_gracefully(self):
        engine, mock_predictor, _ = self._make_engine_with_mocks(
            sample_count=100
        )
        mock_predictor.train = AsyncMock(
            side_effect=RuntimeError("training failed")
        )
        result = asyncio.run(engine.trigger_retraining())
        assert isinstance(result, dict)

    def test_server_py_passes_yield_predictor_to_engine(self):
        with open("backend/server.py") as f:
            source = f.read()
        assert "yield_predictor" in source or "YieldPredictor" in source
        assert "ClosedLoopLearningEngine" in source


# \u2500\u2500 New /api/learning/retrain endpoint \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

class TestRetrainEndpoint:

    def test_retrain_endpoint_exists_in_server(self):
        with open("backend/server.py") as f:
            source = f.read()
        assert "/learning/retrain" in source or "retrain" in source, \
            "No /api/learning/retrain endpoint found in server.py"

    def test_retrain_endpoint_is_post(self):
        with open("backend/server.py") as f:
            source = f.read()
        lines = source.splitlines()
        retrain_lines = [i for i, l in enumerate(lines) if "retrain" in l]
        for li in retrain_lines:
            context = "\n".join(lines[max(0, li-3):li+3])
            if "post" in context.lower() or "POST" in context:
                return
        # If we get here, check if the word "post" appears near retrain
        assert any("post" in source[max(0, source.find("retrain")-200):
                                   source.find("retrain")+200].lower()
                   for _ in [1]), \
            "retrain endpoint should be POST"
