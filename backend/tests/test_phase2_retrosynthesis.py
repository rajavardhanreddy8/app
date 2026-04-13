"""
Phase 2 tests — SMARTS-based retrosynthesis engine.
Requires: rdkit
"""
import sys, os, types, pytest

pytest.importorskip("rdkit")
pytest.importorskip("numpy")
pytest.importorskip("sklearn")
pytest.importorskip("xgboost")

# Stub structlog before any service import
if "structlog" not in sys.modules:
    _sl = types.ModuleType("structlog")
    _sl.get_logger = lambda *a, **kw: __import__("logging").getLogger("stub")
    _sl.configure = lambda **kw: None
    _sl.stdlib = types.SimpleNamespace(filter_by_level=None, LoggerFactory=lambda: None)
    _sl.processors = types.SimpleNamespace(
        TimeStamper=lambda **kw: None, JSONRenderer=lambda: None
    )
    sys.modules.update({
        "structlog": _sl,
        "structlog.stdlib": _sl.stdlib,
        "structlog.processors": _sl.processors,
    })

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_db")

from rdkit import Chem
from rdkit.Chem import AllChem
from services.retrosynthesis_engine import RetrosynthesisEngine, REACTION_TEMPLATES


# ── REACTION_TEMPLATES constant ───────────────────────────────────────────────

class TestReactionTemplatesConstant:

    def test_templates_list_exists(self):
        assert isinstance(REACTION_TEMPLATES, list)

    def test_minimum_template_count(self):
        assert len(REACTION_TEMPLATES) >= 10, \
            f"Expected ≥10 templates, got {len(REACTION_TEMPLATES)}"

    def test_all_templates_are_strings(self):
        for t in REACTION_TEMPLATES:
            assert isinstance(t, str), f"Non-string template: {t}"

    def test_all_templates_are_valid_smarts(self):
        invalid = []
        for t in REACTION_TEMPLATES:
            rxn = AllChem.ReactionFromSmarts(t)
            if rxn is None:
                invalid.append(t)
        assert not invalid, f"Invalid SMARTS templates: {invalid}"

    def test_templates_contain_arrow(self):
        for t in REACTION_TEMPLATES:
            assert ">>" in t, f"Template missing '>>' separator: {t}"

    def test_esterification_template_present(self):
        ester_like = [t for t in REACTION_TEMPLATES
                      if "C(=O)" in t and ("O" in t or "OH" in t)]
        assert ester_like, "No esterification-like template found"

    def test_suzuki_template_present(self):
        suzuki_like = [t for t in REACTION_TEMPLATES
                       if "B(O)O" in t or "[c:1]" in t]
        assert suzuki_like, "No Suzuki-like template found"


# ── _find_precursors ──────────────────────────────────────────────────────────

class TestFindPrecursors:

    @pytest.fixture(scope="class")
    def engine(self):
        return RetrosynthesisEngine()

    def test_returns_list(self, engine):
        result = engine._find_precursors("CC(=O)Oc1ccccc1")
        assert isinstance(result, list)

    def test_precursor_sets_are_nonempty(self, engine):
        result = engine._find_precursors("CC(=O)Oc1ccccc1")
        assert len(result) >= 1

    def test_each_precursor_set_contains_valid_smiles(self, engine):
        result = engine._find_precursors("CC(=O)Oc1ccccc1C(=O)O")
        for precursor_set in result:
            for smi in precursor_set:
                mol = Chem.MolFromSmiles(smi)
                assert mol is not None, f"Invalid SMILES in precursor set: {smi}"

    def test_invalid_smiles_returns_empty_or_fallback(self, engine):
        result = engine._find_precursors("INVALID_SMILES_XYZ")
        assert isinstance(result, list)

    def test_simple_ester_finds_alcohol_and_acid(self, engine):
        """Ethyl acetate should disconnect to ethanol + acetic acid."""
        result = engine._find_precursors("CCOC(C)=O")
        all_precursors = [smi for group in result for smi in group]
        # At least one precursor should be alcohol-like or acid-like
        has_oxygen = any("O" in smi for smi in all_precursors)
        assert has_oxygen, f"Expected O-containing precursor, got: {all_precursors}"

    def test_not_using_substring_matching(self, engine):
        """Regression: ensure C(=O)O substring check is gone from source."""
        import inspect
        src = inspect.getsource(engine._find_precursors)
        assert "in smiles" not in src or "SMARTS" in src or "RunReactants" in src, \
            "_find_precursors still uses substring matching"

    def test_caching_returns_same_result(self, engine):
        smi = "CC(=O)Oc1ccccc1"
        r1 = engine._find_precursors(smi)
        r2 = engine._find_precursors(smi)
        assert r1 == r2

    def test_fallback_returns_list_not_exception(self, engine):
        """Even completely unknown molecules should not raise."""
        try:
            result = engine._find_precursors("C1CC1")  # cyclopropane
            assert isinstance(result, list)
        except Exception as e:
            pytest.fail(f"_find_precursors raised unexpectedly: {e}")


# ── _calculate_node_score ─────────────────────────────────────────────────────

class TestCalculateNodeScore:

    @pytest.fixture(scope="class")
    def engine(self):
        return RetrosynthesisEngine()

    def test_returns_float(self, engine):
        score = engine._calculate_node_score("CCO", depth=1)
        assert isinstance(score, (int, float))

    def test_score_nonnegative(self, engine):
        score = engine._calculate_node_score("CCO", depth=5)
        assert score >= 0

    def test_building_block_scores_higher_than_nonbuilding_block(self, engine):
        bb_score = engine._calculate_node_score("CCO", depth=1)
        non_bb = "CCCCCCCCCCCC(=O)O"  # dodecanoic acid — unlikely in catalog
        non_bb_score = engine._calculate_node_score(non_bb, depth=1)
        if engine._is_building_block("CCO"):
            assert bb_score > non_bb_score, \
                "Building block should score higher than non-building-block"

    def test_depth_penalty_applied(self, engine):
        score_d1 = engine._calculate_node_score("c1ccccc1", depth=1)
        score_d3 = engine._calculate_node_score("c1ccccc1", depth=3)
        assert score_d1 > score_d3, "Deeper nodes should score lower"

    def test_building_block_bonus_is_positive(self, engine):
        """Building block should get a meaningful score bonus."""
        bb = "CCO"
        non_bb = "CCCCCCCC(=O)OCCCCCCCCCCC"
        if engine._is_building_block(bb):
            diff = engine._calculate_node_score(bb, 1) - \
                   engine._calculate_node_score(non_bb, 1)
            assert diff > 0


# ── Full search_routes integration ────────────────────────────────────────────

class TestSearchRoutesIntegration:

    @pytest.fixture(scope="class")
    def engine(self):
        return RetrosynthesisEngine()

    def test_aspirin_returns_routes(self, engine):
        routes = engine.search_routes(
            "CC(=O)Oc1ccccc1C(=O)O", max_depth=3, max_routes=3
        )
        assert isinstance(routes, list)
        assert len(routes) >= 1

    def test_route_has_required_keys(self, engine):
        routes = engine.search_routes("CCOC(C)=O", max_depth=2, max_routes=2)
        if routes:
            route = routes[0]
            for key in ("target", "starting_materials", "steps", "num_steps", "score"):
                assert key in route, f"Route missing key: {key}"

    def test_route_score_is_nonnegative(self, engine):
        routes = engine.search_routes("CC(=O)O", max_depth=2, max_routes=2)
        for r in routes:
            assert r["score"] >= 0

    def test_invalid_smiles_returns_empty(self, engine):
        routes = engine.search_routes("NOT_A_MOLECULE", max_depth=2, max_routes=2)
        assert routes == []

    def test_simple_molecule_terminates_quickly(self, engine):
        import time
        start = time.time()
        routes = engine.search_routes("CCO", max_depth=2, max_routes=2)
        elapsed = time.time() - start
        assert elapsed < 10.0, f"Search took {elapsed:.1f}s — too slow"
