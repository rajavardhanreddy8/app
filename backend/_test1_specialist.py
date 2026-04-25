"""Test 1 — Specialist routing"""
import sys, os
sys.path.insert(0, os.path.abspath('backend'))

from models import get_yield_predictor

p = get_yield_predictor()
print('Predictor type:', type(p).__name__)

reactions = [
    {
        'reactants': ['Brc1ccccc1', 'OB(O)c1ccccc1'],
        'products': ['c1ccc(-c2ccccc2)cc1'],
        'reaction_type': 'suzuki',
        'temperature_celsius': 90,
        'catalyst': 'Pd(PPh3)4',
        'solvent': 'THF',
    },
    {
        'reactants': ['CCO', 'CC(=O)O'],
        'products': ['CCOC(C)=O'],
        'reaction_type': 'esterification',
        'temperature_celsius': 80,
        'catalyst': 'H2SO4',
        'solvent': 'toluene',
    },
    {
        'reactants': ['CC(=O)C'],
        'products': ['CC(O)C'],
        'reaction_type': 'reduction',
        'temperature_celsius': 0,
        'catalyst': 'NaBH4',
        'solvent': 'ethanol',
    },
]

for rxn in reactions:
    r = p.predict_with_uncertainty(rxn)
    rtype = rxn['reaction_type']
    yld   = r['yield_percent']
    lo    = r['lower_bound']
    hi    = r['upper_bound']
    model = r.get('model', '?')
    conf  = r.get('confidence_level', '?')
    print(f"{rtype:<22} {yld:.1f}%  [{lo:.0f}-{hi:.0f}]  {conf:<6}  model={model}")
