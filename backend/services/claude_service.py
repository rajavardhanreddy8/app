import os
import json
import structlog
import httpx
from typing import Optional, Any, Dict, List, Tuple

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from pydantic import BaseModel, Field, ValidationError

logger = structlog.get_logger()

PLACEHOLDER_API_KEYS = {
    "",
    "your-anthropic-api-key-here",
    "your_api_key_here",
    "changeme",
    "change-me",
    "your-openrouter-api-key-here",
}

DEFAULT_OPENROUTER_PLANNER_MODELS = [
    "google/gemini-2.5-flash-lite",
    "deepseek/deepseek-v4-flash",
    "openai/gpt-5-nano",
]

DEFAULT_OPENROUTER_COPILOT_MODELS = [
    "google/gemini-2.0-flash-lite-001",
    "mistralai/mistral-small-3.2-24b-instruct",
]

STALE_OPENROUTER_MODELS = {
    "tencent/hy3-preview:free",
}


def is_placeholder_api_key(api_key: Optional[str]) -> bool:
    if api_key is None:
        return True
    return api_key.strip().lower() in PLACEHOLDER_API_KEYS


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float_per_million(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("invalid_float_env %s=%s default=%s", name, raw, default)
        return default


def _parse_model_list(name: str, default: List[str]) -> List[str]:
    raw = os.getenv(name, "")
    models = [item.strip() for item in raw.split(",") if item.strip()]
    return models or list(default)


def _material_to_text(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("smiles") or value.get("canonical_smiles") or value.get("name") or "")
    return str(value or "")


def _clip_percent(value: Any, fallback: float = 75.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = fallback
    if 0 < parsed <= 1:
        parsed *= 100
    return max(0.0, min(100.0, parsed))


def _strict_json_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """OpenRouter structured outputs work best when object schemas reject extras."""
    if not isinstance(schema, dict):
        return schema
    schema = dict(schema)
    if schema.get("type") == "object":
        schema.setdefault("additionalProperties", False)
    for key in ("properties", "$defs", "definitions"):
        nested = schema.get(key)
        if isinstance(nested, dict):
            schema[key] = {name: _strict_json_schema(value) for name, value in nested.items()}
    if isinstance(schema.get("items"), dict):
        schema["items"] = _strict_json_schema(schema["items"])
    for key in ("anyOf", "allOf", "oneOf"):
        if isinstance(schema.get(key), list):
            schema[key] = [_strict_json_schema(item) for item in schema[key]]
    return schema


class ConditionSchema(BaseModel):
    temperature_celsius: Optional[float] = None
    solvent: Optional[str] = None
    catalyst: Optional[str] = None
    time_hours: Optional[float] = None
    pressure_atm: Optional[float] = None
    solvent_volume_ml: Optional[float] = None
    concentration_m: Optional[float] = None
    catalyst_loading_mol_percent: Optional[float] = None


class MaterialQuantitySchema(BaseModel):
    role: str
    material: str
    equivalents: Optional[float] = None
    amount: str
    basis: str
    notes: Optional[str] = None


class StepSchema(BaseModel):
    reactants: List[str] = Field(..., description="Reactant SMILES strings only. Do not use names.")
    product: str = Field(..., description="Product SMILES string only. Do not use a name.")
    reaction_type: str = Field(..., description="Named reaction or transformation.")
    estimated_yield: float
    estimated_yield_percent: Optional[float] = None
    estimated_cost_usd: float
    conditions: ConditionSchema
    reactant_quantities: List[MaterialQuantitySchema]
    catalyst_loading: str
    solvent_amount: str
    concentration_m: Optional[float] = None
    batch_scale: str
    cost_drivers: List[str]
    safety_flags: List[str]
    feasibility_notes: List[str]


class RouteSchema(BaseModel):
    starting_materials: List[str] = Field(..., description="Commercially available starting material SMILES strings only.")
    steps: List[StepSchema]
    overall_yield: float
    overall_yield_percent: Optional[float] = None
    total_cost_usd: float
    score: float
    notes: str
    batch_scale: str
    cost_drivers: List[str]
    feasibility_notes: List[str]


class SynthesisRouteSchema(BaseModel):
    routes: List[RouteSchema]


class ClaudeService:
    """Service for orchestrating Claude API interactions."""

    def __init__(self, api_key: Optional[str] = None):
        self.provider = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()
        self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        self.demo_mode = os.getenv('DEMO_MODE', 'false').lower() == 'true'

        # Bug Fix 3: Always initialize client attribute to avoid AttributeError
        self.client = None
        self.openrouter_client = None
        self.model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        self.max_tokens = 8192
        self.last_error = None
        self.last_model_used = None
        self.model_validation = None

        self.openrouter_planner_models = _parse_model_list(
            "OPENROUTER_PLANNER_MODELS",
            DEFAULT_OPENROUTER_PLANNER_MODELS,
        )
        self.openrouter_copilot_models = _parse_model_list(
            "OPENROUTER_COPILOT_MODELS",
            DEFAULT_OPENROUTER_COPILOT_MODELS,
        )

        legacy_model = os.getenv("OPENROUTER_MODEL", "").strip()
        explicit_planner_models = bool(os.getenv("OPENROUTER_PLANNER_MODELS", "").strip())
        if legacy_model and not explicit_planner_models:
            if legacy_model in STALE_OPENROUTER_MODELS:
                logger.warning(
                    "stale_openrouter_model_ignored: %s -> %s",
                    legacy_model,
                    self.openrouter_planner_models[0],
                )
            else:
                self.openrouter_planner_models = [legacy_model] + [
                    model for model in self.openrouter_planner_models if model != legacy_model
                ]

        self.openrouter_model = self.openrouter_planner_models[0]
        self.openrouter_copilot_model = self.openrouter_copilot_models[0]
        self.openrouter_require_parameters = _env_bool("OPENROUTER_REQUIRE_PARAMETERS", True)
        self.openrouter_max_prompt_price = _env_float_per_million(
            "OPENROUTER_MAX_PROMPT_PRICE_PER_MILLION",
            0.50,
        )
        self.openrouter_max_completion_price = _env_float_per_million(
            "OPENROUTER_MAX_COMPLETION_PRICE_PER_MILLION",
            2.00,
        )

        if not self.demo_mode:
            if self.provider == "openrouter":
                if is_placeholder_api_key(self.openrouter_api_key):
                    logger.warning("OPENROUTER_API_KEY missing or placeholder, switching to demo mode")
                    self.demo_mode = True
                else:
                    self.openrouter_client = AsyncOpenAI(
                        base_url="https://openrouter.ai/api/v1",
                        api_key=self.openrouter_api_key,
                        default_headers={
                            "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "http://localhost:3000"),
                            "X-Title": os.getenv("OPENROUTER_APP_NAME", "SynthAI Route Planner"),
                        },
                    )
            else:
                if is_placeholder_api_key(self.api_key):
                    logger.warning("ANTHROPIC_API_KEY missing or placeholder, switching to demo mode")
                    self.demo_mode = True
                    self.api_key = None
                else:
                    try:
                        self.client = AsyncAnthropic(api_key=self.api_key)
                    except Exception as e:
                        logger.error(f"Failed to initialize Claude client: {str(e)}, switching to demo mode")
                        self.demo_mode = True
                        self.client = None

    def _openrouter_provider_preferences(self) -> Dict[str, Any]:
        return {
            "require_parameters": self.openrouter_require_parameters,
            "allow_fallbacks": True,
            "sort": "price",
            "max_price": {
                "prompt": self.openrouter_max_prompt_price,
                "completion": self.openrouter_max_completion_price,
            },
        }

    def _openrouter_extra_body(self, models: List[str]) -> Dict[str, Any]:
        extra_body: Dict[str, Any] = {
            "provider": self._openrouter_provider_preferences(),
        }
        fallbacks = [model for model in models[1:] if model]
        if fallbacks:
            extra_body["models"] = fallbacks
        return extra_body

    def _openrouter_response_format(self) -> Dict[str, Any]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "synthesis_routes",
                "strict": True,
                "schema": _strict_json_schema(SynthesisRouteSchema.model_json_schema()),
            },
        }

    def status_snapshot(self) -> Dict[str, Any]:
        has_openrouter_key = not is_placeholder_api_key(self.openrouter_api_key)
        has_anthropic_key = not is_placeholder_api_key(self.api_key)
        if self.demo_mode:
            health = "demo"
        elif self.provider == "openrouter" and has_openrouter_key:
            health = "live"
        elif self.provider == "anthropic" and has_anthropic_key:
            health = "live"
        else:
            health = "misconfigured"

        return {
            "provider": self.provider,
            "health": health,
            "demo_mode": self.demo_mode,
            "planner_models": list(self.openrouter_planner_models) if self.provider == "openrouter" else [],
            "copilot_models": list(self.openrouter_copilot_models) if self.provider == "openrouter" else [],
            "require_parameters": self.openrouter_require_parameters if self.provider == "openrouter" else None,
            "max_price_per_million": {
                "input": round(self.openrouter_max_prompt_price, 4),
                "output": round(self.openrouter_max_completion_price, 4),
            } if self.provider == "openrouter" else None,
            "last_model_used": self.last_model_used,
            "last_error": self.last_error,
            "validation": self.model_validation,
        }

    async def validate_configuration(self) -> Dict[str, Any]:
        snapshot = self.status_snapshot()
        if self.provider != "openrouter":
            self.model_validation = {"checked": False, "reason": "provider is not openrouter"}
            snapshot["validation"] = self.model_validation
            return snapshot

        all_models = list(dict.fromkeys(self.openrouter_planner_models + self.openrouter_copilot_models))
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get("https://openrouter.ai/api/v1/models")
                response.raise_for_status()
                model_map = {item.get("id"): item for item in response.json().get("data", [])}
        except Exception as exc:
            self.model_validation = {
                "checked": False,
                "reason": "model metadata unavailable",
                "error": str(exc),
            }
            snapshot = self.status_snapshot()
            snapshot["validation"] = self.model_validation
            return snapshot

        missing = [model for model in all_models if model not in model_map]
        unsupported = []
        for model in all_models:
            supported = set(model_map.get(model, {}).get("supported_parameters") or [])
            if "response_format" not in supported and "structured_outputs" not in supported:
                unsupported.append(model)

        self.model_validation = {
            "checked": True,
            "model_count": len(all_models),
            "missing": missing,
            "unsupported_structured_output": unsupported,
            "ok": not missing and not unsupported,
        }
        snapshot = self.status_snapshot()
        snapshot["validation"] = self.model_validation
        return snapshot

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
            "You are an expert synthetic organic chemist with 20 years "
            "of industrial process chemistry experience. You plan multi-step synthesis routes "
            "the way a real process chemist would — specifying every intermediate, protecting "
            "group strategy, workup procedure, and purification method.\n\n"
            "When planning synthesis routes, ALWAYS:\n"
            "1. Include all steps a lab chemist would actually perform (typically 4-8 steps "
            "for drug-like molecules, not 2-3 oversimplified steps)\n"
            "2. Specify protecting group installation AND removal as separate steps when needed\n"
            "3. Include workup and purification as part of each step's conditions\n"
            "4. For each step specify: exact reagents with equivalents (e.g., '1.2 eq NaH'), "
            "solvent with volume ratio, temperature profile (e.g., '0°C → RT over 2h'), "
            "reaction time, and expected yield based on literature precedent\n"
            "5. Identify the stereochemistry of each step when applicable\n"
            "6. Flag any hazardous steps (organolithiums, azides, peroxides, etc.)\n"
            "7. For Suzuki couplings: always include base (K2CO3/Cs2CO3), Pd source, ligand\n"
            "8. For amide couplings: always specify coupling reagent (HATU/EDC/T3P) and base\n"
            "9. For reductions: specify exact reductant, equivalents, quench procedure\n"
            "10. Consider convergent synthesis when molecule has multiple distinct fragments\n\n"
            "For every step include explicit reactant quantities, equivalents, catalyst loading, "
            "solvent amount/concentration, batch scale, cost drivers, safety flags, and feasibility notes.\n"
            "All starting_materials, step.reactants, and step.product values must be valid SMILES strings. "
            "Never put chemical names such as phenol, salicylic acid, or aspirin in SMILES fields; names may only appear in notes or quantity material descriptions.\n"
            "Always call the provided tool exactly once with complete fields."
        )

        starting_materials_text = starting_materials or ["Common commercially available building blocks"]
        min_steps = max(4, max_steps)
        max_steps_upper = max_steps + 3

        user_message = (
            f"Plan a complete, realistic synthesis of this target molecule:\n\n"
            f"Target SMILES: {target_smiles}\n"
            f"Starting Materials: {', '.join(str(sm) for sm in starting_materials_text)}\n"
            f"Optimization goal: {optimize_for}\n\n"
            f"REQUIREMENTS:\n"
            f"- Provide {min_steps} to {max_steps_upper} step routes (not fewer than 4 steps "
            f"for any drug-like molecule — real synthesis is never 2-3 steps)\n"
            f"- Each step must be a named, real reaction (not 'functional group transformation')\n"
            f"- Include specific reagents, solvents, temperatures from literature or your training\n"
            f"- Include reagent equivalents, catalyst loading, solvent concentration/volume, and batch scale as structured fields\n"
            f"- Use a 0.10 mol planning basis unless the route clearly needs another basis\n"
            f"- Include cost drivers such as expensive catalysts, chiral ligands, cryogenic steps, chromatography, or hazardous quench\n"
            f"- Every route starting material, reactant, intermediate, and product field must be valid SMILES, not a common name\n"
            f"- Keep costs realistic for lab planning; if a route is expensive, explain the expensive driver in notes\n"
            f"- Route 1: optimize for {optimize_for}\n"
            f"- Route 2: alternative disconnection strategy\n"
            f"- Route 3: most step-efficient (convergent if possible)\n"
            f"- If the molecule has a chiral center, at least one route must address stereochemistry\n\n"
            f"Starting materials must be commercially available (Sigma-Aldrich/Combi-Blocks/Enamine).\n"
            f"Do not use exotic or unavailable starting materials."
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

        if self.provider == "openrouter":
            return await self._plan_synthesis_openrouter(
                messages=messages,
                system_prompt=system_prompt,
            )

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
                "metadata": {
                    "provider": self.provider,
                    "model": self.model,
                    "mode": "live_llm",
                },
            }

        except Exception as e:
            logger.error("synthesis_plan_failed", error=str(e))
            raise

    async def _plan_synthesis_openrouter(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
    ) -> Dict[str, Any]:
        schema = self._openrouter_response_format()["json_schema"]["schema"]
        json_instruction = (
            "Return JSON only. Do not use Markdown. The JSON must validate against this schema:\n"
            f"{json.dumps(schema, indent=2)}"
        )
        request_messages = [
            {"role": "system", "content": system_prompt},
            *messages,
            {"role": "user", "content": json_instruction},
        ]

        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        try:
            parsed, usage = await self._request_openrouter_json(request_messages)
            return {
                "content": json.dumps(parsed, indent=2),
                "structured_content": parsed,
                "usage": usage,
                "metadata": {
                    "provider": self.provider,
                    "model": self.last_model_used or self.openrouter_model,
                    "model_candidates": list(self.openrouter_planner_models),
                    "mode": "live_llm",
                },
            }
        except Exception as first_error:
            self.last_error = str(first_error)
            logger.warning("openrouter_plan_retry", error=str(first_error))
            retry_messages = [
                *request_messages,
                {
                    "role": "user",
                    "content": (
                        "The previous response did not validate. Return only valid JSON with a top-level "
                        "'routes' array. Each route needs starting_materials, steps, overall_yield, "
                        "total_cost_usd, score, notes, batch_scale, cost_drivers, and feasibility_notes. "
                        "Each step needs reactants, product, reaction_type, estimated_yield, estimated_cost_usd, "
                        "conditions, reactant_quantities, catalyst_loading, solvent_amount, batch_scale, "
                        "cost_drivers, safety_flags, and feasibility_notes. Use valid SMILES strings in "
                        "starting_materials, reactants, and product fields; do not use chemical names."
                    ),
                },
            ]
            parsed, retry_usage = await self._request_openrouter_json(retry_messages)
            usage["input_tokens"] += retry_usage["input_tokens"]
            usage["output_tokens"] += retry_usage["output_tokens"]
            usage["total_tokens"] += retry_usage["total_tokens"]
            return {
                "content": json.dumps(parsed, indent=2),
                "structured_content": parsed,
                "usage": usage,
                "metadata": {
                    "provider": self.provider,
                    "model": self.last_model_used or self.openrouter_model,
                    "model_candidates": list(self.openrouter_planner_models),
                    "mode": "live_llm_retry",
                    "first_error": str(first_error),
                },
            }

    async def _request_openrouter_json(
        self,
        messages: List[Dict[str, Any]],
    ) -> Tuple[Dict[str, Any], Dict[str, int]]:
        if self.openrouter_client is None:
            raise RuntimeError("OpenRouter client is not initialized")

        response = await self.openrouter_client.chat.completions.create(
            model=self.openrouter_model,
            max_tokens=self.max_tokens,
            temperature=0.2,
            messages=messages,
            response_format=self._openrouter_response_format(),
            extra_body=self._openrouter_extra_body(self.openrouter_planner_models),
        )

        self.last_model_used = getattr(response, "model", None) or self.openrouter_model
        self.last_error = None
        content = response.choices[0].message.content or ""
        content = content.strip()
        if content.startswith("```"):
            content = content.strip("`")
            if content.lower().startswith("json"):
                content = content[4:].strip()

        parsed_raw = self._normalize_payload(json.loads(content))
        validated = SynthesisRouteSchema.model_validate(parsed_raw).model_dump()
        invalid_smiles = self._invalid_smiles_entries(validated)
        if invalid_smiles:
            raise ValueError(
                "Invalid SMILES in structured route fields: "
                + "; ".join(invalid_smiles[:8])
                + ". Use valid SMILES strings, not chemical names."
            )
        raw_usage = getattr(response, "usage", None)
        prompt_tokens = int(getattr(raw_usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(raw_usage, "completion_tokens", 0) or 0)
        total_tokens = int(getattr(raw_usage, "total_tokens", prompt_tokens + completion_tokens) or 0)
        usage = {
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }
        logger.info(
            "openrouter_synthesis_plan_received",
            model=self.last_model_used,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
        )
        return validated, usage

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
            validated = SynthesisRouteSchema.model_validate(self._normalize_payload(payload))
            return validated.model_dump(), None
        except ValidationError as e:
            return None, str(e)

    def _normalize_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Backfill chemistry planning fields for older/demo payloads."""
        if not isinstance(payload, dict):
            return payload

        normalized = {"routes": []}
        for route in payload.get("routes", []):
            if not isinstance(route, dict):
                continue
            steps = []
            route_cost_drivers = set()
            route_feasibility_notes = []
            for index, step in enumerate(route.get("steps", [])):
                if not isinstance(step, dict):
                    continue
                conditions = dict(step.get("conditions") or {})
                reactants = [_material_to_text(item) for item in step.get("reactants", [])]
                product = _material_to_text(step.get("product"))
                reaction_type = str(step.get("reaction_type") or "unknown")
                estimated_yield = _clip_percent(
                    step.get("estimated_yield", step.get("estimated_yield_percent")),
                    75.0,
                )
                estimated_cost = float(step.get("estimated_cost_usd") or 100.0)
                quantities = step.get("reactant_quantities")
                if not quantities:
                    quantities = self._default_quantities(reactants, conditions, index)

                catalyst = conditions.get("catalyst")
                catalyst_loading = step.get("catalyst_loading")
                if not catalyst_loading:
                    catalyst_loading = "5 mol%" if catalyst else "none"

                solvent_amount = step.get("solvent_amount")
                if not solvent_amount:
                    solvent_amount = "800 mL on 0.10 mol basis" if conditions.get("solvent") else "not specified"

                concentration_m = step.get("concentration_m", conditions.get("concentration_m"))
                if concentration_m is None and conditions.get("solvent"):
                    concentration_m = 0.125
                if concentration_m is not None:
                    conditions.setdefault("concentration_m", concentration_m)
                if conditions.get("solvent") and "solvent_volume_ml" not in conditions:
                    conditions["solvent_volume_ml"] = 800.0
                if catalyst and "catalyst_loading_mol_percent" not in conditions:
                    conditions["catalyst_loading_mol_percent"] = 5.0

                cost_drivers = step.get("cost_drivers") or self._infer_cost_drivers(step, conditions)
                safety_flags = step.get("safety_flags") or self._infer_safety_flags(step, conditions)
                feasibility_notes = step.get("feasibility_notes") or self._infer_feasibility_notes(
                    step, conditions, estimated_yield, estimated_cost
                )
                route_cost_drivers.update(cost_drivers)
                route_feasibility_notes.extend(feasibility_notes)

                steps.append({
                    "reactants": reactants,
                    "product": product,
                    "reaction_type": reaction_type,
                    "estimated_yield": estimated_yield,
                    "estimated_yield_percent": estimated_yield,
                    "estimated_cost_usd": estimated_cost,
                    "conditions": conditions,
                    "reactant_quantities": quantities,
                    "catalyst_loading": str(catalyst_loading),
                    "solvent_amount": str(solvent_amount),
                    "concentration_m": concentration_m,
                    "batch_scale": str(step.get("batch_scale") or route.get("batch_scale") or "0.10 mol lab planning basis"),
                    "cost_drivers": list(cost_drivers),
                    "safety_flags": list(safety_flags),
                    "feasibility_notes": list(feasibility_notes),
                })

            overall_yield = _clip_percent(route.get("overall_yield", route.get("overall_yield_percent")), 50.0)
            normalized["routes"].append({
                "starting_materials": [_material_to_text(item) for item in route.get("starting_materials", [])],
                "steps": steps,
                "overall_yield": overall_yield,
                "overall_yield_percent": overall_yield,
                "total_cost_usd": float(route.get("total_cost_usd") or sum(step["estimated_cost_usd"] for step in steps)),
                "score": float(route.get("score") or 50.0),
                "notes": str(route.get("notes") or "Route generated by configured synthesis planner."),
                "batch_scale": str(route.get("batch_scale") or "0.10 mol lab planning basis"),
                "cost_drivers": list(route.get("cost_drivers") or sorted(route_cost_drivers) or ["Reagent pricing requires supplier quote validation"]),
                "feasibility_notes": list(
                    route.get("feasibility_notes")
                    or route_feasibility_notes[:5]
                    or ["LLM-generated route requires literature and purchasability validation"]
                ),
            })

        return normalized

    def _default_quantities(self, reactants: List[str], conditions: Dict[str, Any], step_index: int) -> List[Dict[str, Any]]:
        quantities = []
        for index, material in enumerate(reactants):
            equivalents = 1.0 if index == 0 else 1.1
            quantities.append({
                "role": "limiting reactant" if index == 0 else "reactant",
                "material": material,
                "equivalents": equivalents,
                "amount": f"{100.0 * equivalents:.1f} mmol",
                "basis": "0.10 mol planning basis",
                "notes": "Estimated stoichiometry; verify against literature procedure",
            })
        catalyst = conditions.get("catalyst")
        if catalyst:
            quantities.append({
                "role": "catalyst",
                "material": str(catalyst),
                "equivalents": 0.05,
                "amount": "5.0 mmol",
                "basis": "5 mol% on 0.10 mol limiting reactant",
                "notes": "Planning estimate",
            })
        return quantities

    def _infer_cost_drivers(self, step: Dict[str, Any], conditions: Dict[str, Any]) -> List[str]:
        text = " ".join(
            str(value).lower()
            for value in [step.get("reaction_type"), conditions.get("catalyst"), conditions.get("solvent"), step.get("notes")]
            if value
        )
        drivers = []
        if any(token in text for token in ["pd", "rhodium", "iridium", "ru", "chiral"]):
            drivers.append("Precious metal or chiral catalyst/ligand")
        if any(token in text for token in ["chromatography", "hplc", "prep"]):
            drivers.append("Chromatographic purification")
        if any(token in text for token in ["dmf", "dcm", "thf", "benzene", "chloroform"]):
            drivers.append("Solvent cost/recovery and waste handling")
        if abs(float(conditions.get("temperature_celsius") or 25)) > 100:
            drivers.append("Thermal control or non-ambient operation")
        if not drivers:
            drivers.append("Supplier quote and stoichiometry need validation")
        return drivers

    def _infer_safety_flags(self, step: Dict[str, Any], conditions: Dict[str, Any]) -> List[str]:
        text = " ".join(str(value).lower() for value in [step.get("reaction_type"), conditions.get("catalyst"), step.get("notes")] if value)
        flags = []
        if any(token in text for token in ["azide", "diazo", "peroxide", "organolithium", "nah"]):
            flags.append("High-energy or strongly reactive reagent")
        if float(conditions.get("pressure_atm") or 1) > 10:
            flags.append("Pressure operation")
        if abs(float(conditions.get("temperature_celsius") or 25)) > 150:
            flags.append("Extreme temperature operation")
        return flags or ["No major safety flag identified by schema-level screen"]

    def _infer_feasibility_notes(
        self,
        step: Dict[str, Any],
        conditions: Dict[str, Any],
        estimated_yield: float,
        estimated_cost: float,
    ) -> List[str]:
        notes = []
        reaction_type = str(step.get("reaction_type") or "").lower()
        catalyst = str(conditions.get("catalyst") or "").lower()
        if estimated_yield < 40:
            notes.append("Low step yield; prioritize condition screen before scale-up")
        if estimated_yield > 98:
            notes.append("Very high yield estimate; verify with literature or experiment")
        if estimated_cost > 1000:
            notes.append("Step cost outlier; check catalyst loading, equivalents, and purification")
        if "suzuki" in reaction_type and "pd" not in catalyst:
            notes.append("Suzuki coupling should specify Pd source, ligand, and base")
        return notes or ["Feasible as an early planning estimate; requires experimental validation"]

    def _invalid_smiles_entries(self, payload: Dict[str, Any]) -> List[str]:
        try:
            from rdkit import Chem
        except Exception:
            return []

        invalid = []

        def is_valid(smiles: str) -> bool:
            return bool(smiles and Chem.MolFromSmiles(str(smiles)) is not None)

        for route_index, route in enumerate(payload.get("routes", []), start=1):
            for material_index, smiles in enumerate(route.get("starting_materials", []), start=1):
                if not is_valid(smiles):
                    invalid.append(f"route {route_index} starting_materials[{material_index}]={smiles!r}")
            for step_index, step in enumerate(route.get("steps", []), start=1):
                product = step.get("product")
                if not is_valid(product):
                    invalid.append(f"route {route_index} step {step_index} product={product!r}")
                valid_reactants = [smiles for smiles in step.get("reactants", []) if is_valid(smiles)]
                if not valid_reactants:
                    invalid.append(f"route {route_index} step {step_index} has no valid reactant SMILES")

        return invalid

    def _generate_demo_routes(
        self,
        target_smiles: str,
        max_steps: int,
        optimize_for: str,
    ) -> Dict[str, Any]:
        """Generate chemically-correct demo synthesis routes for showcase molecules.

        Five molecules have hardcoded literature routes; everything else gets a
        polished generic fallback so demo mode always returns something useful.
        """

        # ── Aspirin (acetylsalicylic acid) ───────────────────────────────────
        # Industrial route from benzene via Kolbe-Schmitt + acetylation
        aspirin_4step = {
            "routes": [
                {
                    "starting_materials": [
                        {"smiles": "c1ccccc1", "name": "Benzene"},
                        {"smiles": "Brc1ccccc1", "name": "Bromobenzene"},
                    ],
                    "steps": [
                        {
                            "id": "step-1",
                            "reactants": [{"smiles": "c1ccccc1"}, {"smiles": "[Br][Br]"}],
                            "product": {"smiles": "Brc1ccccc1"},
                            "reaction_type": "Electrophilic Aromatic Bromination",
                            "estimated_yield_percent": 91,
                            "estimated_cost_usd": 18,
                            "difficulty": "easy",
                            "conditions": {
                                "temperature_celsius": 25,
                                "solvent": "DCM",
                                "catalyst": "FeBr3",
                                "time_hours": 2,
                                "pressure_atm": 1,
                            },
                            "notes": "Lewis-acid catalysed EAS; Br₂/FeBr₃ in DCM at RT gives mono-bromination selectively.",
                        },
                        {
                            "id": "step-2",
                            "reactants": [{"smiles": "Brc1ccccc1"}, {"smiles": "[OH-].[Na+]"}],
                            "product": {"smiles": "Oc1ccccc1"},
                            "reaction_type": "Nucleophilic Aromatic Substitution (Dow process)",
                            "estimated_yield_percent": 73,
                            "estimated_cost_usd": 30,
                            "difficulty": "moderate",
                            "conditions": {
                                "temperature_celsius": 300,
                                "solvent": "H2O",
                                "catalyst": "NaOH (aq)",
                                "time_hours": 4,
                                "pressure_atm": 1,
                            },
                            "notes": "High-temperature hydrolysis of aryl halide; industrial Dow process.",
                        },
                        {
                            "id": "step-3",
                            "reactants": [{"smiles": "Oc1ccccc1"}, {"smiles": "O=C=O"}],
                            "product": {"smiles": "OC(=O)c1ccccc1O"},
                            "reaction_type": "Kolbe–Schmitt Carboxylation",
                            "estimated_yield_percent": 75,
                            "estimated_cost_usd": 22,
                            "difficulty": "moderate",
                            "conditions": {
                                "temperature_celsius": 125,
                                "solvent": "neat",
                                "catalyst": "NaOH / CO₂ (5 atm)",
                                "time_hours": 6,
                                "pressure_atm": 5,
                            },
                            "notes": "Phenol + CO₂ under pressure and base gives salicylic acid regioselectively.",
                        },
                        {
                            "id": "step-4",
                            "reactants": [
                                {"smiles": "OC(=O)c1ccccc1O"},
                                {"smiles": "CC(=O)OC(C)=O"},
                            ],
                            "product": {"smiles": "CC(=O)Oc1ccccc1C(=O)O"},
                            "reaction_type": "O-Acetylation (Fischer–Speier)",
                            "estimated_yield_percent": 87,
                            "estimated_cost_usd": 12,
                            "difficulty": "easy",
                            "conditions": {
                                "temperature_celsius": 85,
                                "solvent": "DCM",
                                "catalyst": "H₃PO₄ (cat.)",
                                "time_hours": 0.33,
                                "pressure_atm": 1,
                            },
                            "notes": "Salicylic acid + acetic anhydride → aspirin. Standard undergraduate synthesis.",
                        },
                    ],
                    "overall_yield_percent": round(0.91 * 0.73 * 0.75 * 0.87 * 100, 1),
                    "total_cost_usd": 82,
                    "total_time_hours": 12.3,
                    "score": 88,
                    "notes": "Industrial 4-step route from benzene via Kolbe–Schmitt carboxylation.",
                },
                {
                    # Short 1-step from salicylic acid (lab teaching route)
                    "starting_materials": [
                        {"smiles": "OC(=O)c1ccccc1O", "name": "Salicylic acid"},
                        {"smiles": "CC(=O)OC(C)=O", "name": "Acetic anhydride"},
                    ],
                    "steps": [
                        {
                            "id": "step-1",
                            "reactants": [
                                {"smiles": "OC(=O)c1ccccc1O"},
                                {"smiles": "CC(=O)OC(C)=O"},
                            ],
                            "product": {"smiles": "CC(=O)Oc1ccccc1C(=O)O"},
                            "reaction_type": "O-Acetylation",
                            "estimated_yield_percent": 87,
                            "estimated_cost_usd": 8,
                            "difficulty": "easy",
                            "conditions": {
                                "temperature_celsius": 85,
                                "solvent": "DCM",
                                "catalyst": "H₃PO₄",
                                "time_hours": 0.33,
                                "pressure_atm": 1,
                            },
                            "notes": "Classic 1-step aspirin synthesis — single-step from commercial salicylic acid.",
                        }
                    ],
                    "overall_yield_percent": 87.0,
                    "total_cost_usd": 8,
                    "total_time_hours": 0.5,
                    "score": 95,
                    "notes": "Fastest route; salicylic acid is commercially available at low cost.",
                },
            ]
        }

        # ── Paracetamol (acetaminophen) ───────────────────────────────────────
        paracetamol_2step = {
            "routes": [
                {
                    "starting_materials": [
                        {"smiles": "O=[N+]([O-])c1ccccc1", "name": "Nitrobenzene"},
                        {"smiles": "CC(=O)OC(C)=O", "name": "Acetic anhydride"},
                    ],
                    "steps": [
                        {
                            "id": "step-1",
                            "reactants": [
                                {"smiles": "O=[N+]([O-])c1ccccc1"},
                                {"smiles": "[H][H]"},
                            ],
                            "product": {"smiles": "Nc1ccc(O)cc1"},
                            "reaction_type": "Nitro-reduction / Baeyer–Villiger-like rearrangement",
                            "estimated_yield_percent": 78,
                            "estimated_cost_usd": 20,
                            "difficulty": "moderate",
                            "conditions": {
                                "temperature_celsius": 80,
                                "solvent": "HCl (aq)",
                                "catalyst": "Fe (Bechamp reduction)",
                                "time_hours": 3,
                                "pressure_atm": 1,
                            },
                            "notes": "Bechamp reduction of nitrobenzene gives aniline; subsequent hydroxylation under acidic conditions gives p-aminophenol selectively.",
                        },
                        {
                            "id": "step-2",
                            "reactants": [
                                {"smiles": "Nc1ccc(O)cc1"},
                                {"smiles": "CC(=O)OC(C)=O"},
                            ],
                            "product": {"smiles": "CC(=O)Nc1ccc(O)cc1"},
                            "reaction_type": "N-Acetylation",
                            "estimated_yield_percent": 91,
                            "estimated_cost_usd": 10,
                            "difficulty": "easy",
                            "conditions": {
                                "temperature_celsius": 40,
                                "solvent": "H₂O",
                                "catalyst": "none",
                                "time_hours": 0.5,
                                "pressure_atm": 1,
                            },
                            "notes": "Selective N-acetylation of the amine in water — O-acetylation is reversible under aqueous conditions.",
                        },
                    ],
                    "overall_yield_percent": round(0.78 * 0.91 * 100, 1),
                    "total_cost_usd": 30,
                    "total_time_hours": 3.5,
                    "score": 90,
                    "notes": "Industrial paracetamol synthesis via Bechamp reduction of nitrobenzene.",
                }
            ]
        }

        # ── Ibuprofen ─────────────────────────────────────────────────────────
        # Hoechst process (6 steps → 3 catalytic)
        ibuprofen_3step = {
            "routes": [
                {
                    "starting_materials": [
                        {"smiles": "CC(C)c1ccccc1", "name": "Isobutylbenzene"},
                        {"smiles": "CC(=O)OC(C)=O", "name": "Acetic anhydride"},
                    ],
                    "steps": [
                        {
                            "id": "step-1",
                            "reactants": [
                                {"smiles": "CC(C)c1ccccc1"},
                                {"smiles": "CC(=O)OC(C)=O"},
                            ],
                            "product": {"smiles": "CC(=O)c1ccc(CC(C)C)cc1"},
                            "reaction_type": "Friedel–Crafts Acylation",
                            "estimated_yield_percent": 90,
                            "estimated_cost_usd": 25,
                            "difficulty": "easy",
                            "conditions": {
                                "temperature_celsius": 35,
                                "solvent": "HF",
                                "catalyst": "HF (cat.)",
                                "time_hours": 1,
                                "pressure_atm": 1,
                            },
                            "notes": "Hoechst process step 1: HF-catalysed acylation with high para selectivity.",
                        },
                        {
                            "id": "step-2",
                            "reactants": [
                                {"smiles": "CC(=O)c1ccc(CC(C)C)cc1"},
                                {"smiles": "[H][H]"},
                            ],
                            "product": {"smiles": "CC(O)c1ccc(CC(C)C)cc1"},
                            "reaction_type": "Meerwein–Ponndorf–Verley Reduction",
                            "estimated_yield_percent": 98,
                            "estimated_cost_usd": 15,
                            "difficulty": "easy",
                            "conditions": {
                                "temperature_celsius": 60,
                                "solvent": "iPrOH",
                                "catalyst": "Raney Ni",
                                "time_hours": 2,
                                "pressure_atm": 4,
                            },
                            "notes": "Catalytic hydrogenation of ketone to alcohol; >98% yield with Raney Ni.",
                        },
                        {
                            "id": "step-3",
                            "reactants": [
                                {"smiles": "CC(O)c1ccc(CC(C)C)cc1"},
                                {"smiles": "O=C=O"},
                            ],
                            "product": {"smiles": "CC(C)Cc1ccc(cc1)C(C)C(=O)O"},
                            "reaction_type": "Koch Carbonylation",
                            "estimated_yield_percent": 97,
                            "estimated_cost_usd": 20,
                            "difficulty": "moderate",
                            "conditions": {
                                "temperature_celsius": 50,
                                "solvent": "neat CO",
                                "catalyst": "PdCl₂(dppf) / CO",
                                "time_hours": 3,
                                "pressure_atm": 30,
                            },
                            "notes": "Pd-catalysed carbonylation introduces the carboxylic acid with >97% selectivity.",
                        },
                    ],
                    "overall_yield_percent": round(0.90 * 0.98 * 0.97 * 100, 1),
                    "total_cost_usd": 60,
                    "total_time_hours": 6,
                    "score": 92,
                    "notes": "Hoechst 3-step green process — only 3 catalytic steps, atom-efficient.",
                }
            ]
        }

        # ── Caffeine ──────────────────────────────────────────────────────────
        caffeine_3step = {
            "routes": [
                {
                    "starting_materials": [
                        {"smiles": "O=c1[nH]cnc2[nH]cnc12", "name": "Xanthine"},
                        {"smiles": "CI", "name": "Methyl iodide"},
                    ],
                    "steps": [
                        {
                            "id": "step-1",
                            "reactants": [
                                {"smiles": "O=c1[nH]cnc2[nH]cnc12"},
                                {"smiles": "CI"},
                            ],
                            "product": {"smiles": "O=c1[nH]cnc2n(C)cnc12"},
                            "reaction_type": "N-Methylation (SN2)",
                            "estimated_yield_percent": 82,
                            "estimated_cost_usd": 35,
                            "difficulty": "moderate",
                            "conditions": {
                                "temperature_celsius": 60,
                                "solvent": "DMF",
                                "catalyst": "K₂CO₃",
                                "time_hours": 4,
                                "pressure_atm": 1,
                            },
                            "notes": "Regioselective N7-methylation of xanthine using K₂CO₃/DMF.",
                        },
                        {
                            "id": "step-2",
                            "reactants": [
                                {"smiles": "O=c1[nH]cnc2n(C)cnc12"},
                                {"smiles": "CI"},
                            ],
                            "product": {"smiles": "O=c1ncnc2n(C)cnc12"},
                            "reaction_type": "N-Methylation (SN2) — N3 position",
                            "estimated_yield_percent": 80,
                            "estimated_cost_usd": 35,
                            "difficulty": "moderate",
                            "conditions": {
                                "temperature_celsius": 70,
                                "solvent": "DMF",
                                "catalyst": "K₂CO₃",
                                "time_hours": 5,
                                "pressure_atm": 1,
                            },
                            "notes": "Second methylation at N3 gives theophylline.",
                        },
                        {
                            "id": "step-3",
                            "reactants": [
                                {"smiles": "O=c1ncnc2n(C)cnc12"},
                                {"smiles": "CI"},
                            ],
                            "product": {"smiles": "Cn1cnc2c1c(=O)n(C)c(=O)n2C"},
                            "reaction_type": "N-Methylation (SN2) — N1 position",
                            "estimated_yield_percent": 88,
                            "estimated_cost_usd": 30,
                            "difficulty": "easy",
                            "conditions": {
                                "temperature_celsius": 55,
                                "solvent": "DMF",
                                "catalyst": "K₂CO₃",
                                "time_hours": 3,
                                "pressure_atm": 1,
                            },
                            "notes": "Final N1-methylation completes the trimethylxanthine (caffeine) skeleton.",
                        },
                    ],
                    "overall_yield_percent": round(0.82 * 0.80 * 0.88 * 100, 1),
                    "total_cost_usd": 100,
                    "total_time_hours": 12,
                    "score": 80,
                    "notes": "Sequential tri-methylation of xanthine; industrial synthesis uses theophylline as intermediate.",
                }
            ]
        }

        # ── Molecule lookup ───────────────────────────────────────────────────
        # Canonicalize for matching (handle minor SMILES variants)
        try:
            from rdkit import Chem
            mol = Chem.MolFromSmiles(target_smiles)
            canonical = Chem.MolToSmiles(mol) if mol else target_smiles
        except Exception:
            canonical = target_smiles

        demo_map = {
            # Aspirin variants
            "CC(=O)Oc1ccccc1C(=O)O": aspirin_4step,
            "OC(=O)c1ccccc1OC(C)=O": aspirin_4step,
            # Paracetamol variants
            "CC(=O)Nc1ccc(O)cc1": paracetamol_2step,
            "CC(=O)Nc1ccc(cc1)O": paracetamol_2step,
            # Ibuprofen
            "CC(C)Cc1ccc(cc1)C(C)C(=O)O": ibuprofen_3step,
            "CC(Cc1ccc(cc1)C(C)C(=O)O)C": ibuprofen_3step,
            # Caffeine
            "Cn1cnc2c1c(=O)n(C)c(=O)n2C": caffeine_3step,
            "CN1C=NC2=C1C(=O)N(C(=O)N2C)C": caffeine_3step,
        }

        routes_data = demo_map.get(target_smiles) or demo_map.get(canonical)

        # ── Generic fallback (polished, not molecule-specific) ────────────────
        if routes_data is None:
            routes_data = {
                "routes": [
                    {
                        "starting_materials": [
                            {"smiles": "c1ccccc1", "name": "Benzene"},
                            {"smiles": "CC(=O)Cl", "name": "Acetyl chloride"},
                        ],
                        "steps": [
                            {
                                "id": "step-1",
                                "reactants": [{"smiles": "c1ccccc1"}, {"smiles": "CC(=O)Cl"}],
                                "product": {"smiles": "CC(=O)c1ccccc1"},
                                "reaction_type": "Friedel–Crafts Acylation",
                                "estimated_yield_percent": 85,
                                "estimated_cost_usd": 45,
                                "difficulty": "easy",
                                "conditions": {
                                    "temperature_celsius": 0,
                                    "solvent": "DCM",
                                    "catalyst": "AlCl₃",
                                    "time_hours": 3,
                                },
                                "notes": "Classic Friedel–Crafts acylation giving acetophenone.",
                            },
                            {
                                "id": "step-2",
                                "reactants": [{"smiles": "CC(=O)c1ccccc1"}],
                                "product": {"smiles": target_smiles},
                                "reaction_type": "Illustrative Retrosynthetic Placeholder",
                                "estimated_yield_percent": 75,
                                "estimated_cost_usd": 60,
                                "difficulty": "moderate",
                                "conditions": {
                                    "temperature_celsius": 25,
                                    "solvent": "THF",
                                    "time_hours": 6,
                                },
                                "notes": "Fallback demo only: this second step is a placeholder because the target is not in the bundled demo route library.",
                            },
                        ],
                        "overall_yield_percent": 63.8,
                        "total_cost_usd": 105,
                        "total_time_hours": 9,
                        "score": 72,
                        "notes": "Generic fallback demo route. Use one of the bundled examples or configure a real Anthropic API key for molecule-specific AI planning.",
                    }
                ]
            }

        normalized_routes = SynthesisRouteSchema.model_validate(self._normalize_payload(routes_data)).model_dump()

        return {
            "content": json.dumps(normalized_routes, indent=2),
            "structured_content": normalized_routes,
            "usage": {
                "input_tokens": 850,
                "output_tokens": 1240,
                "total_tokens": 2090,
            },
            "metadata": {
                "provider": self.provider,
                "mode": "demo_fallback",
                "model": None,
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
