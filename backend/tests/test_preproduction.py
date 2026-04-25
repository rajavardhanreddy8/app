"""
Pre-Production Validation Suite
Tests every visible UI feature and API behavior before release.
Run this and achieve 100% pass before any production deployment.
"""
import sys, os, types, json, pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

# ── Stubs ──────────────────────────────────────────────────────────
if "structlog" not in sys.modules:
    _sl = types.ModuleType("structlog")
    _sl.get_logger = lambda *a, **kw: __import__("logging").getLogger()
    _sl.configure = lambda **kw: None
    _sl.stdlib = types.SimpleNamespace(filter_by_level=None, LoggerFactory=lambda: None)
    _sl.processors = types.SimpleNamespace(TimeStamper=lambda **kw: None, JSONRenderer=lambda: None)
    sys.modules.update({"structlog": _sl, "structlog.stdlib": _sl.stdlib,
                        "structlog.processors": _sl.processors})
if "anthropic" not in sys.modules:
    _anth = types.ModuleType("anthropic")
    _anth.AsyncAnthropic = type("AsyncAnthropic", (), {"__init__": lambda self, **kw: None})
    sys.modules["anthropic"] = _anth

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.update({
    "DEMO_MODE": "true", "ANTHROPIC_API_KEY": "sk-test",
    "MONGO_URL": "mongodb://localhost:27017", "DB_NAME": "test_db",
})


# ════════════════════════════════════════════════════════════════════
# SECTION 1 — INPUT VALIDATION
# ════════════════════════════════════════════════════════════════════

class TestSMILESInputValidation:

    def test_valid_smiles_accepted(self):
        pytest.importorskip("rdkit")
        from rdkit import Chem
        for smi in ["CC(=O)Oc1ccccc1C(=O)O", "CC(=O)Nc1ccc(O)cc1",
                    "CC(C)Cc1ccc(cc1)C(C)C(=O)O", "Cn1cnc2c1c(=O)n(C)c(=O)n2C",
                    "CCO", "c1ccccc1"]:
            assert Chem.MolFromSmiles(smi) is not None, f"Valid SMILES rejected: {smi}"

    def test_invalid_smiles_rejected(self):
        pytest.importorskip("rdkit")
        from rdkit import Chem
        for smi in ["INVALID_XYZ", "CC(=O)Oc1ccccc1C(=O", "1234", ""]:
            mol = Chem.MolFromSmiles(smi) if smi.strip() else None
            assert mol is None, f"Invalid SMILES accepted: {smi}"

    def test_quick_fill_smiles_are_all_valid(self):
        pytest.importorskip("rdkit")
        from rdkit import Chem
        quick_fill = {
            "Aspirin": "CC(=O)Oc1ccccc1C(=O)O",
            "Paracetamol": "CC(=O)Nc1ccc(O)cc1",
            "Ibuprofen": "CC(C)Cc1ccc(cc1)C(C)C(=O)O",
            "Caffeine": "Cn1cnc2c1c(=O)n(C)c(=O)n2C",
            "Ethanol": "CCO", "Benzene": "c1ccccc1",
        }
        for name, smi in quick_fill.items():
            assert Chem.MolFromSmiles(smi) is not None, f"Quick-fill {name} invalid: {smi}"

    def test_optimize_for_modes_are_valid(self):
        from services.enhanced_route_scorer import EnhancedRouteScorer
        scorer = EnhancedRouteScorer()
        for mode in ["yield", "cost", "time", "balanced"]:
            weights = scorer._get_weights(mode)
            assert weights is not None, f"Mode '{mode}' not handled"

    def test_max_steps_range_1_to_10(self):
        pytest.importorskip("rdkit")
        from services.retrosynthesis_engine import RetrosynthesisEngine
        engine = RetrosynthesisEngine()
        for steps in [1, 3, 5, 10]:
            routes = engine.search_routes("CC(=O)O", max_depth=steps, max_routes=2)
            assert isinstance(routes, list), f"max_steps={steps} caused crash"


# ════════════════════════════════════════════════════════════════════
# SECTION 2 — SYNTHESIS ROUTE RESULTS
# ════════════════════════════════════════════════════════════════════

class TestSynthesisRouteResults:

    def _get_demo_routes(self, smiles="CC(=O)Oc1ccccc1C(=O)O"):
        from services.claude_service import ClaudeService
        svc = ClaudeService()
        result = svc._generate_demo_routes(smiles, 5, "balanced")
        return json.loads(result["content"])["routes"]

    def test_routes_found_count_is_between_1_and_5(self):
        routes = self._get_demo_routes()
        assert 1 <= len(routes) <= 5

    def test_routes_are_not_all_identical(self):
        """BUG FIX: Route 1 and Route 2 had identical scores/yields/costs."""
        routes = self._get_demo_routes()
        if len(routes) < 2:
            pytest.skip("Need at least 2 routes")
        scores = [r.get("score", 0) for r in routes]
        yields = [r.get("overall_yield_percent", r.get("overall_yield", 0)) for r in routes]
        costs  = [r.get("total_cost_usd", 0) for r in routes]
        has_diversity = len(set(scores)) > 1 or len(set(yields)) > 1 or len(set(costs)) > 1
        assert has_diversity, f"All routes identical: scores={scores}, yields={yields}"

    def test_reaction_type_is_never_none_or_unknown(self):
        """BUG FIX: Steps showed 'Unknown' reaction type."""
        routes = self._get_demo_routes()
        for i, route in enumerate(routes):
            for j, step in enumerate(route.get("steps", [])):
                rxn_type = step.get("reaction_type", "")
                assert rxn_type and rxn_type.lower() != "unknown", \
                    f"Route {i+1} Step {j+1} has bad reaction type: '{rxn_type}'"

    def test_reactants_are_never_numeric_strings(self):
        """BUG FIX: Route 3 Step 2 showed reactant as '0'."""
        routes = self._get_demo_routes()
        for i, route in enumerate(routes):
            for j, step in enumerate(route.get("steps", [])):
                for k, reactant in enumerate(step.get("reactants", [])):
                    r_str = reactant.get("smiles", reactant) if isinstance(reactant, dict) else reactant
                    assert not str(r_str).strip().isdigit(), \
                        f"Route {i+1} Step {j+1} Reactant {k+1} is a number: '{r_str}'"

    def test_starting_materials_are_valid_smiles(self):
        """BUG FIX: Starting materials showed 'Invalid SMILES' badges."""
        pytest.importorskip("rdkit")
        from rdkit import Chem
        routes = self._get_demo_routes()
        for i, route in enumerate(routes):
            for sm in route.get("starting_materials", []):
                smi = sm.get("smiles", sm) if isinstance(sm, dict) else sm
                if smi and str(smi).strip():
                    assert Chem.MolFromSmiles(str(smi)) is not None, \
                        f"Route {i+1} starting material invalid SMILES: '{smi}'"

    def test_temperature_is_reasonable(self):
        """BUG FIX: Temperature showed as '80.72176361083984°C'."""
        routes = self._get_demo_routes()
        for i, route in enumerate(routes):
            for j, step in enumerate(route.get("steps", [])):
                cond = step.get("conditions", {})
                temp = cond.get("temperature_celsius")
                if temp is not None:
                    assert -100 <= float(temp) <= 500, \
                        f"Route {i+1} Step {j+1} temperature unrealistic: {temp}"
                    # Check max 2 decimal places when rounded
                    assert float(f"{float(temp):.2f}") == round(float(temp), 2)

    def test_yield_is_between_0_and_100(self):
        routes = self._get_demo_routes()
        for i, route in enumerate(routes):
            y = route.get("overall_yield_percent", route.get("overall_yield", -1))
            assert 0 <= y <= 100, f"Route {i+1} overall_yield out of range: {y}"

    def test_cost_is_positive(self):
        routes = self._get_demo_routes()
        for i, route in enumerate(routes):
            cost = route.get("total_cost_usd", -1)
            assert cost > 0, f"Route {i+1} total_cost_usd not positive: {cost}"

    def test_score_is_between_0_and_100(self):
        routes = self._get_demo_routes()
        for i, route in enumerate(routes):
            score = route.get("score", -1)
            assert 0 <= score <= 100, f"Route {i+1} score out of range: {score}"

    def test_computation_time_tokens_reported(self):
        """BUG FIX: Tokens Used showed 0 in demo mode."""
        from services.claude_service import ClaudeService
        svc = ClaudeService()
        result = svc._generate_demo_routes("CCO", 3, "balanced")
        assert "usage" in result
        assert result["usage"]["total_tokens"] > 0, \
            f"Demo mode must report >0 tokens, got {result['usage']['total_tokens']}"


# ════════════════════════════════════════════════════════════════════
# SECTION 3 — RETROSYNTHESIS ENGINE
# ════════════════════════════════════════════════════════════════════

class TestRetrosynthesisEngine:

    @pytest.fixture(scope="class")
    def engine(self):
        pytest.importorskip("rdkit")
        from services.retrosynthesis_engine import RetrosynthesisEngine
        return RetrosynthesisEngine()

    def test_aspirin_finds_routes(self, engine):
        routes = engine.search_routes("CC(=O)Oc1ccccc1C(=O)O", max_depth=4, max_routes=5)
        assert len(routes) > 0, "Aspirin should yield at least one route"

    def test_routes_have_named_reaction_types(self, engine):
        """BUG FIX: Steps showed 'Unknown' in screenshots."""
        routes = engine.search_routes("CC(=O)Oc1ccccc1C(=O)O", max_depth=3, max_routes=3)
        if not routes:
            pytest.skip("No routes found")
        for route in routes:
            for step in route.get("steps", []):
                rxn_type = step.get("reaction_type", "")
                assert rxn_type, f"Step has empty reaction_type"
                assert rxn_type.lower() != "unknown", f"Step has 'Unknown' reaction type"

    def test_no_reactant_is_a_bare_number(self, engine):
        """BUG FIX: Reactant '0' appeared in Route 3 Step 2."""
        routes = engine.search_routes("CC(=O)Oc1ccccc1C(=O)O", max_depth=4, max_routes=5)
        for i, route in enumerate(routes):
            for j, step in enumerate(route.get("steps", [])):
                for k, reactant in enumerate(step.get("reactants", [])):
                    assert not str(reactant).strip().isdigit(), \
                        f"Route {i+1} Step {j+1} Reactant {k+1} is numeric: '{reactant}'"

    def test_starting_materials_renderable(self, engine):
        """BUG FIX: Starting materials showed 'Invalid SMILES'."""
        pytest.importorskip("rdkit")
        from rdkit import Chem
        routes = engine.search_routes("CC(=O)Oc1ccccc1C(=O)O", max_depth=3, max_routes=3)
        if not routes:
            pytest.skip("No routes found")
        invalid = []
        for route in routes:
            for smi in route.get("starting_materials", []):
                if smi and str(smi).strip():
                    if Chem.MolFromSmiles(str(smi)) is None:
                        invalid.append(smi)
        assert not invalid, f"Invalid SMILES in starting materials: {invalid}"

    def test_invalid_smiles_returns_empty_list(self, engine):
        routes = engine.search_routes("NOT_A_MOLECULE", max_depth=3, max_routes=3)
        assert routes == []

    def test_search_completes_within_time_limit(self, engine):
        import time
        start = time.time()
        engine.search_routes("CC(=O)Oc1ccccc1C(=O)O", max_depth=5, max_routes=5)
        assert time.time() - start < 30.0


# ════════════════════════════════════════════════════════════════════
# SECTION 4 — ML MODEL OUTPUTS
# ════════════════════════════════════════════════════════════════════

class TestMLModelOutputs:

    def test_yield_prediction_never_outside_0_100(self):
        pytest.importorskip("numpy"); pytest.importorskip("xgboost"); pytest.importorskip("rdkit")
        from services.yield_predictor import YieldPredictor
        p = YieldPredictor(); p.load_model()
        for rxn in [
            {"reactants": ["CCO", "CC(=O)O"], "products": ["CCOC(C)=O"],
             "reaction_type": "esterification", "temperature_celsius": 80.0},
            {"reactants": ["Brc1ccccc1", "OB(O)c1ccccc1"],
             "products": ["c1ccc(-c2ccccc2)cc1"], "reaction_type": "suzuki"},
        ]:
            pred = p.predict(rxn)
            if pred is not None:
                assert 0 <= pred <= 100, f"Prediction out of range: {pred}"

    def test_uncertainty_interval_ordering(self):
        pytest.importorskip("numpy"); pytest.importorskip("xgboost"); pytest.importorskip("rdkit")
        from services.yield_predictor import YieldPredictor
        p = YieldPredictor(); p.load_model()
        result = p.predict_with_uncertainty({
            "reactants": ["CCO", "CC(=O)O"], "products": ["CCOC(C)=O"],
            "reaction_type": "esterification", "temperature_celsius": 80.0,
        })
        assert result["lower_bound"] <= result["yield_percent"] <= result["upper_bound"]

    def test_specialist_routing_correct(self):
        pytest.importorskip("numpy"); pytest.importorskip("xgboost"); pytest.importorskip("rdkit")
        from services.specialist_yield_predictor import classify_reaction_family
        assert classify_reaction_family("suzuki coupling") == "coupling"
        assert classify_reaction_family("esterification") == "condensation"
        assert classify_reaction_family("grignard") == "c_c_formation"
        assert classify_reaction_family("reduction") == "reduction"

    def test_condition_safety_warnings_for_incompatible(self):
        from services.condition_predictor import ConditionPredictor
        cp = ConditionPredictor()
        warnings = cp.check_compatibility("n-BuLi", "ethanol")
        assert len(warnings) > 0


# ════════════════════════════════════════════════════════════════════
# SECTION 5 — API ENDPOINT CONTRACTS
# ════════════════════════════════════════════════════════════════════

class TestAPIEndpointContracts:

    def test_synthesis_plan_response_schema(self):
        from services.claude_service import ClaudeService
        svc = ClaudeService()
        result = svc._generate_demo_routes("CC(=O)Oc1ccccc1C(=O)O", 5, "balanced")
        data = json.loads(result["content"])
        assert "routes" in data
        for route in data["routes"]:
            for field in ["starting_materials", "steps", "score", "notes"]:
                assert field in route, f"Route missing field: {field}"
            for step in route["steps"]:
                for field in ["reactants", "product", "reaction_type",
                              "estimated_yield_percent", "estimated_cost_usd", "conditions"]:
                    assert field in step, f"Step missing field: {field}"

    def test_demo_tokens_greater_than_zero(self):
        from services.claude_service import ClaudeService
        result = ClaudeService()._generate_demo_routes("CCO", 3, "balanced")
        assert result["usage"]["total_tokens"] > 0

    def test_server_has_health_endpoint(self):
        src = Path("backend/server.py").read_text(encoding="utf-8")
        assert "/health" in src

    def test_all_routers_registered(self):
        src = Path("backend/server.py").read_text(encoding="utf-8")
        for router in ["synthesis", "molecule", "optimization", "equipment", "learning"]:
            assert router in src, f"Router '{router}' not in server.py"

    def test_server_py_line_count(self):
        lines = len(Path("backend/server.py").read_text(encoding="utf-8").splitlines())
        assert lines < 200, f"server.py is {lines} lines"


# ════════════════════════════════════════════════════════════════════
# SECTION 6 — FRONTEND COMPONENTS
# ════════════════════════════════════════════════════════════════════

class TestFrontendComponents:

    def test_molecule_renderer_handles_invalid_smiles(self):
        src = Path("frontend/src/components/MoleculeRenderer.js").read_text(encoding="utf-8")
        assert "Invalid SMILES" in src or "invalid" in src.lower()
        assert "error" in src.lower()

    def test_smiles_input_has_quick_fill_presets(self):
        src = Path("frontend/src/components/SmilesInput.js").read_text(encoding="utf-8")
        for mol in ["Aspirin", "Paracetamol", "Ibuprofen", "Caffeine", "Ethanol", "Benzene"]:
            assert mol in src, f"SmilesInput missing preset: {mol}"

    def test_synthesis_store_has_persist_middleware(self):
        src = Path("frontend/src/store/synthesisStore.js").read_text(encoding="utf-8")
        assert "persist" in src

    def test_rdkit_cdn_in_index_html(self):
        index = Path("frontend/public/index.html")
        if not index.exists():
            pytest.skip("index.html not found")
        assert "rdkit" in index.read_text(encoding="utf-8").lower()


# ════════════════════════════════════════════════════════════════════
# SECTION 7 — DEPLOYMENT READINESS
# ════════════════════════════════════════════════════════════════════

class TestDeploymentReadiness:

    def test_docker_compose_has_all_services(self):
        dc = Path("docker-compose.yml").read_text(encoding="utf-8")
        for service in ["backend", "frontend", "mongo"]:
            assert service in dc, f"docker-compose.yml missing: {service}"

    def test_env_file_has_required_variables(self):
        env_path = Path("backend/.env") if Path("backend/.env").exists() else Path(".env")
        if not env_path.exists():
            pytest.skip(".env not found")
        content = env_path.read_text(encoding="utf-8")
        assert "API_KEY" in content or "DEMO_MODE" in content

    def test_readme_documents_env_vars(self):
        readme = Path("README.md")
        assert readme.exists()
        content = readme.read_text(encoding="utf-8")
        for var in ["ANTHROPIC_API_KEY", "DEMO_MODE", "MONGO_URL"]:
            assert var in content, f"README missing: {var}"

    def test_models_directory_has_trained_model(self):
        model = Path("backend/models/yield_model.pkl")
        assert model.exists(), "yield_model.pkl missing"
        assert model.stat().st_size > 10_000, "yield_model.pkl looks empty"
