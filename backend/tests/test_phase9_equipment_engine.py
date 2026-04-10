from services.equipment_spec_engine import EquipmentSpecEngine
from services.yield_optimization_engine import YieldOptimizationEngine


def test_high_temp_requires_jacketed_reactor_and_cooling():
    engine = EquipmentSpecEngine()
    reaction = {
        "temperature_c": 190.0,
        "pressure_atm": 1.0,
        "density_kg_per_l": 0.95,
        "cp_kj_kg_k": 2.8,
        "delta_t_k": 165.0,
        "cooling_capacity_kw": 30.0,
    }

    result = engine.design_process(reaction, available_equipment=[
        "jacketed_reactor", "cooling_skid", "filtration_unit", "distillation_unit", "drying_unit"
    ], batch_mass_kg=25.0)

    assert result.feasible is True
    assert "jacketed_reactor" in result.required_equipment
    assert "cooling_skid" in result.required_equipment


def test_gas_reaction_requires_autoclave_and_rejects_if_missing():
    engine = EquipmentSpecEngine()
    reaction = {
        "temperature_c": 80.0,
        "pressure_atm": 8.0,
        "phase_type": "gas-liquid",
        "cooling_capacity_kw": 20.0,
    }

    result = engine.design_process(
        reaction,
        available_equipment=["jacketed_reactor", "filtration_unit", "distillation_unit", "drying_unit"],
        batch_mass_kg=10.0,
    )

    assert result.feasible is False
    assert any("Missing required equipment" in msg for msg in result.rejection_reasons)
    assert "autoclave" in result.required_equipment


def test_large_batch_increases_reactor_volume():
    engine = EquipmentSpecEngine()
    base_reaction = {"temperature_c": 25.0, "pressure_atm": 1.0, "density_kg_per_l": 1.0}

    small = engine.design_process(base_reaction, available_equipment=None, batch_mass_kg=5.0)
    large = engine.design_process(base_reaction, available_equipment=None, batch_mass_kg=50.0)

    small_volume = float(small.equipment_spec["reactor"]["volume"].split()[0])
    large_volume = float(large.equipment_spec["reactor"]["volume"].split()[0])

    assert large_volume > small_volume


def test_yield_score_penalizes_equipment_rejection():
    scorer = YieldOptimizationEngine(constraints_engine=None)
    route_ok = {
        "steps": [{"yield_percent": 99}],
        "total_cost_usd": 100.0,
        "equipment_penalty": 0.0,
        "equipment_rejected": False,
    }
    route_bad = {
        "steps": [{"yield_percent": 99}],
        "total_cost_usd": 100.0,
        "equipment_penalty": 0.0,
        "equipment_rejected": True,
    }

    assert scorer._yield_dominant_score(route_ok) > scorer._yield_dominant_score(route_bad)
