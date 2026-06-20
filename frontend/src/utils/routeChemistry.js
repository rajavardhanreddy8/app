export const DEFAULT_BATCH_MOL = 0.1;

const asArray = (value) => {
  if (!value) return [];
  return Array.isArray(value) ? value : [value];
};

export const getSmiles = (value) => {
  if (!value) return "";
  if (typeof value === "string") return value;
  return value.smiles || value.canonical_smiles || value.name || JSON.stringify(value);
};

export const getRouteProduct = (route) => {
  const steps = route?.steps || [];
  const lastStep = steps[steps.length - 1];
  return getSmiles(lastStep?.product) || getSmiles(route?.target_molecule) || route?.target_smiles || "Unknown product";
};

export const getRouteYield = (route) => {
  const direct = route?.overall_yield_percent ?? route?.estimated_yield;
  if (typeof direct === "number") return direct;
  const steps = route?.steps || [];
  if (!steps.length) return null;
  const product = steps.reduce((acc, step) => {
    const y = step.estimated_yield_percent ?? step.estimated_yield ?? 75;
    return acc * Math.max(0, Math.min(100, Number(y))) / 100;
  }, 1);
  return product * 100;
};

export const getRouteCost = (route) => {
  const direct = route?.total_cost_usd;
  if (typeof direct === "number") return direct;
  return (route?.steps || []).reduce((sum, step) => sum + Number(step.estimated_cost_usd || 0), 0);
};

export const formatMoney = (value) => {
  const n = Number(value || 0);
  return n.toLocaleString(undefined, { maximumFractionDigits: n >= 1000 ? 0 : 2 });
};

export const getIndustryFlags = (route) => {
  const yieldPercent = getRouteYield(route);
  const cost = getRouteCost(route);
  const steps = route?.steps?.length || route?.num_steps || 0;
  const flags = [];

  if (yieldPercent !== null && yieldPercent < 25) {
    flags.push({
      level: "critical",
      label: "Very low total yield",
      detail: "This is a route-screening warning. Industry routes usually need higher total yield or cheaper inputs.",
    });
  } else if (yieldPercent !== null && yieldPercent < 50) {
    flags.push({
      level: "warning",
      label: "Low total yield",
      detail: "Expect cost and waste pressure unless later optimization improves step yields.",
    });
  }

  if (cost > 10000) {
    flags.push({
      level: "critical",
      label: "Cost outlier",
      detail: "Estimated cost is far above normal lab-screening scale. Treat this as an AI estimate needing cost-model review.",
    });
  } else if (cost > 1000) {
    flags.push({
      level: "warning",
      label: "High route cost",
      detail: "Worth optimizing reagent stoichiometry, solvent volume, catalyst loading, and purification.",
    });
  }

  if (steps >= 6) {
    flags.push({
      level: "warning",
      label: "Long route",
      detail: "Multiplicative yield loss becomes severe across many steps.",
    });
  }

  return flags;
};

export const estimateStepInputs = (step, stepIndex = 0, batchMol = DEFAULT_BATCH_MOL) => {
  if (Array.isArray(step?.reactant_quantities) && step.reactant_quantities.length > 0) {
    return step.reactant_quantities.map((row) => ({
      step: stepIndex + 1,
      role: row.role || "material",
      name: row.material || row.name || row.smiles || "material",
      equivalents: row.equivalents ?? row.eq ?? null,
      amount: row.amount || [row.mass_g != null ? `${row.mass_g} g` : null, row.volume_ml != null ? `${row.volume_ml} mL` : null].filter(Boolean).join(", ") || row.basis || "-",
      note: row.notes || row.basis || "LLM-provided planning estimate",
    }));
  }

  const reactants = asArray(step?.reactants);
  const conditions = step?.conditions || {};
  const catalyst = conditions.catalyst;
  const solvent = conditions.solvent;
  const hasCatalyst = catalyst && !["none", "unknown", "n/a"].includes(String(catalyst).toLowerCase());

  const rows = reactants.map((reactant, index) => {
    const equivalents = index === 0 ? 1 : 1.1;
    const mmol = batchMol * 1000 * equivalents;
    return {
      role: index === 0 ? "limiting reactant" : "reactant",
      name: getSmiles(reactant),
      equivalents,
      amount: `${mmol.toFixed(1)} mmol`,
      note: "estimated from 0.10 mol planning basis",
    };
  });

  if (hasCatalyst) {
    rows.push({
      role: "catalyst",
      name: catalyst,
      equivalents: 0.05,
      amount: `${(batchMol * 1000 * 0.05).toFixed(1)} mmol`,
      note: "typical 5 mol% assumption",
    });
  }

  if (solvent) {
    rows.push({
      role: "solvent",
      name: solvent,
      equivalents: null,
      amount: `${(batchMol * 1000 * 8).toFixed(0)} mL`,
      note: "typical 8 mL/mmol placeholder; verify concentration",
    });
  }

  return rows.map((row) => ({ ...row, step: stepIndex + 1 }));
};

export const getRouteInputs = (route) => {
  return (route?.steps || []).flatMap((step, index) => estimateStepInputs(step, index));
};

export const getStepSummary = (step) => {
  const conditions = step?.conditions || {};
  return [
    conditions.temperature_celsius !== undefined ? `${conditions.temperature_celsius} C` : null,
    conditions.solvent ? `Solvent: ${conditions.solvent}` : null,
    conditions.catalyst ? `Catalyst: ${conditions.catalyst}` : null,
    conditions.time_hours ? `${conditions.time_hours} h` : null,
    conditions.pressure_atm ? `${conditions.pressure_atm} atm` : null,
    step?.catalyst_loading ? `Loading: ${step.catalyst_loading}` : null,
    step?.solvent_amount ? `Solvent amount: ${step.solvent_amount}` : null,
    step?.batch_scale ? step.batch_scale : null,
  ].filter(Boolean);
};

export const routesFromPlanner = (plannedRoutes) => {
  if (!plannedRoutes || plannedRoutes.length === 0) return [];
  return plannedRoutes.map((route) => ({
    ...route,
    num_steps: route.num_steps || route.steps?.length || 0,
  }));
};
