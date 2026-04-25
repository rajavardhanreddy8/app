from rdkit import Chem
from rdkit.Chem import Descriptors, Crippen, Lipinski, AllChem
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)


def normalize_reaction_fields(reaction: dict) -> dict:
    """
    Normalize reaction/step field names across planner modules.

    Mappings (keeps both source and target keys for compatibility):
    - temperature_celsius -> temperature_c
    - time_hours -> time_h
    - conditions.temperature_celsius -> top-level temperature_c

    The function is idempotent and safe to call multiple times.
    It also normalizes nested dict/list structures, including step.conditions.*
    """
    if not isinstance(reaction, dict):
        return reaction

    normalized = dict(reaction)

    # Recurse into nested structures first.
    for key, value in list(normalized.items()):
        if isinstance(value, dict):
            normalized[key] = normalize_reaction_fields(value)
        elif isinstance(value, list):
            normalized[key] = [
                normalize_reaction_fields(item) if isinstance(item, dict) else item
                for item in value
            ]

    # Top-level aliases.
    if "temperature_celsius" in normalized and "temperature_c" not in normalized:
        normalized["temperature_c"] = normalized["temperature_celsius"]
    if "time_hours" in normalized and "time_h" not in normalized:
        normalized["time_h"] = normalized["time_hours"]

    # Nested conditions aliases promoted to top level.
    conditions = normalized.get("conditions")
    if isinstance(conditions, dict):
        if "temperature_celsius" in conditions:
            normalized.setdefault("temperature_celsius", conditions["temperature_celsius"])
            normalized.setdefault("temperature_c", conditions["temperature_celsius"])
        if "time_hours" in conditions:
            normalized.setdefault("time_hours", conditions["time_hours"])
            normalized.setdefault("time_h", conditions["time_hours"])

    return normalized

class MolecularService:
    """Service for molecular structure operations using RDKit."""
    
    @staticmethod
    def parse_smiles(smiles: str) -> Dict[str, Any]:
        """Parse SMILES string and extract molecular properties."""
        if isinstance(smiles, dict):
            smiles = smiles.get('smiles', '')
        try:
            mol = Chem.MolFromSmiles(str(smiles))
            if mol is None:
                return {"valid": False, "error": "Invalid SMILES string"}
            
            # Calculate molecular properties
            molecular_weight = Descriptors.MolWt(mol)
            logp = Crippen.MolLogP(mol)
            hbd = Descriptors.NumHDonors(mol)
            hba = Descriptors.NumHAcceptors(mol)
            tpsa = Descriptors.TPSA(mol)
            rotatable_bonds = Descriptors.NumRotatableBonds(mol)
            
            # Check Lipinski's rule of five
            lipinski_violations = sum([
                molecular_weight > 500,
                logp > 5,
                hbd > 5,
                hba > 10
            ])
            
            # Get canonical SMILES
            canonical_smiles = Chem.MolToSmiles(mol)
            
            return {
                "valid": True,
                "smiles": smiles,
                "canonical_smiles": canonical_smiles,
                "molecular_weight": round(molecular_weight, 2),
                "logp": round(logp, 2),
                "h_donors": hbd,
                "h_acceptors": hba,
                "tpsa": round(tpsa, 2),
                "rotatable_bonds": rotatable_bonds,
                "lipinski_violations": lipinski_violations,
                "num_atoms": mol.GetNumAtoms(),
                "num_bonds": mol.GetNumBonds(),
                "molecular_formula": Chem.rdMolDescriptors.CalcMolFormula(mol)
            }
        except Exception as e:
            logger.error(f"Error parsing SMILES {smiles}: {str(e)}")
            return {"valid": False, "error": str(e)}
    
    @staticmethod
    def validate_smiles(smiles: str) -> Dict[str, bool]:
        """Validate SMILES string for chemical correctness."""
        if isinstance(smiles, dict):
            smiles = smiles.get('smiles', '')
            
        try:
            # Bug Fix 1: Check for empty string before processing
            if not smiles or str(smiles).strip() == "":
                return {"valid": False, "reason": "Empty SMILES string"}
            
            mol = Chem.MolFromSmiles(str(smiles))
            
            if mol is None:
                return {"valid": False, "reason": "Invalid SMILES syntax"}
            
            # Check for issues
            issues = []
            
            # Check for aromatic valence errors
            try:
                Chem.SanitizeMol(mol)
            except Exception as e:
                issues.append(f"Sanitization error: {str(e)}")
            
            return {
                "valid": len(issues) == 0,
                "issues": issues if issues else None
            }
        except Exception as e:
            return {"valid": False, "error": str(e)}
    
    @staticmethod
    def calculate_fingerprint(smiles: str, fp_type: str = "morgan") -> Optional[List[int]]:
        """Calculate molecular fingerprint."""
        if isinstance(smiles, dict):
            smiles = smiles.get('smiles', '')
        try:
            mol = Chem.MolFromSmiles(str(smiles))
            if mol is None:
                return None
            
            if fp_type == "morgan":
                fp = AllChem.GetMorganFingerprintAsBitVect(mol, radius=2, nBits=2048)
                return list(fp)
            else:
                return None
        except Exception as e:
            logger.error(f"Error calculating fingerprint: {str(e)}")
            return None
    
    @staticmethod
    def estimate_reagent_cost(smiles: str) -> float:
        """Estimate reagent cost based on molecular complexity."""
        if isinstance(smiles, dict):
            smiles = smiles.get('smiles', '')
        try:
            mol = Chem.MolFromSmiles(str(smiles))
            if mol is None:
                return 100.0  # Default cost
            
            # Simple heuristic: cost increases with complexity
            mw = Descriptors.MolWt(mol)
            num_atoms = mol.GetNumAtoms()
            rotatable_bonds = Descriptors.NumRotatableBonds(mol)
            
            # Base cost + complexity factors
            base_cost = 10.0
            mw_factor = mw / 100.0
            atom_factor = num_atoms / 10.0
            rotation_factor = rotatable_bonds * 5.0
            
            total_cost = base_cost + mw_factor + atom_factor + rotation_factor
            
            return round(total_cost, 2)
            
        except Exception as e:
            logger.error(f"Error estimating cost: {str(e)}")
            return 100.0
