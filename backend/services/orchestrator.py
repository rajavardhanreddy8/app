import ast
import json
import os
import sys
import logging
import structlog
import time
from typing import Dict, Any, List, Optional
from models.chemistry import (
    MolecularStructure,
    ReactionCondition,
    ReactionStep,
    SynthesisRequest,
    SynthesisResponse,
    SynthesisRoute,
)
from services.claude_service import ClaudeService
from services.molecular_service import MolecularService, normalize_reaction_fields  
from services.synthesis_planner import SynthesisPlanner
from services.retrosynthesis_engine import RetrosynthesisEngine
from services.scale_aware_optimizer import ScaleAwareOptimizer
from services.advanced_cost_model import AdvancedCostModel
from models import get_yield_predictor
from services.condition_predictor import ConditionPredictor
from services.enhanced_route_scorer import EnhancedRouteScorer
from services.process_constraints_engine import ProcessConstraintsEngine
from services.equipment_spec_engine import EquipmentSpecEngine
from services.chemical_graph import ChemicalGraph
from services.mcts_search import MCTSSearch
from services.green_chemistry_metrics import get_green_metrics
from services.impurity_tracker import ImpurityTracker
from services.telescoping_analyzer import TelescopingAnalyzer

# Phase 11: Industrial Acceptability Gate (optional import)
try:
    from services.industrial_acceptability_engine import IndustrialAcceptabilityEngine
    _ACCEPTABILITY_ENGINE_AVAILABLE = True
except ImportError:
    _ACCEPTABILITY_ENGINE_AVAILABLE = False

# Phase 12: Byproduct, Selectivity, and Reversibility Engine
try:
    from services.byproduct_selectivity_engine import ByproductSelectivityEngine
    _BYPRODUCT_ENGINE_AVAILABLE = True
except ImportError:
    _BYPRODUCT_ENGINE_AVAILABLE = False

# Phase 12: Byproduct, Selectivity, and Reversibility Engine
try:
    from services.byproduct_selectivity_engine import ByproductSelectivityEngine
    _BYPRODUCT_ENGINE_AVAILABLE = True
except ImportError:
    _BYPRODUCT_ENGINE_AVAILABLE = False

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
        self.yield_predictor = get_yield_predictor()
        self.condition_predictor = ConditionPredictor()
        self.route_scorer = EnhancedRouteScorer()
        self.impurity_tracker = ImpurityTracker()
        self.telescoping_analyzer = TelescopingAnalyzer()
        
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
        # yield_predictor is already loaded by get_yield_predictor() singleton
        if hasattr(self.yield_predictor, 'load_model'):
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
            logger.info("graph_init_status", initialized=False, molecules=0, reactions=0)
            return

        molecules = 0
        reactions_count = 0

        try:
            logger.info("initializing_chemical_graph_from_mongodb")

            reactions = await self.db.reactions.find({}, {"_id": 0}).to_list(2000)
            reactions_count = len(reactions)
            logger.info("loaded_reactions_from_db", reactions=reactions_count)

            self.chem_graph = ChemicalGraph()
            self.chem_graph.build_from_reactions(reactions)

            stats = self.chem_graph.get_graph_stats()
            molecules = int(stats.get("num_molecules", 0))
            reactions_count = int(stats.get("num_reactions", reactions_count))
            self._graph_initialized = True

        except Exception as e:
            self.chem_graph = None
            self._graph_initialized = False
            logger.error("chemical_graph_init_failed", error=str(e))

        logger.info(
            "graph_init_status",
            initialized=bool(self._graph_initialized),
            molecules=molecules,
            reactions=reactions_count,
        )

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
            if not self.chem_graph:
                logger.error("mcts_search_failed", error="chemical graph unavailable")
                return []

            if not self.mcts_engine or self.mcts_engine.pharma_mode != pharma_mode:
                self.mcts_engine = MCTSSearch(
                    chemical_graph=self.chem_graph,
                    scorer=self.route_scorer,
                    constraints_engine=self.constraints_engine,
                    pharma_mode=pharma_mode
                )

            routes = self.mcts_engine.search(
                target_molecule=target_smiles,
                max_iterations=300,
                max_depth=6
            )

            logger.info("mcts_generated_routes", routes=len(routes), target_smiles=target_smiles)
            return routes[:num_routes]

        except Exception as e:
            logger.error(
                "mcts_search_failed",
                error=str(e),
                target_smiles=target_smiles,
                num_routes=num_routes,
                pharma_mode=pharma_mode,
            )
            return []

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
        
        # Step 3: Use structured Claude tool output
        parsed_data = claude_response.get("structured_content")
        if not parsed_data and claude_response.get("content"):
            # Backward compatibility path (demo mode or legacy payload)
            try:
                parsed_data = json.loads(claude_response["content"])
            except Exception:
                parsed_data = None

        # Step 4: Build structured synthesis routes
        routes = []
        if parsed_data:
            routes = self.synthesis_planner.build_synthesis_routes(
                target_smiles=request.target_smiles,
                claude_response=parsed_data,
                optimize_for=request.optimize_for
            )
            for route in routes:
                route.llm_metadata = {
                    **(route.llm_metadata or {}),
                    **(claude_response.get("metadata") or {}),
                }
        
        # Step 4: Enrich every route with process-development intelligence.
        routes, enrichment_metadata = self._enrich_synthesis_routes(
            routes,
            request=request,
            scale=request.scale,
        )

        # Step 5: Create response
        computation_time = time.time() - start_time

        response = SynthesisResponse(
            target_smiles=request.target_smiles,
            routes=routes,
            computation_time_seconds=round(computation_time, 2),
            tokens_used=claude_response["usage"]["total_tokens"],
            metadata={
                "computation_time_seconds": round(computation_time, 2),
                "enrichment_timing": enrichment_metadata.get("timing", {}),
                "models_used": enrichment_metadata.get("models_used", []),
                "llm": claude_response.get("metadata") or self.claude_service.status_snapshot(),
            },
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
        pharma_mode: bool = False,  # Phase 5: Pharma enforcement
        use_industrial_gate: bool = False,  # Phase 11: Acceptability gate
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
                
                # Optional convergence feedback pass (if convergence engine is wired in)
                route_dict = self._apply_convergence_feedback_to_route(
                    route_dict,
                    request.optimize_for
                )

                # Phase 9: Sub-step 3f: Equipment-centric process design (hard feasibility)
                route_dict = self._evaluate_equipment_feasibility(route_dict, scale, batch_size_kg)
                if route_dict.get('equipment_rejected', False):
                    logger.info(f"route_rejected_by_equipment_constraints_{idx+1}")
                    continue
                
                # Sub-step 3g: Calculate industrial costs (with hybrid caching)
                route_dict = self._calculate_industrial_costs(route_dict, scale, batch_size_kg)

                # Phase 12: Sub-step 3g.5: Byproduct, Selectivity, and Reversibility Engine
                if _BYPRODUCT_ENGINE_AVAILABLE:
                    try:
                        _byproduct_engine = ByproductSelectivityEngine()
                        route_dict = _byproduct_engine.evaluate(route_dict, pharma_mode=pharma_mode)
                    except Exception as _bp_err:
                        logger.warning('byproduct_engine_failed: %s', _bp_err)

                # Phase 11: Sub-step 3h: Industrial Acceptability Gate
                if use_industrial_gate and _ACCEPTABILITY_ENGINE_AVAILABLE:
                    try:
                        _ia_mode = "pharma" if pharma_mode else request.optimize_for or "balanced"
                        _ia_engine = IndustrialAcceptabilityEngine()
                        route_dict['industrial_acceptability'] = _ia_engine.evaluate(
                            route_dict, mode=_ia_mode
                        )
                    except Exception as _ia_err:
                        logger.warning("industrial_gate_failed: %s", _ia_err)
                        route_dict['industrial_acceptability'] = None

                # Sub-step 3i: Calculate composite score (includes constraint/equipment penalties)
                route_dict['score'] = self._calculate_composite_score(
                    route_dict,
                    request.optimize_for
                )

                optimized_routes.append(route_dict)
                
            except Exception as e:
                logger.error(f"failed_to_optimize_route_{idx+1}: {str(e)}")
                continue
        
        # Step 4: Enrich routes with the same process-development intelligence as normal mode.
        optimized_routes, enrichment_metadata = self._enrich_route_dicts(
            optimized_routes,
            request=request,
            scale=scale,
        )
        
        # Step 5: Convert to SynthesisRoute objects
        final_routes = []
        for route_dict in optimized_routes[:num_routes]:
            try:
                synthesis_route = self._convert_dict_to_synthesis_route(route_dict, request.target_smiles)
                final_routes.append(synthesis_route)
            except Exception as e:
                logger.error(f"failed_to_convert_route: {str(e)}")
                continue
        
        # Step 5a: Attach green chemistry metrics to each final route
        green = get_green_metrics()
        for synthesis_route in final_routes:
            try:
                route_dict_for_green = {
                    "steps": [
                        {
                            "reactants": [r.smiles for r in step.reactants],
                            "product": step.product.smiles,
                            "conditions": {
                                "time_hours": (step.conditions.time_hours or 4.0)
                                if step.conditions else 4.0
                            },
                        }
                        for step in synthesis_route.steps
                    ]
                }
                gm = green.calculate(route_dict_for_green, scale=scale)
                synthesis_route.green_metrics = gm.to_dict()
            except Exception as _gm_err:
                logger.warning(f"green_metrics_advanced_failed: {_gm_err}")

        # Step 6: Create response
        computation_time = time.time() - start_time

        # Phase 11: Group routes by industrial status when gate is active
        grouped: Optional[Dict[str, Any]] = None
        if use_industrial_gate:
            grouped = self._group_routes_by_acceptability(final_routes)

        response = SynthesisResponse(
            target_smiles=request.target_smiles,
            routes=final_routes,
            computation_time_seconds=round(computation_time, 2),
            tokens_used=0,
            metadata={
                "computation_time_seconds": round(computation_time, 2),
                "enrichment_timing": enrichment_metadata.get("timing", {}),
                "models_used": enrichment_metadata.get("models_used", []),
                "industrial_gate_active": use_industrial_gate,
                "grouped_routes": grouped,
            },
        )

        logger.info(
            "advanced_synthesis_planning_complete",
            num_routes=len(final_routes),
            computation_time=computation_time,
            industrial_gate=use_industrial_gate,
        )

        return response

    def _enrich_synthesis_routes(
        self,
        routes: List[SynthesisRoute],
        request: SynthesisRequest,
        scale: str = "lab",
    ) -> tuple[List[SynthesisRoute], Dict[str, Any]]:
        route_dicts = [route.model_dump() for route in routes]
        enriched_dicts, metadata = self._enrich_route_dicts(route_dicts, request=request, scale=scale)
        enriched_routes: List[SynthesisRoute] = []
        for route_dict in enriched_dicts:
            try:
                enriched_routes.append(SynthesisRoute.model_validate(route_dict))
            except Exception as exc:
                logger.warning("route_enrichment_validation_failed", error=str(exc))
        return enriched_routes, metadata

    def _enrich_route_dicts(
        self,
        routes: List[Dict[str, Any]],
        request: SynthesisRequest,
        scale: str = "lab",
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        timing: Dict[str, int] = {}
        models_used = ["condition_prior"]
        routes = [self._normalize_route_dict(route) for route in routes]

        t0 = time.perf_counter()
        for route in routes:
            self._enrich_conditions(route)
        timing["condition_intelligence_ms"] = int((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        if getattr(request, "include_green_metrics", True):
            green = get_green_metrics()
            for route in routes:
                try:
                    route["green_metrics"] = green.calculate(route, scale=scale).to_dict()
                except Exception as exc:
                    logger.warning("green_metrics_failed", error=str(exc))
                    route["green_metrics"] = {
                        "pmi": None,
                        "atom_economy_percent": None,
                        "e_factor": None,
                        "route_type": "unknown",
                        "convergence_score": 0,
                        "pmi_rating": "unknown",
                    }
            models_used.append("green_metrics_v1")
        timing["green_metrics_ms"] = int((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        if getattr(request, "include_impurity_analysis", True):
            for route in routes:
                try:
                    impurity_result = self.impurity_tracker.propagate_route(route)
                    route["impurity_analysis"] = {
                        "overall_impurity_risk": impurity_result["overall_impurity_risk"],
                        "ich_m7_assessment_required": impurity_result["ich_m7_assessment_required"],
                        "gti_flags": impurity_result["gti_flags"],
                        "accumulated_impurities": impurity_result["accumulated_impurities"],
                        "purge_points": impurity_result["purge_points"],
                        "recommended_purification": impurity_result.get("recommended_additional_purification", []),
                    }
                except Exception as exc:
                    logger.warning("impurity_analysis_failed", error=str(exc))
                    route["impurity_analysis"] = {
                        "overall_impurity_risk": "unknown",
                        "ich_m7_assessment_required": False,
                        "gti_flags": [],
                        "accumulated_impurities": [],
                        "purge_points": [],
                    }
            models_used.append("impurity_rules")
        timing["impurity_ms"] = int((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        if getattr(request, "include_telescoping", True):
            for route in routes:
                try:
                    tele_result = self.telescoping_analyzer.analyze_route_telescoping(route)
                    route["telescoping"] = {
                        "telescopable_pairs": [list(pair) for pair in tele_result.get("telescopable_pairs", [])],
                        "total_pmi_reduction": tele_result.get("total_pmi_reduction", 0),
                        "total_time_reduction_hours": tele_result.get("total_time_reduction_hours", 0),
                        "recommended_sequence": tele_result.get("recommended_sequence", ""),
                    }
                except Exception as exc:
                    logger.warning("telescoping_analysis_failed", error=str(exc))
                    route["telescoping"] = {
                        "telescopable_pairs": [],
                        "total_pmi_reduction": 0,
                        "total_time_reduction_hours": 0,
                        "recommended_sequence": "",
                    }
            models_used.append("telescoping_rules")
        timing["telescoping_ms"] = int((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        optimize_for = getattr(request, "optimize_for", "balanced")
        stage = getattr(request, "stage", "phase_2")
        for route in routes:
            try:
                score_result = self.route_scorer.score_route_unified(
                    route,
                    optimize_for=optimize_for,
                    stage=stage,
                )
                route["score"] = score_result["score"]
                route["score_breakdown"] = score_result["dimension_scores"]
                route["improvement_targets"] = score_result["improvement_targets"]
            except Exception as exc:
                logger.warning("unified_scoring_failed", error=str(exc))
        routes.sort(key=lambda item: item.get("score", 0), reverse=True)
        timing["scoring_ms"] = int((time.perf_counter() - t0) * 1000)
        models_used.append("unified_scorer_v1")

        self._attach_quality_metadata(routes, request=request, models_used=models_used)
        models_used.append("quality_evidence_v1")

        logger.info("enrichment_timing", **timing)
        return routes, {"timing": timing, "models_used": models_used}

    def _attach_quality_metadata(
        self,
        routes: List[Dict[str, Any]],
        request: SynthesisRequest,
        models_used: List[str],
    ) -> None:
        """Attach source, confidence, uncertainty, and review metadata."""
        for route in routes:
            llm_meta = route.get("llm_metadata") or {}
            llm_mode = str(llm_meta.get("mode") or "").lower()
            route_type = str(route.get("route_type") or "").lower()
            if "demo" in llm_mode:
                generation_source = "demo"
            elif llm_meta:
                generation_source = "llm"
            elif route_type == "retrosynthesis":
                generation_source = "rules"
            else:
                generation_source = "hybrid"

            route_warnings: List[str] = []
            if generation_source == "demo":
                route_warnings.append(
                    "Demo or fallback route: use only for workflow validation until reviewed against literature."
                )
            if route.get("improvement_targets"):
                route_warnings.extend([str(item) for item in route.get("improvement_targets", [])])

            step_confidences: List[str] = []
            yield_lowers: List[float] = []
            yield_uppers: List[float] = []

            for idx, step in enumerate(route.get("steps", []), start=1):
                yield_prediction = step.get("yield_prediction") or {}
                conditions = step.get("predicted_conditions") or step.get("conditions") or {}
                condition_confidence = conditions.get("confidence")
                yield_confidence = yield_prediction.get("confidence_level")

                confidence = self._combine_confidence([yield_confidence, condition_confidence])
                step_confidences.append(confidence)

                lower = yield_prediction.get("lower_bound")
                upper = yield_prediction.get("upper_bound")
                interval = yield_prediction.get("confidence_interval")
                step_uncertainty = None
                if lower is not None and upper is not None:
                    step_uncertainty = {
                        "yield_percent": {
                            "lower": lower,
                            "upper": upper,
                            "interval": interval if interval is not None else round(float(upper) - float(lower), 1),
                        }
                    }
                    yield_lowers.append(max(0.0, float(lower)) / 100.0)
                    yield_uppers.append(min(100.0, float(upper)) / 100.0)

                step_warnings = []
                for key in ("sanity_flags", "safety_warnings", "feasibility_notes"):
                    step_warnings.extend(str(item) for item in step.get(key, []) if item)
                if "fallback" in str(yield_prediction.get("model_decision") or yield_prediction.get("model") or "").lower():
                    step_warnings.append("Yield estimate used fallback logic; verify experimentally.")
                if condition_confidence == "low" or conditions.get("fallback"):
                    step_warnings.append("Condition estimate used low-confidence or fallback logic.")

                step["prediction_source"] = {
                    "route_generation": generation_source,
                    "yield": yield_prediction.get("model") or ("llm_or_demo_payload" if llm_meta else "heuristic_or_route_input"),
                    "conditions": conditions.get("source") or conditions.get("model_decision") or "condition_prior",
                    "cost": "cost_model_or_route_estimate",
                    "safety": "rules_and_process_constraints",
                }
                step["confidence"] = confidence
                step["uncertainty"] = step_uncertainty
                step["warnings"] = self._unique_strings(step_warnings)
                step["review_status"] = "needs_human_review"
                step["human_review_required"] = True
                step["evidence"] = {
                    "source_type": generation_source,
                    "source_name": llm_meta.get("model") or route.get("route_type") or "SynthAI internal engines",
                    "model_version": self._yield_model_version(),
                    "data_version": self._data_version(),
                    "notes": [
                        f"Step {idx} requires chemist review before experimental use.",
                    ],
                }
                route_warnings.extend(step["warnings"])

            route_confidence = self._combine_confidence(step_confidences)
            route_uncertainty = None
            if yield_lowers and yield_uppers:
                overall_lower = 100.0
                overall_upper = 100.0
                for value in yield_lowers:
                    overall_lower *= value
                for value in yield_uppers:
                    overall_upper *= value
                route_uncertainty = {
                    "overall_yield_percent": {
                        "lower": round(overall_lower, 1),
                        "upper": round(overall_upper, 1),
                    }
                }

            route["prediction_source"] = {
                "route_generation": generation_source,
                "scoring": "unified_scorer_v1",
                "green_metrics": "rules" if route.get("green_metrics") else None,
                "impurity": "rules" if route.get("impurity_analysis") else None,
                "models_used": list(models_used),
            }
            route["confidence"] = route_confidence
            route["uncertainty"] = route_uncertainty
            route["warnings"] = self._unique_strings(route_warnings)[:12]
            route["review_status"] = "needs_human_review"
            route["human_review_required"] = True
            route["evidence"] = {
                "source_type": generation_source,
                "source_name": llm_meta.get("model") or route.get("route_type") or "SynthAI internal engines",
                "model_version": self._yield_model_version(),
                "condition_model_version": "condition_predictor_v1",
                "data_version": self._data_version(),
                "human_review_required": True,
            }

    def _combine_confidence(self, values: List[Optional[str]]) -> str:
        rank = {"low": 0, "medium": 1, "high": 2}
        clean = [str(value).lower() for value in values if value]
        if not clean:
            return "low"
        return min(clean, key=lambda value: rank.get(value, 0))

    def _unique_strings(self, values: List[str]) -> List[str]:
        seen = set()
        unique = []
        for value in values:
            if not value or value in seen:
                continue
            seen.add(value)
            unique.append(value)
        return unique

    def _yield_model_version(self) -> str:
        return str(getattr(self.yield_predictor, "model_version", type(self.yield_predictor).__name__))

    def _data_version(self) -> str:
        return os.getenv("SYNTHAI_DATA_VERSION", "local-artifacts")

    def _smiles_text(self, value: Any) -> str:
        if isinstance(value, dict):
            return str(value.get("smiles") or value.get("canonical_smiles") or "")
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("{") and text.endswith("}"):
                try:
                    parsed = ast.literal_eval(text)
                    if isinstance(parsed, dict):
                        return str(parsed.get("smiles") or parsed.get("canonical_smiles") or text)
                except Exception:
                    return text
            return text
        return str(value or "")

    def _normalize_route_dict(self, route: Dict[str, Any]) -> Dict[str, Any]:
        route = dict(route)
        route["steps"] = [self._normalize_step_dict(step) for step in route.get("steps", [])]
        route["num_steps"] = route.get("num_steps", len(route["steps"]))
        route["overall_yield"] = route.get("overall_yield", route.get("overall_yield_percent", route.get("scale_adjusted_overall_yield", 0)))
        route["overall_yield_percent"] = route.get("overall_yield_percent", route["overall_yield"])
        route["total_cost_usd"] = route.get("total_cost_usd", route.get("total_cost", 0))
        route["total_time_hours"] = route.get("total_time_hours", sum(
            (step.get("conditions") or {}).get("time_hours", 0) or 0
            for step in route["steps"]
        ))
        return route

    def _normalize_step_dict(self, step: Dict[str, Any]) -> Dict[str, Any]:
        step = dict(step)
        conditions = step.get("conditions") or step.get("predicted_conditions") or {}
        step["conditions"] = conditions if isinstance(conditions, dict) else {}
        if "estimated_yield" not in step:
            step["estimated_yield"] = step.get("estimated_yield_percent", step.get("predicted_yield", step.get("scale_adjusted_yield", 75.0)))
        if "estimated_yield_percent" not in step:
            step["estimated_yield_percent"] = step["estimated_yield"]
        if "estimated_cost_usd" not in step:
            step["estimated_cost_usd"] = step.get("cost_breakdown", {}).get("total_cost", 50.0)
        return step

    def _enrich_conditions(self, route: Dict[str, Any]) -> None:
        for step in route.get("steps", []):
            try:
                step.setdefault("conditions", {})
                conditions = self.condition_predictor.predict_conditions({
                    "reaction_type": step.get("reaction_type", ""),
                    "reactants": step.get("reactants", []),
                    "products": [step.get("product", "")],
                    "fast_prior_only": True,
                })
                existing_temp = step["conditions"].get("temperature_celsius")
                if existing_temp is None or abs(float(existing_temp) - 80.72176361083984) < 0.1:
                    step["conditions"]["temperature_celsius"] = conditions.get("temperature_celsius")
                if not step["conditions"].get("catalyst"):
                    step["conditions"]["catalyst"] = conditions.get("catalyst")
                if not step["conditions"].get("solvent"):
                    step["conditions"]["solvent"] = conditions.get("solvent")
                if not step["conditions"].get("time_hours"):
                    step["conditions"]["time_hours"] = conditions.get("time_hours")
                step["predicted_conditions"] = dict(step["conditions"])
                step["catalyst_intelligence"] = {
                    "hierarchy_level": conditions.get("hierarchy_level"),
                    "catalyst_type": conditions.get("catalyst_type"),
                    "catalyst_cost_per_kg": conditions.get("catalyst_cost_per_kg"),
                    "separation_method": conditions.get("separation_method"),
                    "reuse_cycles": conditions.get("reuse_cycles"),
                    "pd_removal_required": conditions.get("pd_removal_required", False),
                    "regulatory_note": conditions.get("regulatory_note"),
                    "notes": conditions.get("notes"),
                }
                step["safety_warnings"] = conditions.get("safety_warnings", [])
            except Exception as exc:
                logger.warning("condition_enrichment_failed", error=str(exc), reaction_type=step.get("reaction_type"))
    
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
        """Predict yields for each step using ML (specialist or global fallback)."""
        overall_yield = 100.0

        for step in route['steps']:
            try:
                reaction_dict = {
                    'reactants': step.get('reactants', []),
                    'products':  [step.get('product', '')],
                    'reaction_type': step.get('reaction_type', 'unknown'),
                    'temperature_celsius': step.get(
                        'predicted_conditions', {}
                    ).get('temperature_celsius', 25.0),
                    'catalyst': step.get('predicted_conditions', {}).get('catalyst', ''),
                    'solvent':  step.get('predicted_conditions', {}).get('solvent', ''),
                }

                # Use predict_with_uncertainty if available (SpecialistYieldPredictor),
                # otherwise fall back to plain predict()
                if hasattr(self.yield_predictor, 'predict_with_uncertainty'):
                    result = self.yield_predictor.predict_with_uncertainty(reaction_dict)
                    predicted_yield = result.get('yield_percent', 75.0)
                    step['yield_prediction'] = result   # full dict surfaced to frontend
                else:
                    predicted_yield = self.yield_predictor.predict(reaction_dict) or 75.0
                    step['yield_prediction'] = {
                        'yield_percent': round(predicted_yield, 1),
                        'model': 'global',
                    }

                step['predicted_yield'] = round(predicted_yield, 1)
                overall_yield *= (step['predicted_yield'] / 100.0)

            except Exception as e:
                logger.error(f"yield_prediction_failed: {str(e)}")
                step['predicted_yield'] = 75.0
                step['yield_prediction'] = {'yield_percent': 75.0, 'model': 'default'}
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
                reaction_dict = normalize_reaction_fields(reaction_dict)
                
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
                reaction_dict = normalize_reaction_fields(reaction_dict)
                
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

    def _apply_convergence_feedback_to_route(self, route: Dict, objective: str) -> Dict:
        """
        Apply convergence feedback with normalized step/reaction fields.

        This delegates to convergence_engine._apply_constraint_feedback_to_route()
        when a convergence engine is available.
        """
        convergence_engine = getattr(self, "convergence_engine", None)
        if not convergence_engine:
            return route

        normalized_route = normalize_reaction_fields(route)
        return convergence_engine._apply_constraint_feedback_to_route(
            normalized_route, objective
        )
    
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

        # Phase 12: Byproduct, selectivity, reversibility penalties
        bp_analysis = route.get('byproduct_analysis', {})
        bp_penalty = bp_analysis.get('byproduct_penalty', 0.0)
        sel_penalty = bp_analysis.get('selectivity_penalty', 0.0)
        rev_penalty = bp_analysis.get('reversibility_penalty', 0.0)
        imp_penalty = bp_analysis.get('impurity_risk_penalty', 0.0)
        
        # Combine Phase 12 penalties into one score component
        total_phase12_penalty = bp_penalty + sel_penalty + rev_penalty + imp_penalty
        phase12_score = max(0, 100 - total_phase12_penalty)
        
        # Weights based on optimization goal (Phase 5: added 10% for constraints, Phase 12: added 10% for phase12 metrics)
        if optimize_for == 'yield':
            weights = {'yield': 0.45, 'cost': 0.10, 'time': 0.05, 'steps': 0.10, 'constraints': 0.10, 'equipment': 0.10, 'phase12': 0.10}
        elif optimize_for == 'cost':
            weights = {'yield': 0.20, 'cost': 0.35, 'time': 0.05, 'steps': 0.10, 'constraints': 0.10, 'equipment': 0.10, 'phase12': 0.10}
        elif optimize_for == 'time':
            weights = {'yield': 0.20, 'cost': 0.10, 'time': 0.35, 'steps': 0.10, 'constraints': 0.05, 'equipment': 0.10, 'phase12': 0.10}
        else:  # balanced
            weights = {'yield': 0.25, 'cost': 0.25, 'time': 0.10, 'steps': 0.10, 'constraints': 0.10, 'equipment': 0.10, 'phase12': 0.10}
        
        composite_score = (
            weights['yield'] * yield_score +
            weights['cost'] * cost_score +
            weights['time'] * time_score +
            weights['steps'] * step_score +
            weights['constraints'] * constraint_score +
            weights['equipment'] * equipment_score +
            weights['phase12'] * phase12_score
        )
        
        return round(composite_score, 2)
    
    def _convert_dict_to_synthesis_route(self, route_dict: Dict, target_smiles: str) -> SynthesisRoute:
        """Convert internal route dict to SynthesisRoute Pydantic model."""
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
                    MolecularStructure(smiles=self._smiles_text(r))
                    for r in step_data.get('reactants', [])
                    if self._smiles_text(r)
                ]
                
                # Create product
                product = MolecularStructure(smiles=self._smiles_text(step_data.get('product', '')))
                
                # Create conditions
                cond_data = step_data.get('predicted_conditions', {})
                conditions = ReactionCondition(
                    temperature_celsius=cond_data.get('temperature_celsius', 25.0),
                    pressure_atm=cond_data.get('pressure_atm', step_data.get('pressure_atm', 1.0)),
                    solvent=cond_data.get('solvent', 'THF'),
                    catalyst=cond_data.get('catalyst'),
                    time_hours=step_data.get('predicted_time_hours', cond_data.get('time_hours', 4.0)),
                    solvent_volume_ml=cond_data.get('solvent_volume_ml'),
                    concentration_m=cond_data.get('concentration_m') or step_data.get('concentration_m'),
                    catalyst_loading_mol_percent=cond_data.get('catalyst_loading_mol_percent'),
                )
                
                # Create step
                step = ReactionStep(
                    reactants=reactants,
                    product=product,
                    reaction_type=step_data.get('reaction_type', 'Unknown'),
                    conditions=conditions,
                    estimated_yield_percent=step_data.get('scale_adjusted_yield', 75.0),
                    estimated_yield=step_data.get('estimated_yield', step_data.get('scale_adjusted_yield', 75.0)),
                    estimated_cost_usd=step_data.get('cost_breakdown', {}).get('total_cost', step_data.get('estimated_cost_usd', 50.0)),
                    reactant_quantities=step_data.get('reactant_quantities'),
                    catalyst_loading=step_data.get('catalyst_loading'),
                    solvent_amount=step_data.get('solvent_amount'),
                    concentration_m=step_data.get('concentration_m') or conditions.concentration_m,
                    batch_scale=step_data.get('batch_scale'),
                    cost_drivers=step_data.get('cost_drivers'),
                    feasibility_notes=step_data.get('feasibility_notes'),
                    sanity_flags=step_data.get('sanity_flags'),
                    catalyst_intelligence=step_data.get('catalyst_intelligence'),
                    safety_warnings=step_data.get('safety_warnings', []),
                    notes=step_data.get('notes'),
                    evidence=step_data.get('evidence'),
                    prediction_source=step_data.get('prediction_source'),
                    confidence=step_data.get('confidence'),
                    uncertainty=step_data.get('uncertainty'),
                    warnings=step_data.get('warnings'),
                    review_status=step_data.get('review_status', 'needs_human_review'),
                    human_review_required=step_data.get('human_review_required', True),
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
            overall_yield=route_dict.get('overall_yield', route_dict.get('scale_adjusted_overall_yield', 75.0)),
            total_cost_usd=route_dict.get('total_cost_usd', 100.0),
            total_time_hours=route_dict.get('total_time_hours', 10.0),
            score=route_dict.get('score', 50.0),
            notes=f"Scale: {route_dict.get('scale', 'lab')}, Batch: {route_dict.get('batch_size_kg', 0.1)}kg",
            green_metrics=route_dict.get('green_metrics'),
            impurity_analysis=route_dict.get('impurity_analysis'),
            telescoping=route_dict.get('telescoping'),
            score_breakdown=route_dict.get('score_breakdown'),
            improvement_targets=route_dict.get('improvement_targets'),
            evidence=route_dict.get('evidence'),
            prediction_source=route_dict.get('prediction_source'),
            confidence=route_dict.get('confidence'),
            uncertainty=route_dict.get('uncertainty'),
            warnings=route_dict.get('warnings'),
            review_status=route_dict.get('review_status', 'needs_human_review'),
            human_review_required=route_dict.get('human_review_required', True),
            industrial_acceptability=route_dict.get('industrial_acceptability'),
            byproduct_analysis=route_dict.get('byproduct_analysis'),
        )
        
        return synthesis_route

    def _group_routes_by_acceptability(self, routes: List) -> Dict[str, Any]:
        """
        Phase 11: Group SynthesisRoute objects by their industrial_acceptability status.

        Returns grouped dict with summary counts.
        """
        accepted:     List = []
        ard_required: List = []
        rejected:     List = []
        exploratory:  List = []

        for route in routes:
            # industrial_acceptability may be on the raw dict or pydantic model extra fields
            ia = None
            if hasattr(route, '__dict__'):
                ia = getattr(route, 'industrial_acceptability', None)
            if ia is None and hasattr(route, 'model_dump'):
                ia = route.model_dump().get('industrial_acceptability')
            if ia is None and isinstance(route, dict):
                ia = route.get('industrial_acceptability')

            status = (ia or {}).get('industrial_status', 'ard_required') if ia else 'ard_required'

            if status == 'accepted':
                accepted.append(route)
            elif status == 'ard_required':
                ard_required.append(route)
            elif status == 'exploratory_only':
                exploratory.append(route)
            else:  # rejected
                rejected.append(route)

        return {
            "accepted_routes":     accepted,
            "ard_required_routes": ard_required,
            "rejected_routes":     rejected,
            "exploratory_routes":  exploratory,
            "summary": {
                "accepted_count":     len(accepted),
                "ard_required_count": len(ard_required),
                "rejected_count":     len(rejected),
                "exploratory_count":  len(exploratory),
            },
        }
