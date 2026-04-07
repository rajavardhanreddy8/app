import logging
import json
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class EquipmentRecommender:
    """Recommend laboratory and industrial equipment for chemical reactions."""
    
    def __init__(self, equipment_db_path: str = "/app/backend/data/equipment.json"):
        self.equipment_db_path = Path(equipment_db_path)
        self.equipment_db = self._load_or_create_database()
    
    def _load_or_create_database(self) -> Dict:
        """Load or create equipment database."""
        if self.equipment_db_path.exists():
            try:
                with open(self.equipment_db_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load equipment database: {str(e)}")
        
        # Create default database
        default_db = self._create_default_database()
        self._save_database(default_db)
        return default_db
    
    def _create_default_database(self) -> Dict:
        """Create comprehensive equipment database."""
        return {
            "reactors": {
                "batch_reactor": {
                    "name": "Batch Reactor",
                    "description": "Standard round-bottom flask or jacketed reactor",
                    "scale_range": [1, 100000],  # mg to 100g
                    "temperature_range": [-80, 200],
                    "pressure_range": [0.1, 5],  # atm
                    "suitable_for": ["general", "organic", "batch"],
                    "cost_range": "$100-$5,000",
                    "typical_use": "Lab-scale organic synthesis"
                },
                "cstr": {
                    "name": "Continuous Stirred Tank Reactor (CSTR)",
                    "description": "Continuous flow reactor with perfect mixing",
                    "scale_range": [1000, 1000000],  # 1g to 1kg
                    "temperature_range": [-20, 150],
                    "pressure_range": [1, 10],
                    "suitable_for": ["continuous", "industrial", "steady_state"],
                    "cost_range": "$10,000-$100,000",
                    "typical_use": "Industrial continuous production"
                },
                "plug_flow_reactor": {
                    "name": "Plug Flow Reactor (PFR)",
                    "description": "Tubular reactor for continuous processes",
                    "scale_range": [100, 500000],
                    "temperature_range": [0, 300],
                    "pressure_range": [1, 50],
                    "suitable_for": ["continuous", "gas_phase", "fast_reactions"],
                    "cost_range": "$5,000-$50,000",
                    "typical_use": "Gas-phase or fast liquid reactions"
                },
                "microwave_reactor": {
                    "name": "Microwave Reactor",
                    "description": "Rapid heating via microwave irradiation",
                    "scale_range": [10, 50000],
                    "temperature_range": [20, 250],
                    "pressure_range": [1, 20],
                    "suitable_for": ["fast_heating", "organic", "small_scale"],
                    "cost_range": "$15,000-$50,000",
                    "typical_use": "Rapid synthesis, method development"
                },
                "autoclave": {
                    "name": "High-Pressure Autoclave",
                    "description": "Reactor for high-pressure reactions",
                    "scale_range": [10, 10000],
                    "temperature_range": [-50, 350],
                    "pressure_range": [1, 200],
                    "suitable_for": ["high_pressure", "hydrogenation", "carbonylation"],
                    "cost_range": "$20,000-$100,000",
                    "typical_use": "Hydrogenations, high-pressure chemistry"
                },
                "photoreactor": {
                    "name": "Photochemical Reactor",
                    "description": "UV/visible light-driven reactions",
                    "scale_range": [10, 10000],
                    "temperature_range": [-20, 80],
                    "pressure_range": [1, 2],
                    "suitable_for": ["photochemistry", "radical", "photoredox"],
                    "cost_range": "$5,000-$30,000",
                    "typical_use": "Photocatalysis, radical reactions"
                }
            },
            "auxiliary_equipment": {
                "rotary_evaporator": {
                    "name": "Rotary Evaporator",
                    "description": "Solvent removal under reduced pressure",
                    "suitable_for": ["workup", "purification", "concentration"],
                    "cost_range": "$1,000-$10,000"
                },
                "distillation_column": {
                    "name": "Distillation Column",
                    "description": "Separation by boiling point differences",
                    "suitable_for": ["purification", "separation", "solvent_recovery"],
                    "cost_range": "$500-$20,000"
                },
                "chromatography": {
                    "name": "Flash Chromatography",
                    "description": "Rapid purification of compounds",
                    "suitable_for": ["purification", "separation", "product_isolation"],
                    "cost_range": "$10,000-$50,000"
                },
                "filtration": {
                    "name": "Filtration System",
                    "description": "Solid-liquid separation",
                    "suitable_for": ["workup", "catalyst_removal", "purification"],
                    "cost_range": "$100-$5,000"
                }
            },
            "analytical": {
                "tlc": {
                    "name": "Thin Layer Chromatography (TLC)",
                    "description": "Quick reaction monitoring",
                    "cost_range": "$50-$500"
                },
                "hplc": {
                    "name": "High-Performance Liquid Chromatography",
                    "description": "Quantitative analysis and purity",
                    "cost_range": "$20,000-$100,000"
                },
                "nmr": {
                    "name": "NMR Spectrometer",
                    "description": "Structure determination",
                    "cost_range": "$200,000-$1,000,000"
                },
                "gc_ms": {
                    "name": "GC-MS",
                    "description": "Gas chromatography-mass spectrometry",
                    "cost_range": "$50,000-$200,000"
                }
            }
        }
    
    def _save_database(self, db: Dict):
        """Save database to disk."""
        self.equipment_db_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.equipment_db_path, 'w') as f:
            json.dump(db, f, indent=2)
        logger.info(f"Equipment database saved to {self.equipment_db_path}")
    
    def recommend_reactor(
        self,
        reaction_type: str,
        scale_mg: float,
        temperature_c: Optional[float] = None,
        pressure_atm: Optional[float] = None,
        special_requirements: Optional[List[str]] = None
    ) -> List[Dict]:
        """Recommend appropriate reactors for a reaction."""
        
        recommendations = []
        
        for reactor_id, reactor_data in self.equipment_db.get('reactors', {}).items():
            score = 0
            reasons = []
            
            # Check scale compatibility
            scale_range = reactor_data.get('scale_range', [0, float('inf')])
            if scale_range[0] <= scale_mg <= scale_range[1]:
                score += 30
                reasons.append(f"✓ Scale compatible ({scale_mg}mg within {scale_range[0]}-{scale_range[1]}mg)")
            else:
                continue  # Skip if scale incompatible
            
            # Check temperature compatibility
            if temperature_c is not None:
                temp_range = reactor_data.get('temperature_range', [-273, 1000])
                if temp_range[0] <= temperature_c <= temp_range[1]:
                    score += 25
                    reasons.append(f"✓ Temperature compatible ({temperature_c}°C)")
                else:
                    reasons.append(f"⚠ Temperature may be challenging ({temperature_c}°C)")
                    score -= 20
            
            # Check pressure compatibility
            if pressure_atm is not None and pressure_atm > 1.5:
                press_range = reactor_data.get('pressure_range', [0, 1])
                if press_range[1] >= pressure_atm:
                    score += 20
                    reasons.append(f"✓ Pressure rated for {pressure_atm} atm")
                else:
                    reasons.append(f"✗ Insufficient pressure rating")
                    continue
            
            # Check reaction type compatibility
            suitable_for = reactor_data.get('suitable_for', [])
            reaction_type_lower = reaction_type.lower()
            
            if any(keyword in reaction_type_lower for keyword in suitable_for):
                score += 25
                reasons.append(f"✓ Suitable for {reaction_type}")
            
            # Check special requirements
            if special_requirements:
                for req in special_requirements:
                    if req in suitable_for:
                        score += 10
                        reasons.append(f"✓ Supports {req}")
            
            if score > 0:
                recommendations.append({
                    'reactor': reactor_data['name'],
                    'description': reactor_data['description'],
                    'score': score,
                    'cost_range': reactor_data.get('cost_range'),
                    'typical_use': reactor_data.get('typical_use'),
                    'reasons': reasons
                })
        
        # Sort by score
        recommendations.sort(key=lambda x: x['score'], reverse=True)
        
        return recommendations[:3]  # Return top 3
    
    def recommend_complete_setup(
        self,
        reaction_type: str,
        scale_mg: float,
        temperature_c: Optional[float] = None
    ) -> Dict:
        """Recommend complete equipment setup."""
        
        setup = {
            'reactor': None,
            'workup': [],
            'purification': [],
            'analytical': []
        }
        
        # Reactor
        reactors = self.recommend_reactor(reaction_type, scale_mg, temperature_c)
        if reactors:
            setup['reactor'] = reactors[0]
        
        # Workup equipment
        setup['workup'] = [
            {
                'equipment': 'Rotary Evaporator',
                'purpose': 'Solvent removal',
                'priority': 'essential'
            },
            {
                'equipment': 'Separatory Funnel',
                'purpose': 'Liquid-liquid extraction',
                'priority': 'essential'
            },
            {
                'equipment': 'Filtration System',
                'purpose': 'Catalyst/solid removal',
                'priority': 'recommended'
            }
        ]
        
        # Purification
        if scale_mg < 10000:  # Lab scale
            setup['purification'] = [
                {
                    'equipment': 'Flash Chromatography',
                    'purpose': 'Product purification',
                    'priority': 'recommended'
                },
                {
                    'equipment': 'Recrystallization',
                    'purpose': 'Final purification',
                    'priority': 'optional'
                }
            ]
        else:  # Larger scale
            setup['purification'] = [
                {
                    'equipment': 'Distillation Column',
                    'purpose': 'Separation',
                    'priority': 'recommended'
                },
                {
                    'equipment': 'Crystallization',
                    'purpose': 'Purification',
                    'priority': 'recommended'
                }
            ]
        
        # Analytical
        setup['analytical'] = [
            {
                'equipment': 'TLC',
                'purpose': 'Reaction monitoring',
                'priority': 'essential'
            },
            {
                'equipment': 'NMR',
                'purpose': 'Structure confirmation',
                'priority': 'essential'
            },
            {
                'equipment': 'HPLC',
                'purpose': 'Purity analysis',
                'priority': 'recommended'
            }
        ]
        
        return setup
    
    def get_database_stats(self) -> Dict:
        """Get equipment database statistics."""
        return {
            'total_reactors': len(self.equipment_db.get('reactors', {})),
            'total_auxiliary': len(self.equipment_db.get('auxiliary_equipment', {})),
            'total_analytical': len(self.equipment_db.get('analytical', {})),
            'reactor_types': list(self.equipment_db.get('reactors', {}).keys())
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    recommender = EquipmentRecommender()
    
    print("\n" + "="*50)
    print("Equipment Recommendation System")
    print("="*50)
    
    stats = recommender.get_database_stats()
    print(f"Reactors: {stats['total_reactors']}")
    print(f"Auxiliary Equipment: {stats['total_auxiliary']}")
    print(f"Analytical Equipment: {stats['total_analytical']}")
    
    print("\n" + "="*50)
    print("Example: Suzuki Coupling Recommendation")
    print("="*50)
    
    recommendations = recommender.recommend_reactor(
        reaction_type="Suzuki coupling",
        scale_mg=100,
        temperature_c=80,
        pressure_atm=1.0
    )
    
    for i, rec in enumerate(recommendations, 1):
        print(f"\n{i}. {rec['reactor']} (Score: {rec['score']})")
        print(f"   {rec['description']}")
        print(f"   Cost: {rec['cost_range']}")
        for reason in rec['reasons']:
            print(f"   {reason}")
    
    print("\n" + "="*50)
