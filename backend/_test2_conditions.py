"""Test 2 — Condition predictor safety filter and temperature prior"""
import sys, os
sys.path.insert(0, os.path.abspath('backend'))

from services.condition_predictor import ConditionPredictor

cp = ConditionPredictor()

print("=" * 55)
print("Test 2 — check_compatibility")
print("=" * 55)

# Should warn — strong base + protic solvent
w1 = cp.check_compatibility('n-BuLi', 'ethanol')
print(f"n-BuLi + ethanol  warnings ({len(w1)}):")
for w in w1:
    print(f"  [WARN] {w}")

# Should warn — Lewis acid + protic
w2 = cp.check_compatibility('AlCl3', 'water')
print(f"\nAlCl3 + water  warnings ({len(w2)}):")
for w in w2:
    print(f"  [WARN] {w}")

# Should be CLEAN — Pd + THF is fine
w3 = cp.check_compatibility('Pd(PPh3)4', 'THF')
print(f"\nPd(PPh3)4 + THF  warnings (expect 0): {w3}")

# Should be CLEAN — NaBH4 + ethanol is normal
w4 = cp.check_compatibility('NaBH4', 'ethanol')
print(f"NaBH4 + ethanol  warnings (expect 0): {w4}")

print()
print("=" * 55)
print("Test 2 — predict_temperature")
print("=" * 55)

cases = [
    {'reaction_type': 'grignard', 'reactants': ['c1ccccc1[Mg]Br']},
    {'reaction_type': 'suzuki', 'reactants': ['Brc1ccccc1']},
    {'reaction_type': 'reduction', 'reactants': ['O=Cc1ccccc1']},
    {'reaction_type': 'esterification', 'reactants': ['CC(=O)O', 'CCO']},
    {'reaction_type': 'diels_alder', 'reactants': ['C=CC=C', 'C=C']},
]

for rxn in cases:
    t = cp.predict_temperature(rxn)
    rt = rxn['reaction_type']
    temp = t['temperature_celsius']
    lo = t['low']
    hi = t['high']
    src = t['source']
    desc = t['description']
    in_range = lo <= temp <= hi
    tag = "OK " if in_range else "OUT-OF-RANGE"
    print(f"  {rt:<22} {temp:>6.1f} C  [{lo:>4},{hi:>4}]  [{tag}]  ({src}) — {desc}")

# Specific assertion: Grignard must be in (-78, 0)
g = cp.predict_temperature({'reaction_type': 'grignard', 'reactants': ['c1ccccc1[Mg]Br']})
assert g['low'] <= g['temperature_celsius'] <= g['high'], \
    f"Grignard temp {g['temperature_celsius']} outside [{g['low']}, {g['high']}]"
print("\nGrignard range assertion: PASS")
