from rdkit import Chem
from rdkit.Chem import Descriptors, Crippen, Lipinski, AllChem
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)

class MolecularService:
    """Service for molecular structure operations using RDKit."""
    
    @staticmethod
    def parse_smiles(smiles: str) -> Dict[str, Any]:
        """Parse SMILES string and extract molecular properties."""
        try:
            mol = Chem.MolFromSmiles(smiles)
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
        try:
            mol = Chem.MolFromSmiles(smiles)
            
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
        try:
            mol = Chem.MolFromSmiles(smiles)
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
        try:
            mol = Chem.MolFromSmiles(smiles)
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
