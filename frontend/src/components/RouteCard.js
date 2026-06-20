import React, { useState } from "react";
import axios from "axios";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Clock, DollarSign, TrendingUp, AlertCircle, ChevronDown, ChevronUp } from "lucide-react";
import MoleculeRenderer from "./MoleculeRenderer";
import { estimateStepInputs } from "@/utils/routeChemistry";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const number = (value, fallback = 0) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const getDifficultyColor = (difficulty) => {
  switch (difficulty) {
    case "easy":
      return "bg-green-500";
    case "moderate":
      return "bg-yellow-500";
    case "high":
    case "difficult":
      return "bg-red-500";
    default:
      return "bg-gray-500";
  }
};

const pmiBadge = (greenMetrics) => {
  const pmi = number(greenMetrics?.pmi, null);
  if (pmi === null) return null;
  if (pmi < 10) return { label: `🟢 PMI: ${pmi.toFixed(1)} — Excellent`, cls: "bg-green-500/20 border-green-400/50 text-green-200" };
  if (pmi <= 25) return { label: `🟡 PMI: ${pmi.toFixed(1)} — Acceptable`, cls: "bg-yellow-500/20 border-yellow-400/50 text-yellow-200" };
  if (pmi <= 50) return { label: `🟠 PMI: ${pmi.toFixed(1)} — Needs improvement`, cls: "bg-orange-500/20 border-orange-400/50 text-orange-200" };
  return { label: `🔴 PMI: ${pmi.toFixed(1)} — Unsustainable`, cls: "bg-red-500/20 border-red-400/50 text-red-200" };
};

const CatalystBadge = ({ level }) => {
  const badges = {
    1: ["🧬 Biocatalysis", "bg-purple-500/20 border-purple-400/50 text-purple-200"],
    2: ["♻ Heterogeneous", "bg-green-500/20 border-green-400/50 text-green-200"],
    3: ["⚙ Earth-abundant", "bg-blue-500/20 border-blue-400/50 text-blue-200"],
    4: ["⚠ Homogeneous Pd", "bg-amber-500/20 border-amber-400/50 text-amber-200"],
  };
  const [label, cls] = badges[level] || ["Standard reagent", "bg-slate-500/20 border-slate-400/50 text-slate-200"];
  return <Badge className={`border ${cls}`}>{label}</Badge>;
};

const qualityPmiBadge = (greenMetrics) => {
  const pmi = number(greenMetrics?.pmi, null);
  if (pmi === null) return null;
  if (pmi < 10) return { label: `PMI ${pmi.toFixed(1)} - Excellent`, cls: "bg-green-500/20 border-green-400/50 text-green-200" };
  if (pmi <= 25) return { label: `PMI ${pmi.toFixed(1)} - Acceptable`, cls: "bg-yellow-500/20 border-yellow-400/50 text-yellow-200" };
  if (pmi <= 50) return { label: `PMI ${pmi.toFixed(1)} - Needs improvement`, cls: "bg-orange-500/20 border-orange-400/50 text-orange-200" };
  return { label: `PMI ${pmi.toFixed(1)} - Unsustainable`, cls: "bg-red-500/20 border-red-400/50 text-red-200" };
};

const CleanCatalystBadge = ({ level }) => {
  const badges = {
    1: ["Biocatalysis", "bg-purple-500/20 border-purple-400/50 text-purple-200"],
    2: ["Heterogeneous", "bg-green-500/20 border-green-400/50 text-green-200"],
    3: ["Earth-abundant", "bg-blue-500/20 border-blue-400/50 text-blue-200"],
    4: ["Homogeneous Pd", "bg-amber-500/20 border-amber-400/50 text-amber-200"],
  };
  const [label, cls] = badges[level] || ["Standard reagent", "bg-slate-500/20 border-slate-400/50 text-slate-200"];
  return <Badge className={`border ${cls}`}>{label}</Badge>;
};

const SourceBadge = ({ source }) => {
  if (!source) return null;
  const sourceText = String(source);
  const palette = sourceText.includes("demo") || sourceText.includes("fallback")
    ? "bg-yellow-500/20 border-yellow-400/50 text-yellow-200"
    : sourceText.includes("ml") || sourceText.includes("ensemble")
      ? "bg-emerald-500/20 border-emerald-400/50 text-emerald-200"
      : "bg-blue-500/20 border-blue-400/50 text-blue-200";
  return <Badge className={`border ${palette}`}>{sourceText}</Badge>;
};

const confidenceClass = (confidence) => {
  switch ((confidence || "low").toLowerCase()) {
    case "high":
      return "bg-emerald-500/20 border-emerald-400/50 text-emerald-200";
    case "medium":
      return "bg-yellow-500/20 border-yellow-400/50 text-yellow-200";
    default:
      return "bg-red-500/20 border-red-400/50 text-red-200";
  }
};

const RouteEvidencePanel = ({ route }) => {
  const source = route.prediction_source || {};
  const evidence = route.evidence || {};
  const uncertainty = route.uncertainty?.overall_yield_percent;
  return (
    <div className="mb-4 rounded-md border border-slate-500/30 bg-slate-950/30 p-3 text-xs text-slate-100">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <SourceBadge source={source.route_generation || evidence.source_type} />
        <Badge className={`border ${confidenceClass(route.confidence)}`}>
          Confidence: {route.confidence || "low"}
        </Badge>
        <Badge className="border border-red-400/40 bg-red-500/15 text-red-200">
          Human review required
        </Badge>
        {route.review_status && (
          <Badge className="border border-slate-400/40 bg-slate-500/15 text-slate-200">
            {String(route.review_status).replaceAll("_", " ")}
          </Badge>
        )}
      </div>
      <div className="grid gap-2 md:grid-cols-3">
        <div>Model: {evidence.model_version || "not reported"}</div>
        <div>Data: {evidence.data_version || "local-artifacts"}</div>
        <div>
          Yield range: {uncertainty ? `${number(uncertainty.lower).toFixed(1)}-${number(uncertainty.upper).toFixed(1)}%` : "not calibrated"}
        </div>
      </div>
      {route.warnings?.length > 0 && (
        <div className="mt-2 text-yellow-100">
          {route.warnings.slice(0, 3).join(" ")}
        </div>
      )}
    </div>
  );
};

const StepEvidencePanel = ({ step }) => {
  const source = step.prediction_source || {};
  const uncertainty = step.uncertainty?.yield_percent;
  return (
    <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
      <SourceBadge source={source.yield} />
      <SourceBadge source={source.conditions} />
      <Badge className={`border ${confidenceClass(step.confidence)}`}>
        Confidence: {step.confidence || "low"}
      </Badge>
      {uncertainty && (
        <Badge className="border border-slate-400/40 bg-slate-500/15 text-slate-200">
          Yield range {number(uncertainty.lower).toFixed(1)}-{number(uncertainty.upper).toFixed(1)}%
        </Badge>
      )}
      {step.human_review_required && (
        <Badge className="border border-red-400/40 bg-red-500/15 text-red-200">
          Review
        </Badge>
      )}
    </div>
  );
};

const FeedbackPanel = ({ route }) => {
  const [actualYield, setActualYield] = useState("");
  const [feedbackStatus, setFeedbackStatus] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const submitFeedback = async () => {
    const parsedYield = Number(actualYield);
    if (!Number.isFinite(parsedYield) || parsedYield < 0 || parsedYield > 100) {
      setFeedbackStatus("Enter an actual yield between 0 and 100.");
      return;
    }
    setSubmitting(true);
    setFeedbackStatus(null);
    try {
      await axios.post(`${API}/feedback/ingest`, {
        predicted_route_id: route.id,
        actual_yield_percent: parsedYield,
        source: "lab",
        verified: true,
      });
      setActualYield("");
      setFeedbackStatus("Feedback recorded.");
    } catch (error) {
      setFeedbackStatus(error.response?.data?.detail || "Feedback could not be recorded.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mt-4 rounded-md border border-slate-500/30 bg-slate-950/30 p-3 text-xs text-slate-100">
      <div className="mb-2 font-medium text-slate-200">Record lab outcome</div>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <Input
          type="number"
          min="0"
          max="100"
          value={actualYield}
          onChange={(event) => setActualYield(event.target.value)}
          placeholder="Actual yield %"
          className="h-8 border-slate-500/40 bg-slate-900/70 text-white sm:max-w-[160px]"
        />
        <Button size="sm" onClick={submitFeedback} disabled={submitting}>
          {submitting ? "Recording..." : "Record"}
        </Button>
        {feedbackStatus && <span className="text-slate-300">{feedbackStatus}</span>}
      </div>
    </div>
  );
};

const ScoreBreakdown = ({ scoreBreakdown }) => {
  if (!scoreBreakdown) return null;
  return (
    <div className="absolute left-0 top-8 z-20 hidden min-w-[280px] rounded-md border border-purple-400/40 bg-slate-950 p-3 text-xs text-purple-100 shadow-xl group-hover:block">
      {Object.entries(scoreBreakdown).map(([name, data]) => {
        const raw = number(data.raw);
        const pct = Math.round(raw * 100);
        const bars = Math.max(0, Math.min(10, Math.round(raw * 10)));
        return (
          <div key={name} className="grid grid-cols-[88px_80px_48px_64px] gap-2 py-1">
            <span className="capitalize">{name.replace("_", " ")}</span>
            <span className="font-mono">{"█".repeat(bars)}{"░".repeat(10 - bars)}</span>
            <span>{pct}%</span>
            <span>{data.contribution_pct}% weight</span>
          </div>
        );
      })}
    </div>
  );
};

const ImpurityBanner = ({ impurityAnalysis }) => {
  if (!impurityAnalysis) return null;
  const risk = (impurityAnalysis.overall_impurity_risk || "medium").toLowerCase();
  const accumulated = impurityAnalysis.accumulated_impurities || [];
  const names = accumulated.slice(0, 4).map((item) => item.name).filter(Boolean).join(", ");
  if (risk === "high") {
    return (
      <Alert className="mb-4 bg-red-500/15 border-red-400/60">
        <AlertDescription className="text-red-100">
          🔴 GTI Alert — ICH M7 assessment required{accumulated.length ? `; ${accumulated.length} impurities propagate to final API` : ""}
        </AlertDescription>
      </Alert>
    );
  }
  if (risk === "medium") {
    return (
      <Alert className="mb-4 bg-yellow-500/15 border-yellow-400/60">
        <AlertDescription className="text-yellow-100">
          ⚠ Monitor{names ? `: ${names}` : ""}{accumulated.length ? `; ${accumulated.length} impurities propagate to final API` : ""}
        </AlertDescription>
      </Alert>
    );
  }
  return null;
};

const IndustrialStatusBadge = ({ status }) => {
  if (!status) return null;
  const badges = {
    accepted: ["Accepted", "bg-green-500/20 border-green-400/50 text-green-200"],
    ard_required: ["AR&D Required", "bg-yellow-500/20 border-yellow-400/50 text-yellow-200"],
    rejected: ["Rejected", "bg-red-500/20 border-red-400/50 text-red-200"],
    exploratory_only: ["Exploratory Only", "bg-gray-500/20 border-gray-400/50 text-gray-200"]
  };
  const [label, cls] = badges[status.toLowerCase()] || [status, "bg-slate-500/20 border-slate-400/50 text-slate-200"];
  return <Badge className={`ml-3 border ${cls}`}>{label}</Badge>;
};

const EffectiveCostPanel = ({ baseCost, yieldLossCost, effectiveCost }) => {
  if (effectiveCost == null || yieldLossCost == null) return null;
  return (
    <div className="flex items-center gap-3 text-xs mt-2 bg-slate-900/40 p-2 rounded-md border border-slate-700/50 w-fit">
      <div className="text-slate-300">Base: ${number(baseCost).toFixed(2)}</div>
      <div className="text-yellow-400/80">+ Yield Loss: ${number(yieldLossCost).toFixed(2)}</div>
      <div className="text-yellow-400 font-semibold">= Effective: ${number(effectiveCost).toFixed(2)}</div>
    </div>
  );
};

const RejectionReasons = ({ reasons, status, yieldPct, requiredYield }) => {
  if (!reasons || reasons.length === 0) return null;
  
  let header = "Issues Detected";
  if (status === "exploratory_only") {
    header = "Critical rejection: exploratory chemistry only. Not suitable for industrial production.";
  } else if (status === "rejected" || status === "ard_required") {
    if (yieldPct < requiredYield) {
      header = "Rejected for pharma production. Send to AR&D optimization.";
    } else {
      header = "Industrially unacceptable route detected.";
    }
  }

  return (
    <Alert className="mb-4 bg-red-500/10 border-red-500/30">
      <AlertCircle className="h-4 w-4 text-red-400" />
      <AlertDescription className="text-red-200 ml-2">
        <div className="font-semibold mb-1">{header}</div>
        <ul className="list-disc pl-5 text-sm">
          {reasons.map((r, i) => <li key={i}>{r}</li>)}
        </ul>
      </AlertDescription>
    </Alert>
  );
};

const ARDActionsPanel = ({ actions }) => {
  const [expanded, setExpanded] = useState(false);
  if (!actions || actions.length === 0) return null;

  return (
    <div className="mt-4 rounded-lg border border-yellow-500/30 bg-yellow-500/10">
      <button className="w-full px-4 py-3 text-left text-yellow-200 flex justify-between items-center" onClick={() => setExpanded(!expanded)}>
        <span>🛠 Recommended AR&D Actions ({actions.length})</span>
        <span className="text-xs opacity-70 flex items-center">
          {expanded ? <><ChevronUp className="w-3 h-3 mr-1" /> Collapse</> : <><ChevronDown className="w-3 h-3 mr-1" /> Expand</>}
        </span>
      </button>
      {expanded && (
        <div className="px-4 pb-4 text-sm text-yellow-100/90">
          <ul className="list-disc pl-5 space-y-1">
            {actions.map((action, idx) => (
              <li key={idx}>{action}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

const RouteCard = ({ route, routeIdx }) => {
  const [showTelescoping, setShowTelescoping] = useState(false);
  const pmi = qualityPmiBadge(route.green_metrics);
  const impurityRisk = (route.impurity_analysis?.overall_impurity_risk || "").toLowerCase();
  const borderClass = impurityRisk === "low" ? "border-green-500/40" : "border-purple-500/30";
  const telescoping = route.telescoping || {};
  const telescopablePairs = telescoping.telescopable_pairs || [];
  const ia = route.industrial_acceptability;

  return (
    <Card className={`bg-white/10 backdrop-blur-md ${borderClass}`} data-testid={`route-${routeIdx}`}>
      <CardHeader>
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div className="flex-1">
            <CardTitle className="text-white flex flex-wrap items-center gap-y-2">
              Route {routeIdx + 1}
              <span className="relative group ml-3 inline-block">
                <Badge className="bg-purple-600 text-white">Score: {route.score}</Badge>
                <ScoreBreakdown scoreBreakdown={route.score_breakdown} />
              </span>
              <Badge className={`ml-3 border ${confidenceClass(route.confidence)}`}>
                {route.confidence || "low"} confidence
              </Badge>
              <SourceBadge source={route.prediction_source?.route_generation || route.evidence?.source_type} />
              {ia && <IndustrialStatusBadge status={ia.industrial_status} />}
              {pmi && <Badge className={`ml-3 border ${pmi.cls}`}>{pmi.label}</Badge>}
              {route.green_metrics?.atom_economy_percent != null && (
                <Badge className="ml-3 bg-cyan-500/20 border border-cyan-400/50 text-cyan-200">
                  AE: {number(route.green_metrics.atom_economy_percent).toFixed(1)}%
                </Badge>
              )}
              {route.green_metrics?.route_type && (
                <Badge className="ml-3 bg-slate-500/20 border border-slate-400/50 text-slate-200 capitalize">
                  {route.green_metrics.route_type}
                </Badge>
              )}
            </CardTitle>
            {ia && (
              <EffectiveCostPanel 
                baseCost={ia.base_cost} 
                yieldLossCost={ia.yield_loss_cost} 
                effectiveCost={ia.effective_cost} 
              />
            )}
          </div>
          <div className="flex gap-4 text-sm flex-wrap justify-end">
            <div className="flex items-center text-green-400">
              <TrendingUp className="w-4 h-4 mr-1" />
              {number(route.overall_yield_percent || route.overall_yield).toFixed(1)}% yield
              {ia && <span className="text-xs text-green-400/60 ml-1">/ {ia.required_yield_percent}% req</span>}
            </div>
            <div className="flex items-center text-yellow-400">
              <DollarSign className="w-4 h-4 mr-1" />
              ${number(route.total_cost_usd).toFixed(2)}
            </div>
            <div className="flex items-center text-blue-400">
              <Clock className="w-4 h-4 mr-1" />
              {number(route.total_time_hours).toFixed(1)}h
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {ia && (
          <RejectionReasons 
            reasons={ia.rejection_reasons} 
            status={ia.industrial_status} 
            yieldPct={ia.yield_percent} 
            requiredYield={ia.required_yield_percent} 
          />
        )}
        <ImpurityBanner impurityAnalysis={route.impurity_analysis} />
        <RouteEvidencePanel route={route} />

        <div className="mb-4">
          <p className="text-purple-300 font-medium mb-3">Starting Materials:</p>
          <div className="flex flex-wrap gap-4">
            {(route.starting_materials || []).map((sm, idx) => {
              const smiles = sm.smiles || sm;
              return (
                <div key={idx} className="flex flex-col items-center gap-1.5">
                  <MoleculeRenderer smiles={smiles} size={120} />
                  <Badge variant="outline" className="bg-blue-500/20 border-blue-400/50 text-blue-200 font-mono text-xs max-w-[130px] truncate" title={smiles}>
                    {smiles}
                  </Badge>
                </div>
              );
            })}
          </div>
        </div>

        <Separator className="my-4 bg-purple-500/30" />

        <div className="space-y-4">
          <p className="text-purple-300 font-medium">Synthesis Steps:</p>
          {(route.steps || []).map((step, stepIdx) => {
            const ci = step.catalyst_intelligence || {};
            return (
              <div key={step.id || stepIdx} className="bg-white/5 rounded-lg p-4 border border-purple-500/20">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <div className="bg-purple-600 text-white rounded-full w-8 h-8 flex items-center justify-center font-bold">{stepIdx + 1}</div>
                    <div>
                      <p className="text-white font-semibold">{step.reaction_type}</p>
                      <div className="flex flex-wrap gap-2 mt-1">
                        <Badge className={`${getDifficultyColor(step.difficulty)} text-white text-xs`}>{step.difficulty || "standard"}</Badge>
                        <CleanCatalystBadge level={ci.hierarchy_level} />
                        {step.confidence && (
                          <Badge className={`border text-xs ${confidenceClass(step.confidence)}`}>
                            {step.confidence}
                          </Badge>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="text-right text-sm">
                    <p className="text-green-400">Yield: {number(step.estimated_yield_percent || step.estimated_yield).toFixed(1)}%</p>
                    <p className="text-yellow-400">Cost: ${number(step.estimated_cost_usd).toFixed(2)}</p>
                  </div>
                </div>

                <div className="mb-3">
                  <p className="text-purple-300 text-xs mb-1">Reactants:</p>
                  <div className="flex flex-wrap gap-2 mb-2">
                    {(step.reactants || []).map((r, idx) => {
                      const smiles = r.smiles || r;
                      return <code key={idx} className="text-xs bg-slate-800/50 px-2 py-1 rounded text-purple-200">{smiles}</code>;
                    })}
                  </div>
                  <p className="text-purple-300 text-xs mb-1">Product:</p>
                  <code className="text-xs bg-slate-800/50 px-2 py-1 rounded text-green-300 block">
                    {step.product?.smiles || step.product}
                  </code>
                </div>

                {step.conditions && (
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs text-purple-200">
                    {step.conditions.temperature_celsius != null && <div><span className="text-purple-400">Temp:</span> {step.conditions.temperature_celsius}°C</div>}
                    {step.conditions.solvent && <div><span className="text-purple-400">Solvent:</span> {step.conditions.solvent}</div>}
                    {step.conditions.catalyst && <div><span className="text-purple-400">Catalyst:</span> {step.conditions.catalyst}</div>}
                    {step.conditions.time_hours && <div><span className="text-purple-400">Time:</span> {step.conditions.time_hours}h</div>}
                    {step.catalyst_loading && <div><span className="text-purple-400">Loading:</span> {step.catalyst_loading}</div>}
                    {step.solvent_amount && <div><span className="text-purple-400">Solvent amt:</span> {step.solvent_amount}</div>}
                    {step.concentration_m != null && <div><span className="text-purple-400">Conc:</span> {number(step.concentration_m).toFixed(2)} M</div>}
                    {step.batch_scale && <div><span className="text-purple-400">Basis:</span> {step.batch_scale}</div>}
                  </div>
                )}

                <StepEvidencePanel step={step} />

                <div className="mt-3 rounded-md border border-purple-500/20 bg-slate-900/30 overflow-hidden">
                  <div className="grid grid-cols-12 gap-2 px-3 py-2 text-[11px] text-purple-300/70 border-b border-purple-500/20">
                    <span className="col-span-3">Role</span>
                    <span className="col-span-4">Material</span>
                    <span className="col-span-2">Eq</span>
                    <span className="col-span-3">Amount</span>
                  </div>
                  {estimateStepInputs(step, stepIdx).map((row, idx) => (
                    <div key={idx} className="grid grid-cols-12 gap-2 px-3 py-2 text-[11px] border-b border-purple-500/10 last:border-b-0">
                      <span className="col-span-3 text-purple-200">{row.role}</span>
                      <span className="col-span-4 text-white font-mono truncate" title={row.name}>{row.name}</span>
                      <span className="col-span-2 text-blue-200">{row.equivalents ?? "-"}</span>
                      <span className="col-span-3 text-green-200">{row.amount}</span>
                    </div>
                  ))}
                </div>

                <div className="mt-3 text-xs text-purple-200">
                  {ci.catalyst_cost_per_kg != null && <p>Est. ${number(ci.catalyst_cost_per_kg).toFixed(2)}/kg product</p>}
                  {ci.pd_removal_required && <p className="text-red-300">Pd removal step required (+2-3 purification steps)</p>}
                  {ci.regulatory_note && <p className="text-purple-300">{ci.regulatory_note}</p>}
                </div>
                {(step.cost_drivers?.length > 0 || step.sanity_flags?.length > 0 || step.feasibility_notes?.length > 0) && (
                  <div className="mt-3 flex flex-wrap gap-2 text-xs">
                    {(step.cost_drivers || []).slice(0, 3).map((item) => (
                      <Badge key={`cost-${item}`} className="bg-yellow-500/15 border border-yellow-400/30 text-yellow-200">
                        Cost: {item}
                      </Badge>
                    ))}
                    {(step.sanity_flags || []).slice(0, 3).map((item) => (
                      <Badge key={`flag-${item}`} className="bg-red-500/15 border border-red-400/30 text-red-200">
                        Check: {item}
                      </Badge>
                    ))}
                    {(step.feasibility_notes || []).slice(0, 2).map((item) => (
                      <Badge key={`note-${item}`} className="bg-blue-500/15 border border-blue-400/30 text-blue-200">
                        {item}
                      </Badge>
                    ))}
                  </div>
                )}
                {step.notes && <p className="text-xs text-purple-300 mt-2 italic">{step.notes}</p>}
              </div>
            );
          })}
        </div>

        {telescopablePairs.length > 0 && (
          <div className="mt-4 rounded-lg border border-cyan-400/40 bg-cyan-500/10">
            <button className="w-full px-4 py-3 text-left text-cyan-100" onClick={() => setShowTelescoping(!showTelescoping)}>
              💡 Optimization opportunity: Steps {telescopablePairs.map((pair) => pair.join("-")).join(", ")} can be telescoped
            </button>
            {showTelescoping && (
              <div className="px-4 pb-4 text-sm text-cyan-100">
                Saves {number(telescoping.total_time_reduction_hours).toFixed(1)} hours, reduces PMI by {number(telescoping.total_pmi_reduction).toFixed(1)}%.
                {telescoping.recommended_sequence && <p className="mt-2">{telescoping.recommended_sequence}</p>}
              </div>
            )}
          </div>
        )}

        {route.improvement_targets?.length > 0 && (
          <Alert className="mt-4 bg-purple-500/10 border-purple-500/30">
            <AlertDescription className="text-purple-200">
              {route.improvement_targets[0]}
            </AlertDescription>
          </Alert>
        )}
        
        {ia && <ARDActionsPanel actions={ia.recommended_actions} />}
        <FeedbackPanel route={route} />
      </CardContent>
    </Card>
  );
};

export default RouteCard;
