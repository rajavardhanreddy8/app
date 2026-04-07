import logging
from typing import Dict, Optional, List
from rdkit import Chem
from rdkit.Chem import Descriptors
import json
from pathlib import Path

logger = logging.getLogger(__name__)

class CostDatabase:
    """Database and estimator for chemical reagent costs."""
    
    def __init__(self, cost_db_path: str = "/app/backend/data/reagent_costs.json"):
        self.cost_db_path = Path(cost_db_path)
        self.cost_db = self._load_or_create_database()
    
    def _load_or_create_database(self) -> Dict[str, Dict]:
        """Load or create reagent cost database."""
        if self.cost_db_path.exists():
            try:
                with open(self.cost_db_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load cost database: {str(e)}")
        
        # Create default database with common reagents
        default_db = self._create_default_database()
        self._save_database(default_db)
        return default_db
    
    def _create_default_database(self) -> Dict[str, Dict]:
        """Create database with common reagent costs (USD per gram)."""
        return {
            # Common solvents (cheap)
            "CCO": {"name": "Ethanol", "price_per_gram": 0.05, "category": "solvent"},
            "C1CCOC1": {"name": "THF", "price_per_gram": 0.15, "category": "solvent"},
            "ClCCl": {"name": "DCM", "price_per_gram": 0.08, "category": "solvent"},
            "CC(=O)C": {"name": "Acetone", "price_per_gram": 0.03, "category": "solvent"},
            "CN(C)C=O": {"name": "DMF", "price_per_gram": 0.12, "category": "solvent"},
            "c1ccncc1": {"name": "Pyridine", "price_per_gram": 0.20, "category": "solvent"},
            
            # Common acids/bases
            "CC(=O)O": {"name": "Acetic acid", "price_per_gram": 0.10, "category": "reagent"},
            "[H]Cl": {"name": "HCl", "price_per_gram": 0.05, "category": "acid"},
            "[H]OS(=O)(=O)O": {"name": "H2SO4", "price_per_gram": 0.02, "category": "acid"},
            "[Na+].[OH-]": {"name": "NaOH", "price_per_gram": 0.03, "category": "base"},
            
            # Common catalysts (expensive)
            "[Pd]": {"name": "Pd catalyst", "price_per_gram": 45.0, "category": "catalyst"},
            "[AlH3]": {"name": "AlCl3", "price_per_gram": 0.80, "category": "catalyst"},
            "[BH4-].[Na+]": {"name": "NaBH4", "price_per_gram": 1.50, "category": "reducing_agent"},
            
            # Aromatic compounds
            "c1ccccc1": {"name": "Benzene", "price_per_gram": 0.25, "category": "building_block"},
            "Cc1ccccc1": {"name": "Toluene", "price_per_gram": 0.18, "category": "building_block"},
            "c1ccc(Br)cc1": {"name": "Bromobenzene", "price_per_gram": 1.20, "category": "building_block"},
            "c1ccc(N)cc1": {"name": "Aniline", "price_per_gram": 0.85, "category": "building_block"},
            
            # Alkyl compounds
            "CC(=O)Cl": {"name": "Acetyl chloride", "price_per_gram": 0.65, "category": "reagent"},
            "CCBr": {"name": "Ethyl bromide", "price_per_gram": 0.90, "category": "alkylating_agent"},
            "CI": {"name": "Methyl iodide", "price_per_gram": 1.80, "category": "alkylating_agent"},
            
            # Carbonyl compounds
            "CC(=O)C": {"name": "Acetone", "price_per_gram": 0.15, "category": "building_block"},
            "CC(=O)CC(=O)C": {"name": "Acetylacetone", "price_per_gram": 0.95, "category": "building_block"},
            "c1ccccc1C=O": {"name": "Benzaldehyde", "price_per_gram": 0.75, "category": "building_block"},
            
            # Boronic acids (for Suzuki)
            "c1ccc(B(O)O)cc1": {"name": "Phenylboronic acid", "price_per_gram": 3.50, "category": "coupling_reagent"},
            
            # Amines
            "CN": {"name": "Methylamine", "price_per_gram": 1.20, "category": "building_block"},
            "CCN": {"name": "Ethylamine", "price_per_gram": 1.00, "category": "building_block"},
        }
    
    def _save_database(self, db: Dict):
        """Save database to disk."""
        self.cost_db_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cost_db_path, 'w') as f:
            json.dump(db, f, indent=2)
        logger.info(f"Cost database saved to {self.cost_db_path}")
    
    def get_reagent_cost(self, smiles: str) -> Optional[float]:
        """Get cost per gram for a reagent."""
        # Try exact match
        if smiles in self.cost_db:
            return self.cost_db[smiles]["price_per_gram"]
        
        # Try canonical SMILES
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol:
                canonical_smiles = Chem.MolToSmiles(mol)
                if canonical_smiles in self.cost_db:
                    return self.cost_db[canonical_smiles]["price_per_gram"]
        except:
            pass
        
        # Return estimated cost based on complexity
        return self._estimate_cost_by_complexity(smiles)
    
    def _estimate_cost_by_complexity(self, smiles: str) -> float:
        """Estimate cost based on molecular complexity."""
        try:
            mol = Chem.MolFromSmiles(smiles)
            if not mol:
                return 10.0  # Default for unknown
            
            # Cost factors
            mw = Descriptors.MolWt(mol)
            num_atoms = mol.GetNumAtoms()
            num_rings = Descriptors.RingCount(mol)
            num_heteroatoms = Descriptors.NumHeteroatoms(mol)
            rotatable_bonds = Descriptors.NumRotatableBonds(mol)
            
            # Base cost
            base_cost = 0.50
            
            # Complexity penalties
            mw_factor = (mw / 100.0) * 0.20
            atom_factor = (num_atoms / 10.0) * 0.15
            ring_factor = num_rings * 0.30
            hetero_factor = num_heteroatoms * 0.25
            rotation_factor = rotatable_bonds * 0.10
            
            total_cost = base_cost + mw_factor + atom_factor + ring_factor + hetero_factor + rotation_factor
            
            # Cap at reasonable values
            return min(max(0.10, total_cost), 50.0)
            
        except Exception as e:
            logger.debug(f"Error estimating cost for {smiles}: {str(e)}")
            return 10.0
    
    def calculate_reaction_cost(
        self, 
        reactants: List[str], 
        reagents: List[str],
        catalyst: Optional[str] = None,
        solvent: Optional[str] = None,
        target_mass_mg: float = 100.0
    ) -> Dict[str, float]:
        """Calculate total cost for a reaction."""
        costs = {
            "reactants_cost": 0.0,
            "reagents_cost": 0.0,
            "catalyst_cost": 0.0,
            "solvent_cost": 0.0,
            "total_cost": 0.0
        }
        
        # Reactant costs (scale by target mass)
        for smi in reactants:
            cost_per_gram = self.get_reagent_cost(smi)
            # Assume stoichiometric amounts, add 20% excess
            costs["reactants_cost"] += cost_per_gram * (target_mass_mg / 1000.0) * 1.2
        
        # Reagent costs
        for smi in reagents:
            cost_per_gram = self.get_reagent_cost(smi)
            # Reagents typically used in smaller amounts
            costs["reagents_cost"] += cost_per_gram * (target_mass_mg / 1000.0) * 0.5
        
        # Catalyst cost (small amounts but expensive)
        if catalyst:
            # Try to find catalyst in database or estimate
            if any(cat_key in catalyst.lower() for cat_key in ['pd', 'palladium']):
                costs["catalyst_cost"] = 45.0 * 0.01  # 10mg of Pd catalyst
            elif any(cat_key in catalyst.lower() for cat_key in ['pt', 'platinum']):
                costs["catalyst_cost"] = 50.0 * 0.01
            else:
                costs["catalyst_cost"] = 1.0 * 0.05  # Generic catalyst
        
        # Solvent cost (typically cheap, used in bulk)
        if solvent:
            # Rough estimate: 10mL of solvent per 100mg product
            solvent_ml = (target_mass_mg / 100.0) * 10
            solvent_cost_per_ml = 0.05  # Typical solvent cost
            costs["solvent_cost"] = solvent_ml * solvent_cost_per_ml
        
        costs["total_cost"] = sum([
            costs["reactants_cost"],
            costs["reagents_cost"],
            costs["catalyst_cost"],
            costs["solvent_cost"]
        ])
        
        return costs
    
    def add_reagent(self, smiles: str, name: str, price_per_gram: float, category: str):
        """Add a new reagent to the database."""
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol:
                canonical_smiles = Chem.MolToSmiles(mol)
                self.cost_db[canonical_smiles] = {
                    "name": name,
                    "price_per_gram": price_per_gram,
                    "category": category
                }
                self._save_database(self.cost_db)
                logger.info(f"Added reagent: {name} ({canonical_smiles})")
                return True
        except Exception as e:
            logger.error(f"Failed to add reagent: {str(e)}")
        return False
    
    def get_database_stats(self) -> Dict:
        """Get statistics about the cost database."""
        categories = {}
        for data in self.cost_db.values():
            cat = data.get("category", "unknown")
            categories[cat] = categories.get(cat, 0) + 1
        
        return {
            "total_reagents": len(self.cost_db),
            "categories": categories,
            "avg_price": sum(d["price_per_gram"] for d in self.cost_db.values()) / len(self.cost_db)
        }


if __name__ == "__main__":
    # Test the cost database
    logging.basicConfig(level=logging.INFO)
    
    cost_db = CostDatabase()
    
    print("\n" + "="*50)
    print("Cost Database Statistics")
    print("="*50)
    stats = cost_db.get_database_stats()
    print(f"Total Reagents: {stats['total_reagents']}")
    print(f"Average Price: ${stats['avg_price']:.2f}/gram")
    print(f"\nCategories:")
    for cat, count in stats['categories'].items():
        print(f"  {cat}: {count}")
    print("="*50)
    
    # Test cost calculation
    print("\nExample Reaction Cost:")
    costs = cost_db.calculate_reaction_cost(
        reactants=["c1ccccc1", "CC(=O)Cl"],
        reagents=[],
        catalyst="AlCl3",
        solvent="DCM",
        target_mass_mg=100.0
    )
    print(f"Reactants: ${costs['reactants_cost']:.2f}")
    print(f"Catalyst: ${costs['catalyst_cost']:.2f}")
    print(f"Solvent: ${costs['solvent_cost']:.2f}")
    print(f"Total: ${costs['total_cost']:.2f}")
    print("="*50)
