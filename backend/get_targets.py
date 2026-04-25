import json

benchmark_smiles = [
    "CC(=O)Oc1ccccc1C(=O)O", "CC(=O)Nc1ccc(O)cc1", "CCOC(C)=O", "O=Cc1ccccc1", "Nc1ccccc1",
    "Cc1ccccc1", "Oc1ccccc1", "CC(=O)c1ccccc1", "COC(=O)c1ccccc1", "OCc1ccccc1",
    "CC(C)Cc1ccc(cc1)C(C)C(=O)O", "CCN(CC)CC(=O)Nc1c(C)cccc1C", "CC(C)NCC(O)COc1ccc(CC(N)=O)cc1",
    "Cn1cnc2c1c(=O)n(C)c(=O)n2C", "CN(C)C(=N)NC(=N)N", "CC(C)NCC(O)COc1cccc2ccccc12",
    "CN1C(=O)CN=C(c2ccccc2)c2cc(Cl)ccc21", "COc1ccc2cc(C(C)C(=O)O)ccc2c1",
    "CC(C(=O)O)c1ccc(cc1)C(=O)c1ccccc1", "CC1=C(CC(=O)O)c2cc(OC)ccc2N1C(=O)c1ccc(Cl)cc1",
    "CN1CCC23c4c5ccc(O)c4OC2C(O)C=CC3C1C5", "O=C1C(O)=C(O)C(CO)O1",
    "CC12CCC3C(CCC4=CC(=O)CCC34C)C1CCC2=O", "CC(O)C(NC)c1ccccc1", "CC(N)Cc1ccccc1",
    "CC1=C2C(C(=O)C3(C)C(CC3C)C2(C)C)C(OC(=O)c4ccccc4)C(O)C(OC(=O)C)C1=O",
    "CCC1(O)CC2CN(CCC23c4ccccc4NC3=O)C1", "COC1=CC=C(C=C1)C2=C(C3=C(C=C2)N=CC=C3)C4CC5CCN4CC5C=C",
    "Oc1ccc(C=Cc2cc(O)cc(O)c2)cc1", "COc1cc(CNC(=O)CCCCCCC(C)C)ccc1O"
]
print("TARGET SMILES:\n", benchmark_smiles)
