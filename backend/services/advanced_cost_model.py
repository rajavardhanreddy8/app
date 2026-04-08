import logging
from typing import Dict, Optional, List
from services.cost_database import CostDatabase

logger = logging.getLogger(__name__)

class AdvancedCostModel:
    """Comprehensive cost modeling including energy, time, waste, and recovery."""
    
    def __init__(self):
        self.basic_cost_db = CostDatabase()
        
        # Cost factors (USD)
        self.energy_costs = {
            'electricity_per_kwh': 0.12,
            'natural_gas_per_mmbtu': 3.50,
            'steam_per_kg': 0.015,
            'cooling_water_per_m3': 0.50
        }
        
        self.labor_costs = {
            'lab_technician_per_hour': 35.0,
            'chemist_per_hour': 75.0,
            'engineer_per_hour': 120.0,
            'operator_per_hour': 45.0
        }
        
        self.equipment_costs = {
            'lab_hourly_rate': 25.0,
            'pilot_hourly_rate': 150.0,
            'industrial_hourly_rate': 500.0
        }
        
        self.waste_disposal_costs = {
            'aqueous_per_kg': 0.50,
            'organic_per_kg': 2.00,
            'halogenated_per_kg': 5.00,
            'hazardous_per_kg': 10.00
        }
    
    def calculate_total_cost(
        self,
        reaction: Dict,
        scale: str = 'lab',
        batch_size_kg: float = 0.1,
        include_recovery: bool = False
    ) -> Dict:
        """Calculate comprehensive reaction cost including reagents, energy, time, labor, equipment, waste."""
        costs = {
            'reagent_cost': 0.0,
            'energy_cost': 0.0,
            'labor_cost': 0.0,
            'equipment_cost': 0.0,
            'waste_disposal_cost': 0.0,
            'recovery_savings': 0.0,
            'total_cost': 0.0
        }
        
        # 1. Reagent costs
        reagents = reaction.get('reactants', []) + reaction.get('catalysts', [])
        for reagent_smiles in reagents:
            cost_info = self.basic_cost_db.get_or_estimate_cost(reagent_smiles)
            # Assume 1:1 molar ratio for simplicity, scale by batch size
            costs['reagent_cost'] += cost_info['price_per_gram'] * (batch_size_kg * 1000) * 0.1
        
        # 2. Energy costs
        temperature = reaction.get('temperature_c', 25.0)
        reaction_time_hours = reaction.get('time_hours', 2.0)
        costs['energy_cost'] = self._calculate_energy_cost(
            temperature, reaction_time_hours, batch_size_kg, scale
        )
        
        # 3. Labor costs
        costs['labor_cost'] = self._calculate_labor_cost(
            reaction_time_hours, scale
        )
        
        # 4. Equipment costs
        costs['equipment_cost'] = self._calculate_equipment_cost(
            reaction_time_hours, scale
        )
        
        # 5. Waste disposal
        solvents = reaction.get('solvents', [])
        costs['waste_disposal_cost'] = self._calculate_waste_cost(
            solvents, batch_size_kg
        )
        
        # 6. Recovery savings (if enabled)
        if include_recovery:
            costs['recovery_savings'] = self._calculate_recovery_savings(
                reaction, batch_size_kg
            )
        
        # Total cost
        costs['total_cost'] = (
            costs['reagent_cost'] +
            costs['energy_cost'] +
            costs['labor_cost'] +
            costs['equipment_cost'] +
            costs['waste_disposal_cost'] -
            costs['recovery_savings']
        )
        
        return costs
    
    def _calculate_energy_cost(
        self,
        temperature_c: float,
        reaction_time_hours: float,
        batch_size_kg: float,
        scale: str
    ) -> float:
        """Calculate energy costs for heating, cooling, mixing."""
        energy_cost = 0.0
        
        # Heating energy (simplified)
        if temperature_c > 25:
            delta_t = temperature_c - 25
            heat_capacity = 4.18  # kJ/kg·K (water approximation)
            energy_kwh = (batch_size_kg * heat_capacity * delta_t) / 3600
            energy_cost += energy_kwh * self.energy_costs['electricity_per_kwh']
        
        # Cooling energy (if cryogenic)
        if temperature_c < 0:
            delta_t = abs(temperature_c)
            cooling_energy_kwh = (batch_size_kg * 0.5 * delta_t) / 3600
            energy_cost += cooling_energy_kwh * self.energy_costs['electricity_per_kwh'] * 2.0
        
        # Mixing/stirring energy
        if scale == 'lab':
            mixing_power_kw = 0.05
        elif scale == 'pilot':
            mixing_power_kw = 1.0
        else:
            mixing_power_kw = 10.0
        
        energy_cost += mixing_power_kw * reaction_time_hours * self.energy_costs['electricity_per_kwh']
        
        return energy_cost
    
    def _calculate_labor_cost(
        self,
        reaction_time_hours: float,
        scale: str
    ) -> float:
        """Calculate labor costs."""
        if scale == 'lab':
            hourly_rate = self.labor_costs['chemist_per_hour']
            labor_multiplier = 1.5  # Includes setup/cleanup
        elif scale == 'pilot':
            hourly_rate = self.labor_costs['chemist_per_hour']
            labor_multiplier = 2.0
        else:
            hourly_rate = self.labor_costs['operator_per_hour']
            labor_multiplier = 1.2
        
        return hourly_rate * reaction_time_hours * labor_multiplier
    
    def _calculate_equipment_cost(
        self,
        reaction_time_hours: float,
        scale: str
    ) -> float:
        """Calculate equipment usage costs."""
        if scale == 'lab':
            hourly_rate = self.equipment_costs['lab_hourly_rate']
        elif scale == 'pilot':
            hourly_rate = self.equipment_costs['pilot_hourly_rate']
        else:
            hourly_rate = self.equipment_costs['industrial_hourly_rate']
        
        return hourly_rate * reaction_time_hours
    
    def _calculate_waste_cost(
        self,
        solvents: List[str],
        batch_size_kg: float
    ) -> float:
        """Calculate waste disposal costs."""
        waste_cost = 0.0
        
        for solvent_smiles in solvents:
            # Assume waste volume proportional to batch size
            waste_kg = batch_size_kg * 2.0  # 2:1 solvent to reagent ratio
            
            # Classify waste type
            if 'Cl' in solvent_smiles or 'Br' in solvent_smiles:
                rate = self.waste_disposal_costs['halogenated_per_kg']
            elif 'O' in solvent_smiles:
                rate = self.waste_disposal_costs['organic_per_kg']
            else:
                rate = self.waste_disposal_costs['aqueous_per_kg']
            
            waste_cost += waste_kg * rate
        
        return waste_cost
    
    def _calculate_recovery_savings(
        self,
        reaction: Dict,
        batch_size_kg: float
    ) -> float:
        """Calculate savings from catalyst and solvent recovery."""
        savings = 0.0
        
        # Catalyst recovery (80% recovery for precious metals)
        catalysts = reaction.get('catalysts', [])
        for cat_smiles in catalysts:
            if 'Pd' in cat_smiles or 'Pt' in cat_smiles or 'Rh' in cat_smiles:
                cost_info = self.basic_cost_db.get_or_estimate_cost(cat_smiles)
                catalyst_amount_g = batch_size_kg * 1000 * 0.01  # 1% catalyst loading
                recovery_rate = 0.80
                savings += cost_info['price_per_gram'] * catalyst_amount_g * recovery_rate
        
        # Solvent recovery (60% recovery via distillation)
        solvents = reaction.get('solvents', [])
        for solv_smiles in solvents:
            cost_info = self.basic_cost_db.get_or_estimate_cost(solv_smiles)
            solvent_amount_g = batch_size_kg * 1000 * 2.0  # 2:1 ratio
            recovery_rate = 0.60
            savings += cost_info['price_per_gram'] * solvent_amount_g * recovery_rate
        
        return savings
    
    def compare_routes_by_cost(
        self,
        routes: List[Dict],
        scale: str = 'lab',
        batch_size_kg: float = 0.1,
        include_recovery: bool = False
    ) -> List[Dict]:
        """Compare multiple routes by total cost."""
        route_costs = []
        
        for route in routes:
            total_cost = 0.0
            cost_breakdown = []
            
            # Calculate cost for each step
            for step in route.get('steps', []):
                step_cost = self.calculate_total_cost(
                    step, scale, batch_size_kg, include_recovery
                )
                total_cost += step_cost['total_cost']
                cost_breakdown.append(step_cost)
            
            route_costs.append({
                'route': route,
                'total_cost': total_cost,
                'cost_breakdown': cost_breakdown,
                'cost_per_kg_product': total_cost / batch_size_kg if batch_size_kg > 0 else 0
            })
        
        # Sort by total cost
        route_costs.sort(key=lambda x: x['total_cost'])
        
        return route_costs


# Demo/testing code
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    model = AdvancedCostModel()
    
    # Test reaction
    test_reaction = {
        'reactants': ['c1ccccc1', 'CCO'],
        'products': ['c1ccccc1O'],
        'catalysts': ['[Pd]'],
        'solvents': ['C1CCOC1'],
        'temperature_c': 80.0,
        'time_hours': 4.0
    }
    
    print("\n=== Advanced Cost Modeling Test ===")
    print(f"Reaction: Phenol synthesis")
    
    # Lab scale
    lab_cost = model.calculate_total_cost(test_reaction, scale='lab', batch_size_kg=0.1)
    print(f"\nLab Scale (100g batch):")
    for key, value in lab_cost.items():
        print(f"  {key}: ${value:.2f}")
    
    # Pilot scale with recovery
    pilot_cost = model.calculate_total_cost(
        test_reaction, 
        scale='pilot', 
        batch_size_kg=10.0, 
        include_recovery=True
    )
    print(f"\nPilot Scale (10kg batch) with Recovery:")
    for key, value in pilot_cost.items():
        print(f"  {key}: ${value:.2f}")
    
    print("\n✓ Advanced Cost Model Test Complete")
