"""Telescoping feasibility analyzer for synthesis routes.

The analyzer evaluates whether two consecutive reaction steps can be run
one-pot without isolating the intermediate.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Sequence, Tuple


INCOMPATIBLE_FOR_TELESCOPING: Sequence[Tuple[str, str]] = (
    ("strong_acid", "base_sensitive_intermediate"),
    ("oxidant", "reduction_step"),
    ("aqueous_workup_required", "moisture_sensitive_next_step"),
    ("halide_byproduct", "pd_catalyst"),
)

MISCIBLE_SOLVENTS = {
    "water": {"methanol", "ethanol", "acetone", "acetonitrile", "dmf", "dmso", "thf", "isopropanol", "ipa"},
    "methanol": {"water", "ethanol", "acetone", "acetonitrile", "dmf", "dmso", "thf", "isopropanol", "ipa"},
    "ethanol": {"water", "methanol", "acetone", "acetonitrile", "dmf", "dmso", "thf", "isopropanol", "ipa"},
    "isopropanol": {"water", "methanol", "ethanol", "acetone", "acetonitrile", "thf"},
    "ipa": {"water", "methanol", "ethanol", "acetone", "acetonitrile", "thf"},
    "acetone": {"water", "methanol", "ethanol", "acetonitrile", "dmf", "dmso", "thf", "dcm"},
    "acetonitrile": {"water", "methanol", "ethanol", "acetone", "dmf", "dmso", "thf", "dcm"},
    "dmf": {"water", "methanol", "ethanol", "acetone", "acetonitrile", "dmso", "thf", "dcm"},
    "dmso": {"water", "methanol", "ethanol", "acetone", "acetonitrile", "dmf", "thf"},
    "thf": {"water", "methanol", "ethanol", "acetone", "acetonitrile", "dmf", "dmso", "toluene", "dcm", "ethyl acetate"},
    "dcm": {"acetone", "acetonitrile", "dmf", "thf", "toluene", "ethyl acetate", "hexane"},
    "toluene": {"thf", "dcm", "ethyl acetate", "hexane", "heptane"},
    "ethyl acetate": {"thf", "dcm", "toluene", "hexane", "heptane", "acetone"},
    "hexane": {"dcm", "toluene", "ethyl acetate", "heptane"},
    "heptane": {"dcm", "toluene", "ethyl acetate", "hexane"},
}

NEAT_SOLVENT_NAMES = {"", "none", "neat", "solvent-free", "solvent free", "no solvent"}


class TelescopingAnalyzer:
    """Evaluate one-pot feasibility for consecutive synthesis steps."""

    def can_telescope(self, step1: Dict[str, Any], step2: Dict[str, Any]) -> Dict[str, Any]:
        blocking_issues: List[str] = []
        enabling_conditions: List[str] = []
        scavenging_reagents_needed: List[str] = []
        warnings: List[str] = []

        tags1 = self._step_tags(step1, role="first")
        tags2 = self._step_tags(step2, role="second")
        conditions1 = self._conditions(step1)
        conditions2 = self._conditions(step2)
        solvent1 = self._normalize_solvent(conditions1.get("solvent", step1.get("solvent", "")))
        solvent2 = self._normalize_solvent(conditions2.get("solvent", step2.get("solvent", "")))
        catalyst2 = self._lower(conditions2.get("catalyst", step2.get("catalyst", "")))
        reaction1 = self._lower(step1.get("reaction_type", ""))
        reaction2 = self._lower(step2.get("reaction_type", ""))

        for left_tag, right_tag in INCOMPATIBLE_FOR_TELESCOPING:
            if left_tag in tags1 and right_tag in tags2:
                blocking_issues.append(self._incompatibility_message(left_tag, right_tag))

        if "halide_byproduct" in tags1 and self._is_pd_catalyst(catalyst2):
            blocking_issues.append("Halide byproduct from step 1 can poison the step 2 Pd catalyst.")
            scavenging_reagents_needed.append("halide scavenger or catalyst-compatible filtration before step 2")

        if "strong_acid" in tags1 and self._uses_hatu_or_carbodiimide(step2):
            blocking_issues.append("Strong acid carryover from step 1 is incompatible with HATU/carbodiimide amide coupling.")
            enabling_conditions.append("neutralize and remove acid before charging coupling reagent")

        if "oxidant" in tags1 and "reduction_step" in tags2:
            blocking_issues.append("Residual oxidant from step 1 can consume or destroy the step 2 reductant.")
            scavenging_reagents_needed.append("reducing scavenger or oxidant quench validated by IPC")

        if "aqueous_workup_required" in tags1 and "moisture_sensitive_next_step" in tags2:
            blocking_issues.append("Aqueous workup or water carryover from step 1 is incompatible with the moisture-sensitive next step.")
            enabling_conditions.append("replace aqueous workup with dry scavenging or solvent swap under anhydrous conditions")

        if "grignard" in reaction1 and "quench" in reaction2 and "reduction_step" in tags2:
            blocking_issues.append("Grignard quench introduces moisture/salts that are incompatible with direct NaBH4 or hydride reduction.")
            enabling_conditions.append("isolate and dry the alcohol/intermediate before charging the reduction step")

        temp1 = self._temperature_c(step1)
        temp2 = self._temperature_c(step2)
        if temp1 is not None and temp2 is not None and temp1 > temp2:
            blocking_issues.append(
                f"Temperature profile is unfavorable: step 1 runs at {temp1:g} C and step 2 at {temp2:g} C."
            )
            enabling_conditions.append("demonstrate controlled cooling or modify step 2 to run at the higher temperature")
        elif temp1 is not None and temp2 is not None and temp1 < temp2:
            enabling_conditions.append("temperature ramp is favorable because the sequence heats from step 1 into step 2")

        if not self._solvents_compatible(solvent1, solvent2):
            blocking_issues.append(f"Solvent incompatibility: {solvent1 or 'neat'} is not reliably miscible with {solvent2 or 'neat'}.")
            enabling_conditions.append("perform solvent swap or choose a common solvent for both steps")
        elif solvent1 and solvent2 and solvent1 != solvent2:
            enabling_conditions.append(f"compatible mixed-solvent system likely: {solvent1} / {solvent2}")

        if not self._solvent_dissolves_next_reactants(solvent1, step2):
            warnings.append("Step 1 solvent may not dissolve all step 2 reactants.")
            enabling_conditions.append("verify step 2 reactant solubility or add cosolvent before telescoping")

        if self._needs_completion_ipc(step1):
            enabling_conditions.append("confirm step 1 completion by IPC before adding step 2 reagents")

        if "excess_isocyanate" in tags1:
            scavenging_reagents_needed.append("ethanol to scavenge excess isocyanate")
        if "acid_chloride" in tags1:
            scavenging_reagents_needed.append("amine or alcohol scavenger for acid chloride carryover")

        feasible = len(blocking_issues) == 0
        confidence = self._confidence(feasible, warnings, enabling_conditions, step1, step2)
        time_reduction = self._time_reduction_hours(step1)
        pmi_reduction = self._pmi_reduction_estimate(step1, step2, feasible)

        if feasible and not enabling_conditions:
            enabling_conditions.append("charge step 2 reagents after step 1 conversion reaches specification")

        return {
            "feasible": feasible,
            "confidence": confidence,
            "blocking_issues": blocking_issues,
            "enabling_conditions": enabling_conditions,
            "pmi_reduction_estimate": pmi_reduction,
            "time_reduction_hours": time_reduction if feasible else 0.0,
            "scavenging_reagents_needed": sorted(set(scavenging_reagents_needed)),
            "warnings": warnings,
            "rule_tags": {
                "step1": sorted(tags1),
                "step2": sorted(tags2),
            },
            "pair_label": f"{step1.get('reaction_type', 'step 1')} -> {step2.get('reaction_type', 'step 2')}",
        }

    def analyze_route_telescoping(self, route: Dict[str, Any]) -> Dict[str, Any]:
        steps = route.get("steps") or []
        pair_results = []
        telescopable_pairs: List[Tuple[int, int]] = []

        for index in range(len(steps) - 1):
            result = self.can_telescope(steps[index], steps[index + 1])
            result["step_pair"] = (index + 1, index + 2)
            pair_results.append(result)
            if result["feasible"]:
                telescopable_pairs.append((index + 1, index + 2))

        selected_pairs = self._select_non_overlapping_pairs(pair_results)
        total_time_reduction = round(sum(pair["time_reduction_hours"] for pair in selected_pairs), 2)
        total_pmi_reduction = self._total_pmi_reduction(selected_pairs)

        optimized_route = self._merge_telescoped_route(route, selected_pairs)

        return {
            "telescopable_pairs": [pair["step_pair"] for pair in selected_pairs],
            "all_pair_assessments": pair_results,
            "total_pmi_reduction": total_pmi_reduction,
            "total_time_reduction_hours": total_time_reduction,
            "recommended_sequence": self._recommended_sequence(len(steps), selected_pairs),
            "optimized_route": optimized_route,
        }

    def _merge_telescoped_route(self, route: Dict[str, Any], selected_pairs: List[Dict[str, Any]]) -> Dict[str, Any]:
        optimized = copy.deepcopy(route)
        steps = optimized.get("steps") or []
        pair_starts = {pair["step_pair"][0] - 1: pair for pair in selected_pairs}
        merged_steps: List[Dict[str, Any]] = []
        index = 0

        while index < len(steps):
            if index in pair_starts and index + 1 < len(steps):
                first = steps[index]
                second = steps[index + 1]
                pair = pair_starts[index]
                merged_steps.append(self._merged_step(first, second, pair))
                index += 2
            else:
                step = copy.deepcopy(steps[index])
                step["telescoped"] = False
                merged_steps.append(step)
                index += 1

        optimized["steps"] = merged_steps
        optimized["telescoping_summary"] = {
            "telescoped_pairs": [pair["step_pair"] for pair in selected_pairs],
            "pmi_reduction_percent": self._total_pmi_reduction(selected_pairs),
            "time_reduction_hours": round(sum(pair["time_reduction_hours"] for pair in selected_pairs), 2),
        }
        return optimized

    def _merged_step(self, first: Dict[str, Any], second: Dict[str, Any], pair: Dict[str, Any]) -> Dict[str, Any]:
        first_conditions = self._conditions(first)
        second_conditions = self._conditions(second)
        merged_conditions = dict(first_conditions)
        merged_conditions.update({k: v for k, v in second_conditions.items() if v not in (None, "", "None")})
        merged_conditions["operation"] = "telescoped one-pot sequence"

        return {
            "telescoped": True,
            "telescoped_steps": list(pair["step_pair"]),
            "reaction_type": f"{first.get('reaction_type', 'Step')} / {second.get('reaction_type', 'Step')}",
            "reactants": self._unique_list(self._as_list(first.get("reactants")) + self._as_list(second.get("reactants"))),
            "product": second.get("product", self._first_product(second)),
            "intermediate": first.get("product", self._first_product(first)),
            "conditions": merged_conditions,
            "estimated_yield_percent": self._combined_yield(first, second),
            "estimated_cost_usd": self._safe_float(first.get("estimated_cost_usd"), 0.0) + self._safe_float(second.get("estimated_cost_usd"), 0.0),
            "telescoping_analysis": {
                "confidence": pair["confidence"],
                "pmi_reduction_estimate": pair["pmi_reduction_estimate"],
                "time_reduction_hours": pair["time_reduction_hours"],
                "enabling_conditions": pair["enabling_conditions"],
                "scavenging_reagents_needed": pair["scavenging_reagents_needed"],
            },
        }

    def _step_tags(self, step: Dict[str, Any], role: str) -> set[str]:
        text = self._step_text(step)
        tags: set[str] = set()

        if any(token in text for token in ("tfa", "hcl", "h2so4", "sulfuric acid", "trifluoroacetic acid", "strong acid", "acidic")):
            tags.add("strong_acid")
        if any(token in text for token in ("naoh", "koh", "base sensitive", "base-sensitive")):
            tags.add("base")
        if any(token in text for token in ("base sensitive", "base-sensitive")):
            tags.add("base_sensitive_intermediate")
        if any(token in text for token in ("oxidation", "oxidant", "mcpba", "kmno4", "naio4", "h2o2", "peroxide", "tempo", "pcc")):
            tags.add("oxidant")
        if any(token in text for token in ("reduction", "hydrogenation", "nabh4", "lialh4", "bh3", "dibal", "fe/hcl", "iron/hcl")):
            tags.add("reduction_step")
        if any(token in text for token in ("grignard", "organolithium", "lialh4", "nabh4", "acid chloride", "anhydrous", "moisture sensitive", "moisture-sensitive")):
            tags.add("moisture_sensitive_next_step" if role == "second" else "moisture_sensitive")
        if "no aqueous workup" not in text and any(token in text for token in ("aqueous workup", "water quench", "quench", "wash", "extraction", "brine")):
            tags.add("aqueous_workup_required")
        if any(token in text for token in ("chloride", "bromide", "iodide", "halide", "hbr", "hcl", "nacl", "kbr")):
            tags.add("halide_byproduct")
        if any(token in text for token in ("pd", "palladium", "suzuki", "heck", "buchwald")):
            tags.add("pd_catalyst")
        if any(token in text for token in ("isocyanate", "n=c=o")):
            tags.add("excess_isocyanate")
        if "acid chloride" in text or "acyl chloride" in text:
            tags.add("acid_chloride")

        # Real-example overrides.
        reaction_type = self._lower(step.get("reaction_type", ""))
        if "boc" in reaction_type and "deprotection" in reaction_type:
            tags.add("strong_acid")
        if "amide" in reaction_type and any(token in text for token in ("hatu", "hbtu", "edci", "dcc")):
            tags.add("base_sensitive_intermediate")
        if "grignard" in reaction_type:
            tags.add("moisture_sensitive")
        return tags

    def _conditions(self, step: Dict[str, Any]) -> Dict[str, Any]:
        conditions = step.get("conditions") or step.get("predicted_conditions") or {}
        return conditions if isinstance(conditions, dict) else {}

    def _temperature_c(self, step: Dict[str, Any]) -> Optional[float]:
        conditions = self._conditions(step)
        for key in ("temperature_celsius", "temperature_c", "temp_c"):
            if key in conditions:
                return self._safe_float(conditions.get(key), None)
            if key in step:
                return self._safe_float(step.get(key), None)
        return None

    def _solvents_compatible(self, solvent1: str, solvent2: str) -> bool:
        if solvent1 in NEAT_SOLVENT_NAMES or solvent2 in NEAT_SOLVENT_NAMES:
            return True
        if solvent1 == solvent2:
            return True
        return solvent2 in MISCIBLE_SOLVENTS.get(solvent1, set()) or solvent1 in MISCIBLE_SOLVENTS.get(solvent2, set())

    def _solvent_dissolves_next_reactants(self, solvent: str, step2: Dict[str, Any]) -> bool:
        if solvent in NEAT_SOLVENT_NAMES:
            return True
        reactant_text = self._lower(" ".join(str(item) for item in self._as_list(step2.get("reactants"))))
        if any(token in reactant_text for token in ("salt", "[na+]", "[k+]", "hcl", "hydrochloride")):
            return solvent in {"water", "methanol", "ethanol", "dmf", "dmso", "acetonitrile"}
        if any(token in reactant_text for token in ("grignard", "mgbr", "mgcl", "organolithium")):
            return solvent in {"thf", "ether", "diethyl ether", "toluene"}
        return True

    def _needs_completion_ipc(self, step: Dict[str, Any]) -> bool:
        text = self._step_text(step)
        return any(token in text for token in ("esterification", "acylation", "deprotection", "grignard", "oxidation", "reduction"))

    def _confidence(
        self,
        feasible: bool,
        warnings: List[str],
        enabling_conditions: List[str],
        step1: Dict[str, Any],
        step2: Dict[str, Any],
    ) -> str:
        if not feasible:
            return "low"
        if warnings:
            return "medium"
        if len(enabling_conditions) > 2:
            return "medium"
        known_positive = (
            ("nitro" in self._lower(step1.get("reaction_type", "")) and "acetyl" in self._lower(step2.get("reaction_type", "")))
            or ("suzuki" in self._lower(step1.get("reaction_type", "")) and "amide" in self._lower(step2.get("reaction_type", "")))
            or ("esterification" in self._lower(step1.get("reaction_type", "")) and "extraction" in self._lower(step2.get("reaction_type", "")))
        )
        return "high" if known_positive else "medium"

    def _pmi_reduction_estimate(self, step1: Dict[str, Any], step2: Dict[str, Any], feasible: bool) -> float:
        if not feasible:
            return 0.0
        reduction = 20.0
        if "aqueous_workup_required" not in self._step_tags(step1, "first"):
            reduction += 10.0
        if self._normalize_solvent(self._conditions(step1).get("solvent", "")) == self._normalize_solvent(self._conditions(step2).get("solvent", "")):
            reduction += 5.0
        if self._confidence(True, [], [], step1, step2) == "high":
            reduction += 5.0
        return round(min(reduction, 45.0), 1)

    def _time_reduction_hours(self, step1: Dict[str, Any]) -> float:
        conditions = self._conditions(step1)
        workup_time = self._safe_float(step1.get("isolation_time_hours"), 2.0)
        workup_time += self._safe_float(conditions.get("workup_time_hours"), 0.0)
        return round(max(workup_time, 1.0), 2)

    @staticmethod
    def _select_non_overlapping_pairs(pair_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        selected = []
        used_steps = set()
        feasible_pairs = [pair for pair in pair_results if pair["feasible"]]
        feasible_pairs.sort(key=lambda pair: (-pair["pmi_reduction_estimate"], pair["step_pair"][0]))
        for pair in feasible_pairs:
            first, second = pair["step_pair"]
            if first not in used_steps and second not in used_steps:
                selected.append(pair)
                used_steps.update({first, second})
        return sorted(selected, key=lambda pair: pair["step_pair"][0])

    @staticmethod
    def _total_pmi_reduction(selected_pairs: List[Dict[str, Any]]) -> float:
        if not selected_pairs:
            return 0.0
        retained_fraction = 1.0
        for pair in selected_pairs:
            retained_fraction *= 1.0 - (pair["pmi_reduction_estimate"] / 100.0)
        return round((1.0 - retained_fraction) * 100.0, 1)

    @staticmethod
    def _recommended_sequence(step_count: int, selected_pairs: List[Dict[str, Any]]) -> str:
        if step_count == 0:
            return "no steps provided"
        telescoped = {tuple(pair["step_pair"]) for pair in selected_pairs}
        phrases = []
        index = 1
        while index <= step_count:
            pair = (index, index + 1)
            if pair in telescoped:
                phrases.append(f"steps {index}-{index + 1} telescoped")
                index += 2
            else:
                phrases.append(f"step {index} isolated")
                index += 1
        return ", ".join(phrases)

    @staticmethod
    def _incompatibility_message(left_tag: str, right_tag: str) -> str:
        messages = {
            ("strong_acid", "base_sensitive_intermediate"): "Strong acid carryover can decompose or suppress a base-sensitive intermediate or coupling system.",
            ("oxidant", "reduction_step"): "Oxidant carryover from step 1 is incompatible with a following reduction step.",
            ("aqueous_workup_required", "moisture_sensitive_next_step"): "Aqueous workup from step 1 is incompatible with a moisture-sensitive next step.",
            ("halide_byproduct", "pd_catalyst"): "Halide byproduct can poison a Pd catalyst in the next step.",
        }
        return messages.get((left_tag, right_tag), f"Incompatible telescoping tags: {left_tag} followed by {right_tag}.")

    def _step_text(self, step: Dict[str, Any]) -> str:
        parts = [
            step.get("reaction_type", ""),
            step.get("notes", ""),
            step.get("byproducts", ""),
            step.get("workup", ""),
            self._conditions(step),
            step.get("reactants", ""),
            step.get("reagents", ""),
            step.get("catalyst", ""),
        ]
        return self._lower(" ".join(str(part) for part in parts))

    @staticmethod
    def _uses_hatu_or_carbodiimide(step: Dict[str, Any]) -> bool:
        text = TelescopingAnalyzer._lower_static(str(step))
        return any(token in text for token in ("hatu", "hbtu", "edci", "dcc", "dipea"))

    @staticmethod
    def _is_pd_catalyst(catalyst: str) -> bool:
        return any(token in catalyst for token in ("pd", "palladium"))

    @staticmethod
    def _normalize_solvent(value: Any) -> str:
        solvent = TelescopingAnalyzer._lower_static(str(value or "")).replace("_", " ").strip()
        aliases = {
            "meoh": "methanol",
            "etoh": "ethanol",
            "ipa": "isopropanol",
            "acn": "acetonitrile",
            "ch2cl2": "dcm",
            "dichloromethane": "dcm",
            "ethyl acetate": "ethyl acetate",
            "etoac": "ethyl acetate",
        }
        return aliases.get(solvent, solvent)

    @staticmethod
    def _as_list(value: Any) -> List[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

    @staticmethod
    def _unique_list(values: List[Any]) -> List[Any]:
        result = []
        seen = set()
        for value in values:
            key = str(value)
            if key not in seen:
                seen.add(key)
                result.append(value)
        return result

    @staticmethod
    def _first_product(step: Dict[str, Any]) -> Any:
        products = step.get("products")
        if isinstance(products, list) and products:
            return products[0]
        return step.get("product")

    @staticmethod
    def _combined_yield(first: Dict[str, Any], second: Dict[str, Any]) -> float:
        yield1 = TelescopingAnalyzer._safe_float_static(first.get("estimated_yield_percent", first.get("predicted_yield", 75.0)), 75.0)
        yield2 = TelescopingAnalyzer._safe_float_static(second.get("estimated_yield_percent", second.get("predicted_yield", 75.0)), 75.0)
        return round((yield1 / 100.0) * (yield2 / 100.0) * 100.0, 1)

    @staticmethod
    def _safe_float(value: Any, default: Optional[float]) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_float_static(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _lower(value: Any) -> str:
        return str(value or "").lower()

    @staticmethod
    def _lower_static(value: Any) -> str:
        return str(value or "").lower()
