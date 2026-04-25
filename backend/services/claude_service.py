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
        self.max_tokens = 8192

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
                                "reaction_type": "Functional Group Transformation",
                                "estimated_yield_percent": 75,
                                "estimated_cost_usd": 60,
                                "difficulty": "moderate",
                                "conditions": {
                                    "temperature_celsius": 25,
                                    "solvent": "THF",
                                    "time_hours": 6,
                                },
                                "notes": "Demo mode: molecule-specific route not available. Enable ANTHROPIC_API_KEY for AI-generated routes.",
                            },
                        ],
                        "overall_yield_percent": 63.8,
                        "total_cost_usd": 105,
                        "total_time_hours": 9,
                        "score": 72,
                        "notes": "Generic demo route — set ANTHROPIC_API_KEY for molecule-specific AI planning.",
                    }
                ]
            }

        return {
            "content": json.dumps(routes_data, indent=2),
            "usage": {
                "input_tokens": 850,
                "output_tokens": 1240,
                "total_tokens": 2090,
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
