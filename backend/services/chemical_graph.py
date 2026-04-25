"""
Chemical Reaction Graph

Builds a directed graph from reaction database where:
- Nodes = molecules (canonical SMILES)
- Edges = reactions
- Weights = yield, cost, time, constraints
"""

import logging
from typing import Dict, List, Set, Optional, Tuple
from collections import defaultdict
import networkx as nx
from rdkit import Chem

logger = logging.getLogger(__name__)


def canonicalize_smiles(smiles: str) -> Optional[str]:
    """Canonicalize a SMILES string using RDKit.

    Returns the canonical SMILES or None if the input is invalid.
    """
    if not smiles or not smiles.strip():
        return None
    mol = Chem.MolFromSmiles(smiles.strip())
    return Chem.MolToSmiles(mol) if mol else None


class ChemicalGraph:
    """
    Directed graph representation of chemical reaction space.
    
    Enables graph-based search algorithms (MCTS, A*, Dijkstra) for
    optimal synthesis route discovery.

    All SMILES are canonicalized before insertion/lookup so that
    equivalent representations (e.g. "OCC", "CCO") map to the same node.
    """
    
    def __init__(self):
        self.graph = nx.DiGraph()  # Directed graph: reactants → products
        self.molecule_to_reactions = defaultdict(list)  # Fast lookup
        self.reaction_count = 0
        self.molecule_count = 0
        
    def build_from_reactions(self, reactions: List[Dict]) -> None:
        """
        Build graph from reaction database.
        
        Args:
            reactions: List of reaction dicts with reactants, products, conditions
        """
        logger.info(f"building_chemical_graph: {len(reactions)} reactions")
        skipped = 0
        
        for idx, rxn in enumerate(reactions):
            try:
                raw_reactants = rxn.get('reactants', [])
                raw_products = rxn.get('products', [])
                
                if not raw_reactants or not raw_products:
                    continue
                
                # Canonicalize all SMILES
                reactants = []
                for smi in raw_reactants:
                    canon = canonicalize_smiles(smi)
                    if canon:
                        reactants.append(canon)
                    else:
                        logger.debug(f"skipping_invalid_reactant: '{smi}' in rxn_{idx}")
                
                products = []
                for smi in raw_products:
                    canon = canonicalize_smiles(smi)
                    if canon:
                        products.append(canon)
                    else:
                        logger.debug(f"skipping_invalid_product: '{smi}' in rxn_{idx}")
                
                if not reactants or not products:
                    skipped += 1
                    continue
                
                # Add nodes (molecules)
                for mol in reactants + products:
                    if not self.graph.has_node(mol):
                        self.graph.add_node(mol, smiles=mol)
                        self.molecule_count += 1
                
                # Add edges (reactions) from each product to reactants
                # This is RETROSYNTHESIS direction: product → reactants
                for product in products:
                    for reactant_set in [tuple(reactants)]:  # Group reactants
                        # Create edge with reaction metadata
                        edge_data = {
                            'reaction_id': f"rxn_{idx}",
                            'reactants': reactants,
                            'products': products,
                            'yield_percent': rxn.get('yield', 75.0),
                            'cost': rxn.get('cost', 100.0),
                            'time_hours': rxn.get('time_hours', 4.0),
                            'temperature_c': rxn.get('conditions', {}).get('temperature', 25.0),
                            'catalyst': rxn.get('conditions', {}).get('catalyst', ''),
                            'solvent': rxn.get('conditions', {}).get('solvent', 'THF'),
                            'reaction_type': rxn.get('reaction_type', 'unknown')
                        }
                        
                        # Add edge for each reactant (retrosynthesis)
                        for reactant in reactants:
                            self.graph.add_edge(
                                product,
                                reactant,
                                **edge_data
                            )
                        
                        # Store reaction lookup
                        self.molecule_to_reactions[product].append(edge_data)
                        self.reaction_count += 1
                
            except Exception as e:
                logger.error(f"failed_to_add_reaction_{idx}: {str(e)}")
                continue
        
        if skipped:
            logger.warning(f"skipped_{skipped}_reactions with invalid SMILES")
        
        logger.info(
            f"chemical_graph_built: {self.molecule_count} molecules, "
            f"{self.reaction_count} reaction edges"
        )
    
    def get_predecessors(self, molecule: str) -> List[str]:
        """
        Get molecules that can produce this molecule (retrosynthesis).
        
        Args:
            molecule: Product SMILES (will be canonicalized)
            
        Returns:
            List of reactant SMILES
        """
        canon = canonicalize_smiles(molecule) or molecule
        if not self.graph.has_node(canon):
            return []
        
        return list(self.graph.predecessors(canon))
    
    def get_reactions_for_product(self, product: str) -> List[Dict]:
        """
        Get all reactions that produce this molecule.
        
        Args:
            product: Product SMILES (will be canonicalized)
            
        Returns:
            List of reaction metadata dicts
        """
        canon = canonicalize_smiles(product) or product
        return self.molecule_to_reactions.get(canon, [])
    
    def get_reaction_edge(self, product: str, reactant: str) -> Optional[Dict]:
        """
        Get reaction metadata for specific product→reactant edge.
        
        Args:
            product: Product SMILES
            reactant: Reactant SMILES
            
        Returns:
            Reaction metadata dict or None
        """
        canon_p = canonicalize_smiles(product) or product
        canon_r = canonicalize_smiles(reactant) or reactant
        if self.graph.has_edge(canon_p, canon_r):
            return self.graph.edges[canon_p, canon_r]
        return None
    
    def find_commercial_building_blocks(
        self,
        max_price_per_g: float = 10.0
    ) -> Set[str]:
        """
        Identify commercially available starting materials.
        
        Heuristic: Molecules with no predecessors (terminal nodes) or low cost.
        
        Args:
            max_price_per_g: Maximum price threshold
            
        Returns:
            Set of SMILES for commercial building blocks
        """
        building_blocks = set()
        
        for node in self.graph.nodes():
            # Check if terminal node (no predecessors = commercial)
            if self.graph.in_degree(node) == 0:
                building_blocks.add(node)
            
            # Also check cost (if available)
            # This is a placeholder - real implementation would query cost DB
        
        logger.info(f"found {len(building_blocks)} commercial building blocks")
        return building_blocks
    
    def get_path_cost(self, path: List[str]) -> Tuple[float, float, float]:
        """
        Calculate cumulative cost for a synthesis path.
        
        Args:
            path: List of molecules in order (product → ... → starting material).
                  SMILES will be canonicalized before lookup.
            
        Returns:
            Tuple of (total_cost, total_time, overall_yield)
        """
        total_cost = 0.0
        total_time = 0.0
        overall_yield = 100.0
        
        for i in range(len(path) - 1):
            product = canonicalize_smiles(path[i]) or path[i]
            reactant = canonicalize_smiles(path[i + 1]) or path[i + 1]
            
            edge_data = self.get_reaction_edge(product, reactant)
            if edge_data:
                total_cost += edge_data.get('cost', 100.0)
                total_time += edge_data.get('time_hours', 4.0)
                overall_yield *= (edge_data.get('yield_percent', 75.0) / 100.0)
        
        return total_cost, total_time, overall_yield
    
    def is_commercial(self, molecule: str) -> bool:
        """Check if molecule is a commercial building block."""
        canon = canonicalize_smiles(molecule) or molecule
        return self.graph.in_degree(canon) == 0 if self.graph.has_node(canon) else False
    
    def get_graph_stats(self) -> Dict:
        """Get graph statistics for analysis."""
        return {
            'num_molecules': self.graph.number_of_nodes(),
            'num_reactions': self.graph.number_of_edges(),
            'avg_out_degree': sum(d for _, d in self.graph.out_degree()) / max(self.graph.number_of_nodes(), 1),
            'avg_in_degree': sum(d for _, d in self.graph.in_degree()) / max(self.graph.number_of_nodes(), 1),
            'is_directed': self.graph.is_directed(),
            'is_dag': nx.is_directed_acyclic_graph(self.graph)
        }


# Demo/testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test with mock reactions using non-canonical SMILES
    test_reactions = [
        {
            'reactants': ['c1ccccc1', 'Cl'],
            'products': ['Clc1ccccc1'],
            'yield': 85.0,
            'cost': 50.0,
            'time_hours': 3.0,
            'reaction_type': 'halogenation'
        },
        {
            'reactants': ['Clc1ccccc1', '[Na]O'],
            'products': ['Oc1ccccc1'],
            'yield': 90.0,
            'cost': 75.0,
            'time_hours': 5.0,
            'reaction_type': 'substitution'
        },
    ]
    
    print("\n=== Building Chemical Graph (with canonicalization) ===")
    graph = ChemicalGraph()
    graph.build_from_reactions(test_reactions)
    
    print(f"\nGraph Stats: {graph.get_graph_stats()}")
    
    # Test canonicalization: OCC and CCO should resolve to same node
    print(f"\ncanon('OCC') = {canonicalize_smiles('OCC')}")
    print(f"canon('CCO') = {canonicalize_smiles('CCO')}")
    print(f"canon('C(O)C') = {canonicalize_smiles('C(O)C')}")
    
    print(f"\nCommercial building blocks: {graph.find_commercial_building_blocks()}")
    
    print("\n✓ Chemical Graph Test Complete")
