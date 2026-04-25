import logging
from typing import Dict, Optional, List
from services.cost_database import CostDatabase

logger = logging.getLogger(__name__)

class AdvancedCostModel:
    """Comprehensive cost modeling with economy of scale — fixed + variable cost split."""
    
    def __init__(self):
        self.basic_cost_db = CostDatabase()
        
        # ── Fixed costs per batch (do NOT scale with batch size) ──
        self.fixed_costs = {
            'lab': {
                'equipment_setup': 200.0,
                'qc_testing': 50.0,
                'regulatory_documentation': 0.0,
            },
            'pilot': {
                'equipment_setup': 2000.0,
                'qc_testing': 500.0,
                'regulatory_documentation': 1000.0,
            },
            'industrial': {
                'equipment_setup': 15000.0,
                'qc_testing': 2000.0,
                'regulatory_documentation': 5000.0,
            },
        }
        
        # ── Energy costs (USD) — variable, scale with batch ──
        self.energy_costs = {
            'electricity_per_kwh': 0.12,
            'natural_gas_per_mmbtu': 3.50,
            'steam_per_kg': 0.015,
            'cooling_water_per_m3': 0.50
        }
        
        # ── Labor costs (variable portion scales with reaction time) ──
        self.labor_costs = {
            'lab_technician_per_hour': 35.0,
            'chemist_per_hour': 75.0,
            'engineer_per_hour': 120.0,
            'operator_per_hour': 45.0
        }
        
        # Fixed setup time per batch — 2 hours regardless of batch size
        self.labor_setup_hours = 2.0
        
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
    
    # ── Tiered reagent pricing ──
    def _reagent_discount_factor(self, batch_size_kg: float) -> float:
        """Volume discount for reagent purchasing."""
        if batch_size_kg > 100.0:
            return 0.25   # Industrial contract pricing
        elif batch_size_kg >= 1.0:
            return 0.60   # Bulk discount
        else:
            return 1.00   # Full catalog price
    
    def calculate_total_cost(
        self,
        reaction: Dict,
        scale: str = 'lab',
        batch_size_kg: float = 0.1,
        include_recovery: bool = False
    ) -> Dict:
        """Calculate comprehensive reaction cost including fixed + variable components."""
        scale = scale.lower()
        
        # ── Fixed costs ──
        fixed = self.fixed_costs.get(scale, self.fixed_costs['lab'])
        fixed_total = sum(fixed.values())
        
        costs = {
            'fixed_equipment_setup': fixed['equipment_setup'],
            'fixed_qc_testing': fixed['qc_testing'],
            'fixed_regulatory': fixed['regulatory_documentation'],
            'fixed_total': fixed_total,
            'reagent_cost': 0.0,
            'energy_cost': 0.0,
            'labor_cost': 0.0,
            'equipment_cost': 0.0,
            'waste_disposal_cost': 0.0,
            'recovery_savings': 0.0,
            'total_cost': 0.0
        }
        
        # ── 1. Reagent costs (variable, with tiered pricing) ──
        discount = self._reagent_discount_factor(batch_size_kg)
        reagents = reaction.get('reactants', []) + reaction.get('catalysts', [])
        for reagent_smiles in reagents:
            if reagent_smiles and reagent_smiles.strip():
                cost_per_gram = self.basic_cost_db.get_reagent_cost(reagent_smiles)
                if cost_per_gram:
                    costs['reagent_cost'] += cost_per_gram * (batch_size_kg * 1000) * 0.10 * discount
        
        # ── 2. Energy costs (variable, scales with batch) ──
        temperature = reaction.get('temperature_c', 25.0)
        reaction_time_hours = reaction.get('time_hours', 2.0)
        costs['energy_cost'] = self._calculate_energy_cost(
            temperature, reaction_time_hours, batch_size_kg, scale
        )
        
        # ── 3. Labor costs (fixed setup + variable time) ──
        costs['labor_cost'] = self._calculate_labor_cost(
            reaction_time_hours, scale
        )
        
        # ── 4. Equipment costs (variable, hourly usage) ──
        costs['equipment_cost'] = self._calculate_equipment_cost(
            reaction_time_hours, scale
        )
        
        # ── 5. Waste disposal (variable, scales with batch) ──
        solvents = reaction.get('solvents', [])
        costs['waste_disposal_cost'] = self._calculate_waste_cost(
            solvents, batch_size_kg
        )
        
        # ── 6. Recovery savings (if enabled) ──
        if include_recovery:
            costs['recovery_savings'] = self._calculate_recovery_savings(
                reaction, batch_size_kg
            )
        
        # ── Total cost ──
        variable_total = (
            costs['reagent_cost'] +
            costs['energy_cost'] +
            costs['labor_cost'] +
            costs['equipment_cost'] +
            costs['waste_disposal_cost']
        )
        
        gross_cost = fixed_total + variable_total
        
        # Cap recovery savings at 80% of gross cost
        max_recovery = gross_cost * 0.80
        costs['recovery_savings'] = min(costs['recovery_savings'], max_recovery)
        
        costs['variable_total'] = variable_total
        costs['total_cost'] = gross_cost - costs['recovery_savings']
        
        return costs
    
    def cost_per_kg_product(
        self,
        reaction: Dict,
        scale: str = 'lab',
        batch_size_kg: float = 0.1
    ) -> Dict:
        """
        Return total cost / (batch_size_kg × overall_yield/100).

        This is what users actually care about — the cost to produce 1 kg of
        final product after accounting for yield losses.
        """
        costs = self.calculate_total_cost(reaction, scale, batch_size_kg, include_recovery=True)
        
        overall_yield_pct = reaction.get('overall_yield', 75.0)
        product_kg = batch_size_kg * (overall_yield_pct / 100.0)
        
        cost_per_kg = costs['total_cost'] / product_kg if product_kg > 0 else float('inf')
        
        return {
            **costs,
            'overall_yield_pct': overall_yield_pct,
            'product_kg': round(product_kg, 4),
            'cost_per_kg_product': round(cost_per_kg, 2),
        }
    
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
        """Calculate labor costs including fixed 2-hour setup per batch."""
        if scale == 'lab':
            hourly_rate = self.labor_costs['chemist_per_hour']
            labor_multiplier = 1.5  # Includes cleanup
        elif scale == 'pilot':
            hourly_rate = self.labor_costs['chemist_per_hour']
            labor_multiplier = 2.0
        else:
            hourly_rate = self.labor_costs['operator_per_hour']
            labor_multiplier = 1.2
        
        # Fixed setup time + variable reaction time
        total_hours = self.labor_setup_hours + (reaction_time_hours * labor_multiplier)
        return hourly_rate * total_hours
    
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
            if cat_smiles and ('Pd' in cat_smiles or 'Pt' in cat_smiles or 'Rh' in cat_smiles):
                cost_per_gram = self.basic_cost_db.get_reagent_cost(cat_smiles) or 45.0
                catalyst_amount_g = batch_size_kg * 1000 * 0.01  # 1% catalyst loading
                recovery_rate = 0.80
                savings += cost_per_gram * catalyst_amount_g * recovery_rate
        
        # Solvent recovery (60% recovery via distillation)
        solvents = reaction.get('solvents', [])
        for solv_smiles in solvents:
            if solv_smiles and solv_smiles.strip():
                cost_per_gram = self.basic_cost_db.get_reagent_cost(solv_smiles) or 0.10
                solvent_amount_g = batch_size_kg * 1000 * 0.5  # 0.5:1 ratio
                recovery_rate = 0.60
                savings += cost_per_gram * solvent_amount_g * recovery_rate
        
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
    
    # Test reaction — esterification
    test_reaction = {
        'reactants': ['CC(=O)O', 'CCO'],
        'products': ['CC(=O)OCC'],
        'catalysts': [''],
        'solvents': ['C1CCOC1'],
        'temperature_c': 80.0,
        'time_hours': 4.0,
        'overall_yield': 75.0,
    }
    
    print("\n" + "=" * 70)
    print("Economy of Scale — Cost per kg Product (Esterification)")
    print("=" * 70)
    print(f"{'Scale':<15} {'Batch kg':<12} {'Fixed $':<12} {'Variable $':<14} {'Total $':<12} {'$/kg product':<14}")
    print("-" * 70)
    
    for scale, batch in [('lab', 0.1), ('pilot', 10.0), ('industrial', 1000.0)]:
        r = model.cost_per_kg_product(test_reaction, scale, batch)
        print(
            f"{scale:<15} {batch:<12.1f} "
            f"${r['fixed_total']:<11.2f} ${r['variable_total']:<13.2f} "
            f"${r['total_cost']:<11.2f} ${r['cost_per_kg_product']:<13.2f}"
        )
    
    print("=" * 70)
    print("✓ Advanced Cost Model Test Complete")
