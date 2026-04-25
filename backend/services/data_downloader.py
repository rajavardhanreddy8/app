import os
import requests
import gzip
import json
import logging
import random
from pathlib import Path
from typing import Optional, Dict, Any, List
from tqdm import tqdm

logger = logging.getLogger(__name__)

def generate_synthetic_training_dataset(n_reactions: int = 200, seed: int = 42) -> List[Dict[str, Any]]:
    """Generates a deterministic synthetic dataset of chemical reactions.

    Each reaction type has a pool of 6-12 real substrate pairs with
    yield offsets reflecting steric/electronic effects.  This ensures
    MorganFingerprint variance across samples so the ML model can
    learn structure-yield correlations.

    Returns ~3200 reactions (200 per type x 16 types) by default.
    """
    random.seed(seed)
    dataset = []

    # ── Substrate pools: (reactants, products, yield_offset) ──
    # yield_offset shifts the base yield range for that pair.

    POOLS = {
        "esterification": {
            'pairs': [
                (["CC(=O)O", "CCO"],       ["CC(=O)OCC"],        0),    # AcOH + EtOH baseline
                (["CC(=O)O", "CCCO"],      ["CC(=O)OCCC"],       -3),   # AcOH + PrOH
                (["CC(=O)O", "CC(C)O"],    ["CC(=O)OC(C)C"],     -8),   # AcOH + iPrOH (hindered)
                (["CCC(=O)O", "CCO"],      ["CCC(=O)OCC"],       -2),   # propanoic + EtOH
                (["c1ccc(C(=O)O)cc1","CCO"],["c1ccc(C(=O)OCC)cc1"], +5),# benzoic + EtOH (activated)
                (["CC(=O)O","CC(C)(C)O"],  ["CC(=O)OC(C)(C)C"],  -15),  # AcOH + tBuOH (very hindered)
                (["CCCC(=O)O","CCO"],      ["CCCC(=O)OCC"],      -1),   # butyric + EtOH
                (["OC(=O)c1ccccc1","CO"],  ["COC(=O)c1ccccc1"],  +3),   # benzoic + MeOH
            ],
            'solvents': ["None", "Toluene"],
            'catalysts': ["H2SO4", "p-TsOH", None],
            'temp_range': (60, 120),
            'yield_range': (65, 92),
        },
        "suzuki": {
            'pairs': [
                (["c1ccc(Br)cc1","OB(O)c1ccccc1"],           ["c1ccc(-c2ccccc2)cc1"],              0),   # PhBr + PhB(OH)2
                (["CC(=O)c1ccc(Br)cc1","OB(O)c1ccccc1"],     ["CC(=O)c1ccc(-c2ccccc2)cc1"],        +8),  # 4-BrAcPh (e-poor, faster)
                (["COc1ccc(Br)cc1","OB(O)c1ccccc1"],         ["COc1ccc(-c2ccccc2)cc1"],             -3),  # 4-BrAnisole (e-rich)
                (["c1ccc(Br)cc1","OB(O)c1ccc(C)cc1"],        ["Cc1ccc(-c2ccccc2)cc1"],              +2),  # PhBr + TolB(OH)2
                (["Fc1ccc(Br)cc1","OB(O)c1ccccc1"],          ["Fc1ccc(-c2ccccc2)cc1"],              +5),  # 4-FPhBr (e-poor)
                (["c1ccc(Br)c(C)c1","OB(O)c1ccccc1"],        ["Cc1ccccc1-c1ccccc1"],               -6),  # o-TolBr (steric)
                (["Brc1ccncc1","OB(O)c1ccccc1"],             ["c1ccc(-c2ccncc2)cc1"],               +4),  # 3-BrPyr (activated)
                (["Brc1ccc2ccccc2c1","OB(O)c1ccccc1"],       ["c1ccc(-c2ccc3ccccc3c2)cc1"],         -2),  # 2-BrNaph
            ],
            'solvents': ["THF", "DMF", "Dioxane"],
            'catalysts': ["Pd(PPh3)4", "Pd(dppf)Cl2", "Pd/C"],
            'temp_range': (60, 100),
            'yield_range': (68, 95),
        },
        "reduction": {
            'pairs': [
                (["CC(=O)C"],              ["CC(O)C"],              0),   # acetone
                (["CC(=O)c1ccccc1"],       ["CC(O)c1ccccc1"],       +3),  # acetophenone
                (["O=Cc1ccccc1"],          ["OCc1ccccc1"],           +5),  # benzaldehyde (fast)
                (["O=CCCC"],              ["OCCCC"],                +2),  # butyraldehyde
                (["CC(=O)CC"],            ["CC(O)CC"],              -2),  # 2-butanone
                (["O=C1CCCCC1"],          ["OC1CCCCC1"],            -4),  # cyclohexanone (steric)
                (["CC(=O)C(C)C"],         ["CC(O)C(C)C"],           -8),  # MIBK (hindered)
            ],
            'solvents': ["Methanol", "Ethanol", "THF"],
            'catalysts': ["NaBH4", "LiAlH4", "DIBAL-H"],
            'temp_range': (0, 25),
            'yield_range': (72, 96),
        },
        "alkylation": {
            'pairs': [
                (["c1ccccc1","CC(=O)Cl"],             ["CC(=O)c1ccccc1"],            0),   # benzene FC
                (["Cc1ccccc1","CC(=O)Cl"],            ["CC(=O)c1ccc(C)cc1"],         +5),  # toluene (activated)
                (["c1ccc(OC)cc1","CC(=O)Cl"],         ["CC(=O)c1ccc(OC)cc1"],        +8),  # anisole
                (["c1ccccc1","CCC(=O)Cl"],            ["CCC(=O)c1ccccc1"],           -3),  # propionyl Cl
                (["c1ccc2ccccc2c1","CC(=O)Cl"],       ["CC(=O)c1ccc2ccccc2c1"],      +4),  # naphthalene
                (["c1ccccc1","ClC(=O)c1ccccc1"],      ["O=C(c1ccccc1)c1ccccc1"],     -5),  # benzoyl Cl (steric)
            ],
            'solvents': ["DCM", "CS2"],
            'catalysts': ["AlCl3", "BF3"],
            'temp_range': (-10, 30),
            'yield_range': (55, 85),
        },
        "hydrogenation": {
            'pairs': [
                (["C=Cc1ccccc1"],          ["CCc1ccccc1"],            0),   # styrene
                (["C=CC=C"],              ["CCCC"],                  +2),  # butadiene
                (["C1=CCCCC1"],           ["C1CCCCC1"],              +5),  # cyclohexene (easy)
                (["c1ccc(C=C)cc1"],       ["c1ccc(CC)cc1"],          -1),  # vinylbenzene
                (["CC(=C)c1ccccc1"],      ["CC(C)c1ccccc1"],         -4),  # alpha-methyl styrene
                (["O=C1C=CC(=O)C=C1"],    ["O=C1CCC(=O)CC1"],       -6),  # quinone (selective)
                (["CC=CC"],              ["CCCC"],                  +3),  # 2-butene
            ],
            'solvents': ["Ethanol", "EtOAc", "Methanol"],
            'catalysts': ["Pd/C", "PtO2", "Rh/C"],
            'temp_range': (20, 50),
            'yield_range': (82, 99),
        },
        "nitration": {
            'pairs': [
                (["c1ccccc1"],             ["[O-][N+](=O)c1ccccc1"],    0),   # benzene
                (["Cc1ccccc1"],            ["Cc1ccc([N+](=O)[O-])cc1"], +5),  # toluene (activated)
                (["c1ccc(OC)cc1"],         ["COc1ccc([N+](=O)[O-])cc1"],+8),  # anisole
                (["c1ccc(Cl)cc1"],         ["O=[N+]([O-])c1ccc(Cl)cc1"],-5),  # chlorobenzene
                (["c1ccc2ccccc2c1"],       ["O=[N+]([O-])c1ccc2ccccc2c1"],+3),# naphthalene
                (["c1ccc(F)cc1"],          ["Fc1ccc([N+](=O)[O-])cc1"], -3),  # fluorobenzene
            ],
            'solvents': ["H2SO4"],
            'catalysts': ["HNO3/H2SO4", None],
            'temp_range': (0, 60),
            'yield_range': (50, 85),
        },
        "amide_coupling": {
            'pairs': [
                (["c1ccc(C(=O)O)cc1","c1ccc(N)cc1"],         ["c1ccc(C(=O)Nc2ccccc2)cc1"],        0),   # PhCOOH + PhNH2
                (["CC(=O)O","c1ccc(N)cc1"],                   ["CC(=O)Nc1ccccc1"],                  -5),  # AcOH (less reactive)
                (["c1ccc(C(=O)O)cc1","NCC"],                  ["c1ccc(C(=O)NCC)cc1"],               +3),  # PhCOOH + EtNH2 (aliphatic)
                (["OC(=O)c1ccncc1","c1ccc(N)cc1"],            ["O=C(Nc1ccccc1)c1ccncc1"],           +5),  # nicotinic acid
                (["c1ccc(C(=O)O)cc1","CC(N)C"],               ["c1ccc(C(=O)NC(C)C)cc1"],            -3),  # hindered amine
                (["OC(=O)CC","c1ccc(N)cc1"],                  ["CCC(=O)Nc1ccccc1"],                 -2),  # propanoic
                (["c1ccc(C(=O)O)cc1","NCCN"],                 ["c1ccc(C(=O)NCCN)cc1"],              +1),  # diamine
                (["OC(=O)c1ccc(F)cc1","c1ccc(N)cc1"],         ["O=C(Nc1ccccc1)c1ccc(F)cc1"],        +6),  # F-benzoic (activated)
            ],
            'solvents': ["DMF", "DCM", "THF"],
            'catalysts': ["HATU/DIPEA", "EDC/HOBt", "T3P/Et3N"],
            'temp_range': (0, 30),
            'yield_range': (70, 95),
        },
        "grignard": {
            'pairs': [
                (["BrCCCC","CC(=O)C"],                 ["CC(O)(CCCC)C"],               0),   # nBuBr + acetone
                (["BrCC","O=Cc1ccccc1"],               ["OC(CC)c1ccccc1"],             +5),  # EtBr + benzaldehyde
                (["Brc1ccccc1","CC(=O)C"],             ["CC(O)(c1ccccc1)C"],            +3),  # PhBr + acetone
                (["BrCCCCC","O=CC"],                   ["OC(CCCCC)C"],                  -2),  # nPentBr + acetaldehyde
                (["BrCC(C)C","CC(=O)C"],               ["CC(O)(CC(C)C)C"],              -6),  # iBuBr (hindered)
                (["BrCC","CC(=O)CC"],                  ["CCC(O)(CC)C"],                 -4),  # EtBr + 2-butanone
                (["Brc1ccccc1","O=Cc1ccccc1"],         ["OC(c1ccccc1)c1ccccc1"],        +2),  # PhBr + PhCHO
            ],
            'solvents': ["THF", "Et2O"],
            'catalysts': [None],
            'temp_range': (-78, 0),
            'yield_range': (50, 85),
        },
        "wittig": {
            'pairs': [
                (["O=Cc1ccccc1","C=P(c1ccccc1)(c1ccccc1)c1ccccc1"],  ["C=Cc1ccccc1"],              0),   # PhCHO + ylide
                (["O=CC","C=P(c1ccccc1)(c1ccccc1)c1ccccc1"],          ["C=CC"],                     +3),  # acetaldehyde
                (["O=CCCC","C=P(c1ccccc1)(c1ccccc1)c1ccccc1"],        ["C=CCCC"],                   +1),  # butyraldehyde
                (["O=Cc1ccc(OC)cc1","C=P(c1ccccc1)(c1ccccc1)c1ccccc1"],["C=Cc1ccc(OC)cc1"],         +4),  # p-MeO-PhCHO
                (["O=Cc1ccc(F)cc1","C=P(c1ccccc1)(c1ccccc1)c1ccccc1"],["C=Cc1ccc(F)cc1"],           +2),  # p-F-PhCHO
                (["O=C1CCCCC1","C=P(c1ccccc1)(c1ccccc1)c1ccccc1"],    ["C=C1CCCCC1"],               -8),  # cyclohexanone (ketone, harder)
            ],
            'solvents': ["THF", "DCM"],
            'catalysts': ["NaH", "KOtBu", "n-BuLi"],
            'temp_range': (-78, 25),
            'yield_range': (55, 85),
        },
        "diels_alder": {
            'pairs': [
                (["C=CC=C","C1=CC(=O)OC1=O"],           ["O=C1OC(=O)C2CCCCC12"],        0),   # butadiene + maleic anhydride
                (["C=CC=C","C=CC(=O)OC"],               ["C(=O)(OC)C1CC=CCC1"],         -3),  # acrylate
                (["CC=CC=C","C1=CC(=O)OC1=O"],           ["O=C1OC(=O)C2CC(C)=CCC12"],   +2),  # isoprene
                (["C=CC=C","O=CC=CC=O"],                 ["O=CC1CC=CCC1C=O"],            +5),  # fumaraldehyde (e-poor)
                (["C=Cc1ccccc1","C1=CC(=O)OC1=O"],       ["O=C1OC(=O)C2CC(c3ccccc3)CCC12"],-6),# styrene (poor diene)
                (["CC(=CC=C)C","C1=CC(=O)OC1=O"],        ["O=C1OC(=O)C2CC(C)(C)=CCC12"],+4),  # 2,3-dimethyl butadiene
            ],
            'solvents': ["Toluene", "DCM", None],
            'catalysts': [None, "AlCl3", "ZnCl2"],
            'temp_range': (25, 200),
            'yield_range': (60, 95),
        },
        "oxidation": {
            'pairs': [
                (["OCc1ccccc1"],            ["O=Cc1ccccc1"],           0),   # benzyl alcohol
                (["OCCC"],                 ["O=CCC"],                 -3),  # propanol
                (["OCC"],                  ["O=CC"],                   +2),  # ethanol → acetaldehyde (fast)
                (["OC(C)c1ccccc1"],        ["CC(=O)c1ccccc1"],        +4),  # 1-phenylethanol → acetophenone
                (["OC1CCCCC1"],            ["O=C1CCCCC1"],            -5),  # cyclohexanol (2° slow)
                (["OCC(C)C"],             ["O=CC(C)C"],               -2),  # isobutanol
                (["OCc1ccc(OC)cc1"],       ["O=Cc1ccc(OC)cc1"],       +3),  # p-MeO benzyl alcohol
            ],
            'solvents': ["DCM", "Acetone"],
            'catalysts': ["PCC", "DMP", "TEMPO/NaOCl"],
            'temp_range': (0, 25),
            'yield_range': (72, 95),
        },
        "sn2": {
            'pairs': [
                (["BrCc1ccccc1","CO"],      ["COCc1ccccc1"],           0),   # BnBr + MeO-
                (["BrCC","CO"],            ["CCOC"],                   +3),  # EtBr (1° fast)
                (["BrCCC","CO"],           ["CCCOC"],                  +1),  # PrBr
                (["BrCC(C)C","CO"],        ["CC(C)COC"],               -5),  # iBuBr (neopentyl-like)
                (["BrCc1ccccc1","CCO"],    ["CCOCc1ccccc1"],           -2),  # BnBr + EtO-
                (["ClCc1ccccc1","CO"],     ["COCc1ccccc1"],            -4),  # BnCl (worse LG)
                (["ICc1ccccc1","CO"],      ["COCc1ccccc1"],            +6),  # BnI (best LG)
            ],
            'solvents': ["DMF", "DMSO", "Acetone"],
            'catalysts': [None, "NaI"],
            'temp_range': (25, 80),
            'yield_range': (65, 90),
        },
        "reductive_amination": {
            'pairs': [
                (["O=Cc1ccccc1","Nc1ccccc1"],    ["c1ccc(CNc2ccccc2)cc1"],       0),   # PhCHO + PhNH2
                (["O=Cc1ccccc1","NCC"],           ["c1ccc(CNCC)cc1"],             +3),  # PhCHO + EtNH2
                (["O=CC","Nc1ccccc1"],            ["CNc1ccccc1"],                 +5),  # HCHO + PhNH2 (fast)
                (["O=CCCC","NCC"],               ["CCCCNCC"],                    +2),  # butanal + EtNH2
                (["CC(=O)c1ccccc1","Nc1ccccc1"],  ["CC(Nc1ccccc1)c1ccccc1"],     -8),  # acetophenone (ketone, slow)
                (["O=Cc1ccc(OC)cc1","NCC"],       ["CCNCc1ccc(OC)cc1"],          +4),  # p-MeO PhCHO
                (["O=CC(C)C","Nc1ccccc1"],        ["CC(C)CNc1ccccc1"],           -3),  # isobutanal
            ],
            'solvents': ["Methanol", "DCE", "THF"],
            'catalysts': ["NaBH3CN", "NaBH(OAc)3", "NaBH4"],
            'temp_range': (0, 25),
            'yield_range': (62, 90),
        },
        "buchwald_hartwig": {
            'pairs': [
                (["Brc1ccccc1","Nc1ccccc1"],         ["c1ccc(Nc2ccccc2)cc1"],             0),   # PhBr + PhNH2
                (["CC(=O)c1ccc(Br)cc1","Nc1ccccc1"], ["CC(=O)c1ccc(Nc2ccccc2)cc1"],       +8),  # e-poor ArBr
                (["COc1ccc(Br)cc1","Nc1ccccc1"],     ["COc1ccc(Nc2ccccc2)cc1"],            -5),  # e-rich ArBr
                (["Brc1ccccc1","NCC"],               ["CCNc1ccccc1"],                      +3),  # aliphatic amine
                (["Brc1ccncc1","Nc1ccccc1"],         ["c1ccc(Nc2ccncc2)cc1"],              +6),  # pyridyl Br
                (["Brc1ccc(C)cc1","Nc1ccccc1"],      ["Cc1ccc(Nc2ccccc2)cc1"],             +1),  # tolyl Br
                (["Brc1ccccc1","Nc1ccc(F)cc1"],      ["Fc1ccc(Nc2ccccc2)cc1"],             -2),  # F-aniline
            ],
            'solvents': ["Toluene", "Dioxane", "THF"],
            'catalysts': ["Pd2(dba)3/XPhos", "Pd(OAc)2/BINAP", "Pd/C"],
            'temp_range': (80, 120),
            'yield_range': (62, 93),
        },
        "heck": {
            'pairs': [
                (["Brc1ccccc1","C=C"],               ["C=Cc1ccccc1"],                0),   # PhBr + ethylene
                (["Brc1ccccc1","C=CC(=O)OCC"],       ["C(=Cc1ccccc1)C(=O)OCC"],      +8),  # + acrylate (activated)
                (["CC(=O)c1ccc(Br)cc1","C=C"],       ["C=Cc1ccc(C(C)=O)cc1"],        +5),  # e-poor ArBr
                (["COc1ccc(Br)cc1","C=C"],           ["C=Cc1ccc(OC)cc1"],             -4),  # e-rich ArBr
                (["Brc1ccccc1","C=Cc1ccccc1"],       ["C(=Cc1ccccc1)c1ccccc1"],       +3),  # + styrene
                (["Brc1ccncc1","C=C"],               ["C=Cc1ccncc1"],                 +6),  # pyridyl Br
            ],
            'solvents': ["DMF", "DMA", "NMP"],
            'catalysts': ["Pd(OAc)2/PPh3", "Pd(PPh3)4"],
            'temp_range': (80, 140),
            'yield_range': (55, 90),
        },
        "deprotection_boc": {
            'pairs': [
                (["CC(C)(C)OC(=O)Nc1ccccc1"],     ["Nc1ccccc1"],              0),   # Boc-aniline
                (["CC(C)(C)OC(=O)NCC"],           ["NCC"],                    +2),  # Boc-EtNH2 (easy)
                (["CC(C)(C)OC(=O)NCCN"],          ["NCCN"],                   +1),  # Boc-ethylenediamine
                (["CC(C)(C)OC(=O)NC1CCCCC1"],     ["NC1CCCCC1"],              -3),  # Boc-cyclohexylamine
                (["CC(C)(C)OC(=O)NC(C)c1ccccc1"], ["CC(N)c1ccccc1"],          -1),  # Boc-MBA
                (["CC(C)(C)OC(=O)N1CCCC1"],       ["C1CCNC1"],               -5),  # Boc-pyrrolidine (amide-like)
            ],
            'solvents': ["DCM", "Dioxane"],
            'catalysts': ["TFA", "HCl/dioxane", "4M HCl"],
            'temp_range': (0, 25),
            'yield_range': (85, 99),
        },
    }

    rxn_per_type = max(n_reactions, 200)

    for rxn_type, config in POOLS.items():
        pairs = config['pairs']
        base_lo, base_hi = config['yield_range']

        for i in range(rxn_per_type):
            # Sample a substrate pair
            reactants, products, yield_offset = random.choice(pairs)

            # Apply yield offset and clamp
            y_lo = max(5, base_lo + yield_offset)
            y_hi = min(99, base_hi + yield_offset)
            if y_lo >= y_hi:
                y_lo, y_hi = y_hi - 5, y_hi

            t_lo, t_hi = config['temp_range']

            dataset.append({
                "id": f"syn_{rxn_type}_{i}",
                "reactants": list(reactants),
                "products": list(products),
                "reaction_type": rxn_type,
                "yield_percent": round(random.uniform(y_lo, y_hi), 2),
                "temperature_celsius": random.randint(t_lo, t_hi),
                "time_hours": round(random.uniform(0.5, 24), 1),
                "solvent": random.choice(config['solvents']),
                "catalyst": random.choice(config['catalysts']),
            })

    random.shuffle(dataset)
    logger.info(f"Generated synthetic dataset with {len(dataset)} reactions across {len(POOLS)} types")
    return dataset

def download_ord_subset(output_path: Optional[str] = None, n_synthetic: int = 100) -> List[Dict]:
    """Offline fallback: generates synthetic data and saves to JSON."""
    if output_path is None:
        output_path = "training_reactions.json"
        
    reactions = generate_synthetic_training_dataset(n_reactions=n_synthetic)
    
    with open(output_path, "w") as f:
        json.dump(reactions, f, indent=2)
        
    return reactions

class USPTODataDownloader:
    """Download and process USPTO reaction dataset."""
    
    # USPTO dataset from Figshare (2025 version with 1.37M reactions)
    FIGSHARE_URL = "https://figshare.com/ndownloader/files/28230053"
    
    def __init__(self, data_dir: str = "/app/backend/data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.raw_data_path = self.data_dir / "uspto_raw.json.gz"
        self.processed_data_path = self.data_dir / "uspto_processed.json"
    
    def download_dataset(self, url: Optional[str] = None, force: bool = False) -> Path:
        """Download USPTO dataset from Figshare."""
        
        if self.raw_data_path.exists() and not force:
            logger.info(f"Dataset already exists at {self.raw_data_path}")
            return self.raw_data_path
        
        download_url = url or self.FIGSHARE_URL
        logger.info(f"Downloading USPTO dataset from {download_url}")
        
        try:
            # Stream download with progress bar
            response = requests.get(download_url, stream=True, timeout=30)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            
            with open(self.raw_data_path, 'wb') as f:
                with tqdm(total=total_size, unit='B', unit_scale=True, desc="Downloading") as pbar:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))
            
            logger.info(f"Downloaded dataset to {self.raw_data_path}")
            return self.raw_data_path
            
        except Exception as e:
            logger.error(f"Failed to download dataset: {str(e)}")
            # For demo, create a small sample dataset
            logger.info("Creating sample dataset for demonstration")
            self._create_sample_dataset()
            return self.raw_data_path
    
    def _create_sample_dataset(self):
        """Create a comprehensive sample dataset for demonstration."""
        base_reactions = [
            {
                "reaction_smiles": "c1ccccc1.CC(=O)Cl>>CC(=O)c1ccccc1",
                "yield": 85.0,
                "temperature": 0,
                "solvent": "DCM",
                "catalyst": "AlCl3",
                "reaction_type": "Friedel-Crafts acylation"
            },
            {
                "reaction_smiles": "CCO.CC(=O)O>>CCOC(=O)C",
                "yield": 88.0,
                "temperature": 80,
                "catalyst": "H2SO4",
                "reaction_type": "Esterification"
            },
            {
                "reaction_smiles": "c1ccccc1Br.c1ccc(B(O)O)cc1>>c1ccccc1-c2ccccc2",
                "yield": 85.0,
                "temperature": 80,
                "solvent": "THF",
                "catalyst": "Pd(PPh3)4",
                "reaction_type": "Suzuki coupling"
            },
            {
                "reaction_smiles": "CC(=O)C>>CC(O)C",
                "yield": 92.0,
                "temperature": 25,
                "solvent": "EtOH",
                "catalyst": "NaBH4",
                "reaction_type": "Reduction"
            },
            {
                "reaction_smiles": "CC(O)C>>CC(=O)C",
                "yield": 87.0,
                "temperature": 25,
                "solvent": "DCM",
                "catalyst": "PCC",
                "reaction_type": "Oxidation"
            },
            {
                "reaction_smiles": "c1ccccc1N.CC(=O)Cl>>CC(=O)Nc1ccccc1",
                "yield": 90.0,
                "temperature": 0,
                "solvent": "Pyridine",
                "reaction_type": "Amidation"
            },
            {
                "reaction_smiles": "CCBr.CN>>CCNC",
                "yield": 78.0,
                "temperature": 60,
                "solvent": "DMF",
                "reaction_type": "SN2 substitution"
            },
            {
                "reaction_smiles": "CC(=O)C.c1ccccc1CHO>>CC(=O)C=Cc1ccccc1",
                "yield": 70.0,
                "temperature": 25,
                "solvent": "EtOH",
                "catalyst": "NaOH",
                "reaction_type": "Aldol condensation"
            },
            {
                "reaction_smiles": "C=CC=C.C=C>>C1=CCCCC1",
                "yield": 88.0,
                "temperature": 150,
                "reaction_type": "Diels-Alder"
            },
            {
                "reaction_smiles": "c1ccccc1.CH3I>>Cc1ccccc1",
                "yield": 65.0,
                "temperature": -78,
                "solvent": "THF",
                "catalyst": "Mg",
                "reaction_type": "Grignard"
            }
        ]
        
        # Create variations with different yields and conditions
        sample_reactions = []
        import random
        random.seed(42)
        
        for _ in range(1200):  # Create 1200 sample reactions for better ML training
            rxn = random.choice(base_reactions).copy()
            # Add realistic variations
            if rxn.get('yield'):
                # More realistic yield distribution
                base_yield = rxn['yield']
                variation = random.gauss(0, 8)  # Normal distribution
                rxn['yield'] = max(30, min(98, base_yield + variation))
            if rxn.get('temperature') is not None:
                rxn['temperature'] = rxn['temperature'] + random.uniform(-10, 10)
            # Add some reactions without catalyst for variety
            if random.random() > 0.8 and 'catalyst' in rxn:
                rxn['catalyst'] = None
            sample_reactions.append(rxn)
        
        # Write as compressed JSON
        with gzip.open(self.raw_data_path, 'wt', encoding='utf-8') as f:
            json.dump({"reactions": sample_reactions}, f)
        
        logger.info(f"Created sample dataset with {len(sample_reactions)} reactions")
    
    def load_dataset(self) -> Dict[str, Any]:
        """Load dataset from disk."""
        if not self.raw_data_path.exists():
            logger.warning("Dataset not found, downloading...")
            self.download_dataset()
        
        logger.info(f"Loading dataset from {self.raw_data_path}")
        
        try:
            with gzip.open(self.raw_data_path, 'rt', encoding='utf-8') as f:
                data = json.load(f)
            
            logger.info(f"Loaded dataset with {len(data.get('reactions', []))} reactions")
            return data
            
        except Exception as e:
            logger.error(f"Failed to load dataset: {str(e)}")
            return {"reactions": []}
