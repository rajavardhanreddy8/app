from rdkit import Chem
from rdkit.Chem import AllChem
import sys

# Append the backend path so we can import engine
sys.path.append('c:/Users/admin/Desktop/agentic lab/API/rxn1/app/backend')
from services.retrosynthesis_engine import RetrosynthesisEngine
from data.building_blocks import is_building_block_smiles

engine = RetrosynthesisEngine()

def debug_molecule(smiles, target_name):
    print(f"\n--- Debugging: {target_name} ---")
    print(f"Target: {smiles}")
    mol = Chem.MolFromSmiles(smiles)
    if not mol:
        print("Invalid SMILES!")
        return

    # Let's see which templates match
    matched = 0
    for rxn, name, prio in engine.compiled_templates:
        try:
            prods = rxn.RunReactants((mol,))
            if prods:
                print(f"Template '{name}' matched! ({len(prods)} products)")
                matched += 1
                for product_set in prods:
                    reactant_smiles = []
                    for p in product_set:
                        try:
                            Chem.SanitizeMol(p)
                            reactant_smiles.append(Chem.MolToSmiles(p))
                        except Exception as e:
                            print("  Sanitize error:", e)
                    print(f"   -> {'.'.join(reactant_smiles)}")
        except Exception as e:
            pass
    print(f"Total templates matched: {matched}")

debug_molecule("CC(=O)Oc1ccccc1C(=O)O", "Aspirin")
debug_molecule("CC(C)Cc1ccc(cc1)C(C)C(=O)O", "Ibuprofen")
debug_molecule("CCN(CC)CC(=O)Nc1c(C)cccc1C", "Lidocaine")
