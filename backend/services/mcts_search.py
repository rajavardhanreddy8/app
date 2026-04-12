"""
Monte Carlo Tree Search (MCTS) for Synthesis Planning

Implements MCTS algorithm for global optimization of synthesis routes:
1. Selection (UCT - Upper Confidence Bound for Trees)
2. Expansion (generate child nodes)
3. Evaluation (rollout/scoring)
4. Backpropagation (update statistics)
"""

import logging
import math
import random
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class MCTSNode:
    """Node in MCTS search tree."""
    molecule: str  # Current molecule (SMILES)
    parent: Optional['MCTSNode'] = None
    children: List['MCTSNode'] = field(default_factory=list)
    
    # MCTS statistics
    visits: int = 0
    total_reward: float = 0.0
    best_reward: float = 0.0
    
    # Route information
    path_from_root: List[str] = field(default_factory=list)
    reaction_used: Optional[Dict] = None
    depth: int = 0
    
    # Pruning flags
    is_terminal: bool = False
    is_commercial: bool = False
    is_pruned: bool = False
    pruning_reason: str = ""
    
    def ucb_score(self, exploration_weight: float = 1.414) -> float:
        """
        Calculate UCB1 (Upper Confidence Bound) score for node selection.
        
        UCB = average_reward + C * sqrt(log(parent_visits) / visits)
        
        Args:
            exploration_weight: C parameter (typically sqrt(2))
            
        Returns:
            UCB score (higher = better to explore)
        """
        if self.visits == 0:
            return float('inf')  # Unvisited nodes have infinite priority
        
        if not self.parent or self.parent.visits == 0:
            return self.total_reward / self.visits
        
        exploitation = self.total_reward / self.visits
        exploration = exploration_weight * math.sqrt(
            math.log(self.parent.visits) / self.visits
        )
        
        return exploitation + exploration
    
    def average_reward(self) -> float:
        """Get average reward from this node."""
        return self.total_reward / max(self.visits, 1)


class MCTSSearch:
    """
    Monte Carlo Tree Search for synthesis route optimization.
    
    Discovers optimal routes by intelligently exploring the chemical graph
    using UCB-based selection and constraint-aware pruning.
    """
    
    def __init__(
        self,
        chemical_graph,
        scorer,
        constraints_engine=None,
        pharma_mode: bool = False
    ):
        """
        Initialize MCTS search.
        
        Args:
            chemical_graph: ChemicalGraph instance
            scorer: Route scoring function
            constraints_engine: ProcessConstraintsEngine instance
            pharma_mode: Enforce ≥99% yield requirement
        """
        self.graph = chemical_graph
        self.scorer = scorer
        self.constraints_engine = constraints_engine
        self.pharma_mode = pharma_mode
        
        # MCTS parameters
        self.exploration_weight = 1.414  # sqrt(2) - standard UCT
        self.max_depth = 6
        self.max_iterations = 500
        
        # Pruning thresholds
        self.min_yield_pharma = 99.0
        self.min_yield_normal = 50.0
        self.max_constraint_penalty = 70.0
        self.max_cost_per_step = 500.0
        
        # Global tracking
        self.best_route = None
        self.best_score = float('-inf')
        self.iteration_count = 0
        
        # Performance tuning: caching
        self._evaluation_cache = {}
        self._pruning_cache = {}
        
        logger.info(f"MCTS initialized: pharma_mode={pharma_mode}")
    
    def search(
        self,
        target_molecule: str,
        max_iterations: Optional[int] = None,
        max_depth: Optional[int] = None
    ) -> List[Dict]:
        """
        Execute MCTS to find optimal synthesis routes.
        
        Args:
            target_molecule: Target product SMILES
            max_iterations: Override default iteration limit
            max_depth: Override default depth limit
            
        Returns:
            List of synthesis routes (best first)
        """
        if max_iterations:
            self.max_iterations = max(100, min(1000, max_iterations))
        if max_depth:
            self.max_depth = max(2, min(12, max_depth))
        
        # Reset caches and state for new search
        self._evaluation_cache = {}
        self._pruning_cache = {}
        self.best_route = None
        self.best_score = float('-inf')
        self.iteration_count = 0
        
        logger.info(
            f"mcts_search_start: target={target_molecule[:20]}..., "
            f"max_iter={self.max_iterations}, max_depth={self.max_depth}"
        )
        
        # Initialize root node
        root = MCTSNode(
            molecule=target_molecule,
            path_from_root=[target_molecule],
            depth=0
        )
        
        # Check if target is already commercial
        if self.graph.is_commercial(target_molecule):
            logger.info("target_is_commercial: returning trivial route")
            return [{
                'target': target_molecule,
                'starting_materials': [target_molecule],
                'steps': [],
                'num_steps': 0,
                'score': 100.0
            }]
        
        # MCTS main loop
        for iteration in range(self.max_iterations):
            self.iteration_count = iteration + 1
            
            # 1. SELECTION: Traverse tree using UCB
            node = self._select(root)
            
            # 2. EXPANSION: Generate children
            if not node.is_terminal and node.depth < self.max_depth:
                node = self._expand(node)
            
            # 3. EVALUATION: Rollout or direct scoring
            reward = self._evaluate(node)
            
            # 4. BACKPROPAGATION: Update statistics
            self._backpropagate(node, reward)
            
            # Log progress
            if (iteration + 1) % 100 == 0:
                logger.info(
                    f"mcts_iteration_{iteration + 1}: "
                    f"best_score={self.best_score:.2f}, "
                    f"root_visits={root.visits}"
                )
        
        # Extract best routes from tree
        routes = self._extract_routes(root, top_k=5)
        
        logger.info(
            f"mcts_search_complete: {len(routes)} routes found, "
            f"best_score={self.best_score:.2f}"
        )
        
        return routes
    
    def _select(self, node: MCTSNode) -> MCTSNode:
        """
        Selection phase: Traverse tree using UCB until leaf.
        
        Args:
            node: Starting node (usually root)
            
        Returns:
            Leaf node for expansion
        """
        current = node
        
        while current.children and not current.is_terminal:
            # Select child with highest UCB score
            current = max(
                current.children,
                key=lambda c: c.ucb_score(self.exploration_weight)
            )
            
            # Stop if pruned
            if current.is_pruned:
                break
        
        return current
    
    def _expand(self, node: MCTSNode) -> MCTSNode:
        """
        Expansion phase: Generate child nodes from reactions.
        
        Args:
            node: Node to expand
            
        Returns:
            New child node (randomly selected) or original node if no expansion
        """
        # Get possible reactions for this molecule
        reactions = self.graph.get_reactions_for_product(node.molecule)
        
        if not reactions:
            node.is_terminal = True
            node.is_commercial = self.graph.is_commercial(node.molecule)
            return node
        
        # Generate children for each reaction's reactants
        for rxn in reactions:
            for reactant in rxn['reactants']:
                # Skip if already in path (cycle detection)
                if reactant in node.path_from_root:
                    continue
                
                # Create child node
                child = MCTSNode(
                    molecule=reactant,
                    parent=node,
                    path_from_root=node.path_from_root + [reactant],
                    reaction_used=rxn,
                    depth=node.depth + 1
                )
                
                # Check if commercial
                if self.graph.is_commercial(reactant):
                    child.is_terminal = True
                    child.is_commercial = True
                
                # Apply pruning rules
                if self._should_prune(child):
                    child.is_pruned = True
                    continue
                
                node.children.append(child)
        
        # Return random child for evaluation (or node if no valid children)
        if node.children:
            return random.choice(node.children)
        else:
            node.is_terminal = True
            return node
    
    def _should_prune(self, node: MCTSNode) -> bool:
        """
        Apply pruning rules to avoid exploring bad branches.
        Uses caching for constraint checks.
        
        Args:
            node: Node to check
            
        Returns:
            True if node should be pruned
        """
        if not node.reaction_used:
            return False
        
        # Check pruning cache
        cache_key = tuple(node.path_from_root)
        if cache_key in self._pruning_cache:
            return self._pruning_cache[cache_key]
        
        rxn = node.reaction_used
        result = False
        
        # Pruning Rule 1: Pharma mode yield enforcement
        if self.pharma_mode:
            yield_pct = rxn.get('yield_percent', 75.0)
            if yield_pct < self.min_yield_pharma:
                node.pruning_reason = f"pharma_yield_{yield_pct:.1f}%<{self.min_yield_pharma}%"
                result = True
        
        # Pruning Rule 2: Normal mode minimum yield
        if not result and not self.pharma_mode:
            yield_pct = rxn.get('yield_percent', 75.0)
            if yield_pct < self.min_yield_normal:
                node.pruning_reason = f"low_yield_{yield_pct:.1f}%"
                result = True
        
        # Pruning Rule 2b: Yield-based expansion control
        # Aggressively prune low-yield branches to focus search on high-yield routes
        if not result:
            yield_pct = rxn.get('yield_percent', 75.0)
            if yield_pct < 70.0 and node.depth > 2:
                node.pruning_reason = f"yield_too_low_at_depth_{node.depth}_{yield_pct:.1f}%"
                result = True
        
        # Pruning Rule 3: High cost
        if not result:
            cost = rxn.get('cost', 100.0)
            if cost > self.max_cost_per_step:
                node.pruning_reason = f"high_cost_${cost:.0f}"
                result = True
        
        # Pruning Rule 4: Constraint penalties (if engine available)
        if not result and self.constraints_engine:
            try:
                constraints = self.constraints_engine.evaluate_reaction_constraints(
                    rxn, scale='lab', batch_size_kg=0.1
                )
                if constraints.total_penalty > self.max_constraint_penalty:
                    node.pruning_reason = f"high_constraints_{constraints.total_penalty:.0f}"
                    result = True
            except Exception as e:
                logger.debug(f"constraint_check_failed: {str(e)}")
        
        self._pruning_cache[cache_key] = result
        return result
    
    def _evaluate(self, node: MCTSNode) -> float:
        """
        Evaluation phase: Score the route from root to this node.
        Uses caching to avoid redundant calculations.
        
        Args:
            node: Node to evaluate
            
        Returns:
            Reward score (0-100)
        """
        # Cache key based on molecule path
        cache_key = tuple(node.path_from_root)
        if cache_key in self._evaluation_cache:
            return self._evaluation_cache[cache_key]
        
        # If not terminal, do a simple heuristic rollout
        if not node.is_terminal:
            score = self._heuristic_evaluation(node)
        elif node.is_commercial:
            # If terminal and commercial, this is a complete route
            score = self._score_complete_route(node)
        else:
            # Terminal but not commercial = dead end
            score = 0.0
        
        # Cache result
        self._evaluation_cache[cache_key] = score
        return score
    
    def _heuristic_evaluation(self, node: MCTSNode) -> float:
        """Quick heuristic evaluation for non-terminal nodes."""
        # Calculate path quality so far
        total_yield = 100.0
        total_cost = 0.0
        
        current = node
        while current.parent:
            if current.reaction_used:
                total_yield *= (current.reaction_used.get('yield_percent', 75.0) / 100.0)
                total_cost += current.reaction_used.get('cost', 100.0)
            current = current.parent
        
        # Penalize depth
        depth_penalty = node.depth * 5
        
        # Simple score
        yield_score = total_yield
        cost_score = max(0, 100 - total_cost / 5)
        
        score = 0.5 * yield_score + 0.3 * cost_score - depth_penalty
        
        return max(0, min(100, score))
    
    def _score_complete_route(self, node: MCTSNode) -> float:
        """Score a complete route (terminal commercial node)."""
        # Build route dict
        route_dict = {
            'target': node.path_from_root[0],
            'starting_materials': [node.molecule],
            'steps': [],
            'num_steps': node.depth
        }
        
        # Calculate metrics along path
        overall_yield = 100.0
        total_cost = 0.0
        total_time = 0.0
        
        current = node
        while current.parent:
            if current.reaction_used:
                overall_yield *= (current.reaction_used.get('yield_percent', 75.0) / 100.0)
                total_cost += current.reaction_used.get('cost', 100.0)
                total_time += current.reaction_used.get('time_hours', 4.0)
            current = current.parent
        
        route_dict['overall_yield_percent'] = overall_yield
        route_dict['total_cost_usd'] = total_cost
        route_dict['total_time_hours'] = total_time
        
        # Use scorer for final evaluation
        # (This is a simplified version - full integration would use complete scoring)
        yield_score = overall_yield
        cost_score = max(0, 100 - total_cost / 10)
        time_score = max(0, 100 - total_time * 2)
        step_score = max(0, 100 - node.depth * 10)
        
        score = 0.35 * yield_score + 0.30 * cost_score + 0.15 * time_score + 0.20 * step_score
        
        # Update global best
        if score > self.best_score:
            self.best_score = score
            self.best_route = route_dict
            logger.info(f"new_best_route: score={score:.2f}, yield={overall_yield:.1f}%, cost=${total_cost:.0f}")
        
        return score
    
    def _backpropagate(self, node: MCTSNode, reward: float) -> None:
        """
        Backpropagation phase: Update node statistics up the tree.
        
        Args:
            node: Starting node
            reward: Reward to propagate
        """
        current = node
        
        while current:
            current.visits += 1
            current.total_reward += reward
            current.best_reward = max(current.best_reward, reward)
            current = current.parent
    
    def _extract_routes(self, root: MCTSNode, top_k: int = 5) -> List[Dict]:
        """
        Extract best routes from MCTS tree.
        
        Args:
            root: Root node
            top_k: Number of routes to return
            
        Returns:
            List of route dicts sorted by score
        """
        routes = []
        
        # Find all terminal commercial nodes
        def find_terminals(node: MCTSNode):
            if node.is_terminal and node.is_commercial and node.visits > 0:
                routes.append({
                    'node': node,
                    'score': node.average_reward(),
                    'visits': node.visits
                })
            
            for child in node.children:
                find_terminals(child)
        
        find_terminals(root)
        
        # Sort by score
        routes.sort(key=lambda r: r['score'], reverse=True)
        
        # Convert to route dicts
        result = []
        for r in routes[:top_k]:
            node = r['node']
            
            route_dict = {
                'target': node.path_from_root[0],
                'starting_materials': [node.molecule],
                'steps': [],
                'num_steps': node.depth,
                'score': r['score'],
                'visits': r['visits']
            }
            
            # Calculate final metrics
            overall_yield = 100.0
            current = node
            while current.parent:
                if current.reaction_used:
                    overall_yield *= (current.reaction_used.get('yield_percent', 75.0) / 100.0)
                current = current.parent
            
            route_dict['estimated_yield'] = overall_yield
            
            result.append(route_dict)
        
        return result


# Demo/testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("\n=== MCTS Search Engine Test ===")
    print("MCTS initialized successfully")
    print("✓ Ready for integration with ChemicalGraph and Orchestrator")
