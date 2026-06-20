"""Impurity propagation and ICH M7 structural-alert screening."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from rdkit import Chem


BYPRODUCT_RULES = {
    "suzuki": {
        "byproducts": ["homocoupling_biaryl", "protodeboronation_product"],
        "typical_levels_ppm": [500, 200],
        "removable_by": ["column_chromatography", "recrystallization"],
    },
    "buchwald_hartwig": {
        "byproducts": ["reduction_byproduct_ArH", "bis_arylation"],
        "typical_levels_ppm": [800, 300],
        "removable_by": ["column_chromatography"],
    },
    "boc_deprotection": {
        "byproducts": ["tert_butanol", "CO2", "isobutylene"],
        "typical_levels_ppm": [50, 0, 0],
        "removable_by": ["evaporation", "aqueous_wash"],
    },
    "amide_coupling_hatu": {
        "byproducts": ["HATU_uronium_byproduct", "HOAt"],
        "typical_levels_ppm": [1000, 500],
        "removable_by": ["aqueous_wash", "recrystallization"],
        "gti_risk": "HOAt has mutagenicity alert - monitor in DS",
    },
    "nitro_reduction_fe": {
        "byproducts": ["iron_salts", "azobenzene_dimer"],
        "typical_levels_ppm": [200, 100],
        "removable_by": ["filtration", "aqueous_wash"],
    },
    "wittig": {
        "byproducts": ["triphenylphosphine_oxide"],
        "typical_levels_ppm": [5000],
        "removable_by": ["recrystallization", "trituration"],
        "note": "Ph3P=O is hard to remove at scale - use HWE instead",
    },
    "grignard": {
        "byproducts": ["MgBrOH", "over_addition_diol"],
        "typical_levels_ppm": [200, 1000],
        "removable_by": ["aqueous_workup", "careful_stoichiometry"],
    },
    "reductive_amination_nabh3cn": {
        "byproducts": ["over_reduced_amine", "CN_ion_traces"],
        "typical_levels_ppm": [500, 100],
        "removable_by": ["pH_adjustment", "aqueous_wash"],
        "gti_risk": "Cyanide traces - NaBH3CN must be controlled. Consider NaBH(OAc)3.",
    },
    "esterification": {
        "byproducts": ["water", "diester"],
        "typical_levels_ppm": [0, 300],
        "removable_by": ["dean_stark", "column"],
    },
    "bromination": {
        "byproducts": ["dibromide", "HBr"],
        "typical_levels_ppm": [500, 0],
        "removable_by": ["recrystallization", "base_wash"],
    },
}


GTI_ALERTS = [
    ("[N+](=O)[O-]", "nitro_aromatic", "Class 2 alert - Ames positive in many nitroaromatics"),
    ("N=N", "azo_compound", "Class 2 alert - azo reduction to aromatic amine"),
    ("[NH2]c1ccccc1", "aromatic_amine", "Class 2 alert - aromatic amines are suspect mutagens"),
    ("C(=O)Cl", "acid_chloride", "Class 3 alert - reactive electrophile, monitor as intermediate"),
    ("[CH2]Br", "alkyl_bromide", "Class 3 alert - alkylating agent"),
    ("[CH2]Cl", "alkyl_chloride", "Class 3 alert - potential alkylating agent"),
    ("O=C1OC1=O", "epoxide_adjacent_carbonyl", "Class 2 alert - Michael acceptor"),
    ("c1cc[nH]c1", "pyrrole", "Class 3 alert - monitor in impurity profile"),
    ("N#N", "diazonium", "Class 1 alert - known mutagen, must purge"),
    ("O=C(N)c", "aromatic_formamide", "Class 2 alert - formamide on arene"),
    ("[N;H0](~[!#6])~[!#6]", "hydrazine_derivative", "Class 2 alert - hydrazines are mutagens"),
    ("C(=S)", "thioamide_or_thioester", "Class 3 alert - thio-carbonyl, monitor"),
    ("O[OH]", "hydroperoxide", "Class 2 alert - reactive oxygen species"),
    ("C=C-C=O", "michael_acceptor", "Class 3 alert - electrophilic alkene"),
]


def any_gti_class_1_or_2(gti_flags: List[Dict[str, Any]]) -> bool:
    return any(
        "Class 1" in str(flag.get("ich_m7_class") or flag.get("class") or "")
        or "Class 2" in str(flag.get("ich_m7_class") or flag.get("class") or "")
        for flag in gti_flags
    )


class ImpurityTracker:
    """Track byproducts through route steps and flag likely GTI concerns."""

    def analyze_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        rxn_type = self._rule_key(step)
        rules = BYPRODUCT_RULES.get(rxn_type, {})

        byproducts = []
        removals = rules.get("removable_by", [])
        for idx, bp_name in enumerate(rules.get("byproducts", [])):
            level_ppm = self._at(rules.get("typical_levels_ppm", []), idx, 0)
            removal = self._at(removals, idx, removals[-1] if removals else None)
            gti_flag = self._check_gti(bp_name, step)
            byproducts.append({
                "name": bp_name,
                "estimated_ppm": level_ppm,
                "removal_method": removal,
                "gti_alert": gti_flag,
                "ich_m7_class": gti_flag["class"] if gti_flag else None,
                "purge_feasible": level_ppm < 5000 and bool(removal),
            })

        return {
            "reaction_type": rxn_type,
            "byproducts": byproducts,
            "gti_notes": rules.get("gti_risk"),
            "step_impurity_risk": self._risk_score(byproducts, rules.get("gti_risk")),
            "notes": rules.get("note"),
        }

    def propagate_route(self, route: Dict[str, Any]) -> Dict[str, Any]:
        accumulated = []
        purge_points = []
        route_impurities = []

        for i, step in enumerate(route.get("steps", [])):
            step_analysis = self.analyze_step(step)
            for bp in step_analysis["byproducts"]:
                if bp["estimated_ppm"] <= 0:
                    continue
                if not self._is_purged_before_next_step(bp, step, i):
                    accumulated.append({
                        **bp,
                        "introduced_at_step": i + 1,
                        "carried_forward": True,
                    })
                else:
                    purge_points.append(
                        f"Step {i + 1}: {bp['name']} removed by {bp['removal_method']}"
                    )
            route_impurities.append(step_analysis)

        all_gti = [
            bp for step_analysis in route_impurities
            for bp in step_analysis["byproducts"]
            if bp.get("gti_alert")
        ]
        gti_notes = [
            step_analysis["gti_notes"] for step_analysis in route_impurities
            if step_analysis.get("gti_notes")
        ]
        overall_risk = (
            "high" if any_gti_class_1_or_2(all_gti) or gti_notes
            else "medium" if accumulated
            else "low"
        )
        return {
            "step_analyses": route_impurities,
            "accumulated_impurities": accumulated,
            "purge_points": purge_points,
            "gti_flags": all_gti,
            "gti_notes": gti_notes,
            "overall_impurity_risk": overall_risk,
            "ich_m7_assessment_required": bool(all_gti or gti_notes),
            "recommended_additional_purification": self._recommend_purification(accumulated),
        }

    def _rule_key(self, step: Dict[str, Any]) -> str:
        rxn_type = str(step.get("reaction_type", "")).lower().replace("-", "_").replace(" ", "_")
        condition_text = str(step.get("conditions", {})).lower()
        step_text = f"{rxn_type} {condition_text} {step.get('catalyst', '')} {step.get('reagent', '')}".lower()
        if "amide_coupling" in rxn_type and "hatu" in step_text:
            return "amide_coupling_hatu"
        if "nitro_reduction" in rxn_type and ("fe" in step_text or "iron" in step_text):
            return "nitro_reduction_fe"
        if "reductive_amination" in rxn_type and "nabh3cn" in step_text:
            return "reductive_amination_nabh3cn"
        return rxn_type

    def _check_gti(self, byproduct_name: str, step: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        byproduct_lower = byproduct_name.lower()
        for smarts, alert_name, description in GTI_ALERTS:
            tokens = [token for token in alert_name.split("_") if len(token) > 2]
            if alert_name in byproduct_lower or any(token in byproduct_lower for token in tokens):
                return {
                    "alert": alert_name,
                    "description": description,
                    "class": self._classify_ich_m7(alert_name),
                    "tcc_limit_ppm": self._get_tcc_limit(alert_name),
                }
            if self._step_has_smarts(step, smarts):
                return {
                    "alert": alert_name,
                    "description": description,
                    "class": self._classify_ich_m7(alert_name),
                    "tcc_limit_ppm": self._get_tcc_limit(alert_name),
                }
        return None

    def _step_has_smarts(self, step: Dict[str, Any], smarts: str) -> bool:
        pattern = Chem.MolFromSmarts(smarts)
        if pattern is None:
            return False
        for smiles in self._step_smiles(step):
            mol = Chem.MolFromSmiles(smiles)
            if mol is not None and mol.HasSubstructMatch(pattern):
                return True
        return False

    def _step_smiles(self, step: Dict[str, Any]) -> List[str]:
        values = []
        for field in ("reactants", "products", "reagents"):
            raw = step.get(field) or []
            if isinstance(raw, str):
                raw = [raw]
            for item in raw:
                values.append(item.get("smiles", "") if isinstance(item, dict) else str(item or ""))
        product = step.get("product")
        if product:
            values.append(product.get("smiles", "") if isinstance(product, dict) else str(product))
        return [value for value in values if value]

    def _classify_ich_m7(self, alert_name: str) -> str:
        class_1 = ["diazonium", "n_nitroso"]
        class_2 = ["nitro_aromatic", "aromatic_amine", "azo_compound", "hydrazine", "michael_acceptor"]
        if any(c in alert_name for c in class_1):
            return "Class 1 (known mutagen - no TCC, minimize)"
        if any(c in alert_name for c in class_2):
            return "Class 2 (Ames positive - TCC applies)"
        return "Class 3 (alerting structure - evaluate per ICH M7)"

    def _get_tcc_limit(self, alert_name: str) -> float:
        return 3.0

    def _risk_score(self, byproducts: List[Dict[str, Any]], gti_risk: Optional[str] = None) -> str:
        if gti_risk or any_gti_class_1_or_2([bp for bp in byproducts if bp.get("gti_alert")]):
            return "high"
        if any(bp.get("gti_alert") for bp in byproducts) or any(bp.get("estimated_ppm", 0) >= 1000 for bp in byproducts):
            return "medium"
        return "low"

    def _is_purged_before_next_step(self, bp: Dict[str, Any], step: Dict[str, Any], index: int) -> bool:
        explicit = any(step.get(field) for field in ("purification", "workup", "isolation"))
        isolated = step.get("isolated", True)
        return bool(explicit or isolated) and bool(bp.get("removal_method")) and bp.get("estimated_ppm", 0) < 5000

    def _recommend_purification(self, accumulated: List[Dict[str, Any]]) -> List[str]:
        recommendations = []
        seen = set()
        for impurity in accumulated:
            method = impurity.get("removal_method") or "targeted purge study"
            text = f"Add {method} for {impurity['name']} from step {impurity['introduced_at_step']}"
            if impurity.get("gti_alert"):
                text += " and document ICH M7 purge factor"
            if text not in seen:
                seen.add(text)
                recommendations.append(text)
        return recommendations

    @staticmethod
    def _at(values: List[Any], index: int, default: Any) -> Any:
        return values[index] if index < len(values) else default
