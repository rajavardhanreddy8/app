import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from services.claude_service import ClaudeService
from services.cost_database import CostDatabase
from services.enhanced_route_scorer import EnhancedRouteScorer
from services.yield_predictor import YieldPredictor

logger = logging.getLogger(__name__)


class SynthesisCopilot:
    """LLM-backed, route-aware copilot for synthesis optimization."""

    def __init__(self, claude_api_key: Optional[str] = None):
        try:
            self.claude_service = ClaudeService(api_key=claude_api_key)
        except Exception:
            logger.exception("Failed to initialize LLM service for copilot")
            self.claude_service = None

        self.route_scorer = EnhancedRouteScorer()
        self.cost_db = CostDatabase()
        self.yield_predictor = YieldPredictor()
        self.yield_predictor.load_model()

    async def process_query(
        self,
        user_query: str,
        current_route: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Process a natural-language optimization query."""

        if current_route is None:
            current_route = self._route_from_context(context)

        llm_answer = await self._answer_with_llm(user_query, current_route, context)
        if llm_answer:
            return llm_answer

        intent = await self._parse_intent_with_llm(user_query, current_route)
        if not intent or intent.get("action") == "general":
            intent = self._parse_intent_keyword(user_query)

        logger.info("Copilot intent: %s", intent)

        if intent["action"] == "combined_cost_yield":
            cost = await self._optimize_for_cost(current_route, intent)
            yield_plan = await self._optimize_for_yield(current_route, intent)
            return {
                "status": "success",
                "action": "combined_cost_yield",
                "suggestions": f"{cost.get('suggestions', '')}\n\n{yield_plan.get('suggestions', '')}",
                "route_aware": bool(current_route),
                "mode": "local_rule_based",
            }
        if intent["action"] == "reduce_cost":
            return await self._optimize_for_cost(current_route, intent)
        if intent["action"] == "increase_yield":
            return await self._optimize_for_yield(current_route, intent)
        if intent["action"] in ("reduce_steps", "speed_up"):
            return await self._optimize_for_speed(current_route, intent)
        if intent["action"] == "predict_yield":
            return self._predict_reaction_yield(intent.get("reaction"))
        if intent["action"] == "estimate_cost":
            return self._estimate_reaction_cost(intent.get("reaction"))
        if intent["action"] == "explain_route":
            return await self._explain_route(current_route)
        if intent["action"] == "suggest_alternatives":
            return await self._suggest_alternatives(current_route, intent)
        return await self._general_query(user_query, current_route, context)

    async def _explain_route(self, route: Optional[Dict]) -> Dict[str, Any]:
        if not route:
            return {"status": "error", "message": "No route provided"}

        lines = ["Route explanation:", self._route_digest(route)]
        drivers = self._cost_drivers(route)
        if drivers:
            lines.append("Key flags: " + "; ".join(drivers[:6]) + ".")
        return {"status": "success", "explanation": "\n".join(lines), "route_aware": True}

    async def _parse_intent_with_llm(self, query: str, route: Optional[Dict]) -> Optional[Dict]:
        """Reserved for structured intent parsing. Full answers use _answer_with_llm."""
        if not self._has_live_llm() or os.getenv("DEMO_MODE") == "true":
            return None
        return None

    def _parse_intent_keyword(self, query: str) -> Dict[str, Any]:
        query_lower = query.lower().strip()

        wants_cost = any(word in query_lower for word in ["cost", "cheaper", "price", "money", "expense"])
        wants_yield = any(word in query_lower for word in ["yield", "efficiency", "improve", "better"])
        if (wants_cost and wants_yield) or query_lower in {
            "both",
            '"reduce cost","improve yield"',
            "reduce cost, improve yield",
        }:
            return {"action": "combined_cost_yield", "priority": "high"}
        if wants_cost:
            return {"action": "reduce_cost", "priority": "high"}
        if wants_yield:
            return {"action": "increase_yield", "priority": "high"}
        if any(word in query_lower for word in ["steps", "faster", "speed", "quicker", "time"]):
            return {"action": "reduce_steps", "priority": "high"}
        if "predict" in query_lower:
            return {"action": "predict_yield", "query": query}
        if any(word in query_lower for word in ["explain", "why", "how", "tell me"]):
            return {"action": "explain_route", "query": query}
        if any(word in query_lower for word in ["alternative", "solvent", "green", "greener"]):
            return {"action": "suggest_alternatives", "query": query}
        return {"action": "general", "query": query}

    def _route_from_context(self, context: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not isinstance(context, dict):
            return None
        for key in ("route", "selected_route", "route_data"):
            if isinstance(context.get(key), dict):
                return context[key]
        route_info = context.get("route_info")
        if isinstance(route_info, str):
            try:
                parsed = json.loads(route_info)
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                return None
        return None

    def _has_live_llm(self) -> bool:
        if not self.claude_service or getattr(self.claude_service, "demo_mode", True):
            return False
        provider = getattr(self.claude_service, "provider", "anthropic")
        if provider == "openrouter":
            return getattr(self.claude_service, "openrouter_client", None) is not None
        return getattr(self.claude_service, "client", None) is not None

    async def _answer_with_llm(
        self,
        query: str,
        route: Optional[Dict[str, Any]],
        context: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not self._has_live_llm():
            return None

        system_prompt = (
            "You are SynthAI Copilot, a senior process chemistry assistant. "
            "Give practical, route-aware synthesis optimization advice. Prefer concrete reagent "
            "equivalents, catalyst loading ranges, solvent/concentration choices, yield bottlenecks, "
            "cost drivers, safety/scale warnings, and verification experiments. Mark estimates clearly."
        )
        extra_context = ""
        if isinstance(context, dict) and context.get("route_info") and not route:
            extra_context = f"\nUser pasted context:\n{context['route_info']}"
        user_prompt = (
            f"User question:\n{query}\n\n"
            f"Current route summary:\n{self._route_digest(route) or 'No structured route was provided.'}"
            f"{extra_context}\n\n"
            "Answer with Markdown headings and bullets. Include a 'Next checks' section."
        )

        try:
            provider = getattr(self.claude_service, "provider", "anthropic")
            if provider == "openrouter":
                copilot_models = getattr(
                    self.claude_service,
                    "openrouter_copilot_models",
                    [getattr(self.claude_service, "openrouter_model", "google/gemini-2.0-flash-lite-001")],
                )
                response = await self.claude_service.openrouter_client.chat.completions.create(
                    model=copilot_models[0],
                    max_tokens=1600,
                    temperature=0.2,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    extra_body=self.claude_service._openrouter_extra_body(copilot_models),
                )
                content = response.choices[0].message.content or ""
                model = getattr(response, "model", None) or copilot_models[0]
                self.claude_service.last_model_used = model
                self.claude_service.last_error = None
            else:
                response = await self.claude_service.client.messages.create(
                    model=getattr(self.claude_service, "model", "claude-sonnet-4-20250514"),
                    max_tokens=1600,
                    temperature=0.2,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                content = "\n".join(
                    block.text for block in response.content if getattr(block, "type", None) == "text"
                )
                model = getattr(self.claude_service, "model", "anthropic")

            return {
                "status": "success",
                "action": "llm_copilot_answer",
                "provider": provider,
                "model": model,
                "suggestions": content.strip(),
                "route_aware": bool(route),
            }
        except Exception as exc:
            logger.warning("copilot_llm_failed", exc_info=exc)
            return None

    def _step_yield(self, step: Dict[str, Any]) -> float:
        value = step.get("estimated_yield_percent", step.get("estimated_yield", 75))
        try:
            return float(value)
        except (TypeError, ValueError):
            return 75.0

    def _route_yield(self, route: Optional[Dict[str, Any]]) -> Optional[float]:
        if not route:
            return None
        direct = route.get("overall_yield_percent", route.get("overall_yield"))
        if isinstance(direct, (int, float)):
            return float(direct)
        steps = route.get("steps") or []
        if not steps:
            return None
        total = 1.0
        for step in steps:
            total *= max(0, min(100, self._step_yield(step))) / 100
        return round(total * 100, 2)

    def _route_cost(self, route: Optional[Dict[str, Any]]) -> float:
        if not route:
            return 0.0
        direct = route.get("total_cost_usd")
        if isinstance(direct, (int, float)):
            return float(direct)
        return sum(float(step.get("estimated_cost_usd", 0) or 0) for step in route.get("steps", []))

    def _route_digest(self, route: Optional[Dict[str, Any]]) -> str:
        if not route:
            return ""
        route_yield = self._route_yield(route)
        lines = [
            f"Product: {route.get('target_molecule') or route.get('target_smiles') or route.get('product') or 'unknown'}",
            f"Overall yield: {route_yield if route_yield is not None else 'unknown'}%",
            f"Estimated cost: ${self._route_cost(route):,.2f}",
            f"Steps: {len(route.get('steps', []))}",
        ]
        for idx, step in enumerate(route.get("steps", []), start=1):
            conditions = step.get("conditions", {}) or {}
            lines.append(
                "Step {idx}: {rxn}; yield {yield_pct:.1f}%; cost ${cost:,.2f}; "
                "solvent {solvent}; catalyst {catalyst}; temp {temp}".format(
                    idx=idx,
                    rxn=step.get("reaction_type", "transformation"),
                    yield_pct=self._step_yield(step),
                    cost=float(step.get("estimated_cost_usd", 0) or 0),
                    solvent=conditions.get("solvent", "unknown"),
                    catalyst=conditions.get("catalyst", "none"),
                    temp=conditions.get("temperature_celsius", "unknown"),
                )
            )
        return "\n".join(lines)

    def _quantity_rows(self, route: Dict[str, Any], batch_mol: float = 0.10) -> List[str]:
        rows = []
        for idx, step in enumerate(route.get("steps", []), start=1):
            reactants = step.get("reactants") or []
            if not isinstance(reactants, list):
                reactants = [reactants]
            for reactant_idx, reactant in enumerate(reactants):
                eq = 1.0 if reactant_idx == 0 else 1.1
                amount = batch_mol * 1000 * eq
                rows.append(
                    f"- Step {idx}: {reactant} at {eq:g} equiv, about {amount:.1f} mmol on a 0.10 mol basis."
                )
            conditions = step.get("conditions", {}) or {}
            catalyst = conditions.get("catalyst")
            if catalyst and str(catalyst).lower() not in {"none", "n/a", "unknown"}:
                rows.append(f"- Step {idx}: {catalyst} at about 1-5 mol% screen; start with 2 mol% for cost checks.")
            solvent = conditions.get("solvent")
            if solvent:
                rows.append(f"- Step {idx}: {solvent} at 5-10 volumes or about 0.1-0.2 M until solubility is proven.")
        return rows

    def _cost_drivers(self, route: Optional[Dict[str, Any]]) -> List[str]:
        drivers = []
        if not route:
            return drivers
        route_yield = self._route_yield(route)
        route_cost = self._route_cost(route)
        if route_yield is not None and route_yield < 25:
            drivers.append(f"overall yield is only {route_yield:.1f}%, so losses multiply cost heavily")
        if route_cost > 10000:
            drivers.append(f"estimated route cost is ${route_cost:,.0f}, an outlier for normal route scouting")
        for idx, step in enumerate(route.get("steps", []), start=1):
            conditions = step.get("conditions", {}) or {}
            catalyst = str(conditions.get("catalyst", ""))
            solvent = str(conditions.get("solvent", ""))
            if re.search(r"\b(pd|palladium|pt|platinum|rh|ir)\b", catalyst, re.I):
                drivers.append(f"step {idx} uses precious-metal catalyst {catalyst}")
            if solvent.lower() in {"dmf", "nmp", "dmac", "dcm", "chloroform", "benzene"}:
                drivers.append(f"step {idx} uses scale-unfriendly solvent {solvent}")
            if self._step_yield(step) < 70:
                drivers.append(f"step {idx} yield is {self._step_yield(step):.1f}%")
        return drivers

    async def _optimize_for_cost(self, route: Optional[Dict], intent: Dict) -> Dict[str, Any]:
        suggestions = ["Cost optimization analysis:"]

        if not route or not route.get("steps"):
            suggestions.extend([
                "- I do not have a structured route attached, so this is a local rule-based answer.",
                "- Send the route JSON or generate/select a planner route and I can rank exact cost drivers.",
                "- First checks: lower catalyst loading, reduce solvent volumes to 5-10 V, avoid chromatography, and compare commodity starting materials.",
                "- If the route uses Pd, screen 1-3 mol% Pd(dppf)Cl2/Pd(OAc)2 systems before moving to Ni/Cu alternatives.",
            ])
            return {
                "status": "success",
                "action": "cost_optimization",
                "suggestions": "\n".join(suggestions),
                "route_aware": False,
                "mode": "local_rule_based",
            }

        route_yield = self._route_yield(route)
        route_cost = self._route_cost(route)
        suggestions.append(f"- Current route estimate: {route_yield:.1f}% total yield, ${route_cost:,.2f} total cost.")
        drivers = self._cost_drivers(route)
        if drivers:
            suggestions.append("- Main cost drivers: " + "; ".join(drivers[:5]) + ".")

        for idx, step in enumerate(route["steps"], start=1):
            conditions = step.get("conditions", {}) or {}
            catalyst = conditions.get("catalyst", "")
            if any(token in str(catalyst).lower() for token in ["pd", "palladium", "platinum", "pt"]):
                suggestions.append(
                    f"- Step {idx}: keep {catalyst} only if it gives a clear yield/selectivity benefit; screen 1, 2, and 5 mol% loading, then compare Ni/Cu after substrate compatibility checks."
                )
            solvent = str(conditions.get("solvent", ""))
            solvent_lower = solvent.lower()
            if solvent_lower in {"dcm", "chloroform"}:
                suggestions.append(f"- Step {idx}: replace {solvent} screen with EtOAc, 2-MeTHF, CPME, or MTBE where solubility allows.")
            elif solvent_lower in {"dmf", "nmp", "dmac"}:
                suggestions.append(f"- Step {idx}: {solvent} is expensive to remove at scale; screen MeCN, 2-MeTHF, CPME, toluene, or aqueous alcohol mixtures.")

        quantity_lines = self._quantity_rows(route)
        if quantity_lines:
            suggestions.append("Estimated quantities to start cost review:")
            suggestions.extend(quantity_lines[:10])
        suggestions.append("- Cost target: improve the worst step yield first, because every 10 percentage-point gain upstream reduces downstream material burn.")
        suggestions.append("- Process target: replace column chromatography with crystallization, slurry wash, or pH extraction before trusting any cost number.")

        return {
            "status": "success",
            "action": "cost_optimization",
            "suggestions": "\n".join(suggestions),
            "route_aware": True,
            "mode": "local_rule_based",
        }

    async def _optimize_for_yield(self, route: Optional[Dict], intent: Dict) -> Dict[str, Any]:
        suggestions = ["Yield improvement analysis:"]

        if not route or not route.get("steps"):
            suggestions.extend([
                "- I do not have a structured route attached, so I cannot identify the bottleneck step yet.",
                "- Send the route JSON or select a planner route so I can rank step yields.",
                "- Generic screen: equivalents 1.0/1.05/1.2, concentration 0.05-0.5 M, temperature +/-20 C, dry vs wet solvent, and crude purity by LCMS/HPLC after each step.",
            ])
            return {
                "status": "success",
                "action": "yield_optimization",
                "suggestions": "\n".join(suggestions),
                "route_aware": False,
                "mode": "local_rule_based",
            }

        route_yield = self._route_yield(route)
        suggestions.append(f"- Current total yield estimate: {route_yield:.1f}%. This is low for industry if the cost estimate is also high.")
        bottlenecks = sorted(enumerate(route.get("steps", []), start=1), key=lambda item: self._step_yield(item[1]))

        for idx, step in enumerate(route["steps"], start=1):
            est_yield = self._step_yield(step)
            if est_yield < 75:
                conditions = step.get("conditions", {}) or {}
                suggestions.append(
                    f"- Step {idx} ({step.get('reaction_type', 'transformation')}): {est_yield:.1f}% predicted. Screen solvent/base/catalyst first; current solvent={conditions.get('solvent', 'unknown')}, catalyst={conditions.get('catalyst', 'none')}."
                )
        if bottlenecks:
            idx, _step = bottlenecks[0]
            suggestions.append(
                f"- Bottleneck priority: step {idx}. Do a small DOE around concentration, temperature, equivalents, and hold time before changing route topology."
            )
        suggestions.extend([
            "- Check mass balance, not only isolated yield: quantify unreacted starting material, product, major impurity, and decomposition.",
            "- Tighten workup: pH window, brine/salt break, solvent swap, and crystallization seed can raise isolated yield without new chemistry.",
            "- If total yield remains under 40%, search a convergent/disconnection alternative instead of optimizing a weak linear route.",
        ])
        return {
            "status": "success",
            "action": "yield_optimization",
            "suggestions": "\n".join(suggestions),
            "route_aware": True,
            "mode": "local_rule_based",
        }

    async def _optimize_for_speed(self, route: Optional[Dict], intent: Dict) -> Dict[str, Any]:
        suggestions = [
            "Cycle-time optimization:",
            "- Identify steps with overnight holds, solvent swaps, and chromatographic purification.",
            "- Telescope compatible steps only after confirming impurity carryover does not damage yield or isolation.",
            "- Prefer crystallization/slurry wash over column purification for scale.",
        ]
        if route and route.get("steps"):
            suggestions.append(f"- This route has {len(route['steps'])} steps; target the slowest workup first, not necessarily the reaction time.")
        return {
            "status": "success",
            "action": "speed_optimization",
            "suggestions": "\n".join(suggestions),
            "route_aware": bool(route),
            "mode": "local_rule_based",
        }

    def _predict_reaction_yield(self, reaction: Optional[Dict]) -> Dict[str, Any]:
        if not reaction:
            return {"status": "error", "message": "No reaction provided"}
        return {"status": "success", "predicted_yield": self.yield_predictor.predict(reaction)}

    def _estimate_reaction_cost(self, reaction: Optional[Dict]) -> Dict[str, Any]:
        return {"status": "success", "estimated_cost": 50.0}

    async def _suggest_alternatives(self, route: Optional[Dict], intent: Dict) -> Dict[str, Any]:
        suggestions = [
            "Greener alternative suggestions:",
            "- DCM/chloroform: screen EtOAc, 2-MeTHF, CPME, MTBE, or toluene depending on polarity and phase behavior.",
            "- DMF/NMP/DMAc: screen MeCN, 2-MeTHF, CPME, toluene, ethanol/water, or isopropanol/water; confirm solubility and conversion.",
            "- Benzene: replace with toluene, heptane/toluene, EtOAc, or anisole where temperature allows.",
            "- Pd-heavy coupling: compare lower Pd loading, ligand swap, base/solvent screen, then Ni/Cu only if the substrate class supports it.",
        ]
        if route and route.get("steps"):
            drivers = self._cost_drivers(route)
            if drivers:
                suggestions.append("- Route-specific flags: " + "; ".join(drivers[:5]) + ".")
            suggestions.append("Estimated quantities:")
            suggestions.extend(self._quantity_rows(route)[:10])
        return {"status": "success", "suggestions": "\n".join(suggestions), "route_aware": bool(route)}

    async def _general_query(self, query: str, route: Optional[Dict], context: Optional[Dict]) -> Dict[str, Any]:
        tokens = re.findall(r"[A-Za-z0-9@\+\-\[\]\(\)=#$\\/%.]+", query)
        molecule_hint = max(tokens, key=len) if tokens else None
        suggestions = [
            "Copilot local analysis:",
            "- The live LLM client is not active, so this answer is generated by the route-aware local advisor.",
        ]
        if molecule_hint and len(molecule_hint) > 15:
            suggestions.append(f"- Molecule/query detected: {molecule_hint}. Attach a planner route so I can identify exact disconnections and cost drivers.")
        if route:
            suggestions.append(self._route_digest(route))
            suggestions.append("- Ask 'reduce cost and improve yield' to get a ranked action list for this route.")
        else:
            suggestions.append("- Generate a planner route first, then Copilot will automatically use that selected route as context.")
        return {
            "status": "success",
            "response": "Local route-aware copilot answer.",
            "suggestions": "\n".join(suggestions),
            "route_aware": bool(route),
            "mode": "local_rule_based",
        }
