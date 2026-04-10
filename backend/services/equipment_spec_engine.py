"""
Equipment-Centric Process Design Engine (Phase 9)

Turns process constraints into hard manufacturability checks, computes
first-pass equipment sizing/specifications, and estimates equipment-linked costs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class EquipmentDesignResult:
    """Result of equipment-driven process design for a route/step."""

    feasible: bool
    rejection_reasons: List[str]
    required_equipment: List[str]
    equipment_spec: Dict[str, Any]
    process_flow: List[str]
    equipment_cost_usd: float
    equipment_penalty: float


class EquipmentSpecEngine:
    """Computes equipment specs and enforces equipment feasibility as a hard constraint."""

    def __init__(self) -> None:
        self.default_available_equipment = {
            "jacketed_reactor",
            "high_shear_mixer",
            "filtration_unit",
            "distillation_unit",
            "drying_unit",
            "cstr",
            "autoclave",
            "cooling_skid",
        }

    def design_process(
        self,
        reaction: Dict[str, Any],
        available_equipment: List[str] | None,
        batch_mass_kg: float,
        constraint_penalty: float = 0.0,
    ) -> EquipmentDesignResult:
        """
        Build equipment spec + process flow and enforce hard industrial constraints.
        """
        available = set(available_equipment or self.default_available_equipment)

        temperature_c = float(reaction.get("temperature_c", 25.0))
        pressure_atm = float(reaction.get("pressure_atm", 1.0))
        pressure_bar = pressure_atm * 1.01325
        density_kg_per_l = max(float(reaction.get("density_kg_per_l", 1.0)), 0.1)

        cp_kj_kg_k = float(reaction.get("cp_kj_kg_k", 4.0))
        delta_t_k = abs(float(reaction.get("delta_t_k", temperature_c - 25.0)))
        agitation_rps = float(reaction.get("agitation_rps", 3.0))
        impeller_diameter_m = float(reaction.get("impeller_diameter_m", 0.4))
        rho_kg_m3 = float(reaction.get("rho_kg_m3", density_kg_per_l * 1000.0))
        power_number = float(reaction.get("power_number", 5.0))

        phase_type = str(reaction.get("phase_type", "single")).lower()
        gas_reaction = phase_type == "gas-liquid" or bool(reaction.get("gas_reaction", False))

        # Core sizing equations
        working_volume_l = batch_mass_kg / density_kg_per_l
        reactor_volume_l = working_volume_l * 1.30  # 30% headspace

        q_kj = batch_mass_kg * cp_kj_kg_k * delta_t_k
        heat_load_kw = q_kj / 3600.0  # approximate 1 h ramp/removal basis

        agitation_power_w = power_number * (agitation_rps ** 3) * (impeller_diameter_m ** 5) * rho_kg_m3
        agitation_power_kw = agitation_power_w / 1000.0

        # Map constraints -> equipment decisions
        required_equipment: List[str] = []
        reactor_type = "jacketed_reactor"

        if heat_load_kw > 8.0 or temperature_c > 120:
            required_equipment.append("jacketed_reactor")
            required_equipment.append("cooling_skid")

        if pressure_bar > 5.0 or gas_reaction:
            reactor_type = "autoclave"
            required_equipment.append("autoclave")

        if constraint_penalty > 35.0 or agitation_power_kw > 2.5:
            required_equipment.append("high_shear_mixer")

        if phase_type in {"gas-liquid", "liquid-liquid", "solid-liquid"}:
            required_equipment.append("cstr")

        required_equipment.extend(["filtration_unit", "distillation_unit", "drying_unit"])
        required_equipment = sorted(set(required_equipment))

        # Hard constraints
        rejection_reasons: List[str] = []
        if temperature_c > 250:
            rejection_reasons.append("Temperature exceeds equipment upper limit (250°C)")

        pressure_rating_bar = 10.0 if reactor_type == "autoclave" else 3.0
        if pressure_bar > pressure_rating_bar:
            rejection_reasons.append(
                f"Pressure {pressure_bar:.1f} bar exceeds reactor rating {pressure_rating_bar:.1f} bar"
            )

        cooling_capacity_kw = float(reaction.get("cooling_capacity_kw", 25.0))
        if heat_load_kw > cooling_capacity_kw:
            rejection_reasons.append(
                f"Cooling capacity insufficient ({heat_load_kw:.1f} kW required > {cooling_capacity_kw:.1f} kW available)"
            )

        # Equipment availability is a hard feasibility gate
        missing = [eq for eq in required_equipment if eq not in available]
        if missing:
            rejection_reasons.append(f"Missing required equipment: {', '.join(sorted(missing))}")

        feasible = len(rejection_reasons) == 0

        process_flow = [
            "Reactor",
            "Workup",
            "Filtration",
            "Distillation",
            "Drying Unit",
        ]

        reactor_cost = 12000.0 if reactor_type == "autoclave" else 7000.0
        energy_cost = (heat_load_kw * 0.12 + agitation_power_kw * 0.18) * max(batch_mass_kg, 1.0)
        maintenance_cost = reactor_cost * 0.03
        equipment_cost = reactor_cost + energy_cost + maintenance_cost

        equipment_spec = {
            "reactor": {
                "type": "Pressure Autoclave" if reactor_type == "autoclave" else "Jacketed Batch Reactor",
                "volume": f"{reactor_volume_l:.1f} L",
                "material": "SS316",
                "temperature_range": "-10 to 250°C",
                "pressure_rating": f"{pressure_rating_bar:.1f} bar",
            },
            "mixing": {
                "impeller": "Rushton turbine" if gas_reaction else "Pitched blade",
                "power": f"{agitation_power_kw:.2f} kW",
            },
            "heat_system": {
                "cooling": "jacketed water/glycol",
                "heat_load": f"{heat_load_kw:.2f} kW",
            },
        }

        equipment_penalty = min(100.0, len(missing) * 30.0 + (0.0 if feasible else 20.0))

        return EquipmentDesignResult(
            feasible=feasible,
            rejection_reasons=rejection_reasons,
            required_equipment=required_equipment,
            equipment_spec=equipment_spec,
            process_flow=process_flow,
            equipment_cost_usd=round(equipment_cost, 2),
            equipment_penalty=round(equipment_penalty, 2),
        )
