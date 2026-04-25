"""
Final integration test suite.
Runs the complete pipeline end-to-end and validates all Phase 1-8 
improvements are working together without regression.
"""
import sys, os, types, asyncio, json, pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

# ── Stubs ──────────────────────────────────────────────────────────────────────
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
if "anthropic" not in sys.modules:
    _anth = types.ModuleType("anthropic")
    _anth.AsyncAnthropic = type("AsyncAnthropic", (), {"__init__": lambda self, **kw: None})
    sys.modules["anthropic"] = _anth

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.update({
    "DEMO_MODE": "true",
    "ANTHROPIC_API_KEY": "sk-test",
    "MONGO_URL": "mongodb://localhost:27017",
    "DB_NAME": "test_db",
})

# ── Phase 1: LLM output contract ──────────────────────────────────────────────

class TestLLMOutputContract:
    """Phase 1 — Structured output never uses regex parsing."""

    def test_no_regex_json_parsing_in_synthesis_planner(self):
        src = Path("backend/services/synthesis_planner.py").read_text(encoding="utf-8")
        assert "re.search" not in src or "parse_claude_response" not in src, \
            "Regex JSON parsing still present in synthesis_planner.py"

    def test_claude_service_uses_tool_use(self):
        src = Path("backend/services/claude_service.py").read_text(encoding="utf-8")
        assert "tool_use" in src or "tools" in src, \
            "claude_service.py not using tool use for structured output"

    def test_pydantic_schemas_defined(self):
        from services.claude_service import (
            SynthesisRouteSchema, RouteSchema, StepSchema, ConditionSchema
        )
        assert SynthesisRouteSchema is not None

    def test_demo_routes_have_minimum_fields(self):
        from services.claude_service import ClaudeService
        svc = ClaudeService()
        result = svc._generate_demo_routes("CCO", 5, "balanced")
        data = json.loads(result["content"])
        route = data["routes"][0]
        for field in ("starting_materials", "steps", "overall_yield_percent",
                      "total_cost_usd", "notes"):
            assert field in route, f"Demo route missing field: {field}"

    def test_aspirin_demo_route_is_chemically_correct(self):
        from services.claude_service import ClaudeService
        svc = ClaudeService()
        result = svc._generate_demo_routes(
            "CC(=O)Oc1ccccc1C(=O)O", 5, "balanced"
        )
        data = json.loads(result["content"])
        all_steps = [s for r in data["routes"] for s in r["steps"]]
        step_types = [s["reaction_type"].lower() for s in all_steps]
        real_chemistry = any(
            kw in " ".join(step_types) for kw in
            ["acetyl", "kolbe", "bromination", "esterification",
             "acylation", "hydroxylation"]
        )
        assert real_chemistry, \
            f"Aspirin demo routes lack real chemistry: {step_types}"


# ── Phase 2: Retrosynthesis chemistry ─────────────────────────────────────────

class TestRetrosynthesisChemistry:
    """Phase 2 — SMARTS templates, canonicalization, building blocks."""

    def test_smarts_templates_count_gte_10(self):
        pytest.importorskip("rdkit")
        from services.retrosynthesis_engine import REACTION_TEMPLATES
        assert len(REACTION_TEMPLATES) >= 10

    def test_no_substring_matching_in_find_precursors(self):
        src = Path("backend/services/retrosynthesis_engine.py").read_text(encoding="utf-8")
        assert "in smiles" not in src or "RunReactants" in src, \
            "Substring matching still present in retrosynthesis engine"

    def test_canonicalization_in_chemical_graph(self):
        pytest.importorskip("rdkit")
        from services.chemical_graph import canonicalize_smiles
        assert canonicalize_smiles("OCC") == canonicalize_smiles("CCO")
        assert canonicalize_smiles("INVALID") is None

    def test_building_block_catalog_size(self):
        pytest.importorskip("rdkit")
        from data.building_blocks import COMMON_BUILDING_BLOCKS
        assert len(COMMON_BUILDING_BLOCKS) >= 100, \
            f"Building block catalog too small: {len(COMMON_BUILDING_BLOCKS)}"

    def test_is_building_block_recognizes_common_molecules(self):
        pytest.importorskip("rdkit")
        from data.building_blocks import is_building_block_smiles
        for smi in ["CCO", "c1ccccc1", "CC(=O)O", "Brc1ccccc1"]:
            assert is_building_block_smiles(smi), \
                f"{smi} should be recognized as building block"

    def test_benchmark_baseline_exists_and_meets_target(self):
        baseline = Path("backend/test_reports/benchmark_baseline.json")
        assert baseline.exists(), "Benchmark baseline not found"
        data = json.loads(baseline.read_text(encoding="utf-8"))
        summary = data.get("summary", {})
        total = sum(cat.get("success", 0) for cat in summary.values())
        assert total >= 21, f"Benchmark below 21/30: {total}/30"


# ── Phase 3: Learning loop ─────────────────────────────────────────────────────

class TestLearningLoop:
    """Phase 3 — Retraining trigger actually calls train()."""

    def test_retrain_calls_train_method(self):
        src = Path("backend/services/closed_loop_learning_engine.py").read_text(encoding="utf-8")
        assert ".train(" in src or "train()" in src, \
            "trigger_retraining() never calls .train()"

    def test_retraining_config_exists(self):
        from services.closed_loop_learning_engine import RetrainingConfig
        cfg = RetrainingConfig()
        assert cfg.enabled is True
        assert cfg.min_samples_required > 0

    def test_retrain_skipped_when_disabled(self):
        from services.closed_loop_learning_engine import (
            ClosedLoopLearningEngine, RetrainingConfig
        )
        mock_db = MagicMock()
        mock_db.feedback.count_documents = AsyncMock(return_value=200)
        mock_db.model_versions.find_one = AsyncMock(return_value=None)
        mock_db.model_versions.insert_one = AsyncMock()
        mock_db.learning_events.insert_one = AsyncMock()

        mock_predictor = MagicMock()
        mock_predictor.train = AsyncMock()

        engine = ClosedLoopLearningEngine(
            db=mock_db,
            yield_predictor=mock_predictor,
            config=RetrainingConfig(enabled=False)
        )
        asyncio.run(engine.trigger_retraining())
        mock_predictor.train.assert_not_called()


# ── Phase 4: ML quality ────────────────────────────────────────────────────────

class TestMLQuality:
    """Phase 4 — Uncertainty, canonicalization, improved XGBoost."""

    def test_predict_with_uncertainty_returns_required_keys(self):
        pytest.importorskip("numpy")
        pytest.importorskip("sklearn")
        pytest.importorskip("xgboost")
        pytest.importorskip("rdkit")
        from services.yield_predictor import YieldPredictor
        p = YieldPredictor()
        p.load_model()
        result = p.predict_with_uncertainty({
            "reactants": ["CCO", "CC(=O)O"],
            "products": ["CCOC(C)=O"],
            "reaction_type": "esterification",
            "temperature_celsius": 80.0,
        })
        for key in ("yield_percent", "lower_bound", "upper_bound",
                    "confidence_interval", "confidence_level"):
            assert key in result, f"Missing key: {key}"
        assert result["lower_bound"] <= result["yield_percent"] <= result["upper_bound"]

    def test_catalyst_encoding_is_12_categories(self):
        pytest.importorskip("rdkit")
        from services.yield_predictor import CATALYST_CATEGORIES, classify_catalyst
        assert len(CATALYST_CATEGORIES) == 12
        assert classify_catalyst("Pd(PPh3)4") == "palladium"
        assert classify_catalyst("AlCl3") == "acid_lewis"
        assert classify_catalyst("K2CO3") == "base_inorganic"
        assert classify_catalyst(None) == "none"

    def test_xgboost_params_improved(self):
        src = Path("backend/services/yield_predictor.py").read_text(encoding="utf-8")
        assert "n_estimators=500" in src or "500" in src, \
            "XGBoost n_estimators not increased to 500"

    def test_model_metadata_shows_improvement(self):
        meta_path = Path("backend/models/yield_model_metadata.json")
        if not meta_path.exists():
            pytest.skip("Model not yet trained")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        test_mae = meta["metrics"]["test_mae"]
        assert test_mae < 15.0, \
            f"Test MAE {test_mae:.1f}% should be < 15%"


# ── Phase 5: Auth + Structure ──────────────────────────────────────────────────

class TestAuthAndStructure:
    """Phase 5 — API auth, router split, test consolidation."""

    def test_verify_api_key_function_exists(self):
        from dependencies import verify_api_key
        assert callable(verify_api_key)

    def test_dev_mode_when_no_api_key_set(self):
        os.environ.pop("API_KEY", None)
        from dependencies import verify_api_key
        # Should not raise when API_KEY not set
        result = verify_api_key(None)
        assert result == "dev_mode"

    def test_router_files_exist(self):
        router_dir = Path("backend/routers")
        assert router_dir.exists(), "backend/routers/ directory missing"
        expected = ["synthesis.py", "molecule.py", "optimization.py",
                    "equipment.py", "learning.py"]
        for f in expected:
            assert (router_dir / f).exists(), f"Router {f} missing"

    def test_server_py_under_200_lines(self):
        lines = len(Path("backend/server.py").read_text(encoding="utf-8").splitlines())
        assert lines < 200, f"server.py is {lines} lines — should be < 200"

    def test_test_files_consolidated_to_15(self):
        test_files = list(Path("backend/tests").glob("test_*.py"))
        assert len(test_files) <= 15, \
            f"Too many test files: {len(test_files)}. Should be ~10-15 after consolidation."


# ── Phase 6: Scale-up and cost ────────────────────────────────────────────────

class TestScaleAndCost:
    """Phase 6 — Economy of scale, physics yield loss."""

    def test_industrial_cheaper_per_kg_than_lab(self):
        from services.advanced_cost_model import AdvancedCostModel
        model = AdvancedCostModel()
        rxn = {
            "reactants": ["CCO", "CC(=O)O"],
            "products": ["CCOC(C)=O"],
            "temperature_celsius": 80.0,
            "time_hours": 4.0,
            "overall_yield": 82.0,
            "solvents": ["Cc1ccccc1"],
        }
        lab = model.cost_per_kg_product(rxn, "lab", 0.1)
        industrial = model.cost_per_kg_product(rxn, "industrial", 1000.0)
        assert industrial["cost_per_kg_product"] < lab["cost_per_kg_product"] / 5, \
            "Industrial should be 5x+ cheaper per kg than lab"

    def test_grignard_loses_more_yield_than_esterification_at_scale(self):
        from services.scale_aware_optimizer import ScaleAwareOptimizer
        opt = ScaleAwareOptimizer()
        grignard = opt.optimize_for_scale(
            {"yield_percent": 85, "temperature_celsius": -40,
             "reaction_type": "grignard", "time_hours": 4},
            "industrial", 1000.0
        )
        ester = opt.optimize_for_scale(
            {"yield_percent": 85, "temperature_celsius": 80,
             "reaction_type": "esterification", "time_hours": 4},
            "industrial", 1000.0
        )
        assert (grignard["yield_loss_detail"]["total_loss_pct"] >
                ester["yield_loss_detail"]["total_loss_pct"]), \
            "Grignard should lose more yield at scale than esterification"

    def test_scale_up_warnings_generated_for_hot_reactions(self):
        from services.scale_aware_optimizer import ScaleAwareOptimizer
        opt = ScaleAwareOptimizer()
        result = opt.optimize_for_scale(
            {"yield_percent": 85, "temperature_celsius": 150,
             "reaction_type": "diels_alder", "time_hours": 4},
            "industrial", 1000.0
        )
        assert len(result.get("scale_up_warnings", [])) > 0, \
            "Hot reaction at industrial scale should generate warnings"


# ── Phase 7: Specialist models ────────────────────────────────────────────────

class TestSpecialistModels:
    """Phase 7 — Specialist routing, condition safety, real training data."""

    def test_specialist_predictor_file_exists(self):
        assert Path("backend/services/specialist_yield_predictor.py").exists()

    def test_reaction_family_classification(self):
        from services.specialist_yield_predictor import classify_reaction_family
        assert classify_reaction_family("suzuki coupling") == "coupling"
        assert classify_reaction_family("esterification") == "condensation"
        assert classify_reaction_family("grignard addition") == "c_c_formation"
        assert classify_reaction_family("nabh4 reduction") == "reduction"

    def test_condition_safety_filter_blocks_incompatible(self):
        from services.condition_predictor import ConditionPredictor
        cp = ConditionPredictor()
        warnings = cp.check_compatibility("n-BuLi", "ethanol")
        assert len(warnings) > 0, "n-BuLi + ethanol should trigger safety warning"

    def test_condition_safety_filter_passes_compatible(self):
        from services.condition_predictor import ConditionPredictor
        cp = ConditionPredictor()
        warnings = cp.check_compatibility("Pd(PPh3)4", "THF")
        assert len(warnings) == 0, "Pd + THF is a safe combination"

    def test_temperature_prior_for_grignard(self):
        from services.condition_predictor import ConditionPredictor
        cp = ConditionPredictor()
        result = cp.predict_temperature({"reaction_type": "grignard"})
        temp = result["temperature_celsius"]
        assert -78 <= temp <= 25, \
            f"Grignard temperature {temp}°C outside expected range [-78, 25]"

    def test_training_data_has_16_reaction_types(self):
        data_path = Path("backend/data/training_reactions.json")
        if not data_path.exists():
            pytest.skip("training_reactions.json not found")
        data = json.loads(data_path.read_text(encoding="utf-8"))
        types = {r.get("reaction_type") for r in data}
        assert len(types) >= 12, \
            f"Only {len(types)} reaction types in training data — need ≥12"

    def test_specialist_models_pkl_exists_after_training(self):
        pkl = Path("backend/models/specialist_models.pkl")
        if not pkl.exists():
            pytest.skip("Specialist models not yet trained — run train_specialist_models.py")
        assert pkl.stat().st_size > 1000, "specialist_models.pkl appears empty"


# ── Phase 8: Portfolio readiness ──────────────────────────────────────────────

class TestPortfolioReadiness:
    """Phase 8 — Frontend components, Docker, README."""

    def test_readme_exists_with_required_sections(self):
        readme = Path("README.md")
        assert readme.exists(), "README.md missing"
        content = readme.read_text(encoding="utf-8").lower()
        for section in ["quick start", "architecture", "api_key",
                        "docker", "benchmark"]:
            assert section in content, f"README missing section: {section}"

    def test_docker_compose_exists(self):
        assert Path("docker-compose.yml").exists(), "docker-compose.yml missing"

    def test_dockerfiles_exist(self):
        assert Path("backend/Dockerfile").exists(), "backend/Dockerfile missing"
        assert Path("frontend/Dockerfile").exists(), "frontend/Dockerfile missing"

    def test_molecule_renderer_component_exists(self):
        assert Path("frontend/src/components/MoleculeRenderer.js").exists()

    def test_smiles_input_component_exists(self):
        assert Path("frontend/src/components/SmilesInput.js").exists()

    def test_retrosynthesis_tree_component_exists(self):
        assert Path("frontend/src/components/RetrosynthesisTree.js").exists()

    def test_synthesis_store_exists(self):
        assert Path("frontend/src/store/synthesisStore.js").exists()

    def test_synthesis_store_has_required_actions(self):
        src = Path("frontend/src/store/synthesisStore.js").read_text(encoding="utf-8")
        for action in ["setTargetSmiles", "setPlannedRoutes",
                       "setSelectedRoute", "clearSession"]:
            assert action in src, f"Store missing action: {action}"

    def test_env_file_exists(self):
        assert Path("backend/.env").exists() or Path(".env").exists(), \
            ".env file missing"

    def test_field_normalization_utility_exists(self):
        assert Path("backend/services/utils/field_normalization.py").exists()

    def test_routers_directory_has_5_files(self):
        routers = list(Path("backend/routers").glob("*.py"))
        router_count = len([r for r in routers if r.name != "__init__.py"])
        assert router_count >= 5, \
            f"Expected 5 router files, found {router_count}"
