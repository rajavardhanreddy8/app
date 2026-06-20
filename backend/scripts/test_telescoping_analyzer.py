"""Smoke tests for TelescopingAnalyzer real-example rules."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.telescoping_analyzer import TelescopingAnalyzer


def check(label, step1, step2, expected):
    analyzer = TelescopingAnalyzer()
    result = analyzer.can_telescope(step1, step2)
    status = "CAN" if result["feasible"] else "CANNOT"
    print(f"{label}: {status} telescope ({result['confidence']})")
    if result["blocking_issues"]:
        for issue in result["blocking_issues"]:
            print(f"  - {issue}")
    assert result["feasible"] is expected


esterification = {
    "reaction_type": "esterification",
    "reactants": ["CC(=O)O", "CCO"],
    "product": "CC(=O)OCC",
    "conditions": {"solvent": "ethanol", "temperature_celsius": 70, "time_hours": 4},
    "notes": "no aqueous workup needed",
}
extraction = {
    "reaction_type": "extraction / crystallization",
    "reactants": ["CC(=O)OCC"],
    "product": "CC(=O)OCC",
    "conditions": {"solvent": "ethyl acetate", "temperature_celsius": 75, "time_hours": 1},
}

boc_deprotection = {
    "reaction_type": "Boc deprotection",
    "reactants": ["Boc-amine"],
    "product": "amine TFA salt",
    "conditions": {"solvent": "dcm", "catalyst": "TFA", "temperature_celsius": 25, "time_hours": 2},
}
amide_coupling = {
    "reaction_type": "amide coupling",
    "reactants": ["amine", "carboxylic acid", "HATU"],
    "product": "amide",
    "conditions": {"solvent": "dmf", "catalyst": "HATU/DIPEA", "temperature_celsius": 25, "time_hours": 4},
}

grignard_addition = {
    "reaction_type": "Grignard addition",
    "reactants": ["RMgBr", "ketone"],
    "product": "alkoxide",
    "conditions": {"solvent": "thf", "temperature_celsius": 0, "time_hours": 2},
}
quench_reduction = {
    "reaction_type": "quench then reduction",
    "reactants": ["alcohol", "NaBH4"],
    "product": "reduced alcohol",
    "conditions": {"solvent": "ethanol", "temperature_celsius": 25, "time_hours": 2},
    "notes": "aqueous workup required before NaBH4 reduction",
}

nitro_reduction = {
    "reaction_type": "nitro reduction",
    "reactants": ["nitroarene", "Fe/HCl"],
    "product": "aniline",
    "conditions": {"solvent": "ethanol", "temperature_celsius": 80, "time_hours": 3},
}
acetylation = {
    "reaction_type": "acetylation",
    "reactants": ["aniline", "acetic anhydride"],
    "product": "acetanilide",
    "conditions": {"solvent": "ethanol", "temperature_celsius": 85, "time_hours": 2},
}

suzuki = {
    "reaction_type": "Suzuki coupling",
    "reactants": ["aryl bromide", "boronic acid"],
    "product": "biaryl acid",
    "conditions": {"solvent": "thf", "catalyst": "Pd(PPh3)4", "temperature_celsius": 80, "time_hours": 4},
}
direct_amide = {
    "reaction_type": "direct amide coupling",
    "reactants": ["biaryl acid", "amine", "EDCI"],
    "product": "biaryl amide",
    "conditions": {"solvent": "dmf", "catalyst": "EDCI", "temperature_celsius": 85, "time_hours": 4},
}


check("Esterification to extraction", esterification, extraction, True)
check("Boc deprotection to amide coupling", boc_deprotection, amide_coupling, False)
check("Grignard addition to quench/reduction", grignard_addition, quench_reduction, False)
check("Nitro reduction to acetylation", nitro_reduction, acetylation, True)
check("Suzuki coupling to direct amide coupling", suzuki, direct_amide, True)

route = {
    "steps": [nitro_reduction, acetylation, suzuki, direct_amide],
}
analysis = TelescopingAnalyzer().analyze_route_telescoping(route)
print("Route telescopable pairs:", analysis["telescopable_pairs"])
print("Recommended sequence:", analysis["recommended_sequence"])
print("SMOKE TEST PASSED")
