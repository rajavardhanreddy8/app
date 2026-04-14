"""
Phase 2 \u2014 building block catalog and utility.
Provides a set of commercially available SMILES for retrosynthesis termination.
"""
from typing import Set, FrozenSet
from rdkit import Chem

# A representative set of ~80+ building blocks
COMMON_BUILDING_BLOCKS = [
    "c1ccccc1", "Cc1ccccc1", "c1ccccc1Br", "c1ccccc1Cl", "c1ccccc1I", "Nc1ccccc1",
    "Oc1ccccc1", "c1ccccc1C(=O)O", "Oc1ccccc1C(=O)O", "CC(=O)Cl", "CCOC(C)=O",
    "CCO", "CN", "CCN", "CCC(C)O", "CC(C)(C)O", "C1CCOC1", "ClCCl", "CS(=O)C",
    "OB(O)c1ccccc1", "OB(O)c1ccc(C)cc1", "OB(O)c1ccc(F)cc1", "OB(O)c1ccc(Cl)cc1",
    "Brc1ccc(O)cc1", "Brc1ccc(N)cc1", "Brc1ccc(C(=O)O)cc1", "Brc1ccc(C#N)cc1",
    "CCCCN", "CCCC(C)N", "CC(C)CN", "CC(C)(C)N", "O=C(Cl)c1ccccc1", "O=C(Cl)CC",
    "O=C(C)CC", "C1CCCCC1", "c1ccncc1", "c1ccsc1", "c1cnoc1", "O=C1CCC1", "O=C1CCCC1",
    "O=C1CCCCC1", "OCC", "OCCC", "OCCCC", "OC5CCCCC5", "NCC", "NCCC", "NCCCC",
    "CC(=O)O", "CCC(=O)O", "CCCC(=O)O", "CCCCC(=O)O", "c1ccccc1O", "c1ccccc1N",
    "c1ccccc1C(=O)Cl", "CC(C)C", "C=C", "C#C", "C=CC", "C#CC", "C=CCCC",
    "F", "Cl", "Br", "I", "CC(F)(F)F", "CC(Cl)(Cl)Cl", "c1ccc(cc1)B(O)O",
    "CC1(C)OB(OC1(C)C)c2ccccc2", "CC1(C)OB(OC1(C)C)c2ccc(C)cc2",
    "CCCC", "CCCCC", "CCCCCC", "CCCCCCC", "CCCCCCCC", "CCCCCCCCC", "CCCCCCCCCC",
    "Cc1ccccc1C", "Cc1cccc(C)c1", "Cc1ccc(C)cc1", "CC(=O)C", "CCC(=O)C",
    "n1ccccc1", "n1[nH]ccc1", "n1c[nH]cc1", "o1cccc1", "s1cccc1"
]

def _get_canonical_set() -> FrozenSet[str]:
    canonical = set()
    for smi in COMMON_BUILDING_BLOCKS:
        mol = Chem.MolFromSmiles(smi)
        if mol:
            canonical.add(Chem.MolToSmiles(mol))
    return frozenset(canonical)

CANONICAL_BUILDING_BLOCKS = _get_canonical_set()

def is_building_block_smiles(smiles: str) -> bool:
    """Checks if a SMILES string (or its canonical form) is in the catalog."""
    if not smiles: return False
    try:
        mol = Chem.MolFromSmiles(smiles)
        if not mol: return False
        canonical = Chem.MolToSmiles(mol)
        return canonical in CANONICAL_BUILDING_BLOCKS
    except:
        return False
