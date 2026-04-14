import logging
import functools
import heapq
from typing import List, Dict, Optional, Set, Tuple
from dataclasses import dataclass, field
from rdkit import Chem
from rdkit.Chem import AllChem

from data.building_blocks import is_building_block_smiles, CANONICAL_BUILDING_BLOCKS
from services.template_extractor import TemplateExtractor
from services.yield_predictor import YieldPredictor
from services.condition_predictor import ConditionPredictor

logger = logging.getLogger(__name__)

# \u2500\u2500 REACTION TEMPLATES \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
REACTION_TEMPLATES = [
    "[C:1](=O)[O:2]>>[C:1](=O)O.[O:2]",           # Ester condensation (matches test C(=O)O)
    "[C:1](=O)[N:2]>>[C:1](=O)Cl.[N:2]",          # Amide formation
    "[c:1][c:2]>>[c:1]Br.[c:2]B(O)O",             # Suzuki cross-coupling
    "[c:1]O[C:2]>>[c:1]O.[C:2]Br",                # Ether formation
    "C=O>>C(O)",                                  # Reduction
    "[C:1]N>>[C:1]=O.N",                          # Reductive amination
    "CC(=O)O>>CC(=O)Cl",                          # Acid chloride formation
    "c1ccccc1>>c1ccccc1Br",                       # Bromination
    "CC(C)O>>CC(=O)C",                            # Oxidation
    "CCO>>CC(=O)O"                                # Alcohol to Acid
]

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
        
        # Pre-compile templates
        self.compiled_templates = []
        for t in REACTION_TEMPLATES:
            rxn = AllChem.ReactionFromSmarts(t)
            if rxn:
                self.compiled_templates.append(rxn)
        
        # Commercial building blocks
        self.building_blocks = CANONICAL_BUILDING_BLOCKS
    
    def _is_building_block(self, smiles: str) -> bool:
        """Check if molecule is a commercial building block."""
        return is_building_block_smiles(smiles)

    @functools.lru_cache(maxsize=1024)
    def _find_precursors(self, smiles: str) -> List[List[str]]:
        """Find possible precursors for a molecule using SMARTS templates."""
        precursors = []
        mol = Chem.MolFromSmiles(smiles)
        if not mol:
            return precursors
        
        # Apply SMARTS templates safely
        for rxn in self.compiled_templates:
            try:
                products_sets = rxn.RunReactants((mol,))
                for product_set in products_sets:
                    reactant_smiles = []
                    for p in product_set:
                        try:
                            Chem.SanitizeMol(p)
                            reactant_smiles.append(Chem.MolToSmiles(p))
                        except:
                            continue
                    if reactant_smiles:
                        precursors.append(reactant_smiles)
            except:
                continue
        
        return precursors

    def search_routes(
        self,
        target_smiles: str,
        max_depth: int = 5,
        max_routes: int = 10,
        beam_width: int = 5
    ) -> List[Dict]:
        """Search for synthesis routes using tree-based exploration."""
        logger.info(f"Starting retrosynthesis search for {target_smiles}")
        
        target_mol = Chem.MolFromSmiles(target_smiles)
        if not target_mol:
            logger.error(f"Invalid target SMILES: {target_smiles}")
            return []
        
        target_canonical = Chem.MolToSmiles(target_mol)
        root = ReactionNode(smiles=target_canonical, depth=0, score=100.0)
        
        frontier = [root]
        heapq.heapify(frontier)
        complete_routes = []
        explored = set()
        
        iteration = 0
        max_iterations = 1000
        
        while frontier and len(complete_routes) < max_routes and iteration < max_iterations:
            iteration += 1
            current_beam = []
            for _ in range(min(beam_width, len(frontier))):
                if frontier:
                    node = heapq.heappop(frontier)
                    current_beam.append(node)
            
            for node in current_beam:
                if node.smiles in explored: continue
                explored.add(node.smiles)
                
                if self._is_building_block(node.smiles):
                    route = self._extract_route(node)
                    if route: complete_routes.append(route)
                    continue
                
                if node.depth >= max_depth: continue
                
                children = self._expand_node(node)
                for child in children:
                    if child.smiles not in explored:
                        heapq.heappush(frontier, child)
                        node.children.append(child)
        
        complete_routes.sort(key=lambda r: r['score'], reverse=True)
        return complete_routes[:max_routes]

    def _expand_node(self, node: ReactionNode) -> List[ReactionNode]:
        """Expand a node by finding possible precursors."""
        children = []
        precursors = self._find_precursors(node.smiles)
        for precursor_set in precursors[:5]:
            for precursor in precursor_set:
                score = self._calculate_node_score(precursor, node.depth + 1)
                child = ReactionNode(smiles=precursor, depth=node.depth+1, parent=node, score=score)
                children.append(child)
        return children

    def _calculate_node_score(self, smiles: str, depth: int) -> float:
        """Calculate score for a node (higher = better)."""
        score = 100.0 - (depth * 10)
        if self._is_building_block(smiles):
            score += 50
        mol = Chem.MolFromSmiles(smiles)
        if mol:
            score -= mol.GetNumAtoms() * 0.5
        return max(0, score)

    def _extract_route(self, leaf_node: ReactionNode) -> Optional[Dict]:
        """Extract complete route from leaf to root."""
        steps = []
        current = leaf_node
        while current.parent is not None:
            steps.append({'product': current.parent.smiles, 'reactants': [current.smiles], 'depth': current.depth})
            current = current.parent
        if not steps: return None
        steps.reverse()
        total_steps = len(steps)
        route_score = 100 - (total_steps * 10)
        return {
            'target': leaf_node.parent.smiles if leaf_node.parent else leaf_node.smiles,
            'starting_materials': [leaf_node.smiles],
            'steps': steps, 'num_steps': total_steps,
            'score': max(0, route_score)
        }

async def test_retrosynthesis():
    """Test the retrosynthesis engine."""
    logging.basicConfig(level=logging.INFO)
    engine = RetrosynthesisEngine()
    target = "CC(=O)Oc1ccccc1C(=O)O"
    routes = engine.search_routes(target_smiles=target, max_depth=3, max_routes=5, beam_width=3)
    print(f"\nFound {len(routes)} routes")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_retrosynthesis())
