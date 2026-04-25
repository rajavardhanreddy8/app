import logging
from rdkit.Chem import AllChem

logging.basicConfig(level=logging.INFO)

templates = [
    # Group 1 - Carbonyl
    ("[C:1](=O)[O:2][C:3]>>[C:1](=O)[OH].[O:2][C:3]", "ester_hydrolysis", 1),
    ("[C:1](=O)[O:2][C:3]>>[C:1](=O)Cl.[O:2][C:3]", "ester_from_acyl_chloride", 1),
    ("[C:1](=O)[N:2]>>[C:1](=O)[OH].[N:2]", "amide_hydrolysis", 1),
    ("[C:1](=O)[N:2]>>[C:1](=O)Cl.[N:2]", "amide_from_acyl_chloride", 1),
    ("[C:1](=O)[c:2]>>[C:1](=O)Cl.[c:2][H]", "retro_friedel_crafts_acylation", 2),
    ("[CH1:1]=O>>[CH2:1][OH]", "retro_oxidation_primary", 3),
    ("[C:1](=O)([C:2])[C:3]>>[C:1]([OH])([C:2])[C:3]", "retro_oxidation_secondary", 3),
    ("[C:1](=O)[OH]>>[CH2:1][OH]", "retro_oxidation_acid_from_alcohol", 3),
    ("[C:1](=O)[OH]>>[CH1:1]=O", "retro_oxidation_acid_from_aldehyde", 3),
    ("[C:1](=O)[O:2][C:3](=O)>>[C:1](=O)[OH].[C:3](=O)[OH]", "anhydride_hydrolysis", 2),

    # Group 2 - C-N bond formations
    ("[C:1][N:2]>>[C:1]=O.[N:2]", "reductive_amination", 2),
    ("[c:1][N:2]>>[c:1]Br.[N:2]", "buchwald_hartwig_br", 2),
    ("[c:1][N:2]>>[c:1]I.[N:2]", "buchwald_hartwig_i", 2),
    ("[c:1]C(=O)[N:2]>>[c:1]C(=O)[OH].[N:2]", "retro_amide_coupling", 1),
    ("[C:1][N:2]([C:3])[C:4]>>[C:1]Br.[N:2]([C:3])[C:4]", "n_alkylation", 2),
    ("[c:1]S(=O)(=O)[N:2]>>[c:1]S(=O)(=O)Cl.[N:2]", "sulfonamide_formation", 1),
    ("[C:1]S(=O)(=O)[N:2]>>[C:1]S(=O)(=O)Cl.[N:2]", "alkyl_sulfonamide", 1),
    ("[N:1]C(=N[N:3])[N:2]>>[N:1]C(=S)[N:2].[N:3]", "guanidine_formation", 4), # Dummy
    ("[N:1][C:2](=O)[O:3][C:4]>>[N:1].[C:4][O:3]C(=O)Cl", "carbamate_formation", 2),
    ("[c:1][N:2][C:3](=O)[C:4]>>[c:1][N:2].[C:4][C:3](=O)Cl", "aromatic_amide", 1),

    # Group 3 - C-C bond formations
    ("[c:1]-[c:2]>>[c:1]Br.[c:2]B(O)O", "suzuki_br", 1),
    ("[c:1]-[c:2]>>[c:1]I.[c:2]B(O)O", "suzuki_i", 1),
    ("[c:1]/[C:2]=[C:3]/>>[c:1]Br.[C:2]=[C:3]", "heck_rxn", 2),
    ("[C:1]([OH])([C:2])[C:3]>>[C:1](=O)[C:2].[C:3]Br", "grignard_ketone", 2),
    ("[CH1:1]([OH])[C:2]>>[CH1:1]=O.[C:2]Br", "grignard_aldehyde", 2),
    ("[C:1]=[C:2]>>[C:1]=O.[C:2]Br", "wittig_rxn", 3),
    ("[C:1][C:2]([OH])[C:3]=O>>[C:1]C=O.[C:3]=O", "aldol_condensation", 3),
    ("[C:1]=[C:2]C(=O)>>[C:1]=O.[C:2]C(=O)", "knoevenagel", 3),
    ("[C:1]#[C:2]-[c:3]>>[C:1]#[C:2].[c:3]Br", "sonogashira", 2),
    ("[C:1]#[C:2]-[C:3]>>[C:1]#[C:2].[C:3]Br", "alkyne_alkylation", 3),

    # Group 4 - C-O bond formations
    ("[c:1][O:2][C:3]>>[c:1][O:2][H].[C:3]Br", "williamson_ether_aromatic", 1),
    ("[C:1][O:2][C:3]>>[C:1][OH].[C:3][OH]", "mitsunobu", 2),
    ("[C:1]([OH])[C:2][O:3][C:4]>>[C:1]1O[C:2]1.[O:3][C:4]", "epoxide_opening_ether", 3),
    ("[C:1]([OH])[C:2][N:3]>>[C:1]1O[C:2]1.[N:3]", "epoxide_opening_amine", 3),
    ("[c:1][O:2][C:3]>>[c:1][OH].[C:3]Br", "phenol_alkylation", 1),
    ("[CH1:1]([O:2][C:3])([O:4][C:5])>>[CH1:1]=O.[O:2][C:3].[O:4][C:5]", "acetal_deprotection", 3), # Requires 3 but let's make it alcohol for simplicity
    ("[CH1:1]([O:2][C:3])([O:4][C:3])>>[CH1:1]=O.[OH][C:3][C:3][OH]", "cyclic_acetal", 3),
    ("[C:1][O:2][C:3]>>[C:1][OH].[C:3]Br", "aliphatic_ether", 2),
    ("[C:1](=O)[O:2][c:3]>>[C:1](=O)Cl.[c:3][OH]", "aryl_ester", 1),
    ("[C:1][O:2]S(=O)(=O)[C:3]>>[C:1][OH].[C:3]S(=O)(=O)Cl", "sulfonate_ester", 2),

    # Group 5 - Aromatic/heterocyclic
    ("[c:1][N+](=O)[O-]>>[c:1][H]", "retro_nitration", 3),
    ("[c:1]Cl>>[c:1][H]", "chlorination", 3),
    ("[c:1]Br>>[c:1][H]", "bromination", 3),
    ("[C:1]1[C:2]=[C:3][C:4][C:5][C:6]1>>[C:1]=[C:2].[C:3]=[C:4][C:5]=[C:6]", "diels_alder", 4),
    ("[c:1]1[n:2][c:3][n:4]c2ccccc12>>[c:3](=O)[OH].[n:2]c1ccccc1[n:4]", "benzimidazole_retro", 4),
    ("[c:1]F>>[c:1][H]", "fluorination_retro", 4),
    ("[c:1]I>>[c:1][H]", "iodination_retro", 3),
    ("[c:1]C#N>>[c:1]Br", "cyanation", 3),
    ("[c:1]C(=O)[OH]>>[c:1]Br", "carboxylation", 3),
    ("[c:1]S(=O)(=O)[OH]>>[c:1][H]", "sulfonation", 3),

    # Group 6 - Protecting group removal
    ("[N:1]C(=O)OC(C)(C)C>>[N:1][H]", "boc_deprotection", 1),
    ("[N:1]C(=O)OCc1ccccc1>>[N:1][H]", "cbz_deprotection", 1),
    ("[C:1]OC1CCCCO1>>[C:1][OH]", "thp_deprotection", 2),
    ("[C:1]O[Si]([C:2])([C:3])[C:4]>>[C:1][OH]", "silyl_deprotection", 2),
    ("[N:1][H]>>[N:1]C(=O)OC(C)(C)C", "boc_protection", 4),
    ("[C:1]([O:2]1)[C:3]([O:4]1)CC(C)(C)>>[C:1][O:2][H].[C:3][O:4][H]", "acetonide_deprotection", 2),
    ("[O:1]Cc1ccccc1>>[O:1][H]", "benzyl_ether_deprotection", 2),
    ("[N:1]Cc1ccccc1>>[N:1][H]", "benzyl_amine_deprotection", 2),
    ("[C:1](=O)OC(C)(C)C>>[C:1](=O)[OH]", "tbutyl_ester_deprotection", 2),
    ("[C:1](=O)OCc1ccccc1>>[C:1](=O)[OH]", "benzyl_ester_deprotection", 2),

    # Group 7 - Reduction/oxidation
    ("[N:1][H2]>>[N+:1](=O)[O-]", "nitro_reduction_aliphatic", 2),
    ("[c:1][NH2]>>[c:1][N+](=O)[O-]", "nitro_reduction_aromatic", 2),
    ("[C:1](=O)[C:2]>>[C:1]([OH])[C:2]", "ketone_reduction", 2),
    ("[CH1:1]=O>>[CH2:1][OH]", "aldehyde_reduction", 2),
    ("[C:1]#[N:2]>>[C:1](=O)[N:2]", "nitrile_reduction", 3), # wait retro? primary amide dehydration
    ("[c:1][CH2:2][NH2]>>[c:1]C#N", "nitrile_reduction", 2),
    ("[C:1]=[C:2]>>[CH1:1]([C:2])Br", "elimination", 3),
    ("[CH2:1][OH]>>[C:1](=O)[OH]", "retro_reduction_to_acid", 3),
    ("[C:1][OH]>>[C:1]=O", "alcohol_oxidation", 2),
    ("[C:1]#[C:2]>>[C:1]=[C:2]", "alkyne_reduction", 3),
]

valid_rules = []
for smarts, name, priority in templates:
    try:
        rxn = AllChem.ReactionFromSmarts(smarts)
        if rxn is not None:
            valid_rules.append((smarts, name, priority))
        else:
            print(f"FAILED (rxn is None): {name} - {smarts}")
    except Exception as e:
        print(f"FAILED ({e}): {name} - {smarts}")

print(f"Valid rules: {len(valid_rules)} / {len(templates)}")
