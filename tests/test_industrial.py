import pytest
from backend.models.chemistry import parse_scale_to_mg
from backend.services.equipment_recommender import EquipmentRecommender
from backend.services.cost_database import CostDatabase

def test_scale_parsing():
    assert parse_scale_to_mg("100mg") == 100.0
    assert parse_scale_to_mg("1g") == 1000.0
    assert parse_scale_to_mg("1.5kg") == 1_500_000.0
    assert parse_scale_to_mg("1 ton") == 1_000_000_000.0
    assert parse_scale_to_mg("invalid") == 100_000.0

def test_equipment_scaling():
    er = EquipmentRecommender()
    
    # Lab scale -> normal workup
    small_setup = er.recommend_complete_setup("suzuki", 5000)
    assert not any("Scrubber" in s['equipment'] for s in small_setup['safety_and_auxiliary'])
    assert "Rotary Evaporator" in [s['equipment'] for s in small_setup['workup']]
    
    # Industrial scale -> industrial workup + scrubber
    large_setup = er.recommend_complete_setup("suzuki", 2_000_000) # 2kg
    assert any("Scrubber" in s['equipment'] for s in large_setup['safety_and_auxiliary'])
    assert "Industrial Thin-Film Evaporator" in [s['equipment'] for s in large_setup['workup']]

def test_cost_scaling():
    c_db = CostDatabase()
    
    # Very small scale
    small_cost = c_db.calculate_reaction_cost(
        reactants=["CCC"], 
        reagents=[], 
        catalyst="Pd", 
        solvent="Water", 
        target_mass_mg=100.0, 
        time_hours=4.0, 
        temperature_celsius=25.0
    )
    
    # Industrial scale - should have opex and bulk discounts
    large_cost = c_db.calculate_reaction_cost(
        reactants=["CCC"], 
        reagents=[], 
        catalyst="Pd", 
        solvent="Water", 
        target_mass_mg=5_000_000.0, # 5kg 
        time_hours=4.0, 
        temperature_celsius=25.0
    )
    
    # 50,000x scale should not mean 50,000x total cost due to fixed baseline scaling factors 
    assert small_cost["total_cost"] > 0
    assert large_cost["total_cost"] > small_cost["total_cost"]
    
    # Larger scale has OPEX
    assert large_cost["opex_cost"] > 0
