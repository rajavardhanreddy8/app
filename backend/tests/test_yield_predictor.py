"""
Phase 3 tests \u2014 trained yield model and inference.
Requires: numpy, sklearn, xgboost, rdkit
"""
import sys, os, types, json, pytest
from pathlib import Path

pytest.importorskip("numpy")
pytest.importorskip("sklearn")
pytest.importorskip("xgboost")
pytest.importorskip("rdkit")

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

from services.yield_predictor import YieldPredictor

MODEL_PATH = Path("backend/models/yield_model.pkl")
TRAINING_DATA_PATH = Path("backend/data/training_reactions.json")
TRAIN_SCRIPT = Path("backend/scripts/train_yield_model.py")


# \u2500\u2500 Training script exists \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

class TestTrainingScript:

    def test_train_script_exists(self):
        assert TRAIN_SCRIPT.exists(), \
            f"backend/scripts/train_yield_model.py not found"

    def test_train_script_imports_yield_predictor(self):
        src = TRAIN_SCRIPT.read_text()
        assert "YieldPredictor" in src or "yield_predictor" in src

    def test_train_script_calls_train(self):
        src = TRAIN_SCRIPT.read_text()
        assert ".train(" in src or "train()" in src

    def test_train_script_saves_model(self):
        src = TRAIN_SCRIPT.read_text()
        assert "yield_model" in src or "save_model" in src or "pkl" in src


# \u2500\u2500 Training data exists \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

class TestTrainingDataExists:

    def test_training_json_exists(self):
        assert TRAINING_DATA_PATH.exists(), \
            "backend/data/training_reactions.json not found \u2014 run generate_training_data.py"

    def test_training_json_has_enough_reactions(self):
        with open(TRAINING_DATA_PATH) as f:
            data = json.load(f)
        assert len(data) >= 500, \
            f"Only {len(data)} reactions \u2014 need \u2265500 for meaningful training"

    def test_training_reactions_have_yield_field(self):
        with open(TRAINING_DATA_PATH) as f:
            data = json.load(f)
        missing = [i for i, r in enumerate(data[:20]) if "yield_percent" not in r]
        assert not missing, f"Reactions at indices {missing} missing yield_percent"


# \u2500\u2500 Model file exists and loads \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

class TestModelLoads:

    def test_model_file_exists(self):
        assert MODEL_PATH.exists(), \
            "backend/models/yield_model.pkl not found \u2014 run train_yield_model.py"

    def test_model_loads_without_error(self):
        p = YieldPredictor()
        result = p.load_model()
        assert result is True, "YieldPredictor.load_model() returned False"

    def test_model_is_not_none_after_load(self):
        p = YieldPredictor()
        p.load_model()
        assert p.model is not None


# \u2500\u2500 Inference correctness \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

class TestInference:

    @pytest.fixture(scope="class")
    def predictor(self):
        p = YieldPredictor()
        loaded = p.load_model()
        if not loaded:
            pytest.skip("Model not loaded \u2014 run train_yield_model.py first")
        return p

    def test_predict_returns_float(self, predictor):
        rxn = {
            "reactants": ["CCO", "CC(=O)O"],
            "products": ["CCOC(C)=O"],
            "reaction_type": "esterification",
            "temperature_celsius": 80.0,
            "catalyst": "H2SO4",
            "solvent": "toluene",
        }
        result = predictor.predict(rxn)
        assert isinstance(result, float)

    def test_esterification_yield_in_range(self, predictor):
        pred = predictor.predict({
            "reactants": ["CCO", "CC(=O)O"],
            "products": ["CCOC(C)=O"],
            "reaction_type": "esterification",
            "temperature_celsius": 80.0,
            "catalyst": "H2SO4",
            "solvent": "toluene",
        })
        assert 50.0 <= pred <= 100.0, \
            f"Esterification prediction {pred:.1f}% out of range 50-100%"

    def test_suzuki_yield_in_range(self, predictor):
        pred = predictor.predict({
            "reactants": ["Brc1ccccc1", "OB(O)c1ccccc1"],
            "products": ["c1ccc(-c2ccccc2)cc1"],
            "reaction_type": "suzuki",
            "temperature_celsius": 90.0,
            "catalyst": "Pd(PPh3)4",
            "solvent": "THF",
        })
        assert 50.0 <= pred <= 100.0, \
            f"Suzuki prediction {pred:.1f}% out of range 50-100%"

    def test_predict_clips_to_0_100(self, predictor):
        # Degenerate input should not produce negative or >100 values
        rxn = {
            "reactants": ["C"],
            "products": ["CC"],
            "reaction_type": "unknown",
            "temperature_celsius": 999.0,
            "catalyst": None,
            "solvent": None,
        }
        result = predictor.predict(rxn)
        assert 0.0 <= result <= 100.0

    def test_different_reactions_give_different_predictions(self, predictor):
        r1 = predictor.predict({
            "reactants": ["CCO", "CC(=O)O"], "products": ["CCOC(C)=O"],
            "reaction_type": "esterification", "temperature_celsius": 80.0,
        })
        r2 = predictor.predict({
            "reactants": ["Brc1ccccc1", "OB(O)c1ccccc1"],
            "products": ["c1ccc(-c2ccccc2)cc1"],
            "reaction_type": "suzuki", "temperature_celsius": 90.0,
        })
        assert r1 != r2, "Different reactions should give different yield predictions"

    def test_invalid_smiles_does_not_crash(self, predictor):
        try:
            result = predictor.predict({
                "reactants": ["INVALID_SMILES"],
                "products": ["ALSO_INVALID"],
                "reaction_type": "esterification",
            })
            assert result is None or isinstance(result, float)
        except Exception as e:
            pytest.fail(f"predict() raised on invalid SMILES: {e}")


# \u2500\u2500 models/__init__.py singleton \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

class TestModelsSingleton:

    def test_models_init_has_get_yield_predictor(self):
        init_path = Path("backend/models/__init__.py")
        assert init_path.exists()
        src = init_path.read_text()
        assert "get_yield_predictor" in src, \
            "models/__init__.py missing get_yield_predictor() singleton"

    def test_singleton_returns_same_instance(self):
        from models import get_yield_predictor
        p1 = get_yield_predictor()
        p2 = get_yield_predictor()
        assert p1 is p2, "get_yield_predictor() must return same instance"

    def test_singleton_has_model_loaded(self):
        from models import get_yield_predictor
        p = get_yield_predictor()
        if MODEL_PATH.exists():
            assert p.model is not None, \
                "Singleton should have model loaded if pkl file exists"
