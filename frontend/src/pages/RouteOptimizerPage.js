import React, { useState, useEffect } from "react";
import axios from "axios";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import {
  Zap,
  Loader2,
  AlertCircle,
  CheckCircle2,
  ArrowRight,
  Shield,
  Gauge,
  Wrench,
  Beaker,
  RefreshCw,
  Sparkles,
  AlertTriangle,
  XCircle,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import useSynthesisStore from "../store/synthesisStore";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const sampleRoute = {
  steps: [
    {
      reaction_type: "esterification",
      conditions: {
        catalyst: "H2SO4",
        solvent: "DCM",
        temperature_celsius: 80,
        pressure_atm: 1,
      },
    },
    {
      reaction_type: "suzuki_coupling",
      conditions: {
        catalyst: "Pd(PPh3)4",
        solvent: "DMF",
        temperature_celsius: 100,
        pressure_atm: 1,
      },
    },
  ],
  overall_yield_percent: 65,
  total_cost_usd: 350,
  num_steps: 2,
};

const sampleHighRiskRoute = {
  steps: [
    {
      reaction_type: "pyrolysis",
      conditions: {
        catalyst: "AlCl3",
        solvent: "benzene",
        temperature_celsius: 280,
        pressure_atm: 5,
      },
    },
    {
      reaction_type: "high_pressure_hydrogenation",
      conditions: {
        catalyst: "Pd/C",
        solvent: "THF",
        temperature_celsius: 150,
        pressure_atm: 50,
      },
    },
  ],
  overall_yield_percent: 40,
  total_cost_usd: 800,
  num_steps: 2,
};

const RouteOptimizerPage = () => {
  // ── Global store ───────────────────────────────────────────
  const { getSelectedRoute, targetSmiles: storedTarget, clearSession, plannedRoutes } = useSynthesisStore();
  const [storedRouteBanner, setStoredRouteBanner] = useState(null);

  // ── Local state ─────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState("full");
  const [routeJson, setRouteJson] = useState(
    JSON.stringify(sampleRoute, null, 2)
  );
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [expandedSection, setExpandedSection] = useState({
    mutations: true,
    constraints: true,
    confidence: true,
    equipment: true,
  });

  // On mount: detect stored route from Synthesis Planner
  useEffect(() => {
    const route = getSelectedRoute();
    if (route && storedTarget) {
      setStoredRouteBanner({
        target: storedTarget,
        steps: route.steps?.length ?? 0,
        yield: route.overall_yield_percent ?? null,
        route,
      });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const presets = [
    {
      name: "Standard 2-step",
      route: sampleRoute,
    },
    {
      name: "High-risk route",
      route: sampleHighRiskRoute,
    },
  ];

  const runFullOptimization = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const route = JSON.parse(routeJson);
      const response = await axios.post(`${API}/routes/optimize`, {
        route,
        apply_mutations: true,
        check_constraints: true,
        calculate_confidence: true,
        check_equipment: true,
        mutation_types: ["all"],
      });
      setResult(response.data);
    } catch (e) {
      setError(e.response?.data?.detail || "Optimization failed. Check JSON.");
    } finally {
      setLoading(false);
    }
  };

  const runMutation = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const route = JSON.parse(routeJson);
      const response = await axios.post(`${API}/routes/mutate`, {
        route,
        mutation_types: ["all"],
      });
      setResult({ mutations_only: true, ...response.data });
    } catch (e) {
      setError(e.response?.data?.detail || "Mutation failed.");
    } finally {
      setLoading(false);
    }
  };

  const runConstraintFeedback = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const route = JSON.parse(routeJson);
      const steps = route.steps || [];
      const reaction =
        steps.length > 0 ? steps[0].conditions || steps[0] : route;
      const response = await axios.post(`${API}/routes/constraint-feedback`, {
        reaction,
        scale: "lab",
        batch_size_kg: 0.1,
      });
      setResult({ constraints_only: true, ...response.data });
    } catch (e) {
      setError(e.response?.data?.detail || "Constraint feedback failed.");
    } finally {
      setLoading(false);
    }
  };

  const runConfidence = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const route = JSON.parse(routeJson);
      const response = await axios.post(`${API}/routes/confidence`, {
        route,
        mcts_visits: 100,
      });
      setResult({ confidence_only: true, ...response.data });
    } catch (e) {
      setError(e.response?.data?.detail || "Confidence calc failed.");
    } finally {
      setLoading(false);
    }
  };

  const runEquipmentCheck = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const route = JSON.parse(routeJson);
      const response = await axios.post(`${API}/routes/equipment-check`, {
        route,
      });
      setResult({ equipment_only: true, ...response.data });
    } catch (e) {
      setError(e.response?.data?.detail || "Equipment check failed.");
    } finally {
      setLoading(false);
    }
  };

  const toggleSection = (section) => {
    setExpandedSection((prev) => ({ ...prev, [section]: !prev[section] }));
  };

  const getRiskIcon = (level) => {
    switch (level) {
      case "low":
        return <CheckCircle2 className="w-5 h-5 text-green-400" />;
      case "medium":
        return <AlertTriangle className="w-5 h-5 text-yellow-400" />;
      case "high":
        return <AlertCircle className="w-5 h-5 text-orange-400" />;
      case "critical":
        return <XCircle className="w-5 h-5 text-red-400" />;
      default:
        return <Gauge className="w-5 h-5 text-purple-400" />;
    }
  };

  const getRiskColor = (level) => {
    switch (level) {
      case "low":
        return "text-green-400";
      case "medium":
        return "text-yellow-400";
      case "high":
        return "text-orange-400";
      case "critical":
        return "text-red-400";
      default:
        return "text-purple-400";
    }
  };

  const getConfidenceColor = (score) => {
    if (score >= 75) return "text-green-400";
    if (score >= 50) return "text-yellow-400";
    if (score >= 25) return "text-orange-400";
    return "text-red-400";
  };

  const ConfidenceBar = ({ label, value, max = 100 }) => {
    const pct = Math.min((value / max) * 100, 100);
    let color = "bg-green-500";
    if (pct < 50) color = "bg-red-500";
    else if (pct < 75) color = "bg-yellow-500";
    return (
      <div className="space-y-1">
        <div className="flex justify-between text-xs">
          <span className="text-purple-300/70">{label}</span>
          <span className="text-white font-mono">{value.toFixed(1)}</span>
        </div>
        <div className="w-full bg-white/10 rounded-full h-2">
          <div
            className={`${color} h-2 rounded-full transition-all duration-500`}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>
    );
  };

  return (
    <div className="max-w-6xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <Zap className="w-8 h-8 text-purple-400" />
        <div>
          <h1 className="text-3xl font-bold text-white">Route Optimizer</h1>
          <p className="text-purple-200/70 text-sm">
            Mutation, constraint feedback, confidence scoring & equipment binding
          </p>
        </div>
      </div>

      {/* ── Stored-route banner ─────────────────────────────── */}
      {storedRouteBanner && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 12,
          background: 'rgba(139,92,246,0.15)',
          border: '1px solid rgba(139,92,246,0.4)',
          borderRadius: 10, padding: '10px 16px', marginBottom: 20,
        }}>
          <Beaker size={16} style={{ color: '#c4b5fd', flexShrink: 0 }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <span style={{ fontSize: 13, color: '#e9d5ff', fontWeight: 600 }}>
              Route from Synthesis Planner&emsp;
            </span>
            <span style={{ fontFamily: 'monospace', fontSize: 12, color: '#a78bfa' }}>
              {storedRouteBanner.target.slice(0, 30)}{storedRouteBanner.target.length > 30 ? '…' : ''}
            </span>
            <span style={{ fontSize: 12, color: '#7c3aed', marginLeft: 8 }}>
              &bull; {storedRouteBanner.steps} step{storedRouteBanner.steps !== 1 ? 's' : ''}
              {storedRouteBanner.yield !== null ? ` • ${storedRouteBanner.yield.toFixed(1)}% yield` : ''}
            </span>
          </div>
          <button
            onClick={() => {
              setRouteJson(JSON.stringify(storedRouteBanner.route, null, 2));
              setStoredRouteBanner(null);
            }}
            style={{
              background: 'rgba(139,92,246,0.3)', border: '1px solid rgba(139,92,246,0.5)',
              borderRadius: 6, padding: '4px 12px', color: '#e9d5ff',
              fontSize: 12, cursor: 'pointer', whiteSpace: 'nowrap',
            }}
          >
            Load into editor
          </button>
          <button
            onClick={() => { clearSession(); setStoredRouteBanner(null); }}
            style={{
              background: 'none', border: 'none', color: '#f87171',
              fontSize: 18, cursor: 'pointer', lineHeight: 1, padding: '2px 4px',
            }}
            title="Clear session"
          >
            ×
          </button>
        </div>
      )}

      {/* Route Input */}
      <Card className="bg-white/5 backdrop-blur-md border-purple-500/20 mb-6">
        <CardContent className="p-6 space-y-4">
          <div className="flex items-center justify-between mb-2">
            <label className="text-white font-medium">Route (JSON)</label>
            <div className="flex gap-2">
              {presets.map((p) => (
                <Button
                  key={p.name}
                  onClick={() => setRouteJson(JSON.stringify(p.route, null, 2))}
                  variant="outline"
                  size="sm"
                  className="bg-purple-500/10 border-purple-500/30 text-purple-200 text-xs"
                >
                  {p.name}
                </Button>
              ))}
            </div>
          </div>
          <textarea
            value={routeJson}
            onChange={(e) => setRouteJson(e.target.value)}
            rows={10}
            className="w-full bg-white/10 border border-purple-500/30 rounded-md p-3 text-white font-mono text-xs"
          />
        </CardContent>
      </Card>

      {/* Action Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="bg-white/5 border border-purple-500/20 mb-6 flex-wrap">
          <TabsTrigger
            value="full"
            className="data-[state=active]:bg-purple-600/30 text-purple-200"
          >
            <Sparkles className="w-4 h-4 mr-2" /> Full Optimization
          </TabsTrigger>
          <TabsTrigger
            value="mutate"
            className="data-[state=active]:bg-purple-600/30 text-purple-200"
          >
            <RefreshCw className="w-4 h-4 mr-2" /> Mutations
          </TabsTrigger>
          <TabsTrigger
            value="constraints"
            className="data-[state=active]:bg-purple-600/30 text-purple-200"
          >
            <Shield className="w-4 h-4 mr-2" /> Constraints
          </TabsTrigger>
          <TabsTrigger
            value="confidence"
            className="data-[state=active]:bg-purple-600/30 text-purple-200"
          >
            <Gauge className="w-4 h-4 mr-2" /> Confidence
          </TabsTrigger>
          <TabsTrigger
            value="equipment"
            className="data-[state=active]:bg-purple-600/30 text-purple-200"
          >
            <Wrench className="w-4 h-4 mr-2" /> Equipment
          </TabsTrigger>
        </TabsList>

        <TabsContent value="full">
          <Button
            onClick={runFullOptimization}
            disabled={loading}
            className="w-full bg-gradient-to-r from-purple-600 to-pink-600 text-white mb-6"
          >
            {loading ? (
              <Loader2 className="w-4 h-4 animate-spin mr-2" />
            ) : (
              <Sparkles className="w-4 h-4 mr-2" />
            )}
            Run Full Optimization Pipeline
          </Button>
        </TabsContent>

        <TabsContent value="mutate">
          <Button
            onClick={runMutation}
            disabled={loading}
            className="w-full bg-gradient-to-r from-blue-600 to-cyan-600 text-white mb-6"
          >
            {loading ? (
              <Loader2 className="w-4 h-4 animate-spin mr-2" />
            ) : (
              <RefreshCw className="w-4 h-4 mr-2" />
            )}
            Apply Mutations (Catalyst, Solvent, Temperature)
          </Button>
        </TabsContent>

        <TabsContent value="constraints">
          <Button
            onClick={runConstraintFeedback}
            disabled={loading}
            className="w-full bg-gradient-to-r from-orange-600 to-red-600 text-white mb-6"
          >
            {loading ? (
              <Loader2 className="w-4 h-4 animate-spin mr-2" />
            ) : (
              <Shield className="w-4 h-4 mr-2" />
            )}
            Evaluate & Auto-Fix Constraints
          </Button>
        </TabsContent>

        <TabsContent value="confidence">
          <Button
            onClick={runConfidence}
            disabled={loading}
            className="w-full bg-gradient-to-r from-green-600 to-emerald-600 text-white mb-6"
          >
            {loading ? (
              <Loader2 className="w-4 h-4 animate-spin mr-2" />
            ) : (
              <Gauge className="w-4 h-4 mr-2" />
            )}
            Calculate Confidence Score
          </Button>
        </TabsContent>

        <TabsContent value="equipment">
          <Button
            onClick={runEquipmentCheck}
            disabled={loading}
            className="w-full bg-gradient-to-r from-indigo-600 to-violet-600 text-white mb-6"
          >
            {loading ? (
              <Loader2 className="w-4 h-4 animate-spin mr-2" />
            ) : (
              <Wrench className="w-4 h-4 mr-2" />
            )}
            Check Equipment Feasibility
          </Button>
        </TabsContent>
      </Tabs>

      {/* Error */}
      {error && (
        <Alert className="mb-6 bg-red-500/20 border-red-500/50">
          <AlertCircle className="h-4 w-4 text-red-400" />
          <AlertDescription className="text-red-200">{error}</AlertDescription>
        </Alert>
      )}

      {/* Full Optimization Results */}
      {result && !result.mutations_only && !result.constraints_only && !result.confidence_only && !result.equipment_only && (
        <div className="space-y-4">
          {/* Mutations Section */}
          {result.mutations && (
            <Card className="bg-white/5 backdrop-blur-md border-purple-500/20">
              <button
                onClick={() => toggleSection("mutations")}
                className="w-full p-4 flex items-center justify-between text-left"
              >
                <div className="flex items-center gap-3">
                  <RefreshCw className="w-5 h-5 text-blue-400" />
                  <span className="text-white font-semibold">
                    Mutations Applied: {result.mutations.count}
                  </span>
                </div>
                {expandedSection.mutations ? (
                  <ChevronUp className="w-5 h-5 text-purple-300" />
                ) : (
                  <ChevronDown className="w-5 h-5 text-purple-300" />
                )}
              </button>
              {expandedSection.mutations && (
                <CardContent className="pt-0 space-y-2">
                  {result.mutations.applied.map((m, i) => (
                    <div
                      key={i}
                      className="bg-blue-500/10 rounded-lg p-3 border border-blue-500/20"
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <Badge className="bg-blue-600/30 text-blue-200 text-xs">
                          {m.type.split("_step_")[0].replace(/_/g, " ")}
                        </Badge>
                        <span className="text-purple-300/60 text-xs">
                          Step {m.type.split("_step_")[1]}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 text-sm">
                        <code className="text-red-300 bg-red-500/10 px-2 py-0.5 rounded">
                          {m.original}
                        </code>
                        <ArrowRight className="w-4 h-4 text-purple-300" />
                        <code className="text-green-300 bg-green-500/10 px-2 py-0.5 rounded">
                          {m.new}
                        </code>
                      </div>
                      <p className="text-purple-200/60 text-xs mt-1">
                        {m.reason}
                      </p>
                    </div>
                  ))}
                </CardContent>
              )}
            </Card>
          )}

          {/* Confidence Section */}
          {result.confidence && (
            <Card className="bg-white/5 backdrop-blur-md border-purple-500/20">
              <button
                onClick={() => toggleSection("confidence")}
                className="w-full p-4 flex items-center justify-between text-left"
              >
                <div className="flex items-center gap-3">
                  {getRiskIcon(result.confidence.risk_level)}
                  <span className="text-white font-semibold">
                    Confidence:{" "}
                    <span className={getConfidenceColor(result.confidence.overall)}>
                      {result.confidence.overall}%
                    </span>
                  </span>
                  <Badge
                    className={`${getRiskColor(result.confidence.risk_level)} bg-white/5 text-xs`}
                  >
                    {result.confidence.risk_level} risk
                  </Badge>
                </div>
                {expandedSection.confidence ? (
                  <ChevronUp className="w-5 h-5 text-purple-300" />
                ) : (
                  <ChevronDown className="w-5 h-5 text-purple-300" />
                )}
              </button>
              {expandedSection.confidence && (
                <CardContent className="pt-0 space-y-3">
                  <ConfidenceBar
                    label="Yield Confidence"
                    value={result.confidence.breakdown.yield}
                  />
                  <ConfidenceBar
                    label="Cost Confidence"
                    value={result.confidence.breakdown.cost}
                  />
                  <ConfidenceBar
                    label="Safety Confidence"
                    value={result.confidence.breakdown.safety}
                  />
                  <ConfidenceBar
                    label="Equipment Feasibility"
                    value={result.confidence.breakdown.equipment}
                  />
                  {result.confidence.risk_factors.length > 0 && (
                    <div className="mt-2">
                      <p className="text-purple-300/70 text-xs mb-1">
                        Risk Factors:
                      </p>
                      {result.confidence.risk_factors.map((f, i) => (
                        <div
                          key={i}
                          className="flex items-center gap-2 text-xs text-orange-300 bg-orange-500/10 px-2 py-1 rounded mb-1"
                        >
                          <AlertTriangle className="w-3 h-3" /> {f}
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              )}
            </Card>
          )}

          {/* Constraint Feedback Section */}
          {result.constraint_feedback && (
            <Card className="bg-white/5 backdrop-blur-md border-purple-500/20">
              <button
                onClick={() => toggleSection("constraints")}
                className="w-full p-4 flex items-center justify-between text-left"
              >
                <div className="flex items-center gap-3">
                  <Shield className="w-5 h-5 text-orange-400" />
                  <span className="text-white font-semibold">
                    Constraint Feedback:{" "}
                    {result.constraint_feedback.fixes.length} fixes
                  </span>
                </div>
                {expandedSection.constraints ? (
                  <ChevronUp className="w-5 h-5 text-purple-300" />
                ) : (
                  <ChevronDown className="w-5 h-5 text-purple-300" />
                )}
              </button>
              {expandedSection.constraints && (
                <CardContent className="pt-0 space-y-3">
                  <p className="text-purple-200/70 text-sm">
                    {result.constraint_feedback.summary}
                  </p>
                  {result.constraint_feedback.fixes.length > 0 ? (
                    result.constraint_feedback.fixes.map((fix, i) => (
                      <div
                        key={i}
                        className="bg-orange-500/10 rounded-lg p-3 border border-orange-500/20"
                      >
                        <div className="flex items-center gap-2 mb-1">
                          <Badge className="bg-orange-600/30 text-orange-200 text-xs">
                            {fix.issue}
                          </Badge>
                        </div>
                        <p className="text-white text-sm">{fix.fix}</p>
                      </div>
                    ))
                  ) : (
                    <div className="bg-green-500/10 rounded-lg p-3 border border-green-500/20">
                      <div className="flex items-center gap-2">
                        <CheckCircle2 className="w-4 h-4 text-green-400" />
                        <span className="text-green-200 text-sm">
                          No constraint issues detected — route is feasible!
                        </span>
                      </div>
                    </div>
                  )}
                  {/* Penalty comparison */}
                  <div className="grid grid-cols-2 gap-4 mt-2">
                    <div className="bg-white/5 rounded p-3 border border-purple-500/20 text-center">
                      <p className="text-purple-300/60 text-xs">
                        Original Penalty
                      </p>
                      <p className="text-2xl font-bold text-white">
                        {result.constraint_feedback.original.total_penalty?.toFixed(1) || "0.0"}
                      </p>
                    </div>
                    <div className="bg-white/5 rounded p-3 border border-purple-500/20 text-center">
                      <p className="text-purple-300/60 text-xs">
                        After Fixes
                      </p>
                      <p className="text-2xl font-bold text-green-400">
                        {result.constraint_feedback.improved.total_penalty?.toFixed(1) || "0.0"}
                      </p>
                    </div>
                  </div>
                </CardContent>
              )}
            </Card>
          )}

          {/* Equipment Section */}
          {result.equipment && (
            <Card className="bg-white/5 backdrop-blur-md border-purple-500/20">
              <button
                onClick={() => toggleSection("equipment")}
                className="w-full p-4 flex items-center justify-between text-left"
              >
                <div className="flex items-center gap-3">
                  <Wrench className="w-5 h-5 text-indigo-400" />
                  <span className="text-white font-semibold">
                    Equipment:{" "}
                    {result.equipment.feasible ? (
                      <span className="text-green-400">Feasible</span>
                    ) : (
                      <span className="text-red-400">Not Feasible</span>
                    )}
                  </span>
                  <Badge className="bg-indigo-600/30 text-indigo-200 text-xs">
                    Score: {result.equipment.overall_score}
                  </Badge>
                </div>
                {expandedSection.equipment ? (
                  <ChevronUp className="w-5 h-5 text-purple-300" />
                ) : (
                  <ChevronDown className="w-5 h-5 text-purple-300" />
                )}
              </button>
              {expandedSection.equipment && (
                <CardContent className="pt-0 space-y-3">
                  {result.equipment.step_equipment?.map((eq, i) => (
                    <div
                      key={i}
                      className="bg-indigo-500/10 rounded-lg p-3 border border-indigo-500/20 flex items-center justify-between"
                    >
                      <div className="flex items-center gap-2">
                        <Beaker className="w-4 h-4 text-indigo-300" />
                        <span className="text-white text-sm">
                          Step {eq.step + 1}: {eq.reactor}
                        </span>
                      </div>
                      <Badge
                        className={`${
                          eq.score >= 50
                            ? "bg-green-500/20 text-green-300"
                            : "bg-red-500/20 text-red-300"
                        } text-xs`}
                      >
                        Score: {eq.score}
                      </Badge>
                    </div>
                  ))}
                  {result.equipment.issues?.length > 0 && (
                    <div className="space-y-2 mt-2">
                      <p className="text-red-300/70 text-xs font-semibold">
                        Issues:
                      </p>
                      {result.equipment.issues.map((issue, i) => (
                        <Alert
                          key={i}
                          className="bg-red-500/10 border-red-500/30"
                        >
                          <XCircle className="h-4 w-4 text-red-400" />
                          <AlertDescription className="text-red-200 text-xs">
                            {issue.detail}
                          </AlertDescription>
                        </Alert>
                      ))}
                    </div>
                  )}
                  {result.equipment.recommendations?.length > 0 && (
                    <div className="space-y-2 mt-2">
                      <p className="text-yellow-300/70 text-xs font-semibold">
                        Recommendations:
                      </p>
                      {result.equipment.recommendations.map((rec, i) => (
                        <div
                          key={i}
                          className="bg-yellow-500/10 rounded p-2 border border-yellow-500/20 text-xs text-yellow-200"
                        >
                          Step {rec.step + 1}: {rec.equipment} (
                          {rec.reaction_type})
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              )}
            </Card>
          )}
        </div>
      )}

      {/* Individual operation results */}
      {result && result.mutations_only && (
        <Card className="bg-white/5 backdrop-blur-md border-purple-500/20">
          <CardHeader>
            <CardTitle className="text-white flex items-center gap-2">
              <RefreshCw className="w-5 h-5 text-blue-400" />
              {result.mutation_count} Mutations Applied
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {(result.mutations_applied || []).map((m, i) => (
              <div
                key={i}
                className="bg-blue-500/10 rounded-lg p-3 border border-blue-500/20"
              >
                <Badge className="bg-blue-600/30 text-blue-200 text-xs mb-1">
                  {m.type.replace(/_/g, " ")}
                </Badge>
                <div className="flex items-center gap-2 text-sm mt-1">
                  <code className="text-red-300 bg-red-500/10 px-2 py-0.5 rounded">
                    {m.original}
                  </code>
                  <ArrowRight className="w-4 h-4 text-purple-300" />
                  <code className="text-green-300 bg-green-500/10 px-2 py-0.5 rounded">
                    {m.new}
                  </code>
                </div>
                <p className="text-purple-200/60 text-xs mt-1">{m.reason}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {result && result.confidence_only && (
        <Card className="bg-white/5 backdrop-blur-md border-purple-500/20">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-white flex items-center gap-2">
                {getRiskIcon(result.risk_level)}
                Confidence: {result.overall_confidence}%
              </CardTitle>
              <Badge
                className={`${getRiskColor(result.risk_level)} bg-white/5`}
              >
                {result.risk_level} risk
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <ConfidenceBar
              label="Yield Confidence"
              value={result.yield_confidence}
            />
            <ConfidenceBar
              label="Cost Confidence"
              value={result.cost_confidence}
            />
            <ConfidenceBar
              label="Safety Confidence"
              value={result.safety_confidence}
            />
            <ConfidenceBar
              label="Equipment Feasibility"
              value={result.equipment_feasibility}
            />
            {result.risk_factors?.length > 0 && (
              <div className="mt-2 space-y-1">
                {result.risk_factors.map((f, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-2 text-xs text-orange-300 bg-orange-500/10 px-2 py-1 rounded"
                  >
                    <AlertTriangle className="w-3 h-3" /> {f}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {result && result.constraints_only && (
        <Card className="bg-white/5 backdrop-blur-md border-purple-500/20">
          <CardHeader>
            <CardTitle className="text-white flex items-center gap-2">
              <Shield className="w-5 h-5 text-orange-400" />
              Constraint Feedback: {result.num_fixes} fixes
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-purple-200/70 text-sm">
              {result.improvement_summary}
            </p>
            {(result.applied_fixes || []).map((fix, i) => (
              <div
                key={i}
                className="bg-orange-500/10 rounded-lg p-3 border border-orange-500/20"
              >
                <Badge className="bg-orange-600/30 text-orange-200 text-xs mb-1">
                  {fix.issue}
                </Badge>
                <p className="text-white text-sm">{fix.fix}</p>
              </div>
            ))}
            {result.num_fixes === 0 && (
              <div className="bg-green-500/10 rounded-lg p-3 border border-green-500/20 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-green-400" />
                <span className="text-green-200 text-sm">
                  All constraints satisfied
                </span>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {result && result.equipment_only && (
        <Card className="bg-white/5 backdrop-blur-md border-purple-500/20">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-white flex items-center gap-2">
                <Wrench className="w-5 h-5 text-indigo-400" />
                Equipment:{" "}
                {result.feasible ? (
                  <span className="text-green-400">Feasible</span>
                ) : (
                  <span className="text-red-400">Not Feasible</span>
                )}
              </CardTitle>
              <Badge className="bg-indigo-600/30 text-indigo-200">
                Score: {result.overall_score}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-2">
            {(result.step_equipment || []).map((eq, i) => (
              <div
                key={i}
                className="bg-indigo-500/10 rounded-lg p-3 border border-indigo-500/20 flex justify-between"
              >
                <span className="text-white text-sm">
                  Step {eq.step + 1}: {eq.reactor}
                </span>
                <Badge
                  className={`${
                    eq.score >= 50
                      ? "bg-green-500/20 text-green-300"
                      : "bg-red-500/20 text-red-300"
                  } text-xs`}
                >
                  {eq.score}
                </Badge>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default RouteOptimizerPage;
