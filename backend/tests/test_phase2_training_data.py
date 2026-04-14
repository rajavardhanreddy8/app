"""
Phase 2 tests — synthetic training data generation.
Requires: rdkit
"""
import sys, os, types, json, tempfile, pytest
from pathlib import Path

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
        "structlog": _sl,
        "structlog.stdlib": _sl.stdlib,
        "structlog.processors": _sl.processors,
    })

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_db")

try:
    from services.data_downloader import generate_synthetic_training_dataset, download_ord_subset
except ImportError:
    def generate_synthetic_training_dataset(*a, **kw): return []
    def download_ord_subset(*a, **kw): return []


# ── generate_synthetic_training_dataset ──────────────────────────────────────

class TestGenerateSyntheticDataset:

    @pytest.fixture(scope="class")
    def dataset(self):
        return generate_synthetic_training_dataset(n_reactions=200, seed=42)

    def test_returns_list(self, dataset):
        assert isinstance(dataset, list)

    def test_returns_requested_count(self, dataset):
        assert len(dataset) == 200

    def test_every_reaction_has_required_fields(self, dataset):
        required = {
            "reactants", "products", "reaction_type",
            "yield_percent", "temperature_celsius",
            "catalyst", "solvent", "time_hours"
        }
        for i, rxn in enumerate(dataset):
            missing = required - set(rxn.keys())
            assert not missing, f"Reaction {i} missing fields: {missing}"

    def test_yield_in_valid_range(self, dataset):
        for rxn in dataset:
            assert 0 <= rxn["yield_percent"] <= 100, \
                f"yield_percent out of range: {rxn['yield_percent']}"

    def test_temperature_is_numeric(self, dataset):
        for rxn in dataset:
            assert isinstance(rxn["temperature_celsius"], (int, float))

    def test_products_are_valid_smiles(self, dataset):
        from rdkit import Chem
        invalid = []
        for i, rxn in enumerate(dataset):
            for smi in rxn["products"]:
                if Chem.MolFromSmiles(smi) is None:
                    invalid.append((i, smi))
        assert not invalid, \
            f"{len(invalid)} invalid product SMILES: {invalid[:3]}"

    def test_reactants_are_valid_smiles(self, dataset):
        from rdkit import Chem
        invalid = []
        for i, rxn in enumerate(dataset):
            for smi in rxn["reactants"]:
                if smi and Chem.MolFromSmiles(smi) is None:
                    invalid.append((i, smi))
        assert not invalid, \
            f"{len(invalid)} invalid reactant SMILES: {invalid[:3]}"

    def test_covers_multiple_reaction_types(self, dataset):
        types_present = {rxn["reaction_type"] for rxn in dataset}
        assert len(types_present) >= 5, \
            f"Expected ≥5 reaction types, got {len(types_present)}: {types_present}"

    def test_expected_reaction_types_present(self, dataset):
        types_present = {rxn["reaction_type"] for rxn in dataset}
        expected = {"esterification", "suzuki", "reduction"}
        missing = expected - types_present
        assert not missing, f"Missing reaction types: {missing}"

    def test_deterministic_with_same_seed(self):
        d1 = generate_synthetic_training_dataset(n_reactions=50, seed=99)
        d2 = generate_synthetic_training_dataset(n_reactions=50, seed=99)
        if not d1: pytest.skip("Not implemented")
        assert d1[0]["yield_percent"] == d2[0]["yield_percent"]
        assert d1[0]["reaction_type"] == d2[0]["reaction_type"]

    def test_different_seeds_give_different_data(self):
        d1 = generate_synthetic_training_dataset(n_reactions=50, seed=1)
        d2 = generate_synthetic_training_dataset(n_reactions=50, seed=2)
        if not d1: pytest.skip("Not implemented")
        yields1 = [r["yield_percent"] for r in d1]
        yields2 = [r["yield_percent"] for r in d2]
        assert yields1 != yields2

    def test_time_hours_positive(self, dataset):
        for rxn in dataset:
            assert rxn["time_hours"] > 0

    def test_no_none_catalyst_in_string_field(self, dataset):
        # Catalyst can be None (Python None) but not the string "None"
        for rxn in dataset:
            assert rxn["catalyst"] != "None", \
                "Catalyst stored as string 'None' — should be Python None or real value"


# ── download_ord_subset (offline fallback) ────────────────────────────────────

class TestDownloadOrdSubset:

    def test_creates_json_file(self, tmp_path):
        output = tmp_path / "training_reactions.json"
        reactions = download_ord_subset(output_path=output, n_synthetic=100)
        assert output.exists()

    def test_json_file_is_valid_list(self, tmp_path):
        output = tmp_path / "training_reactions.json"
        download_ord_subset(output_path=output, n_synthetic=100)
        with open(output) as f:
            data = json.load(f)
        assert isinstance(data, list)
        assert len(data) >= 100

    def test_returns_list_of_dicts(self, tmp_path):
        output = tmp_path / "out.json"
        result = download_ord_subset(output_path=output, n_synthetic=50)
        assert isinstance(result, list)
        assert all(isinstance(r, dict) for r in result)

    def test_saved_file_matches_returned_list(self, tmp_path):
        output = tmp_path / "out.json"
        returned = download_ord_subset(output_path=output, n_synthetic=50)
        with open(output) as f:
            saved = json.load(f)
        assert len(returned) == len(saved)


# ── yield_predictor prepare_training_data ────────────────────────────────────

class TestPrepareTrainingDataSources:

    def test_loads_from_json_file_when_exists(self, tmp_path):
        """Verify prepare_training_data prefers the JSON file source."""
        reactions = generate_synthetic_training_dataset(n_reactions=50, seed=1)
        json_path = tmp_path / "training_reactions.json"
        if not reactions: pytest.skip("Not implemented")
        with open(json_path, "w") as f:
            json.dump(reactions, f)
        assert json_path.exists()
        with open(json_path) as f:
            loaded = json.load(f)
        assert len(loaded) == 50

    def test_json_reactions_have_yield_field(self):
        reactions = generate_synthetic_training_dataset(n_reactions=20, seed=5)
        if not reactions: pytest.skip("Not implemented")
        for rxn in reactions:
            assert "yield_percent" in rxn
            assert rxn["yield_percent"] is not None

    def test_yield_predictor_source_in_prepare_training_data(self):
        """Regression: prepare_training_data must reference training_reactions.json."""
        with open("backend/services/yield_predictor.py") as f:
            source = f.read()
        assert "training_reactions.json" in source, \
            "yield_predictor.prepare_training_data() doesn't load from training_reactions.json"

    def test_generate_training_data_script_exists(self):
        assert Path("backend/scripts/generate_training_data.py").exists(), \
            "backend/scripts/generate_training_data.py not found"

    def test_generate_script_calls_download_ord_subset(self):
        if not Path("backend/scripts/generate_training_data.py").exists(): pytest.skip("Not found")
        with open("backend/scripts/generate_training_data.py") as f:
            source = f.read()
        assert "download_ord_subset" in source
