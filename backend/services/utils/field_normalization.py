"""
Pure-logic field normalization utilities for reaction data.

Zero external dependencies — no rdkit, numpy, or ML imports.
Safe to import in any environment.
"""
from typing import Dict, Any, Optional


# Canonical field mappings: variant → standard name
_FIELD_ALIASES: Dict[str, str] = {
    # Temperature
    "temperature_c": "temperature_celsius",
    "temp_celsius": "temperature_celsius",
    "temp_c": "temperature_celsius",
    "temp": "temperature_celsius",
    "temperature": "temperature_celsius",
    # Time
    "time_h": "time_hours",
    "reaction_time": "time_hours",
    "time": "time_hours",
    "duration_hours": "time_hours",
    # Pressure
    "pressure": "pressure_atm",
    "pressure_bar": "pressure_atm",  # Note: will NOT convert units
    # Yield
    "yield": "yield_percent",
    "yield_pct": "yield_percent",
    "product_yield": "yield_percent",
    # Type
    "rxn_type": "reaction_type",
    "type": "reaction_type",
}


def normalize_reaction_fields(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize reaction field names to canonical forms.

    Maps common aliases (temp_c, time_h, yield, etc.) to their
    standard names (temperature_celsius, time_hours, yield_percent).

    Does NOT convert units — only renames keys.

    Args:
        data: dict with possibly non-standard field names.

    Returns:
        New dict with standardized field names. Unknown keys are
        passed through unchanged.
    """
    result: Dict[str, Any] = {}
    for key, value in data.items():
        canonical = _FIELD_ALIASES.get(key.lower().strip(), key)
        result[canonical] = value
    return result


def safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    """
    Safely cast a value to float.

    Returns *default* if the value is None, empty-string, or
    not parseable.
    """
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default
