from services.molecular_service import normalize_reaction_fields


def test_normalize_reaction_fields_maps_temperature_celsius_to_temperature_c():
    reaction = {
        "reaction_type": "oxidation",
        "temperature_celsius": 80,
    }

    normalized = normalize_reaction_fields(reaction)

    assert normalized["temperature_celsius"] == 80
    assert normalized["temperature_c"] == 80
