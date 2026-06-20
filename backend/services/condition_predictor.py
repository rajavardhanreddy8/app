import numpy as np
import pandas as pd
import pickle
import logging
import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score, mean_absolute_error
from sklearn.preprocessing import LabelEncoder
import xgboost as xgb
from rdkit import Chem
from rdkit.Chem import AllChem, Descriptors
from services.reaction_database import ReactionDatabase
from services.multi_model import MultiModelClassifier, MultiModelRegressor
import asyncio

logger = logging.getLogger(__name__)


class SafeLabelEncoder:
    """Label encoder wrapper that maps unseen labels to index 0 ("unknown")."""

    def __init__(self, unknown_label: str = "unknown"):
        self.unknown_label = unknown_label
        self.encoder = LabelEncoder()
        self.classes_ = np.array([unknown_label], dtype=object)

    def fit(self, y):
        values = [self.unknown_label]
        values.extend([str(label) for label in y if str(label) != self.unknown_label])
        unique_values = sorted(set(values) - {self.unknown_label})
        ordered_classes = [self.unknown_label] + unique_values
        self.encoder.classes_ = np.array(ordered_classes, dtype=object)
        self.classes_ = self.encoder.classes_
        return self

    def transform(self, y):
        labels = [str(label) for label in y]
        try:
            return self.encoder.transform(labels)
        except ValueError:
            class_to_idx = {label: idx for idx, label in enumerate(self.classes_)}
            return np.array([class_to_idx.get(label, 0) for label in labels], dtype=int)

    def fit_transform(self, y):
        self.fit(y)
        return self.transform(y)

    def inverse_transform(self, y):
        return self.encoder.inverse_transform(y)


class _ConditionModelUnpickler(pickle.Unpickler):
    """Load older condition artifacts that pickled SafeLabelEncoder from __main__."""

    def find_class(self, module, name):
        if module == "__main__" and name == "SafeLabelEncoder":
            return SafeLabelEncoder
        return super().find_class(module, name)


CATALYST_HIERARCHY = {
    # Level 1 - Biocatalysis
    "reductive_amination": {
        "level": 1, "type": "biocatalysis",
        "primary": ("transaminase", "pH 7.5 buffer/DMSO 10%"),
        "fallback": ("NaBH3CN", "MeOH"),
        "note": "Transaminase gives >99% ee. Use NaBH3CN only for racemic product.",
    },
    "esterification_chiral": {
        "level": 1, "type": "biocatalysis",
        "primary": ("Candida antarctica lipase B (CAL-B)", "MTBE"),
        "fallback": ("H2SO4", "Toluene"),
        "note": "CAL-B gives enantioselective esterification at ambient temperature.",
    },
    "ketone_reduction": {
        "level": 1, "type": "biocatalysis",
        "primary": ("ketoreductase (KRED)", "iPrOH/buffer"),
        "fallback": ("NaBH4", "EtOH"),
        "note": "KRED gives chiral alcohol directly. NaBH4 for racemic only.",
    },

    # Level 2 - Heterogeneous
    "hydrogenation": {
        "level": 2, "type": "heterogeneous",
        "primary": ("Pd/C 5%", "EtOAc or EtOH"),
        "fallback": ("Pd/Al2O3", "EtOH"),
        "note": "Filter off catalyst after reaction. Reusable 8-12 cycles.",
    },
    "hydrogenolysis": {
        "level": 2, "type": "heterogeneous",
        "primary": ("Pd/C 10%", "EtOH"),
        "fallback": ("Pd(OH)2/C", "MeOH"),
        "note": "Cbz deprotection. H2 balloon or Parr shaker.",
    },
    "cbz_deprotection": {
        "level": 2, "type": "heterogeneous",
        "primary": ("Pd/C 10%", "EtOH"),
        "fallback": ("Pd(OH)2/C", "MeOH"),
        "note": "Standard hydrogenolysis conditions.",
    },
    "nitro_reduction": {
        "level": 2, "type": "heterogeneous",
        "primary": ("Fe powder", "AcOH/EtOH 1:1"),
        "fallback": ("Pd/C + H2", "EtOH"),
        "note": "Fe/AcOH is preferred at scale - no pressure equipment needed.",
    },
    "oxidation": {
        "level": 2, "type": "heterogeneous",
        "primary": ("TEMPO/NaOCl", "DCM/H2O"),
        "fallback": ("PCC", "DCM"),
        "note": "TEMPO is recoverable. PCC generates Cr waste - avoid at scale.",
    },

    # Level 3 - Earth-abundant metals
    "ullmann_coupling": {
        "level": 3, "type": "earth_abundant",
        "primary": ("CuI 10 mol%", "DMF"),
        "fallback": ("Pd(OAc)2", "DMF"),
        "note": "Cu catalyst at 1/1000th cost of Pd. Requires higher temperature.",
    },
    "chan_lam": {
        "level": 3, "type": "earth_abundant",
        "primary": ("Cu(OAc)2", "DCM"),
        "fallback": ("Pd2(dba)3", "Toluene"),
        "note": "Chan-Lam avoids halide waste vs Buchwald-Hartwig.",
    },
    "dehydrogenation": {
        "level": 3, "type": "earth_abundant",
        "primary": ("CuBr2", "DMF"),
        "fallback": ("DDQ", "DCM"),
        "note": "Cu-catalyzed aromatization. Lower cost than DDQ at scale.",
    },

    # Level 4 - Homogeneous Pd
    "suzuki": {
        "level": 4, "type": "homogeneous_pd",
        "primary": ("Pd(PPh3)4", "DMF/H2O 4:1"),
        "fallback": ("Pd(dppf)Cl2", "Dioxane/H2O"),
        "note": "WARNING: Homogeneous Pd. Budget 2-3 purification steps for metal removal. Consider Pd/C Suzuki protocol instead.",
        "flag": "pd_removal_required",
    },
    "buchwald_hartwig": {
        "level": 4, "type": "homogeneous_pd",
        "primary": ("Pd2(dba)3/XPhos", "Toluene"),
        "fallback": ("Pd(OAc)2/BINAP", "THF"),
        "note": "WARNING: Homogeneous Pd. No heterogeneous alternative for C-N coupling yet.",
        "flag": "pd_removal_required",
    },
    "heck": {
        "level": 4, "type": "homogeneous_pd",
        "primary": ("Pd(OAc)2/PPh3", "DMF"),
        "fallback": ("Pd(PPh3)4", "DMF"),
        "note": "WARNING: Homogeneous Pd. Pd/Al2O3 acceptable for simple Heck at scale.",
        "flag": "pd_removal_required",
    },

    # Non-metal reactions
    "boc_deprotection": {
        "level": 0, "type": "acid",
        "primary": ("TFA 20% v/v", "DCM"),
        "fallback": ("4M HCl in dioxane", "no additional solvent"),
        "note": "TFA 0 C to RT, 1-2h. Evaporate TFA completely before next step.",
    },
    "esterification": {
        "level": 0, "type": "acid",
        "primary": ("H2SO4 cat.", "Toluene with Dean-Stark"),
        "fallback": ("p-TsOH", "Toluene"),
        "note": "Dean-Stark trap removes water, drives equilibrium to completion.",
    },
    "amide_coupling": {
        "level": 0, "type": "coupling_reagent",
        "primary": ("HATU/DIPEA", "DMF"),
        "fallback": ("EDC/HOBt", "DMF"),
        "note": "HATU for hindered substrates. EDC/HOBt is cheaper at scale.",
    },
    "bromination": {
        "level": 0, "type": "lewis_acid",
        "primary": ("FeBr3 cat.", "DCM"),
        "fallback": ("AlBr3", "DCM"),
        "note": "Electrophilic aromatic bromination. Use Br2 or NBS as bromine source.",
    },
    "reduction": {
        "level": 0, "type": "hydride",
        "primary": ("NaBH4", "EtOH"),
        "fallback": ("L-Selectride", "THF"),
        "note": "NaBH4 0 C, add slowly. LiAlH4 only if NaBH4 insufficient.",
    },
    "wittig": {
        "level": 0, "type": "organophosphorus",
        "primary": ("Ph3P=CHCO2Et", "THF"),
        "fallback": ("HWE conditions: (EtO)2P(O)CH2CO2Et/NaH", "THF"),
        "note": "HWE (Horner-Wadsworth-Emmons) preferred at scale - Ph3P=O easier to remove.",
    },
    "grignard": {
        "level": 0, "type": "organomagnesium",
        "primary": ("Mg turnings/I2 activation", "dry THF"),
        "fallback": ("iPrMgCl.LiCl", "dry THF"),
        "note": "Strictly anhydrous conditions. No Pd catalyst required.",
    },
}

CATALYST_COSTS_PER_GRAM = {
    "Pd(PPh3)4": 0.85, "Pd2(dba)3": 1.20, "Pd(OAc)2": 0.65,
    "Pd/C 5%": 0.045, "Pd/C 10%": 0.065, "Pd/Al2O3": 0.038,
    "Pd(OH)2/C": 0.055, "CuI": 0.008, "Cu(OAc)2": 0.004,
    "CuBr2": 0.006, "Fe powder": 0.0008, "NaBH4": 0.035,
    "LiAlH4": 0.12, "NaBH3CN": 0.18, "HATU": 2.80,
    "EDC": 0.45, "HOBt": 0.32, "TFA": 0.025,
    "H2SO4": 0.0003, "AlCl3": 0.002, "FeBr3": 0.015,
    "TEMPO": 0.38, "PCC": 0.28, "transaminase": 4.50,
    "ketoreductase": 3.80, "CAL-B lipase": 1.20, "Ph3P": 0.065,
}

CATALYST_REUSE_CYCLES = {
    "Pd/C 5%": 10, "Pd/C 10%": 8, "Pd/Al2O3": 12,
    "Pd-graphene": 16, "CAL-B lipase": 20, "transaminase": 15,
    "ketoreductase": 15, "CuI": 1, "Pd(PPh3)4": 1, "HATU": 1,
}


class CatalystCostAnalysis:
    """Estimate catalyst/reagent cost burden per kg product."""

    HOMOGENEOUS_PD = ("Pd(PPh3)4", "Pd2(dba)3", "Pd(OAc)2")

    def calculate_catalyst_cost_per_kg_product(
        self,
        catalyst_name: str,
        loading_mol_percent: float,
        substrate_mw: float,
        batch_size_kg: float,
    ) -> float:
        normalized = self._cost_key(catalyst_name)
        cost_per_g = CATALYST_COSTS_PER_GRAM.get(normalized, 0.10)
        reuse = CATALYST_REUSE_CYCLES.get(normalized, 1)
        substrate_mw = max(float(substrate_mw or 250.0), 1.0)
        batch_size_kg = max(float(batch_size_kg or 1.0), 0.001)

        moles_substrate = (batch_size_kg * 1000.0) / substrate_mw
        moles_catalyst = moles_substrate * (float(loading_mol_percent or 1.0) / 100.0)
        grams_catalyst = moles_catalyst * 500.0
        effective_cost = (grams_catalyst * cost_per_g) / max(reuse, 1)
        return round(effective_cost / batch_size_kg, 2)

    def build_payload(self, catalyst_name: str, entry: Dict[str, Any], reaction: Dict[str, Any]) -> Dict[str, Any]:
        catalyst_key = self._cost_key(catalyst_name)
        loading = self._default_loading(catalyst_name, entry)
        substrate_mw = self._substrate_mw(reaction)
        batch_size_kg = float(reaction.get("batch_size_kg", 1.0) or 1.0)
        reuse = CATALYST_REUSE_CYCLES.get(catalyst_key, self._default_reuse(entry))
        pd_required = entry.get("flag") == "pd_removal_required" or self._is_homogeneous_pd(catalyst_name)
        return {
            "catalyst_cost_per_kg": self.calculate_catalyst_cost_per_kg_product(
                catalyst_key, loading, substrate_mw, batch_size_kg
            ),
            "separation_method": self._separation_method(entry, catalyst_name),
            "reuse_cycles": reuse,
            "metal_leaching_risk": self._metal_leaching_risk(entry, catalyst_name),
            "pd_removal_required": pd_required,
            "regulatory_note": self._regulatory_note(entry, catalyst_name, pd_required),
            "biocatalytic_alternative": self._biocatalytic_alternative(entry, catalyst_name),
            "estimated_pmi_contribution": self._estimate_pmi_contribution(catalyst_key, loading, substrate_mw, reuse),
        }

    def _estimate_pmi_contribution(self, catalyst_name: str, loading: float, substrate_mw: float, reuse: int) -> float:
        moles_per_kg = 1000.0 / max(substrate_mw, 1.0)
        grams = moles_per_kg * (loading / 100.0) * 500.0
        return round((grams / 1000.0) / max(reuse, 1), 3)

    def _substrate_mw(self, reaction: Dict[str, Any]) -> float:
        for value in reaction.get("reactants") or []:
            smiles = value.get("smiles", "") if isinstance(value, dict) else str(value or "")
            mol = Chem.MolFromSmiles(smiles) if smiles else None
            if mol is not None:
                return float(Descriptors.MolWt(mol))
        return float(reaction.get("substrate_mw", 250.0) or 250.0)

    def _cost_key(self, catalyst_name: str) -> str:
        text = str(catalyst_name or "").strip()
        aliases = {
            "Candida antarctica lipase B (CAL-B)": "CAL-B lipase",
            "ketoreductase (KRED)": "ketoreductase",
            "TFA 20% v/v": "TFA",
            "H2SO4 cat.": "H2SO4",
            "FeBr3 cat.": "FeBr3",
            "HATU/DIPEA": "HATU",
            "Pd2(dba)3/XPhos": "Pd2(dba)3",
            "Pd(OAc)2/PPh3": "Pd(OAc)2",
            "TEMPO/NaOCl": "TEMPO",
            "Ph3P=CHCO2Et": "Ph3P",
            "CuI 10 mol%": "CuI",
            "Mg turnings/I2 activation": "Mg turnings",
        }
        return aliases.get(text, text)

    def _default_loading(self, catalyst_name: str, entry: Dict[str, Any]) -> float:
        catalyst_text = str(catalyst_name or "").lower()
        catalyst_type = entry.get("type")
        if catalyst_type == "biocatalysis":
            return 5.0
        if catalyst_type == "heterogeneous":
            return 5.0
        if catalyst_type == "earth_abundant":
            return 10.0
        if catalyst_type == "homogeneous_pd" or "pd" in catalyst_text:
            return 2.0
        return 100.0 if catalyst_type in {"coupling_reagent", "hydride", "acid"} else 5.0

    def _default_reuse(self, entry: Dict[str, Any]) -> int:
        if entry.get("type") == "biocatalysis":
            return 15
        if entry.get("type") == "heterogeneous":
            return 10
        return 1

    def _is_homogeneous_pd(self, catalyst_name: str) -> bool:
        text = str(catalyst_name or "")
        return "Pd" in text and "/C" not in text and "Al2O3" not in text

    def _separation_method(self, entry: Dict[str, Any], catalyst_name: str) -> str:
        if entry.get("type") == "biocatalysis":
            return "filtration (immobilized enzyme)"
        if entry.get("type") == "heterogeneous":
            return "filtration"
        if entry.get("type") == "homogeneous_pd":
            return "metal scavenger resin + crystallization"
        if entry.get("type") in {"acid", "coupling_reagent", "hydride"}:
            return "aqueous workup / crystallization"
        return "standard workup"

    def _metal_leaching_risk(self, entry: Dict[str, Any], catalyst_name: str) -> str:
        if entry.get("type") == "biocatalysis":
            return "none"
        if entry.get("type") == "heterogeneous":
            return "low"
        if entry.get("type") == "earth_abundant":
            return "medium"
        if self._is_homogeneous_pd(catalyst_name):
            return "high"
        return "none"

    def _regulatory_note(self, entry: Dict[str, Any], catalyst_name: str, pd_required: bool) -> str:
        if entry.get("type") == "biocatalysis":
            return "No metal impurity concerns. ICH Q3D not applicable."
        if pd_required:
            return "Pd metal removal required. ICH Q3D elemental impurity controls needed."
        if entry.get("type") == "heterogeneous":
            return "Easy removal; low metal carryover risk with filtration."
        return entry.get("note", "")

    def _biocatalytic_alternative(self, entry: Dict[str, Any], catalyst_name: str) -> Optional[str]:
        if entry.get("type") == "biocatalysis":
            return None
        if "NaBH4" in str(catalyst_name):
            return "ketoreductase for chiral alcohol synthesis"
        if "Pd" in str(catalyst_name):
            return "Evaluate transaminase/KRED/lipase option if stereocenter-forming step"
        return None


class ConditionPredictor:
    """ML-based prediction of optimal reaction conditions."""

    CONDITION_FEATURE_SIZE = 768
    CONDITION_REACTION_KEYWORDS = [
        "esterification", "fischer_esterification", "transesterification",
        "suzuki", "suzuki_coupling", "buchwald_hartwig", "heck",
        "amide_coupling", "amide_formation", "amidation", "reductive_amination",
        "reduction", "nitro_reduction", "hydrogenation", "nabh4", "lialh4",
        "oxidation", "grignard", "organolithium", "wittig", "aldol",
        "diels_alder", "diels-alder", "friedel_crafts", "friedel-crafts",
        "friedel-crafts_acylation", "sn2", "sn2_substitution", "nitration",
        "bromination", "chlorination", "fluorination", "boc_deprotection",
        "deprotection_boc", "cbz_deprotection", "acylation", "alkylation",
    ]
    FUNCTIONAL_GROUP_SMARTS = {
        "aryl_halide": "[cX3][Cl,Br,I]",
        "alkyl_halide": "[CX4][Cl,Br,I]",
        "boronic_acid": "B(O)O",
        "carboxylic_acid": "C(=O)[OH]",
        "acid_chloride": "C(=O)Cl",
        "amine": "[NX3;H2,H1;!$(NC=O)]",
        "alcohol": "[OX2H][CX4]",
        "aldehyde": "[CX3H1](=O)[#6]",
        "ketone": "[#6][CX3](=O)[#6]",
        "ester": "C(=O)O[#6]",
        "amide": "C(=O)N",
        "nitro": "[NX3](=O)=O",
        "alkene": "C=C",
        "nitrile": "C#N",
        "aromatic": "a",
    }

    def __init__(self, model_dir: Optional[str] = None):
        if model_dir is None:
            # Better path resolution for Windows/Local environments
            base_dir = Path(__file__).parent.parent
            self.model_dir = base_dir / "models"
        else:
            self.model_dir = Path(model_dir)
            
        self.model_dir.mkdir(parents=True, exist_ok=True)
        
        # Models for different condition types
        self.temp_model = None
        self.catalyst_model = None
        self.solvent_model = None
        self.temp_multi_model = None
        self.catalyst_multi_model = None
        self.solvent_multi_model = None
        self.model_metrics: Dict[str, Any] = {}

        # Label encoders
        self.catalyst_encoder = SafeLabelEncoder()
        self.solvent_encoder = SafeLabelEncoder()

        self.models_loaded = False
        self.catalyst_cost_analysis = CatalystCostAnalysis()

    def compute_reaction_features(self, reaction: Dict[str, Any]) -> np.ndarray:
        """Compute features for condition prediction."""
        try:
            reactants = reaction.get('reactants', [])
            products = reaction.get('products', [])

            if not reactants or not products:
                return np.zeros(self.CONDITION_FEATURE_SIZE)

            reactant_mols = self._valid_mols(reactants)
            product_mols = self._valid_mols(products)
            features = []

            features.extend(self._reaction_fingerprint(reactant_mols, product_mols))
            reactant_agg = self._aggregate_descriptors(reactant_mols)
            product_agg = self._aggregate_descriptors(product_mols)
            features.extend(reactant_agg)
            features.extend(product_agg)
            features.extend((np.array(product_agg) - np.array(reactant_agg)).tolist())

            features.extend([
                float(len(reactants)),
                float(len(products)),
                float(len(reactant_mols)),
                float(len(product_mols)),
                float(sum(mol.GetNumAtoms() for mol in reactant_mols)),
                float(sum(mol.GetNumAtoms() for mol in product_mols)),
            ])

            rxn_type = self._normalize_text(reaction.get('reaction_type', ''))
            for rtype in self.CONDITION_REACTION_KEYWORDS:
                features.append(1.0 if self._normalize_text(rtype) in rxn_type else 0.0)

            all_mols = reactant_mols + product_mols
            features.extend(self._functional_group_counts(all_mols))

            while len(features) < self.CONDITION_FEATURE_SIZE:
                features.append(0)

            return np.array(features[:self.CONDITION_FEATURE_SIZE], dtype=float)

        except Exception as e:
            logger.error(f"Error computing features: {str(e)}")
            return np.zeros(self.CONDITION_FEATURE_SIZE)

    def _valid_mols(self, smiles_values: List[Any]) -> List[Any]:
        mols = []
        for value in smiles_values:
            smiles = value.get("smiles", "") if isinstance(value, dict) else str(value or "")
            if not smiles:
                continue
            mol = Chem.MolFromSmiles(smiles)
            if mol is not None:
                mols.append(mol)
        return mols

    def _molecular_descriptor_vector(self, mol: Any) -> List[float]:
        return [
            Descriptors.MolWt(mol),
            Descriptors.MolLogP(mol),
            float(mol.GetNumAtoms()),
            float(mol.GetNumBonds()),
            Descriptors.RingCount(mol),
            Descriptors.NumAromaticRings(mol),
            Descriptors.NumHDonors(mol),
            Descriptors.NumHAcceptors(mol),
            Descriptors.TPSA(mol),
            Descriptors.NumRotatableBonds(mol),
            Descriptors.NumHeteroatoms(mol),
            Descriptors.FractionCSP3(mol),
        ]

    def _aggregate_descriptors(self, mols: List[Any]) -> List[float]:
        if not mols:
            return [0.0] * 24
        vectors = np.array([self._molecular_descriptor_vector(mol) for mol in mols], dtype=float)
        return np.concatenate([vectors.mean(axis=0), vectors.sum(axis=0)]).tolist()

    def _reaction_fingerprint(self, reactant_mols: List[Any], product_mols: List[Any]) -> List[float]:
        if not reactant_mols or not product_mols:
            return [0.0] * 512
        try:
            reactant_fps = [
                np.array(AllChem.GetMorganFingerprintAsBitVect(mol, radius=2, nBits=512), dtype=float)
                for mol in reactant_mols
            ]
            product_fps = [
                np.array(AllChem.GetMorganFingerprintAsBitVect(mol, radius=2, nBits=512), dtype=float)
                for mol in product_mols
            ]
            return (np.mean(product_fps, axis=0) - np.mean(reactant_fps, axis=0)).tolist()
        except Exception:
            return [0.0] * 512

    def _functional_group_counts(self, mols: List[Any]) -> List[float]:
        counts = []
        for smarts in self.FUNCTIONAL_GROUP_SMARTS.values():
            pattern = Chem.MolFromSmarts(smarts)
            if pattern is None:
                counts.append(0.0)
                continue
            counts.append(float(sum(len(mol.GetSubstructMatches(pattern)) for mol in mols)))
        return counts

    @staticmethod
    def _normalize_text(value: Any) -> str:
        return str(value or "").lower().replace(" ", "_").replace("-", "_")

    async def prepare_training_data(self) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
        """Load and prepare training data from database."""
        logger.info("Loading reactions for condition prediction...")

        reactions = self._load_condition_training_json()
        if not reactions:
            try:
                db = ReactionDatabase()
                reactions = await db.get_reactions_with_yield(min_yield=0, limit=10000)
            except Exception as exc:
                logger.warning(f"Database unavailable for condition training: {exc}")

        logger.info(f"Loaded {len(reactions)} reactions")

        X = []
        y_temp = []
        y_catalyst = []
        y_solvent = []
        target_sources = []

        for rxn in reactions:
            features = self.compute_reaction_features(rxn)

            # Temperature target
            temp = rxn.get('temperature_celsius')
            if temp is not None:
                canonical_catalyst, canonical_solvent, target_source = self._canonical_condition_targets(rxn)
                X.append(features)
                y_temp.append(temp)
                y_catalyst.append(canonical_catalyst)
                y_solvent.append(canonical_solvent)
                target_sources.append(target_source)

        X = np.array(X)

        # Encode categorical targets
        y_catalyst_encoded = self.catalyst_encoder.fit_transform(y_catalyst)
        y_solvent_encoded = self.solvent_encoder.fit_transform(y_solvent)

        logger.info(f"Prepared {len(X)} samples")
        logger.info(f"Unique catalysts: {len(self.catalyst_encoder.classes_)}")
        logger.info(f"Unique solvents: {len(self.solvent_encoder.classes_)}")
        logger.info(
            "Condition target sources: "
            f"chemistry_prior={target_sources.count('chemistry_prior')}, "
            f"raw_label={target_sources.count('raw_label')}"
        )

        return X, {
            'temperature': np.array(y_temp),
            'catalyst': np.array([str(label) for label in y_catalyst], dtype=object),
            'solvent': np.array([str(label) for label in y_solvent], dtype=object),
            'catalyst_encoded': y_catalyst_encoded,
            'solvent_encoded': y_solvent_encoded,
            'target_source': np.array(target_sources, dtype=object),
        }

    def _load_condition_training_json(self) -> List[Dict[str, Any]]:
        candidate_paths = [
            Path("training_reactions.json"),
            Path("backend/data/training_reactions.json"),
            Path(__file__).parent.parent / "data" / "training_reactions.json",
        ]
        for path in candidate_paths:
            if path.exists():
                try:
                    with open(path, "r") as f:
                        data = json.load(f)
                    logger.info(f"Loaded condition training data from {path}")
                    return data
                except Exception as exc:
                    logger.warning(f"Failed to load condition training data from {path}: {exc}")
        return []

    def _canonical_condition_targets(self, reaction: Dict[str, Any]) -> Tuple[str, str, str]:
        hierarchy_key = self._select_hierarchy_key(reaction)
        if hierarchy_key is not None:
            catalyst, solvent = CATALYST_HIERARCHY[hierarchy_key]["primary"]
            return self._condition_label(catalyst), self._condition_label(solvent), "chemistry_prior"
        return (
            self._condition_label(reaction.get("catalyst", "None")),
            self._condition_label(reaction.get("solvent", "None")),
            "raw_label",
        )

    def _matched_condition_prior(self, reaction_type: Any) -> Optional[Tuple[Optional[str], Optional[str]]]:
        hierarchy_key = self._select_hierarchy_key({"reaction_type": reaction_type})
        if hierarchy_key is not None:
            return CATALYST_HIERARCHY[hierarchy_key]["primary"]
        return None

    def _select_hierarchy_key(self, reaction: Dict[str, Any]) -> Optional[str]:
        rxn_type = self._normalize_text(reaction.get("reaction_type", ""))
        if "esterification" in rxn_type and self._has_chiral_center(reaction):
            return "esterification_chiral"
        for key in sorted(CATALYST_HIERARCHY, key=len, reverse=True):
            if self._normalize_text(key) in rxn_type:
                return key
        return None

    def _has_chiral_center(self, reaction: Dict[str, Any]) -> bool:
        if reaction.get("chiral") or reaction.get("enantioselective"):
            return True
        for field in ("reactants", "products"):
            for value in reaction.get(field) or []:
                smiles = value.get("smiles", "") if isinstance(value, dict) else str(value or "")
                mol = Chem.MolFromSmiles(smiles) if smiles else None
                if mol and Chem.FindMolChiralCenters(mol, includeUnassigned=True):
                    return True
        return False

    @staticmethod
    def _condition_label(value: Any) -> str:
        text = str(value or "None").strip()
        return "None" if text.lower() in {"", "none", "null", "nan"} else text

    async def train(self, test_size: float = 0.2, random_state: int = 42):
        """Train condition prediction models."""
        logger.info("Starting condition prediction training...")

        # Prepare data
        X, y_dict = await self.prepare_training_data()

        if len(X) < 50:
            logger.warning(f"Insufficient data: {len(X)} samples")
            return None

        train_idx, test_idx = self._condition_train_test_indices(
            y_dict['catalyst'],
            test_size=test_size,
            random_state=random_state,
        )
        X_train, X_test = X[train_idx], X[test_idx]
        y_temp_train, y_temp_test = y_dict['temperature'][train_idx], y_dict['temperature'][test_idx]
        y_cat_train, y_cat_test = y_dict['catalyst'][train_idx], y_dict['catalyst'][test_idx]
        y_solv_train, y_solv_test = y_dict['solvent'][train_idx], y_dict['solvent'][test_idx]

        metrics = {}

        logger.info("Training multi-model temperature predictor...")
        self.temp_multi_model = MultiModelRegressor(random_state=random_state)
        temp_metrics = self.temp_multi_model.fit(X_train, y_temp_train, X_test, y_temp_test)
        self.temp_model = self.temp_multi_model.get_best_model()

        logger.info("Training multi-model catalyst predictor...")
        self.catalyst_multi_model = MultiModelClassifier(random_state=random_state)
        catalyst_metrics = self.catalyst_multi_model.fit(X_train, y_cat_train, X_test, y_cat_test)
        self.catalyst_model = self.catalyst_multi_model.get_best_model()

        logger.info("Training multi-model solvent predictor...")
        self.solvent_multi_model = MultiModelClassifier(random_state=random_state)
        solvent_metrics = self.solvent_multi_model.fit(X_train, y_solv_train, X_test, y_solv_test)
        self.solvent_model = self.solvent_multi_model.get_best_model()

        temp_ensemble = temp_metrics.get("ensemble", {})
        catalyst_ensemble = catalyst_metrics.get("ensemble", {})
        solvent_ensemble = solvent_metrics.get("ensemble", {})

        self.model_metrics = {
            "temperature": temp_metrics,
            "catalyst": catalyst_metrics,
            "solvent": solvent_metrics,
            "n_samples": int(len(X)),
            "n_features": int(X.shape[1]),
            "best_models": {
                "temperature": self.temp_multi_model.best_model_name,
                "catalyst": self.catalyst_multi_model.best_model_name,
                "solvent": self.solvent_multi_model.best_model_name,
            },
            "target_policy": "chemistry_prior_targets_for_known_reaction_types",
            "target_sources": {
                "chemistry_prior": int(np.sum(y_dict.get("target_source", []) == "chemistry_prior")),
                "raw_label": int(np.sum(y_dict.get("target_source", []) == "raw_label")),
            },
            "skipped_models": {
                "temperature": self.temp_multi_model.skipped_models,
                "catalyst": self.catalyst_multi_model.skipped_models,
                "solvent": self.solvent_multi_model.skipped_models,
            },
        }

        metrics.update({
            "temperature_mae": float(temp_ensemble.get("test_mae", 0.0)),
            "temperature_r2": float(temp_ensemble.get("test_r2", 0.0)),
            "catalyst_accuracy": float(catalyst_ensemble.get("accuracy", 0.0)),
            "catalyst_macro_f1": float(catalyst_ensemble.get("macro_f1", 0.0)),
            "solvent_accuracy": float(solvent_ensemble.get("accuracy", 0.0)),
            "solvent_macro_f1": float(solvent_ensemble.get("macro_f1", 0.0)),
            "n_samples": len(X),
            "n_features": X.shape[1],
            "model_metrics": self.model_metrics,
        })

        self.save_models()
        return metrics

    def _condition_train_test_indices(
        self,
        stratify_labels: np.ndarray,
        test_size: float,
        random_state: int,
    ) -> Tuple[np.ndarray, np.ndarray]:
        indices = np.arange(len(stratify_labels))
        values, counts = np.unique(stratify_labels, return_counts=True)
        stratify = stratify_labels if len(values) > 1 and int(np.min(counts)) >= 2 else None
        train_idx, test_idx = train_test_split(
            indices,
            test_size=test_size,
            random_state=random_state,
            stratify=stratify,
        )
        return train_idx, test_idx

        # Train temperature model (regression)
        logger.info("Training temperature predictor...")
        self.temp_model = xgb.XGBRegressor(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            random_state=random_state
        )
        self.temp_model.fit(X_train, y_temp_train)

        temp_pred = self.temp_model.predict(X_test)
        temp_mae = mean_absolute_error(y_temp_test, temp_pred)
        logger.info(f"Temperature MAE: {temp_mae:.2f} deg C")
        print(f"  MAE: {metrics['temperature_mae']:.2f} deg C")

        # Train catalyst model (classification)
        logger.info("Training catalyst predictor...")
        self.catalyst_model = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            random_state=random_state
        )
        self.catalyst_model.fit(X_train, y_cat_train)

        cat_pred = self.catalyst_model.predict(X_test)
        cat_acc = accuracy_score(y_cat_test, cat_pred)
        logger.info(f"Catalyst accuracy: {cat_acc:.2%}")
        metrics['catalyst_accuracy'] = float(cat_acc)

        # Train solvent model (classification)
        logger.info("Training solvent predictor...")
        self.solvent_model = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            random_state=random_state
        )
        self.solvent_model.fit(X_train, y_solv_train)

        solv_pred = self.solvent_model.predict(X_test)
        solv_acc = accuracy_score(y_solv_test, solv_pred)
        logger.info(f"Solvent accuracy: {solv_acc:.2%}")
        metrics['solvent_accuracy'] = float(solv_acc)

        # Save models
        self.save_models()

        metrics['n_samples'] = len(X)
        metrics['n_features'] = X.shape[1]

        return metrics

    def predict(self, reaction: Dict[str, Any]) -> Dict[str, Any]:
        """Predict optimal conditions for a reaction."""
        if not self.models_loaded:
            self.load_models()

        if all([self.temp_multi_model, self.catalyst_multi_model, self.solvent_multi_model]):
            return self._predict_with_multi_models(reaction)

        if not all([self.temp_model, self.catalyst_model, self.solvent_model]):
            # Use fallback values if models are not loaded
            return {
                "temperature_celsius": 25.0,
                "catalyst": "unknown",
                "solvent": "THF",
                "confidence": "low",
                "time_hours": 4.0,
                "fallback": True,
                "model_results": {},
                "ensemble_consensus": {},
                "model_decision": "fallback",
            }

        catalyst_hint = reaction.get('catalyst')
        solvent_hint = reaction.get('solvent')
        if catalyst_hint is not None:
            self.catalyst_encoder.transform([catalyst_hint])
        if solvent_hint is not None:
            self.solvent_encoder.transform([solvent_hint])

        features = self.compute_reaction_features(reaction).reshape(1, -1)

        # Predict temperature
        temp_pred = self.temp_model.predict(features)[0]
        temp_pred = max(-50, min(200, temp_pred))  # Reasonable range

        # Predict catalyst (with probabilities)
        cat_proba = self.catalyst_model.predict_proba(features)[0]
        cat_idx = np.argmax(cat_proba)
        catalyst = self.catalyst_encoder.inverse_transform([cat_idx])[0]
        cat_confidence = float(cat_proba[cat_idx])

        # Predict solvent (with probabilities)
        solv_proba = self.solvent_model.predict_proba(features)[0]
        solv_idx = np.argmax(solv_proba)
        solvent = self.solvent_encoder.inverse_transform([solv_idx])[0]
        solv_confidence = float(solv_proba[solv_idx])

        # Overall confidence
        confidence = 'high' if min(cat_confidence, solv_confidence) > 0.7 else                     'medium' if min(cat_confidence, solv_confidence) > 0.5 else 'low'

        return {
            'temperature_celsius': float(temp_pred),
            'catalyst': str(catalyst) if catalyst != 'None' else None,
            'solvent': str(solvent) if solvent != 'None' else None,
            'confidence': confidence,
            'catalyst_confidence': cat_confidence,
            'solvent_confidence': solv_confidence,
            'alternative_catalysts': self._get_alternatives(cat_proba, self.catalyst_encoder, top_k=3),
            'alternative_solvents': self._get_alternatives(solv_proba, self.solvent_encoder, top_k=3),
            'model_results': {
                'temperature': {
                    'individual_predictions': {'xgboost_legacy': float(temp_pred)},
                    'ensemble_prediction': float(temp_pred),
                    'best_model': 'xgboost_legacy',
                    'model_metrics': self.model_metrics.get('temperature', {}),
                },
                'catalyst': {
                    'individual_predictions': {
                        'xgboost_legacy': {
                            'prediction': str(catalyst),
                            'confidence': cat_confidence,
                        }
                    },
                    'ensemble_prediction': str(catalyst),
                    'best_model': 'xgboost_legacy',
                    'model_metrics': self.model_metrics.get('catalyst', {}),
                },
                'solvent': {
                    'individual_predictions': {
                        'xgboost_legacy': {
                            'prediction': str(solvent),
                            'confidence': solv_confidence,
                        }
                    },
                    'ensemble_prediction': str(solvent),
                    'best_model': 'xgboost_legacy',
                    'model_metrics': self.model_metrics.get('solvent', {}),
                },
            },
            'ensemble_consensus': {
                'temperature_celsius': float(temp_pred),
                'catalyst': str(catalyst) if catalyst != 'None' else None,
                'solvent': str(solvent) if solvent != 'None' else None,
            },
            'model_decision': 'legacy_model',
        }

    def _predict_with_multi_models(self, reaction: Dict[str, Any]) -> Dict[str, Any]:
        """Predict conditions from multi-model regression/classification bundles."""
        features = self.compute_reaction_features(reaction).reshape(1, -1)

        temp_summary = self.temp_multi_model.prediction_summary(features, clip_range=(-50, 200))
        cat_summary = self.catalyst_multi_model.prediction_summary(features)
        solv_summary = self.solvent_multi_model.prediction_summary(features)

        temp_pred = temp_summary.get("ensemble_prediction")
        if temp_pred is None:
            temp_pred = 25.0
        temp_pred = float(np.clip(float(temp_pred), -50, 200))

        catalyst = self._normalize_none_label(cat_summary.get("ensemble_prediction"))
        solvent = self._normalize_none_label(solv_summary.get("ensemble_prediction"))

        cat_confidence = self._classification_confidence(cat_summary)
        solv_confidence = self._classification_confidence(solv_summary)
        consensus_floor = min(cat_confidence, solv_confidence)
        confidence = (
            "high" if consensus_floor >= 0.7
            else "medium" if consensus_floor >= 0.5
            else "low"
        )

        return {
            "temperature_celsius": temp_pred,
            "catalyst": catalyst,
            "solvent": solvent,
            "confidence": confidence,
            "catalyst_confidence": float(cat_confidence),
            "solvent_confidence": float(solv_confidence),
            "alternative_catalysts": self._classification_alternatives(cat_summary),
            "alternative_solvents": self._classification_alternatives(solv_summary),
            "model_results": {
                "temperature": temp_summary,
                "catalyst": cat_summary,
                "solvent": solv_summary,
            },
            "ensemble_consensus": {
                "temperature_celsius": round(temp_pred, 2),
                "catalyst": catalyst,
                "solvent": solvent,
            },
            "model_decision": "ensemble",
        }

    @staticmethod
    def _normalize_none_label(label: Any) -> Optional[str]:
        if label is None:
            return None
        text = str(label)
        return None if text.lower() in {"none", "null", ""} else text

    def _classification_confidence(self, summary: Dict[str, Any]) -> float:
        consensus = summary.get("ensemble_prediction")
        for item in summary.get("alternatives", []):
            if item.get("option") == consensus:
                if item.get("confidence") is not None:
                    return float(item["confidence"])
                return float(summary.get("consensus_fraction") or 0.0)
        return float(summary.get("consensus_fraction") or 0.0)

    def _classification_alternatives(self, summary: Dict[str, Any], top_k: int = 3) -> List[Dict[str, Any]]:
        alternatives = []
        for item in summary.get("alternatives", [])[:top_k]:
            option = self._normalize_none_label(item.get("option"))
            if option is None:
                continue
            alternatives.append({
                "option": option,
                "confidence": item.get("confidence"),
                "votes": item.get("votes"),
            })
        return alternatives

    def predict_safe(self, reaction: Dict[str, Any]) -> Dict[str, Any]:
        """Safe prediction wrapper that returns fallback conditions when prediction fails."""
        try:
            return self.predict_conditions(reaction)
        except Exception as e:
            logger.error(f"predict_conditions failed: {e}")
            return self._fallback_response()

    def _fallback_response(self) -> Dict[str, Any]:
        return {
            "temperature_celsius": 25.0,
            "temperature_range": (20, 30),
            "catalyst": None,
            "solvent": "THF",
            "time_hours": 4.0,
            "confidence": "low",
            "source": "fallback",
            "hierarchy_level": None,
            "catalyst_type": "unknown",
            "catalyst_cost_per_kg": 0.0,
            "separation_method": "standard workup",
            "reuse_cycles": 1,
            "metal_leaching_risk": "unknown",
            "pd_removal_required": False,
            "regulatory_note": "Fallback estimate; verify experimentally.",
            "biocatalytic_alternative": None,
            "safety_warnings": [],
            "notes": "No reaction-type prior matched.",
            "fallback": True,
        }

    # Safety filter

    # Known incompatible reagent-solvent pairs: (reagent_kw, solvent_kw) -> warning
    _INCOMPATIBLE_PAIRS = [
        (["n-buli", "nbuli", "butyllithium", "buli", "lda", "organolithium",
          "grignard", "mgbr", "nah", "kh", "lah", "lithium aluminum"],
         ["ethanol", "methanol", "water", "protic", "isopropanol", "iPrOH"],
         "Strong base/nucleophile reacts violently with protic solvents"),
        (["alcl3", "aluminum chloride", "becl2", "lewis acid", "bf3", "ticl4"],
         ["water", "methanol", "ethanol", "dmso"],
         "Lewis acid hydrolyses/deactivates in protic/coordinating media"),
        (["pd", "palladium", "pdcl2"],
         ["dmso"],
         "DMSO can coordinate and poison Pd catalysts at elevated temperature"),
        (["lialh4", "lithium aluminum hydride"],
         ["water", "methanol", "ethanol", "thf/water", "ether/water"],
         "LiAlH4 reacts explosively with protic solvents - use dry ether or THF only"),
        (["peroxide", "m-cpba", "oxone", "peracid"],
         ["acetone", "thf"],
         "Peroxides may form explosive peroxide salts with certain solvents"),
    ]

    def check_compatibility(self, reagent: str, solvent: str) -> list:
        """
        Check for known reagent-solvent incompatibilities.

        Returns a list of warning strings (empty list = safe).

        Parameters
        ----------
        reagent : str
            Reagent/catalyst name or SMILES.
        solvent : str
            Solvent name.
        """
        warnings = []
        r = str(reagent or "").lower()
        s = str(solvent or "").lower()

        for reagent_kws, solvent_kws, message in self._INCOMPATIBLE_PAIRS:
            reagent_match = any(kw in r for kw in reagent_kws)
            solvent_match = any(kw in s for kw in solvent_kws)
            if reagent_match and solvent_match:
                warnings.append(
                    f"INCOMPATIBILITY: {reagent!r} + {solvent!r} - {message}"
                )

        return warnings

    # Temperature prior

    # Reaction-type -> (typical_low, typical_high)
    _TEMP_PRIORS = {
        'grignard': (-78, 0),
        'organolithium': (-78, -40),
        'diels_alder': (100, 220),
        'diels-alder': (100, 220),
        'esterification': (60, 120),
        'fischer_esterification': (60, 120),
        'reduction': (0, 25),
        'nabh4': (0, 25),
        'lialh4': (-20, 0),
        'hydrogenation': (20, 60),
        'suzuki': (60, 100),
        'buchwald_hartwig': (80, 120),
        'amide_coupling': (0, 25),
        'amide_formation': (0, 25),
        'reductive_amination': (20, 40),
        'wittig': (-78, 25),
        'aldol': (-78, 25),
        'sn2': (25, 80),
        'oxidation': (0, 40),
        'nitration': (0, 60),
        'bromination': (0, 25),
        'chlorination': (0, 25),
        'fluorination': (80, 160),   # nucleophilic aromatic fluorination
        'boc_deprotection': (0, 25),
        'deprotection_boc': (0, 25),
        'cbz_deprotection': (20, 40),
        'acylation': (0, 25),
        'friedel_crafts': (-10, 25),
        'alkylation': (0, 80),
        'heck': (80, 140),
        'nitro_reduction': (20, 80),
    }

    def predict_temperature(self, reaction: dict) -> dict:
        """
        Return a temperature estimate based on reaction type and (optionally)
        the ML temp_model if it is loaded.
        """
        rxn_type = reaction.get("reaction_type", "").lower()

        # Look up the prior
        prior_key = next(
            (k for k in sorted(self._TEMP_PRIORS, key=len, reverse=True) if k in rxn_type), None
        )
        if prior_key is not None:
            lo, hi = self._TEMP_PRIORS[prior_key]
            midpoint = (lo + hi) / 2.0
            return {
                "temperature_celsius": midpoint,
                "temperature_range": (lo, hi),
                "source": "chemistry_prior"
            }
        
        ml_temp = None
        # Try ML model if loaded
        if self.temp_multi_model is not None:
            try:
                features = self.compute_reaction_features(reaction).reshape(1, -1)
                ml_temp = self.temp_multi_model.predict(features, clip_range=(-100, 250))
            except Exception:
                ml_temp = None
        elif self.temp_model is not None:
            try:
                features = self.compute_reaction_features(reaction).reshape(1, -1)
                ml_pred = float(self.temp_model.predict(features)[0])
                ml_temp = max(-100, min(250, ml_pred))
            except Exception:
                pass

        if ml_temp is not None:
            return {
                "temperature_celsius": ml_temp,
                "source": "ml_only"
            }
        else:
            return {
                "temperature_celsius": 25.0,
                "source": "default"
            }

    REACTION_TIMES = {
        'grignard': (2.0, 6.0),
        'suzuki': (2.0, 8.0),
        'amide_coupling': (2.0, 12.0),
        'boc_deprotection': (0.5, 2.0),
        'deprotection_boc': (0.5, 2.0),
        'reduction': (0.5, 3.0),
        'hydrogenation': (1.0, 24.0),
        'nitro_reduction': (2.0, 8.0),
        'esterification': (2.0, 8.0),
        'bromination': (1.0, 4.0),
        'fluorination': (4.0, 24.0),
        'diels_alder': (1.0, 12.0),
        'wittig': (1.0, 6.0),
        'heck': (4.0, 24.0),
        'aldol': (1.0, 4.0),
        'reductive_amination': (4.0, 16.0),
    }

    def _estimate_time(self, reaction_type: str) -> float:
        for key, (lo, hi) in self.REACTION_TIMES.items():
            if key in reaction_type.lower():
                return round((lo + hi) / 2, 1)
        return 4.0

    def predict_conditions(self, reaction: Dict[str, Any]) -> Dict[str, Any]:
        """Predict optimal conditions, falling back to ML when no prior exists."""
        reaction_type = self._normalize_text(reaction.get('reaction_type', ''))
        if self._cacheable_prior_request(reaction):
            cached = self._cached_condition_prior(reaction_type)
            if cached:
                return deepcopy(cached)

        hierarchy_key = self._select_hierarchy_key(reaction)
        if hierarchy_key is not None:
            return self._build_hierarchy_condition_payload(reaction, hierarchy_key)

        if reaction.get("fast_prior_only"):
            temp_result = self.predict_temperature(reaction)
            fallback = self._fallback_response()
            fallback.update({
                "temperature_celsius": temp_result["temperature_celsius"],
                "temperature_range": temp_result.get("temperature_range", fallback.get("temperature_range")),
                "source": "fast_prior_fallback",
                "notes": "No reaction-type hierarchy matched; ML skipped for fast route enrichment.",
            })
            return fallback

        if not self.models_loaded:
            self.load_models()
        ml_context: Dict[str, Any] = {}
        if all([self.temp_multi_model, self.catalyst_multi_model, self.solvent_multi_model]):
            try:
                ml_context = self._predict_with_multi_models(reaction)
            except Exception as exc:
                logger.warning(f"Multi-model condition prediction unavailable: {exc}")

        ml_pred = self.predict(reaction)
        temp_result = self.predict_temperature(reaction)
        ml_pred["temperature_celsius"] = temp_result["temperature_celsius"]
        if "temperature_range" in temp_result:
            ml_pred["temperature_range"] = temp_result["temperature_range"]
        
        ml_pred["time_hours"] = self._estimate_time(reaction_type)
        ml_pred["safety_warnings"] = self.check_compatibility(
            ml_pred.get("catalyst", ""), ml_pred.get("solvent", "")
        )
        catalyst = str(ml_pred.get("catalyst") or "")
        pd_required = "Pd" in catalyst and "/C" not in catalyst and "Al2O3" not in catalyst
        ml_pred.setdefault("temperature_range", temp_result.get("temperature_range"))
        ml_pred.update({
            "hierarchy_level": None,
            "catalyst_type": "ml_model",
            "catalyst_cost_per_kg": 0.0,
            "separation_method": "standard workup",
            "reuse_cycles": 1,
            "metal_leaching_risk": "high" if pd_required else "unknown",
            "pd_removal_required": pd_required,
            "regulatory_note": "ML-only condition; verify against chemistry hierarchy.",
            "biocatalytic_alternative": "Evaluate biocatalysis if stereocenter-forming step" if pd_required else None,
            "notes": "No chemistry prior matched; ML/legacy prediction used.",
        })
        return ml_pred

    def _cacheable_prior_request(self, reaction: Dict[str, Any]) -> bool:
        return (
            bool(reaction.get("reaction_type"))
            and not reaction.get("reactants")
            and not reaction.get("products")
            and not reaction.get("batch_size_kg")
            and not reaction.get("substrate_mw")
        )

    @lru_cache(maxsize=64)
    def _cached_condition_prior(self, reaction_type: str) -> Dict[str, Any]:
        reaction = {"reaction_type": reaction_type}
        hierarchy_key = self._select_hierarchy_key(reaction)
        if hierarchy_key is None:
            return {}
        return self._build_hierarchy_condition_payload(reaction, hierarchy_key)

    def _build_hierarchy_condition_payload(
        self,
        reaction: Dict[str, Any],
        hierarchy_key: str,
    ) -> Dict[str, Any]:
        reaction_type = self._normalize_text(reaction.get("reaction_type", ""))
        entry = CATALYST_HIERARCHY[hierarchy_key]
        catalyst, solvent = entry["primary"]
        temp_result = self.predict_temperature(reaction)
        cost_payload = self.catalyst_cost_analysis.build_payload(catalyst, entry, reaction)
        return {
            "temperature_celsius": temp_result["temperature_celsius"],
            "temperature_range": temp_result.get("temperature_range"),
            "catalyst": catalyst,
            "solvent": solvent,
            "time_hours": self._estimate_time(reaction_type),
            "confidence": "high",
            "source": "chemistry_prior",
            "hierarchy_level": entry.get("level"),
            "catalyst_type": entry.get("type"),
            "catalyst_cost_per_kg": cost_payload["catalyst_cost_per_kg"],
            "separation_method": cost_payload["separation_method"],
            "reuse_cycles": cost_payload["reuse_cycles"],
            "metal_leaching_risk": cost_payload["metal_leaching_risk"],
            "pd_removal_required": cost_payload["pd_removal_required"],
            "regulatory_note": cost_payload["regulatory_note"],
            "biocatalytic_alternative": cost_payload["biocatalytic_alternative"],
            "estimated_pmi_contribution": cost_payload["estimated_pmi_contribution"],
            "safety_warnings": self.check_compatibility(catalyst or "", solvent or ""),
            "notes": entry.get("note"),
            "model_results": {},
            "ensemble_consensus": {},
            "model_decision": "chemistry_prior",
            "ml_alternative_conditions": {},
        }


    def _get_alternatives(self, proba: np.ndarray, encoder: SafeLabelEncoder, top_k: int = 3) -> List[Dict]:
        """Get top alternative options with probabilities."""
        top_indices = np.argsort(proba)[-top_k:][::-1]
        alternatives = []

        for idx in top_indices:
            label = encoder.inverse_transform([idx])[0]
            if label != 'None':
                alternatives.append({
                    'option': str(label),
                    'confidence': float(proba[idx])
                })

        return alternatives

    def save_models(self):
        """Save all models to disk."""
        models_data = {
            'temp_model': self.temp_model,
            'catalyst_model': self.catalyst_model,
            'solvent_model': self.solvent_model,
            'temp_multi_model': self.temp_multi_model,
            'catalyst_multi_model': self.catalyst_multi_model,
            'solvent_multi_model': self.solvent_multi_model,
            'catalyst_encoder': self.catalyst_encoder,
            'solvent_encoder': self.solvent_encoder,
            'model_metrics': self.model_metrics,
            'feature_size': self.CONDITION_FEATURE_SIZE,
        }

        model_path = self.model_dir / 'condition_models.pkl'
        with open(model_path, 'wb') as f:
            pickle.dump(models_data, f)

        metrics_path = self.model_dir / 'condition_model_metrics.json'
        with open(metrics_path, 'w') as f:
            json.dump(self.model_metrics, f, indent=2)

        logger.info(f"Condition models saved to {model_path}")

    def load_models(self) -> bool:
        """Load models from disk."""
        model_path = self.model_dir / 'condition_models.pkl'

        if not model_path.exists():
            logger.warning(f"Model file not found: {model_path}")
            return False

        try:
            with open(model_path, 'rb') as f:
                models_data = _ConditionModelUnpickler(f).load()

            artifact_feature_size = models_data.get('feature_size')
            if artifact_feature_size != self.CONDITION_FEATURE_SIZE:
                logger.warning(
                    "Condition model feature size mismatch: "
                    f"artifact={artifact_feature_size}, expected={self.CONDITION_FEATURE_SIZE}. "
                    "Retrain condition models."
                )
                return False

            self.temp_model = models_data['temp_model']
            self.catalyst_model = models_data['catalyst_model']
            self.solvent_model = models_data['solvent_model']
            self.temp_multi_model = models_data.get('temp_multi_model')
            self.catalyst_multi_model = models_data.get('catalyst_multi_model')
            self.solvent_multi_model = models_data.get('solvent_multi_model')
            self.catalyst_encoder = models_data['catalyst_encoder']
            self.solvent_encoder = models_data['solvent_encoder']
            self.model_metrics = models_data.get('model_metrics', {})

            self.models_loaded = True
            logger.info("Condition models loaded successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to load models: {str(e)}")
            return False


async def main():
    """Train condition prediction models."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    predictor = ConditionPredictor()
    metrics = await predictor.train()

    if metrics:
        print("\n" + "=" * 50)
        print("Condition Prediction Models Training Complete")
        print("=" * 50)
        print(f"Samples: {metrics['n_samples']}")
        print(f"Features: {metrics['n_features']}")
        print("\nTemperature Predictor:")
        print(f"  MAE: {metrics['temperature_mae']:.2f} deg C")
        print("\nCatalyst Predictor:")
        print(f"  Accuracy: {metrics['catalyst_accuracy']:.2%}")
        print("\nSolvent Predictor:")
        print(f"  Accuracy: {metrics['solvent_accuracy']:.2%}")
        print("=" * 50)

        # Test prediction
        print("\nTesting prediction on sample reaction...")
        test_reaction = {
            'reactants': ['c1ccccc1', 'CC(=O)Cl'],
            'products': ['CC(=O)c1ccccc1'],
            'reaction_type': 'Friedel-Crafts acylation'
        }

        conditions = predictor.predict_safe(test_reaction)
        print("\nPredicted Conditions:")
        print(f"  Temperature: {conditions['temperature_celsius']:.1f} deg C")
        print(f"  Catalyst: {conditions['catalyst']}")
        print(f"  Solvent: {conditions['solvent']}")
        print(f"  Confidence: {conditions['confidence']}")
        print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())

