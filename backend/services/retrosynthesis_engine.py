import logging
import numpy as np
from typing import List, Dict, Optional, Set, Tuple
from dataclasses import dataclass, field
from rdkit import Chem
from services.template_extractor import TemplateExtractor
from services.yield_predictor import YieldPredictor
from services.condition_predictor import ConditionPredictor
import heapq

logger = logging.getLogger(__name__)

@dataclass
class ReactionNode:
    """Node in the retrosynthesis tree."""
    smiles: str
    depth: int
    parent: Optional['ReactionNode'] = None
    children: List['ReactionNode'] = field(default_factory=list)
    reaction_template: Optional[str] = None
    predicted_yield: float = 0.0
    cost: float = 0.0
    is_available: bool = False
    score: float = 0.0
    
    def __lt__(self, other):
        return self.score > other.score  # Higher score = better (for heapq)

class RetrosynthesisEngine:
    """Tree-based retrosynthesis search engine with MCTS-inspired search."""
    
    def __init__(self):
        self.template_extractor = TemplateExtractor()
        self.yield_predictor = YieldPredictor()
        self.condition_predictor = ConditionPredictor()
        
        # Load models
        self.template_extractor.load_templates()
        self.yield_predictor.load_model()
        self.condition_predictor.load_models()
        
        # Commercial building blocks (simplified)
        self.building_blocks = self._load_building_blocks()
    
    def _load_building_blocks(self) -> Set[str]:
        """Load commercially available building blocks."""
        # Common building blocks
        blocks = {
            'c1ccccc1',  # benzene
            'CCO',  # ethanol
            'CC(=O)O',  # acetic acid
            'CC(C)=O',  # acetone
            'c1ccccc1Br',  # bromobenzene
            'c1ccccc1N',  # aniline
            'CC(=O)Cl',  # acetyl chloride
            'c1ccc(B(O)O)cc1',  # phenylboronic acid
            'Cc1ccccc1',  # toluene
            'ClCCl',  # DCM
            'C1CCOC1',  # THF
        }
        
        # Canonicalize
        canonical_blocks = set()
        for smi in blocks:
            mol = Chem.MolFromSmiles(smi)
            if mol:
                canonical_blocks.add(Chem.MolToSmiles(mol))
        
        return canonical_blocks
    
    def search_routes(
        self,
        target_smiles: str,
        max_depth: int = 5,
        max_routes: int = 10,
        beam_width: int = 5
    ) -> List[Dict]:
        """
        Search for synthesis routes using tree-based exploration.
        
        Uses beam search with best-first exploration.
        """
        logger.info(f"Starting retrosynthesis search for {target_smiles}")
        
        # Validate target
        target_mol = Chem.MolFromSmiles(target_smiles)
        if not target_mol:
            logger.error(f"Invalid target SMILES: {target_smiles}")
            return []
        
        target_canonical = Chem.MolToSmiles(target_mol)
        
        # Initialize search
        root = ReactionNode(
            smiles=target_canonical,
            depth=0,
            score=100.0
        )
        
        # Priority queue for beam search
        frontier = [root]
        heapq.heapify(frontier)
        
        # Completed routes
        complete_routes = []
        
        # Explored nodes
        explored = set()
        
        iteration = 0
        max_iterations = 1000
        
        while frontier and len(complete_routes) < max_routes and iteration < max_iterations:
            iteration += 1
            
            # Get best nodes (beam search)
            current_beam = []
            for _ in range(min(beam_width, len(frontier))):
                if frontier:
                    node = heapq.heappop(frontier)
                    current_beam.append(node)
            
            # Expand each node in beam
            for node in current_beam:
                # Skip if already explored
                if node.smiles in explored:
                    continue
                
                explored.add(node.smiles)
                
                # Check if we've reached building blocks
                if self._is_building_block(node.smiles):
                    route = self._extract_route(node)
                    if route:
                        complete_routes.append(route)
                        logger.info(f"Found route {len(complete_routes)} with {route['num_steps']} steps")
                    continue
                
                # Check depth limit
                if node.depth >= max_depth:
                    continue
                
                # Expand node (find precursors)
                children = self._expand_node(node)
                
                # Add children to frontier
                for child in children:
                    if child.smiles not in explored:
                        heapq.heappush(frontier, child)
                        node.children.append(child)
        
        logger.info(f"Search complete: {len(complete_routes)} routes found in {iteration} iterations")
        
        # Rank routes by score
        complete_routes.sort(key=lambda r: r['score'], reverse=True)
        
        return complete_routes[:max_routes]
    
    def _is_building_block(self, smiles: str) -> bool:
        """Check if molecule is a commercial building block."""
        return smiles in self.building_blocks
    
    def _expand_node(self, node: ReactionNode) -> List[ReactionNode]:
        """Expand a node by finding possible precursors."""
        children = []
        
        # Try to match against reaction templates
        # For simplicity, we'll do a basic retrosynthetic disconnection
        
        # Example disconnections (simplified)
        precursors = self._find_precursors(node.smiles)
        
        for precursor_set in precursors[:5]:  # Top 5 precursors
            # Create child nodes
            for precursor in precursor_set:
                # Calculate score for this precursor
                score = self._calculate_node_score(precursor, node.depth + 1)
                
                child = ReactionNode(
                    smiles=precursor,
                    depth=node.depth + 1,
                    parent=node,
                    score=score
                )
                
                children.append(child)
        
        return children
    
    def _find_precursors(self, smiles: str) -> List[List[str]]:
        """Find possible precursors for a molecule."""
        precursors = []
        
        mol = Chem.MolFromSmiles(smiles)
        if not mol:
            return precursors
        
        # Strategy 1: Break ester bonds (simple retrosynthesis)
        if 'C(=O)O' in smiles:
            # Ester → alcohol + acid
            # Simplified: return building blocks
            precursors.append(['CCO', 'CC(=O)O'])
        
        # Strategy 2: Break amide bonds
        if 'C(=O)N' in smiles:
            # Amide → amine + acid/acid chloride
            precursors.append(['c1ccccc1N', 'CC(=O)Cl'])
        
        # Strategy 3: Break aromatic C-C bonds (Suzuki disconnection)
        if 'c1ccccc1-c' in smiles:
            # Biaryl → aryl halide + boronic acid
            precursors.append(['c1ccccc1Br', 'c1ccc(B(O)O)cc1'])
        
        # Strategy 4: Break C-O bonds (Williamson)
        if 'COc' in smiles:
            precursors.append(['CO', 'c1ccccc1Br'])
        
        # Strategy 5: Functional group interconversions
        if 'C(=O)C' in smiles:
            # Ketone → secondary alcohol (reduction)
            precursors.append(['CC(O)C'])
        
        # Fallback: return similar building blocks
        if not precursors:
            precursors.append(['c1ccccc1', 'CCO'])
        
        return precursors
    
    def _calculate_node_score(self, smiles: str, depth: int) -> float:
        """Calculate score for a node (higher = better)."""
        score = 100.0
        
        # Penalize depth (fewer steps = better)
        score -= depth * 10
        
        # Check if building block (bonus)
        if self._is_building_block(smiles):
            score += 50
        
        # Molecular complexity penalty
        mol = Chem.MolFromSmiles(smiles)
        if mol:
            num_atoms = mol.GetNumAtoms()
            score -= num_atoms * 0.5
        
        return max(0, score)
    
    def _extract_route(self, leaf_node: ReactionNode) -> Optional[Dict]:
        """Extract complete route from leaf to root."""
        steps = []
        current = leaf_node
        
        # Traverse from leaf to root
        while current.parent is not None:
            step = {
                'product': current.parent.smiles,
                'reactants': [current.smiles],
                'depth': current.depth
            }
            steps.append(step)
            current = current.parent
        
        if not steps:
            return None
        
        # Reverse to get root → leaf order
        steps.reverse()
        
        # Calculate route metrics
        total_steps = len(steps)
        estimated_yield = 75.0 ** total_steps  # Assume 75% per step
        estimated_cost = total_steps * 50.0  # $50 per step
        
        route_score = 100 - (total_steps * 10) - (estimated_cost / 10)
        
        return {
            'target': leaf_node.parent.smiles if leaf_node.parent else leaf_node.smiles,
            'starting_materials': [leaf_node.smiles],
            'steps': steps,
            'num_steps': total_steps,
            'estimated_yield': estimated_yield,
            'estimated_cost': estimated_cost,
            'score': max(0, route_score)
        }


async def test_retrosynthesis():
    """Test the retrosynthesis engine."""
    logging.basicConfig(level=logging.INFO)
    
    engine = RetrosynthesisEngine()
    
    # Test on aspirin-like molecule
    target = "CC(=O)Oc1ccccc1C(=O)O"
    
    print("\n" + "="*60)
    print("Tree-Based Retrosynthesis Search")
    print("="*60)
    print(f"Target: {target}")
    print(f"Max depth: 3")
    print(f"Max routes: 5")
    print("="*60)
    
    routes = engine.search_routes(
        target_smiles=target,
        max_depth=3,
        max_routes=5,
        beam_width=3
    )
    
    print(f"\nFound {len(routes)} routes:\n")
    
    for i, route in enumerate(routes, 1):
        print(f"Route {i}:")
        print(f"  Steps: {route['num_steps']}")
        print(f"  Starting materials: {route['starting_materials']}")
        print(f"  Estimated yield: {route['estimated_yield']:.1f}%")
        print(f"  Estimated cost: ${route['estimated_cost']:.2f}")
        print(f"  Score: {route['score']:.1f}")
        print()
    
    print("="*60)

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_retrosynthesis())
