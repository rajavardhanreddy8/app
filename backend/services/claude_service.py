import os
import json
import structlog
from typing import Optional, Any, Dict, List, Tuple

from anthropic import AsyncAnthropic
from pydantic import BaseModel, ValidationError

logger = structlog.get_logger()


class ConditionSchema(BaseModel):
    temperature_celsius: Optional[float] = None
    solvent: Optional[str] = None
    catalyst: Optional[str] = None
    time_hours: Optional[float] = None


class StepSchema(BaseModel):
    reactants: List[str]
    product: str
    reaction_type: str
    estimated_yield: float
    estimated_cost_usd: float
    conditions: ConditionSchema


class RouteSchema(BaseModel):
    starting_materials: List[str]
    steps: List[StepSchema]
    overall_yield: float
    total_cost_usd: float
    score: float
    notes: str


class SynthesisRouteSchema(BaseModel):
    routes: List[RouteSchema]


class ClaudeService:
    """Service for orchestrating Claude API interactions."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
        self.demo_mode = os.getenv('DEMO_MODE', 'false').lower() == 'true'

        # Bug Fix 3: Always initialize client attribute to avoid AttributeError
        self.client = None
        self.model = "claude-sonnet-4-20250514"  # Latest Claude Sonnet 4.5
        self.max_tokens = 4096

        if not self.demo_mode:
            if not self.api_key:
                logger.warning("ANTHROPIC_API_KEY not found, switching to demo mode")
                self.demo_mode = True
            else:
                try:
                    self.client = AsyncAnthropic(api_key=self.api_key)
                except Exception as e:
                    logger.error(f"Failed to initialize Claude client: {str(e)}, switching to demo mode")
                    self.demo_mode = True
                    self.client = None

    async def plan_synthesis(
        self,
        target_smiles: str,
        starting_materials: Optional[List[str]] = None,
        max_steps: int = 5,
        optimize_for: str = "balanced",
        tools: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """
        Plan synthesis route from starting materials to target using Anthropic tool use.

        Returns structured_content validated by SynthesisRouteSchema.
        """

        # Demo mode: Generate example routes based on common patterns
        if self.demo_mode:
            logger.info("Using demo mode for synthesis planning")
            return self._generate_demo_routes(target_smiles, max_steps, optimize_for)

        system_prompt = (
            "You are an expert organic chemist specialized in retrosynthetic analysis and "
            "synthesis planning. Produce practical, safe routes with realistic yields and costs. "
            "Always call the provided tool exactly once with complete fields."
        )

        starting_materials_text = starting_materials or ["Common commercially available building blocks"]

        user_message = (
            "Please plan synthesis routes from available starting materials to the target molecule.\n\n"
            f"Target SMILES: {target_smiles}\n"
            f"Starting Materials: {', '.join(str(sm) for sm in starting_materials_text)}\n"
            f"Maximum Steps: {max_steps}\n"
            f"Optimization Priority: {optimize_for}\n\n"
            "Provide 3-5 alternative routes ranked by the requested optimization objective."
        )

        tool_def = {
            "name": "plan_synthesis_routes",
            "description": "Return structured synthesis routes for the target molecule.",
            "input_schema": SynthesisRouteSchema.model_json_schema(),
        }

        request_tools = tools or [tool_def]

        logger.info(
            "requesting_synthesis_plan",
            target_smiles=target_smiles,
            max_steps=max_steps,
            optimize_for=optimize_for,
            tool_name="plan_synthesis_routes",
        )

        messages = [{"role": "user", "content": user_message}]

        try:
            response, usage = await self._request_tool_plan(
                messages=messages,
                system_prompt=system_prompt,
                tools=request_tools,
            )

            parsed, validation_error = self._extract_and_validate_tool_payload(response)

            # Validation retry once with corrective instruction.
            if parsed is None:
                retry_message = (
                    "Your previous tool output was invalid or incomplete for 'plan_synthesis_routes'. "
                    "Please call the tool again and include all required fields with correct types. "
                    f"Validation detail: {validation_error}"
                )
                retry_messages = messages + [{"role": "user", "content": retry_message}]
                retry_response, retry_usage = await self._request_tool_plan(
                    messages=retry_messages,
                    system_prompt=system_prompt,
                    tools=request_tools,
                )
                usage["input_tokens"] += retry_usage["input_tokens"]
                usage["output_tokens"] += retry_usage["output_tokens"]
                usage["total_tokens"] += retry_usage["total_tokens"]

                parsed, validation_error = self._extract_and_validate_tool_payload(retry_response)
                if parsed is None:
                    raise ValueError(f"Tool response validation failed after retry: {validation_error}")

            return {
                "content": json.dumps(parsed, indent=2),
                "structured_content": parsed,
                "usage": usage,
            }

        except Exception as e:
            logger.error("synthesis_plan_failed", error=str(e))
            raise

    async def _request_tool_plan(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        tools: List[Dict[str, Any]],
    ) -> Tuple[Any, Dict[str, int]]:
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system_prompt,
            messages=messages,
            tools=tools,
            tool_choice={"type": "tool", "name": "plan_synthesis_routes"},
        )

        usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
        }

        logger.info(
            "synthesis_plan_received",
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
        )

        return response, usage

    def _extract_and_validate_tool_payload(self, response: Any) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        payload = None
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == "plan_synthesis_routes":
                payload = getattr(block, "input", None)
                break

        if payload is None:
            return None, "Missing tool_use block for plan_synthesis_routes"

        try:
            validated = SynthesisRouteSchema.model_validate(payload)
            return validated.model_dump(), None
        except ValidationError as e:
            return None, str(e)

    def _generate_demo_routes(
        self,
        target_smiles: str,
        max_steps: int,
        optimize_for: str,
    ) -> Dict[str, Any]:
        """Generate demo synthesis routes for demonstration."""

        # Common building blocks
        starting_materials = [
            "c1ccccc1",  # benzene
            "CCO",  # ethanol
            "CC(=O)O",  # acetic acid
            "CC(C)=O",  # acetone
        ]

        # Generate 3 example routes
        routes_data = {
            "routes": [
                {
                    "starting_materials": ["c1ccccc1", "CC(=O)Cl"],
                    "steps": [
                        {
                            "reactants": ["c1ccccc1", "CC(=O)Cl"],
                            "product": "CC(=O)c1ccccc1",
                            "reaction_type": "Friedel-Crafts acylation",
                            "estimated_yield": 85,
                            "estimated_cost_usd": 45,
                            "conditions": {
                                "temperature_celsius": 0,
                                "solvent": "DCM",
                                "catalyst": "AlCl3",
                                "time_hours": 3,
                            },
                        },
                        {
                            "reactants": ["CC(=O)c1ccccc1"],
                            "product": target_smiles,
                            "reaction_type": "Functional group transformation",
                            "estimated_yield": 75,
                            "estimated_cost_usd": 60,
                            "conditions": {
                                "temperature_celsius": 25,
                                "solvent": "THF",
                                "time_hours": 6,
                            },
                        },
                    ],
                    "overall_yield": 63.75,
                    "total_cost_usd": 105,
                    "notes": "High-yielding route using common reagents",
                },
                {
                    "starting_materials": ["CCO", "CC(=O)O"],
                    "steps": [
                        {
                            "reactants": ["CCO", "CC(=O)O"],
                            "product": "CCOC(=O)C",
                            "reaction_type": "Esterification",
                            "estimated_yield": 88,
                            "estimated_cost_usd": 25,
                            "conditions": {
                                "temperature_celsius": 80,
                                "solvent": "None",
                                "catalyst": "H2SO4",
                                "time_hours": 4,
                            },
                        },
                        {
                            "reactants": ["CCOC(=O)C", "c1ccccc1"],
                            "product": target_smiles,
                            "reaction_type": "Nucleophilic substitution",
                            "estimated_yield": 70,
                            "estimated_cost_usd": 80,
                            "conditions": {
                                "temperature_celsius": 40,
                                "solvent": "DMF",
                                "time_hours": 8,
                            },
                        },
                    ],
                    "overall_yield": 61.6,
                    "total_cost_usd": 105,
                    "notes": "Cost-effective approach with good scalability",
                },
                {
                    "starting_materials": ["c1ccccc1", "CC(C)=O"],
                    "steps": [
                        {
                            "reactants": ["c1ccccc1"],
                            "product": "c1ccc(O)cc1",
                            "reaction_type": "Hydroxylation",
                            "estimated_yield": 80,
                            "estimated_cost_usd": 55,
                            "conditions": {
                                "temperature_celsius": 100,
                                "solvent": "H2O",
                                "catalyst": "Cu(II)",
                                "time_hours": 5,
                            },
                        },
                        {
                            "reactants": ["c1ccc(O)cc1", "CC(=O)Cl"],
                            "product": "CC(=O)Oc1ccccc1",
                            "reaction_type": "Acetylation",
                            "estimated_yield": 90,
                            "estimated_cost_usd": 40,
                            "conditions": {
                                "temperature_celsius": 25,
                                "solvent": "Pyridine",
                                "time_hours": 2,
                            },
                        },
                        {
                            "reactants": ["CC(=O)Oc1ccccc1"],
                            "product": target_smiles,
                            "reaction_type": "Carboxylation",
                            "estimated_yield": 75,
                            "estimated_cost_usd": 70,
                            "conditions": {
                                "temperature_celsius": 60,
                                "solvent": "THF",
                                "catalyst": "Pd/C",
                                "time_hours": 12,
                            },
                        },
                    ],
                    "overall_yield": 54.0,
                    "total_cost_usd": 165,
                    "notes": "More steps but high selectivity",
                },
            ]
        }

        # Convert to JSON string format
        return {
            "content": json.dumps(routes_data, indent=2),
            "usage": {
                "input_tokens": 150,
                "output_tokens": 800,
                "total_tokens": 950,
            },
        }

    async def analyze_molecule(self, smiles: str) -> Dict[str, Any]:
        """Analyze a molecule and provide insights."""

        system_prompt = "You are an expert chemist analyzing molecular structures. Provide concise, accurate analysis."

        user_message = f"Analyze this molecule (SMILES: {smiles}). Describe its key functional groups, potential reactivity, and common uses."

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )

            response_text = ""
            for block in response.content:
                if block.type == "text":
                    response_text += block.text

            return {
                "analysis": response_text,
                "tokens_used": response.usage.input_tokens + response.usage.output_tokens,
            }

        except Exception as e:
            logger.error("molecule_analysis_failed", error=str(e))
            raise
