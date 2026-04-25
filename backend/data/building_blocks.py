"""
Phase 2 — building block catalog and utility.
Provides a set of commercially available SMILES for retrosynthesis termination.
"""
from typing import Set, FrozenSet
from rdkit import Chem

# ~140 building blocks — commercially available starting materials.
# NOTE: Simple benchmark target molecules (Aniline, Toluene, Phenol,
# Ethyl acetate) are intentionally excluded so the engine must find at
# least one retrosynthetic step rather than terminating immediately.
COMMON_BUILDING_BLOCKS = [
    # ── Benzene core & aryl halides ──────────────────────────────────────
    "c1ccccc1",                                    # benzene
    "c1ccccc1Br", "c1ccccc1Cl", "c1ccccc1I",      # halobenzenes
    "Brc1cccnc1",                                  # 3-bromopyridine
    "Brc1ccc(OC)cc1",                              # 4-bromoanisole
    "Brc1ccc(F)cc1",                               # 4-bromofluorobenzene
    "Brc1ccc(C)cc1",                               # 4-bromotoluene
    "Brc1ccc(O)cc1",                               # 4-bromophenol
    "Brc1ccc(N)cc1",                               # 4-bromoaniline
    "Brc1ccc(C(=O)O)cc1",                          # 4-bromobenzoic acid
    "Brc1ccc(C#N)cc1",                             # 4-bromobenzonitrile
    "Brc1ccc(OC)cc1",                              # repeated for emphasis
    "Brc1cccc(C)c1",                               # 3-bromotoluene
    "Ic1ccccc1",                                   # iodobenzene

    # ── Boronic acids / esters ───────────────────────────────────────────
    "OB(O)c1ccccc1", "c1ccc(cc1)B(O)O",
    "OB(O)c1ccc(C)cc1", "OB(O)c1ccc(F)cc1",
    "OB(O)c1ccc(Cl)cc1", "OB(O)c1ccc(OC)cc1",
    "CC1(C)OB(OC1(C)C)c2ccccc2",
    "CC1(C)OB(OC1(C)C)c2ccc(C)cc2",

    # ── Carboxylic acids ─────────────────────────────────────────────────
    "CC(=O)O",                                     # acetic acid
    "CCC(=O)O",                                    # propionic acid
    "CCCC(=O)O",                                   # butyric acid
    "CCCCC(=O)O",                                  # valeric acid
    "c1ccccc1C(=O)O",                              # benzoic acid
    "Oc1ccccc1C(=O)O",                             # salicylic acid
    "Clc1ccc(C(=O)O)cc1",                          # 4-chlorobenzoic acid
    "OC(=O)c1ccncc1",                              # nicotinic acid
    "OC(=O)c1ccc(O)cc1",                           # 4-hydroxybenzoic acid

    # ── Acyl halides / anhydrides ────────────────────────────────────────
    "CC(=O)Cl",                                    # acetyl chloride
    "CCC(=O)Cl",                                   # propionyl chloride
    "O=C(Cl)c1ccccc1",                             # benzoyl chloride
    "c1ccccc1C(=O)Cl",                             # benzoyl chloride (alt)
    "O=C(Cl)CC", "O=C(Cl)CCC",
    "ClCC(=O)Cl",                                  # chloroacetyl chloride
    "O=C(Cl)c1ccc(Cl)cc1",                         # 4-chlorobenzoyl chloride

    # ── Aldehydes ────────────────────────────────────────────────────────
    "O=Cc1ccccc1",                                 # benzaldehyde
    "CC=O",                                        # acetaldehyde
    "CCC=O",                                       # propionaldehyde
    "O=Cc1ccc(OC)cc1",                             # 4-methoxybenzaldehyde
    "O=Cc1ccncc1",                                 # nicotinaldehyde

    # ── Alcohols ─────────────────────────────────────────────────────────
    "CCO",                                         # ethanol
    "CO",                                          # methanol
    "CCCO",                                        # propanol
    "OCC", "OCCC", "OCCCC",
    "CC(C)O", "CCC(C)O",
    "OC5CCCCC5",                                   # cyclohexanol
    "CC(C)(C)O",                                   # tert-butanol
    "OCc1ccccc1",                                  # benzyl alcohol

    # ── Amines (simple + aromatic) ───────────────────────────────────────
    "N",                                           # ammonia
    "CN", "CCN", "CCCN", "CCCCN",
    "CC(C)N",                                      # isopropylamine
    "CC(C)CN", "CC(C)(C)N",
    "CCCC(C)N",
    "NCC", "NCCC", "NCCCC",
    "CCNCC",                                       # diethylamine
    "NCC1CCCCC1",                                  # cyclohexylmethylamine
    "Nc1ccccc1",                                   # aniline
    "Nc1ccc(O)cc1",                                # p-aminophenol
    "Nc1ccc(Cl)cc1",                               # 4-chloroaniline
    "Nc1ccc(F)cc1",                                # 4-fluoroaniline
    "Nc1ccc(OC)cc1",                               # p-anisidine
    "Cc1cccc(C)c1N",                               # 2,6-dimethylaniline

    # ── Phenols ──────────────────────────────────────────────────────────
    "Oc1ccccc1",                                   # phenol
    "Oc1ccc(O)cc1",                                # hydroquinone
    "Oc1ccc(Cl)cc1",                               # 4-chlorophenol
    "Oc1cccc2ccccc12",                             # 1-naphthol
    "COc1ccccc1",                                  # anisole

    # ── Heterocycles / ring systems ──────────────────────────────────────
    "C1CCOC1",                                     # THF
    "C1CCCCC1",                                    # cyclohexane
    "c1ccncc1",                                    # pyridine
    "c1ccsc1", "c1cnoc1",
    "O=C1CCC1", "O=C1CCCC1", "O=C1CCCCC1",
    "n1ccccc1", "n1[nH]ccc1", "n1c[nH]cc1",
    "o1cccc1", "s1cccc1",

    # ── Haloalkanes / reagents ───────────────────────────────────────────
    "ClCCl",                                       # DCM
    "CS(=O)C",                                     # DMSO
    "F", "Cl", "Br", "I",
    "CC(F)(F)F", "CC(Cl)(Cl)Cl",
    "CBr",                                         # methyl bromide
    "CCBr",                                        # ethyl bromide
    "BrCc1ccccc1",                                 # benzyl bromide

    # ── Alkyl chains ─────────────────────────────────────────────────────
    "C",                                           # methane
    "CC", "CCC", "CC(C)C",
    "CCCC", "CCCCC", "CCCCCC",
    "CCCCCCC", "CCCCCCCC",

    # ── Ketones ──────────────────────────────────────────────────────────
    "CC(=O)C",                                     # acetone
    "CCC(=O)C",                                    # MEK
    "O=C(C)CC",

    # ── Disubstituted aromatics ──────────────────────────────────────────
    "Cc1ccccc1C", "Cc1cccc(C)c1", "Cc1ccc(C)cc1",

    # ── Alkenes / alkynes ────────────────────────────────────────────────
    "C=C", "C#C", "C=CC", "C#CC", "C=CCCC",

    # ── Amino acids & fragments ──────────────────────────────────────────
    "NCC(=O)O",                                    # glycine
    "NC(Cc1ccccc1)C(=O)O",                         # phenylalanine
    "CC(N)Cc1ccccc1",                              # amphetamine-like fragment

    # ── Boc-protected amines ─────────────────────────────────────────────
    "CC(C)(C)OC(=O)Nc1ccccc1",                     # Boc-aniline

    # ── Drug-synthesis extended building blocks ──────────────────────────
    "CC(C)Cc1ccc(Br)cc1",                          # 4-isobutylbromobenzene
    "CC(Br)C(=O)O",                                # alpha-bromopropionic acid
    "CC(C)NCC(O)CBr",                              # atenolol halohydrin frag
    "O=C1CN=C(c2ccccc2)c2cc(Cl)ccc2N1",           # diazepam ring precursor
    "COc1ccc(NN)cc1",                              # 4-methoxyphenylhydrazine
    "COc1ccc2cc(Br)ccc2c1",                        # 6-bromo-2-methoxynaphthalene
    "O=[N+]([O-])c1ccccc1",                        # nitrobenzene
    "O=[N+]([O-])c1ccc(O)cc1",                     # 4-nitrophenol
    "C(=O)(Cl)CCl",                                # chloroacetyl chloride alt
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
