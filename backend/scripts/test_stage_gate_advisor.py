"""Smoke test for StageGateAdvisor."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.stage_gate_advisor import StageGateAdvisor


routes = [
    {
        "id": "fast-discovery-route",
        "overall_yield": 42.0,
        "num_steps": 2,
        "green_metrics": {"pmi": 80, "convergence_score": 0.0},
        "cost_per_kg_product": 5000,
        "steps": [{"conditions": {"catalyst": "Pd(PPh3)4"}}],
    },
    {
        "id": "commercializable-route",
        "overall_yield": 78.0,
        "num_steps": 4,
        "green_metrics": {"pmi": 14, "convergence_score": 0.8},
        "cost_per_kg_product": 850,
        "steps": [{"conditions": {"catalyst": "Pd/C"}}],
    },
]


advisor = StageGateAdvisor()

phase_1 = advisor.advise_for_stage(routes, "phase_1", 0.5)
assert phase_1["recommended_route"]["id"] == "fast-discovery-route"
print("Phase I route:", phase_1["recommended_route"]["id"])

commercial = advisor.advise_for_stage(routes, "commercial", 250)
assert commercial["recommended_route"]["id"] == "commercializable-route"
print("Commercial route:", commercial["recommended_route"]["id"])
print("SMOKE TEST PASSED")
