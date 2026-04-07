import logging
import pickle
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
from rdkit import Chem
from rdkit.Chem import AllChem
from services.reaction_database import ReactionDatabase
import asyncio

logger = logging.getLogger(__name__)

class TemplateExtractor:
    """Extract and store reaction templates for retrosynthesis."""
    
    def __init__(self, template_db_path: str = "/app/backend/data/templates.pkl"):
        self.template_db_path = Path(template_db_path)
        self.templates = {}
        
    async def extract_templates_from_database(self) -> Dict[str, List[Dict]]:
        """Extract reaction templates from database reactions."""
        logger.info("Extracting templates from reaction database...")
        
        db = ReactionDatabase()
        reactions = await db.get_reactions_with_yield(min_yield=0, limit=10000)
        
        logger.info(f"Processing {len(reactions)} reactions for template extraction")
        
        templates_by_type = defaultdict(list)
        
        for rxn in reactions:
            try:
                template = self._extract_template_from_reaction(rxn)
                if template:
                    rxn_type = rxn.get('reaction_type', 'unknown')
                    templates_by_type[rxn_type].append(template)
            except Exception as e:
                logger.debug(f"Failed to extract template: {str(e)}")
                continue
        
        # Aggregate statistics
        aggregated_templates = {}
        for rxn_type, templates in templates_by_type.items():
            aggregated_templates[rxn_type] = self._aggregate_templates(templates)
        
        logger.info(f"Extracted templates for {len(aggregated_templates)} reaction types")
        
        self.templates = aggregated_templates
        self.save_templates()
        
        return aggregated_templates
    
    def _extract_template_from_reaction(self, reaction: Dict) -> Optional[Dict]:
        """Extract a simple template from a reaction."""
        try:
            reactants = reaction.get('reactants', [])
            products = reaction.get('products', [])
            
            if not reactants or not products:
                return None
            
            # Simple template: store SMARTS patterns
            reactant_mols = [Chem.MolFromSmiles(s) for s in reactants if Chem.MolFromSmiles(s)]
            product_mols = [Chem.MolFromSmiles(s) for s in products if Chem.MolFromSmiles(s)]
            
            if not reactant_mols or not product_mols:
                return None
            
            # Create simple template
            template = {
                'reactant_patterns': [Chem.MolToSmarts(mol) for mol in reactant_mols],
                'product_patterns': [Chem.MolToSmarts(mol) for mol in product_mols],
                'reaction_smiles': reaction.get('reaction_smiles'),
                'yield': reaction.get('yield_percent', 0),
                'conditions': {
                    'temperature': reaction.get('temperature_celsius'),
                    'catalyst': reaction.get('catalyst'),
                    'solvent': reaction.get('solvent')
                }
            }
            
            return template
            
        except Exception as e:
            logger.debug(f"Template extraction failed: {str(e)}")
            return None
    
    def _aggregate_templates(self, templates: List[Dict]) -> Dict:
        """Aggregate multiple templates into statistics."""
        if not templates:
            return {}
        
        avg_yield = sum(t.get('yield', 0) for t in templates) / len(templates)
        
        # Common conditions
        catalysts = [t['conditions'].get('catalyst') for t in templates if t['conditions'].get('catalyst')]
        solvents = [t['conditions'].get('solvent') for t in templates if t['conditions'].get('solvent')]
        temperatures = [t['conditions'].get('temperature') for t in templates if t['conditions'].get('temperature')]
        
        return {
            'count': len(templates),
            'avg_yield': round(avg_yield, 2),
            'common_catalysts': list(set(catalysts))[:5],
            'common_solvents': list(set(solvents))[:5],
            'avg_temperature': round(sum(temperatures) / len(temperatures), 1) if temperatures else None,
            'example_templates': templates[:3]  # Store first 3 as examples
        }
    
    def get_templates_for_reaction_type(self, reaction_type: str) -> Optional[Dict]:
        """Get templates for a specific reaction type."""
        if not self.templates:
            self.load_templates()
        
        # Try exact match
        if reaction_type in self.templates:
            return self.templates[reaction_type]
        
        # Try partial match
        reaction_type_lower = reaction_type.lower()
        for key, value in self.templates.items():
            if reaction_type_lower in key.lower():
                return value
        
        return None
    
    def save_templates(self):
        """Save templates to disk."""
        self.template_db_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.template_db_path, 'wb') as f:
            pickle.dump(self.templates, f)
        
        logger.info(f"Templates saved to {self.template_db_path}")
    
    def load_templates(self) -> bool:
        """Load templates from disk."""
        if not self.template_db_path.exists():
            logger.warning(f"Template file not found: {self.template_db_path}")
            return False
        
        try:
            with open(self.template_db_path, 'rb') as f:
                self.templates = pickle.load(f)
            
            logger.info(f"Loaded {len(self.templates)} template types")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load templates: {str(e)}")
            return False
    
    def get_statistics(self) -> Dict:
        """Get template database statistics."""
        if not self.templates:
            self.load_templates()
        
        total_count = sum(t.get('count', 0) for t in self.templates.values())
        
        return {
            'total_reaction_types': len(self.templates),
            'total_templates': total_count,
            'reaction_types': list(self.templates.keys()),
            'avg_yield_by_type': {k: v.get('avg_yield') for k, v in self.templates.items()}
        }


async def main():
    """Extract templates from database."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    extractor = TemplateExtractor()
    templates = await extractor.extract_templates_from_database()
    
    print("\n" + "="*50)
    print("Reaction Template Extraction Complete")
    print("="*50)
    
    stats = extractor.get_statistics()
    print(f"Total Reaction Types: {stats['total_reaction_types']}")
    print(f"Total Templates: {stats['total_templates']}")
    
    print(f"\nReaction Types:")
    for rxn_type, avg_yield in stats['avg_yield_by_type'].items():
        count = templates[rxn_type]['count']
        print(f"  {rxn_type}: {count} templates (avg {avg_yield}% yield)")
    
    print("="*50)

if __name__ == "__main__":
    asyncio.run(main())
