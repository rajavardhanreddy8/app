import React, { useState } from "react";
import axios from "axios";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import {
  Target,
  Loader2,
  AlertCircle,
  CheckCircle2,
  ArrowRight,
  TrendingUp,
  RefreshCw,
  Timer,
  Flame,
  Leaf,
  DollarSign,
  Zap,
  PauseCircle,
  ChevronDown,
  ChevronUp,
  FlaskConical,
} from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const sampleRoutes = [
  {
    steps: [
      { reaction_type: "esterification", conditions: { catalyst: "H2SO4", solvent: "DCM", temperature_celsius: 120, pressure_atm: 1 }},
      { reaction_type: "suzuki_coupling", conditions: { catalyst: "Pd(PPh3)4", solvent: "DMF", temperature_celsius: 100, pressure_atm: 1 }},
    ],
    overall_yield_percent: 60,
    total_cost_usd: 350,
    num_steps: 2,
  },
];

const greenRoutes = [
  {
    steps: [
      { reaction_type: "coupling", conditions: { catalyst: "Pd(PPh3)4", solvent: "benzene", temperature_celsius: 80 }},
      { reaction_type: "reduction", conditions: { catalyst: "AlCl3", solvent: "chloroform", temperature_celsius: 60 }},
    ],
    overall_yield_percent: 70,
    total_cost_usd: 200,
    num_steps: 2,
  },
];

const pharmaRoute = [
  {
    steps: [
      { reaction_type: "asymmetric_hydrogenation", conditions: { catalyst: "Pd(PPh3)4", solvent: "THF", temperature_celsius: 50 }},
    ],
    overall_yield_percent: 99.5,
    total_cost_usd: 800,
    num_steps: 1,
  },
];

const objectiveConfig = {
  balanced: { icon: Target, label: "Balanced", color: "from-purple-600 to-pink-600", desc: "Balance yield, cost, safety & sustainability" },
  pharma: { icon: FlaskConical, label: "Pharma", color: "from-blue-600 to-cyan-600", desc: "Max yield (>99%), min impurities" },
  cost: { icon: DollarSign, label: "Cost", color: "from-green-600 to-emerald-600", desc: "Minimize total synthesis cost" },
  green: { icon: Leaf, label: "Green", color: "from-emerald-600 to-teal-600", desc: "Maximize sustainability (green solvents, recyclable catalysts)" },
  speed: { icon: Zap, label: "Speed", color: "from-orange-600 to-amber-600", desc: "Minimize reaction time, fewer steps" },
};

const ConvergenceLoopPage = () => {
  const [routeJson, setRouteJson] = useState(JSON.stringify(sampleRoutes, null, 2));
  const [objective, setObjective] = useState("balanced");
  const [iterations, setIterations] = useState(3);
  const [topK, setTopK] = useState(5);
  const [earlyStopThreshold, setEarlyStopThreshold] = useState(0.5);
  const [pharmaMode, setPharmaMode] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [expandedRoute, setExpandedRoute] = useState(0);

  const presets = [
    { name: "Standard 2-step", routes: sampleRoutes },
    { name: "Green chemistry", routes: greenRoutes },
    { name: "Pharma (99.5%)", routes: pharmaRoute },
  ];

  const runOptimization = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const routes = JSON.parse(routeJson);
      const response = await axios.post(`${API}/routes/iterative-optimize`, {
        routes: Array.isArray(routes) ? routes : [routes],
        objective,
        optimization_iterations: iterations,
        top_k: topK,
        early_stop_threshold: earlyStopThreshold,
        pharma_mode: pharmaMode,
      });
      setResult(response.data);
    } catch (e) {
      setError(e.response?.data?.detail || "Optimization failed. Check route JSON.");
    } finally {
      setLoading(false);
    }
  };

  const getStatusBadge = (status) => {
    const map = {
      converged: { color: "bg-green-600/30 text-green-300", icon: CheckCircle2, text: "Converged" },
      max_iterations: { color: "bg-blue-600/30 text-blue-300", icon: RefreshCw, text: "Max Iterations" },
      no_improvement: { color: "bg-yellow-600/30 text-yellow-300", icon: PauseCircle, text: "No Improvement" },
    };
    const config = map[status] || map.no_improvement;
    const Icon = config.icon;
    return (
      <Badge className={`${config.color} text-sm gap-1`}>
        <Icon className="w-3 h-3" /> {config.text}
      </Badge>
    );
  };

  const ImprovementChart = ({ history }) => {
    if (!history || history.length === 0) return null;
    const maxScore = Math.max(...history.map(h => h.score_after), ...history.map(h => h.score_before));
    const minScore = Math.min(...history.map(h => h.score_before));
    const range = maxScore - minScore || 1;

    return (
      <div className="bg-white/5 rounded-lg p-4 border border-purple-500/20">
        <h3 className="text-white font-semibold text-sm mb-3">Convergence Progress</h3>
        <div className="flex items-end gap-4 h-32">
          {/* Initial bar */}
          <div className="flex flex-col items-center gap-1 flex-1">
            <span className="text-purple-300/60 text-xs">Start</span>
            <div className="w-full bg-white/10 rounded-t" style={{ height: `${((history[0].score_before - minScore + 5) / (range + 10)) * 100}%`, minHeight: '10px' }}>
              <div className="w-full h-full bg-purple-500/40 rounded-t" />
            </div>
            <span className="text-white text-xs font-mono">{history[0].score_before}</span>
          </div>
          {/* Iteration bars */}
          {history.map((h, i) => (
            <div key={i} className="flex flex-col items-center gap-1 flex-1">
              <span className="text-purple-300/60 text-xs">Iter {h.iteration}</span>
              <div className="w-full bg-white/10 rounded-t" style={{ height: `${((h.score_after - minScore + 5) / (range + 10)) * 100}%`, minHeight: '10px' }}>
                <div className={`w-full h-full rounded-t ${h.improvement > 0 ? 'bg-green-500/60' : h.improvement < 0 ? 'bg-red-500/60' : 'bg-yellow-500/60'}`} />
              </div>
              <span className="text-white text-xs font-mono">{h.score_after}</span>
              {h.improvement !== 0 && (
                <span className={`text-xs font-mono ${h.improvement > 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {h.improvement > 0 ? '+' : ''}{h.improvement}
                </span>
              )}
            </div>
          ))}
        </div>
      </div>
    );
  };

  return (
    <div className="max-w-6xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <Target className="w-8 h-8 text-purple-400" />
        <div>
          <h1 className="text-3xl font-bold text-white">Convergence Loop</h1>
          <p className="text-purple-200/70 text-sm">
            Iterative optimization: search → improve → re-search → converge
          </p>
        </div>
      </div>

      {/* Objective Selector */}
      <div className="grid grid-cols-5 gap-3 mb-6">
        {Object.entries(objectiveConfig).map(([key, config]) => {
          const Icon = config.icon;
          const isActive = objective === key;
          return (
            <button
              key={key}
              onClick={() => {
                setObjective(key);
                if (key === "pharma") setPharmaMode(true);
                else setPharmaMode(false);
              }}
              className={`p-3 rounded-lg border transition-all text-left ${
                isActive
                  ? "bg-purple-600/30 border-purple-500/50"
                  : "bg-white/5 border-purple-500/20 hover:bg-white/10"
              }`}
            >
              <Icon className={`w-5 h-5 mb-1 ${isActive ? "text-purple-300" : "text-purple-400/60"}`} />
              <p className={`text-sm font-semibold ${isActive ? "text-white" : "text-purple-200/70"}`}>{config.label}</p>
              <p className="text-[10px] text-purple-300/50 mt-0.5 leading-tight">{config.desc}</p>
            </button>
          );
        })}
      </div>

      {/* Route Input */}
      <Card className="bg-white/5 backdrop-blur-md border-purple-500/20 mb-6">
        <CardContent className="p-6 space-y-4">
          <div className="flex items-center justify-between mb-1">
            <label className="text-white font-medium">Routes (JSON array)</label>
            <div className="flex gap-2">
              {presets.map((p) => (
                <Button
                  key={p.name}
                  onClick={() => setRouteJson(JSON.stringify(p.routes, null, 2))}
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
            rows={8}
            className="w-full bg-white/10 border border-purple-500/30 rounded-md p-3 text-white font-mono text-xs"
          />

          {/* Parameters */}
          <div className="grid grid-cols-4 gap-4">
            <div>
              <label className="text-purple-200/70 text-xs mb-1 block">Iterations</label>
              <Input
                type="number"
                min={1}
                max={10}
                value={iterations}
                onChange={(e) => setIterations(parseInt(e.target.value) || 3)}
                className="bg-white/10 border-purple-500/30 text-white text-sm"
              />
            </div>
            <div>
              <label className="text-purple-200/70 text-xs mb-1 block">Top-K routes</label>
              <Input
                type="number"
                min={1}
                max={20}
                value={topK}
                onChange={(e) => setTopK(parseInt(e.target.value) || 5)}
                className="bg-white/10 border-purple-500/30 text-white text-sm"
              />
            </div>
            <div>
              <label className="text-purple-200/70 text-xs mb-1 block">Early stop threshold</label>
              <Input
                type="number"
                step={0.1}
                min={0}
                max={10}
                value={earlyStopThreshold}
                onChange={(e) => setEarlyStopThreshold(parseFloat(e.target.value) || 0.5)}
                className="bg-white/10 border-purple-500/30 text-white text-sm"
              />
            </div>
            <div className="flex items-end">
              <label className="flex items-center gap-2 text-purple-200/70 text-sm cursor-pointer pb-2">
                <input
                  type="checkbox"
                  checked={pharmaMode}
                  onChange={(e) => setPharmaMode(e.target.checked)}
                  className="rounded border-purple-500/30"
                />
                Pharma Mode (>99% yield)
              </label>
            </div>
          </div>

          {/* Run Button */}
          <Button
            onClick={runOptimization}
            disabled={loading}
            className={`w-full bg-gradient-to-r ${objectiveConfig[objective].color} text-white text-lg py-6`}
          >
            {loading ? (
              <><Loader2 className="w-5 h-5 animate-spin mr-2" /> Optimizing...</>
            ) : (
              <><Target className="w-5 h-5 mr-2" /> Run Convergence Loop ({objective})</>
            )}
          </Button>
        </CardContent>
      </Card>

      {/* Error */}
      {error && (
        <Alert className="mb-6 bg-red-500/20 border-red-500/50">
          <AlertCircle className="h-4 w-4 text-red-400" />
          <AlertDescription className="text-red-200">{error}</AlertDescription>
        </Alert>
      )}

      {/* Results */}
      {result && (
        <div className="space-y-6">
          {/* Summary Card */}
          <Card className="bg-white/5 backdrop-blur-md border-purple-500/20">
            <CardContent className="p-6">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  {getStatusBadge(result.status)}
                  <Badge className="bg-purple-600/30 text-purple-200">
                    {result.objective}
                  </Badge>
                  {result.pharma_mode && (
                    <Badge className="bg-blue-600/30 text-blue-200">Pharma</Badge>
                  )}
                </div>
                <div className="flex items-center gap-2 text-purple-300/60 text-sm">
                  <Timer className="w-4 h-4" />
                  {result.total_duration_ms.toFixed(1)}ms
                </div>
              </div>

              {/* Score Summary */}
              <div className="grid grid-cols-4 gap-4">
                <div className="bg-white/5 rounded-lg p-4 text-center border border-purple-500/20">
                  <p className="text-purple-300/60 text-xs">Initial Score</p>
                  <p className="text-2xl font-bold text-white">{result.initial_score}</p>
                </div>
                <div className="bg-white/5 rounded-lg p-4 text-center border border-purple-500/20">
                  <p className="text-purple-300/60 text-xs">Final Score</p>
                  <p className="text-2xl font-bold text-green-400">{result.final_score}</p>
                </div>
                <div className="bg-white/5 rounded-lg p-4 text-center border border-purple-500/20">
                  <p className="text-purple-300/60 text-xs">Improvement</p>
                  <p className={`text-2xl font-bold ${result.total_improvement > 0 ? 'text-green-400' : result.total_improvement < 0 ? 'text-red-400' : 'text-yellow-400'}`}>
                    {result.total_improvement > 0 ? '+' : ''}{result.total_improvement}
                  </p>
                </div>
                <div className="bg-white/5 rounded-lg p-4 text-center border border-purple-500/20">
                  <p className="text-purple-300/60 text-xs">Iterations</p>
                  <p className="text-2xl font-bold text-white">{result.total_iterations}</p>
                </div>
              </div>

              {result.early_stopped && result.early_stop_reason && (
                <div className="mt-4 bg-green-500/10 rounded-lg p-3 border border-green-500/20 flex items-center gap-2">
                  <PauseCircle className="w-4 h-4 text-green-400 flex-shrink-0" />
                  <span className="text-green-200 text-sm">{result.early_stop_reason}</span>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Convergence Chart */}
          <ImprovementChart history={result.convergence_history} />

          {/* Iteration Details */}
          <Card className="bg-white/5 backdrop-blur-md border-purple-500/20">
            <CardHeader>
              <CardTitle className="text-white">Iteration Details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {result.convergence_history.map((h, i) => (
                <div key={i} className="bg-white/5 rounded-lg p-4 border border-purple-500/20">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-3">
                      <Badge className="bg-purple-600/30 text-purple-200">Iter {h.iteration}</Badge>
                      <span className={`text-sm font-mono font-bold ${h.improvement > 0 ? 'text-green-400' : h.improvement < 0 ? 'text-red-400' : 'text-yellow-400'}`}>
                        {h.improvement > 0 ? '↑' : h.improvement < 0 ? '↓' : '→'} {h.improvement > 0 ? '+' : ''}{h.improvement}
                      </span>
                    </div>
                    <div className="flex items-center gap-4 text-xs text-purple-300/60">
                      <span>{h.mutations_applied} mutations</span>
                      <span>{h.routes_evaluated} evaluated</span>
                      <span>{h.routes_kept} kept</span>
                      <span>{h.duration_ms}ms</span>
                    </div>
                  </div>

                  {/* Score change */}
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-white text-sm font-mono">{h.score_before}</span>
                    <ArrowRight className="w-4 h-4 text-purple-400" />
                    <span className={`text-sm font-mono font-bold ${h.score_after > h.score_before ? 'text-green-400' : 'text-white'}`}>
                      {h.score_after}
                    </span>
                  </div>

                  {/* Changes */}
                  {h.changes && h.changes.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {h.changes.map((change, ci) => (
                        <Badge key={ci} variant="outline" className="border-blue-500/30 text-blue-200 text-xs">
                          {change}
                        </Badge>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </CardContent>
          </Card>

          {/* Best Routes */}
          <Card className="bg-white/5 backdrop-blur-md border-purple-500/20">
            <CardHeader>
              <CardTitle className="text-white">
                Best Routes ({result.best_routes.length})
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {result.best_routes.map((route, idx) => (
                <div key={idx} className="bg-white/5 rounded-lg border border-purple-500/20">
                  <button
                    onClick={() => setExpandedRoute(expandedRoute === idx ? null : idx)}
                    className="w-full p-4 flex items-center justify-between text-left"
                  >
                    <div className="flex items-center gap-3">
                      <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${idx === 0 ? 'bg-green-600/40 text-green-300' : 'bg-white/10 text-purple-300'}`}>
                        {idx + 1}
                      </div>
                      <div>
                        <span className="text-white font-semibold text-sm">
                          {route.steps?.length || 0} steps
                        </span>
                        <div className="flex items-center gap-3 mt-0.5">
                          <span className="text-green-400 text-xs">
                            <TrendingUp className="w-3 h-3 inline mr-1" />
                            {route.overall_yield_percent || '?'}%
                          </span>
                          <span className="text-yellow-400 text-xs">
                            <DollarSign className="w-3 h-3 inline mr-1" />
                            ${route.total_cost_usd || '?'}
                          </span>
                          <span className="text-blue-400 text-xs">
                            {route.mutation_count || 0} mutations
                          </span>
                        </div>
                      </div>
                    </div>
                    {expandedRoute === idx ? (
                      <ChevronUp className="w-5 h-5 text-purple-300" />
                    ) : (
                      <ChevronDown className="w-5 h-5 text-purple-300" />
                    )}
                  </button>

                  {expandedRoute === idx && (
                    <div className="px-4 pb-4 border-t border-purple-500/20 pt-3 space-y-3">
                      {/* Steps */}
                      {(route.steps || []).map((step, si) => (
                        <div key={si} className="bg-slate-800/40 rounded-lg p-3">
                          <div className="flex items-center gap-2 mb-1">
                            <FlaskConical className="w-4 h-4 text-purple-400" />
                            <span className="text-white text-sm font-semibold">
                              Step {si + 1}: {step.reaction_type}
                            </span>
                          </div>
                          <div className="grid grid-cols-3 gap-2 mt-2">
                            {Object.entries(step.conditions || {}).map(([k, v]) => (
                              <div key={k} className="text-xs">
                                <span className="text-purple-300/60">{k.replace(/_/g, ' ')}:</span>{' '}
                                <span className="text-white font-mono">{v}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      ))}

                      {/* Mutations applied */}
                      {route.mutations_applied && route.mutations_applied.length > 0 && (
                        <div>
                          <p className="text-purple-300/70 text-xs mb-1">Mutations applied:</p>
                          <div className="space-y-1">
                            {route.mutations_applied.map((m, mi) => (
                              <div key={mi} className="flex items-center gap-2 text-xs">
                                <RefreshCw className="w-3 h-3 text-blue-400" />
                                <code className="text-red-300">{m.original}</code>
                                <ArrowRight className="w-3 h-3 text-purple-400" />
                                <code className="text-green-300">{m.new}</code>
                                <span className="text-purple-300/50">({m.reason})</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
};

export default ConvergenceLoopPage;
