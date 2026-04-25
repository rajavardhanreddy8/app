import logging
import functools
import heapq
from typing import List, Dict, Optional, Set, Tuple
from dataclasses import dataclass, field
from rdkit import Chem
from rdkit.Chem import AllChem, Descriptors

from data.building_blocks import is_building_block_smiles, CANONICAL_BUILDING_BLOCKS
from services.template_extractor import TemplateExtractor
from services.yield_predictor import YieldPredictor
from services.condition_predictor import ConditionPredictor

logger = logging.getLogger(__name__)

# \u2500\u2500 REACTION TEMPLATES \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
REACTION_TEMPLATES = [
    # Group 1 — Carbonyl disconnections
    "[C:1](=O)[O:2][C:3]>>[C:1](=O)[OH].[O:2][C:3]",
    "[C:1](=O)[O:2][C:3]>>[C:1](=O)Cl.[O:2][C:3]",
    "[C:1](=O)[N:2]>>[C:1](=O)[OH].[N:2]",
    "[C:1](=O)[N:2]>>[C:1](=O)Cl.[N:2]",
    "[C:1](=O)[c:2]>>[C:1](=O)Cl.[c:2][H]",
    "[CH1:1]=O>>[CH2:1][OH]",
    "[C:1](=O)[C:2]>>[C:1]([OH])[C:2]",
    "[C:1](=O)[OH]>>[CH2:1][OH]",
    "[C:1](=O)[OH]>>[CH1:1]=O",
    "[C:1](=O)[O:2][C:3](=O)>>[C:1](=O)[OH].[C:3](=O)[OH]",

    # Group 2 — C-N bond formations
    "[C:1][N:2][C:3]>>[C:1]=O.[H][N:2][C:3]",
    "[c:1][N:2]>>[c:1]Br.[N:2][H]",
    "[c:1][N:2]>>[c:1]I.[N:2][H]",
    "[c:1]C(=O)[N:2]>>[c:1]C(=O)O.[N:2][H]",
    "[C:1][N:2]([C:3])[C:4]>>[C:1]Br.[H][N:2]([C:3])[C:4]",
    "[c:1]S(=O)(=O)[N:2]>>[c:1]S(=O)(=O)Cl.[N:2][H]",
    "[C:1]S(=O)(=O)[N:2]>>[C:1]S(=O)(=O)Cl.[N:2][H]",
    "[N:1]C(=N[N:3])[N:2]>>[N:1]C(=S)[N:2].[N:3]",
    "[N:1][C:2](=O)[O:3][C:4]>>[N:1].[C:4][O:3]C(=O)Cl",
    "[c:1][N:2][C:3](=O)[C:4]>>[c:1][N:2].[C:4][C:3](=O)Cl",

    # Group 3 — C-C bond formations
    "[c:1]-[c:2]>>[c:1]Br.[c:2]B(O)O",
    "[c:1]-[c:2]>>[c:1]I.[c:2]B(O)O",
    "[c:1][C:2]=[C:3]>>[c:1]Br.[C:2]=[C:3]",
    "[C:1]([OH])([C:2])[C:3]>>[C:1](=O)[C:2].[C:3][MgBr]",
    "[CH1:1]([OH])[C:2]>>[CH1:1]=O.[C:2][MgBr]",
    "[C:1]=[C:2]>>[C:1]=O.[C:2]=[P+](c1ccccc1)(c1ccccc1)",
    "[C:1][C:2]([OH])[C:3]=O>>[C:1]C=O.[C:3]=O",
    "[C:1]=[C:2]C(=O)>>[C:1]=O.[C:2]C(=O)",
    "[C:1]#[C:2]-[c:3]>>[C:1]#[C:2].[c:3]Br",
    "[C:1]#[C:2]-[C:3]>>[C:1]#[C:2].[C:3]Br",

    # Group 4 — C-O bond formations
    "[c:1][O:2][C:3]>>[c:1][O:2][H].[C:3]Br",
    "[C:1][O:2][C:3]>>[C:1][OH].[C:3][OH]",
    "[C:1]([OH])[C:2][O:3][C:4]>>[C:1]1O[C:2]1.[O:3][C:4]",
    "[c:1][O:2][C:3]>>[c:1]O.[C:3]Br",
    "[CH1:1]([O:2][C:3])([O:4][C:5])>>[CH1:1]=O.[O:2][C:3].[O:4][C:5]",
    "[C:1][O:2][C:3]>>[C:1][OH].[C:3]Br",
    "[C:1](=O)[O:2][c:3]>>[C:1](=O)Cl.[c:3][OH]",
    "[C:1][O:2]S(=O)(=O)[C:3]>>[C:1][OH].[C:3]S(=O)(=O)Cl",
    "[C:1]([OH])[C:2][N:3]>>[C:1]1O[C:2]1.[N:3]",
    "[CH1:1]([O:2][C:3])([O:4][C:3])>>[CH1:1]=O.[OH][C:3][C:3][OH]",

    # Group 5 — Aromatic/heterocyclic
    "[c:1][N+](=O)[O-]>>[c:1][H]",
    "[c:1]Cl>>[c:1][H]",
    "[c:1]Br>>[c:1][H]",
    "[C:1]1[C:2]=[C:3][C:4][C:5][C:6]1>>[C:1]=[C:2].[C:3]=[C:4][C:5]=[C:6]",
    "[c:1]1[n:2][c:3][n:4]c2ccccc12>>[c:3](=O)[OH].[n:2]c1ccccc1[n:4]",
    "[c:1]F>>[c:1][H]",
    "[c:1]I>>[c:1][H]",
    "[c:1]C#N>>[c:1]Br",
    "[c:1]C(=O)[OH]>>[c:1]Br",
    "[c:1]S(=O)(=O)[OH]>>[c:1][H]",

    # Group 6 — Protecting group removal
    "[N:1]C(=O)OC(C)(C)C>>[N:1][H]",
    "[N:1]C(=O)OCc1ccccc1>>[N:1][H]",
    "[C:1]OC1CCCCO1>>[C:1][OH]",
    "[C:1]O[Si]([C:2])([C:3])[C:4]>>[C:1][OH]",
    "[N:1][H]>>[N:1]C(=O)OC(C)(C)C",
    "[C:1]([O:2]1)[C:3]([O:4]1)CC(C)(C)>>[C:1][O:2][H].[C:3][O:4][H]",
    "[O:1]Cc1ccccc1>>[O:1][H]",
    "[N:1]Cc1ccccc1>>[N:1][H]",
    "[C:1](=O)OC(C)(C)C>>[C:1](=O)[OH]",
    "[C:1](=O)OCc1ccccc1>>[C:1](=O)[OH]",

    # Group 7 — Reduction/oxidation
    "[N:1][H2]>>[N+:1](=O)[O-]",
    "[c:1][NH2]>>[c:1][N+](=O)[O-]",
    "[C:1](=O)[C:2]>>[C:1]([OH])[C:2]",
    "[CH1:1]=O>>[CH2:1][OH]",
    "[c:1][CH2:2][NH2]>>[c:1]C#N",
    "[C:1]#[N:2]>>[C:1](=O)[N:2]",
    "[C:1]=[C:2]>>[CH1:1]([C:2])Br",
    "[CH2:1][OH]>>[C:1](=O)[OH]",
    "[C:1][OH]>>[C:1]=O",
    "[C:1]#[C:2]>>[C:1]=[C:2]"
]

# Human-readable names aligned 1-to-1 with REACTION_TEMPLATES indices
_TEMPLATE_NAMES = [
    # Group 1 — Carbonyl (0-9)
    "Ester Hydrolysis", "Acyl Chloride Formation", "Amide Hydrolysis", "Amide from Acid Chloride",
    "Aromatic Acylation", "Aldehyde Oxidation", "Ketone Reduction", "Alcohol Oxidation",
    "Carboxylic Acid Reduction", "Anhydride Hydrolysis",
    # Group 2 — C-N (10-19)
    "Reductive Amination", "Buchwald-Hartwig (Ar-Br)", "Buchwald-Hartwig (Ar-I)",
    "Amide Coupling", "N-Alkylation", "Sulfonamide Formation", "Sulfonamide from Sulfonyl Chloride",
    "Guanidine Synthesis", "Carbamate Formation", "N-Acylation",
    # Group 3 — C-C (20-29)
    "Suzuki Coupling (Ar-Br)", "Suzuki Coupling (Ar-I)", "Heck Reaction",
    "Grignard Addition", "Grignard Aldehyde Addition", "Wittig Olefination",
    "Aldol Condensation", "Michael Addition", "Sonogashira (Ar-Br)", "Sonogashira (Ar-I)",
    # Group 4 — C-O (30-39)
    "O-Alkylation (Ar-Br)", "Ether Synthesis", "Epoxide Ring Opening",
    "O-Alkylation", "Acetal Hydrolysis", "Ether from Alcohol-Alkyl Bromide",
    "Ester from Acid Chloride-Phenol", "Sulfonate Ester Formation", "Amino Alcohol Cyclization", "Acetal Cyclization",
    # Group 5 — Aromatic (40-49)
    "Nitration", "Chlorination", "Bromination", "Diels-Alder",
    "Purine Ring Synthesis", "Fluorination", "Iodination", "Cyanation",
    "Carboxylation", "Sulfonation",
    # Group 6 — Protecting groups (50-59)
    "Boc Deprotection", "Cbz Deprotection", "THP Deprotection", "TBS Deprotection",
    "Boc Protection", "Acetonide Deprotection", "Benzyl Ether Cleavage", "Benzyl Amine Cleavage",
    "Boc Ester Cleavage", "Cbz Ester Cleavage",
    # Group 7 — Redox (60-69)
    "Nitro Reduction", "Aromatic Nitro Reduction", "Carbonyl Reduction",
    "Aldehyde Reduction", "Nitrile Hydrogenation", "Beckmann Rearrangement",
    "Alkene Hydrobromination", "Primary Alcohol Oxidation", "Secondary Alcohol Oxidation", "Alkyne Reduction",
]

def _compile_templates():
    compiled = []
    for i, smarts in enumerate(REACTION_TEMPLATES):
        try:
            rxn = AllChem.ReactionFromSmarts(smarts)
            if rxn is not None:
                name = _TEMPLATE_NAMES[i] if i < len(_TEMPLATE_NAMES) else f"Transformation (rule_{i})"
                priority = i // 10  # grouped priority
                compiled.append((rxn, name, priority))
        except Exception:
            pass
    return compiled

COMPILED_TEMPLATES = _compile_templates()

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
        
        # Pre-compiled templates from module loading
        self.compiled_templates = COMPILED_TEMPLATES
        
        # Commercial building blocks
        self.building_blocks = CANONICAL_BUILDING_BLOCKS
    
    def _is_simple_molecule(self, smiles: str) -> bool:
        """Auto-terminate molecules too simple to need further disconnection."""
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return False
            num_heavy = mol.GetNumHeavyAtoms()
            num_rings = Descriptors.RingCount(mol)
            # Simple aliphatics under 6 heavy atoms are always commercial
            if num_heavy <= 6 and num_rings == 0:
                return True
            # Single-ring aromatics with one substituent are always commercial
            if num_rings == 1 and num_heavy <= 10:
                return True
            return False
        except Exception:
            return False

    def _is_building_block(self, smiles: str, target_smiles: str = "") -> bool:
        """Check if all molecules in a state are commercial building blocks
        or simple enough to be considered commercially available.
        
        The original target molecule is never auto-terminated so the engine
        is forced to find at least one retrosynthetic step.
        """
        if not smiles:
            return False
        for s in smiles.split('.'):
            # Never auto-terminate the original target itself
            if target_smiles and s == target_smiles:
                return False
            if is_building_block_smiles(s):
                continue
            if self._is_simple_molecule(s):
                continue
            return False
        return True

    @functools.lru_cache(maxsize=1024)
    def _find_precursors(self, smiles: str) -> List[str]:
        """Find possible precursor states. Expands one non-building-block molecule at a time."""
        molecules = smiles.split('.')
        current_target = getattr(self, '_current_target', '')
        # Find the first molecule that is not a building block.
        # The original search target is always treated as non-building-block
        # so templates are applied to it even if it's in the catalog.
        target_idx = -1
        for i, s in enumerate(molecules):
            is_search_target = (s == current_target)
            if is_search_target or not is_building_block_smiles(s):
                target_idx = i
                break
                
        if target_idx == -1:
            return [] # All are building blocks
            
        target_smi = molecules[target_idx]
        mol = Chem.MolFromSmiles(target_smi)
        if not mol:
            return []
            
        precursor_states = []
        seen_states = set()
        
        for rxn, name, priority in self.compiled_templates:
            try:
                products_sets = rxn.RunReactants((mol,))
                for product_set in products_sets:
                    reactant_smiles = []
                    valid_products = True
                    for p in product_set:
                        try:
                            Chem.SanitizeMol(p)
                            # Bug 5 fix: strip atom-map numbers so SMILES renders in RDKit-JS
                            rw = Chem.RWMol(p)
                            for atom in rw.GetAtoms():
                                atom.SetAtomMapNum(0)
                            smi = Chem.MolToSmiles(rw)
                            if not smi:
                                valid_products = False
                                break
                            reactant_smiles.append(smi)
                        except Exception:
                            valid_products = False
                            break
                            
                    if valid_products and reactant_smiles:
                        # Reconstruct the state: replace target with new reactants
                        new_state_mols = molecules[:target_idx] + reactant_smiles + molecules[target_idx+1:]
                        
                        # Canonicalize the entire state to deduplicate
                        canonical_mols = []
                        valid_state = True
                        for m_str in new_state_mols:
                            m = Chem.MolFromSmiles(m_str)
                            if m:
                                canonical_mols.append(Chem.MolToSmiles(m))
                            else:
                                valid_state = False
                                break
                                
                        if valid_state:
                            state_key = frozenset(canonical_mols)
                            if state_key not in seen_states:
                                seen_states.add(state_key)
                                state_str = '.'.join(sorted(canonical_mols))
                                # store name alongside for extraction
                                precursor_states.append((state_str, priority, name))
            except Exception:
                continue
                
        # Sort by priority (lower number = higher priority)
        precursor_states.sort(key=lambda x: x[1])
        # Return top 10 precursor sets maximum — now as (smiles, reaction_name) tuples
        return [(state, rxn_name) for state, prio, rxn_name in precursor_states][:10]

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
        
        # Store target so _is_building_block can exclude it
        self._current_target = target_canonical
        
        frontier = [root]
        heapq.heapify(frontier)
        complete_routes = []
        partial_candidates = []  # FIX 3: track deepest nodes for partial routes
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
                if node.smiles in explored:
                    continue
                explored.add(node.smiles)
                
                if self._is_building_block(node.smiles, target_smiles=target_canonical):
                    route = self._extract_route(node)
                    if route:
                        complete_routes.append(route)
                    continue
                
                if node.depth >= max_depth:
                    # FIX 3: remember as partial candidate
                    if node.depth > 0:
                        partial_candidates.append(node)
                    continue
                
                children = self._expand_node(node)
                for child in children:
                    if child.smiles not in explored:
                        heapq.heappush(frontier, child)
                        node.children.append(child)
                
                # Also save deepest explored nodes as partial candidates
                if not children and node.depth > 0:
                    partial_candidates.append(node)
        
        # ── FIX 3: If no complete routes, accept partial routes ───────────
        if not complete_routes and partial_candidates:
            for node in partial_candidates:
                # Accept partial routes where leaf molecules have MW < 200
                # and are not the original target
                if node.smiles == target_canonical:
                    continue
                leaf_ok = True
                for frag in node.smiles.split('.'):
                    fmol = Chem.MolFromSmiles(frag)
                    if fmol is None:
                        leaf_ok = False
                        break
                    if Descriptors.ExactMolWt(fmol) > 200:
                        leaf_ok = False
                        break
                if leaf_ok:
                    route = self._extract_route(node)
                    if route:
                        route['partial'] = True
                        complete_routes.append(route)
                if len(complete_routes) >= max_routes:
                    break
        
        complete_routes.sort(key=lambda r: r['score'], reverse=True)
        return complete_routes[:max_routes]

    def _expand_node(self, node: ReactionNode) -> List[ReactionNode]:
        """Expand a node by finding possible precursor states."""
        children = []
        precursors = self._find_precursors(node.smiles)
        target = getattr(self, '_current_target', '')
        for item in precursors[:5]:
            # _find_precursors now returns (smiles, reaction_name) tuples
            if isinstance(item, tuple):
                precursor_state, rxn_name = item
            else:
                precursor_state, rxn_name = item, "Retrosynthetic Disconnection"
            score = self._calculate_node_score(precursor_state, node.depth + 1, target)
            child = ReactionNode(
                smiles=precursor_state, depth=node.depth+1, parent=node, score=score,
                reaction_template=rxn_name
            )
            children.append(child)
        return children

    def _calculate_node_score(self, smiles: str, depth: int, target_smiles: str = "") -> float:
        """Calculate score for a node (higher = better)."""
        score = 100.0 - (depth * 10)
        if self._is_building_block(smiles, target_smiles=target_smiles):
            score += 50
        num_atoms = 0
        for s in smiles.split('.'):
            mol = Chem.MolFromSmiles(s)
            if mol: num_atoms += mol.GetNumAtoms()
        score -= num_atoms * 0.5
        return max(0, score)

    def _extract_route(self, leaf_node: ReactionNode) -> Optional[Dict]:
        """Extract complete route from leaf to root."""
        steps = []
        current = leaf_node
        while current.parent is not None:
            # Bug 3 fix: pull reaction_type from the node's reaction_template
            rxn_type = (current.reaction_template or "Retrosynthetic Disconnection").strip()
            if not rxn_type or rxn_type.lower() == "unknown":
                rxn_type = "Retrosynthetic Disconnection"

            # Bug 2 fix: filter out bare numeric reactants
            raw_reactants = current.smiles.split('.')
            clean_reactants = [r for r in raw_reactants if r.strip() and not r.strip().isdigit()]

            steps.append({
                'product': current.parent.smiles,
                'reactants': clean_reactants,
                'reaction_type': rxn_type,
                'depth': current.depth,
            })
            current = current.parent
        if not steps:
            return None
        steps.reverse()
        total_steps = len(steps)
        route_score = 100 - (total_steps * 10)

        # Bug 2 fix: filter numeric bare strings from starting materials too
        raw_sm = leaf_node.smiles.split('.')
        clean_sm = [s for s in raw_sm if s.strip() and not s.strip().isdigit()]

        return {
            'target': leaf_node.parent.smiles if leaf_node.parent else leaf_node.smiles,
            'starting_materials': clean_sm,
            'steps': steps,
            'num_steps': total_steps,
            'score': max(0, route_score),
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
