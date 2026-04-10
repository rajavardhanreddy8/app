import os
import sys
import logging
import structlog
import time
from typing import Dict, Any, List, Optional
from models.chemistry import SynthesisRequest, SynthesisResponse, SynthesisRoute
from services.claude_service import ClaudeService
from services.molecular_service import MolecularService  
from services.synthesis_planner import SynthesisPlanner
from services.retrosynthesis_engine import RetrosynthesisEngine
from services.scale_aware_optimizer import ScaleAwareOptimizer
from services.advanced_cost_model import AdvancedCostModel
from services.yield_predictor import YieldPredictor
from services.condition_predictor import ConditionPredictor
from services.enhanced_route_scorer import EnhancedRouteScorer
from services.process_constraints_engine import ProcessConstraintsEngine
from services.equipment_spec_engine import EquipmentSpecEngine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logger = structlog.get_logger()

class SynthesisPlanningOrchestrator:
    """Orchestrates the complete synthesis planning workflow."""
    
    def __init__(self, api_key: str = None, db=None):
        """
        Initialize orchestrator with optional database connection.
        
        Args:
            api_key: Anthropic API key
            db: MongoDB database connection (for Phase 6 graph building)
        """
        self.claude_service = ClaudeService(api_key=api_key)
        self.molecular_service = MolecularService()
        self.synthesis_planner = SynthesisPlanner()
        
        # Advanced modules for Phase 4
        self.retrosynthesis_engine = RetrosynthesisEngine()
        self.scale_optimizer = ScaleAwareOptimizer()
        self.cost_model = AdvancedCostModel()
        self.yield_predictor = YieldPredictor()
        self.condition_predictor = ConditionPredictor()
        self.route_scorer = EnhancedRouteScorer()
        
        # Phase 5: Process constraints engine
        try:
            self.constraints_engine = ProcessConstraintsEngine()
        except Exception as e:
            logger.warning(f"ProcessConstraintsEngine init failed: {e}, using fallback")
            self.constraints_engine = None

        try:
            self.equipment_engine = EquipmentSpecEngine()
        except Exception as e:
            logger.warning(f"EquipmentSpecEngine init failed: {e}, using fallback")
            self.equipment_engine = None
        
        # Phase 6: Chemical graph + MCTS (CRITICAL INTEGRATION)
        self.db = db
        self.chem_graph = None
        self.mcts_engine = None
        self._graph_initialized = False
        
        # Load ML models
        self.yield_predictor.load_model()
        self.condition_predictor.load_models()
        
        # Cost calculation cache (hybrid approach)
        self._cost_cache = {}
    
    async def initialize_graph(self):
        """
        Initialize chemical graph from MongoDB reactions.
        
        CRITICAL: This must be called once on startup or before first MCTS search.
        """
        if self._graph_initialized or not self.db:
            return
        
        try:
            logger.info("initializing_chemical_graph_from_mongodb")
            
            # Load reactions from database
            reactions = await self.db.reactions.find({}, {"_id": 0}).to_list(2000)
            logger.info(f"loaded_{len(reactions)}_reactions_from_db")
            
            # Build graph
            self.chem_graph = ChemicalGraph()
            self.chem_graph.build_from_reactions(reactions)
            
            # Log stats
            stats = self.chem_graph.get_graph_stats()
            logger.info(
                f"chemical_graph_initialized: "
                f"{stats['num_molecules']} molecules, "
                f"{stats['num_reactions']} reactions"
            )
            
            self._graph_initialized = True
            
        except Exception as e:
            logger.error(f"chemical_graph_init_failed: {str(e)}")
            self.chem_graph = None

    async def _generate_routes_mcts(
        self,
        target_smiles: str,
        num_routes: int,
        pharma_mode: bool
    ) -> List[Dict]:
        """
        Generate routes using MCTS search (Phase 6).
        
        Args:
            target_smiles: Target molecule
            num_routes: Number of routes to return
            pharma_mode: Pharma yield enforcement
            
        Returns:
            List of route dicts from MCTS
        """
        try:
            # Initialize MCTS engine if not done
            if not self.mcts_engine or self.mcts_engine.pharma_mode != pharma_mode:
                self.mcts_engine = MCTSSearch(
                    chemical_graph=self.chem_graph,
                    scorer=self.route_scorer,
                    constraints_engine=self.constraints_engine,
                    pharma_mode=pharma_mode
                )
            
            # Run MCTS search
            routes = self.mcts_engine.search(
                target_molecule=target_smiles,
                max_iterations=300,  # Tunable parameter
                max_depth=6
            )
            
            logger.info(f"mcts_generated_{len(routes)}_routes")
            return routes
            
        except Exception as e:
            logger.error(f"mcts_search_failed: {str(e)}, falling back to beam search")
            # Fallback to beam search
            return self.retrosynthesis_engine.search_routes(
                target_smiles=target_smiles,
                max_depth=6,
                max_routes=num_routes,
                beam_width=5
            )

    async def plan_synthesis(self, request: SynthesisRequest) -> SynthesisResponse:
        """Complete synthesis planning workflow."""
        
        start_time = time.time()
        
        logger.info(
            "starting_synthesis_planning",
            target_smiles=request.target_smiles,
            max_steps=request.max_steps,
            optimize_for=request.optimize_for
        )
        
        # Step 1: Validate target molecule
        validation = self.molecular_service.validate_smiles(request.target_smiles)
        if not validation.get("valid"):
            raise ValueError(f"Invalid target SMILES: {validation.get('reason')}")
        
        # Step 2: Request synthesis plan from Claude
        claude_response = await self.claude_service.plan_synthesis(
            target_smiles=request.target_smiles,
            starting_materials=request.starting_materials,
            max_steps=request.max_steps,
            optimize_for=request.optimize_for
        )
        
        # Step 3: Parse Claude's response
        parsed_data = self.synthesis_planner.parse_claude_response(
            claude_response["content"]
        )
        
        # Step 4: Build structured synthesis routes
        routes = []
        if parsed_data:
            routes = self.synthesis_planner.build_synthesis_routes(
                target_smiles=request.target_smiles,
                claude_response=parsed_data,
                optimize_for=request.optimize_for
            )
        
        # Step 5: Create response
        computation_time = time.time() - start_time
        
        response = SynthesisResponse(
            target_smiles=request.target_smiles,
            routes=routes,
            computation_time_seconds=round(computation_time, 2),
            tokens_used=claude_response["usage"]["total_tokens"]
        )
        
        logger.info(
            "synthesis_planning_complete",
            num_routes=len(routes),
            computation_time=computation_time,
            tokens_used=response.tokens_used
        )
        
        return response
    
    async def plan_synthesis_advanced(
        self, 
        request: SynthesisRequest,
        num_routes: int = 5,
        scale: str = "lab",
        batch_size_kg: float = 0.1,
        use_mcts: bool = False,  # Phase 6: MCTS toggle
        pharma_mode: bool = False  # Phase 5: Pharma enforcement
    ) -> SynthesisResponse:
        """
        Advanced synthesis planning with full optimization loop.
        
        Phase 6: Can use MCTS for global optimization or beam search (fallback).
        
        Integrates retrosynthesis, ML prediction, scale optimization, and cost modeling.
        Returns top N routes ranked by composite score.
        """
        start_time = time.time()
        
        logger.info(
            "starting_advanced_synthesis_planning",
            target_smiles=request.target_smiles,
            max_routes=num_routes,
            scale=scale,
            batch_size_kg=batch_size_kg,
            use_mcts=use_mcts,
            pharma_mode=pharma_mode
        )
        
        # Step 1: Validate target molecule
        validation = self.molecular_service.validate_smiles(request.target_smiles)
        if not validation.get("valid"):
            raise ValueError(f"Invalid target SMILES: {validation.get('reason')}")
        
        # Step 2: Generate candidate routes (MCTS or Beam Search)
        if use_mcts and self.chem_graph:
            logger.info("using_mcts_search_for_route_generation")
            candidate_routes = await self._generate_routes_mcts(
                request.target_smiles,
                num_routes,
                pharma_mode
            )
        else:
            if use_mcts and not self.chem_graph:
                logger.warning("mcts_requested_but_graph_not_initialized_falling_back_to_beam_search")
            
            logger.info("using_beam_search_for_route_generation")
            candidate_routes = self.retrosynthesis_engine.search_routes(
                target_smiles=request.target_smiles,
                max_depth=request.max_steps,
                max_routes=num_routes,
                beam_width=5
            )
        
        if not candidate_routes:
            # Fallback to Claude-based planning if retrosynthesis finds nothing
            logger.warning("retrosynthesis_found_no_routes_falling_back_to_claude")
            return await self.plan_synthesis(request)
        
        logger.info(f"retrosynthesis_generated_{len(candidate_routes)}_routes")
        
        # Step 3: Optimization loop - enhance each route
        optimized_routes = []
        
        for idx, route_data in enumerate(candidate_routes):
            try:
                logger.info(f"optimizing_route_{idx+1}")
                
                # Convert to internal format for processing
                route_dict = self._convert_retro_route_to_dict(route_data)
                
                # Sub-step 3a: Predict conditions for each step using ML
                route_dict = self._predict_conditions_for_route(route_dict)
                
                # Sub-step 3b: Predict yields using ML
                route_dict = self._predict_yields_for_route(route_dict)
                
                # Sub-step 3c: Predict reaction times
                route_dict = self._predict_times_for_route(route_dict)
                
                # Sub-step 3d: Scale optimization
                route_dict = self._optimize_for_scale(route_dict, scale, batch_size_kg)
                
                # Phase 5: Sub-step 3e: Evaluate process constraints
                route_dict = self._evaluate_process_constraints(route_dict, scale, batch_size_kg)

                # Phase 9: Sub-step 3f: Equipment-centric process design (hard feasibility)
                route_dict = self._evaluate_equipment_feasibility(route_dict, scale, batch_size_kg)
                if route_dict.get('equipment_rejected', False):
                    logger.info(f"route_rejected_by_equipment_constraints_{idx+1}")
                    continue
                
                # Sub-step 3g: Calculate industrial costs (with hybrid caching)
                route_dict = self._calculate_industrial_costs(route_dict, scale, batch_size_kg)
                
                # Sub-step 3h: Calculate composite score (includes constraint/equipment penalties)
                route_dict['score'] = self._calculate_composite_score(
                    route_dict, 
                    request.optimize_for
                )
                
                optimized_routes.append(route_dict)
                
            except Exception as e:
                logger.error(f"failed_to_optimize_route_{idx+1}: {str(e)}")
                continue
        
        # Step 4: Rank routes by score
        optimized_routes.sort(key=lambda r: r.get('score', 0), reverse=True)
        
        # Step 5: Convert to SynthesisRoute objects
        final_routes = []
        for route_dict in optimized_routes[:num_routes]:
            try:
                synthesis_route = self._convert_dict_to_synthesis_route(route_dict, request.target_smiles)
                final_routes.append(synthesis_route)
            except Exception as e:
                logger.error(f"failed_to_convert_route: {str(e)}")
                continue
        
        # Step 6: Create response
        computation_time = time.time() - start_time
        
        response = SynthesisResponse(
            target_smiles=request.target_smiles,
            routes=final_routes,
            computation_time_seconds=round(computation_time, 2),
            tokens_used=0  # No LLM tokens used in advanced mode
        )
        
        logger.info(
            "advanced_synthesis_planning_complete",
            num_routes=len(final_routes),
            computation_time=computation_time
        )
        
        return response
    
    def _convert_retro_route_to_dict(self, retro_route: Dict) -> Dict:
        """Convert retrosynthesis route to internal processing format."""
        return {
            'target': retro_route['target'],
            'starting_materials': retro_route['starting_materials'],
            'steps': retro_route['steps'],
            'num_steps': retro_route['num_steps'],
            'base_yield': retro_route.get('estimated_yield', 75.0),
            'base_cost': retro_route.get('estimated_cost', 100.0),
            'route_type': 'retrosynthesis'
        }
    
    def _predict_conditions_for_route(self, route: Dict) -> Dict:
        """Predict optimal conditions for each step using ML."""
        for step in route['steps']:
            try:
                reaction_dict = {
                    'reactants': step.get('reactants', []),
                    'products': [step.get('product', '')],
                    'reaction_type': step.get('reaction_type', 'unknown')
                }
                
                conditions = self.condition_predictor.predict_conditions(reaction_dict)
                
                # Update step with predicted conditions
                step['predicted_conditions'] = {
                    'temperature_celsius': conditions.get('temperature_celsius', 25.0),
                    'catalyst': conditions.get('catalyst', 'None'),
                    'solvent': conditions.get('solvent', 'THF'),
                    'confidence': conditions.get('confidence', 'medium')
                }
                
            except Exception as e:
                logger.error(f"condition_prediction_failed: {str(e)}")
                # Use defaults
                step['predicted_conditions'] = {
                    'temperature_celsius': 25.0,
                    'catalyst': 'None',
                    'solvent': 'THF',
                    'confidence': 'low'
                }
        
        return route
    
    def _predict_yields_for_route(self, route: Dict) -> Dict:
        """Predict yields for each step using ML."""
        overall_yield = 100.0
        
        for step in route['steps']:
            try:
                reaction_dict = {
                    'reactants': step.get('reactants', []),
                    'products': [step.get('product', '')],
                    'conditions': step.get('predicted_conditions', {})
                }
                
                predicted_yield = self.yield_predictor.predict(reaction_dict)
                
                if predicted_yield and predicted_yield > 0:
                    step['predicted_yield'] = round(predicted_yield, 1)
                else:
                    step['predicted_yield'] = 75.0  # Default
                
                overall_yield *= (step['predicted_yield'] / 100.0)
                
            except Exception as e:
                logger.error(f"yield_prediction_failed: {str(e)}")
                step['predicted_yield'] = 75.0
                overall_yield *= 0.75
        
        route['overall_yield_percent'] = round(overall_yield, 2)
        return route
    
    def _predict_times_for_route(self, route: Dict) -> Dict:
        """Predict reaction times for each step."""
        total_time = 0.0
        
        for step in route['steps']:
            # Simple time prediction based on reaction type and conditions
            temp = step.get('predicted_conditions', {}).get('temperature_celsius', 25.0)
            
            # Base time: 4 hours
            base_time = 4.0
            
            # Adjust for temperature
            if temp < 0:
                time_hours = base_time * 1.5  # Cryogenic slower
            elif temp > 80:
                time_hours = base_time * 0.7  # High temp faster
            else:
                time_hours = base_time
            
            step['predicted_time_hours'] = round(time_hours, 1)
            total_time += time_hours
        
        route['total_time_hours'] = round(total_time, 1)
        return route
    
    def _optimize_for_scale(self, route: Dict, scale: str, batch_size_kg: float) -> Dict:
        """Apply scale-aware optimization."""
        try:
            # Optimize each step for scale
            for step in route['steps']:
                reaction_dict = {
                    'catalyst_loading': 5.0,
                    'solvent_volume_ml_per_g': 10.0,
                    'time_hours': step.get('predicted_time_hours', 4.0),
                    'yield_percent': step.get('predicted_yield', 75.0),
                    'temperature_c': step.get('predicted_conditions', {}).get('temperature_celsius', 25.0)
                }
                
                scale_adjustments = self.scale_optimizer.optimize_for_scale(
                    reaction_dict, scale, batch_size_kg
                )
                
                step['scale_optimization'] = scale_adjustments
                
                # Adjust yield based on scale
                step['scale_adjusted_yield'] = scale_adjustments.get('predicted_yield_percent', step['predicted_yield'])
            
            # Recalculate overall yield with scale adjustments
            overall_yield = 100.0
            for step in route['steps']:
                overall_yield *= (step['scale_adjusted_yield'] / 100.0)
            
            route['scale_adjusted_overall_yield'] = round(overall_yield, 2)
            route['scale'] = scale
            route['batch_size_kg'] = batch_size_kg
            
        except Exception as e:
            logger.error(f"scale_optimization_failed: {str(e)}")
            route['scale_adjusted_overall_yield'] = route.get('overall_yield_percent', 75.0)
        
        return route
    
    def _evaluate_equipment_feasibility(self, route: Dict, scale: str, batch_size_kg: float) -> Dict:
        """Phase 9: Equipment feasibility + process flow generation as hard constraints."""
        if not self.equipment_engine:
            route['equipment_rejected'] = False
            route['equipment_penalty'] = 0.0
            return route

        available_equipment = route.get('available_equipment', None)
        total_penalty = 0.0
        total_equipment_cost = 0.0
        process_flow = []
        route_specs = []
        route_required = []

        for step in route.get('steps', []):
            conditions = step.get('predicted_conditions', {})
            constraints = step.get('process_constraints', {})

            reaction = {
                'temperature_c': conditions.get('temperature_celsius', 25.0),
                'pressure_atm': step.get('pressure_atm', 1.0),
                'phase_type': step.get('phase_type', 'single'),
                'density_kg_per_l': step.get('density_kg_per_l', 1.0),
                'cp_kj_kg_k': step.get('cp_kj_kg_k', 4.0),
                'delta_t_k': abs(conditions.get('temperature_celsius', 25.0) - 25.0),
                'cooling_capacity_kw': step.get('cooling_capacity_kw', 25.0),
            }

            design = self.equipment_engine.design_process(
                reaction=reaction,
                available_equipment=available_equipment,
                batch_mass_kg=batch_size_kg / max(route.get('num_steps', 1), 1),
                constraint_penalty=constraints.get('total_penalty', 0.0),
            )

            step['equipment_design'] = {
                'feasible': design.feasible,
                'required_equipment': design.required_equipment,
                'spec': design.equipment_spec,
                'rejection_reasons': design.rejection_reasons,
            }

            if not design.feasible:
                route['equipment_rejected'] = True
                route['equipment_rejection_reasons'] = design.rejection_reasons
                return route

            total_penalty += design.equipment_penalty
            total_equipment_cost += design.equipment_cost_usd
            process_flow = design.process_flow
            route_specs.append(design.equipment_spec)
            route_required.extend(design.required_equipment)

        route['equipment_rejected'] = False
        route['process_flow'] = process_flow
        route['equipment_specs'] = route_specs
        route['required_equipment'] = sorted(set(route_required))
        route['equipment_penalty'] = round(total_penalty / max(route.get('num_steps', 1), 1), 2)
        route['equipment_cost_usd'] = round(total_equipment_cost, 2)

        return route

    def _evaluate_process_constraints(self, route: Dict, scale: str, batch_size_kg: float) -> Dict:
        """
        Phase 5: Evaluate physical realism and process constraints for each step.
        
        Analyzes thermal, mixing, mass transfer, safety, and purification constraints.
        """
        total_constraint_penalty = 0.0
        route_recommendations = []
        route_equipment_requirements = []
        
        for step in route['steps']:
            try:
                # Build reaction dict for constraint evaluation
                reaction_dict = {
                    'reactants': step.get('reactants', []),
                    'products': [step.get('product', '')],
                    'reaction_type': step.get('reaction_type', 'unknown'),
                    'temperature_c': step.get('predicted_conditions', {}).get('temperature_celsius', 25.0),
                    'time_hours': step.get('predicted_time_hours', 4.0),
                    'catalyst': step.get('predicted_conditions', {}).get('catalyst', ''),
                    'solvent': step.get('predicted_conditions', {}).get('solvent', 'THF'),
                    'pressure_atm': step.get('pressure_atm', 1.0),
                    'yield_percent': step.get('scale_adjusted_yield', 75.0),
                    'phase_type': step.get('phase_type', 'single')
                }
                
                # Evaluate constraints
                constraints = self.constraints_engine.evaluate_reaction_constraints(
                    reaction_dict, scale, batch_size_kg / route['num_steps']
                )
                
                # Store constraint data in step
                step['process_constraints'] = {
                    'heat_risk': constraints.heat_risk,
                    'mixing_efficiency': constraints.mixing_efficiency,
                    'mass_transfer': constraints.mass_transfer,
                    'safety_risk': constraints.safety_risk,
                    'purification_difficulty': constraints.purification_difficulty,
                    'total_penalty': constraints.total_penalty,
                    'recommendations': constraints.recommendations,
                    'equipment_requirements': constraints.equipment_requirements
                }
                
                # Accumulate penalties and recommendations
                total_constraint_penalty += constraints.total_penalty
                route_recommendations.extend(constraints.recommendations[:3])  # Top 3 per step
                route_equipment_requirements.extend(constraints.equipment_requirements)
                
                # Adjust yield if safety/heat risk is critical
                if constraints.safety_risk == 'critical' or constraints.heat_risk == 'critical':
                    step['scale_adjusted_yield'] *= 0.95  # 5% yield reduction for critical risks
                    logger.warning(f"Critical constraint detected - yield adjusted for step {step.get('reaction_type')}")
                
            except Exception as e:
                logger.error(f"constraint_evaluation_failed: {str(e)}")
                step['process_constraints'] = {'total_penalty': 0, 'recommendations': []}
        
        # Store route-level constraint data
        route['total_constraint_penalty'] = total_constraint_penalty / max(route['num_steps'], 1)
        route['constraint_recommendations'] = list(set(route_recommendations))[:10]  # Unique, top 10
        route['equipment_requirements'] = list(set(route_equipment_requirements))
        
        # Recalculate overall yield after constraint adjustments
        overall_yield = 100.0
        for step in route['steps']:
            overall_yield *= (step['scale_adjusted_yield'] / 100.0)
        route['scale_adjusted_overall_yield'] = round(overall_yield, 2)
        
        logger.info(f"constraint_evaluation_complete: penalty={total_constraint_penalty:.1f}, recommendations={len(route['constraint_recommendations'])}")
        
        return route
    
    def _calculate_industrial_costs(self, route: Dict, scale: str, batch_size_kg: float) -> Dict:
        """Calculate industrial costs with hybrid caching."""
        total_cost = 0.0
        cost_breakdown = {
            'reagent_cost': 0.0,
            'energy_cost': 0.0,
            'labor_cost': 0.0,
            'equipment_cost': 0.0,
            'waste_disposal_cost': 0.0
        }
        
        for step in route['steps']:
            try:
                # Create cache key
                cache_key = f"{step.get('product', '')}_{scale}_{batch_size_kg}"
                
                # Check cache (hybrid approach)
                if cache_key in self._cost_cache:
                    step_cost = self._cost_cache[cache_key]
                    logger.debug(f"cost_cache_hit: {cache_key}")
                else:
                    # Calculate cost using advanced model
                    reaction_dict = {
                        'reactants': step.get('reactants', []),
                        'products': [step.get('product', '')],
                        'catalysts': [step.get('predicted_conditions', {}).get('catalyst', '')],
                        'solvents': [step.get('predicted_conditions', {}).get('solvent', 'THF')],
                        'temperature_c': step.get('predicted_conditions', {}).get('temperature_celsius', 25.0),
                        'time_hours': step.get('predicted_time_hours', 4.0)
                    }
                    
                    step_cost = self.cost_model.calculate_total_cost(
                        reaction_dict,
                        scale=scale,
                        batch_size_kg=batch_size_kg / route['num_steps'],  # Distribute batch size
                        include_recovery=(scale in ['pilot', 'industrial'])
                    )
                    
                    # Cache the result
                    self._cost_cache[cache_key] = step_cost
                
                step['cost_breakdown'] = step_cost
                total_cost += step_cost['total_cost']
                
                # Aggregate breakdown
                for key in cost_breakdown:
                    if key in step_cost:
                        cost_breakdown[key] += step_cost[key]
                
            except Exception as e:
                logger.error(f"cost_calculation_failed: {str(e)}")
                step['cost_breakdown'] = {'total_cost': 50.0}
                total_cost += 50.0
        
        total_cost += route.get('equipment_cost_usd', 0.0)
        cost_breakdown['equipment_cost'] += route.get('equipment_cost_usd', 0.0)
        route['total_cost_usd'] = round(total_cost, 2)
        route['cost_breakdown'] = {k: round(v, 2) for k, v in cost_breakdown.items()}
        
        return route
    
    def _calculate_composite_score(self, route: Dict, optimize_for: str) -> float:
        """
        Calculate composite score based on yield, cost, time, steps, and constraints (Phase 5).
        """
        
        # Normalize metrics (0-100 scale)
        yield_score = route.get('scale_adjusted_overall_yield', 75.0)
        
        # Cost score (inverse, lower is better)
        cost = route.get('total_cost_usd', 100.0)
        cost_score = max(0, 100 - (cost / 10.0))  # Normalize assuming $1000 = 0 score
        
        # Time score (inverse, lower is better)
        time = route.get('total_time_hours', 10.0)
        time_score = max(0, 100 - (time * 2))  # Normalize assuming 50h = 0 score
        
        # Steps penalty (fewer is better)
        steps = route.get('num_steps', 3)
        step_score = max(0, 100 - (steps * 10))
        
        # Phase 5/9: Constraint + equipment penalties (higher penalty = lower score)
        constraint_penalty = route.get('total_constraint_penalty', 0.0)
        equipment_penalty = route.get('equipment_penalty', 0.0)
        constraint_score = max(0, 100 - constraint_penalty)
        equipment_score = max(0, 100 - equipment_penalty)
        
        # Weights based on optimization goal (Phase 5: added 10% for constraints)
        if optimize_for == 'yield':
            weights = {'yield': 0.50, 'cost': 0.10, 'time': 0.05, 'steps': 0.10, 'constraints': 0.15, 'equipment': 0.10}
        elif optimize_for == 'cost':
            weights = {'yield': 0.20, 'cost': 0.40, 'time': 0.05, 'steps': 0.10, 'constraints': 0.15, 'equipment': 0.10}
        elif optimize_for == 'time':
            weights = {'yield': 0.20, 'cost': 0.10, 'time': 0.40, 'steps': 0.10, 'constraints': 0.10, 'equipment': 0.10}
        else:  # balanced
            weights = {'yield': 0.30, 'cost': 0.25, 'time': 0.15, 'steps': 0.10, 'constraints': 0.10, 'equipment': 0.10}
        
        composite_score = (
            weights['yield'] * yield_score +
            weights['cost'] * cost_score +
            weights['time'] * time_score +
            weights['steps'] * step_score +
            weights['constraints'] * constraint_score +
            weights['equipment'] * equipment_score
        )
        
        return round(composite_score, 2)
    
    def _convert_dict_to_synthesis_route(self, route_dict: Dict, target_smiles: str) -> SynthesisRoute:
        """Convert internal route dict to SynthesisRoute Pydantic model."""
        from models.chemistry import SynthesisRoute, ReactionStep, MolecularStructure, ReactionCondition
        from datetime import datetime
        
        # Create target molecule
        target_mol = MolecularStructure(smiles=target_smiles)
        
        # Create starting materials
        starting_materials = [
            MolecularStructure(smiles=sm) 
            for sm in route_dict.get('starting_materials', [])
        ]
        
        # Create steps
        steps = []
        for step_data in route_dict.get('steps', []):
            try:
                # Create reactants
                reactants = [
                    MolecularStructure(smiles=r) 
                    for r in step_data.get('reactants', [])
                ]
                
                # Create product
                product = MolecularStructure(smiles=step_data.get('product', ''))
                
                # Create conditions
                cond_data = step_data.get('predicted_conditions', {})
                conditions = ReactionCondition(
                    temperature_celsius=cond_data.get('temperature_celsius', 25.0),
                    solvent=cond_data.get('solvent', 'THF'),
                    catalyst=cond_data.get('catalyst'),
                    time_hours=step_data.get('predicted_time_hours', 4.0)
                )
                
                # Create step
                step = ReactionStep(
                    reactants=reactants,
                    product=product,
                    reaction_type=step_data.get('reaction_type', 'Unknown'),
                    conditions=conditions,
                    estimated_yield_percent=step_data.get('scale_adjusted_yield', 75.0),
                    estimated_cost_usd=step_data.get('cost_breakdown', {}).get('total_cost', 50.0)
                )
                
                steps.append(step)
                
            except Exception as e:
                logger.error(f"step_conversion_failed: {str(e)}")
                continue
        
        # Create route
        synthesis_route = SynthesisRoute(
            target_molecule=target_mol,
            starting_materials=starting_materials,
            steps=steps,
            overall_yield_percent=route_dict.get('scale_adjusted_overall_yield', 75.0),
            total_cost_usd=route_dict.get('total_cost_usd', 100.0),
            total_time_hours=route_dict.get('total_time_hours', 10.0),
            score=route_dict.get('score', 50.0),
            notes=f"Scale: {route_dict.get('scale', 'lab')}, Batch: {route_dict.get('batch_size_kg', 0.1)}kg"
        )
        
        return synthesis_route
