"""
Phase 1 tests for field normalization utilities.

This tests the pure-logic normalize_reaction_fields() and
safe_float() functions. Zero external deps required — these
functions are intentionally isolated from rdkit/numpy.
"""
import sys
import os
import pytest

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.utils.field_normalization import normalize_reaction_fields, safe_float


# ── normalize_reaction_fields tests ───────────────────────────────

class TestNormalizeReactionFields:
    """Test field name normalization."""

    def test_temperature_celsius_maps(self):
        result = normalize_reaction_fields({"temperature_c": 80})
        assert "temperature_celsius" in result
        assert result["temperature_celsius"] == 80

    def test_temp_c_maps(self):
        result = normalize_reaction_fields({"temp_c": 100})
        assert result["temperature_celsius"] == 100

    def test_temp_maps(self):
        result = normalize_reaction_fields({"temp": 25})
        assert result["temperature_celsius"] == 25

    def test_time_h_maps(self):
        result = normalize_reaction_fields({"time_h": 4.5})
        assert result["time_hours"] == 4.5

    def test_reaction_time_maps(self):
        result = normalize_reaction_fields({"reaction_time": 2.0})
        assert result["time_hours"] == 2.0

    def test_yield_maps(self):
        result = normalize_reaction_fields({"yield": 85.0})
        assert result["yield_percent"] == 85.0

    def test_yield_pct_maps(self):
        result = normalize_reaction_fields({"yield_pct": 90})
        assert result["yield_percent"] == 90

    def test_rxn_type_maps(self):
        result = normalize_reaction_fields({"rxn_type": "suzuki"})
        assert result["reaction_type"] == "suzuki"

    def test_unknown_keys_pass_through(self):
        result = normalize_reaction_fields({
            "custom_field": "value",
            "another": 42,
        })
        assert result["custom_field"] == "value"
        assert result["another"] == 42

    def test_already_canonical_unchanged(self):
        result = normalize_reaction_fields({
            "temperature_celsius": 80,
            "time_hours": 4,
            "yield_percent": 75,
        })
        assert result["temperature_celsius"] == 80
        assert result["time_hours"] == 4
        assert result["yield_percent"] == 75

    def test_empty_dict_returns_empty(self):
        assert normalize_reaction_fields({}) == {}

    def test_mixed_canonical_and_aliases(self):
        result = normalize_reaction_fields({
            "temperature_celsius": 100,  # already canonical
            "time_h": 3,                 # alias
            "yield": 80,                 # alias
            "catalyst": "Pd/C",          # passthrough
        })
        assert result == {
            "temperature_celsius": 100,
            "time_hours": 3,
            "yield_percent": 80,
            "catalyst": "Pd/C",
        }

    def test_case_insensitive(self):
        result = normalize_reaction_fields({"Temp_C": 50})
        assert result["temperature_celsius"] == 50

    def test_whitespace_stripped(self):
        result = normalize_reaction_fields({" temp_c ": 75})
        assert result["temperature_celsius"] == 75


# ── safe_float tests ──────────────────────────────────────────────

class TestSafeFloat:
    """Test safe_float utility."""

    def test_int_to_float(self):
        assert safe_float(42) == 42.0

    def test_string_to_float(self):
        assert safe_float("3.14") == 3.14

    def test_none_returns_default(self):
        assert safe_float(None) is None
        assert safe_float(None, default=0.0) == 0.0

    def test_empty_string_returns_default(self):
        assert safe_float("", default=-1.0) == -1.0

    def test_unparseable_returns_default(self):
        assert safe_float("not_a_number") is None
        assert safe_float("abc", default=99.9) == 99.9

    def test_float_passthrough(self):
        assert safe_float(2.718) == 2.718

    def test_negative_float(self):
        assert safe_float("-40.5") == -40.5
from services.molecular_service import normalize_reaction_fields


def test_normalize_reaction_fields_maps_temperature_celsius_to_temperature_c():
    reaction = {
        "reaction_type": "oxidation",
        "temperature_celsius": 80,
    }

    normalized = normalize_reaction_fields(reaction)

    assert normalized["temperature_celsius"] == 80
    assert normalized["temperature_c"] == 80
