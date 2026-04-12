"""Common commercial building blocks catalog for retrosynthesis services."""

from rdkit import Chem

COMMON_BUILDING_BLOCKS = [
    # Simple aromatics (~15)
    "c1ccccc1", "Cc1ccccc1", "Cc1ccccc1C", "Cc1ccc(C)cc1", "Nc1ccccc1",
    "Oc1ccccc1", "O=[N+]([O-])c1ccccc1", "Clc1ccccc1", "Brc1ccccc1", "O=Cc1ccccc1",
    "O=C(O)c1ccccc1", "C=CC1=CC=CC=C1", "COc1ccccc1", "Fc1ccccc1", "Ic1ccccc1",
    "OCc1ccccc1",

    # Heteroaromatics (~10)
    "n1ccccc1", "n1ccnc(n1)", "n1ccncc1", "c1ncc[nH]1", "c1ccsc1",
    "c1ccoc1", "c1ccc2[nH]ccc2c1", "c1ccc2ncccc2c1", "O1CCNCC1", "N1CCCCC1",

    # Simple aliphatics (~15)
    "CO", "CCO", "CCCO", "CC(C)O", "CCCCO",
    "CC(=O)C", "CCC(=O)C", "C1CCCCC1", "O=C1CCCCC1", "CC(=O)O",
    "CCC(=O)O", "O=C(O)C(=O)O", "N#CCC#N", "CC#N", "CN(C)C=O",

    # Amines (~10)
    "CN", "CN(C)", "CN(C)C", "CCN", "CCNCC",
    "CCCCN", "NC1CCCCC1", "NCc1ccccc1", "N1CCNCC1", "NCCOCCO",

    # Acid chlorides / anhydrides (~8)
    "CC(=O)Cl", "O=C(Cl)c1ccccc1", "CC(=O)OC(=O)C", "O=C(Cl)C(=O)Cl", "CC(C)(C)C(=O)Cl",
    "O=C(Cl)CCl", "O=[N+]([O-])c1ccc(C(=O)Cl)cc1", "O=C1OC(=O)CC1",

    # Boronic acids (~8)
    "OB(O)c1ccccc1", "Cc1ccc(B(O)O)cc1", "COc1ccc(B(O)O)cc1", "Fc1ccc(B(O)O)cc1",
    "OB(O)c1ccncc1", "OB(O)c1cccs1", "C=CB(O)O", "C1CC1B(O)O",

    # Halides for coupling (~10)
    "Brc1ccccc1", "Ic1ccccc1", "COc1ccc(Br)cc1", "CC(=O)c1ccc(Br)cc1", "Brc1ncccc1",
    "Brc1cccnc1", "O=Cc1ccc(Br)cc1", "Fc1ccc(Br)cc1", "COc1ccc(I)cc1", "Cc1cccc(I)c1",

    # Grignard/organometallic precursors (~8)
    "C[Mg]Br", "CC[Mg]Br", "c1ccccc1[Mg]Br", "C=CC[Mg]Br", "C=C[Mg]Br", "CC(C)[Mg]Cl",
    "CCCC[Li]", "CC(C)(C)[Li]",

    # Reducing/oxidizing agents and common reagents (~16)
    "[Na+].[BH4-]", "[Li+].[AlH4-]", "CC(C)(C)O[Al](C(C)(C)C)H", "O=C(OOC1=CC=CC=C1Cl)C2=CC=CC=C2Cl",
    "O=I1OC(=O)C(C2=CC=CC=C2)(C3=CC=CC=C3)OC1=O", "O=C(Cl)C(=O)Cl", "[Na+].[H-]", "[K+].[O-]C(=O)[O-]",
    "[Cs+].[O-]C(=O)[O-]", "CCN(CC)CC", "CCN(C(C)C)C(C)C", "CCN=C=NCCCN(C)C",
    "N1N=CC=C1", "O=C(N(C(=O)N(c1ccccc1)c2ccccc2)c3ccccc3)N(c4ccccc4)c5ccccc5", "O=C(NC(=O)N1CCCCC1)N1CCCCC1",
    "CCOP(=O)(OCC)OC(C)(C)C",
]


def _canonicalize_smiles(smiles: str):
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    return Chem.MolToSmiles(mol)


CANONICAL_BUILDING_BLOCKS = frozenset(
    canonical for canonical in (_canonicalize_smiles(s) for s in COMMON_BUILDING_BLOCKS) if canonical
)


def is_building_block_smiles(smiles: str) -> bool:
    """Return True if the SMILES canonicalizes into the building-block catalog."""
    canonical = _canonicalize_smiles(smiles)
    if canonical is None:
        return False
    return canonical in CANONICAL_BUILDING_BLOCKS
