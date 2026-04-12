"""
Convergence Engine — Phase 7: Iterative Optimization

Implements the self-improving optimization loop:
  search → improve → re-search → converge → best possible route

Key capabilities:
1. Iterative convergence loop
2. Objective-driven optimization
3. Improvement score tracking per iteration
4. Early stopping when converged
5. Pharma mode integration (reject <99% yield)
"""

import logging
import copy
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


@dataclass
class IterationResult:
    """Metrics for a single optimization iteration."""
    iteration: int
    score_before: float
    score_after: float
    improvement: float
    mutations_applied: int
    changes: List[str]
    routes_evaluated: int
    routes_kept: int
    best_yield: float
    best_cost: float
    duration_ms: float


@dataclass 
class ConvergenceResult:
    """Final result of the convergence loop."""
    status: str  # "converged", "max_iterations", "no_improvement"
    total_iterations: int
    total_improvement: float
    initial_score: float
    final_score: float
    convergence_history: List[Dict]
    best_routes: List[Dict]
    objective: str
    pharma_mode: bool
    early_stopped: bool
    early_stop_reason: str
    total_duration_ms: float


class ConvergenceEngine:
    """
    Iterative optimization engine that converges to the best possible route.
    
    Loop: search → mutate → evaluate → select_top_k → repeat
    """
    
    def __init__(self, route_optimizer, constraints_engine=None):
        """
        Args:
            route_optimizer: RouteOptimizer instance (with mutation + scoring)
            constraints_engine: ProcessConstraintsEngine instance
        """
        self.optimizer = route_optimizer
        self.constraints_engine = constraints_engine
        
        # Default parameters
        self.default_iterations = 3
        self.default_top_k = 5
        self.default_early_stop_threshold = 0.5
        self.pharma_yield_threshold = 99.0
    
    def optimize(
        self,
        routes: List[Dict],
        objective: str = "balanced",
        max_iterations: int = None,
        top_k: int = None,
        early_stop_threshold: float = None,
        pharma_mode: bool = False,
    ) -> ConvergenceResult:
        """
        Run iterative optimization convergence loop.
        
        Args:
            routes: Initial routes to optimize
            objective: Optimization objective ("pharma", "cost", "green", "speed", "balanced")
            max_iterations: Maximum optimization iterations (default 3)
            top_k: Number of top routes to keep per iteration (default 5)
            early_stop_threshold: Stop if improvement < this (default 0.5)
            pharma_mode: If True, reject routes with <99% yield
            
        Returns:
            ConvergenceResult with full history
        """
        iterations = max_iterations or self.default_iterations
        k = top_k or self.default_top_k
        threshold = early_stop_threshold or self.default_early_stop_threshold
        
        # Override objective for pharma mode
        if pharma_mode and objective != "pharma":
            objective = "pharma"
        
        logger.info(
            f"convergence_start: {len(routes)} routes, "
            f"objective={objective}, iterations={iterations}, "
            f"top_k={k}, pharma={pharma_mode}"
        )
        
        start_time = time.time()
        
        # Ensure all routes have scores
        best_routes = self._score_and_rank(routes, objective, pharma_mode)
        
        if not best_routes:
            return ConvergenceResult(
                status="no_routes",
                total_iterations=0,
                total_improvement=0,
                initial_score=0,
                final_score=0,
                convergence_history=[],
                best_routes=[],
                objective=objective,
                pharma_mode=pharma_mode,
                early_stopped=True,
                early_stop_reason="No valid routes to optimize",
                total_duration_ms=0,
            )
        
        initial_score = best_routes[0].get('_optimization_score', 0)
        convergence_history = []
        early_stopped = False
        early_stop_reason = ""
        
        # === CONVERGENCE LOOP ===
        for i in range(iterations):
            iter_start = time.time()
            score_before = best_routes[0].get('_optimization_score', 0)
            
            improved_routes = []
            all_changes = []
            total_mutations = 0
            
            for route in best_routes:
                # 1. MUTATE: Apply objective-driven mutations
                mutated = self.optimizer.mutate_route(
                    route=route,
                    mutation_types=None,  # Let objective drive mutation selection
                    objective=objective
                )
                
                # Track changes
                mutations = mutated.get('mutations_applied', [])
                total_mutations += len(mutations)
                for m in mutations:
                    all_changes.append(f"{m['type']}: {m['original']} → {m['new']}")
                
                # 2. CONSTRAINT FEEDBACK: Auto-fix based on constraints
                if self.constraints_engine:
                    mutated = self._apply_constraint_feedback_to_route(mutated, objective)
                
                improved_routes.append(mutated)
                
                # Also keep original for comparison
                improved_routes.append(copy.deepcopy(route))
            
            # 3. EVALUATE: Score all routes
            all_candidates = self._score_and_rank(improved_routes, objective, pharma_mode)
            
            # 4. SELECT TOP-K: Merge and keep best
            best_routes = self._select_top_k(all_candidates, k)
            
            # Calculate iteration metrics
            score_after = best_routes[0].get('_optimization_score', 0) if best_routes else 0
            improvement = score_after - score_before
            
            # Best route metrics
            best = best_routes[0] if best_routes else {}
            best_yield = best.get('overall_yield_percent', best.get('estimated_yield', 0))
            best_cost = best.get('total_cost_usd', 0)
            
            iter_result = IterationResult(
                iteration=i + 1,
                score_before=round(score_before, 2),
                score_after=round(score_after, 2),
                improvement=round(improvement, 2),
                mutations_applied=total_mutations,
                changes=all_changes[:10],  # Cap at 10 changes for readability
                routes_evaluated=len(all_candidates),
                routes_kept=len(best_routes),
                best_yield=round(best_yield, 2),
                best_cost=round(best_cost, 2),
                duration_ms=round((time.time() - iter_start) * 1000, 1),
            )
            
            convergence_history.append(asdict(iter_result))
            
            logger.info(
                f"convergence_iteration_{i+1}: "
                f"score={score_after:.2f} (Δ{improvement:+.2f}), "
                f"mutations={total_mutations}, yield={best_yield:.1f}%"
            )
            
            # 5. EARLY STOPPING CHECK
            if abs(improvement) < threshold and i > 0:
                early_stopped = True
                early_stop_reason = f"Converged: improvement {improvement:.3f} < threshold {threshold}"
                logger.info(f"early_stop: {early_stop_reason}")
                break
            
            # No mutations applied = nothing more to improve
            if total_mutations == 0 and i > 0:
                early_stopped = True
                early_stop_reason = "No mutations applicable — route is already optimal"
                logger.info(f"early_stop: {early_stop_reason}")
                break
        
        # Final cleanup: remove internal scoring fields
        final_routes = []
        for route in best_routes:
            clean_route = {k: v for k, v in route.items() if not k.startswith('_')}
            final_routes.append(clean_route)
        
        total_duration = (time.time() - start_time) * 1000
        final_score = best_routes[0].get('_optimization_score', 0) if best_routes else 0
        
        status = "converged" if early_stopped else "max_iterations"
        if not best_routes:
            status = "no_improvement"
        
        result = ConvergenceResult(
            status=status,
            total_iterations=len(convergence_history),
            total_improvement=round(final_score - initial_score, 2),
            initial_score=round(initial_score, 2),
            final_score=round(final_score, 2),
            convergence_history=convergence_history,
            best_routes=final_routes,
            objective=objective,
            pharma_mode=pharma_mode,
            early_stopped=early_stopped,
            early_stop_reason=early_stop_reason,
            total_duration_ms=round(total_duration, 1),
        )
        
        logger.info(
            f"convergence_complete: status={status}, "
            f"iterations={len(convergence_history)}, "
            f"improvement={result.total_improvement:+.2f}, "
            f"duration={total_duration:.0f}ms"
        )
        
        return result
    
    def _score_and_rank(self, routes: List[Dict], objective: str, pharma_mode: bool) -> List[Dict]:
        """Score all routes and filter by pharma constraints if needed."""
        scored = []
        
        for route in routes:
            score = self.optimizer.score_route(route, objective)
            route_copy = copy.deepcopy(route)
            route_copy['_optimization_score'] = score
            
            # Pharma mode: reject low-yield routes
            if pharma_mode:
                yield_val = route_copy.get('overall_yield_percent', route_copy.get('estimated_yield', 0))
                if yield_val < self.pharma_yield_threshold:
                    continue  # Reject
            
            scored.append(route_copy)
        
        # Sort by score descending
        scored.sort(key=lambda r: r.get('_optimization_score', 0), reverse=True)
        return scored
    
    def _select_top_k(self, routes: List[Dict], k: int) -> List[Dict]:
        """Select top-k routes, deduplicated by step signatures."""
        seen = set()
        selected = []
        
        for route in routes:
            # Create a signature for deduplication
            steps = route.get('steps', [])
            sig_parts = []
            for step in steps:
                if isinstance(step, dict):
                    conditions = step.get('conditions', step)
                    sig_parts.append(
                        f"{conditions.get('catalyst', '')}_"
                        f"{conditions.get('solvent', '')}_"
                        f"{conditions.get('temperature_celsius', conditions.get('temperature_c', ''))}"
                    )
            
            sig = "|".join(sig_parts)
            
            if sig not in seen:
                seen.add(sig)
                selected.append(route)
                
                if len(selected) >= k:
                    break
        
        return selected
    
    def _apply_constraint_feedback_to_route(self, route: Dict, objective: str) -> Dict:
        """Apply constraint feedback to each step in the route."""
        if not self.constraints_engine:
            return route
        
        steps = route.get('steps', [])
        for step in steps:
            if not isinstance(step, dict):
                continue
            
            conditions = step.get('conditions', step)
            if not conditions:
                continue
            
            try:
                evaluation = self.constraints_engine.evaluate_reaction_constraints(
                    reaction=conditions, scale='lab', batch_size_kg=0.1
                )
                
                # Auto-fix based on constraint feedback
                if evaluation.heat_risk in ("high", "critical"):
                    temp_key = 'temperature_celsius' if 'temperature_celsius' in conditions else 'temperature_c'
                    if temp_key in conditions and conditions[temp_key]:
                        conditions[temp_key] = max(conditions[temp_key] - 20, 0)
                
                if evaluation.mixing_efficiency in ("poor", "very_poor"):
                    current_solvent = conditions.get('solvent', '')
                    if current_solvent in ("hexane", "None", "water"):
                        conditions['solvent'] = "THF"
                
            except Exception:
                pass
        
        return route
