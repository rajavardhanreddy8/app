import logging
from typing import Dict, Optional, List
from enum import Enum

logger = logging.getLogger(__name__)

class Scale(Enum):
    """Production scale levels."""
    LAB = "lab"
    PILOT = "pilot"
    INDUSTRIAL = "industrial"

class ScaleAwareOptimizer:
    """Scale-dependent optimization for chemical reactions."""
    
    def __init__(self):
        self.scale_parameters = self._define_scale_parameters()
    
    def _define_scale_parameters(self) -> Dict:
        """Define scale-dependent parameters."""
        return {
            Scale.LAB: {
                'batch_size_range': [0.001, 1.0],  # kg
                'priority': 'purity',
                'cost_weight': 0.1,
                'yield_weight': 0.4,
                'purity_weight': 0.5,
                'catalyst_loading_factor': 1.0,
                'solvent_volume_factor': 1.0,
                'mixing_efficiency': 0.95,
                'heat_transfer_coeff': 500,  # W/m²K
                'reaction_time_factor': 1.0,
                'catalyst_recovery': False,
                'solvent_recovery': False
            },
            Scale.PILOT: {
                'batch_size_range': [1.0, 100.0],  # kg
                'priority': 'balanced',
                'cost_weight': 0.3,
                'yield_weight': 0.4,
                'purity_weight': 0.3,
                'catalyst_loading_factor': 0.8,  # Reduced loading at scale
                'solvent_volume_factor': 0.85,
                'mixing_efficiency': 0.85,
                'heat_transfer_coeff': 300,
                'reaction_time_factor': 1.2,  # Longer times
                'catalyst_recovery': True,
                'solvent_recovery': True
            },
            Scale.INDUSTRIAL: {
                'batch_size_range': [100.0, 10000.0],  # kg
                'priority': 'cost',
                'cost_weight': 0.6,
                'yield_weight': 0.3,
                'purity_weight': 0.1,
                'catalyst_loading_factor': 0.6,
                'solvent_volume_factor': 0.7,
                'mixing_efficiency': 0.75,
                'heat_transfer_coeff': 200,
                'reaction_time_factor': 1.5,
                'catalyst_recovery': True,
                'solvent_recovery': True
            }
        }
    
    def optimize_for_scale(
        self,
        reaction: Dict,
        target_scale: str,
        batch_size_kg: float
    ) -> Dict:
        """
        Optimize reaction parameters for specific scale.
        
        Returns scale-adjusted parameters and predictions.
        """
        scale = Scale(target_scale.lower())
        params = self.scale_parameters[scale]
        
        # Validate batch size
        if not (params['batch_size_range'][0] <= batch_size_kg <= params['batch_size_range'][1]):
            logger.warning(f"Batch size {batch_size_kg}kg outside {scale.value} range")
        
        # Calculate scale-dependent adjustments
        adjustments = {
            'scale': scale.value,
            'batch_size_kg': batch_size_kg,
            'optimization_priority': params['priority']
        }
        
        # Catalyst loading adjustment
        base_catalyst_loading = reaction.get('catalyst_loading', 5.0)  # mol%
        adjusted_catalyst = base_catalyst_loading * params['catalyst_loading_factor']
        adjustments['catalyst_loading_mol_percent'] = round(adjusted_catalyst, 2)
        
        # Solvent volume adjustment
        base_solvent_volume = reaction.get('solvent_volume_ml_per_g', 10.0)
        adjusted_solvent = base_solvent_volume * params['solvent_volume_factor']
        adjustments['solvent_volume_ml_per_g'] = round(adjusted_solvent, 2)
        
        # Reaction time adjustment
        base_time = reaction.get('time_hours', 4.0)
        adjusted_time = base_time * params['reaction_time_factor']
        adjustments['reaction_time_hours'] = round(adjusted_time, 2)
        
        # Mixing considerations
        adjustments['mixing_efficiency'] = params['mixing_efficiency']
        adjustments['requires_special_mixing'] = batch_size_kg > 10.0
        
        # Heat transfer
        adjustments['heat_transfer_coefficient'] = params['heat_transfer_coeff']
        adjustments['requires_cooling_jacket'] = batch_size_kg > 1.0
        
        # Recovery options
        adjustments['catalyst_recovery_feasible'] = params['catalyst_recovery']
        adjustments['solvent_recovery_feasible'] = params['solvent_recovery']
        
        # Yield prediction with scale effects
        base_yield = reaction.get('yield_percent', 75.0)
        
        # Scale-dependent yield loss
        if scale == Scale.LAB:
            yield_loss = 0
        elif scale == Scale.PILOT:
            yield_loss = 3.0  # 3% typical loss at pilot
        else:  # Industrial
            yield_loss = 5.0  # 5% typical loss at industrial
        
        # Mixing efficiency effect
        mixing_loss = (1.0 - params['mixing_efficiency']) * 5.0
        
        adjusted_yield = base_yield - yield_loss - mixing_loss
        adjustments['predicted_yield_percent'] = round(max(0, adjusted_yield), 2)
        
        # Calculate scale factor (useful for equipment)
        adjustments['scale_factor'] = batch_size_kg / 0.1  # Relative to 100g
        
        # Recommendations
        recommendations = self._generate_scale_recommendations(scale, batch_size_kg, params)
        adjustments['recommendations'] = recommendations
        
        return adjustments
    
    def _generate_scale_recommendations(
        self,
        scale: Scale,
        batch_size: float,
        params: Dict
    ) -> List[str]:
        """Generate scale-specific recommendations."""
        recs = []
        
        if scale == Scale.LAB:
            recs.append("Use round-bottom flask with magnetic stirring")
            recs.append("Monitor reaction by TLC every 30 minutes")
            recs.append("Optimize conditions for maximum purity")
            if batch_size > 0.5:
                recs.append("Consider using overhead stirrer for larger batches")
        
        elif scale == Scale.PILOT:
            recs.append("Use jacketed reactor with temperature control")
            recs.append("Implement in-line monitoring (HPLC or GC)")
            recs.append("Plan catalyst recovery (20-30% cost savings)")
            recs.append("Design solvent recovery system")
            recs.append("Document mixing parameters (rpm, impeller type)")
            if batch_size > 50:
                recs.append("Conduct heat transfer calculations")
        
        elif scale == Scale.INDUSTRIAL:
            recs.append("Use industrial reactor with automatic control")
            recs.append("Implement real-time PAT (Process Analytical Technology)")
            recs.append("REQUIRED: Catalyst recovery system")
            recs.append("REQUIRED: Solvent recovery/recycling")
            recs.append("Conduct full process safety analysis")
            recs.append("Design for continuous operation if possible")
            recs.append("Plan waste treatment and disposal")
            recs.append("Calculate energy efficiency and optimize")
            if batch_size > 1000:
                recs.append("Consider distributed reactors for better control")
        
        # Recovery recommendations
        if params['catalyst_recovery']:
            recs.append(f"Expected catalyst recovery: 60-80%")
        if params['solvent_recovery']:
            recs.append(f"Expected solvent recovery: 85-95%")
        
        return recs
    
    def calculate_scale_up_risk(
        self,
        from_scale: str,
        to_scale: str,
        reaction_type: str
    ) -> Dict:
        """Calculate risk factors for scale-up."""
        
        scale_changes = {
            ('lab', 'pilot'): {'risk_level': 'medium', 'success_rate': 0.75},
            ('pilot', 'industrial'): {'risk_level': 'high', 'success_rate': 0.60},
            ('lab', 'industrial'): {'risk_level': 'very_high', 'success_rate': 0.40}
        }
        
        key = (from_scale.lower(), to_scale.lower())
        base_risk = scale_changes.get(key, {'risk_level': 'unknown', 'success_rate': 0.50})
        
        # Reaction-specific adjustments
        high_risk_types = ['grignard', 'organolithium', 'high_pressure', 'cryogenic']
        low_risk_types = ['esterification', 'amidation', 'reduction']
        
        reaction_lower = reaction_type.lower()
        
        if any(rt in reaction_lower for rt in high_risk_types):
            risk_adjustment = -0.15
            risk_factors = ["High-risk reaction type", "Requires specialized equipment"]
        elif any(rt in reaction_lower for rt in low_risk_types):
            risk_adjustment = 0.10
            risk_factors = ["Standard reaction type", "Well-established protocols"]
        else:
            risk_adjustment = 0.0
            risk_factors = ["Moderate risk reaction"]
        
        adjusted_success = max(0.2, min(0.95, base_risk['success_rate'] + risk_adjustment))
        
        return {
            'from_scale': from_scale,
            'to_scale': to_scale,
            'risk_level': base_risk['risk_level'],
            'predicted_success_rate': round(adjusted_success, 2),
            'risk_factors': risk_factors,
            'mitigation_strategies': self._get_mitigation_strategies(base_risk['risk_level'])
        }
    
    def _get_mitigation_strategies(self, risk_level: str) -> List[str]:
        """Get risk mitigation strategies."""
        strategies = {
            'medium': [
                "Conduct small pilot batches first",
                "Monitor key process parameters closely",
                "Document any deviations from lab conditions"
            ],
            'high': [
                "Perform detailed process hazard analysis",
                "Install redundant safety systems",
                "Conduct multiple pilot runs before full scale",
                "Hire experienced process engineer",
                "Plan for 20-30% longer development time"
            ],
            'very_high': [
                "Consider intermediate pilot scale first",
                "Engage process development specialists",
                "Conduct computational fluid dynamics (CFD) modeling",
                "Install advanced process control systems",
                "Budget for significant development time",
                "Plan for iterative optimization cycles"
            ]
        }
        
        return strategies.get(risk_level, ["Consult process engineering specialist"])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    optimizer = ScaleAwareOptimizer()
    
    # Test reaction
    test_reaction = {
        'catalyst_loading': 5.0,
        'solvent_volume_ml_per_g': 10.0,
        'time_hours': 4.0,
        'yield_percent': 85.0
    }
    
    print("\n" + "="*60)
    print("Scale-Aware Optimization System")
    print("="*60)
    
    for scale in ['lab', 'pilot', 'industrial']:
        batch_sizes = {'lab': 0.1, 'pilot': 10.0, 'industrial': 1000.0}
        batch = batch_sizes[scale]
        
        result = optimizer.optimize_for_scale(test_reaction, scale, batch)
        
        print(f"\n{scale.upper()} Scale ({batch}kg):")
        print(f"  Catalyst loading: {result['catalyst_loading_mol_percent']}%")
        print(f"  Solvent volume: {result['solvent_volume_ml_per_g']} mL/g")
        print(f"  Reaction time: {result['reaction_time_hours']}h")
        print(f"  Predicted yield: {result['predicted_yield_percent']}%")
        print(f"  Mixing efficiency: {result['mixing_efficiency']}")
        print(f"  Recommendations: {len(result['recommendations'])}")
    
    print("\n" + "="*60)
    print("Scale-Up Risk Assessment")
    print("="*60)
    
    risk = optimizer.calculate_scale_up_risk('lab', 'industrial', 'Suzuki coupling')
    print(f"Risk level: {risk['risk_level']}")
    print(f"Success rate: {risk['predicted_success_rate']:.0%}")
    print(f"Mitigation strategies: {len(risk['mitigation_strategies'])}")
    
    print("\n" + "="*60)
