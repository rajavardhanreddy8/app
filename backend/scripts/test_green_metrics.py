"""Smoke test for GreenChemistryMetrics."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.green_chemistry_metrics import GreenChemistryMetrics

g = GreenChemistryMetrics()

aspirin_route = {
    "steps": [
        {
            "reactants": [
                {"smiles": "OC(=O)c1ccccc1O"},
                {"smiles": "CC(=O)OC(C)=O"},
            ],
            "product": {"smiles": "CC(=O)Oc1ccccc1C(=O)O"},
            "conditions": {"time_hours": 0.33},
        }
    ]
}

ibuprofen_route = {
    "steps": [
        {"reactants": [{"smiles": "CC(C)c1ccccc1"}, {"smiles": "CC(=O)OC(C)=O"}],
         "product": {"smiles": "CC(=O)c1ccc(CC(C)C)cc1"}, "conditions": {"time_hours": 1}},
        {"reactants": [{"smiles": "CC(=O)c1ccc(CC(C)C)cc1"}, {"smiles": "[H][H]"}],
         "product": {"smiles": "CC(O)c1ccc(CC(C)C)cc1"}, "conditions": {"time_hours": 2}},
        {"reactants": [{"smiles": "CC(O)c1ccc(CC(C)C)cc1"}, {"smiles": "O=C=O"}],
         "product": {"smiles": "CC(C)Cc1ccc(cc1)C(C)C(=O)O"}, "conditions": {"time_hours": 3}},
    ]
}

r1 = g.calculate(aspirin_route, scale="lab")
r2 = g.calculate(ibuprofen_route, scale="lab")

print("=== Aspirin (1-step) ===")
print(f"  AE:         {r1.atom_economy_percent:.1f}%")
print(f"  E-factor:   {r1.e_factor:.2f}")
print(f"  PMI:        {r1.pmi:.2f}  ({r1.pmi_rating})")
print(f"  CO2:        {r1.estimated_co2_kg_per_kg_product:.2f} kg/kg")
print(f"  Route type: {r1.route_type}")

print()
print("=== Ibuprofen (3-step Hoechst) ===")
print(f"  AE:         {r2.atom_economy_percent:.1f}%")
print(f"  E-factor:   {r2.e_factor:.2f}")
print(f"  PMI:        {r2.pmi:.2f}  ({r2.pmi_rating})")
print(f"  CO2:        {r2.estimated_co2_kg_per_kg_product:.2f} kg/kg")
print(f"  Bottleneck: step {r2.bottleneck_step}")

print()
print("=== Sustainability Ranking ===")
ranked = g.rank_routes([aspirin_route, ibuprofen_route], scale="lab")
for e in ranked:
    gm = e["green_metrics"]
    rank = e["sustainability_rank"]
    score = e["sustainability_score"]
    pmi = gm["pmi"]
    ae = gm["atom_economy_percent"]
    print(f"  Rank {rank}: score={score}  PMI={pmi}  AE={ae}%")

print()
print("SMOKE TEST PASSED")
