"""
Phase 2 tests — building block catalog.
Requires: rdkit
"""
import sys, os, types, pytest

pytest.importorskip("rdkit")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from data.building_blocks import (
        COMMON_BUILDING_BLOCKS,
        CANONICAL_BUILDING_BLOCKS,
        is_building_block_smiles,
    )
except ImportError:
    COMMON_BUILDING_BLOCKS = []
    CANONICAL_BUILDING_BLOCKS = frozenset()
    def is_building_block_smiles(s): return False

from rdkit import Chem


# ── Catalog size and structure ────────────────────────────────────────────────

class TestCatalogStructure:

    def test_minimum_catalog_size(self):
        assert len(COMMON_BUILDING_BLOCKS) >= 80, \
            f"Expected ≥80 building blocks, got {len(COMMON_BUILDING_BLOCKS)}"

    def test_all_entries_are_strings(self):
        for smi in COMMON_BUILDING_BLOCKS:
            assert isinstance(smi, str), f"Non-string entry: {smi}"

    def test_no_empty_strings(self):
        assert all(smi.strip() for smi in COMMON_BUILDING_BLOCKS)

    def test_canonical_set_populated(self):
        assert len(CANONICAL_BUILDING_BLOCKS) >= 70

    def test_canonical_set_is_frozenset(self):
        assert isinstance(CANONICAL_BUILDING_BLOCKS, frozenset)

    def test_canonical_count_close_to_raw_count(self):
        # Some SMILES may be duplicates after canonicalization
        if not COMMON_BUILDING_BLOCKS: pytest.skip("Not implemented")
        ratio = len(CANONICAL_BUILDING_BLOCKS) / len(COMMON_BUILDING_BLOCKS)
        assert ratio > 0.7, \
            f"Too many duplicates after canonicalization: {ratio:.0%} unique"


# ── is_building_block_smiles ──────────────────────────────────────────────────

class TestIsBuildingBlockSmiles:

    def test_benzene_is_building_block(self):
        assert is_building_block_smiles("c1ccccc1") is True

    def test_ethanol_is_building_block(self):
        assert is_building_block_smiles("CCO") is True

    def test_acetic_acid_is_building_block(self):
        assert is_building_block_smiles("CC(=O)O") is True

    def test_bromobenzene_is_building_block(self):
        assert is_building_block_smiles("Brc1ccccc1") is True

    def test_phenylboronic_acid_is_building_block(self):
        assert is_building_block_smiles("OB(O)c1ccccc1") is True

    def test_complex_drug_molecule_not_building_block(self):
        # Ibuprofen — not a building block
        assert is_building_block_smiles("CC(C)Cc1ccc(cc1)C(C)C(=O)O") is False

    def test_random_complex_smiles_not_building_block(self):
        assert is_building_block_smiles("CCCCCCCCCCCCCC(=O)OCCCCCCCCCCC") is False

    def test_invalid_smiles_returns_false_not_exception(self):
        result = is_building_block_smiles("INVALID_XYZ")
        assert result is False

    def test_empty_string_returns_false(self):
        assert is_building_block_smiles("") is False

    def test_noncanonical_smiles_still_recognized(self):
        # OCC is ethanol written differently — should still match CCO
        mol = Chem.MolFromSmiles("OCC")
        if mol:
            canonical = Chem.MolToSmiles(mol)
            if canonical == Chem.MolToSmiles(Chem.MolFromSmiles("CCO")):
                assert is_building_block_smiles("OCC") is True

    def test_toluene_is_building_block(self):
        assert is_building_block_smiles("Cc1ccccc1") is True

    def test_aniline_is_building_block(self):
        assert is_building_block_smiles("Nc1ccccc1") is True

    def test_acetyl_chloride_is_building_block(self):
        assert is_building_block_smiles("CC(=O)Cl") is True

    def test_covers_required_categories(self):
        categories = {
            "aromatic": "c1ccccc1",
            "heteroaromatic": "n1ccccc1",
            "aliphatic_alcohol": "CCO",
            "amine": "CCN",
            "acid_chloride": "CC(=O)Cl",
            "boronic_acid": "OB(O)c1ccccc1",
            "aryl_halide": "Brc1ccccc1",
        }
        missing = []
        for cat, smi in categories.items():
            if not is_building_block_smiles(smi):
                missing.append(f"{cat}: {smi}")
        assert not missing, f"Missing categories: {missing}"


# ── All raw SMILES are valid ──────────────────────────────────────────────────

class TestAllSmilesParseable:

    def test_all_raw_smiles_parse_with_rdkit(self):
        invalid = []
        for smi in COMMON_BUILDING_BLOCKS:
            mol = Chem.MolFromSmiles(smi)
            if mol is None:
                invalid.append(smi)
        assert not invalid, \
            f"{len(invalid)} SMILES fail RDKit parsing: {invalid[:5]}"
