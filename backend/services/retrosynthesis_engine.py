import logging
import numpy as np
from typing import List, Dict, Optional, Set, Tuple
from dataclasses import dataclass, field
from functools import lru_cache
from rdkit import Chem
from rdkit.Chem import AllChem
from data.building_blocks import COMMON_BUILDING_BLOCKS
from services.template_extractor import TemplateExtractor
from services.yield_predictor import YieldPredictor
from services.condition_predictor import ConditionPredictor
import heapq

logger = logging.getLogger(__name__)

REACTION_TEMPLATES = [
    "[C:1](=O)[OH:2].[O:3][C:4]>>[C:1](=O)[O:3][C:4]",
    "[C:1](=O)[NH:2]>>[C:1](=O)Cl.[N:2]",
    "[c:1]-[c:2]>>[c:1]Br.[c:2]B(O)O",
    "[C:1]([OH])[C:2]>>[C:1]=O.[C:2][Mg]Br",
    "[C:1][NH:2][C:3]>>[C:1]=O.[NH2:2][C:3]",
    "[C:1]=[C:2]>>[C:1]=O.[C:2]=[P](c1ccccc1)(c1ccccc1)",
    "[C:1][O:2]>>[C:1]Br.[O:2]",
    "[C:1][C:2](=O)>>[C:1]C=O.[C:2](=O)",
    "[C:1][OH]>>[C:1]=O",
    "[C:1][O:2][C:3]>>[C:1]O.[HO:2][C:3]",
    "[c:1][N:2]>>[c:1]Br.[N:2]",
    "[c:1][C:2]=[C:3]>>[c:1]Br.[C:2]=[C:3]",
    "[C:1]1[C:2][C:3][C:4][C:5][C:6]1>>[C:1]=[C:2].[C:3]=[C:4][C:5]=[C:6]",
    "[C:1](=O)[c:2]>>[C:1](=O)Cl.[c:2]",
    "[N:1]>>[N:1]C(=O)OC(C)(C)C",
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
        
        # Commercial building blocks (simplified)
        self.building_blocks = self._load_building_blocks()
    
    def _load_building_blocks(self) -> Set[str]:
        """Load commercially available building blocks."""
        canonical_blocks: Set[str] = set()
        for smi in COMMON_BUILDING_BLOCKS:
            mol = Chem.MolFromSmiles(smi)
            if mol is None:
                logger.warning(f"invalid_building_block_smiles_skipped: {smi}")
                continue
            canonical_blocks.add(Chem.MolToSmiles(mol))

        logger.info(
            f"loaded_building_blocks: requested={len(COMMON_BUILDING_BLOCKS)} canonical={len(canonical_blocks)}"
        )
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
        """Find possible precursor sets via SMARTS retrosynthetic templates."""
        mol = Chem.MolFromSmiles(smiles)
        if not mol:
            return []

        canonical_smiles = Chem.MolToSmiles(mol)
        cached = self._find_precursors_cached(canonical_smiles)
        if cached:
            return [list(option) for option in cached]
        return [["c1ccccc1", "CCO"]]

    @lru_cache(maxsize=512)
    def _find_precursors_cached(self, canonical_smiles: str) -> Tuple[Tuple[str, ...], ...]:
        """Cached SMARTS retrosynthesis on canonical product SMILES."""
        mol = Chem.MolFromSmiles(canonical_smiles)
        if not mol:
            return tuple()

        extractor_smarts = self._get_extractor_template_smarts()
        extractor_results = self._apply_smarts_templates(
            mol=mol,
            template_smarts=extractor_smarts,
            source_label="templates.pkl",
        )
        if extractor_results:
            return tuple(tuple(option) for option in extractor_results)

        fallback_results = self._apply_smarts_templates(
            mol=mol,
            template_smarts=REACTION_TEMPLATES,
            source_label="fallback_smarts",
        )
        if fallback_results:
            return tuple(tuple(option) for option in fallback_results)

        return tuple()

    def _get_extractor_template_smarts(self) -> List[str]:
        """Build reverse SMARTS templates from TemplateExtractor-loaded templates."""
        templates = self.template_extractor.templates or {}
        smarts_list: List[str] = []

        for template_data in templates.values():
            examples = template_data.get("example_templates", [])
            for template in examples:
                reaction_smarts = template.get("reaction_smarts")
                if reaction_smarts:
                    smarts_list.append(reaction_smarts)
                    continue

                reactant_patterns = template.get("reactant_patterns", [])
                product_patterns = template.get("product_patterns", [])
                if reactant_patterns and product_patterns:
                    reverse_smarts = f"{'.'.join(product_patterns)}>>{'.'.join(reactant_patterns)}"
                    smarts_list.append(reverse_smarts)

        return smarts_list

    def _apply_smarts_templates(
        self,
        mol: Chem.Mol,
        template_smarts: List[str],
        source_label: str,
    ) -> List[List[str]]:
        """Apply a list of retrosynthetic SMARTS templates and collect precursor sets."""
        precursor_sets: List[List[str]] = []
        seen: Set[Tuple[str, ...]] = set()

        for template in template_smarts:
            try:
                rxn = AllChem.ReactionFromSmarts(template)
                if rxn is None:
                    continue
                outcomes = rxn.RunReactants((mol,))
            except Exception as e:
                logger.debug(f"template_application_failed source={source_label} template={template}: {e}")
                continue

            if outcomes:
                logger.info(
                    f"retrosynthesis_template_hit source={source_label} template={template} precursor_sets={len(outcomes)}"
                )

            valid_count = 0
            for product_set in outcomes:
                precursor_smiles: List[str] = []
                valid = True
                for precursor_mol in product_set:
                    if precursor_mol is None:
                        valid = False
                        break
                    smi = Chem.MolToSmiles(precursor_mol)
                    if not Chem.MolFromSmiles(smi):
                        valid = False
                        break
                    precursor_smiles.append(smi)

                if not valid or not precursor_smiles:
                    continue

                canonical_set = tuple(sorted(precursor_smiles))
                if canonical_set in seen:
                    continue

                seen.add(canonical_set)
                precursor_sets.append(list(canonical_set))
                valid_count += 1

            if valid_count:
                logger.info(
                    f"retrosynthesis_template_valid_sets source={source_label} template={template} valid_sets={valid_count}"
                )

        return precursor_sets
    
    def _calculate_node_score(self, smiles: str, depth: int) -> float:
        """Calculate score for a node (higher = better)."""
        score = 100.0
        
        # Penalize depth (fewer steps = better)
        score -= depth * 10
        
        # Check if building block (bonus)
        if self._is_building_block(smiles):
            score += 50
            score += 20
        
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
